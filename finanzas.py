"""Cálculos semanales de Glori según las secciones 6.3 y 6.4 del informe.

Las tasas se expresan como fracciones (Decimal("0.24") equivale a 24 %)
y se calculan con al menos 50 dígitos de precisión de trabajo. El capital
de entrada, el interés de cada semana, la cuota regular y la mora de cada
obligación se redondean a dos decimales con ROUND_HALF_UP (medio céntimo
hacia arriba). El saldo y la amortización se calculan con esos importes,
incluido el interés que se capitaliza cada semana de gracia total.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Literal


NumeroDecimal = Decimal | str | int
TipoGracia = Literal["parcial", "total"]
Modalidad = Literal["gracia_parcial", "gracia_total", "amortizacion"]

_CENTIMO = Decimal("0.01")
_CERO = Decimal("0.00")
_BASE_ANUAL = Decimal(360)
_DIAS_SEMANA = 7


@dataclass(frozen=True)
class Periodo:
    semana: int
    fecha_vencimiento: date
    modalidad: Modalidad
    saldo_inicial: Decimal
    interes: Decimal
    amortizacion: Decimal
    pago_programado: Decimal
    saldo_final: Decimal


@dataclass(frozen=True)
class Mora:
    dias_atraso: int
    importe_base: Decimal
    interes_moratorio: Decimal


def _decimal_no_negativo(valor: NumeroDecimal, nombre: str) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, (Decimal, str, int)):
        raise TypeError(f"{nombre} debe ser Decimal, str o int.")
    try:
        numero = Decimal(valor, context=Context(traps=[InvalidOperation]))
    except InvalidOperation as error:
        raise ValueError(f"{nombre} debe ser un número decimal válido.") from error
    if not numero.is_finite() or numero < 0:
        raise ValueError(f"{nombre} debe ser finito y no negativo.")
    return numero


def _validar_fecha(valor: date, nombre: str) -> None:
    if not isinstance(valor, date) or isinstance(valor, datetime):
        raise TypeError(f"{nombre} debe ser una fecha de calendario (date).")


def _contexto(tasa: Decimal, importe: Decimal = _CERO) -> Context:
    # Reserva dígitos para restar 1 al factor cuando la tasa es muy pequeña.
    precision = max(50 + max(0, -tasa.adjusted()), importe.adjusted() + 12)
    return Context(prec=precision)


def _redondear_importe(importe: Decimal) -> Decimal:
    return importe.quantize(_CENTIMO, rounding=ROUND_HALF_UP)


def _convertir_tea(tea: NumeroDecimal, dias: int) -> Decimal:
    anual = _decimal_no_negativo(tea, "TEA")
    if anual == 0:
        return Decimal(0)
    with localcontext(_contexto(anual)):
        return (1 + anual) ** (Decimal(dias) / _BASE_ANUAL) - 1


def tasa_efectiva_semanal(tea: NumeroDecimal) -> Decimal:
    """Convierte una TEA a tasa efectiva de siete días en base 360."""
    return _convertir_tea(tea, _DIAS_SEMANA)


def tasa_efectiva_diaria_moratoria(tea_moratoria: NumeroDecimal) -> Decimal:
    """Convierte una TEA moratoria a tasa efectiva de un día en base 360."""
    return _convertir_tea(tea_moratoria, 1)


def generar_cronograma(
    capital: NumeroDecimal,
    fecha_compra: date,
    tea: NumeroDecimal,
    semanas_totales: int,
    *,
    semanas_gracia: int = 0,
    tipo_gracia: TipoGracia | None = None,
    plazo_maximo_cliente_dias: int | None = None,
) -> tuple[Periodo, ...]:
    """Genera las semanas de gracia y amortización de un capital financiado.

    Los saldos suponen que cada pago programado se realiza al vencimiento.
    El plazo pactado se mide en días calendario desde la compra. Cuando hay
    semanas de gracia se requiere el tipo correspondiente. Si el redondeo
    adelanta la cancelación de un capital muy pequeño, las semanas restantes
    se conservan con pago cero. La última semana liquida el saldo remanente.
    """
    _validar_fecha(fecha_compra, "fecha_compra")
    if type(semanas_totales) is not int or not 1 <= semanas_totales <= 12:
        raise ValueError("El plazo total debe ser un entero de 1 a 12 semanas.")
    if type(semanas_gracia) is not int or not 0 <= semanas_gracia <= 3:
        raise ValueError("La gracia debe ser un entero de 0 a 3 semanas.")
    if semanas_gracia >= semanas_totales:
        raise ValueError("Se requiere al menos una semana de amortización.")
    if semanas_gracia and tipo_gracia not in ("parcial", "total"):
        raise ValueError("Indica si la gracia es parcial o total.")
    if semanas_gracia == 0 and tipo_gracia is not None:
        raise ValueError("Indica un tipo de gracia solo si hay semanas de gracia.")
    if plazo_maximo_cliente_dias is not None:
        if type(plazo_maximo_cliente_dias) is not int or plazo_maximo_cliente_dias < 1:
            raise ValueError("El plazo máximo del cliente debe ser un entero positivo en días.")
        if semanas_totales * _DIAS_SEMANA > plazo_maximo_cliente_dias:
            raise ValueError("El plazo total supera el máximo pactado del cliente.")

    principal = _decimal_no_negativo(capital, "capital")
    tasa = tasa_efectiva_semanal(tea)
    periodos = []
    with localcontext(_contexto(tasa, principal)):
        saldo = _redondear_importe(principal)
        if saldo == 0:
            raise ValueError("El capital financiado debe ser al menos un céntimo tras redondear.")

        for semana in range(1, semanas_gracia + 1):
            vencimiento = fecha_compra + timedelta(days=semana * _DIAS_SEMANA)
            interes = _redondear_importe(saldo * tasa)
            if tipo_gracia == "total":
                modalidad: Modalidad = "gracia_total"
                pago = _CERO
                saldo_final = saldo + interes
            else:
                modalidad = "gracia_parcial"
                pago = interes
                saldo_final = saldo
            periodos.append(
                Periodo(semana, vencimiento, modalidad, saldo, interes, _CERO, pago, saldo_final)
            )
            saldo = saldo_final

        semanas_amortizacion = semanas_totales - semanas_gracia
        # El valor actual de cada cuota unitaria suma N cuando la tasa es cero.
        factores_descuento = sum(
            (1 + tasa) ** -semana for semana in range(1, semanas_amortizacion + 1)
        )
        cuota_regular = _redondear_importe(saldo / factores_descuento)
        for semana in range(semanas_gracia + 1, semanas_totales + 1):
            vencimiento = fecha_compra + timedelta(days=semana * _DIAS_SEMANA)
            interes = _redondear_importe(saldo * tasa)
            importe_liquidacion = saldo + interes
            pago = (
                importe_liquidacion
                if semana == semanas_totales
                else min(cuota_regular, importe_liquidacion)
            )
            amortizacion = pago - interes
            saldo_final = saldo - amortizacion
            periodos.append(
                Periodo(
                    semana, vencimiento, "amortizacion",
                    saldo, interes, amortizacion, pago, saldo_final,
                )
            )
            saldo = saldo_final
    return tuple(periodos)


def calcular_mora(
    periodo: Periodo,
    fecha_evaluacion: date,
    tea_moratoria: NumeroDecimal,
    *,
    importe_pendiente: NumeroDecimal | None = None,
) -> Mora:
    """Liquida la mora de un periodo a la fecha de consulta o de pago.

    Por defecto se usa el pago programado de la obligación. Si el llamador
    conoce su saldo impago, puede indicar ese importe sin mora anterior,
    o cero para una obligación cancelada. Para liquidar al momento del pago
    se pasa el saldo inmediatamente anterior a ese pago. El importe indicado
    se toma como base desde el vencimiento.

    El primer día de atraso es el día calendario posterior al vencimiento.
    """
    _validar_fecha(fecha_evaluacion, "fecha_evaluacion")
    tasa = tasa_efectiva_diaria_moratoria(tea_moratoria)
    pendiente = periodo.pago_programado
    if importe_pendiente is not None:
        pendiente = _decimal_no_negativo(importe_pendiente, "importe_pendiente")
        if pendiente > periodo.pago_programado:
            raise ValueError("El importe pendiente no puede superar el pago programado.")

    dias_atraso = (fecha_evaluacion - periodo.fecha_vencimiento).days
    with localcontext(_contexto(tasa, pendiente)):
        base = _redondear_importe(pendiente)
        if dias_atraso <= 0 or base == 0:
            return Mora(0, _CERO, _CERO)
        interes = _redondear_importe(base * ((1 + tasa) ** dias_atraso - 1))
    return Mora(dias_atraso, base, interes)
