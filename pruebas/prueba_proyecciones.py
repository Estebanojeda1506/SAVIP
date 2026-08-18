import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.datos.cargador_datos import cargar_todas_tablas
from app_icociv.proyeccion.servicio_proyeccion import (
    resolver_fila_seleccionada,
    construir_serie,
    ejecutar_proyeccion
)

from app_icociv.utilidades.utilidades import ANIO_BASE


def resolver_archivo_excel() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    candidatos = sorted(ROOT.glob("*.xlsb")) + sorted(ROOT.glob("*.xlsx"))
    if not candidatos:
        raise FileNotFoundError("Indique la ruta de un archivo .xlsx/.xlsb como argumento.")
    return candidatos[0]


# ==========================================
# CARGAR ARCHIVO
# ==========================================

FILE = resolver_archivo_excel()

with open(FILE, "rb") as f:
    file_bytes = f.read()

tables, year_month = cargar_todas_tablas(
    file_bytes,
    FILE.name
)

# ==========================================
# SELECCIÃ“N DE EJEMPLO
# ==========================================

selection = {
    "idx_g": 0,
    "chk_T16": False,
}

# ==========================================
# RESOLVER FILA SELECCIONADA
# ==========================================

fuente, fila = resolver_fila_seleccionada(
    tables,
    year_month,
    selection
)

print("\n=== FUENTE ===")
print(fuente)

print("\n=== FILA ===")
print(fila.head())

# ==========================================
# CONSTRUIR SERIE
# ==========================================

serie_df = construir_serie(
    fila,
    year_month
)

print("\n=== SERIE ===")
print(serie_df.head())

# ==========================================
# EJECUTAR PROYECCIÃ“N
# ==========================================

result = ejecutar_proyeccion(
    serie_df=serie_df,
    year_proj=2026,
    month_proj=6,
    anio_base=ANIO_BASE,
)

# ==========================================
# RESULTADOS
# ==========================================

print("\n=== RESULTADO PROYECCIÃ“N ===")

print("Modelo:", result["model_name"])
print("Proyección generada:", result.get("proyeccion_generada"))
if result.get("proyeccion_generada"):
    print("Periodo proyectado:", result["periodo_proj"])
    print("Valor proyectado:", result["y_proj"])
    print("IC inferior:", result["ci_lo"])
    print("IC superior:", result["ci_hi"])
else:
    print("Resultado de factibilidad:", result.get("factibilidad", {}).get("nivel_confianza_metodologica"))
    print("Explicacion:", result.get("explicacion"))
    razones = result.get("factibilidad", {}).get("razones_tecnicas", [])
    for razon in razones[:6]:
        print("-", razon)
    if len(razones) > 6:
        print(f"- {len(razones) - 6} diagnosticos adicionales registrados en el informe.")
