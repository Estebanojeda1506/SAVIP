"""Estabilidad numerica del RMSE fuera de muestra global (hallazgo clase B).

`seleccionar_modelo_por_rmse_oos_global` evaluaba la suma de cuadrados de forma
ingenua:

    suma_cuadrados = sum(errores[par] ** 2 for par in comunes)

Con errores INDIVIDUALMENTE FINITOS pero muy grandes -medido: 3,72e155 en el
fixture `_serie_erratica(72)`- el cuadrado excede el rango del flotante y, al ser
`float` de Python, el operador `**` levanta `OverflowError` en vez de devolver
`inf`. La guarda `np.isfinite(rmse_global)` de la linea siguiente, escrita
justamente para excluir candidatos divergentes, nunca se alcanzaba y la excepcion
abortaba `ejecutar_proyeccion` entera.

La correccion es **puramente numerica**: la misma expresion evaluada de forma
estable.

    RMSE = sqrt((e_1^2 + ... + e_n^2) / n) = hypot(e_1, ..., e_n) / sqrt(n)

No cambia la metrica, ni la muestra comun, ni los pesos, ni el orden de
candidatos, ni el desempate, ni la guarda. No hay clipping, epsilon, umbral de
magnitud, descarte por tamano ni tope de horizonte.

Ejecucion directa, sin pytest:

    python tests/test_rmse_global_estable.py
"""
from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    _rmse_global_estable,
    seleccionar_modelo_por_rmse_oos_global,
)


def _banco(errores_por_modelo: dict[str, dict[tuple[int, int], float]]) -> dict:
    """Banco de backtesting minimo con la forma exacta que consume el selector.

    `_errores_oos_por_par` espera claves ``"{modelo}_h{h}"`` y, en cada una, un
    DataFrame `predicciones` con las columnas `t` y `Error`. Se construye a mano
    para que la muestra comun, los pares y el orden de los candidatos sean
    EXACTAMENTE los que la prueba declara: ningun caso depende de que un modelo
    real diverja de una forma concreta.
    """
    banco: dict[str, dict] = {}
    for modelo, errores in errores_por_modelo.items():
        por_horizonte: dict[int, list[tuple[int, float]]] = {}
        for (objetivo, horizonte), error in errores.items():
            por_horizonte.setdefault(horizonte, []).append((objetivo, error))
        for horizonte, filas in por_horizonte.items():
            banco[f"{modelo}_h{horizonte}"] = {
                "ejecutado": True,
                "predicciones": pd.DataFrame(
                    {"t": [f[0] for f in filas], "Error": [f[1] for f in filas]}
                ),
            }
    return banco


# ==============================
# T1-T6: el calculo de la norma
# ==============================


def test_t1_ordinario_coincide_con_la_formula_directa() -> None:
    """T1. En el rango ordinario ambas formas dan el mismo numero."""
    for valores in ([1.0, 2.0, 3.0], [0.5], [-4.0, 4.0], list(np.linspace(-9, 9, 25))):
        directo = math.sqrt(sum(v ** 2 for v in valores) / len(valores))
        estable = _rmse_global_estable(valores)
        assert math.isclose(estable, directo, rel_tol=1e-12, abs_tol=1e-12), (valores, estable, directo)


def test_t2_dos_errores_enormes_no_desbordan() -> None:
    """T2. [1e200, 1e200]: el cuadrado no cabe en float, el RMSE si."""
    estable = _rmse_global_estable([1e200, 1e200])
    assert math.isfinite(estable), estable
    # sqrt((2 * 1e400) / 2) = 1e200
    assert math.isclose(estable, 1e200, rel_tol=1e-12), estable


def test_t3_caso_del_hallazgo_no_levanta_overflow() -> None:
    """T3. La magnitud exacta medida en el fixture que abortaba."""
    valores = [3.7243e155, 1.2258e240, 5.0, -2.0]
    estable = _rmse_global_estable(valores)
    assert math.isfinite(estable), estable
    # Domina el mayor: 1.2258e240 / sqrt(4) = 6.129e239
    assert math.isclose(estable, 1.2258e240 / 2.0, rel_tol=1e-9), estable


def test_t4_todos_ceros_dan_cero() -> None:
    """T4. Sin error no hay RMSE que penalizar."""
    assert _rmse_global_estable([0.0, 0.0, 0.0]) == 0.0
    assert _rmse_global_estable([0.0]) == 0.0


def test_t5_un_error_infinito_produce_rmse_no_finito() -> None:
    """T5. `inf` debe propagarse como no finito, no como excepcion."""
    resultado = _rmse_global_estable([1.0, float("inf"), 2.0])
    assert not math.isfinite(resultado), resultado


def test_t6_un_error_nan_produce_rmse_no_finito() -> None:
    """T6. `nan` debe propagarse como no finito, no como excepcion."""
    resultado = _rmse_global_estable([1.0, float("nan"), 2.0])
    assert not math.isfinite(resultado), resultado
    # Mezcla inf+nan: basta con que no sea finito; el candidato no gana igual.
    assert not math.isfinite(_rmse_global_estable([float("inf"), float("nan")]))


def test_t6b_una_suma_que_no_cabe_en_float_da_infinito_sin_excepcion() -> None:
    """El caso D del contrato: si el resultado real no cabe, es `inf`, no error."""
    resultado = _rmse_global_estable([1e308] * 10)
    assert not math.isfinite(resultado), resultado


# ==============================
# T7-T9: el selector completo
# ==============================


def test_t7_un_candidato_divergente_no_aborta_y_pierde() -> None:
    """T7. El caso que abortaba `ejecutar_proyeccion` entera.

    `divergente` tiene errores finitos pero enormes; `sano` tiene errores
    pequenos. Antes del microfix esta llamada levantaba `OverflowError`. Ahora
    debe devolver el candidato de menor RMSE, que es el sano.
    """
    pares = [(t, h) for t in range(1, 6) for h in (1, 2)]
    banco = _banco({
        "divergente": {p: 1.2258e240 for p in pares},
        "sano": {p: 1.5 for p in pares},
    })
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1, 2)) == "sano"


def test_t7b_un_rmse_calculado_no_finito_no_gana() -> None:
    """La guarda de no finitud sigue haciendo su trabajo, y ahora es alcanzable.

    Los errores de entrada ya se filtran por finitud en `_errores_oos_por_par`,
    de modo que la guarda de la linea 2240 protege contra un RMSE **calculado**
    no finito. Se provoca con errores finitos cuya norma si desborda: antes eso
    era una excepcion; ahora es `inf`, y el candidato pierde.
    """
    pares = [(t, h) for t in range(1, 6) for h in (1, 2)]
    banco = _banco({
        "desbordante": {p: 1e308 for p in pares},
        "sano": {p: 3.0 for p in pares},
    })
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1, 2)) == "sano"


def test_t8_la_muestra_comun_no_cambia() -> None:
    """T8. La interseccion de pares sigue gobernando la comparacion.

    `parcial` solo tiene evidencia en h=1. La muestra comun se reduce a esos
    pares, y sobre ELLOS `parcial` es mejor, de modo que gana: la correccion no
    toco el conjunto comun ni introdujo ninguna preferencia por cobertura.
    """
    pares_ambos = [(t, 1) for t in range(1, 6)]
    pares_solo_completo = [(t, 2) for t in range(1, 6)]
    banco = _banco({
        "completo": {**{p: 4.0 for p in pares_ambos}, **{p: 0.1 for p in pares_solo_completo}},
        "parcial": {p: 1.0 for p in pares_ambos},
    })
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1, 2)) == "parcial"


def test_t9_el_desempate_sigue_siendo_el_orden_de_aparicion() -> None:
    """T9. Ante empate exacto gana el primer candidato del banco, como antes."""
    pares = [(t, 1) for t in range(1, 6)]
    banco = _banco({"primero": {p: 2.0 for p in pares}, "segundo": {p: 2.0 for p in pares}})
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1,)) == "primero"
    # Y al invertir el orden de insercion gana el otro: es el orden, no el nombre.
    invertido = _banco({"segundo": {p: 2.0 for p in pares}, "primero": {p: 2.0 for p in pares}})
    assert seleccionar_modelo_por_rmse_oos_global(invertido, (1,)) == "segundo"


def _ejecutar() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except Exception:
            fallos += 1
            print(f"  FALLA {prueba.__name__}")
            traceback.print_exc()
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} aprobadas")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
