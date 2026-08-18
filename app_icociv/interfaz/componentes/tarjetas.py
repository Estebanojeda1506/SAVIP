"""Tarjetas de superficie y de métrica para la interfaz de SAVIP.

La tarjeta es la unidad de contenido del rediseño: agrupa información afín sobre
una superficie elevada, en lugar de separarla con bordes. La elevación se aplica
con QGraphicsDropShadowEffect porque QSS no admite sombras.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.animaciones.microinteracciones import (
    ElevacionHover,
    aplicar_elevacion,
)
from app_icociv.interfaz.tema import tokens


class Tarjeta(QFrame):
    """Superficie elevada con título opcional y cuerpo libre."""

    def __init__(
        self,
        titulo: str = "",
        descripcion: str = "",
        tema: str | None = "claro",
        elevacion: tokens.Elevacion = tokens.ELEVACION_1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self._tema = tema
        self._elevacion = elevacion

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            tokens.ESPACIO_4, tokens.ESPACIO_4, tokens.ESPACIO_4, tokens.ESPACIO_4
        )
        self._layout.setSpacing(tokens.ESPACIO_3)

        self.etiqueta_titulo: QLabel | None = None
        self.etiqueta_descripcion: QLabel | None = None
        if titulo:
            self.etiqueta_titulo = QLabel(titulo)
            self.etiqueta_titulo.setObjectName("titulo_seccion")
            self._layout.addWidget(self.etiqueta_titulo)
        if descripcion:
            self.etiqueta_descripcion = QLabel(descripcion)
            self.etiqueta_descripcion.setObjectName("descripcion_seccion")
            self.etiqueta_descripcion.setWordWrap(True)
            self._layout.addWidget(self.etiqueta_descripcion)

        aplicar_elevacion(self, elevacion, tema)

    def cuerpo(self) -> QVBoxLayout:
        """Layout donde el llamador añade su contenido."""
        return self._layout

    def agregar(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def actualizar_tema(self, tema: str | None) -> None:
        self._tema = tema
        aplicar_elevacion(self, self._elevacion, tema)


class TarjetaMetrica(QFrame):
    """Tarjeta de resultado: etiqueta, valor destacado, contexto y estado.

    Sustituye a la tarjeta KPI anterior conservando su comportamiento: es
    activable con ratón y con teclado, y emite `clicked` para abrir el detalle.
    """

    clicked = Signal()

    ESTADOS = {
        "neutro": "",
        "exito": "exito",
        "advertencia": "advertencia",
        "error": "error",
        "informacion": "informacion",
    }

    def __init__(
        self,
        etiqueta: str = "",
        valor: str = "—",
        contexto: str = "",
        accion: str = "",
        tema: str | None = "claro",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("tarjeta_kpi")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(tokens.TARJETA_KPI_MIN_ALTURA)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            tokens.ESPACIO_4, tokens.ESPACIO_3, tokens.ESPACIO_4, tokens.ESPACIO_3
        )
        layout.setSpacing(tokens.ESPACIO_1)

        fila_superior = QHBoxLayout()
        fila_superior.setSpacing(tokens.ESPACIO_2)
        self.etiqueta = QLabel(etiqueta)
        self.etiqueta.setObjectName("etiqueta_kpi")
        fila_superior.addWidget(self.etiqueta)
        fila_superior.addStretch(1)
        self.indicador_estado = QLabel("")
        self.indicador_estado.setObjectName("etiqueta_kpi")
        fila_superior.addWidget(self.indicador_estado)
        layout.addLayout(fila_superior)

        self.valor = QLabel(valor)
        self.valor.setObjectName("valor_kpi")
        self.valor.setWordWrap(True)
        layout.addWidget(self.valor)

        self.contexto = QLabel(contexto)
        self.contexto.setObjectName("etiqueta_kpi")
        self.contexto.setWordWrap(True)
        self.contexto.setVisible(bool(contexto))
        layout.addWidget(self.contexto)

        self.accion = QLabel(accion)
        self.accion.setObjectName("accion_kpi")
        self.accion.setVisible(bool(accion))
        layout.addWidget(self.accion)

        self._hover = ElevacionHover(self, tokens.ELEVACION_1, tokens.ELEVACION_2, tema)

    def actualizar(
        self,
        valor: str | None = None,
        contexto: str | None = None,
        estado: str = "neutro",
        detalle: str | None = None,
    ) -> None:
        """Refresca el contenido y el estado visual de la tarjeta."""
        if valor is not None:
            self.valor.setText(str(valor))
        if contexto is not None:
            self.contexto.setText(str(contexto))
            self.contexto.setVisible(bool(contexto))
        if detalle:
            self.setToolTip(str(detalle))
        self.establecer_estado(estado)

    def establecer_estado(self, estado: str) -> None:
        """El estado se comunica con texto e icono, nunca solo con color."""
        clave = estado if estado in self.ESTADOS else "neutro"
        simbolos = {
            "neutro": "",
            "exito": "OK",
            "advertencia": "!",
            "error": "×",
            "informacion": "i",
        }
        self.indicador_estado.setText(simbolos[clave])
        self.setProperty("estado", self.ESTADOS[clave])
        # Qt no reevalúa la hoja al cambiar una propiedad dinámica.
        self.style().unpolish(self)
        self.style().polish(self)

    def actualizar_tema(self, tema: str | None) -> None:
        self._hover.actualizar_tema(tema)

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - firma Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - firma Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["Tarjeta", "TarjetaMetrica"]
