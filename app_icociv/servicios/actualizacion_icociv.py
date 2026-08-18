"""Actualización de un valor con índices ICOCIV (base -> proyectado).

Metodología análoga a la del empalme, pero usando un solo tramo ICOCIV:

    R = (P - A) × [(I / I0) - 1]
    Valor proyectado = (P - A) + R

No usa ICCP. I0 es el índice ICOCIV del último periodo observado e I es el
índice ICOCIV proyectado por la aplicación para el horizonte solicitado.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def calcular_actualizacion_icociv(entrada: dict[str, Any]) -> dict[str, Any]:
    """Calcula el valor proyectado ICOCIV y su trazabilidad.

    ``entrada`` requiere: precio_base (P), anticipo_amortizado (A), i0_icociv,
    i_icociv. Campos opcionales: item, unidad, cantidad, observacion_tecnica,
    ruta_icociv, modelo_proyeccion, horizonte, periodo_base, periodo_proyectado.
    """
    precio = _positivo(entrada.get("precio_base"), "precio base P")
    anticipo = _no_negativo(entrada.get("anticipo_amortizado", 0), "anticipo amortizado A")
    base = precio - anticipo
    if base <= 0:
        raise ValueError("La base ajustable P - A debe ser mayor que cero.")

    i0 = _finito(entrada.get("i0_icociv"), "índice ICOCIV base I0")
    if i0 <= 0:
        raise ValueError("El índice ICOCIV base I0 debe ser mayor que cero.")
    i = _finito(entrada.get("i_icociv"), "índice ICOCIV proyectado I")

    factor = i / i0
    r = base * (factor - 1.0)
    valor_proyectado = base + r
    diferencia_porcentual = (r / base) * 100.0

    return {
        "tipo_calculo": "Actualización ICOCIV proyectada",
        "item": str(entrada.get("item", "")),
        "unidad": str(entrada.get("unidad", "")),
        "cantidad": _numero_opcional(entrada.get("cantidad")),
        "precio_base": precio,
        "anticipo_amortizado": anticipo,
        "base_ajustable": base,
        "ruta_icociv": str(entrada.get("ruta_icociv", "")),
        "i0_icociv": i0,
        "i_icociv": i,
        "factor_icociv": factor,
        "r_total": r,
        "valor_proyectado": valor_proyectado,
        "diferencia_absoluta": r,
        "diferencia_porcentual": diferencia_porcentual,
        "modelo_proyeccion": str(entrada.get("modelo_proyeccion", "")),
        "horizonte": entrada.get("horizonte"),
        "periodo_base": str(entrada.get("periodo_base", "")),
        "periodo_proyectado": str(entrada.get("periodo_proyectado", "")),
        "observacion_tecnica": str(entrada.get("observacion_tecnica", "")),
        "fecha_calculo": datetime.now().isoformat(timespec="seconds"),
        "trazabilidad_formula": (
            f"Base = P - A = {base:.6f}\n"
            f"R = Base × [(I/I0) - 1] = {base:.6f} × [({i:.6f}/{i0:.6f}) - 1] = {r:.6f}\n"
            f"Valor proyectado = Base + R = {base:.6f} + {r:.6f} = {valor_proyectado:.6f}"
        ),
    }


def _finito(valor: Any, campo: str) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"El valor de {campo} no es numérico.") from exc
    if not math.isfinite(numero):
        raise ValueError(f"El valor de {campo} no es válido.")
    return numero


def _positivo(valor: Any, campo: str) -> float:
    numero = _finito(valor, campo)
    if numero <= 0:
        raise ValueError(f"El {campo} debe ser mayor que cero.")
    return numero


def _no_negativo(valor: Any, campo: str) -> float:
    numero = _finito(0 if valor in (None, "") else valor, campo)
    if numero < 0:
        raise ValueError(f"El {campo} no puede ser negativo.")
    return numero


def _numero_opcional(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    return _finito(valor, "cantidad")


if __name__ == "__main__":
    r = calcular_actualizacion_icociv(
        {"precio_base": 1000.0, "anticipo_amortizado": 0.0, "i0_icociv": 100.0, "i_icociv": 110.0}
    )
    assert math.isclose(r["factor_icociv"], 1.1), r["factor_icociv"]
    assert math.isclose(r["r_total"], 100.0), r["r_total"]
    assert math.isclose(r["valor_proyectado"], 1100.0), r["valor_proyectado"]
    assert math.isclose(r["diferencia_porcentual"], 10.0), r["diferencia_porcentual"]

    r2 = calcular_actualizacion_icociv(
        {"precio_base": 1000.0, "anticipo_amortizado": 200.0, "i0_icociv": 100.0, "i_icociv": 110.0}
    )
    assert math.isclose(r2["base_ajustable"], 800.0)
    assert math.isclose(r2["r_total"], 80.0)
    assert math.isclose(r2["valor_proyectado"], 880.0)

    for mala in (
        {"precio_base": 0, "i0_icociv": 100, "i_icociv": 110},
        {"precio_base": 1000, "i0_icociv": 0, "i_icociv": 110},
        {"precio_base": 1000, "anticipo_amortizado": 1000, "i0_icociv": 100, "i_icociv": 110},
    ):
        try:
            calcular_actualizacion_icociv(mala)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Debió rechazar entrada inválida: {mala}")
    print("OK actualizacion_icociv")
