"""Seleccion por RMSE fuera de muestra global (C-SEL-001, 08-08-2026).

Cierra H-9, la ultima heuristica decisoria del producto.

QUE SE RETIRA. Hasta esta fecha el modelo lo elegia
`_modelo_trayectoria_consistente`: promedio del RMSE relativo al mejor de cada
horizonte, **ponderado con peso 1/h**. El peso no tenia fuente -su justificacion
era operativa, «la evidencia de corto plazo es mas confiable y mas usada»- y
cambiaba el modelo entregado. Medido sobre las diez series del anexo de mayo de
2026, la regla nueva y la vieja discrepan en **una**.

QUE ENTRA.

    RMSE_global(m) = sqrt( SUM_{(t,h) in S} e(m,t,h)^2 / |S| )
    m* = argmin_m RMSE_global(m)

con ``S`` la muestra comun: los pares (objetivo, horizonte) en los que **todos**
los candidatos tienen error finito. Sin parametros libres, sin umbrales, sin
imputacion y sin minimos de tamano.

PONDERACION IMPLICITA, DECLARADA. Cada observacion pesa igual, pero los
horizontes largos aportan errores mayores: sobre el anexo, h=18 pone el 2,6 % de
las observaciones y hasta el 8,8 % de la suma de cuadrados. El peso lo pone la
magnitud medida, no una constante elegida. Es la direccion contraria a 1/h y hay
que saberlo al leer el resultado.

Ejecucion:
    python tests/test_seleccion_rmse_global.py
"""
from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion import servicio_proyeccion as sp  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    seleccionar_modelo_por_rmse_oos_global,
)


def banco(errores_por_modelo: dict[str, dict[int, list[float]]]) -> dict[str, dict]:
    """Banco sintetico: {modelo: {h: [errores por origen]}}.

    Los objetivos ``t`` se numeran de forma que el par (t, h) sea comparable
    entre modelos: mismo indice, mismo horizonte.
    """
    salida: dict[str, dict] = {}
    for modelo, por_h in errores_por_modelo.items():
        for h, errores in por_h.items():
            salida[f"{modelo}_h{h}"] = {
                "ejecutado": True,
                "predicciones": pd.DataFrame({
                    "t": [100 + i for i in range(len(errores))],
                    "Error": list(errores),
                    "Observado": [100.0] * len(errores),
                    "Predicho": [100.0 - e for e in errores],
                }),
                "metricas": {"rmse": float(np.sqrt(np.mean(np.square(errores))))},
            }
    return salida


def rmse_global(errores: list[float]) -> float:
    return math.sqrt(sum(e ** 2 for e in errores) / len(errores))


# ======================================================================
# 1. La formula
# ======================================================================
def test_elige_el_minimo_rmse_global():
    b = banco({
        "a": {1: [1.0, 1.0], 2: [1.0, 1.0]},
        "b": {1: [0.5, 0.5], 2: [0.5, 0.5]},
    })
    assert seleccionar_modelo_por_rmse_oos_global(b, (1, 2)) == "b"


def test_el_valor_es_la_raiz_del_error_cuadratico_medio():
    """Se comprueba contra el calculo directo, no contra otra implementacion."""
    errores_a = [1.0, 2.0, 3.0, 4.0]
    errores_b = [2.5, 2.5, 2.5, 2.5]
    b = banco({"a": {1: errores_a[:2], 2: errores_a[2:]},
               "b": {1: errores_b[:2], 2: errores_b[2:]}})
    # a: sqrt((1+4+9+16)/4) = 2.7386 ; b: 2.5  -> gana b
    assert rmse_global(errores_a) > rmse_global(errores_b)
    assert seleccionar_modelo_por_rmse_oos_global(b, (1, 2)) == "b"


def test_no_hay_peso_por_horizonte():
    """El caso que separa a las dos reglas.

    `corto` domina en h=1 y pierde en h=18; `largo` al reves. Con peso 1/h gana
    `corto`; minimizando la perdida cuadratica total gana `largo`.
    """
    b = banco({
        "corto": {1: [1.0] * 4, 18: [3.0] * 4},
        "largo": {1: [1.3] * 4, 18: [2.0] * 4},
    })
    assert seleccionar_modelo_por_rmse_oos_global(b, (1, 18)) == "largo"
    # Y la regla retirada elegiria el otro, que es justo lo que se corrige.
    evaluaciones = [
        {"horizonte": h, "backtesting_por_modelo": {
            "corto": {"metricas": {"rmse": rc}}, "largo": {"metricas": {"rmse": rl}}}}
        for h, rc, rl in ((1, 1.0, 1.3), (18, 3.0, 2.0))
    ]
    assert sp._modelo_trayectoria_consistente(evaluaciones) == "corto"


# ======================================================================
# 2. La muestra comun
# ======================================================================
def test_solo_compara_pares_presentes_en_todos():
    """Un modelo con menos observaciones no puede ganar por tener menos.

    `parcial` solo falla -error grande- en el par que le falta a `completo`.
    Si la comparacion no se restringiera a la interseccion, `parcial` ganaria
    por omision.
    """
    b = banco({"completo": {1: [1.0, 1.0, 1.0]}, "parcial": {1: [0.9, 0.9]}})
    # La interseccion son los dos primeros pares: parcial gana ahi, legitimamente.
    assert seleccionar_modelo_por_rmse_oos_global(b, (1,)) == "parcial"
    # Con el tercer par a favor de completo, la interseccion sigue siendo de dos
    # y el resultado no cambia: nadie puntua sobre observaciones que el otro no tiene.
    b2 = banco({"completo": {1: [1.0, 1.0, 0.01]}, "parcial": {1: [0.9, 0.9]}})
    assert seleccionar_modelo_por_rmse_oos_global(b2, (1,)) == "parcial"


def test_sin_muestra_comun_no_se_elige():
    """Sin observaciones comparables no se afirma nada: cae al camino previo."""
    b = {
        "a_h1": {"ejecutado": True, "metricas": {"rmse": 1.0},
                 "predicciones": pd.DataFrame({"t": [1], "Error": [1.0]})},
        "b_h1": {"ejecutado": True, "metricas": {"rmse": 1.0},
                 "predicciones": pd.DataFrame({"t": [2], "Error": [1.0]})},
    }
    assert seleccionar_modelo_por_rmse_oos_global(b, (1,)) is None


def test_banco_vacio_devuelve_none():
    assert seleccionar_modelo_por_rmse_oos_global({}, (1, 2)) is None


def test_los_errores_no_finitos_no_participan():
    b = banco({"a": {1: [1.0, 1.0]}, "b": {1: [0.5, float("nan")]}})
    # El par no finito de `b` sale de la muestra comun; queda uno, y `b` gana ahi.
    assert seleccionar_modelo_por_rmse_oos_global(b, (1,)) == "b"


# ======================================================================
# 3. Invariancias y determinismo
# ======================================================================
def test_invariante_al_orden_de_los_horizontes():
    b = banco({"a": {1: [1.0, 2.0], 6: [3.0, 1.0], 12: [2.0, 2.0]},
               "b": {1: [1.5, 1.5], 6: [1.5, 1.5], 12: [1.5, 1.5]}})
    referencia = seleccionar_modelo_por_rmse_oos_global(b, (1, 6, 12))
    for orden in ((12, 6, 1), (6, 1, 12), (12, 1, 6)):
        assert seleccionar_modelo_por_rmse_oos_global(b, orden) == referencia


def test_invariante_al_orden_de_los_candidatos():
    directo = banco({"a": {1: [1.0, 2.0]}, "b": {1: [1.5, 1.5]}})
    invertido = {k: directo[k] for k in reversed(list(directo))}
    assert (seleccionar_modelo_por_rmse_oos_global(directo, (1,))
            == seleccionar_modelo_por_rmse_oos_global(invertido, (1,)))


def test_el_empate_exacto_se_resuelve_por_orden_de_aparicion():
    """Determinista y sin preferencia por identidad, complejidad ni metrica."""
    b = banco({"primero": {1: [1.0, 1.0]}, "segundo": {1: [1.0, 1.0]}})
    assert seleccionar_modelo_por_rmse_oos_global(b, (1,)) == "primero"


def test_es_reproducible():
    b = banco({"a": {1: [1.0, 2.0], 3: [2.0, 1.0]}, "b": {1: [1.4, 1.4], 3: [1.4, 1.4]}})
    resultados = {seleccionar_modelo_por_rmse_oos_global(b, (1, 3)) for _ in range(5)}
    assert len(resultados) == 1


# ======================================================================
# 4. Lo que la regla NO consulta
# ======================================================================
def test_la_regla_no_consulta_umbrales_ni_identidad():
    for funcion in (sp.seleccionar_modelo_por_rmse_oos_global,
                    sp._errores_oos_por_par,
                    sp._modelo_consistente_desde_comparativo):
        fuente = inspect.getsource(funcion)
        for prohibido in ("UMBRAL_", "TOLERANCIA_", "MIN_ERRORES", "COBERTURA_IC95",
                          "es_benchmark", "MODELOS_BENCHMARK", "estado"):
            assert prohibido not in fuente, (funcion.__name__, prohibido)


def test_no_queda_el_peso_1_h_en_la_ruta_de_seleccion():
    fuente = inspect.getsource(sp._modelo_consistente_desde_comparativo)
    assert "1.0 / float(horizonte)" not in fuente
    assert "seleccionar_modelo_por_rmse_oos_global" in fuente
    assert "_modelo_trayectoria_consistente" not in fuente


def test_la_regla_retirada_ya_no_se_invoca_en_la_ruta_productiva():
    """`_modelo_trayectoria_consistente` se conserva por historia, no por uso."""
    fuente_modulo = inspect.getsource(sp)
    llamadas = fuente_modulo.count("_modelo_trayectoria_consistente(")
    assert llamadas == 1, (
        f"solo debe quedar su definicion, no llamadas ({llamadas})"
    )


def test_un_solo_modelo_para_toda_la_trayectoria():
    """La propiedad que la regla anterior introdujo y esta conserva."""
    b = banco({"a": {1: [1.0], 3: [1.0], 18: [1.0]},
               "b": {1: [2.0], 3: [2.0], 18: [2.0]}})
    for horizontes in ((1,), (1, 3), (1, 3, 18)):
        assert seleccionar_modelo_por_rmse_oos_global(b, horizontes) == "a"


# ======================================================================
# 5. Reproduccion desde los errores OOS
# ======================================================================
def test_el_resultado_se_reproduce_desde_los_errores():
    """Quien audite debe poder recalcularlo con los errores publicados."""
    errores = {"a": {1: [1.0, 2.0], 6: [3.0, 2.0]},
               "b": {1: [2.0, 2.0], 6: [2.0, 2.0]}}
    b = banco(errores)
    planos = {m: [e for lista in por_h.values() for e in lista]
              for m, por_h in errores.items()}
    esperado = min(planos, key=lambda m: rmse_global(planos[m]))
    assert seleccionar_modelo_por_rmse_oos_global(b, (1, 6)) == esperado


def _ejecutar() -> int:
    fallos = 0
    for nombre, prueba in sorted(globals().items()):
        if nombre.startswith("test_") and callable(prueba):
            try:
                prueba()
                print(f"  OK   {nombre}")
            except AssertionError as exc:
                fallos += 1
                print(f"  FALLA {nombre}: {exc}")
    print(f"\n{'todas las pruebas pasan' if not fallos else f'{fallos} fallidas'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
