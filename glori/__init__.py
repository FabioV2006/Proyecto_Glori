import os
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
import psycopg
from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from psycopg.errors import UniqueViolation
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .db import close_connection, connection, migrate
from .simulator import simulate


def access(*roles):
    def decorate(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not g.user:
                abort(401, "Inicia sesión para continuar.")
            if g.user["role"] not in roles:
                abort(403, "Tu perfil no tiene acceso a esta operación.")
            return view(*args, **kwargs)
        return protected
    return decorate


def data():
    payload = request.get_json()
    if not isinstance(payload, dict):
        abort(400, "Se esperaba un objeto JSON.")
    return payload


def required(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        abort(400, f"Completa el campo {field}.")
    return value.strip()


def credentials(payload):
    username = required(payload, "username").lower()
    password = payload.get("password")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        abort(400, "La contraseña debe tener entre 8 y 128 caracteres.")
    return username, generate_password_hash(password)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("GLORI_SECRET"),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.environ.get("GLORI_HTTPS") == "1",
        MAX_CONTENT_LENGTH=3 * 1024 * 1024,
        DEMO_DATES=os.environ.get("GLORI_DEMO_DATES") == "1",
        SHOW_DEMO_ACCOUNTS=os.environ.get("GLORI_SHOW_DEMO_ACCOUNTS") == "1",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["DATABASE_URL"] or not app.config["SECRET_KEY"]:
        raise RuntimeError("Configura DATABASE_URL y GLORI_SECRET.")
    app.teardown_appcontext(close_connection)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.before_request
    def load_user():
        g.user = None
        if not request.path.startswith("/api/"):
            return
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.is_json:
            abort(415, "Envía una solicitud JSON.")
        user_id = session.get("user_id")
        if user_id:
            g.user = connection().execute(
                """SELECT u.id, u.username, u.role, u.shop_id, s.name AS shop_name,
                          s.timezone, s.active AS shop_active
                   FROM users u LEFT JOIN shops s ON s.id = u.shop_id
                   WHERE u.id = %s AND u.active AND (s.id IS NULL OR s.active)""",
                (user_id,),
            ).fetchone()
            if not g.user:
                session.clear()

    @app.post("/api/login")
    def login():
        payload = data()
        user = connection().execute(
            """SELECT u.id, u.password_hash
               FROM users u LEFT JOIN shops s ON s.id = u.shop_id
               WHERE u.username = %s AND u.active AND (s.id IS NULL OR s.active)""",
            (required(payload, "username").lower(),),
        ).fetchone()
        password = payload.get("password")
        if not user or not isinstance(password, str) or not check_password_hash(
            user["password_hash"], password
        ):
            abort(401, "Usuario o contraseña incorrectos.")
        session.clear()
        session["user_id"] = user["id"]
        return jsonify(ok=True)

    @app.post("/api/simulator")
    @access("shop")
    def loan_simulator():
        try:
            return jsonify(simulate(data()))
        except ValueError as error:
            abort(400, str(error))

    @app.get("/api/me")
    def me():
        return jsonify({**g.user, "demo_dates": app.config["DEMO_DATES"]} if g.user else None)

    @app.get("/api/login-options")
    def login_options():
        return jsonify(demo=app.config["SHOW_DEMO_ACCOUNTS"])

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/shops")
    @access("platform")
    def shops():
        return jsonify(connection().execute("SELECT * FROM shops ORDER BY id").fetchall())

    @app.post("/api/shops")
    @access("platform")
    def add_shop():
        payload = data()
        name = required(payload, "name")
        timezone = required(payload, "timezone")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            abort(400, "Usa una zona horaria IANA válida.")
        username, password_hash = credentials(payload)
        db = connection()
        try:
            shop = db.execute(
                "INSERT INTO shops (name, timezone) VALUES (%s, %s) RETURNING *", (name, timezone)
            ).fetchone()
            db.execute(
                "INSERT INTO users (username,password_hash,role,shop_id) VALUES (%s,%s,'shop',%s)",
                (username, password_hash, shop["id"]),
            )
            db.commit()
        except UniqueViolation:
            db.rollback()
            abort(409, "Ese nombre de usuario ya existe.")
        return jsonify(shop), 201

    @app.patch("/api/shops/<int:shop_id>")
    @access("platform")
    def update_shop(shop_id):
        active = data().get("active")
        if type(active) is not bool:
            abort(400, "Indica si la tienda está activa.")
        db = connection()
        shop = db.execute("UPDATE shops SET active=%s WHERE id=%s RETURNING *", (active, shop_id)).fetchone()
        if not shop:
            abort(404)
        db.commit()
        return jsonify(shop)

    @app.cli.command("migrate")
    def migrate_command():
        migrate()
        click.echo("Migraciones aplicadas.")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin(username, password):
        login_name, password_hash = credentials({"username": username, "password": password})
        db = connection()
        db.execute(
            "INSERT INTO users (username,password_hash,role) VALUES (%s,%s,'platform')",
            (login_name, password_hash),
        )
        db.commit()

    @app.cli.command("bootstrap-admin")
    @click.option("--username", envvar="GLORI_ADMIN_USERNAME", default="admin")
    @click.option("--password", envvar="GLORI_ADMIN_PASSWORD", required=True)
    def bootstrap_admin(username, password):
        """Crea el administrador inicial de forma idempotente."""
        username = username.strip().lower()
        if not username or not 8 <= len(password) <= 128:
            raise click.ClickException("Configura el usuario y una contraseña de 8 a 128 caracteres.")
        db = connection()
        existing = db.execute("SELECT role FROM users WHERE username=%s", (username,)).fetchone()
        if existing and existing["role"] != "platform":
            raise click.ClickException("El usuario inicial ya pertenece a otro perfil.")
        if not existing:
            db.execute(
                """INSERT INTO users (username,password_hash,role) VALUES (%s,%s,'platform')
                   ON CONFLICT (username) DO NOTHING""",
                (username, generate_password_hash(password)),
            )
        db.commit()

    @app.cli.command("seed-demo")
    def seed_demo():
        db = connection()
        with db.transaction():
            db.execute("SELECT pg_advisory_xact_lock(642202621)")
            password_hash = generate_password_hash("Glori-demo-2026")
            db.execute(
                """INSERT INTO users (username,password_hash,role) VALUES ('demo.plataforma',%s,'platform')
                   ON CONFLICT (username) DO NOTHING""",
                (password_hash,),
            )
            for name, prefix in (("Bodegas Gloria", "gloria"), ("Panadería del Barrio", "panaderia")):
                shop = db.execute("SELECT shop_id AS id FROM users WHERE username=%s", (f"{prefix}.admin",)).fetchone()
                if not shop:
                    shop = db.execute(
                        "INSERT INTO shops (name,timezone) VALUES (%s,'America/Lima') RETURNING id", (name,)
                    ).fetchone()
                    for role, suffix in (("shop", "admin"), ("client", "cliente")):
                        db.execute(
                            """INSERT INTO users (username,password_hash,role,shop_id)
                               VALUES (%s,%s,%s,%s)""", (f"{prefix}.{suffix}", password_hash, role, shop["id"]),
                        )
                customer = db.execute(
                    "SELECT id FROM users WHERE username=%s", (f"{prefix}.cliente",),
                ).fetchone()
                if customer:
                    db.execute(
                        """INSERT INTO clients
                           (shop_id,user_id,name,currency,credit_limit,max_months,cutoff_day,cutoff_time,
                            payment_day,compensatory,moratory)
                           VALUES (%s,%s,%s,'PEN',500,6,20,'18:00',26,
                              '{"kind":"effective","value":"0.24","period_days":360}',
                              '{"kind":"effective","value":"0.30","period_days":360}')
                           ON CONFLICT (user_id) DO NOTHING""",
                        (shop["id"], customer["id"], f"Cliente de {name}"),
                    )
                db.execute(
                    """INSERT INTO products
                       (shop_id,name,kind,description,brand,unit,image,cash_price,credit_price,
                        single_allowed,monthly_allowed,currency)
                       SELECT %s,%s,'producto','Paquete de demostración','Demo','unidad',
                              %s,90,100,true,true,'PEN'
                       WHERE NOT EXISTS (SELECT 1 FROM products WHERE shop_id=%s AND name=%s)""",
                    (shop["id"], "Canasta de demostración",
                     "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l2kAAAAASUVORK5CYII=",
                     shop["id"], "Canasta de demostración"),
                )

    dist = Path(__file__).resolve().parent.parent / "dist"

    @app.get("/")
    def index():
        return send_from_directory(dist, "index.html")

    @app.get("/healthz")
    def health():
        try:
            connection().execute("SELECT 1 FROM schema_migrations LIMIT 1")
        except psycopg.Error:
            return jsonify(ok=False), 503
        return jsonify(ok=True)

    @app.get("/assets/<path:name>")
    def asset(name):
        return send_from_directory(dist / "assets", name)

    from .catalog import bp as catalog
    from .collections import bp as collections, close_command
    from .reporting import bp as reporting
    from .sales import bp as sales

    app.register_blueprint(catalog)
    app.register_blueprint(sales)
    app.register_blueprint(collections)
    app.register_blueprint(reporting)
    app.cli.add_command(close_command)
    return app
