"""Nomenclatura institucional visible para tablas y jerarquias ICOCIV."""

from __future__ import annotations

from typing import Any


NOMBRE_SECCION_SELECCION = "Selección de tabla e índices ICOCIV"
NOMBRE_RUTA_JERARQUICA = "Ruta de tabla e índice seleccionado"
ETIQUETA_TABLA_ACTIVA = "Tabla ICOCIV activa"
TEXTO_TABLA_SIN_SELECCION = f"{ETIQUETA_TABLA_ACTIVA}: seleccione un grupo de obra"

NOMBRES_TABLAS: dict[str, str] = {
    "A16": "A16. Índice por agrupaciones de subclases",
    "A16.1": "A16.1 Índice por subclases CPC",
    "A16_1": "A16.1 Índice por subclases CPC",
    "A16.2": "A16.2 Índice por tipologías de obra",
    "A16_2": "A16.2 Índice por tipologías de obra",
    "A16.3": "A16.3 Índice por tipologías de obra y capítulos constructivos",
    "A16_3": "A16.3 Índice por tipologías de obra y capítulos constructivos",
    "A16.4": "A16.4 Índice por grupos de costos",
    "A16_4": "A16.4 Índice por grupos de costos",
    "A16.5": "A16.5 Índice por grupos de costos e insumos",
    "A16_5": "A16.5 Índice por grupos de costos e insumos",
    "A16.6": "A16.6 Índice por agrupaciones de subclases y grupos de costos",
    "A16_6": "A16.6 Índice por agrupaciones de subclases y grupos de costos",
    "A16.7": "A16.7 Índice por agrupaciones de subclases e insumos",
    "A16_7": "A16.7 Índice por agrupaciones de subclases e insumos",
    "A16.8": "A16.8 Índice por subclases CPC y grupos de costos",
    "A16_8": "A16.8 Índice por subclases CPC y grupos de costos",
    "A16.9": "A16.9 Índice por subclases CPC e insumos",
    "A16_9": "A16.9 Índice por subclases CPC e insumos",
    "A16.10": "A16.10 Índice por tipologías de obra y grupos de costos",
    "A16_10": "A16.10 Índice por tipologías de obra y grupos de costos",
    "A16.11": "A16.11 Índice por tipologías de obra e insumos",
    "A16_11": "A16.11 Índice por tipologías de obra e insumos",
    "A16.12": "A16.12 Índice por tipologías de obra, capítulos y grupos de costos",
    "A16_12": "A16.12 Índice por tipologías de obra, capítulos y grupos de costos",
    "A16.13": "A16.13 Índice por tipologías de obra, capítulos e insumos",
    "A16_13": "A16.13 Índice por tipologías de obra, capítulos e insumos",
    "T_16": "A16. Índice por agrupaciones de subclases",
    "T_16_1": "A16.1 Índice por subclases CPC",
    "T_16_2": "A16.2 Índice por tipologías de obra",
    "T_16_3": "A16.3 Índice por tipologías de obra y capítulos constructivos",
    "T_16_6": "A16.6 Índice por agrupaciones de subclases y grupos de costos",
    "T_16_7": "A16.7 Índice por agrupaciones de subclases e insumos",
    "T_16_8": "A16.8 Índice por subclases CPC y grupos de costos",
    "T_16_9": "A16.9 Índice por subclases CPC e insumos",
    "T_16_10": "A16.10 Índice por tipologías de obra y grupos de costos",
    "T_16_11": "A16.11 Índice por tipologías de obra e insumos",
    "T_16_12": "A16.12 Índice por tipologías de obra, capítulos y grupos de costos",
    "T_16_13": "A16.13 Índice por tipologías de obra, capítulos e insumos",
}

NOMBRES_NIVELES: dict[str, str] = {
    "grupo_obra": "Grupo de obra",
    "subclase_cpc": "Subclase CPC",
    "tipologia_obra": "Tipología de obra",
    "capitulo_constructivo": "Capítulo constructivo",
    "grupo_costos": "Grupo de costos",
    "insumo": "Insumo",
}

TEXTOS_CHECKBOXES: dict[str, str] = {
    "t16_costos": "Costos/Insumos asociados",
    "subclase_costos": "Costos/Insumos subclase",
    "tipologia_costos": "Costos/Insumos tipología",
    "capitulo_costos": "Costos/Insumos capítulo",
}


def nombre_tabla_icociv(clave_tabla: str | None) -> str:
    """Devuelve el nombre visible normalizado de una tabla ICOCIV."""
    if not clave_tabla:
        return ""
    return NOMBRES_TABLAS.get(str(clave_tabla), str(clave_tabla))


def nombre_nivel(clave_nivel: str) -> str:
    """Devuelve el nombre visible normalizado de un nivel jerárquico."""
    return NOMBRES_NIVELES.get(clave_nivel, clave_nivel)


def texto_checkbox(clave: str) -> str:
    """Devuelve texto visible normalizado para opciones de navegacion."""
    return TEXTOS_CHECKBOXES.get(clave, clave)


def construir_ruta_con_tabla(
    fuente: str | None,
    ruta_jerarquica: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """
    Agrega la tabla ICOCIV como primer elemento visible de trazabilidad.

    No modifica índices ni filtros; solo normaliza la representación documental.
    """
    ruta = [{"nivel": "Tabla ICOCIV", "valor": nombre_tabla_icociv(fuente)}] if fuente else []
    for item in ruta_jerarquica or []:
        nivel = str(item.get("nivel", "")).strip()
        valor = str(item.get("valor", "")).strip()
        if nivel and valor:
            ruta.append({"nivel": nivel, "valor": valor})
    return ruta


def es_nivel_tabla(nivel: str | None) -> bool:
    """Indica si una fila de ruta corresponde al descriptor de tabla."""
    return str(nivel or "").strip().lower() == "tabla icociv"


def ruta_sin_tabla(
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
) -> list[dict[str, str]]:
    """Devuelve la ruta de selección sin el descriptor de tabla para nombres cortos."""
    if not ruta_jerarquica:
        return []
    if isinstance(ruta_jerarquica, dict):
        return [
            {"nivel": str(k), "valor": str(v)}
            for k, v in ruta_jerarquica.items()
            if v not in (None, "") and not es_nivel_tabla(str(k))
        ]
    return [
        item
        for item in ruta_jerarquica
        if not es_nivel_tabla(item.get("nivel") or item.get("etiqueta") or item.get("campo"))
    ]


def fuente_visible_desde_resultado(resultado: dict[str, Any]) -> str:
    """Obtiene la fuente visible desde un resultado de análisis."""
    return nombre_tabla_icociv(resultado.get("fuente"))
