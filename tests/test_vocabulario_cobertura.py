"""Vocabulario y separacion de campos de cobertura (remediacion 04-08-2026).

Fija tres cosas que la verificacion de salidas del 03-08-2026 encontro mal:

* el metodo de evaluacion se escribia FIJO en los informes ("particion
  temporal"), de modo que cambiarlo habria convertido el texto en falso;
* la etiqueta visible se escribia a mano en cada rama y podia quedarse atras
  respecto de la clasificacion, hasta contradecirla;
* el minimo de errores viajaba a las salidas y se imprimia aunque el criterio
  ya no lo usara.

Tras integrar D-12b-C (04-08-2026) el metodo vigente es el origen movil; las
tres pruebas del metodo lo comprueban en los dos sentidos. Ninguna de estas
pruebas depende de D-1b-B, que sigue sin integrarse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.interfaz import presentacion_resultados as ui  # noqa: E402
from app_icociv.proyeccion import servicio_proyeccion as sp  # noqa: E402
from app_icociv.reportes.generador_reportes import (  # noqa: E402
    describir_metodo_cobertura,
)

PROHIBIDAS = ("cobertura garantizada", "cobertura asegurada", "cobertura validada")


def _cobertura(n: int = 26, paso: int = 1, semilla: int = 11) -> dict:
    errores = {paso: np.random.default_rng(semilla).normal(0.0, 0.3, n)}
    return sp._cobertura_empirica_intervalos(errores, paso_exacto=paso)


# ------------------------------------------------- metodo visible desde datos
def test_el_metodo_de_evaluacion_se_declara_en_el_resultado():
    """Desde D-12b-C (04-08-2026) el metodo vigente es el origen movil."""
    assert _cobertura()["metodo_evaluacion"] == "origen_movil"


def test_sin_evaluacion_el_metodo_no_se_supone():
    vacia = sp._cobertura_empirica_intervalos({1: np.array([0.1, 0.2])}, paso_exacto=1)
    assert vacia["metodo_evaluacion"] == "no_evaluable"
    assert describir_metodo_cobertura({"cobertura_empirica": vacia}) == "Cobertura no evaluable."


def test_la_frase_del_metodo_sigue_al_resultado_y_no_es_fija():
    """La frase la decide el resultado, no el texto del informe.

    Se comprueba en los dos sentidos: el metodo vigente produce su frase, y un
    resultado que declarase el metodo anterior produciria la suya. Si la frase
    estuviera escrita fija, ambas coincidirian.
    """
    vigente = describir_metodo_cobertura({"cobertura_empirica": _cobertura()})
    anterior = describir_metodo_cobertura(
        {"cobertura_empirica": {"metodo_evaluacion": "particion_temporal", "verificable": True}}
    )
    assert "origen móvil" in vigente
    assert "partición temporal" in anterior
    assert vigente != anterior


def test_la_interfaz_nombra_el_metodo_desde_el_resultado():
    assert "origen móvil" in ui._texto_metodo_evaluacion(_cobertura())
    assert "partición temporal" in ui._texto_metodo_evaluacion(
        {"metodo_evaluacion": "particion_temporal"}
    )


# ------------------------------------------------------- etiqueta y coherencia
def test_la_etiqueta_se_deriva_de_la_clasificacion():
    for clasificacion, etiqueta in sp.ETIQUETA_VISIBLE_POR_CLASIFICACION.items():
        salida = sp._salida_clasificacion(
            clasificacion,
            cobertura_minima=None,
            degrada_a_escenario=False,
            umbral_aplicado="",
            advertencia="",
            comunes={},
        )
        assert salida["etiqueta"] == etiqueta
        assert salida["etiqueta_visible"] == etiqueta


def test_ninguna_etiqueta_afirma_cobertura_cumplida():
    for etiqueta in sp.ETIQUETA_VISIBLE_POR_CLASIFICACION.values():
        bajo = etiqueta.lower()
        for prohibida in ("garantiz", "asegurad", "validad", "verificada"):
            assert prohibida not in bajo, etiqueta


def test_nominal_describe_el_nivel_no_un_resultado():
    """'nominal' debe calificar la banda calculada, no la cobertura medida."""
    etiqueta = sp.ETIQUETA_VISIBLE_POR_CLASIFICACION["nominal"]
    assert "calculada para un nivel nominal" in etiqueta
    assert not re.search(r"intervalo de predicci[oó]n nominal del 95 %$", etiqueta.lower())


def test_tipo_de_banda_y_estado_de_horizonte_son_campos_distintos():
    salida = sp._salida_clasificacion(
        # CIERRE 08-08-2026: `cobertura_insuficiente` se renombro a
        # `cobertura_por_debajo_del_nominal` al dejar de degradar. El campo que
        # esta prueba vigila -que el tipo de banda y el estado del horizonte
        # sean cosas distintas- sigue siendo el mismo.
        "cobertura_por_debajo_del_nominal",
        cobertura_minima=0.5,
        degrada_a_escenario=True,
        umbral_aplicado="",
        advertencia="",
        comunes={},
    )
    assert salida["tipo_banda"] == "rango_de_referencia"
    # El estado del horizonte NO viaja en la clasificacion del intervalo.
    assert "estado_horizonte" not in salida
    assert salida["consecuencia_operativa"]


def test_nivel_nominal_y_cobertura_observada_van_separados():
    salida = sp._salida_clasificacion(
        "admisible_con_advertencia",
        cobertura_minima=0.84,
        degrada_a_escenario=False,
        umbral_aplicado="",
        advertencia="",
        comunes={},
    )
    assert salida["nivel_nominal"] == 0.95
    assert salida["cobertura_observada"] == 0.84
    assert salida["limitacion"]


def test_la_cobertura_se_publica_como_x_sobre_y():
    texto = ui._texto_cobertura_empirica(_cobertura())
    assert re.search(r"h=\d+: \d+/\d+ \(\d+%\)", texto), texto


# -------------------------------------------------------- frases prohibidas
def test_ninguna_salida_afirma_cobertura_garantizada():
    textos = [
        *sp.ETIQUETA_VISIBLE_POR_CLASIFICACION.values(),
        *sp.CONSECUENCIA_POR_CLASIFICACION.values(),
        sp.LIMITACION_COBERTURA,
        ui._texto_cobertura_empirica(_cobertura()),
        ui._texto_metodo_evaluacion(_cobertura()),
    ]
    for texto in textos:
        for prohibida in PROHIBIDAS:
            assert prohibida not in texto.lower(), texto


def test_el_minimo_de_errores_se_lee_en_ejecucion():
    """El 16 no puede quedar ligado como valor por omision del parametro."""
    errores = {12: np.random.default_rng(5).normal(0.0, 0.4, 15)}
    original = sp.MIN_ERRORES_COBERTURA_EMPIRICA
    try:
        assert sp._cobertura_empirica_intervalos(errores, paso_exacto=12)[
            "min_errores_exigidos"
        ] == original
        sp.MIN_ERRORES_COBERTURA_EMPIRICA = 10
        assert sp.min_errores_cobertura_vigente() == 10
        assert sp._cobertura_empirica_intervalos(errores, paso_exacto=12)[
            "min_errores_exigidos"
        ] == 10, "la funcion sigue usando el literal ligado al definirla"
    finally:
        sp.MIN_ERRORES_COBERTURA_EMPIRICA = original
    assert sp.min_errores_cobertura_vigente() == 16, "el valor productivo sigue siendo 16"


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
