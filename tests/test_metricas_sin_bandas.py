"""Decisión D-9: métricas sin bandas internas de interpretación.

Comprueba que MAPE, sMAPE, MASE y el sesgo se publican con sus valores, que la
única lectura comparativa conservada es MASE frente a 1, y que ninguna banda
interna vuelve a decidir bloqueo, degradación ni recorte de horizonte.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica import criterios
from app_icociv.estadistica.metricas import (
    calcular_mape,
    calcular_mase,
    calcular_sesgo_medio,
    calcular_smape,
)
from app_icociv.validacion.backtesting import interpretar_backtesting

ETIQUETAS_PROHIBIDAS = (
    "excelente",
    "bueno",
    "aceptable",
    "muy malo",
    "malo",
    "calidad predictiva alta",
    "calidad predictiva media",
    "calidad predictiva baja",
    "muy favorable",
)


def _metricas(mase: float, mape: float = 4.0) -> dict[str, float]:
    return {"mape": mape, "smape": mape, "mase": mase, "rmse": 1.0, "mae": 0.8}


def test_no_quedan_constantes_de_banda():
    for nombre in (
        "UMBRAL_MASE_MEDIA",
        "UMBRAL_MAPE_ALTA_CONFIANZA",
        "UMBRAL_MAPE_MEDIA_CONFIANZA",
        "UMBRAL_MAPE_ALTO",
        "UMBRAL_MAPE_EXTREMO",
        "UMBRAL_SMAPE_ALTO",
        "UMBRAL_SMAPE_EXTREMO",
        "UMBRAL_SMAPE_EVIDENCIA_OK",
        "UMBRAL_SESGO_MAE",
    ):
        assert not hasattr(criterios, nombre), f"{nombre} sigue definida"


def test_se_conserva_la_referencia_de_mase_frente_a_uno():
    assert criterios.UMBRAL_MASE_ADVERTENCIA == 1.0


def test_mase_menor_que_uno():
    texto = interpretar_backtesting(_metricas(0.6))
    assert "MASE < 1" in texto
    assert "0.600" in texto
    assert not any(e in texto.lower() for e in ETIQUETAS_PROHIBIDAS)


def test_mase_igual_a_uno():
    texto = interpretar_backtesting(_metricas(1.0))
    assert "MASE = 1" in texto
    assert not any(e in texto.lower() for e in ETIQUETAS_PROHIBIDAS)


def test_mase_mayor_que_uno():
    texto = interpretar_backtesting(_metricas(1.4))
    assert "MASE > 1" in texto
    assert not any(e in texto.lower() for e in ETIQUETAS_PROHIBIDAS)


def test_la_interpretacion_publica_siempre_los_valores():
    texto = interpretar_backtesting(_metricas(0.9, mape=17.5))
    for esperado in ("MAPE=17.500%", "MASE=0.900", "RMSE=1.000", "MAE=0.800"):
        assert esperado in texto, f"falta {esperado} en: {texto}"


def test_mape_no_calculable_no_inventa_lectura():
    texto = interpretar_backtesting({"mape": float("nan"), "mase": None, "rmse": 1.0, "mae": 1.0})
    assert "no fue posible interpretar" in texto.lower()


def test_mape_con_observado_cero_se_excluye_y_no_rompe():
    valor = calcular_mape([0.0, 100.0], [1.0, 110.0])
    assert abs(valor - 10.0) < 1e-9


def test_smape_se_calcula_y_no_se_clasifica():
    valor = calcular_smape([100.0, 200.0], [110.0, 190.0])
    assert 0.0 < valor < 200.0


def test_sesgo_positivo_y_negativo_conservan_signo():
    assert calcular_sesgo_medio([10.0, 10.0], [9.0, 9.0]) > 0
    assert calcular_sesgo_medio([10.0, 10.0], [11.0, 11.0]) < 0


def test_mase_se_calcula_con_la_escala_de_entrenamiento():
    valor = calcular_mase([10.0, 11.0], [10.5, 11.5], [1.0, 2.0, 3.0, 4.0])
    assert abs(valor - 0.5) < 1e-9


def test_ningun_modulo_vivo_usa_las_bandas_retiradas():
    objetivo = (
        RAIZ / "app_icociv" / "proyeccion" / "servicio_proyeccion.py",
        RAIZ / "app_icociv" / "estadistica" / "analisis_series.py",
        RAIZ / "app_icociv" / "validacion" / "backtesting.py",
        RAIZ / "app_icociv" / "estadistica" / "metricas.py",
    )
    prohibidas = (
        "UMBRAL_MASE_MEDIA",
        "UMBRAL_MAPE_ALTA_CONFIANZA",
        "UMBRAL_MAPE_MEDIA_CONFIANZA",
        "UMBRAL_MAPE_ALTO",
        "UMBRAL_MAPE_EXTREMO",
        "UMBRAL_SMAPE_ALTO",
        "UMBRAL_SMAPE_EXTREMO",
        "UMBRAL_SMAPE_EVIDENCIA_OK",
        "UMBRAL_SESGO_MAE",
    )
    for ruta in objetivo:
        texto = ruta.read_text(encoding="utf-8")
        for prohibida in prohibidas:
            assert prohibida not in texto, f"{ruta.name} conserva {prohibida}"


def test_el_catalogo_ya_no_declara_bandas_internas():
    ids = {c.id for c in criterios.matriz_criterios()}
    for retirado in ("C-MAPE-001", "C-SMAPE-001", "C-SES-001"):
        assert retirado not in ids, f"{retirado} sigue en la matriz"
    assert "C-MASE-001" in ids


def test_no_se_introdujeron_etiquetas_nuevas():
    for mase in (0.2, 0.8, 1.0, 1.2, 3.5):
        texto = interpretar_backtesting(_metricas(mase)).lower()
        for etiqueta in ETIQUETAS_PROHIBIDAS:
            assert etiqueta not in texto, f"etiqueta '{etiqueta}' con MASE={mase}"


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
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas de métricas sin bandas (D-9)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
