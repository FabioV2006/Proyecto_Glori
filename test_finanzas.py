"""Casos de aceptación del informe del Grupo 3 y límites de la etapa 1."""

import unittest
from datetime import date
from decimal import Decimal, localcontext

from finanzas import (
    Mora,
    calcular_mora,
    generar_cronograma,
    tasa_efectiva_diaria_moratoria,
    tasa_efectiva_semanal,
)


D = Decimal
COMPRA_CON_INTERES = date(2026, 10, 6)


class CronogramasDelInforme(unittest.TestCase):
    def comprobar_filas(self, cronograma, filas):
        self.assertEqual(len(cronograma), len(filas))
        for semana, (periodo, fila) in enumerate(zip(cronograma, filas), start=1):
            fecha, modalidad, *importes = fila
            with self.subTest(semana=semana):
                self.assertEqual(periodo.semana, semana)
                self.assertEqual(periodo.fecha_vencimiento, date.fromisoformat(fecha))
                self.assertEqual(periodo.modalidad, modalidad)
                observados = (
                    periodo.saldo_inicial,
                    periodo.interes,
                    periodo.pago_programado,
                    periodo.amortizacion,
                    periodo.saldo_final,
                )
                self.assertEqual(observados, tuple(map(D, importes)))
                for importe in observados:
                    self.assertEqual(importe.as_tuple().exponent, -2)

    def comprobar_totales(self, cronograma, *, pagos, intereses, amortizacion):
        self.assertEqual(sum(fila.pago_programado for fila in cronograma), D(pagos))
        self.assertEqual(sum(fila.interes for fila in cronograma), D(intereses))
        self.assertEqual(sum(fila.amortizacion for fila in cronograma), D(amortizacion))
        self.assertEqual(cronograma[-1].saldo_final, D("0.00"))

    def test_caso_1_cuatro_cuotas_sin_interes(self):
        cronograma = generar_cronograma("400.00", date(2026, 10, 5), "0", 4)
        # Sección 6.4, imagen del cronograma. Filas correspondientes a semanas 1 a 4.
        self.comprobar_filas(cronograma, [
            ("2026-10-12", "amortizacion", "400.00", "0.00", "100.00", "100.00", "300.00"),
            ("2026-10-19", "amortizacion", "300.00", "0.00", "100.00", "100.00", "200.00"),
            ("2026-10-26", "amortizacion", "200.00", "0.00", "100.00", "100.00", "100.00"),
            ("2026-11-02", "amortizacion", "100.00", "0.00", "100.00", "100.00", "0.00"),
        ])
        self.comprobar_totales(cronograma, pagos="400.00", intereses="0.00", amortizacion="400.00")
        for periodo in cronograma:
            with self.subTest(semana=periodo.semana):
                self.assertEqual(
                    calcular_mora(periodo, periodo.fecha_vencimiento, "0").interes_moratorio,
                    D("0.00"),
                )

    def test_caso_2_gracia_parcial_y_atraso(self):
        cronograma = generar_cronograma(
            "350.00", COMPRA_CON_INTERES, "0.24", 6, semanas_gracia=2, tipo_gracia="parcial"
        )
        # Sección 6.4, segunda simulación. Cuota teórica S/ 88.4188040122…
        self.comprobar_filas(cronograma, [
            ("2026-10-13", "gracia_parcial", "350.00", "1.47", "1.47", "0.00", "350.00"),
            ("2026-10-20", "gracia_parcial", "350.00", "1.47", "1.47", "0.00", "350.00"),
            ("2026-10-27", "amortizacion", "350.00", "1.47", "88.42", "86.95", "263.05"),
            ("2026-11-03", "amortizacion", "263.05", "1.10", "88.42", "87.32", "175.73"),
            ("2026-11-10", "amortizacion", "175.73", "0.74", "88.42", "87.68", "88.05"),
            ("2026-11-17", "amortizacion", "88.05", "0.37", "88.42", "88.05", "0.00"),
        ])
        self.comprobar_totales(cronograma, pagos="356.62", intereses="6.62", amortizacion="350.00")
        atraso = cronograma[2]
        mora = calcular_mora(atraso, date(2026, 10, 30), "0.30")
        self.assertEqual(mora, Mora(3, D("88.42"), D("0.19")))
        self.assertEqual(atraso.pago_programado + mora.interes_moratorio, D("88.61"))
        self.assertEqual(
            sum(fila.pago_programado for fila in cronograma) + mora.interes_moratorio,
            D("356.81"),
        )
        for periodo in (*cronograma[:2], *cronograma[3:]):
            with self.subTest(semana=periodo.semana):
                self.assertEqual(
                    calcular_mora(periodo, periodo.fecha_vencimiento, "0.30"),
                    Mora(0, D("0.00"), D("0.00")),
                )

    def test_caso_3_gracia_total(self):
        cronograma = generar_cronograma(
            "350.00", COMPRA_CON_INTERES, "0.24", 6, semanas_gracia=2, tipo_gracia="total"
        )
        # Sección 6.4, tercera simulación. Cuota teórica S/ 89.1615219659…
        self.comprobar_filas(cronograma, [
            ("2026-10-13", "gracia_total", "350.00", "1.47", "0.00", "0.00", "351.47"),
            ("2026-10-20", "gracia_total", "351.47", "1.47", "0.00", "0.00", "352.94"),
            ("2026-10-27", "amortizacion", "352.94", "1.48", "89.16", "87.68", "265.26"),
            ("2026-11-03", "amortizacion", "265.26", "1.11", "89.16", "88.05", "177.21"),
            ("2026-11-10", "amortizacion", "177.21", "0.74", "89.16", "88.42", "88.79"),
            ("2026-11-17", "amortizacion", "88.79", "0.37", "89.16", "88.79", "0.00"),
        ])
        self.comprobar_totales(cronograma, pagos="356.64", intereses="6.64", amortizacion="352.94")
        self.assertEqual(sum(periodo.interes for periodo in cronograma[:2]), D("2.94"))
        for periodo in cronograma:
            with self.subTest(semana=periodo.semana):
                self.assertEqual(
                    calcular_mora(periodo, periodo.fecha_vencimiento, "0.30"),
                    Mora(0, D("0.00"), D("0.00")),
                )


class TasasYRedondeo(unittest.TestCase):
    def test_tasas_efectivas_en_base_360(self):
        tes = tasa_efectiva_semanal("0.24")
        ted = tasa_efectiva_diaria_moratoria("0.30")
        self.assertLess(abs(tes - D("0.004191481057933869597424522247")), D("1e-30"))
        self.assertLess(abs(ted - D("0.000729055255204436598800595529")), D("1e-30"))
        self.assertEqual(tasa_efectiva_semanal(0), D(0))
        self.assertEqual(tasa_efectiva_diaria_moratoria(0), D(0))
        self.assertGreater(tasa_efectiva_semanal("1e-60"), D(0))

    def test_tasa_cero_y_ajuste_de_ultima_cuota(self):
        cronograma = generar_cronograma("100.00", date(2026, 12, 25), 0, 3)
        self.assertEqual(
            [periodo.pago_programado for periodo in cronograma],
            [D("33.33"), D("33.33"), D("33.34")],
        )
        self.assertEqual(cronograma[0].fecha_vencimiento, date(2027, 1, 1))
        for periodo in cronograma:
            self.assertEqual(periodo.interes, D("0.00"))
            self.assertEqual(periodo.amortizacion, periodo.pago_programado)
        self.assertEqual(cronograma[-1].saldo_final, D("0.00"))

    def test_medio_centimo_y_contexto_decimal_del_llamador(self):
        with localcontext() as contexto:
            contexto.prec = 3
            cronograma = generar_cronograma("100.005", COMPRA_CON_INTERES, "0", 2)
        self.assertEqual(cronograma[0].saldo_inicial, D("100.01"))
        self.assertEqual(cronograma[0].pago_programado, D("50.01"))
        self.assertEqual(cronograma[1].pago_programado, D("50.00"))

    def test_redondeo_no_amortiza_mas_que_el_saldo_en_capital_pequeno(self):
        cronograma = generar_cronograma("0.02", COMPRA_CON_INTERES, "0", 4)
        self.assertEqual(
            [periodo.pago_programado for periodo in cronograma],
            [D("0.01"), D("0.01"), D("0.00"), D("0.00")],
        )
        self.assertTrue(all(periodo.saldo_final >= 0 for periodo in cronograma))


class MoraPorObligacion(unittest.TestCase):
    def setUp(self):
        self.gracia, self.cuota, self.cuota_siguiente = generar_cronograma(
            "350.00", COMPRA_CON_INTERES, "0.24", 3, semanas_gracia=1, tipo_gracia="parcial"
        )

    def test_mora_compuesta_por_dias_calendario_sobre_saldo_pendiente(self):
        # Del 20/10 al 19/12 hay 60 días. S/ 50 × (1.30**(60/360) - 1) ≈ S/ 2.23.
        mora = calcular_mora(
            self.cuota, date(2026, 12, 19), "0.30", importe_pendiente="50.00"
        )
        self.assertEqual(mora, Mora(60, D("50.00"), D("2.23")))

    def test_dos_obligaciones_vencidas_con_dias_y_bases_distintos(self):
        fecha = date(2026, 10, 25)
        self.assertEqual(calcular_mora(self.gracia, fecha, "0.30"), Mora(12, D("1.47"), D("0.01")))
        self.assertEqual(calcular_mora(self.cuota, fecha, "0.30"), Mora(5, D("176.10"), D("0.64")))
        self.assertEqual(calcular_mora(self.cuota_siguiente, fecha, "0.30"), Mora(0, D(0), D(0)))

    def test_pago_puntual_anticipado_o_ya_cancelado(self):
        for fecha, pendiente in (
            (date(2026, 10, 19), None),
            (date(2026, 10, 20), None),
            (date(2026, 10, 24), "0.00"),
        ):
            with self.subTest(fecha=fecha, pendiente=pendiente):
                self.assertEqual(
                    calcular_mora(self.cuota, fecha, "0.30", importe_pendiente=pendiente),
                    Mora(0, D(0), D(0)),
                )

    def test_gracia_total_sin_obligacion_exigible(self):
        gracia, _ = generar_cronograma(
            350, COMPRA_CON_INTERES, "0.24", 2, semanas_gracia=1, tipo_gracia="total"
        )
        self.assertEqual(calcular_mora(gracia, date(2026, 10, 25), "0.30"), Mora(0, D(0), D(0)))

    def test_tasa_moratoria_cero_con_atraso(self):
        mora = calcular_mora(self.gracia, date(2026, 10, 25), 0)
        self.assertEqual(mora, Mora(12, D("1.47"), D("0.00")))

    def test_rechaza_pendiente_invalido_o_que_supera_el_pago_programado(self):
        for pendiente in ("-0.01", "NaN", self.cuota.pago_programado + D("0.01")):
            with self.subTest(pendiente=pendiente), self.assertRaises(ValueError):
                calcular_mora(self.cuota, date(2026, 10, 25), "0.30", importe_pendiente=pendiente)


class ValidacionDePlazos(unittest.TestCase):
    def test_plazos_validos_en_los_extremos(self):
        minimo = generar_cronograma(350, COMPRA_CON_INTERES, "0.24", 1, plazo_maximo_cliente_dias=7)
        maximo = generar_cronograma(
            350, COMPRA_CON_INTERES, "0.24", 12,
            semanas_gracia=3, tipo_gracia="total", plazo_maximo_cliente_dias=84,
        )
        self.assertEqual(len(minimo), 1)
        self.assertEqual(minimo[0].amortizacion, D("350.00"))
        self.assertEqual(len(maximo), 12)
        self.assertEqual(maximo[2].modalidad, "gracia_total")
        self.assertEqual(maximo[3].modalidad, "amortizacion")
        self.assertEqual(maximo[-1].fecha_vencimiento, date(2026, 12, 29))
        self.assertEqual(maximo[-1].saldo_final, D("0.00"))

    def test_plazo_total_invalido(self):
        for semanas in (0, -1, 13, 4.0, True):
            with self.subTest(semanas=semanas), self.assertRaises(ValueError):
                generar_cronograma(350, COMPRA_CON_INTERES, "0.24", semanas)

    def test_gracia_invalida_o_sin_semana_de_amortizacion(self):
        for semanas, gracia, tipo in (
            (6, -1, "parcial"), (6, 4, "total"), (3, 3, "total"), (2, 3, "total"),
            (6, 1.0, "total"), (6, True, "total"), (6, 1, None), (6, 1, "otra"), (6, 0, "total"),
        ):
            with (
                self.subTest(semanas=semanas, gracia=gracia, tipo=tipo),
                self.assertRaises(ValueError),
            ):
                generar_cronograma(
                    350, COMPRA_CON_INTERES, "0.24", semanas,
                    semanas_gracia=gracia, tipo_gracia=tipo,
                )

    def test_plazo_pactado_del_cliente_cuenta_las_semanas_de_gracia(self):
        for dias in (41, 0, -1, 42.0, True):
            with self.subTest(dias=dias), self.assertRaises(ValueError):
                generar_cronograma(
                    350, COMPRA_CON_INTERES, "0.24", 6,
                    semanas_gracia=2, tipo_gracia="parcial", plazo_maximo_cliente_dias=dias,
                )
        cronograma = generar_cronograma(
            350, COMPRA_CON_INTERES, "0.24", 6,
            semanas_gracia=2, tipo_gracia="parcial", plazo_maximo_cliente_dias=42,
        )
        self.assertEqual(cronograma[-1].fecha_vencimiento, date(2026, 11, 17))

    def test_rechaza_importes_y_tasas_fuera_del_dominio(self):
        for capital in (0, "-0.01", "0.004", "Infinity"):
            with self.subTest(capital=capital), self.assertRaises(ValueError):
                generar_cronograma(capital, COMPRA_CON_INTERES, 0, 1)
        for tasa in ("-0.01", "NaN", "abc"):
            with self.subTest(tasa=tasa), self.assertRaises(ValueError):
                tasa_efectiva_semanal(tasa)
        with self.assertRaises(TypeError):
            tasa_efectiva_diaria_moratoria(0.30)
