"""Paleta de SAVIP en temas claro y oscuro.

Derivada de la referencia cromática aportada por el usuario: una rampa teal de
croma 36 que va del negro al casi blanco, sobre un fondo crema cálido. De ahí
salen el teal profundo de las acciones principales, la escala de superficies del
tema oscuro y la arena del tema claro.

La rampa de referencia, de oscuro a claro:

    #000000  #04222A  #073540  #0A4C5C  #0E6E7C  #2A8296  #4A97A8
    #6BAEC0  #8CC8DC  #A9DEF0  #C4EBFA  #DDF3FC  #F2FAFE

`#0E6E7C` es el tono central de la referencia y actúa como color de marca.

Tres decisiones deliberadas:

* El **morado se retiró por completo**. El foco y la selección usan ahora teal
  profundo en claro y blanco suave en oscuro, dentro del mismo tronco cromático.
* El **tema claro** usa un gris azulado muy claro y neutro. El crema de la
  referencia se probó como fondo pero tiraba a amarillo en pantalla; se conserva
  el teal frío de acción y se descarta la calidez del fondo.
* El **tema oscuro** separa el fondo de las tarjetas: fondo negro grafito y
  tarjetas de teal profundo. Cuando ambos compartían el azul verdoso de la
  rampa, la ventana entera se leía como una sola masa de color.
"""

from __future__ import annotations

from app_icociv.interfaz.tema.tokens import (
    OPACIDAD_HOVER,
    OPACIDAD_PRESIONADO,
    OPACIDAD_SUPERFICIE,
    OPACIDAD_SUTIL,
    OPACIDAD_VELO,
)


# Rampa de la referencia, nombrada por posición para poder citarla desde la paleta.
RAMPA = {
    "t00": "#000000",
    "t05": "#04222A",
    "t10": "#073540",
    "t20": "#0A4C5C",
    "t30": "#0E6E7C",  # tono de marca
    "t40": "#2A8296",
    "t50": "#4A97A8",
    "t60": "#6BAEC0",
    "t70": "#8CC8DC",
    "t80": "#A9DEF0",
    "t85": "#C4EBFA",
    "t90": "#DDF3FC",
    "t95": "#F2FAFE",
}
CREMA = "#FAF7F2"  # fondo de la referencia

CLARO: dict[str, str] = {
    # Marca: el teal central de la referencia.
    "principal": RAMPA["t30"],
    "principal_intenso": RAMPA["t20"],
    "principal_suave": RAMPA["t90"],
    "acento_hover": RAMPA["t20"],
    "acento_presionado": "#083F49",
    "secundario": RAMPA["t40"],
    "secundario_suave": RAMPA["t85"],
    "acento": RAMPA["t40"],
    "acento_suave": RAMPA["t90"],
    # Estado, desaturado para convivir con la paleta fría sin estridencias.
    "exito": "#1A6B4F",
    "exito_suave": "#E2F1EB",
    "advertencia": "#8A5709",
    "advertencia_suave": "#FAEEDC",
    "error": "#A33129",
    "error_suave": "#FAE7E4",
    "informacion": RAMPA["t30"],
    "informacion_suave": RAMPA["t90"],
    # Superficies: gris azulado muy claro y neutro. El crema anterior tiraba a
    # amarillo y ensuciaba la lectura; este fondo es luminoso y frío, y sigue
    # separándose de la tarjeta blanca.
    "fondo": "#F4F7F8",
    "fondo_secundario": "#EDF2F4",
    "barra_lateral": "#FFFFFF",
    "superficie": "#FFFFFF",
    "superficie_2": "#F1F5F6",
    "superficie_3": "#E7EEF0",
    "superficie_inversa": RAMPA["t05"],
    # Texto: azul muy oscuro, no gris lavado.
    "texto": "#0F2128",
    "texto_secundario": "#4A6068",
    "texto_terciario": "#6A8288",
    "texto_sobre_principal": "#FFFFFF",
    "texto_inverso": RAMPA["t95"],
    "texto_deshabilitado": "#95A6AB",
    # Bordes: azul grisáceo claro.
    "borde": "#DBE4E7",
    "borde_control": "#C2D0D4",
    "borde_fuerte": "#9FB2B7",
    "deshabilitado": "#E6ECEE",
    # Datos y gráfica
    "grafica_fondo": "#FFFFFF",
    "grafica_rejilla": "#E4EBED",
    "serie_historica": RAMPA["t30"],
    "serie_ajuste": "#8FA2A7",
    "serie_proyeccion": RAMPA["t40"],
    "banda_intervalo": RAMPA["t40"],
    "marca_calendario": "#8A5709",
    "marca_atipico": "#A33129",
    # Interacción
    "superficie_formulario": "#FFFFFF",
    "campo": "#F5F8F9",
    "campo_hover": "#FFFFFF",
    "seleccion": RAMPA["t85"],
    "navegacion_seleccionada": RAMPA["t90"],
    "navegacion_hover": "#EDF3F5",
    # Foco en claro: teal profundo, bien visible sobre superficies claras.
    "foco": RAMPA["t20"],
    "sombra": "#12252B",
}

OSCURO: dict[str, str] = {
    # Marca: los tonos claros de la rampa sostienen el contraste sobre el fondo.
    "principal": RAMPA["t60"],
    "principal_intenso": RAMPA["t70"],
    "principal_suave": "#0B3039",
    "acento_hover": RAMPA["t70"],
    "acento_presionado": RAMPA["t80"],
    "secundario": RAMPA["t50"],
    "secundario_suave": "#0A2A33",
    "acento": RAMPA["t70"],
    "acento_suave": "#0B3039",
    # Estado
    "exito": "#4CC397",
    "exito_suave": "#0C2620",
    "advertencia": "#E0A54B",
    "advertencia_suave": "#291F12",
    "error": "#ED8177",
    "error_suave": "#2A1A18",
    "informacion": RAMPA["t60"],
    "informacion_suave": "#0B3039",
    # Superficies: el fondo pasa a negro grafito para que las tarjetas de teal
    # profundo se despeguen. Antes fondo y tarjeta compartían el mismo azul
    # verdoso y toda la ventana se leía como una sola masa de color.
    "fondo": "#0B0E10",
    "fondo_secundario": "#101416",
    "barra_lateral": "#12181B",
    "superficie": "#072C34",
    "superficie_2": "#0A353F",
    "superficie_3": "#0E404C",
    "superficie_inversa": RAMPA["t95"],
    # Texto: blanco suave, nunca blanco puro.
    "texto": "#E4EDEF",
    "texto_secundario": "#A3BAC0",
    "texto_terciario": "#7C959C",
    "texto_sobre_principal": "#06222A",
    "texto_inverso": RAMPA["t05"],
    "texto_deshabilitado": "#5F787F",
    # Bordes: azul grisáceo de contraste moderado.
    "borde": "#1C3840",
    "borde_control": "#26505C",
    "borde_fuerte": "#3B7183",
    "deshabilitado": "#0C1417",
    # Datos y gráfica
    "grafica_fondo": "#072C34",
    "grafica_rejilla": "#16414C",
    "serie_historica": RAMPA["t60"],
    "serie_ajuste": "#7C959C",
    "serie_proyeccion": RAMPA["t80"],
    "banda_intervalo": RAMPA["t80"],
    "marca_calendario": "#E0A54B",
    "marca_atipico": "#ED8177",
    # Interacción
    "superficie_formulario": "#0F1A1D",
    "campo": "#070F12",
    "campo_hover": "#0A171B",
    "seleccion": "#12505F",
    "navegacion_seleccionada": "#0E3A46",
    "navegacion_hover": "#182226",
    # Foco en oscuro: blanco suave, el realce más sobrio sobre fondo profundo.
    "foco": RAMPA["t95"],
    "sombra": "#000000",
}

TEMAS_DISPONIBLES = ("claro", "oscuro")


def normalizar_tema(tema: str | None) -> str:
    """Cualquier valor no reconocido cae en el tema claro."""
    return "oscuro" if str(tema).strip().lower() == "oscuro" else "claro"


def paleta(tema: str | None) -> dict[str, str]:
    """Devuelve una copia de la paleta del tema para evitar mutaciones externas."""
    return dict(OSCURO if normalizar_tema(tema) == "oscuro" else CLARO)


def hex_a_rgb(color: str) -> tuple[int, int, int]:
    texto = str(color).strip().lstrip("#")
    if len(texto) == 3:
        texto = "".join(c * 2 for c in texto)
    if len(texto) != 6:
        raise ValueError(f"Color hexadecimal inválido: {color!r}")
    return int(texto[0:2], 16), int(texto[2:4], 16), int(texto[4:6], 16)


def rgba(color: str, alfa: float) -> str:
    """Expresa un color con transparencia en la sintaxis que acepta QSS."""
    r, g, b = hex_a_rgb(color)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, float(alfa))):.3f})"


def mezclar(color_a: str, color_b: str, proporcion: float) -> str:
    """Interpola dos colores; `proporcion` 0 devuelve el primero y 1 el segundo."""
    p = max(0.0, min(1.0, float(proporcion)))
    ra, ga, ba = hex_a_rgb(color_a)
    rb, gb, bb = hex_a_rgb(color_b)
    return "#{:02x}{:02x}{:02x}".format(
        round(ra + (rb - ra) * p),
        round(ga + (gb - ga) * p),
        round(ba + (bb - ba) * p),
    )


def _luminancia_relativa(color: str) -> float:
    """Luminancia relativa según WCAG 2.1."""

    def canal(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = hex_a_rgb(color)
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(color_a: str, color_b: str) -> float:
    """Razón de contraste WCAG entre dos colores (1.0 a 21.0)."""
    la, lb = _luminancia_relativa(color_a), _luminancia_relativa(color_b)
    claro, oscuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (oscuro + 0.05)


def derivados(tema: str | None) -> dict[str, str]:
    """Colores compuestos que dependen de la paleta base.

    Se calculan una sola vez por tema en lugar de repetir expresiones rgba() por
    toda la hoja de estilos.
    """
    p = paleta(tema)
    return {
        "hover_principal": rgba(p["principal"], OPACIDAD_HOVER),
        "presionado_principal": rgba(p["principal"], OPACIDAD_PRESIONADO),
        "hover_superficie": rgba(p["texto"], OPACIDAD_SUTIL),
        "velo_superficie": rgba(p["superficie"], OPACIDAD_VELO),
        "velo_fondo": rgba(p["fondo"], OPACIDAD_VELO),
        "cabecera_fondo": rgba(p["barra_lateral"], 0.94),
        "separador": rgba(p["borde"], 0.85),
        "sombra_suave": rgba(p["sombra"], OPACIDAD_SUPERFICIE),
    }
