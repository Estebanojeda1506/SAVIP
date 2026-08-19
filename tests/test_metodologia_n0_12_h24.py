"""Pruebas dirigidas de la metodologia final N0=12 / H=24 rectangular
(post-r1-metodologia-12-24, Prompt 10). Validada empiricamente en los
Prompts 08/09 sobre MUESTRA_ESTRATIFICADA_SAVIP_10.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.proyeccion.servicio_proyeccion import (
    H_OPERATIVO_MAX,
    HORIZONTE_MAXIMO_OPERATIVO,
    N0_BACKTESTING,
    _matriz_rectangular_12_24,
    _modelos_para_analisis,
    ejecutar_proyeccion,
    validar_horizonte_solicitado,
)
from app_icociv.estadistica.analisis_series import (
    calcular_variables_derivadas,
    detectar_valores_atipicos_mad,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.utilidades.utilidades import ANIO_BASE, periodo_a_t


def _serie_sintetica(n: int, semilla: int = 1, pendiente: float = 0.5, ruido: float = 1.2) -> pd.DataFrame:
    periodos = [f"{2020 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    rng = np.random.default_rng(semilla)
    valores = [100.0 + pendiente * i + rng.normal(0, ruido) for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _objetivo(n: int, h: int) -> tuple[int, int]:
    """(anio, mes) correspondiente a h meses despues de la ultima observacion."""
    last_year = 2020 + (n - 1) // 12
    last_month = (n - 1) % 12 + 1
    tm = last_month + h
    ty = last_year + (tm - 1) // 12
    tm = (tm - 1) % 12 + 1
    return ty, tm


# --------------------------------------------------------------- A y B
def test_a_n0_backtesting_es_12():
    assert N0_BACKTESTING == 12


def test_b_h_operativo_max_es_24():
    assert H_OPERATIVO_MAX == 24
    assert HORIZONTE_MAXIMO_OPERATIVO == 24
    assert validar_horizonte_solicitado(24) == 24
    try:
        validar_horizonte_solicitado(25)
        raise AssertionError("h=25 deberia rechazarse (H_OPERATIVO_MAX=24)")
    except ValueError:
        pass


# --------------------------------------------------------------- C
def test_c_rectangulo_n65_da_w_estrella_30_y_mismos_origenes_por_h():
    n = 65
    df = _serie_sintetica(n, semilla=5)
    sn = normalizar_serie_mensual(df)
    val = validar_serie_mensual(sn)
    s = calcular_variables_derivadas(sn)["serie"].copy()
    s["t"] = s["Periodo"].apply(lambda p: periodo_a_t(p, anio_base=ANIO_BASE))
    out = detectar_valores_atipicos_mad(s)
    modelos, _ = _modelos_para_analisis(
        serie_trabajo=s, horizonte_solicitado=12, validacion_serie=val, outliers=out
    )
    matriz = _matriz_rectangular_12_24(s, modelos, ANIO_BASE)
    assert matriz["suficiente"] is True
    assert matriz["w_estrella"] == 30
    assert n - N0_BACKTESTING - H_OPERATIVO_MAX + 1 == 30

    origenes_por_h = {}
    for modelo in modelos:
        datos = matriz["datos"].get(modelo, {})
        for h in matriz["horizontes"]:
            origenes_por_h.setdefault(h, set()).update(o for (o, hh) in datos if hh == h)
    # Bajo el rectangulo, cada h evaluado usa como maximo el mismo conjunto de
    # 30 origenes -algunos modelos pueden fallar en un origen puntual, pero
    # ninguno puede EXCEDER el conjunto de origenes elegibles del rectangulo-.
    for h, origenes in origenes_por_h.items():
        assert origenes <= set(matriz["origenes"]), f"h={h} usa origenes fuera del rectangulo"
    assert set(matriz["origenes"]) == set(range(N0_BACKTESTING, n - H_OPERATIVO_MAX + 1))


# --------------------------------------------------------------- D
def test_d_seleccion_usa_muestra_comun_y_rmse_global_del_rectangulo():
    n = 45
    df = _serie_sintetica(n, semilla=3)
    ty, tm = _objetivo(n, 12)
    res = ejecutar_proyeccion(df, ty, tm, 2020)
    assert res["proyeccion_generada"] is True
    assert res["rmse_seleccion_oos"] is not None
    assert np.isfinite(res["rmse_seleccion_oos"])
    # El segundo lugar existe y su RMSE es mayor o igual al del ganador.
    assert res["rmse_segundo_oos"] is None or res["rmse_segundo_oos"] >= res["rmse_seleccion_oos"]


# --------------------------------------------------------------- E, F, G
def test_efg_horizonte_solicitado_no_cambia_modelo_ni_trayectoria():
    n = 45
    df = _serie_sintetica(n, semilla=9)
    resultados = {}
    for h in (6, 12, 17, 24):
        ty, tm = _objetivo(n, h)
        resultados[h] = ejecutar_proyeccion(df, ty, tm, 2020)

    modelos = {h: r["modelo_codigo"] for h, r in resultados.items()}
    assert len(set(modelos.values())) == 1, f"el modelo cambio con el horizonte: {modelos}"

    rmses = {h: r["rmse_seleccion_oos"] for h, r in resultados.items()}
    assert len(set(rmses.values())) == 1, f"el RMSE de seleccion cambio con el horizonte: {rmses}"

    # F: trayectoria interna de 24 valores en todos los casos.
    for h, r in resultados.items():
        assert len(r["trayectoria_24_meses"]) == 24

    trayectorias = {h: tuple(r["trayectoria_24_meses"]) for h, r in resultados.items()}
    assert len(set(trayectorias.values())) == 1, "la trayectoria interna de 24 meses debe ser identica"

    # G: y17 mostrado == elemento 17 (indice 16) de la trayectoria de 24.
    r17 = resultados[17]
    assert abs(r17["y_proj"] - r17["trayectoria_24_meses"][16]) < 1e-9


# --------------------------------------------------------------- H
def test_h_distingue_rmse_seleccion_de_rmse_horizonte_solicitado():
    n = 45
    df = _serie_sintetica(n, semilla=11)
    ty, tm = _objetivo(n, 6)
    res = ejecutar_proyeccion(df, ty, tm, 2020)
    rmse_seleccion = res["rmse_seleccion_oos"]
    rmse_horizonte = res["backtesting"]["metricas"]["rmse"]
    # No se afirma que estos numeros SIEMPRE difieran (podrian coincidir por
    # azar si h=1..24 tiene errores homogeneos), pero deben ser conceptos
    # accesibles por separado y ninguno debe faltar.
    assert rmse_seleccion is not None and np.isfinite(rmse_seleccion)
    assert rmse_horizonte is not None and np.isfinite(rmse_horizonte)
    assert res["backtesting"]["horizonte"] == 6
    assert res["backtesting"]["iteraciones"] == res["horizonte_info"]["w_estrella"]


# --------------------------------------------------------------- I
def test_i_historia_insuficiente_devuelve_estado_explicito_no_fallback():
    n = 30  # < N0 + H = 36
    df = _serie_sintetica(n, semilla=2)
    res = ejecutar_proyeccion(df, 2024, 1, 2020)
    assert res["proyeccion_generada"] is False
    assert "12" in res["explicacion"] and "24" in res["explicacion"]
    assert res["horizonte_info"]["historia_suficiente_12_24"] is False
    assert res["horizonte_info"]["w_estrella"] < 1
    # No debe reducir H silenciosamente ni caer a N0=6: no hay proyeccion ni
    # modelo entregado, solo el estado explicito.
    assert res["model_name"] in ("No seleccionado", None)


def test_i_frontera_n36_es_suficiente_w_estrella_1():
    n = N0_BACKTESTING + H_OPERATIVO_MAX  # 36
    df = _serie_sintetica(n, semilla=4, ruido=0.0)
    ty, tm = _objetivo(n, 1)
    res = ejecutar_proyeccion(df, ty, tm, 2020)
    assert res["proyeccion_generada"] is True
    assert res["horizonte_info"]["w_estrella"] == 1


# --------------------------------------------------------------- J
def test_j_no_existe_tolerancia_smape_productiva():
    fuente = Path(ROOT / "app_icociv" / "proyeccion" / "servicio_proyeccion.py").read_text(encoding="utf-8")
    for prohibido in ("tolerancia_smape", "horizonte_operativo_por_tolerancia", "validar_tolerancia_smape"):
        assert prohibido not in fuente, f"'{prohibido}' no deberia existir en esta rama (parte de R1 limpio)"

    import inspect
    from app_icociv.proyeccion import servicio_proyeccion as sp

    firma = inspect.signature(sp.ejecutar_proyeccion)
    assert "tolerancia_smape" not in firma.parameters

    # Grep amplio: ningun archivo de la interfaz debe mencionar la tolerancia
    # (checkbox/spinbox) que existia en la rama experimental descartada.
    resultado = subprocess.run(
        ["git", "-C", str(ROOT), "grep", "-l", "-i", "tolerancia operativa de error"],
        capture_output=True, text=True,
    )
    assert resultado.stdout.strip() == "", f"referencias residuales a la tolerancia: {resultado.stdout}"


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
