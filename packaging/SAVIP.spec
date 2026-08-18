# -*- mode: python ; coding: utf-8 -*-
"""Especificacion de empaquetado de la aplicacion SAVIP con PyInstaller.

Genera una distribucion en carpeta (onedir). Se admiten dos variantes mediante
la variable de entorno SAVIP_BUILD:

  distribucion  (por defecto)  SAVIP.exe         sin consola
  diagnostico                  SAVIP-debug.exe   con consola, para depurar

Uso habitual (desde la raiz del repositorio):

    pyinstaller packaging/SAVIP.spec --noconfirm

No editar rutas absolutas aqui: todo se resuelve desde la raiz del repositorio.
"""

import os
import pathlib
from pathlib import Path

# SPECPATH lo define PyInstaller: carpeta que contiene este .spec.
RAIZ = Path(SPECPATH).resolve().parent

MODO = os.environ.get("SAVIP_BUILD", "distribucion").strip().lower()
ES_DIAGNOSTICO = MODO == "diagnostico"
NOMBRE_EXE = "SAVIP-debug" if ES_DIAGNOSTICO else "SAVIP"

# --- Recursos internos de solo lectura -------------------------------------
# Se conserva la misma ruta relativa que en el repositorio, porque
# app_icociv.config.rutas.ruta_recurso() los busca con esa estructura.
datas = [
    (str(RAIZ / "app_icociv" / "datos" / "iccp_historico.json"), "app_icociv/datos"),
    (str(RAIZ / "app_icociv" / "interfaz" / "tema" / "plantilla.qss"), "app_icociv/interfaz/tema"),
    (str(RAIZ / "app_icociv" / "interfaz" / "recursos" / "savip_logo.png"), "app_icociv/interfaz/recursos"),
    (str(RAIZ / "app_icociv" / "interfaz" / "recursos" / "savip_icono.png"), "app_icociv/interfaz/recursos"),
    (str(RAIZ / "VERSION"), "."),
]

# Fuentes Bitstream Vera que ReportLab incrusta en el PDF. PyInstaller no las
# arrastra solo porque se abren por ruta en tiempo de ejecucion; sin ellas el
# informe caeria a una fuente base del visor y dejaria de ser autocontenido.
try:
    import reportlab as _reportlab

    _FUENTES = pathlib.Path(_reportlab.__file__).parent / "fonts"
    datas += [
        (str(_FUENTES / nombre), "reportlab/fonts")
        for nombre in ("Vera.ttf", "VeraBd.ttf", "VeraIt.ttf")
        if (_FUENTES / nombre).is_file()
    ]
except ImportError:
    pass

# --- Imports que PyInstaller no siempre detecta ----------------------------
hiddenimports = [
    # Backend Qt de matplotlib: se importa por nombre dentro de matplotlib.
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
    # Lectura de anexos ICOCIV en formato binario y xlsx.
    "pyxlsb",
    "openpyxl",
    # Modelos usados por app_icociv.estadistica.modelos_interpretables.
    "sklearn.linear_model",
    "sklearn.utils._typedefs",
    "sklearn.utils._heap",
    "sklearn.utils._sorting",
    "sklearn.utils._vector_sentinel",
    # Generacion de informes DOCX.
    "docx",
    # Generacion de informes PDF paginados con indice y marcadores.
    "reportlab",
    "reportlab.pdfbase._fontdata",
    "reportlab.graphics.barcode",
]

# statsmodels es dependencia OBLIGATORIA desde julio de 2026. Se usa solo para
# el diagnostico Ljung-Box; no interviene en modelos ni en intervalos.
#
# Se declara unicamente el submodulo que la aplicacion importa. No se agregan
# hiddenimports adicionales sin evidencia de que PyInstaller no los detecte:
# statsmodels arrastra un arbol grande y declararlo entero infla la
# distribucion sin necesidad.
import statsmodels  # noqa: F401

hiddenimports += ["statsmodels.stats.diagnostic"]

# --- Exclusiones justificadas ----------------------------------------------
# Reducen tamano sin afectar el flujo: la aplicacion no usa cuadernos Jupyter,
# ni Tkinter, ni los modulos web/multimedia de Qt.
#
# Las librerias de aprendizaje profundo (torch, onnxruntime, etc.) no forman
# parte del proyecto. Se excluyen como defensa por si la compilacion se
# ejecuta en un entorno con esas librerias instaladas: sin esta barrera, una
# unica referencia transitiva agrega varios gigabytes a la distribucion.
# La compilacion normal usa .venv-build y no deberia encontrarlas.
#
# Los arboles que NO son el producto se excluyen por nombre, aunque hoy ningun
# import los alcance: la barrera es explicita para que una importacion futura no
# los arrastre en silencio. La auditoria bibliografica y la verificacion de
# fuentes pertenecen al proceso academico de la tesis; el ejecutable no lleva
# tesis, auditorias, referencias, pruebas ni documentos de remediacion.
excludes = [
    "tests",
    "pruebas",
    "auditoria_academica",
    "docs",
    "tkinter",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "torch",
    "torchvision",
    "torchaudio",
    "onnxruntime",
    "transformers",
    "pyarrow",
    "llvmlite",
    "numba",
    "av",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtQuick",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
]

# --- Material de pruebas de dependencias de terceros -----------------------
# RA-06 (reauditoria de 0.3.0-rc2): la distribucion llevaba 83 archivos bajo
# _internal/sklearn/datasets/tests/data. No son pruebas ni bibliografia de
# SAVIP: son ficheros de apoyo (svmlight, mocks de OpenML) del banco de pruebas
# de scikit-learn, arrastrados por el hook de PyInstaller, que recolecta los
# datos del paquete completo.
#
# Se determino que pueden excluirse con seguridad porque:
#   1. SAVIP importa unicamente `sklearn.linear_model`
#      (HuberRegressor y LinearRegression), nunca `sklearn.datasets`;
#   2. son insumos del propio banco de pruebas de la dependencia, no recursos
#      que su codigo de ejecucion abra;
#   3. la carga, la prediccion, las metricas y los informes se verifican tras
#      la compilacion con la autocomprobacion 7/7 y la generacion CSV/DOCX/PDF.
#
# Se excluyen SOLO arboles `tests` de dependencias, por prefijo explicito. No
# se toca ningun otro dato de paquete: una exclusion amplia podria retirar un
# recurso que si se usa en ejecucion.
ARBOLES_DE_PRUEBAS_DE_TERCEROS = (
    "sklearn/datasets/tests/",
    "sklearn/datasets/tests\\",
)


def _es_material_de_pruebas_de_terceros(destino: str) -> bool:
    ruta = str(destino).replace("\\", "/")
    return any(ruta.startswith(p.replace("\\", "/")) for p in ARBOLES_DE_PRUEBAS_DE_TERCEROS)


a = Analysis(
    [str(RAIZ / "aplicacion.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# Filtro efectivo: se aplica despues del analisis, cuando ya se conoce la lista
# final de datos recolectados. Se informa el recuento para que quede en el log
# de compilacion y sea contrastable con el inventario del ejecutable.
_datas_antes = len(a.datas)
a.datas = [entrada for entrada in a.datas if not _es_material_de_pruebas_de_terceros(entrada[0])]
print(
    f"[SAVIP.spec] Material de pruebas de terceros excluido: "
    f"{_datas_antes - len(a.datas)} archivo(s); quedan {len(a.datas)} datos empaquetados."
)

pyz = PYZ(a.pure)

# El archivo de metadatos de Windows solo se aplica si existe.
_version_file = RAIZ / "packaging" / "version_info.txt"
version_file = str(_version_file) if _version_file.exists() else None

# Icono opcional: si no hay .ico disponible, se compila sin icono propio.
_icono = RAIZ / "packaging" / "savip.ico"
icono = str(_icono) if _icono.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE_EXE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=ES_DIAGNOSTICO,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icono,
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NOMBRE_EXE,
)
