"""Préstamo simulado, en meses comerciales y quincenas vencidas."""

import re
from decimal import Context, Decimal, DecimalException, ROUND_HALF_UP, localcontext

from .finance import money


def positive(value, label, decimals=16):
    raw = str(value)
    if not re.fullmatch(rf"[0-9]{{1,16}}(?:\.[0-9]{{1,{decimals}}})?", raw) or Decimal(raw) <= 0:
        raise ValueError(f"{label} debe ser mayor que cero (hasta 16 dígitos enteros y {decimals} decimales).")
    return Decimal(raw)


def rate_text(rate):
    rounded = rate.quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


def simulate(payload):
    required = {"principal", "tea", "late_tea", "months", "periods"}
    if not required <= payload.keys() or payload.keys() - required - {"initial", "rate_change"}:
        raise ValueError("Indica monto, TEA, TEA de mora, plazo y configuración por periodo.")
    principal = positive(payload["principal"], "El monto", decimals=2 if "initial" in payload else 16)
    tea = positive(payload["tea"], "La TEA", decimals=7)
    late_tea = positive(payload["late_tea"], "La TEA de mora", decimals=7)
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
    initial = str(payload.get("initial", "0"))
    if not re.fullmatch(r"[0-9]{1,16}(?:\.[0-9]{1,2})?", initial) or Decimal(initial) >= principal:
        raise ValueError("La inicial debe ser menor que el precio y tener hasta dos decimales.")
    change = payload.get("rate_change")
    if change is not None:
        if (not isinstance(change, dict) or type(change.get("period")) is not int
                or not 2 <= change["period"] <= len(periods)):
            raise ValueError("El cambio de TEA debe empezar entre la segunda y la última cuota.")
        change = (change["period"] - 1, positive(change.get("tea"), "La nueva TEA", decimals=7))
    try:
        with localcontext(Context(prec=80)):
            funded = principal - Decimal(initial)
            annual = [tea] * len(periods)
            if change:
                start, new_tea = change
                annual[start:] = [new_tea] * (len(periods) - start)
            result = schedule(funded, annual, late_tea / 100, periods)
            total = result.pop("total_exact")
            return {**result, "price": money(principal), "initial": money(Decimal(initial)),
                    "sale_total": money(total + Decimal(initial))}
    except DecimalException as exc:
        raise ValueError("El resultado excede la precisión admitida. Revisa las tasas y los días.") from exc


def schedule(principal, annual, late_tea, periods, period_days=15):
    growth = [(1 + tea / 100) ** (Decimal(period_days) / 360) for tea in annual]
    # En cada cambio se recalcula la cuota sobre el saldo y plazo restantes.
    # La proyección usa la tasa vigente hasta el siguiente recálculo.
    last_normal = max(i for i, row in enumerate(periods) if row["grace"] == "normal")
    balance = principal
    rows = []
    interests = payments = penalties = Decimal(0)
    for i, row in enumerate(periods):
        if i == 0 or annual[i] != annual[i-1]:
            weight = Decimal(0)
            for future in reversed(periods[i:]):
                if future["grace"] != "partial":
                    weight = (weight + int(future["grace"] == "normal")) / growth[i]
            fixed = balance / weight if weight else Decimal(0)
        effective = growth[i] - 1
        interest = balance * effective
        mode = row["grace"]
        if mode == "normal":
            payment = balance + interest if i == last_normal else fixed
            capital = payment - interest
            closing = Decimal(0) if i == last_normal else balance - capital
        else:
            capital = Decimal(0)
            payment = interest if mode == "partial" else Decimal(0)
            closing = balance if mode == "partial" else balance + interest
        late_rate = (1 + late_tea) ** (Decimal(row["days"]) / 360) - 1
        penalty = payment * late_rate
        rows.append(dict(period=i+1, day=(i+1)*period_days, opening=money(balance), interest=money(interest),
                         tea=rate_text(annual[i]), rate_percent=rate_text(effective*100),
                         late_percent=rate_text(late_rate*100),
                         payment=money(payment), capital=money(capital), closing=money(closing),
                         late_rate=rate_text(late_rate), penalty=money(penalty), total=money(payment+penalty)))
        interests += interest
        payments += payment
        penalties += penalty
        balance = closing
    return dict(rows=rows, rate=rate_text(growth[0]-1), principal=money(principal), interest=money(interests),
                penalty=money(penalties), total=money(payments+penalties), total_exact=payments+penalties)
