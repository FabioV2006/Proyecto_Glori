import unittest
from datetime import date, datetime, time
from decimal import Decimal

from glori.finance import cycle, factor, quote

RATE = {"kind": "nominal", "value": "0.12", "capitalization_days": 30}
TERMS = dict(cutoff_day=20, cutoff_time=time(18), payment_day=26, compensatory=RATE)


def september(day, time_of_day="12:00:00"):
    return datetime.fromisoformat(f"2026-09-{day:02d}T{time_of_day}-05:00")


class SI642FinanceTests(unittest.TestCase):
    def test_nominal_effective_and_base_360(self):
        self.assertEqual(factor(RATE, 30), Decimal("1.01"))
        self.assertEqual(
            factor({"kind": "effective", "value": "0.01", "period_days": 30}, 30),
            Decimal("1.01"),
        )
        self.assertLess(
            abs(factor({"kind": "effective", "value": "0.24", "period_days": 360}, 30)
                - Decimal("1.018087582483510674531353084")), Decimal("1e-25"),
        )

    def test_pdf_and_monthly_after_cutoff(self):
        for day, grace_days, dates in (
            (15, 11, ["2026-10-26", "2026-11-26", "2026-12-26"]),
            (21, 35, ["2026-11-26", "2026-12-26", "2027-01-26"]),
        ):
            with self.subTest(day=day):
                result = quote(Decimal("360.00"), september(day), "America/Lima", TERMS, "monthly", 3)
                self.assertEqual(result["grace_days"], grace_days)
                self.assertEqual(str(result["grace_interest"]), "1.32" if day == 15 else "4.20")
                self.assertEqual([row["due"].isoformat() for row in result["installments"]], dates)
                self.assertEqual(result["installments"][0]["opening"], result["financed_principal"])
                self.assertEqual(sum(row["capital"] for row in result["installments"]), result["financed_principal"])
                self.assertEqual(result["installments"][-1]["closing"], Decimal("0.00"))

    def test_single_before_at_and_after_cutoff(self):
        for time_of_day, reference, days in (
            ("17:59:59", date(2026, 9, 26), 6),
            ("18:00:00", date(2026, 9, 26), 6),
            ("18:00:01", date(2026, 10, 26), 36),
        ):
            with self.subTest(time=time_of_day):
                result = quote(Decimal("100.00"), september(20, time_of_day), "America/Lima", TERMS, "single", 0)
                self.assertEqual(result["reference_due"], reference)
                self.assertEqual(result["interest_days"], days)
        self.assertEqual(quote(Decimal("100"), september(21), "America/Lima", TERMS, "single", 0)["interest_days"], 35)

    def test_short_month_moves_payment_and_recovers_pact_day(self):
        instant = datetime.fromisoformat("2028-02-25T12:00:00-05:00")
        _, cutoff, due = cycle(instant, "America/Lima", 30, time(18), 31)
        self.assertEqual(cutoff.date(), date(2028, 2, 29))
        self.assertEqual(due, date(2028, 3, 31))
        terms = {**TERMS, "cutoff_day": 20, "payment_day": 31, "compensatory": {**RATE, "value": "0"}}
        result = quote(Decimal("100.00"), instant, "America/Lima", terms, "monthly", 2)
        self.assertEqual([row["due"].isoformat() for row in result["installments"]], ["2028-04-30", "2028-05-31"])
        self.assertEqual([row["amount"] for row in result["installments"]], [Decimal("50.00")] * 2)
