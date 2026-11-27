"""Préstamo simulado, en meses comerciales y quincenas vencidas."""

import re
from decimal import Context, Decimal, DecimalException, ROUND_HALF_UP, localcontext

from .finance import money


def positive(value, label):
    raw = str(value)
    if not re.fullmatch(r"[0-9]{1,16}(?:\.[0-9]{1,16})?", raw) or Decimal(raw) <= 0:
        raise ValueError(f"{label} debe ser mayor que cero (hasta 16 dígitos enteros y 16 decimales).")
    return Decimal(raw)


def rate_text(rate):
    return format(rate.quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP), "f")


def simulate(payload):
    if set(payload) != {"principal", "tea", "late_tea", "months", "periods"}:
        raise ValueError("Indica monto, TEA, TEA de mora, plazo y configuración por periodo.")
    principal = positive(payload["principal"], "El monto")
    tea = positive(payload["tea"], "La TEA")
    late_tea = positive(payload["late_tea"], "La TEA de mora")
    months = payload["months"]
    if type(months) is not int or not 1 <= months <= 120:
        raise ValueError("El plazo debe ser un entero de 1 a 120 meses.")
    periods = payload["periods"]
    if not isinstance(periods, list) or len(periods) != 2 * months:
        raise ValueError("Configura dos periodos de 15 días por mes.")
    for row in periods:
        if not isinstance(row, dict) or row.get("grace") not in ("normal", "total", "partial"):
            raise ValueError("Selecciona el tipo de gracia de cada periodo.")
        days = row.get("days")
        if type(days) is not int or days < 0:
            raise ValueError("Los días de demora deben ser enteros mayores o iguales a cero.")
    if all(row["grace"] != "normal" for row in periods):
        raise ValueError("Al menos un periodo debe quedar sin gracia para amortizar el préstamo.")
    try:
        with localcontext(Context(prec=80)):
            return schedule(principal, tea / 100, late_tea / 100, periods)
    except DecimalException as exc:
        raise ValueError("El resultado excede la precisión admitida. Revisa las tasas y los días.") from exc


def schedule(principal, tea, late_tea, periods):
    growth = (1 + tea) ** (Decimal(15) / 360)
    # Valor actual de las cuotas normales unitarias que quedan desde cada fila.
    # La gracia parcial conserva el saldo; la total descuenta un periodo adicional.
    weights = [Decimal(0)] * (len(periods) + 1)
    for i in reversed(range(len(periods))):
        mode = periods[i]["grace"]
        weights[i] = (weights[i+1] if mode == "partial" else
                      (weights[i+1] + int(mode == "normal")) / growth)
    fixed = principal / weights[0]
    balance = principal
    rows = []
    interests = payments = penalties = Decimal(0)
    for i, row in enumerate(periods):
        interest = balance * (growth - 1)
        mode = row["grace"]
        if mode == "normal":
            payment = fixed if weights[i+1] else balance + interest
            capital = payment - interest
            closing = balance - capital if weights[i+1] else Decimal(0)
        else:
            capital = Decimal(0)
            payment = interest if mode == "partial" else Decimal(0)
            closing = balance if mode == "partial" else balance + interest
        late_rate = (1 + late_tea) ** (Decimal(row["days"]) / 360) - 1
        penalty = payment * late_rate
        rows.append(dict(period=i+1, day=(i+1)*15, opening=money(balance), interest=money(interest),
                         payment=money(payment), capital=money(capital), closing=money(closing),
                         late_rate=rate_text(late_rate), penalty=money(penalty), total=money(payment+penalty)))
        interests += interest
        payments += payment
        penalties += penalty
        balance = closing
    return dict(rows=rows, rate=rate_text(growth-1), principal=money(principal), interest=money(interests),
                penalty=money(penalties), total=money(payments+penalties))
