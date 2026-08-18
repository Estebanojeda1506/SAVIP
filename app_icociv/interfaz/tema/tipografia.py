"""Familias tipográficas de SAVIP, resueltas contra lo que ofrezca el sistema.

No se empaquetan fuentes: se elige la primera familia disponible de una lista de
preferencia. En Windows eso significa Segoe UI Variable en 11 y Segoe UI en 10,
sin que la aplicación dependa de ninguna de las dos.
"""

from __future__ import annotations

PREFERENCIA_INTERFAZ = (
    "Segoe UI Variable Text",
    "Segoe UI",
    "Inter",
    "Noto Sans",
    "DejaVu Sans",
    "Arial",
)

PREFERENCIA_TITULO = (
    "Segoe UI Variable Display",
    "Segoe UI Semibold",
    "Segoe UI",
    "Inter",
    "DejaVu Sans",
    "Arial",
)

# Cifras de ancho fijo: imprescindible para que las columnas numéricas de las
# tablas y las métricas no bailen al actualizarse.
PREFERENCIA_NUMERICA = (
    "Segoe UI Variable Text",
    "Segoe UI",
    "Consolas",
    "DejaVu Sans Mono",
    "Courier New",
)

_cache: dict[str, str] = {}


def _familias_disponibles() -> set[str]:
    try:
        from PySide6.QtGui import QFontDatabase

        return set(QFontDatabase.families())
    except Exception:
        return set()


def _resolver(preferencias: tuple[str, ...], clave: str) -> str:
    if clave in _cache:
        return _cache[clave]
    disponibles = _familias_disponibles()
    elegida = next((f for f in preferencias if f in disponibles), preferencias[-1])
    _cache[clave] = elegida
    return elegida


def familia_interfaz() -> str:
    return _resolver(PREFERENCIA_INTERFAZ, "interfaz")


def familia_titulo() -> str:
    return _resolver(PREFERENCIA_TITULO, "titulo")


def familia_numerica() -> str:
    return _resolver(PREFERENCIA_NUMERICA, "numerica")


def pila_css(preferencias: tuple[str, ...]) -> str:
    """Lista de familias entrecomillada para hojas QSS y HTML embebido."""
    return ", ".join(f'"{familia}"' for familia in preferencias)


def limpiar_cache() -> None:
    """Solo para pruebas: fuerza a resolver de nuevo contra el sistema."""
    _cache.clear()
