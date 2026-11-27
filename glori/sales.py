from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, g, jsonify
from psycopg.types.json import Jsonb

from . import access, data
from .catalog import insert, integer
from .db import connection
from .finance import factor, quote
from .simulator import rate_text

bp = Blueprint("sales", __name__, url_prefix="/api")


def client_for_shop(db, client_id, *, lock=False):
    query = """SELECT c.*,u.active,s.timezone FROM clients c
               JOIN users u ON u.id=c.user_id JOIN shops s ON s.id=c.shop_id
               WHERE c.shop_id=%s AND c.id=%s"""
    if lock:
        query += " FOR UPDATE OF c,u"
    row = db.execute(query, (g.user["shop_id"], client_id)).fetchone()
    if not row:
        abort(404, "Cliente no encontrado.")
    return row


def instant(raw=None):
    if raw in (None, ""):
        clock = current_app.config.get("CLOCK")
        return clock() if clock else datetime.now(timezone.utc)
    if not (current_app.testing or current_app.config.get("DEMO_DATES")):
        abort(400, "La fecha de registro se toma del servidor.")
    try:
        value = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        abort(400, "Fecha y hora inválidas.")
    if value.utcoffset() is None:
        abort(400, "La fecha requiere un desplazamiento horario.")
    return value.astimezone(timezone.utc)


def available(db, client):
    used = db.execute(
        """SELECT COALESCE(sum(principal_pending),0) AS used
           FROM sales WHERE shop_id=%s AND client_id=%s AND currency=%s""",
        (client["shop_id"], client["id"], client["currency"]),
    ).fetchone()["used"]
    return client["credit_limit"] - used


def format_sale(plan):
    dates = {key: plan[key].isoformat() for key in ("sold_at", "cutoff_at", "reference_due")}
    return {**plan, **dates, "installments": [
        {**item, "due": item["due"].isoformat()} for item in plan["installments"]
    ]}


def prepare(db, payload, *, lock):
    client = client_for_shop(db, integer(payload, "client_id", 1, 2**53-1), lock=lock)
    if not client["active"]:
        abort(409, "El cliente está inactivo.")
    mode = payload.get("mode")
    if mode not in ("single", "monthly"):
        abort(400, "Selecciona una modalidad de crédito.")
    months = integer(payload, "months", 1, client["max_months"]) if mode == "monthly" else 0
    sold_at = instant(payload.get("sold_at"))
    requested_lines = payload.get("lines")
    if not isinstance(requested_lines, list) or not 1 <= len(requested_lines) <= 100:
        abort(400, "Agrega de 1 a 100 líneas de venta.")
    quantities = {}
    for line in requested_lines:
        if not isinstance(line, dict):
            abort(400, "Línea inválida.")
        product_id = integer(line, "product_id", 1, 2**53-1)
        if product_id in quantities:
            abort(400, "Agrupa la cantidad de los ítems repetidos.")
        quantities[product_id] = integer(line, "quantity", 1, 10000)
    query = "SELECT * FROM products WHERE shop_id=%s AND id=ANY(%s) AND active ORDER BY id"
    if lock:
        query += " FOR SHARE"
    products = db.execute(query, (client["shop_id"], list(quantities))).fetchall()
    if len(products) != len(quantities):
        abort(409, "Hay ítems inactivos o ajenos al catálogo de la tienda.")
    lines = []
    for item in products:
        if not item[mode + "_allowed"]:
            abort(409, f"{item['name']} no admite esa modalidad.")
        if item["currency"] != client["currency"]:
            abort(409, f"{item['name']} está cotizado en otra moneda.")
        lines.append(dict(
            product_id=item["id"], product_name=item["name"], description=item["description"],
            unit=item["unit"], quantity=quantities[item["id"]], price=item["credit_price"],
        ))
    principal = sum(row["price"] * row["quantity"] for row in lines)
    credit = available(db, client)
    if principal > credit:
        abort(409, "La venta supera el crédito disponible.")
    plan = quote(principal, sold_at, client["timezone"], client, mode, months)
    if plan["financed_principal"] > credit:
        abort(409, "El capital con la gracia acumulada supera el crédito disponible.")
    scope = (client["shop_id"], client["id"], plan["cutoff_at"])
    if db.execute(
        """SELECT 1 FROM statements WHERE shop_id=%s AND client_id=%s AND cutoff_at=%s
           AND due=%s AND currency=%s""", (*scope, plan["reference_due"], client["currency"]),
    ).fetchone():
        abort(409, "Ya se emitió el estado de cuenta de ese ciclo.")
    if mode == "single":
        existing = db.execute(
            """SELECT terms->'moratory' AS moratory,reference_due,currency FROM sales
               WHERE shop_id=%s AND client_id=%s AND cutoff_at=%s AND mode='single' LIMIT 1""", scope,
        ).fetchone()
        if existing and (
            existing["moratory"] != client["moratory"] or existing["reference_due"] != plan["reference_due"]
            or existing["currency"] != client["currency"]
        ):
            abort(409, "El ciclo ya tiene compras con otro vencimiento, moneda o tasa moratoria.")
    return client, mode, months, lines, plan, credit


def quote_key(plan, client, mode, lines):
    return {
        "reference_due": plan["reference_due"].isoformat(),
        "cutoff_at": plan["cutoff_at"].isoformat(),
        "capital": str(plan["capital"]), "financed_principal": str(plan["financed_principal"]),
        "single_interest": str(plan["single_interest"]),
        "payments": [str(row["amount"]) for row in plan["installments"]],
        "mode": mode, "currency": client["currency"], "compensatory": client["compensatory"],
        "moratory": client["moratory"],
        "lines": [[line["product_id"], line["quantity"], str(line["price"])] for line in lines],
    }


@bp.post("/sales/preview")
@access("shop")
def preview():
    client, mode, _, lines, plan, credit = prepare(connection(), data(), lock=False)
    return jsonify({
        **format_sale(plan), "lines": lines, "credit_available": credit, "currency": client["currency"],
        "mode": mode, "expected": quote_key(plan, client, mode, lines),
    })


@bp.post("/sales")
@access("shop")
def confirm():
    db = connection()
    payload = data()
    client, mode, months, lines, plan, credit = prepare(db, payload, lock=True)
    if payload.get("expected") != quote_key(plan, client, mode, lines):
        abort(409, "La cotización cambió. Revisa la nueva vista previa antes de confirmar.")
    sale = store_sale(db, client, mode, months, lines, plan)
    db.commit()
    return jsonify({
        **format_sale(plan), "id": sale["id"], "mode": mode, "lines": lines,
        "currency": client["currency"], "credit_available": credit - plan["financed_principal"],
    }), 201


def store_sale(db, client, mode, months, lines, plan):
    terms = {key: client[key] for key in (
        "cutoff_day", "payment_day", "compensatory", "moratory", "timezone", "max_months",
    )}
    terms["cutoff_time"] = client["cutoff_time"].isoformat()
    shop_id = client["shop_id"]
    sale = insert(db, "sales", {
        **{key: value for key, value in plan.items() if key != "installments"},
        "shop_id": shop_id, "client_id": client["id"], "currency": client["currency"],
        "mode": mode, "months": months, "terms": Jsonb(terms),
        "principal_pending": plan["financed_principal"],
    })
    for item in lines:
        insert(db, "sale_lines", {**item, "shop_id": shop_id, "sale_id": sale["id"]})
    for item in plan["installments"]:
        insert(db, "installments", {**item, "shop_id": shop_id, "sale_id": sale["id"]})
    return sale


@bp.get("/clients/<int:client_id>/schedules")
@access("shop")
def schedules(client_id):
    db = connection()
    client = client_for_shop(db, client_id)
    rows = db.execute(
        """SELECT id,sold_at,cutoff_at,reference_due,currency,capital,financed_principal,
                  principal_pending,grace_days,grace_interest,terms
           FROM sales WHERE shop_id=%s AND client_id=%s AND mode='monthly'
           ORDER BY sold_at DESC,id DESC""", (client["shop_id"], client_id),
    ).fetchall()
    for sale in rows:
        rate = sale.pop("terms")["compensatory"]
        sale["tea"] = rate_text((factor(rate, 360) - 1) * 100)
        sale["period_rate"] = rate_text((factor(rate, 30) - 1) * 100)
        sale["installments"] = db.execute(
            """SELECT i.sequence,i.due,i.opening,i.interest,i.capital,i.amount,i.closing,
                      pa.payment_id IS NOT NULL AS paid
               FROM installments i LEFT JOIN payment_allocations pa ON pa.installment_id=i.id
               WHERE i.shop_id=%s AND i.sale_id=%s ORDER BY i.sequence""",
            (client["shop_id"], sale["id"]),
        ).fetchall()
    return jsonify([format_sale(row) for row in rows])
