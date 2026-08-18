"""Tokens visuales de SAVIP: la única fuente de verdad de forma, ritmo y movimiento.

Ningún módulo de interfaz debe escribir radios, espaciados, duraciones ni tamaños
como números sueltos. Todo valor visual reutilizable vive aquí, de modo que un
ajuste de escala o de ritmo se haga en un solo lugar.

La escala de espaciado es de base 4: cada paso es un múltiplo, lo que mantiene el
alineamiento vertical entre paneles construidos por distintas partes del código.
"""

from __future__ import annotations

from dataclasses import dataclass


# ==============================
# ESPACIADO (base 4)
# ==============================

ESPACIO_0 = 0
ESPACIO_1 = 4
ESPACIO_2 = 8
ESPACIO_3 = 12
ESPACIO_4 = 16
ESPACIO_5 = 20
ESPACIO_6 = 24
ESPACIO_7 = 32
ESPACIO_8 = 40


# ==============================
# RADIOS
# ==============================
# Superficies grandes llevan radios grandes y controles pequeños radios pequeños:
# un radio uniforme en todo hace que los controles parezcan hinchados.

RADIO_NULO = 0
RADIO_PEQUENO = 6
RADIO_MEDIO = 10
RADIO_GRANDE = 14
RADIO_EXTRA = 20
RADIO_PILDORA = 999


# ==============================
# CONTROLES
# ==============================
# Altura cómoda para puntero y teclado; el mínimo de 40 px evita controles
# diminutos sin llegar al tamaño táctil de una tableta.

ALTURA_CONTROL = 38
ALTURA_CONTROL_COMPACTO = 32
ALTURA_BOTON = 38
ALTURA_BOTON_GRANDE = 44
ALTURA_FILA_NAVEGACION = 42
ANCHO_BOTON_INCREMENTO = 38
ANCHO_MINIMO_BOTON = 96
LADO_ICONO = 20
LADO_ICONO_GRANDE = 24
GROSOR_BORDE = 1
GROSOR_BORDE_FOCO = 2
GROSOR_INDICADOR_SELECCION = 3


# ==============================
# LAYOUT
# ==============================

PANEL_MIN_WIDTH = 330
PANEL_MAX_WIDTH = 430
PANEL_SCROLL_MIN_WIDTH = 350
PANEL_SCROLL_MAX_WIDTH = 450
# El panel aloja también las acciones de archivo y sesión, así que necesita
# ancho para botones con texto, no solo para las entradas de navegación.
NAVEGACION_ANCHO_EXPANDIDO = 244
NAVEGACION_ANCHO_CONTRAIDO = 60
CABECERA_ALTURA = 56
VENTANA_MIN_WIDTH = 1100
VENTANA_MIN_HEIGHT = 700
GRAFICA_MIN_WIDTH = 420
GRAFICA_MIN_HEIGHT = 280
TARJETA_KPI_MIN_ALTURA = 84
ANCHO_MAXIMO_NOTIFICACION = 420


# ==============================
# ELEVACIÓN
# ==============================
# Qt no admite box-shadow en QSS: la sombra se aplica con
# QGraphicsDropShadowEffect. Cada nivel define desenfoque, desplazamiento
# vertical y opacidad del negro. Se reserva a superficies de primer nivel;
# aplicarla a muchos widgets pequeños degrada el rendimiento.


@dataclass(frozen=True)
class Elevacion:
    """Parámetros de una sombra proyectada."""

    desenfoque: int
    desplazamiento_y: int
    opacidad: float

    def como_dict(self) -> dict[str, float]:
        return {
            "desenfoque": self.desenfoque,
            "desplazamiento_y": self.desplazamiento_y,
            "opacidad": self.opacidad,
        }


ELEVACION_0 = Elevacion(0, 0, 0.0)
ELEVACION_1 = Elevacion(12, 2, 0.06)
ELEVACION_2 = Elevacion(22, 4, 0.10)
ELEVACION_3 = Elevacion(34, 8, 0.14)


# ==============================
# MOVIMIENTO
# ==============================
# Duraciones en milisegundos. Las microinteracciones son casi imperceptibles a
# propósito; lo que se percibe como "suave" es la curva, no la duración larga.

DURACION_INSTANTANEA = 0
DURACION_RAPIDA = 140
DURACION_NORMAL = 200
DURACION_PAUSADA = 240
DURACION_ENTRADA = 180
DURACION_NOTIFICACION = 220
RETARDO_ESCALONADO = 40
PERMANENCIA_NOTIFICACION = 4000

# Nombres de curvas de QEasingCurve; se resuelven en animaciones/transiciones.py
# para no importar Qt desde el módulo de tokens.
CURVA_ENTRADA = "OutCubic"
CURVA_SALIDA = "InCubic"
CURVA_ESTANDAR = "InOutCubic"
CURVA_ENFASIS = "OutBack"


# ==============================
# TIPOGRAFÍA
# ==============================
# Tamaños en puntos, tal como los interpreta QSS. La familia se resuelve en
# tipografia.py según lo que ofrezca el sistema.

TAMANO_DISPLAY = 22.0
TAMANO_TITULO = 16.0
TAMANO_SUBTITULO = 12.5
TAMANO_CUERPO = 10.0
TAMANO_CUERPO_FUERTE = 10.0
TAMANO_SECUNDARIO = 9.0
TAMANO_MICRO = 8.5
TAMANO_METRICA = 20.0

PESO_NORMAL = 400
PESO_MEDIO = 600
PESO_FUERTE = 700

INTERLINEADO_COMODO = "140%"
INTERLINEADO_COMPACTO = "125%"


# ==============================
# OPACIDADES
# ==============================
# Se aplican como canal alfa dentro de rgba() sobre una superficie sólida. No
# son translucidez real de widget, que en Qt genera artefactos de repintado.

OPACIDAD_SUTIL = 0.04
OPACIDAD_SUPERFICIE = 0.08
OPACIDAD_HOVER = 0.12
OPACIDAD_PRESIONADO = 0.18
OPACIDAD_VELO = 0.55
OPACIDAD_DESHABILITADO = 0.45


def escalar(valor: int, factor: float) -> int:
    """Escala un token conservando el paso mínimo de 1 px."""
    return max(1, int(round(valor * float(factor))))
