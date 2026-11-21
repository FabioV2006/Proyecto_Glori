"""Cálculos SI642 independientes de Flask y PostgreSQL."""

from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

ZERO = Decimal("0.00")


def money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def factor(rate, days):
    value = Decimal(rate["value"])
    if not days or not value:
        return Decimal(1)
    with localcontext(Context(prec=55 + max(0, -value.adjusted()))):
        if rate["kind"] == "nominal":
            cap = Decimal(rate["capitalization_days"])
            return (1 + value * cap / 360) ** (Decimal(days) / cap)
        return (1 + value) ** (Decimal(days) / rate["period_days"])


def interest(amount, rate, days):
    with localcontext(Context(prec=55)):
        return money(amount * (factor(rate, days) - 1))


def month_day(origin, offset, day):
    year, month_index = divmod(origin.year * 12 + origin.month - 1 + offset, 12)
    month = month_index + 1
    return date(year, month, min(day, monthrange(year, month)[1]))


def cycle(sold_at, zone, cutoff_day, cutoff_time, payment_day):
    local_zone = ZoneInfo(zone)
    local_date = sold_at.astimezone(local_zone).date()

    def cutoff(offset):
        day = month_day(local_date, offset, cutoff_day)
        return datetime.combine(day, cutoff_time, local_zone).astimezone(timezone.utc)

    cutoff_at = cutoff(0)
    if sold_at > cutoff_at:
        cutoff_at = cutoff(1)
    cutoff_date = cutoff_at.astimezone(local_zone).date()
    due = month_day(cutoff_date, 0, payment_day)
    if due <= cutoff_date:
        due = month_day(cutoff_date, 1, payment_day)
    return local_date, cutoff_at, due


def quote(principal, sold_at, zone, terms, mode, months):
    local_date, cutoff_at, anchor = cycle(
        sold_at, zone, terms["cutoff_day"], terms["cutoff_time"], terms["payment_day"]
    )
    days = (anchor - local_date).days
    rate = terms["compensatory"]
    rows = []
    monthly = mode == "monthly"
    grace = interest(principal, rate, days) if monthly else ZERO
    financed = principal + grace
    single_interest = ZERO if monthly else interest(principal, rate, days)
    if monthly:
        with localcontext(Context(prec=55)):
            monthly_factor = factor(rate, 30)
            effective = monthly_factor - 1
            fixed = money(financed / sum(monthly_factor ** -n for n in range(1, months + 1)))
            balance = financed
            for n in range(1, months + 1):
                row_interest = money(balance * effective)
                payoff = balance + row_interest
                payment = payoff if n == months else min(fixed, payoff)
                capital = payment - row_interest
                rows.append(dict(
                    sequence=n, due=month_day(anchor, n, terms["payment_day"]), opening=balance,
                    interest=row_interest, capital=capital, amount=payment, closing=balance-capital,
                ))
                balance -= capital
    return dict(
        sold_at=sold_at, cutoff_at=cutoff_at, reference_due=anchor, capital=principal,
        financed_principal=financed, grace_days=days if monthly else 0, grace_interest=grace,
        single_interest=single_interest, interest_days=days, installments=rows,
    )
