"""Transiciones y microinteracciones de SAVIP.

Qt Widgets no admite transiciones CSS: el movimiento se consigue con
QPropertyAnimation sobre propiedades que Qt puede interpolar (geometría,
opacidad, tamaños). Los cambios de color de hover y pressed se resuelven en la
hoja de estilos y son instantáneos por diseño del framework.

Todas las funciones respetan `movimiento_reducido()`. Con el movimiento
desactivado no se omite el efecto: se aplica directamente su estado final, de
modo que ninguna función dependa de que una animación llegue a ejecutarse.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from app_icociv.interfaz.tema import tokens

_movimiento_reducido = False
# Las animaciones se guardan mientras corren: sin una referencia viva, el
# recolector de basura de Python las destruye a mitad y el widget queda a medio
# camino.
_animaciones_vivas: set[QAbstractAnimation] = set()


def movimiento_reducido() -> bool:
    return _movimiento_reducido


def establecer_movimiento_reducido(activo: bool) -> None:
    """Desactiva o reactiva todo el movimiento de la interfaz."""
    global _movimiento_reducido
    _movimiento_reducido = bool(activo)


def detectar_preferencia_sistema() -> bool:
    """True si el sistema pide reducir animaciones.

    En Windows corresponde a la opción de accesibilidad «Mostrar animaciones».
    Si no puede consultarse, se asume que el movimiento está permitido.
    """
    try:
        import ctypes

        SPI_GETCLIENTAREAANIMATION = 0x1042
        habilitado = ctypes.c_bool(True)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(habilitado), 0
        )
        return bool(ok) and not habilitado.value
    except Exception:
        return False


def aplicar_preferencia_sistema() -> bool:
    """Sincroniza el movimiento con la preferencia del sistema y la devuelve."""
    reducido = detectar_preferencia_sistema()
    establecer_movimiento_reducido(reducido)
    return reducido


def _curva(nombre: str) -> QEasingCurve:
    return QEasingCurve(getattr(QEasingCurve.Type, nombre, QEasingCurve.Type.OutCubic))


def _registrar(animacion: QAbstractAnimation) -> QAbstractAnimation:
    _animaciones_vivas.add(animacion)
    animacion.finished.connect(lambda: _animaciones_vivas.discard(animacion))
    return animacion


def _efecto_opacidad(widget: QWidget) -> QGraphicsOpacityEffect:
    efecto = widget.graphicsEffect()
    if not isinstance(efecto, QGraphicsOpacityEffect):
        efecto = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efecto)
    return efecto


def desvanecer_entrada(
    widget: QWidget,
    duracion: int = tokens.DURACION_ENTRADA,
    retardo: int = 0,
    al_terminar: Callable[[], None] | None = None,
) -> QPropertyAnimation | None:
    """Aparición progresiva del widget."""
    widget.show()
    if movimiento_reducido() or duracion <= 0:
        widget.setGraphicsEffect(None)
        if al_terminar:
            al_terminar()
        return None

    efecto = _efecto_opacidad(widget)
    efecto.setOpacity(0.0)
    animacion = QPropertyAnimation(efecto, b"opacity", widget)
    animacion.setDuration(int(duracion))
    animacion.setStartValue(0.0)
    animacion.setEndValue(1.0)
    animacion.setEasingCurve(_curva(tokens.CURVA_ENTRADA))
    # El efecto se retira al terminar: mantenerlo penaliza el repintado.
    animacion.finished.connect(lambda: widget.setGraphicsEffect(None))
    if al_terminar:
        animacion.finished.connect(al_terminar)
    _registrar(animacion)
    if retardo > 0:
        QTimer.singleShot(int(retardo), lambda: animacion.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped))
    else:
        animacion.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return animacion


def desvanecer_salida(
    widget: QWidget,
    duracion: int = tokens.DURACION_RAPIDA,
    ocultar: bool = True,
    al_terminar: Callable[[], None] | None = None,
) -> QPropertyAnimation | None:
    """Desaparición progresiva del widget."""
    if movimiento_reducido() or duracion <= 0:
        if ocultar:
            widget.hide()
        widget.setGraphicsEffect(None)
        if al_terminar:
            al_terminar()
        return None

    efecto = _efecto_opacidad(widget)
    efecto.setOpacity(1.0)
    animacion = QPropertyAnimation(efecto, b"opacity", widget)
    animacion.setDuration(int(duracion))
    animacion.setStartValue(1.0)
    animacion.setEndValue(0.0)
    animacion.setEasingCurve(_curva(tokens.CURVA_SALIDA))

    def _finalizar() -> None:
        if ocultar:
            widget.hide()
        widget.setGraphicsEffect(None)
        if al_terminar:
            al_terminar()

    animacion.finished.connect(_finalizar)
    _registrar(animacion)
    animacion.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return animacion


def entrada_escalonada(
    widgets: list[QWidget],
    duracion: int = tokens.DURACION_ENTRADA,
    retardo: int = tokens.RETARDO_ESCALONADO,
) -> None:
    """Aparición sucesiva de una lista de widgets, con retardo creciente."""
    for indice, widget in enumerate(widgets):
        desvanecer_entrada(widget, duracion=duracion, retardo=indice * retardo)


def animar_ancho(
    widget: QWidget,
    ancho_final: int,
    duracion: int = tokens.DURACION_PAUSADA,
    al_terminar: Callable[[], None] | None = None,
) -> QParallelAnimationGroup | None:
    """Anima el ancho fijo de un widget, típicamente un panel lateral."""
    if movimiento_reducido() or duracion <= 0:
        widget.setMinimumWidth(ancho_final)
        widget.setMaximumWidth(ancho_final)
        if al_terminar:
            al_terminar()
        return None

    grupo = QParallelAnimationGroup(widget)
    for propiedad in (b"minimumWidth", b"maximumWidth"):
        animacion = QPropertyAnimation(widget, propiedad, widget)
        animacion.setDuration(int(duracion))
        animacion.setStartValue(widget.width())
        animacion.setEndValue(int(ancho_final))
        animacion.setEasingCurve(_curva(tokens.CURVA_ESTANDAR))
        grupo.addAnimation(animacion)
    if al_terminar:
        grupo.finished.connect(al_terminar)
    _registrar(grupo)
    grupo.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return grupo


def animar_altura(
    widget: QWidget,
    altura_final: int,
    duracion: int = tokens.DURACION_NORMAL,
    al_terminar: Callable[[], None] | None = None,
) -> QPropertyAnimation | None:
    """Expande o contrae la altura máxima; sirve para secciones plegables."""
    if movimiento_reducido() or duracion <= 0:
        widget.setMaximumHeight(altura_final)
        if al_terminar:
            al_terminar()
        return None

    animacion = QPropertyAnimation(widget, b"maximumHeight", widget)
    animacion.setDuration(int(duracion))
    animacion.setStartValue(widget.height())
    animacion.setEndValue(int(altura_final))
    animacion.setEasingCurve(_curva(tokens.CURVA_ESTANDAR))
    if al_terminar:
        animacion.finished.connect(al_terminar)
    _registrar(animacion)
    animacion.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return animacion


def deslizar_a(
    widget: QWidget,
    x: int,
    y: int,
    duracion: int = tokens.DURACION_NOTIFICACION,
    curva: str = tokens.CURVA_ENTRADA,
    al_terminar: Callable[[], None] | None = None,
) -> QPropertyAnimation | None:
    """Desplaza un widget hasta una posición dentro de su padre."""
    if movimiento_reducido() or duracion <= 0:
        widget.move(int(x), int(y))
        if al_terminar:
            al_terminar()
        return None

    animacion = QPropertyAnimation(widget, b"pos", widget)
    animacion.setDuration(int(duracion))
    animacion.setStartValue(widget.pos())
    destino = widget.pos()
    destino.setX(int(x))
    destino.setY(int(y))
    animacion.setEndValue(destino)
    animacion.setEasingCurve(_curva(curva))
    if al_terminar:
        animacion.finished.connect(al_terminar)
    _registrar(animacion)
    animacion.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
    return animacion


def transicion_vista(contenedor, indice: int, duracion: int = tokens.DURACION_NORMAL) -> None:
    """Cambia la vista activa de un QStackedWidget con desvanecido de entrada."""
    if contenedor.currentIndex() == indice:
        return
    contenedor.setCurrentIndex(indice)
    actual = contenedor.currentWidget()
    if actual is not None:
        desvanecer_entrada(actual, duracion=duracion)


def detener_todas() -> None:
    """Detiene el movimiento en curso; se usa al cerrar la ventana."""
    for animacion in list(_animaciones_vivas):
        animacion.stop()
    _animaciones_vivas.clear()


__all__ = [
    "animar_altura",
    "animar_ancho",
    "aplicar_preferencia_sistema",
    "deslizar_a",
    "desvanecer_entrada",
    "desvanecer_salida",
    "detectar_preferencia_sistema",
    "detener_todas",
    "entrada_escalonada",
    "establecer_movimiento_reducido",
    "movimiento_reducido",
    "transicion_vista",
]
