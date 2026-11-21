import re
from datetime import time
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, g, jsonify, request
from psycopg import sql
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from . import access, credentials, data, required
from .db import connection

bp = Blueprint("catalog", __name__, url_prefix="/api")


def integer(payload, field, low, high):
    value = payload.get(field)
    if type(value) is not int or not low <= value <= high:
        abort(400, f"{field} debe ser un entero entre {low} y {high}.")
    return value


def decimal_value(value, field, *, money=False, positive=False):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)?", value):
        abort(400, f"{field} debe ser un decimal sin signo.")
    try:
        number = Decimal(value)
    except InvalidOperation:
        abort(400, f"{field} debe ser un decimal válido.")
    if (positive and not number) or number >= Decimal("1e16") or (
        money and number.as_tuple().exponent < -2
    ):
        abort(400, f"{field} está fuera del rango o precisión admitidos.")
    return number


def optional(payload, field):
    value = payload.get(field, "")
    if not isinstance(value, str):
        abort(400, f"{field} debe ser texto.")
    return value.strip()


def rate(payload, field):
    value = payload.get(field)
    if not isinstance(value, dict) or value.get("kind") not in ("effective", "nominal"):
        abort(400, f"Selecciona el tipo de tasa {field}.")
    result = {"kind": value["kind"], "value": str(decimal_value(value.get("value"), field))}
    if result["kind"] == "effective":
        result["period_days"] = integer(value, "period_days", 1, 360)
    else:
        result["capitalization_days"] = integer(value, "capitalization_days", 1, 360)
    return result


def currency_code(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}", value):
        abort(400, "Usa un código de moneda de tres letras.")
    return value.upper()


def product_values(payload):
    kind = required(payload, "kind")
    if kind not in ("producto", "servicio"):
        abort(400, "Selecciona producto o servicio.")
    image = required(payload, "image")
    if not re.fullmatch(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}", image):
        abort(400, "Sube una imagen PNG, JPEG o WebP.")
    single, monthly = payload.get("single_allowed"), payload.get("monthly_allowed")
    if type(single) is not bool or type(monthly) is not bool or not (single or monthly):
        abort(400, "Selecciona al menos una modalidad.")
    return dict(
        name=required(payload, "name"), kind=kind, description=required(payload, "description"),
        brand=required(payload, "brand"), unit=required(payload, "unit"),
        supplier=optional(payload, "supplier"), image=image,
        currency=currency_code(payload.get("currency", "PEN")),
        cash_price=decimal_value(payload.get("cash_price"), "precio contado", money=True),
        credit_price=decimal_value(payload.get("credit_price"), "precio crédito", money=True, positive=True),
        single_allowed=single, monthly_allowed=monthly,
    )


def client_values(payload):
    currency = currency_code(required(payload, "currency"))
    raw_time = required(payload, "cutoff_time")
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}(?::[0-9]{2})?", raw_time):
        abort(400, "Indica la hora local del corte.")
    try:
        cutoff = time.fromisoformat(raw_time)
    except ValueError:
        abort(400, "La hora de corte es inválida.")
    return dict(
        name=required(payload, "name"), document=optional(payload, "document"),
        phone=optional(payload, "phone"), email=optional(payload, "email"), currency=currency,
        credit_limit=decimal_value(payload.get("credit_limit"), "límite", money=True),
        max_months=integer(payload, "max_months", 1, 120),
        cutoff_day=integer(payload, "cutoff_day", 1, 31), cutoff_time=cutoff,
        payment_day=integer(payload, "payment_day", 1, 31),
        compensatory=Jsonb(rate(payload, "compensatory")), moratory=Jsonb(rate(payload, "moratory")),
    )


def insert(db, table, values):
    columns = list(map(sql.Identifier, values))
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table), sql.SQL(",").join(columns),
        sql.SQL(",").join([sql.Placeholder()] * len(columns)),
    )
    return db.execute(query, tuple(values.values())).fetchone()


def update(db, table, record_id, values):
    assignments = sql.SQL(",").join(
        sql.SQL("{}=%s").format(sql.Identifier(column)) for column in values
    )
    query = sql.SQL("UPDATE {} SET {} WHERE shop_id=%s AND id=%s RETURNING *").format(
        sql.Identifier(table), assignments
    )
    row = db.execute(query, (*values.values(), g.user["shop_id"], record_id)).fetchone()
    if not row:
        abort(404, "Registro no encontrado.")
    return row


def serialize_client(row):
    return {**row, "cutoff_time": row["cutoff_time"].isoformat()}


@bp.get("/products")
@access("shop")
def products():
    return jsonify(connection().execute(
        "SELECT * FROM products WHERE shop_id=%s ORDER BY active DESC,name,id", (g.user["shop_id"],)
    ).fetchall())


@bp.post("/products")
@access("shop")
def add_product():
    db = connection()
    row = insert(db, "products", {**product_values(data()), "shop_id": g.user["shop_id"]})
    db.commit()
    return jsonify(row), 201


@bp.route("/products/<int:record_id>", methods=["PUT", "PATCH"])
@access("shop")
def edit_product(record_id):
    db = connection()
    payload = data()
    if request.method == "PATCH":
        active = payload.get("active")
        if type(active) is not bool:
            abort(400, "Indica si el ítem está activo.")
        values = {"active": active}
    else:
        values = product_values(payload)
    row = update(db, "products", record_id, values)
    db.commit()
    return jsonify(row)


@bp.get("/clients")
@access("shop")
def clients():
    rows = connection().execute(
        """SELECT c.*,u.username,u.active FROM clients c JOIN users u ON u.id=c.user_id
           WHERE c.shop_id=%s ORDER BY u.active DESC,c.name,c.id""", (g.user["shop_id"],)
    ).fetchall()
    return jsonify([serialize_client(row) for row in rows])


@bp.post("/clients")
@access("shop")
def add_client():
    payload = data()
    settings = client_values(payload)
    username, password_hash = credentials(payload)
    db = connection()
    try:
        user = insert(db, "users", dict(
            username=username, password_hash=password_hash, role="client", shop_id=g.user["shop_id"],
        ))
        row = insert(db, "clients", {**settings, "shop_id": g.user["shop_id"], "user_id": user["id"]})
        db.commit()
    except UniqueViolation:
        db.rollback()
        abort(409, "Ese nombre de usuario ya existe.")
    return jsonify(serialize_client(row)), 201


@bp.put("/clients/<int:record_id>")
@access("shop")
def edit_client(record_id):
    db = connection()
    values = client_values(data())
    existing = db.execute(
        "SELECT currency FROM clients WHERE shop_id=%s AND id=%s FOR UPDATE",
        (g.user["shop_id"], record_id),
    ).fetchone()
    if not existing:
        abort(404, "Cliente no encontrado.")
    if values["currency"] != existing["currency"] and db.execute(
        """SELECT 1 FROM sales WHERE shop_id=%s AND client_id=%s AND principal_pending>0 LIMIT 1""",
        (g.user["shop_id"], record_id),
    ).fetchone():
        abort(409, "Cancela el capital pendiente antes de cambiar la moneda.")
    row = update(db, "clients", record_id, values)
    db.commit()
    return jsonify(serialize_client(row))


@bp.patch("/clients/<int:record_id>")
@access("shop")
def set_client_active(record_id):
    active = data().get("active")
    if type(active) is not bool:
        abort(400, "Indica si el cliente está activo.")
    db = connection()
    row = db.execute(
        """UPDATE users SET active=%s FROM clients
           WHERE users.id=clients.user_id AND clients.shop_id=%s AND clients.id=%s
           RETURNING users.active""", (active, g.user["shop_id"], record_id)
    ).fetchone()
    if not row:
        abort(404, "Cliente no encontrado.")
    db.commit()
    return jsonify(row)


@bp.get("/my-profile")
@access("client")
def my_profile():
    row = connection().execute(
        "SELECT * FROM clients WHERE shop_id=%s AND user_id=%s",
        (g.user["shop_id"], g.user["id"]),
    ).fetchone()
    return jsonify(serialize_client(row) if row else None)
