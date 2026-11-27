"""Carga transaccional de la tienda ficticia para la exposición."""
from base64 import b64encode
from datetime import datetime, time, timedelta
from pathlib import Path
from secrets import token_hex, token_urlsafe
from zoneinfo import ZoneInfo

from werkzeug.security import generate_password_hash

from .catalog import client_values, insert, product_values
from .collections import generate, liquidate, store_payment
from .finance import month_day, quote
from .sales import store_sale


def populate(db, today):
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(642202626)")
        if db.execute("SELECT 1 FROM showcase").fetchone():
            return
        zone = ZoneInfo("America/Lima")
        shop = insert(db, "shops", dict(name="Bodega Santa Rosa · Demostración", timezone=zone.key))
        namespace = token_hex(6)

        def user(alias, role):
            return insert(db, "users", dict(username=f"muestra.{namespace}.{alias}", role=role,
                        password_hash=generate_password_hash(token_urlsafe(32)), shop_id=shop["id"]))

        merchant = user("tienda", "shop")
        products = []
        for name, icon, unit, price, credit in [
            ("Arroz extra", "arroz", "saco de 5 kg", "22.50", "24.00"),
            ("Leche evaporada", "leche", "paquete de 6 latas", "24.00", "26.00"),
            ("Huevos de corral", "huevos", "bandeja de 30", "17.50", "19.00"),
            ("Café de Chanchamayo", "cafe", "bolsa de 250 g", "16.50", "18.00"),
            ("Canasta familiar", "canasta", "canasta", "90.00", "100.00"),
        ]:
            image = (Path(__file__).with_name("showcase_images") / (icon + ".png")).read_bytes()
            values = product_values(dict(name=name, kind="producto", description=f"{name}, presentación por {unit}.",
                brand="Santa Rosa", unit=unit, supplier="Distribuidora Valle Central", cash_price=price,
                credit_price=credit, single_allowed=True, monthly_allowed=True,
                image="data:image/png;base64," + b64encode(image).decode("ascii")))
            products.append(insert(db, "products", dict(shop_id=shop["id"], **values)))

        clients = []
        for name, alias, limit in [("Ana Torres", "ana", "1500"), ("Luis Medina", "luis", "800"),
                                   ("Rosa Campos", "rosa", "1200"), ("Diego Salas", "diego", "600")]:
            customer = user(alias, "client")
            rate = dict(kind="effective", value="0.25", period_days=360)
            values = client_values(dict(name=name, currency="PEN", credit_limit=limit, max_months=6,
                cutoff_day=20, cutoff_time="18:00", payment_day=26, compensatory=rate,
                moratory={**rate, "value":"0.60"}))
            client = insert(db, "clients", dict(shop_id=shop["id"], user_id=customer["id"], **values))
            clients.append({**client, "timezone":zone.key})
        ana, luis, rosa, _ = clients

        def at(offset, day, hour=12):
            return datetime.combine(month_day(today.date(), offset, day), time(hour), zone)

        def sale(client, when, mode, months, basket):
            lines = [dict(product_id=p["id"], product_name=p["name"], description=p["description"],
                          unit=p["unit"], quantity=n, price=p["credit_price"]) for p,n in basket]
            principal = sum(line["price"] * line["quantity"] for line in lines)
            plan = quote(principal, when, zone.key, client, mode, months)
            store_sale(db, client, mode, months, lines, plan)

        rice, milk, eggs, coffee, basket = products
        sale(ana, at(-2, 15), "monthly", 3, [(basket, 3)])
        sale(luis, at(-1, 15), "single", 0, [(rice, 2), (milk, 1)])
        sale(luis, at(-1, 20, 18), "single", 0, [(eggs, 1), (coffee, 2)])
        sale(rosa, at(-1, 12), "single", 0, [(basket, 2), (coffee, 1)])
        sale(rosa, today - timedelta(minutes=1), "monthly", 3, [(milk, 2), (rice, 1)])
        for client, when in [(ana, at(-1, 26)), (rosa, at(-1, 29))]:
            generate(db, client, when)
            due = liquidate(db, client, when)
            store_payment(db, client, "presentacion-inicial", when, due)
        for client in clients:
            generate(db, client, today)
        insert(db, "showcase", dict(shop_id=shop["id"], merchant_id=merchant["id"], customer_id=ana["user_id"]))
