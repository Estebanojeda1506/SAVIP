"""Pruebas de la clasificación de atípicos y del patrón calendario de enero.

Decisión aprobada D-4: los eneros que cumplen los criterios confirmados del
módulo de cambio de año se clasifican como «patrón calendario de cambio de
año», no cuentan como valores atípicos, y las alertas se deduplican por
periodo (antes un mismo mes aparecía hasta tres veces, una por escala).
Los umbrales del módulo de salto anual no cambian.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.analisis_series import (
    calcular_variables_derivadas,
    detectar_valores_atipicos_mad,
    evaluar_calidad_datos,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.estadistica.criterios import (
    CONSISTENCIA_SIGNO_SALTO_ANUAL,
    MIN_TRANSICIONES_SALTO_ANUAL,
    RATIO_SALTO_ANUAL,
    TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO,
)

RUTA_ANEXO = ROOT / "anex-ICOCIV-may2026.xlsb"


def _serie_df(valores: list[float], anio_inicial: int = 2020) -> pd.DataFrame:
    periodos = [f"{anio_inicial + i // 12}_{i % 12 + 1}" for i in range(len(valores))]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _alertas(valores: list[float]) -> tuple[list[dict], pd.DataFrame]:
    serie = normalizar_serie_mensual(_serie_df(valores))
    derivadas = calcular_variables_derivadas(serie)
    return detectar_valores_atipicos_mad(derivadas["serie"]), serie


def _serie_salto_enero(n: int = 60, salto: float = 1.05, base: float = 1.002) -> list[float]:
    """Salto de ~5% cada enero sobre crecimiento suave con jitter determinista."""
    import math

    vals, nivel = [], 100.0
    for i in range(n):
        mes = i % 12 + 1
        factor = salto if (mes == 1 and i > 0) else base + 0.0004 * math.sin(i * 1.7)
        nivel *= factor
        vals.append(nivel)
    return vals


def _serie_con_ruido(n: int, ruido_pct: float, eventos: dict[int, float]) -> list[float]:
    """Serie con variación de fondo ±ruido_pct (jitter senoidal) y eventos puntuales."""
    import math

    vals, nivel = [], 100.0
    for i in range(n):
        variacion = eventos.get(i, ruido_pct * math.sin(i * 1.7))
        nivel *= 1.0 + variacion
        vals.append(nivel)
    return vals


def test_enero_confirmado_es_patron_calendario() -> None:
    """EN-1: eneros del patrón confirmado no cuentan como atípicos."""
    alertas, _ = _alertas(_serie_salto_enero())
    con_periodo = [a for a in alertas if a.get("periodo")]
    assert con_periodo, "La serie sintética con salto de enero debe generar alertas."
    eneros = [a for a in con_periodo if str(a["periodo"]).endswith("_1")]
    assert eneros, "Los eneros deben aparecer en las alertas consolidadas."
    for alerta in eneros:
        assert alerta.get("clasificacion") == "patron_calendario", alerta
        assert alerta.get("severidad") != "posible_atipico", alerta
    assert not [a for a in con_periodo if a.get("severidad") == "posible_atipico"]


def test_conteos_excluyen_patron_calendario() -> None:
    """Los recuentos de calidad de datos no incluyen los eneros del patrón."""
    alertas, serie = _alertas(_serie_salto_enero())
    validacion = validar_serie_mensual(serie)
    estado = evaluar_calidad_datos(validacion, alertas)
    assert not any("atipic" in str(a).lower() for a in estado.get("advertencias", [])), estado


def test_alertas_deduplicadas_por_periodo() -> None:
    """EN-2: una alerta por periodo, con las escalas que la detectaron."""
    alertas, _ = _alertas(_serie_salto_enero())
    con_periodo = [a for a in alertas if a.get("periodo")]
    periodos = [a["periodo"] for a in con_periodo]
    assert len(periodos) == len(set(periodos)), f"Alertas duplicadas por periodo: {sorted(periodos)}"
    assert any(len(a.get("escalas_detectadas", [])) >= 2 for a in con_periodo), (
        "La alerta consolidada debe conservar las escalas que la detectaron."
    )


def test_enero_sin_patron_puede_ser_atipico() -> None:
    """EN-4: un enero anómalo sin patrón recurrente sigue siendo posible atípico."""
    # 40 meses suaves con un unico enero anomalo (i=24 => 2022_1) que revierte.
    eventos = {24: 0.04, 25: -0.033}
    alertas, _ = _alertas(_serie_con_ruido(40, 0.003, eventos))
    con_periodo = [a for a in alertas if a.get("periodo")]
    enero = [a for a in con_periodo if a["periodo"] == "2022_1"]
    assert enero, f"El enero anomalo aislado debe detectarse: {con_periodo}"
    assert enero[0].get("clasificacion") != "patron_calendario", enero[0]
    assert enero[0].get("severidad") == "posible_atipico", enero[0]


def test_serie_no_se_modifica() -> None:
    """EN-5: la detección no elimina, interpola ni suaviza observaciones."""
    valores = _serie_salto_enero()
    serie = normalizar_serie_mensual(_serie_df(valores))
    derivadas = calcular_variables_derivadas(serie)
    antes = derivadas["serie"]["Indice"].copy()
    detectar_valores_atipicos_mad(derivadas["serie"])
    despues = derivadas["serie"]["Indice"]
    assert len(despues) == len(valores)
    assert np.allclose(antes.to_numpy(dtype=float), despues.to_numpy(dtype=float))


def test_umbrales_salto_anual_sin_cambios() -> None:
    """EN-6: los umbrales del módulo de salto anual quedan intactos (D-4)."""
    assert MIN_TRANSICIONES_SALTO_ANUAL == 2
    assert abs(RATIO_SALTO_ANUAL - 1.5) < 1e-12
    assert abs(CONSISTENCIA_SIGNO_SALTO_ANUAL - 0.6) < 1e-12
    assert abs(TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO - 1.00) < 1e-12


def test_cuatro_clasificaciones_distinguibles() -> None:
    """EN-7: patrón calendario, atípico aislado, cambio de nivel y posible error."""
    # a) patron calendario (cubierto arriba).
    alertas_cal, _ = _alertas(_serie_salto_enero())
    assert any(a.get("clasificacion") == "patron_calendario" for a in alertas_cal if a.get("periodo"))

    # b) posible cambio de nivel: salto de +10% en julio (i=18 => 2021_7) que persiste.
    alertas_nivel, _ = _alertas(_serie_con_ruido(40, 0.002, {18: 0.10}))
    nivel = [a for a in alertas_nivel if a.get("periodo") == "2021_7"]
    assert nivel and nivel[0].get("clasificacion") == "posible_cambio_nivel", alertas_nivel

    # c) posible error de datos: pico extremo (+15%) que revierte por completo al mes siguiente.
    alertas_err, _ = _alertas(_serie_con_ruido(40, 0.002, {18: 0.15, 19: -0.13}))
    error = [a for a in alertas_err if a.get("periodo") == "2021_7"]
    assert error and error[0].get("clasificacion") == "posible_error_datos", alertas_err

    # d) atipico aislado: salto moderado (+2.5% con ruido 0.5%) con reversion parcial >=50%.
    alertas_ais, _ = _alertas(_serie_con_ruido(40, 0.005, {18: 0.025, 19: -0.015}))
    aislado = [a for a in alertas_ais if a.get("periodo") == "2021_7"]
    assert aislado and aislado[0].get("clasificacion") == "posible_atipico_aislado", alertas_ais


def test_serie_real_total_icociv() -> None:
    """EN-3: la serie total pasa de 15 alertas a 5 consolidadas; eneros = patrón."""
    if not RUTA_ANEXO.exists():
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    from app_icociv.datos.cargador_datos import cargar_todas_tablas
    from app_icociv.proyeccion.servicio_proyeccion import construir_serie

    tables, year_month = cargar_todas_tablas(RUTA_ANEXO.read_bytes(), RUTA_ANEXO.name)
    serie = normalizar_serie_mensual(construir_serie(tables["T_16"].loc[[0]], year_month))
    derivadas = calcular_variables_derivadas(serie)
    alertas = [a for a in detectar_valores_atipicos_mad(derivadas["serie"]) if a.get("periodo")]
    periodos = sorted(a["periodo"] for a in alertas)
    assert len(periodos) == len(set(periodos)), periodos
    assert len(periodos) <= 5, periodos
    for alerta in alertas:
        if str(alerta["periodo"]).endswith("_1"):
            assert alerta.get("clasificacion") == "patron_calendario", alerta
    otros = [a for a in alertas if not str(a["periodo"]).endswith("_1")]
    for alerta in otros:
        assert alerta.get("clasificacion") != "patron_calendario", alerta


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: clasificación de atípicos y patron calendario.")
