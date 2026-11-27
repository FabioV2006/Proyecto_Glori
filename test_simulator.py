import unittest
from decimal import Decimal, localcontext

from glori.simulator import schedule, simulate


def loan(*modes):
    return dict(principal="1000", tea="25", late_tea="60", months=len(modes)//2,
                periods=[dict(grace=mode, days=0) for mode in modes])


class SimulatorTests(unittest.TestCase):
    def test_class_example_with_total_grace_and_rate_change(self):
        periods = loan("total", *["normal"] * 7)["periods"]
        with localcontext() as context:
            context.prec = 80
            result = schedule(Decimal("1440000"), [Decimal(9)] * 4 + [Decimal(8)] * 4,
                              Decimal("0"), periods, period_days=180)
        rows = result["rows"]
        self.assertEqual([row["rate_percent"] for row in rows], ["4.4030651"] * 4 + ["3.9230485"] * 4)
        self.assertEqual([str(row["payment"]) for row in rows], ["0.00"] + ["254225.60"] * 3 + ["251372.54"] * 4)
        self.assertEqual([str(row["closing"]) for row in rows], [
            "1503404.14", "1315374.40", "1119065.59", "914113.18",
            "698601.75", "474635.69", "241883.34", "0.00",
        ])

    def test_initial_payment_and_optional_repricing(self):
        case = {**loan("total", "normal", "normal", "normal"),
                "principal": "400", "initial": "50", "rate_change": {"period": 3, "tea": "20"}}
        result = simulate(case)
        self.assertEqual(result["principal"], Decimal("350.00"))
        self.assertEqual(result["sale_total"], result["total"] + Decimal("50.00"))
        self.assertEqual([row["tea"] for row in result["rows"]], ["25", "25", "20", "20"])
        self.assertEqual(result["rows"][-1]["closing"], 0)
        with self.assertRaisesRegex(ValueError, "inicial"):
            simulate({**case, "initial": "400"})
        with self.assertRaisesRegex(ValueError, "segunda"):
            simulate({**case, "rate_change": {"period": 1, "tea": "20"}})

    def test_grace_and_five_days_late(self):
        case = loan("total", "partial", "normal", "normal")
        case["periods"][0]["days"] = case["periods"][2]["days"] = 5
        result = simulate(case)
        self.assertEqual(result["rate"], "0.009341")
        expected = [
            ("1000.00", "9.34", "0.00", "0.00", "1009.34", "0.00", "0.00"),
            ("1009.34", "9.43", "9.43", "0.00", "1009.34", "0.00", "9.43"),
            ("1009.34", "9.43", "511.75", "502.32", "507.02", "3.35", "515.10"),
            ("507.02", "4.74", "511.75", "507.02", "0.00", "0.00", "511.75"),
        ]
        for i, (row, values) in enumerate(zip(result["rows"], expected, strict=True)):
            self.assertEqual(row["day"], (i+1)*15)
            self.assertEqual(row["late_rate"], "0.0065492" if i in (0, 2) else "0")
            for name, value in zip(("opening","interest","payment","capital","closing","penalty","total"), values):
                self.assertEqual(row[name], Decimal(value), (i, name))
        # La suma exacta (interés parcial + dos cuotas + mora) se redondea
        # una sola vez. Sumar los importes ya mostrados daría 1036.28.
        self.assertEqual(result["total"], Decimal("1036.29"))

    def test_rate_input_precision(self):
        for field in ("tea", "late_tea"):
            case = loan("normal", "normal")
            simulate({**case, field: "25.1234567"})
            with self.assertRaisesRegex(ValueError, "7 decimales"):
                simulate({**case, field: "25.12345678"})

    def test_interleaved_grace_and_full_precision(self):
        result = simulate(loan("normal", "total", "partial", "normal"))
        first, total, partial, last = result["rows"]
        self.assertEqual(first["payment"], last["payment"])
        self.assertEqual(total["payment"], 0)
        self.assertEqual(partial["interest"], partial["payment"])
        self.assertEqual(partial["opening"], partial["closing"])
        self.assertEqual(last["closing"], 0)
        self.assertEqual(result["total"], result["principal"] + result["interest"])

    def test_input_rules(self):
        for name, values in dict(principal=[0,-1000000,"NaN"], tea=[0,-25], late_tea=[0,-60],
                                 months=[0,-2,1.5,True], periods=[[],[{},{}]]).items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    simulate({**loan("normal","normal"), name:value})
        for days in [-1, 1.5, True]:
            case = loan("normal", "normal")
            case["periods"][0]["days"] = days
            with self.assertRaises(ValueError):
                simulate(case)
        for case in [loan("total","partial"), loan("bad","normal"),
                     {**loan("normal","normal"), "capitalization_days":30}]:
            with self.assertRaises(ValueError):
                simulate(case)
