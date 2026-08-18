"""Validación del módulo estadístico y backtesting temporal."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.interfaz.controladores.controlador_principal import ControladorPrincipal
from app_icociv.validacion.backtesting import ejecutar_backtesting
from app_icociv.estadistica.diagnostico_residuos import durbin_watson, evaluar_residuos
from app_icociv.estadistica.validacion_series import analizar_serie_temporal, validar_serie
from app_icociv.reportes.generador_reportes import generar_reporte_proyeccion


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
serie_df = resultado["serie_df"]
proyeccion = resultado["proyeccion"]

validacion = validar_serie(serie_df)
analisis = analizar_serie_temporal(serie_df)
backtesting = ejecutar_backtesting(serie_df)
residuos = proyeccion["y_obs"] - proyeccion["y_fit_obs"]
diagnostico = evaluar_residuos(residuos)

assert validacion["observaciones"] >= 24
assert validacion["continuidad_temporal"] == "OK"
assert backtesting["ejecutado"]
assert backtesting["iteraciones"] > 0
assert "mape" in backtesting["metricas"]
assert durbin_watson(residuos) > 0
assert diagnostico["durbin_watson"] > 0
assert proyeccion["stats"].get("r2_ajustado") is not None
assert proyeccion["stats"].get("durbin_watson") is not None
assert proyeccion.get("interpretacion_estadistica")

ruta_reporte = ROOT / "reportes_generados" / "validacion_estadistica_icociv.docx"
generar_reporte_proyeccion(
    ruta_salida=ruta_reporte,
    usuario="validacion",
    archivo_excel=str(archivo_excel),
    seleccion=seleccion,
    parametros_proyeccion={"anio": 2026, "mes": 6},
    ruta_jerarquica=resultado["ruta_jerarquica"],
    fuente_label=resultado["fuente"],
    fila=resultado["fila"],
    serie_df=serie_df,
    resultado_proyeccion=proyeccion,
    year_month=controlador.periodos,
    nombre_sesion=None,
)

assert ruta_reporte.exists()
assert ruta_reporte.stat().st_size > 10_000

print("=== VALIDACIÓN ESTADÍSTICA ===")
print("Observaciones:", validacion["observaciones"])
print("Continuidad:", validacion["continuidad_temporal"])
print("Tendencia:", analisis["tendencia"])
print("Backtesting iteraciones:", backtesting["iteraciones"])
print("MAPE:", backtesting["metricas"]["mape"])
print("Durbin-Watson:", diagnostico["durbin_watson"])
print("Reporte:", ruta_reporte)
