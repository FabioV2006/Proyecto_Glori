from pathlib import Path

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row


def connection():
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def close_connection(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate():
    db = connection()
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(642202620)")
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY)")
        applied = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
        for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            if path.name not in applied:
                db.execute(path.read_text(encoding="utf-8"))
                db.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))
