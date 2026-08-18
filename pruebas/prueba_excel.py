import sys
from pathlib import Path
from pprint import pprint

# ==========================================
# AGREGAR RAÃZ DEL PROYECTO AL PATH
# ==========================================
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.datos.cargador_datos import cargar_todas_tablas


def resolver_archivo_excel() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    candidatos = sorted(ROOT.glob("*.xlsb")) + sorted(ROOT.glob("*.xlsx"))
    if not candidatos:
        raise FileNotFoundError("Indique la ruta de un archivo .xlsx/.xlsb como argumento.")
    return candidatos[0]


# ==========================================
# ARCHIVO EXCEL A PROBAR
# ==========================================
FILE = resolver_archivo_excel()

with open(FILE, "rb") as f:
    file_bytes = f.read()

tables, periods = cargar_todas_tablas(
    file_bytes,
    FILE.name
)

# ==========================================
# VALIDACIÃ“N DE PERIODOS
# ==========================================
print("\n=== PERIODOS DETECTADOS ===")
pprint(periods)

print("\n=== RESUMEN PERIODOS ===")
print("Primer periodo:", periods[0])
print("Ãšltimo periodo:", periods[-1])
print("Cantidad periodos:", len(periods))

# ==========================================
# TABLAS CARGADAS
# ==========================================
print("\n=== TABLAS ===")

for name, df in tables.items():

    print(f"\n========== {name} ==========")

    print("\nShape:")
    print(df.shape)

    print("\nColumnas:")
    pprint(df.columns.tolist())

    print("\nTipos Ãºltimas columnas:")
    print(df.dtypes.tail())

    print("\nValores nulos Ãºltimas columnas:")
    print(df.isnull().sum().tail())

    print("\nPrimeras filas:")
    print(df.head())

    print("\nÃšltima columna:")
    print(df.iloc[:, -1].head())
