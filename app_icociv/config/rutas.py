"""Rutas centrales de la aplicación SAVIP.

Este módulo es el único lugar del proyecto que distingue entre ejecución desde
código fuente y ejecución desde un ejecutable empaquetado (PyInstaller). El
resto de la aplicación importa rutas ya resueltas y no consulta ``sys.frozen``.

Se separan tres categorías, porque tienen permisos y ciclos de vida distintos:

- **Recursos internos** (solo lectura): viajan con la aplicación. Se resuelven
  con :func:`ruta_recurso`.
- **Datos del usuario** (lectura y escritura): reportes, exportaciones y
  sesiones. Van a ``Documentos/SAVIP`` para que sobrevivan a una
  reinstalación y no dependan de permisos de escritura del directorio de
  instalación.
- **Datos de aplicación**: registros de ejecución, en ``%LOCALAPPDATA%``.

Nunca se escribe dentro de ``_MEIPASS`` ni de ``_internal``: en modo *onefile*
esa carpeta es temporal y se borra al cerrar, y en instalaciones bajo
``Program Files`` es de solo lectura.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def es_ejecutable_congelado() -> bool:
    """Indica si la aplicación corre desde un ejecutable empaquetado."""
    return bool(getattr(sys, "frozen", False))


def _raiz_recursos() -> Path:
    """Directorio base de los recursos de solo lectura.

    En *onefile* PyInstaller expone ``sys._MEIPASS``; en *onedir* los datos
    quedan junto al ejecutable. Desde código fuente, la raíz del repositorio.
    """
    if es_ejecutable_congelado():
        base = getattr(sys, "_MEIPASS", None)
        return Path(base) if base else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def ruta_recurso(ruta_relativa: str | os.PathLike[str]) -> Path:
    """Resuelve un recurso interno de solo lectura empaquetado con la aplicación.

    La ruta relativa se expresa igual que en el repositorio, por ejemplo
    ``"app_icociv/datos/iccp_historico.json"``.
    """
    return _raiz_recursos() / Path(ruta_relativa)


def _carpeta_documentos() -> Path:
    """Carpeta Documentos del usuario, con respaldo si el perfil es atípico."""
    perfil = Path.home()
    for nombre in ("Documents", "Documentos"):
        candidata = perfil / nombre
        if candidata.is_dir():
            return candidata
    return perfil


def carpeta_datos_usuario() -> Path:
    """Carpeta raíz de datos del usuario para reportes, exportables y sesiones."""
    if es_ejecutable_congelado():
        return _carpeta_documentos() / "SAVIP"
    # En desarrollo se conserva el comportamiento histórico dentro del repositorio.
    return RAIZ_PROYECTO


def carpeta_logs() -> Path:
    """Carpeta de registros de ejecución.

    Empaquetada usa ``%LOCALAPPDATA%\\SAVIP\\logs``; en desarrollo, ``logs/``
    dentro del repositorio para no ensuciar el perfil del desarrollador.
    """
    if es_ejecutable_congelado():
        base = os.environ.get("LOCALAPPDATA")
        raiz = Path(base) if base else _carpeta_documentos()
        return raiz / "SAVIP" / "logs"
    return RAIZ_PROYECTO / "logs"


def asegurar_carpeta(ruta: Path) -> Path:
    """Crea la carpeta si no existe y devuelve la ruta; nunca lanza excepción."""
    try:
        ruta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return ruta


def version_aplicacion() -> str:
    """Lee la versión desde el archivo ``VERSIÓN``, única fuente de verdad."""
    candidatas = (
        ruta_recurso("VERSION"),
        Path(__file__).resolve().parents[2] / "VERSION",
    )
    for candidata in candidatas:
        try:
            texto = candidata.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if texto:
            return texto
    return "desconocida"


RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
"""Raíz del repositorio. Solo valida al ejecutar desde código fuente."""

CARPETA_SESIONES = carpeta_datos_usuario() / "sesiones"
"""Carpeta donde se sugieren y guardan las sesiones JSON."""

CARPETA_REPORTES = carpeta_datos_usuario() / "reportes_generados"
"""Carpeta donde se sugieren y guardan reportes y exportables."""

CARPETA_DOCS = RAIZ_PROYECTO / "docs"
"""Carpeta de documentación técnica y académica (solo en desarrollo)."""

VERSION = version_aplicacion()
"""Versión de la aplicación leída desde el archivo ``VERSIÓN``."""
