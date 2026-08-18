"""P0-D: el ganador no puede depender del redondeo del RMSE (D1-D12).

La revision independiente reabrio P0-D porque

    hypot(e_1,...,e_n) / sqrt(n)   y   sqrt(sum(e_i**2) / n)

son algebraicamente iguales pero **no redondean igual**. Medido: con dos
candidatos que difieren en una ULP en un solo error, la forma directa distingue
cual es menor y `hypot` devuelve **el mismo flotante para los dos**, creando un
empate que matematicamente no existe. Con el desempate por orden de aparicion,
ese empate artificial hace ganar al primer candidato del banco en lugar de al de
menor error real.

La solucion NO es una tolerancia. Es una derivacion: como la raiz cuadrada es
estrictamente creciente y el factor 1/n es comun a todos los candidatos sobre la
misma muestra comun,

    argmin RMSE = argmin MSE = argmin SSE

de modo que la decision puede tomarse sobre la suma de cuadrados calculada de
forma EXACTA. Cada flotante IEEE-754 es un racional con denominador potencia de
dos, y `float.as_integer_ratio()` lo entrega sin perdida.

Ejecucion directa, sin pytest:

    python tests/test_p0d_rmse_orden_exacto.py
"""
from __future__ import annotations

import inspect
import math
import re
import struct
import sys
import traceback
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    _errores_oos_por_par,
    _rmse_global_estable,
    _sse_exacto,
    seleccionar_modelo_por_rmse_oos_global,
)

#: Contraejemplo medido el 14-08-2026: B difiere de A en UNA ULP del tercer error.
#: `sqrt(sum/n)` distingue a B como menor; `hypot/sqrt(n)` devuelve el mismo
#: flotante para ambos. El SSE exacto da la razon a B, sin ambiguedad.
ULP_A = [1.236534220264296, 1.970026263557579, 0.7527746719239033]
ULP_B = [1.236534220264296, 1.970026263557579, 0.7527746719239032]


def _banco(errores_por_modelo: dict[str, dict[tuple[int, int], float]]) -> dict:
    banco: dict[str, dict] = {}
    for modelo, errores in errores_por_modelo.items():
        por_h: dict[int, list[tuple[int, float]]] = {}
        for (objetivo, horizonte), error in errores.items():
            por_h.setdefault(horizonte, []).append((objetivo, error))
        for horizonte, filas in por_h.items():
            banco[f"{modelo}_h{horizonte}"] = {
                "ejecutado": True,
                "predicciones": pd.DataFrame(
                    {"t": [f[0] for f in filas], "Error": [f[1] for f in filas]}
                ),
            }
    return banco


def _con_errores(**por_modelo: list[float]) -> dict:
    return _banco({
        modelo: {(i, 1): valor for i, valor in enumerate(valores, start=1)}
        for modelo, valores in por_modelo.items()
    })


def _rmse_directo(valores: list[float]) -> float:
    return math.sqrt(sum(float(v) ** 2 for v in valores) / len(valores))


# ==============================
# D1-D4: el contraejemplo y la invariancia
# ==============================


def test_d1_el_contraejemplo_de_una_ulp_se_decide_de_forma_unica() -> None:
    """D1. Las dos formas flotantes discrepan; el SSE exacto no."""
    directo_a, directo_b = _rmse_directo(ULP_A), _rmse_directo(ULP_B)
    hypot_a, hypot_b = _rmse_global_estable(ULP_A), _rmse_global_estable(ULP_B)
    # La forma directa distingue; hypot empata. Ese es el defecto.
    assert directo_a != directo_b, (directo_a, directo_b)
    assert hypot_a == hypot_b, (hypot_a, hypot_b)

    sse_a, sse_b = _sse_exacto(ULP_A), _sse_exacto(ULP_B)
    assert sse_a != sse_b, "el empate era un artefacto del redondeo"
    assert sse_b < sse_a, (sse_a, sse_b)
    # Y el selector elige B, el de menor suma de cuadrados real.
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(a=ULP_A, b=ULP_B), (1,)) == "b"


def test_d2_invertir_el_orden_de_candidatos_no_cambia_el_ganador() -> None:
    """D2. Con SSE exactos distintos, el orden del banco es irrelevante."""
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(a=ULP_A, b=ULP_B), (1,)) == "b"
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(b=ULP_B, a=ULP_A), (1,)) == "b"


def test_d3_un_empate_exacto_conserva_el_desempate_historico() -> None:
    """D3. Ante igualdad EXACTA gana el primer candidato del banco."""
    valores = [1.5, -2.25, 0.125]
    assert _sse_exacto(valores) == _sse_exacto(list(valores))
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(primero=valores, segundo=list(valores)), (1,)) == "primero"
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(segundo=list(valores), primero=valores), (1,)) == "segundo"


def test_d4_permutar_la_muestra_comun_no_cambia_nada() -> None:
    """D4. El SSE exacto es invariante al orden de iteracion de S_common."""
    generador = np.random.default_rng(11)
    valores = [float(x) for x in generador.uniform(-4, 4, 40)]
    referencia = _sse_exacto(valores)
    for _ in range(50):
        permutado = list(valores)
        generador.shuffle(permutado)
        assert _sse_exacto(permutado) == referencia


# ==============================
# D5-D6: correccion y magnitudes
# ==============================


def test_d5_en_el_rango_ordinario_gana_el_minimo_matematico() -> None:
    """D5."""
    peor = [3.0, 3.0, 3.0]
    mejor = [1.0, 1.0, 1.0]
    assert _sse_exacto(mejor) < _sse_exacto(peor)
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(peor=peor, mejor=mejor), (1,)) == "mejor"
    # Y coincide con la comparacion flotante cuando esta no es ambigua.
    assert _rmse_directo(mejor) < _rmse_directo(peor)


def test_d6_errores_enormes_finitos_no_desbordan() -> None:
    """D6. El caso que motivo el microfix: cuadrados fuera del rango del float."""
    divergente = [1.2258e240, 3.7243e155, 5.0]
    sano = [1.5, 2.0, 0.5]
    # El acumulador exacto no desborda: son enteros de precision arbitraria.
    assert _sse_exacto(divergente) > _sse_exacto(sano)
    assert seleccionar_modelo_por_rmse_oos_global(
        _con_errores(divergente=divergente, sano=sano), (1,)) == "sano"


# ==============================
# D7-D9: no finitud
# ==============================


def test_d7_un_candidato_con_inf_no_gana() -> None:
    """D7."""
    banco = _con_errores(patologico=[float("inf")] * 3, sano=[9.0, 9.0, 9.0])
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1,)) in (None, "sano")


def test_d8_un_candidato_con_nan_no_gana() -> None:
    """D8."""
    banco = _con_errores(patologico=[float("nan")] * 3, sano=[9.0, 9.0, 9.0])
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1,)) in (None, "sano")


def test_d9_sin_candidatos_utilizables_no_se_inventa_ninguno() -> None:
    """D9. Sin muestra comun no hay seleccion: se devuelve None, como antes."""
    banco = _banco({
        "uno": {(1, 1): 1.0, (2, 1): 1.0},
        "otro": {(3, 1): 1.0, (4, 1): 1.0},
    })
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1,)) is None
    assert seleccionar_modelo_por_rmse_oos_global({}, (1,)) is None


# ==============================
# D10-D12: contrato de la muestra y ausencia de tolerancias
# ==============================


def test_d10_la_muestra_comun_sigue_siendo_la_interseccion() -> None:
    """D10. Todos los candidatos se puntuan sobre exactamente los mismos pares."""
    pares_comunes = [(t, 1) for t in range(1, 6)]
    solo_de_uno = [(t, 2) for t in range(1, 6)]
    banco = _banco({
        "completo": {**{p: 4.0 for p in pares_comunes}, **{p: 0.01 for p in solo_de_uno}},
        "parcial": {p: 1.0 for p in pares_comunes},
    })
    # Sobre la interseccion gana `parcial`: sus errores son menores ahi.
    assert seleccionar_modelo_por_rmse_oos_global(banco, (1, 2)) == "parcial"
    pares = _errores_oos_por_par(banco, (1, 2))
    comunes = set.intersection(*(set(d) for d in pares.values()))
    assert comunes == set(pares_comunes)


def _lineas_ejecutables(funcion) -> str:
    """Codigo de la funcion sin comentarios ni docstring.

    Buscar cadenas sobre la fuente completa da falsos positivos: los docstrings de
    estas dos funciones **describen** las reglas retiradas -la ponderacion 1/h y la
    prohibicion de `isclose`- precisamente para dejar constancia de que no estan.
    Lo que hay que inspeccionar es lo que se ejecuta.
    """
    fuente = inspect.getsource(funcion)
    sin_docstring = re.sub(r'"""(?:.|\n)*?"""', "", fuente)
    return "\n".join(
        linea.split("#", 1)[0]
        for linea in sin_docstring.splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    )


def test_d11_los_pesos_siguen_siendo_uniformes() -> None:
    """D11. Ninguna ponderacion por horizonte ni por antiguedad."""
    ejecutable = _lineas_ejecutables(seleccionar_modelo_por_rmse_oos_global).lower()
    for sospechoso in ("1/h", "1 / h", "peso", "ponder"):
        assert sospechoso not in ejecutable, sospechoso
    # Dos errores iguales en horizontes distintos pesan lo mismo.
    assert _sse_exacto([2.0, 0.0]) == _sse_exacto([0.0, 2.0])


def test_d12_la_decision_no_usa_ninguna_tolerancia() -> None:
    """D12. Sin epsilon, sin isclose, sin redondeo en la ruta de decision."""
    for funcion in (seleccionar_modelo_por_rmse_oos_global, _sse_exacto):
        ejecutable = _lineas_ejecutables(funcion)
        for prohibido in ("isclose", "epsilon", "EPS", "round(", "tolerancia",
                          "atol", "rtol", "Decimal"):
            assert prohibido not in ejecutable, (funcion.__name__, prohibido)


def test_d13_el_acumulador_entero_coincide_con_fraction_puro() -> None:
    """El atajo de rendimiento debe dar EXACTAMENTE lo mismo que Fraction."""
    generador = np.random.default_rng(3)
    for _ in range(200):
        valores = [float(x) for x in generador.uniform(-1e6, 1e6, 7)]
        referencia = sum((Fraction(v) ** 2 for v in valores), Fraction(0))
        assert _sse_exacto(valores) == referencia
    # Y con magnitudes extremas.
    extremos = [1e-300, 1e300, -1e150, 0.0]
    assert _sse_exacto(extremos) == sum((Fraction(v) ** 2 for v in extremos), Fraction(0))


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
