"""Pruebas dirigidas de RA-04 (reauditoria de 0.3.0-rc2).

La reauditoria comprobo que, cuando Ljung-Box no arroja valor p por muestra
corta o por residuos constantes, el informe decia que la prueba «no esta
disponible en esta distribucion de SAVIP». Eso es falso: statsmodels es
dependencia obligatoria y su ausencia impide arrancar la aplicacion. Lo que no
es calculable es el diagnostico para esa serie.

Se blindan tres cosas y **no** se toca el calculo validado:

1. la dependencia se declara disponible;
2. el diagnostico se declara no calculable;
3. se da el motivo especifico.

Ejecucion directa, sin pytest:

    python tests/test_mensajes_ljung_box.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica.diagnostico_residuos import calcular_ljung_box  # noqa: E402
from app_icociv.reportes.contenido import _motivo_ljung_box  # noqa: E402
from app_icociv.utilidades.utilidades import version_statsmodels  # noqa: E402

#: Frase prohibida por RA-04 cuando statsmodels si esta instalado.
PROHIBIDA = "no está disponible en esta distribución"


# =========================================================
# El calculo validado no cambia
# =========================================================


def test_el_calculo_sigue_dando_valor_p_con_muestra_suficiente():
    generador = np.random.default_rng(11)
    resultado = calcular_ljung_box(generador.normal(0.0, 1.0, 80))
    assert resultado["disponible"] is True, resultado
    assert resultado["p_value"] is not None
    assert 0.0 <= float(resultado["p_value"]) <= 1.0
    assert resultado["model_df"] == 0, "model_df declarado sigue siendo 0"


# =========================================================
# Muestra corta
# =========================================================


def test_muestra_corta_no_es_calculable_y_dice_por_que():
    """D-10: el minimo es derivado, n > rezagos, no un valor fijo de 12."""
    # Con 4 residuos, min(10, 4//5) = 0 rezagos: el contraste no existe.
    resultado = calcular_ljung_box(np.arange(4, dtype=float))
    assert resultado["disponible"] is False
    assert resultado["p_value"] is None
    assert "No calculable" in resultado["mensaje"]
    assert "n/5" in resultado["mensaje"], resultado["mensaje"]


def test_los_rezagos_siguen_la_regla_de_la_fuente():
    """D-10: h = min(10, n/5), segun Hyndman y Athanasopoulos (2021), 5.4."""
    generador = np.random.default_rng(5)
    for n, esperado in ((20, 4), (40, 8), (50, 10), (65, 10), (120, 10)):
        resultado = calcular_ljung_box(generador.normal(0.0, 1.0, n))
        assert resultado["rezagos"] == esperado, (n, resultado["rezagos"], esperado)


def test_el_texto_de_muestra_corta_no_culpa_a_la_distribucion():
    resultado = calcular_ljung_box(np.arange(4, dtype=float))
    texto = _motivo_ljung_box(resultado)
    assert PROHIBIDA not in texto, texto
    assert "no se calcula" in texto.lower(), texto


# =========================================================
# Residuos constantes
# =========================================================


def test_residuos_constantes_no_son_calculables_y_dicen_por_que():
    resultado = calcular_ljung_box(np.full(40, 3.5))
    assert resultado["disponible"] is False
    assert resultado["p_value"] is None
    assert "constantes" in resultado["mensaje"]


def test_el_texto_de_residuos_constantes_es_el_exigido():
    resultado = calcular_ljung_box(np.full(40, 3.5))
    texto = _motivo_ljung_box(resultado)
    assert PROHIBIDA not in texto, texto
    assert texto == "Ljung–Box no se calcula porque los residuos son constantes.", texto


# =========================================================
# La dependencia siempre se declara presente
# =========================================================


def test_statsmodels_esta_instalado_y_se_puede_informar_su_version():
    version = str(version_statsmodels() or "").strip()
    assert version, "statsmodels es obligatorio y su version debe poder informarse"
    assert version.startswith("0.14.6"), version


def test_ningun_motivo_atribuye_la_ausencia_a_la_distribucion():
    casos = (
        # Muestra corta. El minimo fijo de 12 residuos se retiro el
        # 04-08-2026 por estar muerto: la condicion viva es n > rezagos,
        # derivada en `calcular_ljung_box` por D-10.
        np.arange(11, dtype=float),
        np.full(40, 3.5),
        np.array([], dtype=float),
    )
    for residuos in casos:
        texto = _motivo_ljung_box(calcular_ljung_box(residuos))
        assert PROHIBIDA not in texto, (len(residuos), texto)
        assert "distribución de SAVIP" not in texto, (len(residuos), texto)
        assert texto.strip().endswith("."), texto


def test_el_informe_declara_dependencia_disponible_y_diagnostico_no_calculable():
    """Las tres piezas exigidas viajan juntas al informe técnico."""
    from app_icociv.reportes.contenido import _seccion_residuos
    from app_icociv.reportes.contenido import DatosProyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme
    import pandas as pd

    diagnostico = {
        "media": 0.0,
        "desviacion": 0.0,
        "durbin_watson": 2.0,
        "ljung_box": calcular_ljung_box(np.full(40, 3.5)),
        "alertas": [],
    }
    serie = pd.DataFrame({"Periodo": ["2020_1", "2020_2"], "Indice": [100.0, 101.0]})
    datos = DatosProyeccion(resultado={"diagnostico_residuos": diagnostico}, serie_df=serie)
    seccion = _seccion_residuos(datos, ConfiguracionInforme.desde_tipo("tecnico"))
    texto = " ".join(getattr(b, "texto", "") for b in seccion.bloques)
    assert PROHIBIDA not in texto, texto
    assert "no se calcula" in texto, texto
    assert "residuos son constantes" in texto, texto
    assert "statsmodels" in texto and "está disponible" in texto, texto
    assert "obligatoria" in texto, texto


# ==============================
# CORREDOR
# ==============================


def main() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except Exception:
            fallos += 1
            print(f"  FALLA {prueba.__name__}")
            traceback.print_exc()
    total = len(pruebas)
    print(f"\n{total - fallos}/{total} pruebas de mensajes de Ljung-Box")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
