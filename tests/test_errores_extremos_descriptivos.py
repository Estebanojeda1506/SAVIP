"""Decisión D-8: los errores inusuales de backtesting son descriptivos.

Comprueba que la detección individual usa el puntaje z modificado con el umbral
bibliográfico 3,5 y que la proporción resultante no bloquea, no degrada, no
recorta horizonte y no altera modelo, pronóstico ni intervalo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica import criterios
from app_icociv.estadistica.metricas import detectar_errores_extremos


def _z_modificado(errores: list[float]) -> np.ndarray:
    abs_err = np.abs(np.asarray(errores, dtype=float))
    mediana = float(np.median(abs_err))
    mad = float(np.median(np.abs(abs_err - mediana)))
    return criterios.FACTOR_Z_MODIFICADO * (abs_err - mediana) / mad


def test_serie_sin_errores_inusuales():
    errores = [1.0, -1.1, 0.9, -1.05, 0.95, -1.02, 1.03, -0.98]
    resultado = detectar_errores_extremos(errores)
    assert resultado["calculable"] is True
    assert resultado["cantidad"] == 0
    assert resultado["proporcion"] == 0.0
    assert len(resultado["observaciones"]) == len(errores)


def test_un_error_inusual_se_marca():
    errores = [1.0, 1.02, 0.98, 1.01, 0.99, 1.0, 1.03, 0.97, 40.0]
    resultado = detectar_errores_extremos(errores)
    assert resultado["calculable"] is True
    assert resultado["cantidad"] == 1
    marcados = [o for o in resultado["observaciones"] if o["extremo"]]
    assert len(marcados) == 1
    assert marcados[0]["error_absoluto"] == 40.0
    assert abs(marcados[0]["z_modificado"]) > criterios.UMBRAL_Z_MODIFICADO_ATIPICO


def test_varios_errores_inusuales_se_marcan():
    errores = [1.0, 1.02, 0.98, 1.01, 0.99, 1.0, 1.03, 0.97, 40.0, -55.0, 61.0]
    resultado = detectar_errores_extremos(errores)
    assert resultado["cantidad"] == 3
    assert resultado["proporcion"] == 3 / len(errores) * 100.0


def test_umbral_es_el_bibliografico_y_no_uno_interno():
    assert criterios.UMBRAL_Z_MODIFICADO_ATIPICO == 3.5
    assert criterios.FACTOR_Z_MODIFICADO == 0.6745
    errores = [1.0, 1.02, 0.98, 1.01, 0.99, 1.0, 1.03, 0.97, 12.0]
    resultado = detectar_errores_extremos(errores)
    esperado = int((np.abs(_z_modificado(errores)) > 3.5).sum())
    assert resultado["cantidad"] == esperado


def test_mad_igual_a_cero_no_es_calculable():
    errores = [2.0, -2.0, 2.0, -2.0, 2.0, -2.0]
    resultado = detectar_errores_extremos(errores)
    assert resultado["calculable"] is False
    assert resultado["cantidad"] == 0
    assert np.isnan(resultado["proporcion"])
    assert "mediana" in resultado["motivo"].lower()


def test_sin_errores_finitos_no_es_calculable():
    resultado = detectar_errores_extremos([float("nan"), float("inf"), float("-inf")])
    assert resultado["calculable"] is False
    assert resultado["n"] == 0
    assert np.isnan(resultado["proporcion"])


def test_lista_vacia_no_es_calculable():
    resultado = detectar_errores_extremos([])
    assert resultado["calculable"] is False
    assert resultado["n"] == 0


def test_los_periodos_se_conservan_por_observacion():
    errores = [1.0, 1.02, 0.98, 1.01, 0.99, 1.0, 1.03, 0.97, 40.0]
    periodos = [f"2025_{i + 1}" for i in range(len(errores))]
    resultado = detectar_errores_extremos(errores, periodos)
    marcados = [o for o in resultado["observaciones"] if o["extremo"]]
    assert marcados[0]["periodo"] == "2025_9"
    assert all(o["periodo"] for o in resultado["observaciones"])


def test_no_quedan_constantes_de_proporcion():
    for nombre in (
        "UMBRAL_ERRORES_EXTREMOS_ADVERTENCIA",
        "UMBRAL_ERRORES_EXTREMOS_BLOQUEO",
        "UMBRAL_ERRORES_EXTREMOS_BLOQUEO_HORIZONTE",
        "MULTIPLICADOR_MAD_ERRORES_EXTREMOS",
    ):
        assert not hasattr(criterios, nombre), f"{nombre} sigue definida"


def test_ningun_modulo_vivo_decide_por_proporcion_de_extremos():
    """Ni el servicio ni el análisis pueden bloquear o degradar por proporción."""
    objetivo = (
        RAIZ / "app_icociv" / "proyeccion" / "servicio_proyeccion.py",
        RAIZ / "app_icociv" / "estadistica" / "analisis_series.py",
        RAIZ / "app_icociv" / "validacion" / "backtesting.py",
    )
    for ruta in objetivo:
        texto = ruta.read_text(encoding="utf-8")
        for prohibido in (
            "UMBRAL_ERRORES_EXTREMOS_ADVERTENCIA",
            "UMBRAL_ERRORES_EXTREMOS_BLOQUEO",
            "UMBRAL_ERRORES_EXTREMOS_BLOQUEO_HORIZONTE",
            "MULTIPLICADOR_MAD_ERRORES_EXTREMOS",
        ):
            assert prohibido not in texto, f"{ruta.name} conserva {prohibido}"


def test_el_criterio_del_catalogo_es_bibliografico():
    entradas = [c for c in criterios.matriz_criterios() if c.id == "C-ERR-001"]
    assert len(entradas) == 1
    assert entradas[0].tipo == criterios.TIPO_BIBLIOGRAFICO
    assert "Iglewicz" in entradas[0].fuente
    assert not [c for c in criterios.matriz_criterios() if c.id == "C-ERR-002"]


def test_la_proporcion_no_aparece_en_ninguna_razon_de_bloqueo():
    servicio = (RAIZ / "app_icociv" / "proyeccion" / "servicio_proyeccion.py").read_text(encoding="utf-8")
    assert "Errores extremos recurrentes en backtesting" not in servicio
    analisis = (RAIZ / "app_icociv" / "estadistica" / "analisis_series.py").read_text(encoding="utf-8")
    assert "El backtesting muestra errores extremos recurrentes." not in analisis
    assert "El backtesting contiene errores extremos; limitar horizonte." not in analisis


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
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas de errores inusuales (D-8)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
