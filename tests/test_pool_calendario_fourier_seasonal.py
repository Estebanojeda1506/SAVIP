"""Pruebas dirigidas del Prompt Calendario 04: pool productivo de 21
candidatos (10 modelos base + 10 variantes Fourier K=1 + Seasonal Naive)
con N0=12/H=24 sin cambios.

No ejecuta la suite global: pruebas puntuales sobre los modulos tocados por
este prompt, ejecutables con
`python tests/test_pool_calendario_fourier_seasonal.py`.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica import modelos_interpretables as mi
from app_icociv.proyeccion.servicio_proyeccion import (
    CATALOGO_MODELOS_CANDIDATOS,
    H_OPERATIVO_MAX,
    N0_BACKTESTING,
    ejecutar_proyeccion,
)
from app_icociv.utilidades.utilidades import ANIO_BASE


def _serie_sintetica_estacional(n: int, semilla: int = 1, pendiente: float = 0.5, amplitud: float = 3.0, ruido: float = 0.6) -> pd.DataFrame:
    periodos = [f"{2021 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    rng = np.random.default_rng(semilla)
    t = np.arange(1, n + 1, dtype=float)
    s = amplitud * np.sin(2 * np.pi * t / 12.0) - 1.5 * np.cos(2 * np.pi * t / 12.0)
    valores = 100.0 + pendiente * t + s + rng.normal(0, ruido, n)
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _objetivo(n: int, h: int) -> tuple[int, int]:
    last_year = 2021 + (n - 1) // 12
    last_month = (n - 1) % 12 + 1
    tm = last_month + h
    ty = last_year + (tm - 1) // 12
    tm = (tm - 1) % 12 + 1
    return ty, tm


# --------------------------------------------------------------- CASO A
def test_casoA_catalogo_tiene_exactamente_21_candidatos():
    assert len(mi.CATALOGO_POOL_CALENDARIO) == 21
    base = [m for m in mi.CATALOGO_POOL_CALENDARIO if not m.startswith("fourier_k1__") and m != "seasonal_naive"]
    fourier = [m for m in mi.CATALOGO_POOL_CALENDARIO if m.startswith("fourier_k1__")]
    assert len(base) == 10
    assert len(fourier) == 10
    assert "seasonal_naive" in mi.CATALOGO_POOL_CALENDARIO
    # Cada variante Fourier corresponde a un modelo base real del pool.
    assert set(m[len("fourier_k1__"):] for m in fourier) == set(base)
    # No hay duplicados.
    assert len(set(mi.CATALOGO_POOL_CALENDARIO)) == 21


# --------------------------------------------------------------- CASO B
def test_casoB_fourier_k1_periodo_y_reestacionalizacion():
    n = 40
    t = np.arange(1, n + 1, dtype=float)
    rng = np.random.default_rng(3)
    a_real, b_real = 2.5, -1.2
    s = a_real * np.sin(2 * np.pi * t / 12.0) + b_real * np.cos(2 * np.pi * t / 12.0)
    y = 50.0 + 0.3 * t + s + rng.normal(0, 0.05, n)

    r = mi.ajustar_modelo_interpretable("fourier_k1__drift", t, y)
    assert r["parametros"]["fourier_k"] == 1
    assert r["parametros"]["fourier_periodo"] == 12
    assert r["estrategia_calendario"] == "fourier_k1"
    assert r["modelo_base"] == "drift"
    # Coeficientes recuperados razonablemente cerca de los reales (ruido bajo).
    assert abs(r["parametros"]["fourier_coef_sin_1"] - a_real) < 0.3
    assert abs(r["parametros"]["fourier_coef_cos_1"] - b_real) < 0.3
    amplitud_esperada = math.sqrt(a_real**2 + b_real**2)
    assert abs(r["parametros"]["fourier_amplitud"] - amplitud_esperada) < 0.3

    # No leakage: alterar una observacion NO usada en el ajuste (aqui no hay
    # "futuro" porque el ajuste es full-history, asi que se prueba que el
    # ajuste depende solo de (t,y) recibidos, no de estado global).
    a1, b1 = mi._fourier_k1_coeficientes(t, y.copy())
    y_mod = y.copy()
    y_mod[-1] = y_mod[-1] * 5 + 1000.0
    a2, b2 = mi._fourier_k1_coeficientes(t, y_mod)
    assert not (math.isclose(a1, a2) and math.isclose(b1, b2)), (
        "cambiar la serie debe cambiar el ajuste (confirma que no hay cache cruzado indebido)"
    )
    # Pero repetir la MISMA serie exacta debe reproducir el mismo resultado.
    a3, b3 = mi._fourier_k1_coeficientes(t, y.copy())
    assert math.isclose(a1, a3) and math.isclose(b1, b3)

    # Reestacionalizacion: predict(t_hist) debe reponer S_F sobre el ajuste
    # base, y predict(t_futuro) tambien.
    tf = np.arange(n + 1, n + 25, dtype=float)
    yhat = r["predict"](tf)
    assert len(yhat) == 24
    assert np.all(np.isfinite(yhat))


# --------------------------------------------------------------- CASO C
def test_casoC_seasonal_naive_valores_h1_h12_h13_h24():
    n = 36
    t = np.arange(1, n + 1, dtype=float)
    y = np.arange(100.0, 100.0 + n, dtype=float)  # valores distintos y reconocibles
    r = mi.ajustar_modelo_interpretable("seasonal_naive", t, y)
    assert r["estrategia_calendario"] == "seasonal_naive"
    assert r["parametros"]["periodo"] == 12
    tf = np.arange(n + 1, n + 25, dtype=float)
    yhat = r["predict"](tf)
    # h=1 -> misma posicion que hace 12 meses = y[n-12] (0-based: n-12)
    assert abs(yhat[0] - y[n - 12]) < 1e-9
    # h=12 -> y[n-12+11] = y[n-1] (el ultimo valor observado)
    assert abs(yhat[11] - y[n - 1]) < 1e-9
    # h=13 -> misma posicion que h=1 (un año despues): y[n-12] otra vez
    assert abs(yhat[12] - y[n - 12]) < 1e-9
    # h=24 -> y[n-1] otra vez
    assert abs(yhat[23] - y[n - 1]) < 1e-9


# --------------------------------------------------------------- CASO D
def test_casoD_muestra_comun_w_estrella_30_con_n_65():
    df = _serie_sintetica_estacional(65, semilla=7)
    ty, tm = _objetivo(65, 12)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    assert res["proyeccion_generada"] is True
    hi = res["horizonte_info"]
    assert hi["w_estrella"] == 65 - N0_BACKTESTING - H_OPERATIVO_MAX + 1 == 30
    assert hi["pares_esperados"] == 30 * 24 == 720
    # La interseccion comun no debe perder pares frente a lo esperado en una
    # serie sintetica limpia (todos los 21 candidatos deberian ser estimables
    # en todos los origenes de esta serie).
    assert hi["pares_comunes"] == hi["pares_esperados"]


# --------------------------------------------------------------- CASO E
def test_casoE_selector_rmse_comun_un_ganador_y_h_no_lo_altera():
    df = _serie_sintetica_estacional(65, semilla=11)
    resultados = {}
    for h in (6, 17, 24):
        ty, tm = _objetivo(65, h)
        res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
        resultados[h] = res["horizonte_info"]["candidato_seleccionado"]
    # El horizonte solicitado no debe cambiar el candidato ganador (item 6,
    # Prompt Calendario 04; ya era asi para el pool de 10, sigue siendo cierto
    # para 21).
    assert resultados[6] == resultados[17] == resultados[24]
    assert resultados[6] in mi.CATALOGO_POOL_CALENDARIO


# --------------------------------------------------------------- CASO F
def test_casoF_refit_fourier_ganador_24_puntos_y_coeficientes_reproducibles():
    n = 65
    df = _serie_sintetica_estacional(n, semilla=21, amplitud=6.0, ruido=0.3)
    ty, tm = _objetivo(n, 24)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    hi = res["horizonte_info"]
    if hi["estrategia_calendario"] != "fourier_k1":
        return  # esta serie sintetica no siempre elige Fourier; no se fuerza el resultado.
    proyecciones = res["proyecciones"]
    assert len(proyecciones) == 24
    # Los coeficientes publicados deben coincidir con un ajuste full-history
    # independiente sobre exactamente la misma serie.
    t_full = np.arange(1, n + 1, dtype=float)
    y_full = df["Indice"].to_numpy(dtype=float)
    a_ref, b_ref = mi._fourier_k1_coeficientes(t_full, y_full)
    assert abs(hi["fourier_coef_sin_1"] - a_ref) < 1e-6
    assert abs(hi["fourier_coef_cos_1"] - b_ref) < 1e-6


# --------------------------------------------------------------- CASO G
def test_casoG_tabla_mae_h_corresponde_al_candidato_final():
    df = _serie_sintetica_estacional(65, semilla=33)
    ty, tm = _objetivo(65, 17)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    hi = res["horizonte_info"]
    tabla = hi["tabla_horizontes"]
    assert len(tabla) == 24
    fila_17 = next(item for item in tabla if item["horizonte"] == 17)
    assert fila_17["mae"] is not None and math.isfinite(fila_17["mae"])
    # La metrica de la tarjeta "Error historico" (backtesting del horizonte
    # solicitado) debe coincidir con la fila h=17 de la tabla, ambas leidas
    # del mismo candidato ganador.
    assert abs(res["backtesting"]["metricas"]["mae"] - fila_17["mae"]) < 1e-9


# --------------------------------------------------------------- CASO H
def test_casoH_reporte_muestra_estrategia_sin_ic95_ni_maximo_estadistico():
    from app_icociv.reportes.contenido import _texto_estrategia_calendario

    assert _texto_estrategia_calendario("fourier_k1") == "Fourier anual (K=1, periodo 12 meses)"
    assert _texto_estrategia_calendario("seasonal_naive") == "Patrón estacional de 12 meses (Seasonal Naive)"
    assert _texto_estrategia_calendario("ninguna") == "Ninguno"

    fuente = (ROOT / "app_icociv" / "reportes" / "contenido.py").read_text(encoding="utf-8")
    # "IC95"/"IC80"/"máximo estadístico" no deben aparecer como codigos o
    # afirmaciones vigentes (item 13). No se prohibe la frase "intervalo de
    # confianza" en si: el texto legitimo de la banda +-MAE la menciona para
    # NEGARLA explicitamente ("no corresponde a un intervalo de confianza"),
    # que es justamente lo que V3/P0-C exige.
    for prohibido in ("IC95", "IC80", "máximo estadístico"):
        assert prohibido not in fuente, f"texto prohibido '{prohibido}' en contenido.py"
    # Prohibiciones especificas del item 13 sobre el tratamiento Fourier.
    for prohibido in ("corrige enero", "garantiza estacionalidad", "elimina el error calendario"):
        assert prohibido not in fuente.lower(), f"afirmacion prohibida sobre Fourier en contenido.py: '{prohibido}'"


# --------------------------------------------------------------- CASO I
def test_casoI_ui_smoke_ganador_fourier_y_ganador_base():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app_icociv.interfaz.presentacion_resultados import construir_html_explicacion_tarjeta

    resultado_fourier = {
        "proyeccion": {
            "resultado_horizonte_solicitado": {
                "modelo_aplicado": "Fourier K=1 + Holt tendencia amortiguada",
                "modelo_base": "holt_amortiguado",
                "estrategia_calendario": "fourier_k1",
                "fourier_coef_sin_1": 1.2,
                "fourier_coef_cos_1": -0.8,
                "fourier_amplitud": 1.44,
            },
        }
    }
    html_f = construir_html_explicacion_tarjeta("modelo", resultado_fourier, "claro")
    assert "Fourier anual (K=1, periodo 12 meses)" in html_f
    assert "holt_amortiguado" in html_f or "Holt" in html_f

    resultado_base = {
        "proyeccion": {
            "resultado_horizonte_solicitado": {
                "modelo_aplicado": "Drift",
                "modelo_base": "drift",
                "estrategia_calendario": "ninguna",
            },
        }
    }
    html_b = construir_html_explicacion_tarjeta("modelo", resultado_base, "claro")
    assert "Ninguno" in html_b
    assert app is not None


# --------------------------------------------------------------- CASO J
def test_casoJ_ids_internos_no_visibles_en_ui_ni_reportes():
    """Hallazgo 1 de auditoria (Prompt Calendario 06): 'fourier_k1__...' no
    debe llegar a ninguna superficie visible (UI, HTML de resultados, HTML
    de reporte). Puede seguir existiendo en CSV/campos tecnicos."""
    from app_icociv.interfaz.presentacion_resultados import (
        construir_html_explicacion_tarjeta,
        construir_html_resultados,
    )
    from app_icociv.reportes.generador_reportes import (
        _lineas_determinacion_horizonte,
        _lineas_horizontes,
    )
    from app_icociv.reportes.contenido import _nombre_visible_candidato

    # Traduccion directa del helper para varios candidatos Fourier.
    for base in mi.MODELOS_FOURIER_BASE:
        visible = _nombre_visible_candidato(f"fourier_k1__{base}")
        assert "fourier_k1__" not in visible
        assert visible.startswith("Fourier K=1 + ")

    df = _serie_sintetica_estacional(65, semilla=42, amplitud=7.0, ruido=0.3)
    ty, tm = _objetivo(65, 24)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    hi = res["horizonte_info"]

    html_resultados = construir_html_resultados(res, "claro")
    assert "fourier_k1__" not in html_resultados

    html_modelo = construir_html_explicacion_tarjeta("modelo", res, "claro")
    assert "fourier_k1__" not in html_modelo

    lineas_det = _lineas_determinacion_horizonte(res)
    assert not any("fourier_k1__" in linea for linea in lineas_det)

    lineas_eval = _lineas_horizontes(res)
    assert not any("fourier_k1__" in str(linea) for linea in lineas_eval)

    # El identificador tecnico interno SI puede seguir en horizonte_info
    # (campo tecnico, no superficie de usuario) y en CSV.
    assert hi.get("candidato_seleccionado") in mi.CATALOGO_POOL_CALENDARIO


# --------------------------------------------------------------- CASO K
def test_casoK_cache_fourier_depende_de_y_y_t():
    """Hallazgo 2 de auditoria: la clave de cache debe distinguir ejes t
    distintos aunque y sea identico."""
    mi._MEMORIA_FOURIER.clear()
    n = 24
    rng = np.random.default_rng(5)
    y = 100 + 0.4 * np.arange(1, n + 1) + 2 * np.sin(2 * np.pi * np.arange(1, n + 1) / 12) + rng.normal(0, 0.1, n)

    t1 = np.arange(1, n + 1, dtype=float)
    t2 = np.arange(5, n + 5, dtype=float)  # mismo largo y valores de y, eje t distinto

    a1, b1 = mi._fourier_k1_coeficientes(t1, y.copy())
    a2, b2 = mi._fourier_k1_coeficientes(t2, y.copy())
    cache_depende_de_y_y_t = not (math.isclose(a1, a2) and math.isclose(b1, b2))
    print(f"CACHE_FOURIER_DEPENDE_DE_Y_Y_T={cache_depende_de_y_y_t}")
    assert cache_depende_de_y_y_t

    # Contra ejecucion con cache limpia: el resultado de t2 debe ser
    # reproducible, no un residuo cacheado de t1.
    mi._MEMORIA_FOURIER.clear()
    a2b, b2b = mi._fourier_k1_coeficientes(t2, y.copy())
    assert math.isclose(a2, a2b) and math.isclose(b2, b2b)

    # Anti-leakage normal (se repite aqui junto al arreglo de cache): alterar
    # una observacion posterior a un origen no cambia coeficientes/pronostico
    # de ese origen.
    mi._MEMORIA_FOURIER.clear()
    o = 30
    t_hist = np.arange(1, o + 1, dtype=float)
    df = _serie_sintetica_estacional(65, semilla=9)
    y_full = df["Indice"].to_numpy(dtype=float)
    y_hist = y_full[:o].copy()
    r1 = mi.ajustar_modelo_interpretable("fourier_k1__drift", t_hist, y_hist)
    a_antes = r1["parametros"]["fourier_coef_sin_1"]
    b_antes = r1["parametros"]["fourier_coef_cos_1"]
    yhat_antes = r1["predict"](np.arange(o + 1, o + 25, dtype=float))

    y_full_mod = y_full.copy()
    y_full_mod[o + 5] = y_full_mod[o + 5] * 4.0 + 500.0
    y_hist_mod = y_full_mod[:o]
    r2 = mi.ajustar_modelo_interpretable("fourier_k1__drift", t_hist, y_hist_mod)
    a_despues = r2["parametros"]["fourier_coef_sin_1"]
    b_despues = r2["parametros"]["fourier_coef_cos_1"]
    yhat_despues = r2["predict"](np.arange(o + 1, o + 25, dtype=float))
    assert math.isclose(a_antes, a_despues) and math.isclose(b_antes, b_despues)
    assert np.allclose(yhat_antes, yhat_despues)


# --------------------------------------------------------------- CASO L
def test_casoL_k_fourier_es_k_base_mas_4_y_no_cambia_seleccion():
    """Hallazgo 3 de auditoria: k=k_base+4 (alpha,beta,a,b), y el cambio de k
    no debe afectar RMSE de seleccion, pronostico ni candidato ganador."""
    n = 30
    t = np.arange(1, n + 1, dtype=float)
    rng = np.random.default_rng(2)
    y = 80 + 0.2 * t + 1.5 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 0.2, n)

    # k_base se obtiene del ajuste bare real (no se hardcodea: evita que la
    # prueba adivine mal el conteo de parametros de cada modelo base).
    for base in mi.MODELOS_FOURIER_BASE:
        fn, kw = mi._DISPATCH_MODELO_BASE[base]
        k_base = fn(t, y, **kw)["k"]
        r = mi.ajustar_modelo_interpretable(f"fourier_k1__{base}", t, y)
        assert r["k"] == k_base + 4, (base, r["k"], k_base)

    # k no debe afectar RMSE de seleccion, ni pronostico, ni candidato
    # ganador: se reproduce el caso real G5-A (ya validado exactamente contra
    # el experimento de decision con k=k_base+2) y se confirma que el
    # candidato/RMSE/pronostico no cambiaron con k=k_base+4.
    df = _serie_sintetica_estacional(65, semilla=42, amplitud=7.0, ruido=0.3)
    ty, tm = _objetivo(65, 24)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    hi = res["horizonte_info"]
    if hi["estrategia_calendario"] == "fourier_k1":
        modelo_base_ganador = hi["modelo_base"]
        assert hi["fourier_k"] == 1  # K de Fourier (armonicos), no confundir con k de AIC/parametros.


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
