"""Pruebas del ajuste de salto de cambio de año (diciembre--enero)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.calendario_anual import (
    aplicar_ajuste_calendario,
    eneros_en_horizonte,
    evaluar_ajuste_en_backtesting,
    factor_ajuste_calendario,
    perfil_salto_anual,
)
from app_icociv.proyeccion.servicio_proyeccion import _ajustar_salto_anual


def _serie(anio_inicial: int, meses: int, salto_enero: float, deriva: float) -> pd.DataFrame:
    """Serie mensual sintética con salto controlado en cada enero."""
    periodos, valores = [], []
    valor = 100.0
    anio, mes = anio_inicial, 1
    for _ in range(meses):
        periodos.append(f"{anio}_{mes}")
        valores.append(valor)
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1
        valor *= (1.0 + salto_enero) if mes == 1 else (1.0 + deriva)
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def test_detecta_salto_recurrente() -> None:
    perfil = perfil_salto_anual(_serie(2019, 72, salto_enero=0.05, deriva=0.002))
    assert perfil["hay_evidencia"]
    assert perfil["transiciones"] >= 5
    assert abs(np.exp(perfil["gamma"]) - 1.05) < 1e-6


def test_serie_sin_patron_no_activa_ajuste() -> None:
    perfil = perfil_salto_anual(_serie(2019, 72, salto_enero=0.002, deriva=0.002))
    assert not perfil["hay_evidencia"]


def test_serie_corta_no_activa_ajuste() -> None:
    """Con una sola transición diciembre-enero no hay evidencia suficiente."""
    perfil = perfil_salto_anual(_serie(2023, 15, salto_enero=0.05, deriva=0.002))
    assert not perfil["hay_evidencia"]


def test_factor_es_neutral_a_doce_meses() -> None:
    """El ajuste reconcentra el salto sin alterar el crecimiento anual."""
    for mes_origen in range(1, 13):
        assert abs(factor_ajuste_calendario(0.05, mes_origen, 12) - 1.0) < 1e-12


def test_eneros_en_horizonte() -> None:
    assert eneros_en_horizonte(mes_origen=5, horizonte=3) == 0
    assert eneros_en_horizonte(mes_origen=5, horizonte=8) == 1
    assert eneros_en_horizonte(mes_origen=12, horizonte=1) == 1
    assert eneros_en_horizonte(mes_origen=5, horizonte=24) == 2


def test_ajuste_eleva_enero_y_modera_el_resto() -> None:
    base = [100.0] * 12
    ajustados = aplicar_ajuste_calendario(base, [], mes_origen=11, gamma=0.05)
    # Origen noviembre: el paso 2 cae en enero y concentra el salto.
    assert ajustados[1] > ajustados[0]
    assert ajustados[0] < base[0]
    assert abs(ajustados[11] - base[11]) < 1e-9  # h=12 neutral


def test_backtesting_rechaza_ajuste_que_deteriora() -> None:
    """Si la serie no tiene patrón, el ajuste no debe recomendarse."""
    serie = _serie(2019, 72, salto_enero=0.002, deriva=0.002)
    predicciones = pd.DataFrame(
        {
            "Origen": serie["Periodo"].iloc[40:60].tolist(),
            "Observado": serie["Indice"].iloc[41:61].tolist(),
            "Predicho": serie["Indice"].iloc[40:60].tolist(),
            "Observaciones_entrenamiento": list(range(41, 61)),
        }
    )
    resultado = evaluar_ajuste_en_backtesting(serie, predicciones, horizonte=1)
    assert resultado["evaluado"]
    # Sin evidencia por origen, base y ajustado coinciden.
    assert abs(resultado["mejora_mae"]) < 1e-9


def _backtesting_comparativo_sintetico(serie: pd.DataFrame, modelo: str = "drift") -> dict:
    """Ventanas walk-forward mínimas para los horizontes de validación calendario."""
    from app_icociv.proyeccion.servicio_proyeccion import HORIZONTES_VALIDACION_CALENDARIO

    comparativo = {}
    for h in HORIZONTES_VALIDACION_CALENDARIO:
        origenes = serie["Periodo"].iloc[40:60].tolist()
        comparativo[f"{modelo}_h{h}"] = {
            "predicciones": pd.DataFrame(
                {
                    "Origen": origenes,
                    "Observado": serie["Indice"].iloc[40 + h : 60 + h].tolist(),
                    "Predicho": serie["Indice"].iloc[40:60].tolist(),
                    "Observaciones_entrenamiento": list(range(41, 61)),
                }
            )
        }
    return comparativo


def test_la_activacion_no_depende_de_si_el_horizonte_cruza_enero() -> None:
    """Decisión aprobada: el ajuste es propiedad de la serie, no del horizonte pedido.

    Antes, un horizonte que no cruzaba enero desactivaba el ajuste por completo,
    de modo que la proyección de un mismo mes cambiaba según lo que se pidiera.
    """
    from app_icociv.estadistica.calendario_anual import eneros_en_horizonte

    serie = _serie(2019, 72, salto_enero=0.05, deriva=0.002)  # termina en diciembre
    serie_junio = serie.iloc[:-6].reset_index(drop=True)  # último periodo: junio
    comparativo = _backtesting_comparativo_sintetico(serie_junio)
    assert eneros_en_horizonte(6, 3) == 0, "el horizonte corto no debe cruzar enero"

    corto = _ajustar_salto_anual(
        serie=serie_junio,
        y_futuro=np.array([100.0, 101.0, 102.0]),
        backtesting_comparativo=comparativo,
        modelo_codigo="drift",
        horizonte=3,
    )
    largo = _ajustar_salto_anual(
        serie=serie_junio,
        y_futuro=np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]),
        backtesting_comparativo=comparativo,
        modelo_codigo="drift",
        horizonte=9,
    )
    assert corto["trazabilidad"]["hay_evidencia_calendario"]
    # La decisión de aplicar debe ser la misma en ambos casos.
    assert (
        corto["trazabilidad"]["ajuste_calendario_aplicado"]
        == largo["trazabilidad"]["ajuste_calendario_aplicado"]
    )
    # Y los factores de los pasos comunes deben coincidir exactamente.
    assert np.allclose(corto["factores"][:3], largo["factores"][:3], atol=1e-12)


def test_no_se_aplica_sin_validacion_de_backtesting() -> None:
    """Sin ventanas de validación no se aplica, aunque exista patrón confirmado."""
    serie = _serie(2019, 72, salto_enero=0.05, deriva=0.002)
    salida = _ajustar_salto_anual(
        serie=serie,
        y_futuro=np.array([100.0, 101.0]),
        backtesting_comparativo={},
        modelo_codigo="drift",
        horizonte=2,
    )
    assert salida["trazabilidad"]["hay_evidencia_calendario"]
    assert not salida["trazabilidad"]["ajuste_calendario_aplicado"]
    assert np.allclose(salida["y_futuro"], [100.0, 101.0])


def test_bloque_de_interfaz_aparece_solo_con_patron() -> None:
    from app_icociv.interfaz.presentacion_resultados import construir_html_resultados

    traza = {
        "hay_evidencia_calendario": True,
        "ajuste_calendario_aplicado": True,
        "transiciones_diciembre_enero": 5,
        "salto_mediano_pct": 2.22,
        "movimiento_mensual_tipico_pct": 0.24,
        "ratio_salto_movimiento": 8.95,
        "eneros_en_horizonte": 1,
        "mensaje": "Se detecto un patron recurrente de cambio de anio.",
        "validacion_backtesting": {"evaluado": True, "ventanas": 12, "mejora_mae": 21.6, "mejora_rmse": 21.3},
    }
    html = construir_html_resultados({"ajuste_calendario": traza})
    assert "Patron de cambio de anio" in html
    assert "21,60 %" in html or "21.60 %" in html

    traza_sin = dict(traza, hay_evidencia_calendario=False)
    assert "Patron de cambio de anio" not in construir_html_resultados({"ajuste_calendario": traza_sin})
    assert "Patron de cambio de anio" not in construir_html_resultados({})


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: ajuste de salto anual.")
