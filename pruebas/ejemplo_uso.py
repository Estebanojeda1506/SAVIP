"""
example_usage.py
Ejemplo de uso completo del backend ICOCIV sin ninguna interfaz grÃ¡fica.
Ejecutar con: python example_usage.py
"""

import sys
from pathlib import Path

from app_icociv.proyeccion.servicio_proyeccion import ejecutar_analisis
from app_icociv.reportes.generador_reportes import guardar_reporte_docx, esta_docx_disponible


ROOT = Path(__file__).resolve().parents[1]


def resolver_archivo_excel() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    candidatos = sorted(ROOT.glob("*.xlsb")) + sorted(ROOT.glob("*.xlsx"))
    if not candidatos:
        raise FileNotFoundError("Indique la ruta de un archivo .xlsx/.xlsb como argumento.")
    return candidatos[0]


# ==============================
# 1. Cargar el archivo Excel
# ==============================
EXCEL_PATH = resolver_archivo_excel()

with open(EXCEL_PATH, "rb") as f:
    file_bytes = f.read()

# ==============================
# 2. Definir los parÃ¡metros de selecciÃ³n jerÃ¡rquica
#
# Estos valores equivalen a lo que el usuario elegirÃ­a en la UI:
#
#   idx_g       â†’ Ã­ndice de fila en T_16 (Grupos_Obra)
#   chk_T16     â†’ True: va a costos/insumos globales (T_16_6 â†’ T_16_7)
#   chk_T16_1   â†’ True: costos a nivel subclase (T_16_8 â†’ T_16_9)
#   chk_T16_2   â†’ True: costos a nivel tipologÃ­a (T_16_10 â†’ T_16_11)
#   chk_T16_3   â†’ True: costos a nivel capÃ­tulo (T_16_12 â†’ T_16_13)
#   idx_l2..l6  â†’ Ã­ndices de fila en el respectivo DataFrame filtrado
#
# Para empezar solo con el nivel 1 (Grupo de obra):
selection = {
    "idx_g":    0,       # primer grupo en T_16
    "chk_T16":  False,   # rama normal (subclases â†’ tipologÃ­as â†’ capÃ­tulos)
    "idx_l2":   0,       # primera subclase en T_16_1
    "chk_T16_1": False,
    "idx_l3":   0,       # primera tipologÃ­a en T_16_2
    "chk_T16_2": False,
    "idx_l4":   None,    # sin capÃ­tulo constructivo
    "chk_T16_3": False,
}

# ==============================
# 3. Definir el periodo de proyecciÃ³n
# ==============================
YEAR_PROJ  = 2026
MONTH_PROJ = 6

# ==============================
# 4. Ejecutar el anÃ¡lisis completo
# ==============================
print("Cargando datos y ejecutando anÃ¡lisis...")

result = ejecutar_analisis(
    file_bytes=file_bytes,
    file_name=EXCEL_PATH.name,
    selection=selection,
    year_proj=YEAR_PROJ,
    month_proj=MONTH_PROJ,
)

# ==============================
# 5. Mostrar resultados
# ==============================
proj = result["projection"]

print(f"\n{'='*50}")
print(f"Tabla fuente:         {result['fuente']}")
print(f"Periodo proyectado:   {proj['periodo_proj'].strip()}")
print(f"Modelo seleccionado:  {proj['model_name']}")
print(f"Ãndice proyectado:    {proj['y_proj']:.4f}")
print(f"IC 95%:               [{proj['ci_lo']:.4f}, {proj['ci_hi']:.4f}]")
print(f"\nEstadÃ­sticos del modelo:")
stats = proj["stats"]
print(f"  RÂ²:         {stats['r2']:.4f}")
print(f"  JB p-value: {stats['jb_p']:.4f}")
print(f"  Curtosis:   {stats['kurt_ex']:.4f}")
print(f"  n obs:      {stats['n']}")

print(f"\nSerie histÃ³rica (Ãºltimos 6 periodos):")
print(result["serie_df"].tail(6).to_string(index=False))

# ==============================
# 6. Exportar reporte Word (opcional)
# ==============================
if esta_docx_disponible():
    OUTPUT_DOCX = "Informe_ICOCIV.docx"
    guardar_reporte_docx(
        output_path=OUTPUT_DOCX,
        fuente_label=result["fuente"],
        fila=result["fila"],
        serie_df=result["serie_df"],
        projection=result["projection"],
        year_month=result["year_month"],
    )
    print(f"\nReporte guardado en: {OUTPUT_DOCX}")
else:
    print("\nInstala python-docx para exportar el reporte: pip install python-docx")

# ==============================
# 7. Acceso directo a tablas (para debugging / exploraciÃ³n)
# ==============================
tables = result["tables"]
print(f"\nTablas disponibles: {list(tables.keys())}")
print(f"Columnas T_16: {tables['T_16'].columns.tolist()}")
print(f"Periodos detectados: {len(result['year_month'])} "
      f"(Ãºltimo: {result['year_month'][-1].strip()})")
