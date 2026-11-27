from collections import defaultdict
from datetime import date, datetime, time, timezone
from time import sleep
from zoneinfo import ZoneInfo

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from flask.cli import with_appcontext
from psycopg.types.json import Jsonb

from . import access, data, required
from .catalog import decimal_value, insert
from .db import connection
from .finance import ZERO, interest, month_day
from .sales import available, client_for_shop, instant

bp = Blueprint("collections", __name__, url_prefix="/api")


def document(result):
    if isinstance(result, dict):
        return {key: document(value) for key, value in result.items()}
    if isinstance(result, (list, tuple)):
        return [document(value) for value in result]
    if isinstance(result, date):
        return result.isoformat()
    return result


def installment_cutoff(due, terms):
    def day(offset):
        return month_day(due, offset, terms["cutoff_day"])

    cutoff = day(0)
    if cutoff >= due:
        cutoff = day(-1)
    return datetime.combine(
        cutoff, time.fromisoformat(terms["cutoff_time"]), ZoneInfo(terms["timezone"])
    ).astimezone(timezone.utc)


def generate(db, client, now):
    """El cierre se emite después del instante inclusivo, bajo el bloqueo del cliente."""
    scope = (client["shop_id"], client["id"])
    sales = db.execute(
        """SELECT s.* FROM sales s
           WHERE s.shop_id=%s AND s.client_id=%s AND s.cutoff_at<%s
           AND NOT EXISTS (SELECT 1 FROM statement_sales ss WHERE ss.sale_id=s.id)
           ORDER BY sold_at,id""", (*scope, now),
    ).fetchall()
    installments = db.execute(
        """SELECT i.id,i.due,s.currency,s.terms FROM installments i
           JOIN sales s ON i.sale_id=s.id AND i.shop_id=s.shop_id
           WHERE s.shop_id=%s AND s.client_id=%s AND i.amount>0
           AND NOT EXISTS (SELECT 1 FROM statement_installments si WHERE si.installment_id=i.id)
           ORDER BY i.due,i.id""", scope,
    ).fetchall()
    groups = defaultdict(lambda: {"sales": [], "installments": []})
    for sale in sales:
        groups[(sale["cutoff_at"], sale["reference_due"], sale["currency"])]["sales"].append(sale)
    for row in installments:
        cutoff = installment_cutoff(row["due"], row["terms"])
        if cutoff < now:
            groups[(cutoff, row["due"], row["currency"])]["installments"].append(row)
    for (cutoff, due, currency), group in sorted(groups.items()):
        single = [sale for sale in group["sales"] if sale["mode"] == "single"]
        statement = db.execute(
            """INSERT INTO statements (shop_id,client_id,cutoff_at,due,currency)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (shop_id,client_id,cutoff_at,due,currency)
               DO UPDATE SET currency=EXCLUDED.currency RETURNING id""", (*scope, cutoff, due, currency),
        ).fetchone()["id"]
        for sale in group["sales"]:
            insert(db, "statement_sales", dict(shop_id=scope[0], statement_id=statement, sale_id=sale["id"]))
        for row in group["installments"]:
            insert(db, "statement_installments", dict(
                shop_id=scope[0], statement_id=statement, installment_id=row["id"],
            ))
        if single:
            db.execute(
                """UPDATE statements SET single_capital=%s,single_interest=%s,single_rate=%s
                   WHERE shop_id=%s AND id=%s""",
                (sum(row["capital"] for row in single), sum(row["single_interest"] for row in single),
                 Jsonb(single[0]["terms"]["moratory"]), scope[0], statement),
            )
    return len(groups)


def liquidate(db, client, now):
    today = now.astimezone(ZoneInfo(client["timezone"])).date()
    scope = (client["shop_id"], client["id"], client["currency"], today)
    rows = db.execute(
        """SELECT 'statement' AS kind,st.id,st.due,st.single_capital AS capital,
                  st.single_interest AS interest,st.single_rate AS rate
           FROM statements st
           WHERE st.shop_id=%s AND st.client_id=%s AND st.currency=%s AND st.due<=%s
             AND st.single_capital>0
             AND NOT EXISTS (SELECT 1 FROM payment_allocations pa WHERE pa.statement_id=st.id)
           UNION ALL
           SELECT 'installment',i.id,i.due,i.capital,i.interest,s.terms->'moratory'
           FROM installments i JOIN sales s ON s.id=i.sale_id AND s.shop_id=i.shop_id
           WHERE s.shop_id=%s AND s.client_id=%s AND s.currency=%s AND i.due<=%s
             AND i.amount>0
             AND NOT EXISTS (SELECT 1 FROM payment_allocations pa WHERE pa.installment_id=i.id)
           ORDER BY due,kind,id""", (*scope, *scope),
    ).fetchall()
    for row in rows:
        days = (today - row["due"]).days
        row["days_late"] = days
        row["mora"] = interest(row["capital"] + row["interest"], row.pop("rate"), days)
        row["amount"] = row["capital"] + row["interest"] + row["mora"]
    totals = {field: sum((row[field] for row in rows), ZERO)
              for field in ("amount", "mora", "interest", "capital")}
    expected = [[row["kind"], row["id"], row["days_late"], str(row["amount"])] for row in rows]
    return {**totals, "rows": rows, "expected": expected}


def view_account(db, client, now):
    shop_id, client_id = client["shop_id"], client["id"]
    statements = db.execute(
        """SELECT st.*,pa.payment_id FROM statements st
           LEFT JOIN payment_allocations pa ON pa.statement_id=st.id
           WHERE st.shop_id=%s AND st.client_id=%s AND st.cutoff_at<%s
           ORDER BY st.cutoff_at DESC,st.due DESC,st.id""", (shop_id, client_id, now),
    ).fetchall()
    for state in statements:
        state["purchases"] = db.execute(
            """SELECT s.id,s.sold_at,s.mode,s.capital,s.single_interest,s.grace_interest,
                      (SELECT string_agg(product_name, ', ' ORDER BY id) FROM sale_lines WHERE sale_id=s.id) AS items
               FROM statement_sales link JOIN sales s ON s.id=link.sale_id
               WHERE link.shop_id=%s AND link.statement_id=%s ORDER BY s.sold_at,s.id""",
            (shop_id, state["id"]),
        ).fetchall()
        state["installments"] = db.execute(
            """SELECT i.id,i.sale_id,i.sequence,i.due,i.capital,i.interest,i.amount,pa.payment_id
               FROM statement_installments link JOIN installments i ON i.id=link.installment_id
               LEFT JOIN payment_allocations pa ON pa.installment_id=i.id
               WHERE link.shop_id=%s AND link.statement_id=%s ORDER BY i.due,i.sale_id,i.sequence""",
            (shop_id, state["id"]),
        ).fetchall()
    sales = db.execute(
        """SELECT id,sold_at,reference_due,mode,capital,principal_pending,currency
           FROM sales WHERE shop_id=%s AND client_id=%s AND sold_at<=%s ORDER BY sold_at DESC,id DESC""",
        (shop_id, client_id, now),
    ).fetchall()
    receipts = db.execute(
        """SELECT id,paid_at,currency,amount,capital,interest,mora FROM payments
           WHERE shop_id=%s AND client_id=%s AND paid_at<=%s ORDER BY paid_at DESC,id DESC""",
        (shop_id, client_id, now),
    ).fetchall()
    return document(dict(
        name=client["name"], currency=client["currency"], credit_limit=client["credit_limit"],
        credit_available=available(db, client), statements=statements, sales=sales, payments=receipts,
        liquidation=liquidate(db, client, now), timezone=client["timezone"],
    ))


@bp.post("/clients/<int:client_id>/account")
@access("shop")
def account(client_id):
    db = connection()
    client = client_for_shop(db, client_id, lock=True)
    now = instant(data().get("as_of"))
    generate(db, client, now)
    result = view_account(db, client, now)
    db.commit()
    return jsonify(result)


@bp.get("/my-account")
@access("client")
def my_account():
    db = connection()
    client = db.execute(
        """SELECT c.*,s.timezone FROM clients c JOIN shops s ON s.id=c.shop_id
           WHERE c.shop_id=%s AND c.user_id=%s FOR UPDATE OF c""",
        (g.user["shop_id"], g.user["id"]),
    ).fetchone()
    if not client:
        abort(404, "La cuenta no está disponible.")
    now = instant(request.args.get("as_of"))
    generate(db, client, now)
    result = view_account(db, client, now)
    db.commit()
    return jsonify(result)


def receipt(db, payment):
    rows = db.execute(
        """SELECT statement_id,installment_id,days_late,mora,interest,capital
           FROM payment_allocations WHERE shop_id=%s AND payment_id=%s ORDER BY id""",
        (payment["shop_id"], payment["id"]),
    ).fetchall()
    return document({**payment, "allocations": rows})


@bp.post("/clients/<int:client_id>/payments")
@access("shop")
def pay(client_id):
    db = connection()
    payload = data()
    client = client_for_shop(db, client_id, lock=True)
    key = required(payload, "idempotency_key")
    if len(key) > 128:
        abort(400, "La clave de reintento es demasiado larga.")
    amount = decimal_value(payload.get("amount"), "importe", money=True, positive=True)
    scope = (client["shop_id"], client_id)
    previous = db.execute(
        """SELECT * FROM payments WHERE shop_id=%s AND client_id=%s AND idempotency_key=%s""",
        (*scope, key),
    ).fetchone()
    if previous:
        if previous["amount"] != amount:
            abort(409, "La clave de reintento ya corresponde a otro importe.")
        return jsonify(receipt(db, previous))
    now = instant(payload.get("as_of"))
    generate(db, client, now)
    due = liquidate(db, client, now)
    if amount != due["amount"]:
        abort(409, "El cobro debe ser por el importe exigible íntegro.")
    if payload.get("expected") != due["expected"]:
        abort(409, "La liquidación cambió. Actualiza el estado de cuenta.")
    payment = store_payment(db, client, key, now, due)
    result = receipt(db, payment)
    db.commit()
    return jsonify(result), 201


def store_payment(db, client, key, now, due):
    scope = (client["shop_id"], client["id"])
    payment = insert(db, "payments", dict(
        shop_id=scope[0], client_id=scope[1], idempotency_key=key, paid_at=now,
        currency=client["currency"], **{key: due[key] for key in ("amount", "mora", "interest", "capital")},
    ))
    for row in due["rows"]:
        statement = row["id"] if row["kind"] == "statement" else None
        installment = row["id"] if statement is None else None
        insert(db, "payment_allocations", dict(
            shop_id=scope[0], payment_id=payment["id"], statement_id=statement, installment_id=installment,
            **{key: row[key] for key in ("days_late", "mora", "interest", "capital")},
        ))
        if statement is not None:
            db.execute(
                """UPDATE sales s SET principal_pending=s.principal_pending-s.capital
                   FROM statement_sales link WHERE link.shop_id=%s AND link.statement_id=%s
                   AND s.id=link.sale_id AND s.shop_id=link.shop_id AND s.mode='single'""",
                (scope[0], statement),
            )
        else:
            db.execute(
                """UPDATE sales s SET principal_pending=s.principal_pending-i.capital
                   FROM installments i WHERE i.shop_id=%s AND i.id=%s
                   AND s.id=i.sale_id AND s.shop_id=i.shop_id""", (scope[0], installment),
            )
    return payment


def close_cycles():
    db = connection()
    # Mismo orden de bloqueo para todas las ejecuciones programadas.
    clients = db.execute(
        """SELECT c.*,s.timezone FROM clients c JOIN shops s ON s.id=c.shop_id
           WHERE s.active AND EXISTS (SELECT 1 FROM sales x WHERE x.client_id=c.id)
           ORDER BY c.id FOR UPDATE OF c"""
    ).fetchall()
    now = instant()
    count = sum(generate(db, client, now) for client in clients)
    db.commit()
    return count


@click.command("close-cycles")
@click.option("--watch", is_flag=True, help="Procesa los cortes cada 15 segundos.")
@with_appcontext
def close_command(watch):
    app = current_app._get_current_object()
    while True:
        with app.app_context():
            count = close_cycles()
        if count or not watch:
            click.echo(f"Ciclos procesados: {count}")
        if not watch:
            break
        sleep(15)
