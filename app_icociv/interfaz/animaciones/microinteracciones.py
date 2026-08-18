"""Profundidad y realimentación de contacto en los controles de SAVIP.

Qt Widgets no admite `box-shadow`: la elevación se consigue con
QGraphicsDropShadowEffect. Es un efecto costoso, así que se reserva a las
superficies de primer nivel (tarjetas, paneles flotantes, notificaciones) y
nunca se aplica a filas de tabla ni a controles repetidos.

Un widget solo admite un QGraphicsEffect a la vez. Como las animaciones de
opacidad también usan uno, aquí se retira la sombra antes de desvanecer y se
restituye después.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from app_icociv.interfaz.tema import tokens
from app_icociv.interfaz.tema.colores import hex_a_rgb, paleta

_sombras_habilitadas = True


def sombras_habilitadas() -> bool:
    return _sombras_habilitadas


def establecer_sombras(activas: bool) -> None:
    """Interruptor global: permite degradar a bordes en equipos limitados."""
    global _sombras_habilitadas
    _sombras_habilitadas = bool(activas)


def aplicar_elevacion(
    widget: QWidget,
    nivel: tokens.Elevacion = tokens.ELEVACION_1,
    tema: str | None = "claro",
) -> QGraphicsDropShadowEffect | None:
    """Aplica una sombra proyectada al widget y devuelve el efecto creado.

    En tema oscuro la sombra apenas se percibe, porque la elevación se comunica
    aclarando la superficie; se mantiene sutil para no ensuciar el fondo.
    """
    if not _sombras_habilitadas or nivel.opacidad <= 0:
        widget.setGraphicsEffect(None)
        return None

    colores = paleta(tema)
    r, g, b = hex_a_rgb(colores["sombra"])
    efecto = QGraphicsDropShadowEffect(widget)
    efecto.setBlurRadius(nivel.desenfoque)
    efecto.setXOffset(0)
    efecto.setYOffset(nivel.desplazamiento_y)
    efecto.setColor(QColor(r, g, b, int(255 * nivel.opacidad)))
    widget.setGraphicsEffect(efecto)
    return efecto


def retirar_elevacion(widget: QWidget) -> None:
    widget.setGraphicsEffect(None)


class ElevacionHover(QObject):
    """Sube la elevación de una tarjeta mientras el cursor está encima.

    Se instala como filtro de eventos para no obligar a heredar de una clase
    concreta; así funciona con cualquier QWidget existente.
    """

    def __init__(
        self,
        widget: QWidget,
        reposo: tokens.Elevacion = tokens.ELEVACION_1,
        activo: tokens.Elevacion = tokens.ELEVACION_2,
        tema: str | None = "claro",
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._reposo = reposo
        self._activo = activo
        self._tema = tema
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget.installEventFilter(self)
        aplicar_elevacion(widget, reposo, tema)

    def actualizar_tema(self, tema: str | None) -> None:
        self._tema = tema
        aplicar_elevacion(self._widget, self._reposo, tema)

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:  # noqa: N802 - firma Qt
        if objeto is self._widget:
            tipo = evento.type()
            if tipo in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
                aplicar_elevacion(self._widget, self._activo, self._tema)
            elif tipo in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
                aplicar_elevacion(self._widget, self._reposo, self._tema)
        return False


def elevar_tarjetas(
    widgets: list[QWidget],
    nivel: tokens.Elevacion = tokens.ELEVACION_1,
    tema: str | None = "claro",
) -> None:
    """Aplica la misma elevación a un conjunto de superficies."""
    for widget in widgets:
        aplicar_elevacion(widget, nivel, tema)


__all__ = [
    "ElevacionHover",
    "aplicar_elevacion",
    "elevar_tarjetas",
    "establecer_sombras",
    "retirar_elevacion",
    "sombras_habilitadas",
]
