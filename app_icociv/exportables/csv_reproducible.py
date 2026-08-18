"""Exportación CSV de resultados reproducibles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app_icociv.reportes.generador_reportes import (
    construir_dataframe_reproducibilidad,
    generar_csv_reproducibilidad,
)


def construir_csv_reproducible(
    ruta_salida: str | Path,
    serie_df: Any,
    resultado_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None = None,
) -> Path:
    """
    Guarda un CSV reproducible a partir de un resultado de proyección.

    El cálculo de columnas reproducibles permanece en el módulo de reportes
    para evitar duplicación. Este adaptador existe para que las exportaciones
    tengan una ubicación funcional clara dentro de ``app_icociv/exportables``.
    """
    return Path(
        generar_csv_reproducibilidad(
            ruta_salida,
            serie_df,
            resultado_proyeccion,
            ruta_jerarquica,
        )
    )


__all__ = ["construir_csv_reproducible", "construir_dataframe_reproducibilidad"]
