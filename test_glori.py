import os
import unittest
from uuid import uuid4


@unittest.skipUnless(os.getenv("GLORI_TEST_DATABASE_URL"), "Configura GLORI_TEST_DATABASE_URL")
class PostgresAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from glori import create_app

        cls.url = os.environ["GLORI_TEST_DATABASE_URL"]
        cls.schema = "test_glori_" + uuid4().hex
        identifier = sql.Identifier(cls.schema)
        with psycopg.connect(cls.url) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(identifier))

        def remove_schema():
            with psycopg.connect(cls.url) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(identifier))

        cls.addClassCleanup(remove_schema)
        cls.config = {
            "TESTING": True,
            "DATABASE_URL": make_conninfo(cls.url, options=f"-c search_path={cls.schema}"),
            "SECRET_KEY": "integration-secret",
        }
        cls.app = create_app(cls.config)
        run = cls.app.test_cli_runner().invoke
        for command in ("migrate", "migrate", "seed-demo", "seed-demo", "close-cycles"):
            result = run(args=[command])
            if result.exit_code:
                raise result.exception

    def sign_in(self, username):
        client = self.app.test_client()
        response = client.post("/api/login", json={"username": username, "password": "Glori-demo-2026"})
        self.assertEqual(response.status_code, 200)
        return client

    def test_roles_and_unauthorized_requests(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/api/shops").status_code, 401)
        self.assertEqual(guest.post("/api/login", json={"username": "demo.plataforma", "password": "incorrecta"}).status_code, 401)
        for username, role in (("gloria.admin", "shop"), ("gloria.cliente", "client")):
            user = self.sign_in(username)
            self.assertEqual(user.get("/api/me").json["role"], role)
            self.assertEqual(user.get("/api/shops").status_code, 403)
            self.assertEqual(user.patch("/api/shops/2", json={"active": False}).status_code, 403)
            self.assertEqual(user.post("/api/logout", json={}).status_code, 200)
            self.assertIsNone(user.get("/api/me").json)

    def test_showcase_is_ready_and_repeatable(self):
        run = self.app.test_cli_runner().invoke
        for _ in range(2):
            seeded = run(args=["seed-showcase"])
            if seeded.exception:
                raise seeded.exception
        platform = self.sign_in("demo.plataforma")
        self.assertEqual(sum(s["showcase"] for s in platform.get("/api/shops").json), 1)
        self.assertEqual(platform.post("/api/showcase/access", json={"role":"shop"}).status_code, 200)
        self.assertEqual(len(platform.get("/api/products").json), 5)
        clients = {c["name"]: c["id"] for c in platform.get("/api/clients").json}
        self.assertEqual(len(clients), 4)
        def account(name):
            return platform.post(f"/api/clients/{clients[name]}/account", json={}).json
        luis = account("Luis Medina")
        self.assertEqual(luis["liquidation"]["capital"], "129.00")
        self.assertEqual(len(luis["statements"][0]["purchases"]), 2)
        rosa = account("Rosa Campos")
        self.assertEqual(len(rosa["payments"]), 1)
        self.assertEqual(rosa["payments"][0]["capital"], "218.00")
        ana_id = clients["Ana Torres"]
        schedule = platform.get(f"/api/clients/{ana_id}/schedules").json[0]
        self.assertEqual([i["paid"] for i in schedule["installments"]], [True, False, False])
        self.assertEqual(platform.post("/api/showcase/access", json={"role":"client"}).status_code, 403)
        platform = self.sign_in("demo.plataforma")
        self.assertEqual(platform.post("/api/showcase/access", json={"role":"client"}).status_code, 200)
        self.assertEqual(platform.get("/api/my-account").json["name"], "Ana Torres")
        self.assertEqual(platform.get("/api/clients").status_code, 403)

    def test_web_bootstrap_health_and_demo_options(self):
        guest = self.app.test_client()
        self.assertEqual(guest.get("/healthz").json, {"ok": True})
        self.assertEqual(guest.get("/api/login-options").json, {"demo": False})
        cli = self.app.test_cli_runner()
        for password in ("initial-2026", "replacement-2026"):
            result = cli.invoke(args=["bootstrap-admin"], env={
                "GLORI_ADMIN_USERNAME": "hosted.test",
                "GLORI_ADMIN_PASSWORD": password,
            })
            self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(guest.post("/api/login", json={
            "username": "hosted.test", "password": "initial-2026",
        }).status_code, 200)
        self.assertEqual(guest.get("/api/me").json["role"], "platform")

    def test_shop_creation_deactivation_and_persistence(self):
        from glori import create_app
        from glori.db import connection

        platform = self.sign_in("demo.plataforma")
        shop = platform.post("/api/shops", json={
            "name": "Tienda de integración", "timezone": "America/Lima",
            "username": "integracion.admin", "password": "integracion-2026",
        })
        self.assertEqual(shop.status_code, 201)
        shop_id = shop.json["id"]
        staff = self.app.test_client()
        credentials = {"username": "integracion.admin", "password": "integracion-2026"}
        self.assertEqual(staff.post("/api/login", json=credentials).status_code, 200)
        self.assertEqual(staff.get("/api/me").json["shop_id"], shop_id)
        self.assertEqual(platform.patch(f"/api/shops/{shop_id}", json={"active": False}).status_code, 200)
        self.assertIsNone(staff.get("/api/me").json)
        self.assertEqual(staff.post("/api/login", json=credentials).status_code, 401)
        restarted = create_app(self.config)
        with restarted.app_context():
            db = connection()
            self.assertFalse(db.execute("SELECT active FROM shops WHERE id=%s", (shop_id,)).fetchone()["active"])
            stored = db.execute("SELECT password_hash FROM users WHERE shop_id=%s", (shop_id,)).fetchone()
            self.assertNotEqual(stored["password_hash"], credentials["password"])
        self.assertEqual(platform.patch(f"/api/shops/{shop_id}", json={"active": True}).status_code, 200)
        self.assertEqual(staff.post("/api/login", json=credentials).status_code, 200)

    def test_catalog_scoped_by_shop_and_soft_delete(self):
        shop = self.sign_in("gloria.admin")
        other = self.sign_in("panaderia.admin")
        payload = {
            "name": "Arroz", "kind": "producto", "description": "Arroz por kilo", "brand": "Gloria",
            "unit": "kg", "image": "data:image/png;base64,AAAA", "cash_price": "5.00",
            "credit_price": "6.00", "single_allowed": True, "monthly_allowed": False,
        }
        created = shop.post("/api/products", json=payload)
        self.assertEqual(created.status_code, 201)
        path = f"/api/products/{created.json['id']}"
        self.assertEqual(other.patch(path, json={"active": False}).status_code, 404)
        self.assertNotIn(created.json["id"], [row["id"] for row in other.get("/api/products").json])
        self.assertFalse(shop.patch(path, json={"active": False}).json["active"])
        self.assertEqual(next(row for row in shop.get("/api/products").json if row["id"] == created.json["id"])["credit_price"], "6.00")

    def test_client_conditions_portal_and_scope(self):
        shop = self.sign_in("gloria.admin")
        other = self.sign_in("panaderia.admin")
        payload = {
            "name": "Ana Demo", "username": "ana.demo", "password": "cliente-2026",
            "currency": "PEN", "credit_limit": "200.00", "max_months": 3,
            "cutoff_day": 20, "cutoff_time": "18:00", "payment_day": 26,
            "compensatory": {"kind": "nominal", "value": "0.240000001"},
            "moratory": {"kind": "effective", "value": "0.30", "period_days": 360},
        }
        self.assertEqual(shop.post("/api/clients", json=payload).status_code, 400)
        payload["compensatory"]["capitalization_days"] = 30
        created = shop.post("/api/clients", json=payload)
        self.assertEqual(created.status_code, 201)
        path = f"/api/clients/{created.json['id']}"
        self.assertEqual(other.put(path, json=payload).status_code, 404)
        client = self.app.test_client()
        self.assertEqual(client.post("/api/login", json={"username": "ana.demo", "password": "cliente-2026"}).status_code, 200)
        self.assertEqual(client.get("/api/my-profile").json["name"], "Ana Demo")
        self.assertEqual(client.get("/api/my-profile").json["compensatory"], payload["compensatory"])
        self.assertEqual(client.get("/api/clients").status_code, 403)
        self.assertFalse(shop.patch(path, json={"active": False}).json["active"])
        self.assertEqual(client.get("/api/my-profile").status_code, 401)

    def sales_fixture(self, label):
        shop = self.sign_in("gloria.admin")
        product = shop.post("/api/products", json={
            "name": label, "kind": "producto", "description": "Ejemplo", "brand": "Demo",
            "unit": "unidad", "image": "data:image/png;base64,AAAA", "cash_price": "90.00",
            "credit_price": "100.00", "single_allowed": True, "monthly_allowed": True,
        }).json
        client = shop.post("/api/clients", json={
            "name": label, "username": label.lower(), "password": "cliente-2026",
            "currency": "PEN", "credit_limit": "350.00", "max_months": 3, "cutoff_day": 20,
            "cutoff_time": "18:00", "payment_day": 26,
            "compensatory": {"kind": "effective", "value": "0.24", "period_days": 360},
            "moratory": {"kind": "effective", "value": "0.30", "period_days": 360},
        }).json
        return shop, product["id"], client["id"]

    def register_sale(self, shop, product, client, sold_at, mode="single", quantity=1):
        payload = dict(client_id=client, sold_at=sold_at, mode=mode, months=3,
                       lines=[dict(product_id=product, quantity=quantity)])
        preview = shop.post("/api/sales/preview", json=payload)
        self.assertEqual(preview.status_code, 200, preview.json)
        sale = shop.post("/api/sales", json={**payload, "expected": preview.json["expected"]})
        self.assertEqual(sale.status_code, 201, sale.json)
        return sale.json

    def test_sales_persist_original_conditions_and_limit(self):
        from glori.db import connection

        shop, product, client = self.sales_fixture("PruebaMensual")
        sale = self.register_sale(shop, product, client, "2026-09-15T12:00:00-05:00", "monthly")
        self.assertEqual(sale["grace_days"], 11)
        self.assertEqual([row["due"] for row in sale["installments"]],
                         ["2026-10-26", "2026-11-26", "2026-12-26"])
        self.assertEqual(shop.patch(f"/api/products/{product}", json={"active": False}).status_code, 200)
        with self.app.app_context():
            db = connection()
            stored = db.execute("SELECT * FROM sales WHERE id=%s", (sale["id"],)).fetchone()
            self.assertEqual(stored["terms"]["payment_day"], 26)
            self.assertEqual(db.execute("SELECT count(*) AS n FROM installments WHERE sale_id=%s", (sale["id"],)).fetchone()["n"], 3)
            self.assertEqual(db.execute("SELECT product_name FROM sale_lines WHERE sale_id=%s", (sale["id"],)).fetchone()["product_name"], "PruebaMensual")
        shop.patch(f"/api/products/{product}", json={"active": True})
        payload = dict(client_id=client, mode="single", lines=[dict(product_id=product, quantity=3)])
        self.assertEqual(shop.post("/api/sales/preview", json=payload).status_code, 409)
        other = self.sign_in("panaderia.admin")
        self.assertEqual(other.post("/api/sales/preview", json=payload).status_code, 404)
        schedule_path = f"/api/clients/{client}/schedules"
        self.assertEqual(other.get(schedule_path).status_code, 404)
        self.assertEqual(shop.get(schedule_path).json[0]["installments"][-1]["due"], "2026-12-26")
        self.assertEqual(other.get("/api/reports").json["currencies"], [])
        self.assertIn(sale["id"], [row["id"] for row in shop.get("/api/reports").json["latest"]])

    def test_concurrent_sales_cannot_exceed_credit_limit(self):
        from concurrent.futures import ThreadPoolExecutor

        shop, product, client = self.sales_fixture("CreditoConcurrente")
        payload = dict(client_id=client, mode="single", sold_at="2026-09-15T12:00:00-05:00",
                       lines=[dict(product_id=product, quantity=2)])
        quote = shop.post("/api/sales/preview", json=payload)
        self.assertEqual(quote.status_code, 200)
        request = {**payload, "expected": quote.json["expected"]}
        users = [self.sign_in("gloria.admin"), self.sign_in("gloria.admin")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda user: user.post("/api/sales", json=request), users))
        self.assertEqual(sorted(result.status_code for result in results), [201, 409])
        result = next(result for result in results if result.status_code == 201)
        self.assertEqual(result.json["credit_available"], "150.00")

    def test_cutoff_includes_exact_instant_and_charges_mora_per_cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        from glori import create_app
        from glori.db import connection

        shop, product, client = self.sales_fixture("CicloConCompras")
        path = f"/api/clients/{client}"
        first = self.register_sale(shop, product, client, "2026-09-15T12:00:00-05:00")
        cutoff = "2026-09-20T18:00:00-05:00"
        self.assertEqual(shop.post(path + "/account", json={"as_of": cutoff}).json["statements"], [])
        exact = self.register_sale(shop, product, client, cutoff)
        next_sale = self.register_sale(shop, product, client, "2026-09-20T18:00:01-05:00")
        just_closed = shop.post(path + "/account", json={"as_of": "2026-09-20T18:00:01-05:00"}).json
        self.assertEqual(len(just_closed["statements"]), 1)
        self.assertEqual([row["id"] for row in just_closed["statements"][0]["purchases"]], [first["id"], exact["id"]])
        punctual = shop.post(path + "/account", json={"as_of": "2026-09-26T10:00:00-05:00"}).json
        self.assertEqual(punctual["liquidation"]["mora"], "0.00")
        late = "2026-09-27T10:00:00-05:00"
        before = shop.post(path + "/account", json={"as_of": late}).json
        due = before["liquidation"]
        self.assertEqual(before["credit_available"], "50.00")
        self.assertEqual(len(due["rows"]), 1)
        self.assertEqual((due["capital"], due["interest"], due["mora"], due["amount"]),
                         ("200.00", "1.02", "0.15", "201.17"))
        request = dict(as_of=late, expected=due["expected"], amount=due["amount"], idempotency_key="retry-cycle")
        self.assertEqual(shop.post(path + "/payments", json={**request, "amount": "100.00"}).status_code, 409)
        self.assertEqual(shop.post(path + "/account", json={"as_of": late}).json["credit_available"], "50.00")
        other = self.sign_in("panaderia.admin")
        self.assertEqual(other.post(path + "/account", json={"as_of": late}).status_code, 404)
        self.assertEqual(other.post(path + "/payments", json=request).status_code, 404)
        browser_sessions = [self.sign_in("gloria.admin") for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda browser: browser.post(path + "/payments", json=request), browser_sessions))
        self.assertEqual(sorted(row.status_code for row in outcomes), [200, 201])
        self.assertEqual(outcomes[0].json["id"], outcomes[1].json["id"])
        after = shop.post(path + "/account", json={"as_of": late}).json
        self.assertEqual(after["credit_available"], "250.00")
        self.assertEqual(len(after["payments"]), 1)
        self.assertEqual(after["liquidation"]["amount"], "0.00")
        self.assertEqual(next(row for row in after["sales"] if row["id"] == next_sale["id"])["principal_pending"], "100.00")
        restarted = create_app(self.config)
        with restarted.app_context():
            db = connection()
            self.assertEqual(db.execute("SELECT count(*) AS n FROM payment_allocations WHERE payment_id=%s",
                                        (outcomes[0].json["id"],)).fetchone()["n"], 1)
            self.assertEqual(db.execute("SELECT count(*) AS n FROM statements WHERE client_id=%s", (client,)).fetchone()["n"], 1)
        customer = restarted.test_client()
        self.assertEqual(customer.post("/api/login", json={"username": "cicloconcompras", "password": "cliente-2026"}).status_code, 200)
        restored = customer.get("/api/my-account", query_string={"as_of": late}).json
        self.assertEqual(restored["payments"], after["payments"])
        self.assertEqual(restored["credit_available"], "250.00")

    def test_monthly_mora_is_per_due_installment_and_releases_amortization(self):
        from decimal import Decimal

        shop, product, client = self.sales_fixture("CuotasEnMora")
        sale = self.register_sale(shop, product, client, "2026-09-15T12:00:00-05:00", "monthly")
        now = "2026-11-27T12:00:00-05:00"
        path = f"/api/clients/{client}"
        before = shop.post(path + "/account", json={"as_of": now}).json
        due = before["liquidation"]
        self.assertEqual([row["kind"] for row in due["rows"]], ["installment", "installment"])
        self.assertEqual([row["days_late"] for row in due["rows"]], [32, 1])
        self.assertEqual([row["capital"] for row in due["rows"]], [row["capital"] for row in sale["installments"][:2]])
        self.assertTrue(all(Decimal(row["mora"]) > 0 for row in due["rows"]))
        payment = shop.post(path + "/payments", json=dict(
            as_of=now, expected=due["expected"], amount=due["amount"], idempotency_key="monthly",
        ))
        self.assertEqual(payment.status_code, 201, payment.json)
        self.assertEqual(len(payment.json["allocations"]), 2)
        after = shop.post(path + "/account", json={"as_of": now}).json
        self.assertEqual(Decimal(after["credit_available"]) - Decimal(before["credit_available"]), Decimal(due["capital"]))
        self.assertEqual(after["sales"][0]["principal_pending"], sale["installments"][2]["capital"])

    def test_payment_failure_rolls_back_receipt_and_allocations(self):
        from psycopg.errors import RaiseException
        from glori.db import connection

        shop, product, client = self.sales_fixture("CobroReversible")
        self.register_sale(shop, product, client, "2026-09-15T12:00:00-05:00")
        now = "2026-09-27T12:00:00-05:00"
        path = f"/api/clients/{client}"
        before = shop.post(path + "/account", json={"as_of": now}).json
        due = before["liquidation"]
        with self.app.app_context():
            db = connection()
            db.execute("""CREATE FUNCTION fail_payment() RETURNS trigger LANGUAGE plpgsql
                          AS $$ BEGIN RAISE EXCEPTION 'prueba de reversión'; END $$""")
            db.execute("""CREATE TRIGGER simulate_payment_error BEFORE UPDATE OF principal_pending ON sales
                          FOR EACH ROW EXECUTE FUNCTION fail_payment()""")
            db.commit()
        try:
            with self.assertRaises(RaiseException):
                shop.post(path + "/payments", json=dict(
                    as_of=now, expected=due["expected"], amount=due["amount"], idempotency_key="failure",
                ))
            after = shop.post(path + "/account", json={"as_of": now}).json
            self.assertEqual(after["liquidation"], due)
            self.assertEqual(after["credit_available"], before["credit_available"])
            self.assertEqual(after["payments"], [])
        finally:
            with self.app.app_context():
                db = connection()
                db.execute("DROP TRIGGER simulate_payment_error ON sales")
                db.execute("DROP FUNCTION fail_payment()")
                db.commit()
