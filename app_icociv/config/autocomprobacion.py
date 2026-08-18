"""Autocomprobación de una distribución empaquetada de SAVIP.

Un ejecutable puede arrancar y aun así fallar al usar una función concreta,
porque falte un módulo que solo se importa en ese punto o porque un recurso no
viaje en la distribución. Este módulo ejercita, sin interfaz gráfica, las rutas
críticas del programa y devuelve un código de salida distinto de cero si alguna
falla.

Se invoca con ``SAVIP.exe --autocomprobacion`` y lo usa el script de
compilación como verificación posterior al empaquetado.
"""

from __future__ import annotations

import tempfile
import traceback
from pathlib import Path
from typing import Callable

from app_icociv.config.dependencias import VERSION_STATSMODELS_REQUERIDA
from app_icociv.config.rutas import (
    VERSION,
    asegurar_carpeta,
    carpeta_logs,
    es_ejecutable_congelado,
    ruta_recurso,
)


def _verificar_statsmodels() -> str:
    """`statsmodels` es obligatorio y su version debe ser la fijada.

    Antes era opcional y su presencia cambiaba modelos y cifras en silencio
    (hallazgo H-01). Ahora la distribucion no es valida sin el, y la version
    forma parte de la identidad del entorno.
    """
    import statsmodels
    from statsmodels.stats.diagnostic import acorr_ljungbox  # noqa: F401

    from app_icociv.estadistica.diagnostico_residuos import calcular_ljung_box

    instalada = str(statsmodels.__version__)
    if instalada != VERSION_STATSMODELS_REQUERIDA:
        raise ValueError(
            f"statsmodels {instalada} instalado; se requiere exactamente "
            f"{VERSION_STATSMODELS_REQUERIDA}."
        )

    import numpy as np

    residuos = np.sin(np.arange(40, dtype=float))
    prueba = calcular_ljung_box(residuos)
    if not prueba.get("disponible") or prueba.get("p_value") is None:
        raise ValueError("Ljung-Box no se pudo calcular con statsmodels instalado.")
    return f"statsmodels {instalada}; Ljung-Box operativo"


def _verificar_recursos_internos() -> str:
    """Los recursos de solo lectura deben viajar con la distribución."""
    faltantes = []
    for relativa in (
        "app_icociv/datos/iccp_historico.json",
        "app_icociv/interfaz/tema/plantilla.qss",
        "app_icociv/interfaz/recursos/savip_logo.png",
        "app_icociv/interfaz/recursos/savip_icono.png",
    ):
        if not ruta_recurso(relativa).is_file():
            faltantes.append(relativa)
    if faltantes:
        raise FileNotFoundError(f"Recursos ausentes: {', '.join(faltantes)}")
    return "recursos internos localizados"


def _verificar_datos_iccp() -> str:
    """El Anexo 10 ICCP interno debe cargarse y exponer sus series."""
    from app_icociv.servicios.empalme_iccp_icociv import grupos_iccp, series_iccp_por_tipo

    grupos = grupos_iccp()
    if not grupos:
        raise ValueError("El histórico ICCP se cargó vacío.")
    tipos = series_iccp_por_tipo()
    if not tipos.get("total_iccp"):
        raise ValueError("No se encontró la serie Total ICCP.")
    return f"ICCP cargado ({len(grupos)} grupos)"


def _verificar_empalme() -> str:
    """El cálculo de empalme debe producir un valor actualizado coherente."""
    from app_icociv.servicios.empalme_iccp_icociv import calcular_empalme_general

    resultado = calcular_empalme_general(
        {
            "precio_base": 1_000_000.0,
            "anticipo_amortizado": 0.0,
            "fecha_inicial": "2021_1",
            "fecha_final": "2021_12",
            "grupo_iccp": "Total ICCP",
            "unidad": "m3",
        },
        indices_icociv={},
    )
    if "valor_actualizado" not in resultado:
        raise ValueError("El empalme no devolvió valor actualizado.")
    return "empalme ICCP-ICOCIV operativo"


def _verificar_proyeccion() -> str:
    """El flujo estadístico debe ejecutarse de extremo a extremo."""
    import pandas as pd

    from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion

    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(48)]
    valores = [100.0 + 0.8 * i for i in range(48)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": valores})

    resultado = ejecutar_proyeccion(serie, 2025, 3, 2021)
    if not resultado.get("proyecciones") is not None:
        raise ValueError("La proyección no devolvió tabla de resultados.")
    modelo = resultado.get("model_name")
    if not modelo:
        raise ValueError("La proyección no seleccionó modelo.")
    return f"proyección ejecutada (modelo {modelo})"


def _verificar_exportables() -> str:
    """Los informes deben generarse en una carpeta escribible externa."""
    import pandas as pd

    from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
    from app_icociv.reportes.generador_reportes import (
        generar_csv_reproducibilidad,
        generar_reporte_pdf,
        generar_reporte_proyeccion,
    )
    from app_icociv.reportes.modelo import ConfiguracionInforme

    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(48)]
    valores = [100.0 + 0.8 * i for i in range(48)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": valores})
    resultado = ejecutar_proyeccion(serie, 2025, 3, 2021)

    with tempfile.TemporaryDirectory(prefix="savip_check_") as tmp:
        destino = Path(tmp)
        csv = generar_csv_reproducibilidad(destino / "prueba.csv", serie, resultado, None)
        if not Path(csv).is_file():
            raise ValueError("No se generó el CSV reproducible.")
        comunes = dict(
            usuario="autocomprobacion",
            archivo_excel="serie_sintetica",
            seleccion={},
            parametros_proyeccion={},
            ruta_jerarquica=None,
            fuente_label="autocomprobacion",
            fila=serie.head(1),
            serie_df=serie,
            resultado_proyeccion=resultado,
            year_month=periodos,
            configuracion=ConfiguracionInforme.desde_tipo("ejecutivo"),
        )
        docx = generar_reporte_proyeccion(destino / "prueba.docx", **comunes)
        if not Path(docx).is_file():
            raise ValueError("No se generó el informe DOCX.")
        pdf = Path(generar_reporte_pdf(destino / "prueba.pdf", **comunes))
        if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF"):
            raise ValueError("No se generó un informe PDF válido.")
    return "exportables DOCX, PDF y CSV generados"


def _verificar_escritura_externa() -> str:
    """Debe existir una ubicación escribible fuera de la carpeta del programa."""
    carpeta = asegurar_carpeta(carpeta_logs())
    prueba = carpeta / ".escritura_autocomprobacion"
    prueba.write_text("ok", encoding="utf-8")
    prueba.unlink()
    return f"escritura verificada en {carpeta}"


COMPROBACIONES: tuple[tuple[str, Callable[[], str]], ...] = (
    ("Dependencia statsmodels", _verificar_statsmodels),
    ("Recursos internos", _verificar_recursos_internos),
    ("Datos ICCP internos", _verificar_datos_iccp),
    ("Cálculo de empalme", _verificar_empalme),
    ("Flujo de proyección", _verificar_proyeccion),
    ("Generación de exportables", _verificar_exportables),
    ("Escritura fuera del bundle", _verificar_escritura_externa),
)


def ejecutar_autocomprobacion() -> int:
    """Ejecuta todas las comprobaciones y devuelve 0 si todas pasan."""
    print(f"Autocomprobacion de SAVIP {VERSION}")
    print(f"Modo: {'ejecutable empaquetado' if es_ejecutable_congelado() else 'codigo fuente'}")
    print("-" * 60)

    fallos = 0
    for nombre, comprobacion in COMPROBACIONES:
        try:
            detalle = comprobacion()
        except Exception as exc:  # se reporta y se continua con las demas
            fallos += 1
            print(f"  FALLA  {nombre}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
        else:
            print(f"  OK     {nombre}: {detalle}")

    print("-" * 60)
    total = len(COMPROBACIONES)
    if fallos:
        print(f"Resultado: {total - fallos}/{total} comprobaciones superadas. HAY FALLOS.")
        return 1
    print(f"Resultado: {total}/{total} comprobaciones superadas.")
    return 0
