"""Defectos matematicos de la banda de prediccion (remediacion 04-08-2026).

Dos defectos verificados antes de esta remediacion:

* un intervalo con los limites invertidos se aprobaba como proyeccion tecnica,
  porque su ancho relativo salia negativo y ninguna comparacion `ancho > umbral`
  lo detectaba;
* la ausencia de errores fuera de muestra del paso exacto se comunicaba como
  "falla numerica" con ancho infinito, que confunde "no calculable" con
  "infinitamente ancho".

Estas pruebas fijan el comportamiento correcto. No dependen de D-4b ni de D-11:
ninguna toca umbrales de amplitud ni minimos de longitud.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    BANDA_LIMITES_INVERTIDOS,
    BANDA_LIMITES_NO_FINITOS,
    BANDA_NO_CALCULABLE,
    BANDA_SEMIANCHO_CERO,
    BANDA_VALIDA,
    _evaluar_intervalos_prediccion,
    _intervalos_prediccion,
    estado_banda,
)


# ---------------------------------------------------------------- 8.1 limites
def test_intervalo_normal_es_valido():
    assert estado_banda(90.0, 110.0, 100.0) == BANDA_VALIDA


def test_limites_iguales_no_son_invalidos_pero_se_declaran():
    assert estado_banda(100.0, 100.0, 100.0) == BANDA_SEMIANCHO_CERO


def test_limites_invertidos_se_detectan():
    assert estado_banda(110.0, 90.0, 100.0) == BANDA_LIMITES_INVERTIDOS


def test_los_limites_invertidos_no_se_intercambian_en_silencio():
    """Invertir el orden debe declararse, nunca corregirse por detras."""
    assert estado_banda(110.0, 90.0, 100.0) != BANDA_VALIDA
    # Y el caso simetrico bien ordenado si es valido: la deteccion no es
    # simplemente "los limites son 90 y 110".
    assert estado_banda(90.0, 110.0, 100.0) == BANDA_VALIDA


def test_nan_e_infinito_se_detectan():
    for inferior, superior in (
        (float("nan"), 110.0),
        (90.0, float("nan")),
        (float("-inf"), 110.0),
        (90.0, float("inf")),
    ):
        assert estado_banda(inferior, superior, 100.0) == BANDA_LIMITES_NO_FINITOS


def test_pronostico_no_finito_se_nombra_aparte_de_la_banda():
    """Reescrito por P0-C ruta C2 (paso 0).

    Antes, un pronostico no finito devolvia el mismo codigo que unos limites no
    finitos. Retirado el intervalo del producto, esa fusion haria que un fallo de
    la banda cancelara el punto, de modo que la imposibilidad del PUNTO se nombra
    con su propio codigo y es la unica que bloquea.
    """
    from app_icociv.proyeccion.servicio_proyeccion import PUNTO_NO_FINITO
    assert estado_banda(90.0, 110.0, float("nan")) == PUNTO_NO_FINITO
    assert estado_banda(90.0, 110.0, float("inf")) == PUNTO_NO_FINITO
    # Los limites no finitos conservan su propio codigo.
    assert estado_banda(float("nan"), 110.0, 100.0) == BANDA_LIMITES_NO_FINITOS


def test_piso_cero_no_invalida_una_banda_bien_ordenada():
    assert estado_banda(0.0, 12.0, 6.0) == BANDA_VALIDA


def test_piso_cero_con_pronostico_negativo_produce_banda_invertida():
    """Caso real: si el modelo extrapola por debajo de cero, hi < 0 = lo."""
    assert estado_banda(0.0, -5.0, -8.0) == BANDA_LIMITES_INVERTIDOS


# ------------------------------------------------------------ 8.2 sin errores
def test_sin_errores_la_banda_no_es_calculable():
    assert estado_banda(90.0, 110.0, 100.0, n_errores=0) == BANDA_NO_CALCULABLE


def test_un_solo_error_tampoco_permite_construirla():
    with np.errstate(all="ignore"):
        try:
            _intervalos_prediccion(np.array([100.0]), {1: np.array([0.5])})
        except ValueError as exc:
            assert "errores fuera de muestra" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("un solo error deberia impedir construir la banda")


def test_no_se_mezclan_errores_de_otro_horizonte():
    """Con errores solo en h=1, el paso 2 no puede tomarlos prestados."""
    try:
        _intervalos_prediccion(np.array([100.0, 101.0]), {1: np.array([0.3, -0.2, 0.1, 0.4])})
    except ValueError as exc:
        assert "paso 2" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("el paso 2 no tiene errores propios y no debe fabricarse")


def test_vacio_no_se_interpreta_como_cero():
    assert estado_banda(100.0, 100.0, 100.0, n_errores=0) == BANDA_NO_CALCULABLE
    assert estado_banda(100.0, 100.0, 100.0, n_errores=5) == BANDA_SEMIANCHO_CERO


# ------------------------------------------- la evaluacion no aprueba lo roto
def _tabla(inferior: float, superior: float, pronostico: float) -> pd.DataFrame:
    """Tabla minima con las mismas columnas que `_construir_tabla_proyecciones`."""
    return pd.DataFrame(
        {
            "indice_proyectado": [pronostico],
            "limite_inferior_95": [inferior],
            "limite_superior_95": [superior],
            "limite_inferior": [inferior],
            "limite_superior": [superior],
        }
    )


def test_la_evaluacion_marca_critico_el_intervalo_invertido():
    salida = _evaluar_intervalos_prediccion(_tabla(110.0, 90.0, 100.0), horizonte=6)
    assert salida["critico"] is True
    assert salida["estado_banda"] == BANDA_LIMITES_INVERTIDOS
    assert salida["banda_valida"] is False
    assert not math.isfinite(salida["ancho_relativo_maximo"])
    assert "menor que el inferior" in " ".join(salida["razones"])


def test_la_evaluacion_no_confunde_no_calculable_con_ancho_infinito():
    salida = _evaluar_intervalos_prediccion(
        _tabla(float("nan"), float("nan"), 100.0), horizonte=6
    )
    assert salida["critico"] is True
    assert not math.isfinite(salida["ancho_relativo_maximo"]), (
        "un ancho infinito haria pasar la banda por 'muy ancha' en vez de 'inexistente'"
    )
    assert math.isnan(salida["ancho_relativo_maximo"])


def test_la_evaluacion_acepta_una_banda_bien_construida():
    salida = _evaluar_intervalos_prediccion(_tabla(95.0, 105.0, 100.0), horizonte=6)
    assert salida["critico"] is False
    assert math.isfinite(salida["ancho_relativo_maximo"])


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
