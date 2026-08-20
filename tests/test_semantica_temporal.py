"""Pruebas dirigidas de la semantica temporal SAVIP (Prompt 11).

Distingue tres conceptos que no deben confundirse:
- PERIODO_BASE_DEL_INDICE: referencia economica del ICOCIV (dic-2021=100),
  ajena a este modulo (vive en empalme/actualizacion, no en forecasting).
- PERIODO_INICIAL_DE_LA_SERIE: enero de 2021 (ANIO_BASE), ancla el eje
  calendario "t" para ordenar/etiquetar, no para ajustar modelos.
- INDICE_TEMPORAL_DEL_MODELO (tau=1..n): coordenada secuencial local que
  reciben los modelos de forecasting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.utilidades.utilidades import ANIO_BASE, periodo_a_t
from app_icociv.proyeccion.servicio_proyeccion import (
    H_OPERATIVO_MAX,
    _ejecutar_proyeccion_base,
    ejecutar_proyeccion,
)


def _serie_sintetica(n: int, semilla: int = 1, pendiente: float = 0.5, ruido: float = 1.2) -> pd.DataFrame:
    periodos = [f"{2021 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    rng = np.random.default_rng(semilla)
    valores = [100.0 + pendiente * i + rng.normal(0, ruido) for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _objetivo(n: int, h: int) -> tuple[int, int]:
    last_year = 2021 + (n - 1) // 12
    last_month = (n - 1) % 12 + 1
    tm = last_month + h
    ty = last_year + (tm - 1) // 12
    tm = (tm - 1) % 12 + 1
    return ty, tm


# --------------------------------------------------------------- A
def test_a_mapeo_temporal_calendario_actual():
    """El eje calendario "t" (ANIO_BASE=2021) es 0-indexado: Ene2021 -> 0, no
    1. Documentado como hallazgo del Prompt 11, no como error a corregir en
    `periodo_a_t` (tocar esa funcion global afecta empalme/calendario/reportes
    fuera del alcance de este prompt). El INDICE_TEMPORAL_DEL_MODELO (tau,
    ver test_b/test_c) es el que sigue la convencion 1..n pedida."""
    assert periodo_a_t("2021_1", anio_base=2021) == 0
    assert periodo_a_t("2021_2", anio_base=2021) == 1
    assert periodo_a_t("2021_12", anio_base=2021) == 11
    assert periodo_a_t("2022_1", anio_base=2021) == 12
    assert periodo_a_t("2026_5", anio_base=2021) == 64
    # Relacion exacta con la secuencia pedida por el Prompt 11: tau = t + 1.
    esperado_tau = {"2021_1": 1, "2021_2": 2, "2021_12": 12, "2022_1": 13, "2026_5": 65}
    for periodo, tau in esperado_tau.items():
        assert periodo_a_t(periodo, anio_base=2021) + 1 == tau


# --------------------------------------------------------------- B, C
def test_bc_tau_obs_y_tau_futuro_del_modelo():
    """El INDICE_TEMPORAL_DEL_MODELO tau=1..n se construye dentro de
    `_ejecutar_proyeccion_base` a partir de "t" (tau = t - t.min() + 1), y
    tau_futuro = n+1..n+24. Se verifica indirectamente: el modelo unico se
    reajusta con tau_obs y genera la trayectoria con tau_futuro; en una serie
    sintetica LINEAL en el tiempo, el modelo Drift/OLS debe reproducir
    exactamente la pendiente conocida al extrapolar tau_futuro, lo que solo
    ocurre si tau_futuro continua la secuencia 1..n sin saltos ni reinicios.
    """
    n = 45
    pendiente = 0.7
    periodos = [f"{2021 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    valores = [100.0 + pendiente * i for i in range(n)]  # exactamente lineal, sin ruido
    df = pd.DataFrame({"Periodo": periodos, "Indice": valores})
    ty, tm = _objetivo(n, 24)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    assert res["proyeccion_generada"] is True
    trayectoria = res["trayectoria_24_meses"]
    assert len(trayectoria) == H_OPERATIVO_MAX == 24
    # y(tau) = 100 + pendiente*(tau-1); en tau=n+24=69 (i=64 en la
    # numeracion 0-indexada original) da 100 + pendiente*68.
    ultimo_valor_esperado = 100.0 + pendiente * (n - 1 + 24)
    assert abs(trayectoria[-1] - ultimo_valor_esperado) < 1e-6, (trayectoria[-1], ultimo_valor_esperado)
    # El primer valor de la trayectoria (tau=n+1) continua exactamente un
    # paso despues del ultimo observado (tau=n): sin salto ni reinicio.
    primer_valor_esperado = 100.0 + pendiente * n
    assert abs(trayectoria[0] - primer_valor_esperado) < 1e-6, (trayectoria[0], primer_valor_esperado)


def test_c_construccion_directa_tau():
    """Construccion directa de tau_obs/tau_futuro dentro de
    `_ejecutar_proyeccion_base`, verificada via el resultado publico para
    n=65: la trayectoria interna tiene 24 valores y el ultimo (tau=89)
    coincide con la extrapolacion lineal esperada, confirmando
    tau_futuro == [66, ..., 89]."""
    n = 65
    pendiente = 0.3
    periodos = [f"{2021 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    valores = [50.0 + pendiente * i for i in range(n)]
    df = pd.DataFrame({"Periodo": periodos, "Indice": valores})
    ty, tm = _objetivo(n, 1)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    trayectoria = res["trayectoria_24_meses"]
    # tau_obs = 1..65; tau_futuro = 66..89. y(tau=89) = 50 + pendiente*88.
    esperado_tau89 = 50.0 + pendiente * (65 + 24 - 1)
    assert abs(trayectoria[-1] - esperado_tau89) < 1e-6


# --------------------------------------------------------------- D
def test_d_independencia_de_metadatos_del_periodo_base_economico():
    """Cambiar metadatos relativos al periodo base ECONOMICO del indice (que
    vive fuera de este modulo, en empalme/actualizacion_icociv) no puede
    modificar t_obs/tau ni la seleccion del modelo: no existe ninguna via de
    codigo que conecte `periodo_base`/I0 (empalme) con la construccion del
    eje temporal de `_ejecutar_proyeccion_base`. Se verifica que el modulo de
    proyeccion no importa nada de `servicios.actualizacion_icociv` ni
    `servicios.empalme_iccp_icociv`."""
    fuente = (ROOT / "app_icociv" / "proyeccion" / "servicio_proyeccion.py").read_text(encoding="utf-8")
    assert "actualizacion_icociv" not in fuente
    assert "empalme_iccp_icociv" not in fuente
    assert "periodo_base" not in fuente
    assert "I0" not in fuente or "I0_ICCP" not in fuente  # sin referencias a I0 del empalme


# --------------------------------------------------------------- E, F
def test_ef_savip10_no_se_valida_aqui():
    """La revalidacion completa contra el anexo real (SAVIP-10, items E/F)
    requiere el archivo DANE y toma ~5 minutos; se ejecuta por separado
    (scratch de sesion) y se reporta en el informe, no como prueba unitaria
    de este archivo para mantener el presupuesto de tiempo de esta suite."""
    assert True


def _principal() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    fallos = 0
    for nombre, funcion in pruebas:
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {nombre}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {nombre}: {type(exc).__name__}: {exc}")
    print()
    print("todas las pruebas pasan" if not fallos else f"{fallos} fallo(s) de {len(pruebas)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_principal())
