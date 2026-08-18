"""Decisión D-7: diagnóstico residual formal, descriptivo e informativo.

Comprueba que la media residual y la heterocedasticidad se contrastan con
pruebas formales publicadas por completo, que Ljung-Box sigue siendo la prueba
formal de autocorrelación y Durbin-Watson un descriptor, y que ningún contraste
bloquea, degrada, selecciona modelo ni cambia pronóstico, intervalo u horizonte.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica import criterios
from app_icociv.estadistica.diagnostico_residuos import (
    contrastar_heterocedasticidad,
    contrastar_media_residual,
    evaluar_residuos,
)

AFIRMACIONES_PROHIBIDAS = (
    "los residuos son independientes",
    "los residuos son normales",
    "no existe heterocedasticidad",
    "los residuos son homocedasticos",
    "se confirma la normalidad",
)

CAMPOS_MEDIA = (
    "n",
    "media",
    "error_estandar",
    "estadistico",
    "grados_libertad",
    "p_value",
    "alfa",
    "hipotesis_nula",
    "hipotesis_alternativa",
    "calculable",
)

CAMPOS_HETERO = (
    "n",
    "estadistico",
    "grados_libertad",
    "p_value",
    "alfa",
    "regresores",
    "hipotesis_nula",
    "calculable",
    "limitacion",
    "consecuencia",
)


def _serie(n: int, media: float = 0.0, escala: float = 1.0, semilla: int = 11) -> np.ndarray:
    return np.random.default_rng(semilla).normal(media, escala, n)


def test_media_residual_publica_todos_los_campos():
    resultado = contrastar_media_residual(_serie(30))
    for campo in CAMPOS_MEDIA:
        assert campo in resultado, f"falta {campo}"
    assert resultado["calculable"] is True
    assert resultado["grados_libertad"] == 29


def test_media_residual_centrada_no_rechaza():
    r = _serie(60, media=0.0, semilla=3)
    r = r - r.mean()  # media muestral exactamente cero
    resultado = contrastar_media_residual(r)
    assert resultado["calculable"] is True
    assert resultado["p_value"] > criterios.ALPHA_PRUEBAS_RESIDUALES
    assert "no se rechazó" in resultado["mensaje"].lower()


def test_media_residual_desplazada_rechaza():
    r = _serie(60, media=0.0, semilla=5)
    r = r - r.mean() + 3.0
    resultado = contrastar_media_residual(r)
    assert resultado["p_value"] < criterios.ALPHA_PRUEBAS_RESIDUALES
    assert "se rechazó" in resultado["mensaje"].lower()


def test_media_residual_no_calculable_con_un_residuo():
    resultado = contrastar_media_residual(np.array([1.0]))
    assert resultado["calculable"] is False
    assert "no fue calculable" in resultado["mensaje"].lower()


def test_media_residual_no_calculable_sin_dispersion():
    resultado = contrastar_media_residual(np.full(10, 2.0))
    assert resultado["calculable"] is False
    assert "dispersión" in resultado["mensaje"].lower()


def test_heterocedasticidad_publica_todos_los_campos():
    resultado = contrastar_heterocedasticidad(_serie(40))
    for campo in CAMPOS_HETERO:
        assert campo in resultado, f"falta {campo}"
    assert resultado["calculable"] is True
    assert resultado["grados_libertad"] == 1
    assert "Breusch" in resultado["fuente"]


def test_heterocedasticidad_constante_no_rechaza():
    resultado = contrastar_heterocedasticidad(_serie(60, escala=1.0, semilla=9))
    assert resultado["calculable"] is True
    assert resultado["p_value"] > criterios.ALPHA_PRUEBAS_RESIDUALES


def test_heterocedasticidad_creciente_rechaza():
    n = 80
    base = np.random.default_rng(4).normal(0.0, 1.0, n)
    r = base * np.linspace(0.2, 8.0, n)
    resultado = contrastar_heterocedasticidad(r)
    assert resultado["calculable"] is True
    assert resultado["p_value"] < criterios.ALPHA_PRUEBAS_RESIDUALES


def test_heterocedasticidad_no_calculable_con_pocos_residuos():
    resultado = contrastar_heterocedasticidad(np.array([1.0, -1.0]))
    assert resultado["calculable"] is False
    assert "no fue calculable" in resultado["mensaje"].lower()


def test_heterocedasticidad_no_calculable_con_residuos_constantes():
    resultado = contrastar_heterocedasticidad(np.full(20, 5.0))
    assert resultado["calculable"] is False


def test_limitacion_por_muestra_pequena():
    resultado = contrastar_heterocedasticidad(_serie(6, semilla=2))
    if resultado["calculable"]:
        assert resultado["limitacion"], "debe declarar la limitación con n pequeño"


def test_evaluar_residuos_integra_los_contrastes():
    d = evaluar_residuos(_serie(40))
    assert "media_residual" in d
    assert "heterocedasticidad" in d
    assert "ljung_box" in d
    assert "durbin_watson" in d
    assert "jb_p" in d
    assert d["consecuencia_operativa"] == criterios.CONSECUENCIA_INFORMATIVA


def test_ljung_box_sigue_siendo_la_prueba_formal_de_autocorrelacion():
    d = evaluar_residuos(_serie(60))
    assert d["ljung_box"]["disponible"] is True
    assert d["ljung_box"]["p_value"] is not None
    assert d["durbin_watson_alcance"] in ("descriptivo_no_ols", "formal_ols_aproximado")
    assert "descriptiva" in d["durbin_watson_interpretacion"].lower()


def test_jarque_bera_publica_sus_campos():
    d = evaluar_residuos(_serie(40))
    for campo in ("jb", "jb_p", "jb_asimetria", "jb_curtosis", "jb_n", "jb_hipotesis_nula", "jb_mensaje"):
        assert campo in d, f"falta {campo}"


def test_ninguna_redaccion_afirma_la_hipotesis_nula():
    for n in (12, 40, 90):
        d = evaluar_residuos(_serie(n, semilla=n))
        textos = [
            str(d["media_residual"].get("mensaje", "")),
            str(d["heterocedasticidad"].get("mensaje", "")),
            str(d.get("jb_mensaje", "")),
            str(d.get("durbin_watson_interpretacion", "")),
        ] + [str(a) for a in d["alertas"]]
        for texto in textos:
            for prohibida in AFIRMACIONES_PROHIBIDAS:
                assert prohibida not in texto.lower(), f"afirmación prohibida: {texto}"


def test_solo_tres_redacciones_de_resultado():
    permitidas = ("se rechazó la hipótesis nula", "no se rechazó la hipótesis nula", "no fue calculable")
    casos = [_serie(40), np.full(10, 2.0), np.array([1.0])]
    for r in casos:
        for contraste in (contrastar_media_residual(r), contrastar_heterocedasticidad(r)):
            mensaje = contraste["mensaje"].lower()
            assert any(p in mensaje for p in permitidas), f"redacción inesperada: {mensaje}"


def test_no_quedan_constantes_sin_fuente():
    for nombre in ("UMBRAL_CORR_HETEROCEDASTICIDAD", "UMBRAL_MEDIA_RESIDUAL_DESV"):
        assert not hasattr(criterios, nombre), f"{nombre} sigue definida"


def test_el_catalogo_declara_los_contrastes_como_estandar():
    """Los dos contrastes formales deben citar fuente y no bloquear.

    El 04-08-2026 los siete estados admitidos del campo ``tipo`` sustituyeron a
    las categorias anteriores: `estadistico_estandar` paso a `bibliografico`,
    que es lo que ambos contrastes son -Breusch y Pagan (1979) y la prueba t de
    una muestra tienen fuente externa-.
    """
    entradas = {c.id: c for c in criterios.matriz_criterios()}
    for cid, clave in (("C-HET-001", "Breusch"), ("C-RES-002", "t de una muestra")):
        assert cid in entradas, f"falta {cid}"
        assert entradas[cid].tipo == criterios.TIPO_BIBLIOGRAFICO
        assert clave in entradas[cid].fuente
        assert "informativa" in entradas[cid].accion.lower()


def test_el_diagnostico_no_bloquea_ni_degrada():
    """Ningún módulo vivo debe decidir a partir de los contrastes residuales."""
    servicio = (RAIZ / "app_icociv" / "proyeccion" / "servicio_proyeccion.py").read_text(encoding="utf-8")
    for prohibido in ("heterocedasticidad", "media_residual"):
        for decision in ("bloqueo_duro = True", "permitido = False", "forzar_solo_escenario = True"):
            bloque = servicio.split(prohibido)
            for parte in bloque[1:]:
                assert decision not in parte[:400], (
                    f"'{prohibido}' aparece cerca de '{decision}' en servicio_proyeccion"
                )


def _ejecutar() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {prueba.__name__}: {exc}")
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas de diagnóstico residual formal (D-7)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
