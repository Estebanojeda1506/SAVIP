"""Validación funcional de sesiones JSON e informes DOCX."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.interfaz.controladores.controlador_principal import ControladorPrincipal
from app_icociv.persistencia.gestor_sesiones import (
    cargar_sesion,
    generar_nombre_sesion,
    guardar_sesion,
)
from app_icociv.reportes.generador_reportes import generar_nombre_reporte, generar_reporte_proyeccion


def resolver_archivo_excel() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    candidatos = sorted(ROOT.glob("*.xlsb")) + sorted(ROOT.glob("*.xlsx"))
    if not candidatos:
        raise FileNotFoundError("Indique la ruta de un archivo .xlsx/.xlsb como argumento.")
    return candidatos[0]


archivo_excel = resolver_archivo_excel()
controlador = ControladorPrincipal()
controlador.cargar_archivo(archivo_excel)

seleccion = {"idx_g": 0, "chk_T16": False}
resultado = controlador.ejecutar_analisis(seleccion, 2026, 6)
ruta_jerarquica = resultado["ruta_jerarquica"]
usuario = "validacion"
parametros = {"anio": 2026, "mes": 6}

nombre_sesion = generar_nombre_sesion(
    usuario,
    ruta_jerarquica,
    resultado["proyeccion"]["periodo_proj"],
)
ruta_sesion = ROOT / "sesiones" / nombre_sesion
datos_sesion = controlador.crear_datos_sesion(usuario, seleccion, parametros, ruta_jerarquica)
guardar_sesion(ruta_sesion, datos_sesion)
datos_cargados = cargar_sesion(ruta_sesion)

nombre_reporte = generar_nombre_reporte(
    usuario,
    ruta_jerarquica,
    resultado["proyeccion"]["periodo_proj"],
)
ruta_reporte = ROOT / "reportes_generados" / nombre_reporte
generar_reporte_proyeccion(
    ruta_salida=ruta_reporte,
    usuario=usuario,
    archivo_excel=str(archivo_excel),
    seleccion=seleccion,
    parametros_proyeccion=parametros,
    ruta_jerarquica=ruta_jerarquica,
    fuente_label=resultado["fuente"],
    fila=resultado["fila"],
    serie_df=resultado["serie_df"],
    resultado_proyeccion=resultado["proyeccion"],
    year_month=controlador.periodos,
    nombre_sesion=ruta_sesion.name,
)

print("Sesion:", ruta_sesion, ruta_sesion.exists(), datos_cargados["usuario"])
print("Reporte:", ruta_reporte, ruta_reporte.exists(), ruta_reporte.stat().st_size)
