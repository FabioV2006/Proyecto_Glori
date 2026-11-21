from flask import Blueprint, g, jsonify

from . import access
from .collections import document
from .db import connection


bp = Blueprint("reporting", __name__, url_prefix="/api")


@bp.get("/shop")
@access("shop")
def shop():
    return jsonify(connection().execute(
        "SELECT id,name,timezone,active FROM shops WHERE id=%s", (g.user["shop_id"],)
    ).fetchone())


@bp.get("/reports")
@access("shop")
def reports():
    db = connection()
    scope = (g.user["shop_id"],)
    levels = db.execute(
        """SELECT (SELECT count(*) FROM products WHERE shop_id=%s AND active) AS products,
               (SELECT count(*) FROM clients c JOIN users u ON u.id=c.user_id
                 WHERE c.shop_id=%s AND u.active) AS clients""", (*scope, *scope),
    ).fetchone()
    currencies = db.execute(
        """WITH sold AS (
               SELECT currency,sum(capital) AS original,sum(principal_pending) AS pending,count(*) AS sales
               FROM sales WHERE shop_id=%s GROUP BY currency
           ), collected AS (
               SELECT currency,sum(capital) AS recovered,sum(interest) AS interest,sum(mora) AS mora,
               sum(amount) AS received,count(*) AS payments
               FROM payments WHERE shop_id=%s GROUP BY currency
           )
           SELECT currency,COALESCE(original,0.00) AS original,COALESCE(pending,0.00) AS pending,
                  COALESCE(recovered,0.00) AS recovered,COALESCE(interest,0.00) AS interest,
                  COALESCE(mora,0.00) AS mora,COALESCE(received,0.00) AS received,
                  COALESCE(sales,0) AS sales,COALESCE(payments,0) AS payments
           FROM sold FULL JOIN collected USING(currency) ORDER BY currency""", (*scope, *scope),
    ).fetchall()
    latest = db.execute(
        """SELECT s.id,s.sold_at,c.name,s.mode,s.currency,s.capital
           FROM sales s JOIN clients c ON c.shop_id=s.shop_id AND c.id=s.client_id
           WHERE s.shop_id=%s ORDER BY s.sold_at DESC,s.id DESC LIMIT 8""", scope,
    ).fetchall()
    return jsonify(document({**levels, "currencies": currencies, "latest": latest}))
