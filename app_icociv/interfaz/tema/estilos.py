"""Compone la hoja de estilos de SAVIP resolviendo la plantilla contra los tokens.

Sustituye al mecanismo anterior, que escribía los colores en hexadecimal dentro
del QSS y obtenía el tema oscuro reemplazando cadena por cadena: bastaba con
introducir un color nuevo sin registrarlo para que quedara fijado en claro dentro
del tema oscuro. Aquí la plantilla no puede contener colores literales, y un
marcador sin token correspondiente detiene la composición con un error explícito.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app_icociv.interfaz.tema import tokens
from app_icociv.interfaz.tema.colores import derivados, normalizar_tema, paleta
from app_icociv.interfaz.tema.tipografia import (
    PREFERENCIA_INTERFAZ,
    PREFERENCIA_NUMERICA,
    PREFERENCIA_TITULO,
    pila_css,
)

RUTA_PLANTILLA = Path(__file__).with_name("plantilla.qss")

_PATRON_MARCADOR = re.compile(r"\{([a-z0-9_]+)\}")
# Un color literal en la plantilla rompería el sistema de temas: se detecta.
_PATRON_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _tokens_forma() -> dict[str, object]:
    """Tokens de forma, ritmo y tipografía disponibles para la plantilla."""
    return {
        "espacio_1": tokens.ESPACIO_1,
        "espacio_2": tokens.ESPACIO_2,
        "espacio_3": tokens.ESPACIO_3,
        "espacio_4": tokens.ESPACIO_4,
        "espacio_5": tokens.ESPACIO_5,
        "espacio_6": tokens.ESPACIO_6,
        "espacio_7": tokens.ESPACIO_7,
        "espacio_8": tokens.ESPACIO_8,
        "radio_pequeno": tokens.RADIO_PEQUENO,
        "radio_medio": tokens.RADIO_MEDIO,
        "radio_grande": tokens.RADIO_GRANDE,
        "radio_extra": tokens.RADIO_EXTRA,
        "radio_pildora": tokens.RADIO_PILDORA,
        "altura_control": tokens.ALTURA_CONTROL,
        "altura_control_compacto": tokens.ALTURA_CONTROL_COMPACTO,
        "altura_boton": tokens.ALTURA_BOTON,
        "altura_fila_navegacion": tokens.ALTURA_FILA_NAVEGACION,
        "ancho_minimo_boton": tokens.ANCHO_MINIMO_BOTON,
        "tarjeta_kpi_min_altura": tokens.TARJETA_KPI_MIN_ALTURA,
        "grosor_borde": tokens.GROSOR_BORDE,
        "grosor_borde_foco": tokens.GROSOR_BORDE_FOCO,
        "grosor_indicador_seleccion": tokens.GROSOR_INDICADOR_SELECCION,
        "tamano_display": tokens.TAMANO_DISPLAY,
        "tamano_titulo": tokens.TAMANO_TITULO,
        "tamano_subtitulo": tokens.TAMANO_SUBTITULO,
        "tamano_cuerpo": tokens.TAMANO_CUERPO,
        "tamano_secundario": tokens.TAMANO_SECUNDARIO,
        "tamano_micro": tokens.TAMANO_MICRO,
        "tamano_metrica": tokens.TAMANO_METRICA,
        "peso_normal": tokens.PESO_NORMAL,
        "peso_medio": tokens.PESO_MEDIO,
        "peso_fuerte": tokens.PESO_FUERTE,
        "interlineado_comodo": tokens.INTERLINEADO_COMODO,
        "interlineado_compacto": tokens.INTERLINEADO_COMPACTO,
        "familia_interfaz": pila_css(PREFERENCIA_INTERFAZ),
        "familia_titulo": pila_css(PREFERENCIA_TITULO),
        "familia_numerica": pila_css(PREFERENCIA_NUMERICA),
    }


def contexto_estilos(tema: str | None) -> dict[str, object]:
    """Diccionario completo de sustitución: colores, derivados y forma."""
    contexto: dict[str, object] = {}
    contexto.update(paleta(tema))
    contexto.update(derivados(tema))
    contexto.update(_tokens_forma())
    return contexto


def _leer_plantilla() -> str:
    if not RUTA_PLANTILLA.is_file():
        raise FileNotFoundError(f"No se encontro la plantilla de estilos: {RUTA_PLANTILLA}")
    return RUTA_PLANTILLA.read_text(encoding="utf-8")


def validar_plantilla(texto: str | None = None) -> list[str]:
    """Devuelve los problemas de la plantilla: colores literales o tokens huérfanos.

    Una lista vacía significa que la plantilla es íntegramente tematizable.
    """
    contenido = _leer_plantilla() if texto is None else texto
    problemas: list[str] = []

    sin_comentarios = re.sub(r"/\*.*?\*/", "", contenido, flags=re.DOTALL)
    for literal in sorted(set(_PATRON_HEX.findall(sin_comentarios))):
        problemas.append(f"Color literal en la plantilla: {literal}")

    disponibles = set(contexto_estilos("claro"))
    # El QSS usa {{ }} para llaves literales; se descartan antes de buscar tokens.
    solo_marcadores = sin_comentarios.replace("{{", "\x00").replace("}}", "\x01")
    for marcador in sorted(set(_PATRON_MARCADOR.findall(solo_marcadores))):
        if marcador not in disponibles:
            problemas.append(f"Token sin definir: {{{marcador}}}")
    return problemas


@lru_cache(maxsize=4)
def hoja_estilos(tema: str | None = "claro") -> str:
    """Hoja QSS completa para el tema indicado.

    El resultado se memoriza: cambiar de tema no vuelve a componer la hoja.
    """
    normalizado = normalizar_tema(tema)
    problemas = validar_plantilla()
    if problemas:
        raise ValueError("Plantilla de estilos inválida:\n  - " + "\n  - ".join(problemas))
    plantilla = _leer_plantilla()
    contexto = contexto_estilos(normalizado)
    try:
        return plantilla.format(**contexto)
    except KeyError as exc:  # pragma: no cover - lo cubre validar_plantilla
        raise ValueError(f"Token sin definir en la plantilla: {exc}") from exc


def limpiar_cache() -> None:
    """Recompone las hojas en la próxima llamada (pruebas y recarga en caliente)."""
    hoja_estilos.cache_clear()
