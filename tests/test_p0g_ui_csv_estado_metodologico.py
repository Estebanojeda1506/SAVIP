"""P0-G: la interfaz y el CSV reproducible comunican P0-C y P0-E (U1-U6).

Ultimo residuo de la reapertura. El resultado transportaba `estado_metodologico`,
`bloqueos_metodologicos`, `intervalo_sustentado` y `evidencia_oos_provisional`, y
**ni la interfaz ni el CSV reproducible los mostraban**: el usuario veia un
pronostico y unos intervalos sin saber que su fundamento sigue abierto, y un
archivo pensado para auditar omitia los bloqueos vigentes.

Estas seis pruebas fijan el transporte en las tres rutas -con proyeccion, sin
proyeccion y bloqueo tecnico- y que ninguna de las dos salidas sobreafirme.

Ejecucion directa, sin pytest:

    python tests/test_p0g_ui_csv_estado_metodologico.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.interfaz.presentacion_resultados import construir_html_resultados  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion  # noqa: E402
from app_icociv.reportes.generador_reportes import (  # noqa: E402
    construir_dataframe_reproducibilidad,
)

CAMPOS = (
    "estado_metodologico",
    "bloqueos_metodologicos",
    "intervalo_sustentado",
    "evidencia_oos_provisional",
)

#: Nada de esto puede aparecer mientras P0-C y P0-E sigan pendientes.
PROHIBIDAS = ("validado", "desempeño aceptable", "desempeno aceptable",
              "confianza alta", "confianza media", "confianza baja",
              "certificad", "garantiza")


def _serie(n: int, pendiente: float = 1.5) -> pd.DataFrame:
    return pd.DataFrame({
        "Periodo": [f"{2024 + i // 12}_{i % 12 + 1}" for i in range(n)],
        "Indice": [100.0 + pendiente * i for i in range(n)],
    })


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _con_proyeccion() -> dict:
    serie = _serie(8)
    return ejecutar_proyeccion(serie, *_objetivo(serie, 1), 2021)


def _sin_proyeccion() -> tuple[pd.DataFrame, dict]:
    """Serie con un periodo invalido: imposibilidad TECNICA, no metodologica."""
    serie = _serie(10)
    serie.loc[5, "Periodo"] = "2024_13"
    return serie, ejecutar_proyeccion(serie, 2025, 6, 2021)


def _sin_prohibidas(texto: str, contexto: str) -> None:
    bajo = texto.lower()
    for palabra in PROHIBIDAS:
        assert palabra not in bajo, (contexto, palabra)


# ==============================
# U1-U2: interfaz
# ==============================


def test_u1_la_interfaz_declara_p0c_y_p0e_cuando_hay_punto() -> None:
    """U1. Con punto calculable y bloqueos abiertos, la interfaz lo dice."""
    resultado = _con_proyeccion()
    assert resultado["proyeccion_generada"] is True
    html = construir_html_resultados(resultado)

    assert "Estado metodológico" in html
    assert "P0-C" in html and "P0-E" in html, "los dos bloqueos deben nombrarse"
    assert "no cuenta con sustento" in html or "no cuenta con un método sustentado" in html
    assert "Provisional" in html
    # El intervalo se declara sin método sustentado.
    assert "Intervalo con método sustentado" in html
    _sin_prohibidas(html, "UI con proyección")


def test_u2_la_interfaz_declara_el_estado_sin_proyeccion() -> None:
    """U2. Sin tabla de proyección el estado metodológico no se oculta."""
    _, resultado = _sin_proyeccion()
    assert resultado["proyeccion_generada"] is False
    html = construir_html_resultados(resultado)

    assert "Estado metodológico" in html
    assert "P0-C" in html and "P0-E" in html
    _sin_prohibidas(html, "UI sin proyección")


def test_u3_la_interfaz_distingue_lo_tecnico_de_lo_metodologico() -> None:
    """U3. Una imposibilidad de cálculo no se etiqueta como P0-C/P0-E."""
    _, resultado = _sin_proyeccion()
    assert resultado["estado_metodologico"] == "no_calculable"
    html = construir_html_resultados(resultado)
    assert "no es técnicamente calculable" in html
    assert "distinta de las limitaciones metodológicas" in html


# ==============================
# U4-U6: CSV reproducible
# ==============================


def test_u4_el_csv_trae_los_cuatro_campos_con_proyeccion() -> None:
    """U4."""
    resultado = _con_proyeccion()
    tabla = construir_dataframe_reproducibilidad(_serie(8), resultado)
    for campo in CAMPOS:
        assert campo in tabla.columns, campo
    fila = tabla.iloc[0]
    assert bool(fila["intervalo_sustentado"]) is False
    assert bool(fila["evidencia_oos_provisional"]) is True
    assert str(fila["estado_metodologico"]) == "calculable_metodologia_pendiente"
    assert str(fila["bloqueos_metodologicos"]) == "P0-C|P0-E"
    _sin_prohibidas(" ".join(str(v) for v in fila.values), "CSV con proyección")


def test_u5_el_csv_trae_los_cuatro_campos_sin_proyeccion() -> None:
    """U5. La ruta bloqueada tampoco puede omitirlos."""
    serie, resultado = _sin_proyeccion()
    tabla = construir_dataframe_reproducibilidad(serie, resultado)
    for campo in CAMPOS:
        assert campo in tabla.columns, campo
    fila = tabla.iloc[0]
    assert str(fila["estado_metodologico"]) == "no_calculable"
    assert str(fila["bloqueos_metodologicos"]) == "P0-C|P0-E"
    assert bool(fila["intervalo_sustentado"]) is False


def test_u6_la_serializacion_de_bloqueos_es_determinista() -> None:
    """U6. Mismo resultado, misma cadena: el CSV debe ser reproducible (REQ 24)."""
    resultado = _con_proyeccion()
    serie = _serie(8)
    primera = construir_dataframe_reproducibilidad(serie, resultado).iloc[0]
    segunda = construir_dataframe_reproducibilidad(serie, resultado).iloc[0]
    assert str(primera["bloqueos_metodologicos"]) == str(segunda["bloqueos_metodologicos"])
    # Orden alfabético estable y separador declarado, sin repr de Python.
    texto = str(primera["bloqueos_metodologicos"])
    assert texto == "|".join(sorted(texto.split("|"))), texto
    for basura in ("{", "}", "[", "]", "'", "dict_keys"):
        assert basura not in texto, (basura, texto)


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
