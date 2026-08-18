"""Caso especial del acero ICCP-ICOCIV, reproducible paso a paso (hallazgo H-09).

El generador de resultados de referencia del paquete auditado no producía los
casos de acero: pasaba `"Aceros y elementos metalicos"` sin tilde y la búsqueda
de la serie ICCP fallaba con `ValueError`. Las dos filas E-04 y E-05 salían con
un mensaje de error en lugar de con los valores.

Esta suite fija el caso completo y comprueba cada fórmula contra una sustitución
numérica independiente, sin usar el resultado de la aplicación como oráculo.

Ejecutar con:  python tests/test_caso_acero_reproducible.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.servicios.empalme_iccp_icociv import (  # noqa: E402
    PERIODO_TRANSICION,
    calcular_empalme_iccp_icociv,
    cargar_iccp_historico,
    obtener_indice_iccp,
    series_iccp_por_tipo,
)

TOLERANCIA_MONEDA = 0.01  # una unidad monetaria centesimal
TOLERANCIA_FACTOR = 1e-12

# Nombre exacto de la serie ICCP. La tilde importa: sin ella la busqueda falla.
SERIE_ICCP_ACERO = "Aceros y elementos metálicos"

#: Índices ICOCIV del caso. Son valores fijos del ejercicio, no lecturas del
#: anexo, para que el caso sea reproducible sin depender del archivo Excel.
INDICES_ICOCIV = {"2019_3": 92.0, "2021_12": 100.0, "2026_5": 131.7}

ENTRADA_ACERO = {
    "item": "Acero de refuerzo",
    "unidad": "kg",
    "calculo_acero": True,
    "p0": 500_000_000.0,
    "ix": 4_200.0,
    "q": 150_000.0,
    "fecha_inicial": "2019_3",
    "fecha_final": "2026_5",
    "tipo_serie_iccp": "grupo_obra",
    "serie_iccp": SERIE_ICCP_ACERO,
    "ruta_icociv": "Carreteras > Materiales > Acero",
}


def test_la_serie_iccp_de_acero_existe_con_ese_nombre_exacto() -> None:
    """H-09: el nombre sin tilde no existe y hacia fallar el generador."""
    disponibles = series_iccp_por_tipo()["grupo_obra"]
    assert SERIE_ICCP_ACERO in disponibles, (
        f"La serie debe llamarse exactamente {SERIE_ICCP_ACERO!r}. "
        f"Disponibles: {disponibles}"
    )
    assert "Aceros y elementos metalicos" not in disponibles, (
        "El nombre sin tilde no existe: usarlo provoca ValueError"
    )

    historico = cargar_iccp_historico()
    assert PERIODO_TRANSICION in historico[SERIE_ICCP_ACERO], (
        "La serie debe cubrir el periodo de transición para el empalme completo"
    )


def test_el_caso_de_acero_se_calcula_sin_error() -> None:
    resultado = calcular_empalme_iccp_icociv(ENTRADA_ACERO, INDICES_ICOCIV)
    assert resultado["tipo_calculo"] == "Cálculo especial acero"
    assert resultado["caso"] == "empalme_completo"
    for clave in ("r1", "r2", "r_total", "valor_actualizado", "z"):
        assert resultado.get(clave) is not None, f"{clave} no se calculó"


def test_formulas_del_acero_contra_sustitucion_numerica_independiente() -> None:
    """R1, R2, R y Z verificados a mano, sin usar la salida como oráculo."""
    resultado = calcular_empalme_iccp_icociv(ENTRADA_ACERO, INDICES_ICOCIV)

    p0 = float(ENTRADA_ACERO["p0"])
    ix = float(ENTRADA_ACERO["ix"])
    q = float(ENTRADA_ACERO["q"])

    # Los índices se leen de la fuente, no del resultado.
    i0_iccp = obtener_indice_iccp("2019_3", SERIE_ICCP_ACERO)
    i_iccp = obtener_indice_iccp(PERIODO_TRANSICION, SERIE_ICCP_ACERO)
    i0_icociv = INDICES_ICOCIV["2021_12"]
    i_icociv = INDICES_ICOCIV["2026_5"]

    assert abs(resultado["i0_iccp"] - i0_iccp) < TOLERANCIA_FACTOR
    assert abs(resultado["i_iccp"] - i_iccp) < TOLERANCIA_FACTOR
    assert abs(resultado["i0_icociv"] - i0_icociv) < TOLERANCIA_FACTOR
    assert abs(resultado["i_icociv"] - i_icociv) < TOLERANCIA_FACTOR

    # R1 = P0 [(I_ICCP / I0_ICCP) - 1]
    r1 = p0 * ((i_iccp / i0_iccp) - 1.0)
    assert abs(r1 - resultado["r1"]) < TOLERANCIA_MONEDA, f"R1: {r1} vs {resultado['r1']}"

    # R2 = (P0 + R1) [(I_ICOCIV / I0_ICOCIV) - 1]
    r2 = (p0 + r1) * ((i_icociv / i0_icociv) - 1.0)
    assert abs(r2 - resultado["r2"]) < TOLERANCIA_MONEDA, f"R2: {r2} vs {resultado['r2']}"

    # R = R1 + R2
    r_total = r1 + r2
    assert abs(r_total - resultado["r_total"]) < TOLERANCIA_MONEDA

    # Valor actualizado = P0 + R  (en acero la base es P0, sin anticipo)
    assert abs((p0 + r_total) - resultado["valor_actualizado"]) < TOLERANCIA_MONEDA
    assert abs(resultado["base_ajustable"] - p0) < TOLERANCIA_MONEDA
    assert float(resultado["anticipo_amortizado"]) == 0.0

    # Z = (Ix * q) - (R + P0)
    z = (ix * q) - (r_total + p0)
    assert abs(z - resultado["z"]) < TOLERANCIA_MONEDA, f"Z: {z} vs {resultado['z']}"
    assert abs((ix * q) - resultado["valor_facturado_total"]) < TOLERANCIA_MONEDA


def test_el_encadenamiento_no_es_sobre_la_misma_base() -> None:
    """R2 se aplica sobre (P0 + R1), no sobre P0. La diferencia es material."""
    resultado = calcular_empalme_iccp_icociv(ENTRADA_ACERO, INDICES_ICOCIV)
    p0 = float(ENTRADA_ACERO["p0"])
    factor_icociv = resultado["factor_icociv"]

    encadenado = (p0 + resultado["r1"]) * (factor_icociv - 1.0)
    sobre_base = p0 * (factor_icociv - 1.0)

    assert abs(encadenado - resultado["r2"]) < TOLERANCIA_MONEDA
    assert abs(sobre_base - resultado["r2"]) > 1_000.0, (
        "Si ambas formas coincidieran, la prueba no distinguiría el encadenamiento"
    )


def test_z_no_calculable_sin_ix_ni_q() -> None:
    entrada = {k: v for k, v in ENTRADA_ACERO.items() if k not in ("ix", "q")}
    entrada["item"] = "Acero estructural"
    resultado = calcular_empalme_iccp_icociv(entrada, INDICES_ICOCIV)

    assert resultado["z"] is None
    assert resultado["valor_facturado_total"] is None
    assert "Ix" in resultado["z_observacion"] and "q" in resultado["z_observacion"]
    # El resto del cálculo sí debe estar disponible.
    for clave in ("r1", "r2", "r_total", "valor_actualizado"):
        assert resultado.get(clave) is not None


def test_la_trazabilidad_deja_la_sustitucion_numerica() -> None:
    resultado = calcular_empalme_iccp_icociv(ENTRADA_ACERO, INDICES_ICOCIV)
    traza = resultado["trazabilidad_formula"]
    for fragmento in ("Base =", "R1 =", "R2 =", "R = R1 + R2", "Valor actualizado ="):
        assert fragmento in traza, f"Falta {fragmento!r} en la trazabilidad"


def test_el_informe_de_empalme_incluye_la_formula_de_z() -> None:
    from app_icociv.reportes.contenido_empalme import construir_informe_empalme
    from app_icociv.reportes.modelo import Formula

    calculo = calcular_empalme_iccp_icociv(ENTRADA_ACERO, INDICES_ICOCIV)
    calculo["ruta_icociv"] = ENTRADA_ACERO["ruta_icociv"]
    informe = construir_informe_empalme([calculo], {"contrato": "PRUEBA-ACERO"})

    formulas = {
        b.etiqueta: b
        for seccion in informe.secciones
        for b in seccion.bloques
        if isinstance(b, Formula)
    }
    assert "Valor adicional por fluctuación del acero (Z)" in formulas
    z = formulas["Valor adicional por fluctuación del acero (Z)"]
    assert z.general == "Z = (Ix x q) - (R + P0)"
    assert z.sustitucion, "La fórmula debe traer sustitución numérica"


def _ejecutar() -> int:
    fallos = total = 0
    for nombre, funcion in sorted(globals().items()):
        if not nombre.startswith("test_") or not callable(funcion):
            continue
        total += 1
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as error:
            fallos += 1
            print(f"  FALLA {nombre}: {error}")
        except Exception as error:  # pragma: no cover
            fallos += 1
            print(f"  ERROR {nombre}: {type(error).__name__}: {error}")
    print(f"\n{total - fallos}/{total} pruebas aprobadas.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
