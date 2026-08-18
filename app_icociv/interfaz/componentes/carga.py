"""Indicador de trabajo en curso, superpuesto al área de contenido.

Las operaciones largas ya se ejecutan en un hilo (`TrabajadorFuncion`), de modo
que la ventana nunca se congela; lo que faltaba era decírselo al usuario. Este
velo cubre solo el área de contenido, deja visible la cabecera y describe la
etapa en curso en lugar de mostrar un giro anónimo.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.animaciones.microinteracciones import aplicar_elevacion
from app_icociv.interfaz.animaciones.transiciones import (
    desvanecer_entrada,
    desvanecer_salida,
)
from app_icociv.interfaz.tema import tokens


class VeloCarga(QFrame):
    """Superposición con mensaje de etapa y barra de progreso indeterminada."""

    def __init__(self, contenedor: QWidget, tema: str | None = "claro") -> None:
        super().__init__(contenedor)
        self.setObjectName("velo_carga")
        self._contenedor = contenedor
        self._al_cancelar: Callable[[], None] | None = None
        # Sin esto el velo no bloquearía los clics sobre los controles de abajo.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)

        fila = QHBoxLayout()
        fila.addStretch(1)

        self.panel = QFrame()
        self.panel.setObjectName("panel_carga")
        self.panel.setMinimumWidth(320)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(
            tokens.ESPACIO_6, tokens.ESPACIO_5, tokens.ESPACIO_6, tokens.ESPACIO_5
        )
        panel_layout.setSpacing(tokens.ESPACIO_3)

        self.etiqueta = QLabel("Procesando…")
        self.etiqueta.setObjectName("texto_carga")
        self.etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.etiqueta)

        self.detalle = QLabel("")
        self.detalle.setObjectName("detalle_carga")
        self.detalle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detalle.setWordWrap(True)
        self.detalle.setVisible(False)
        panel_layout.addWidget(self.detalle)

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setRange(0, 0)  # indeterminada
        panel_layout.addWidget(self.barra)

        self.boton_cancelar = QPushButton("Cancelar")
        self.boton_cancelar.setObjectName("boton_secundario")
        self.boton_cancelar.setVisible(False)
        self.boton_cancelar.clicked.connect(self._cancelar)
        panel_layout.addWidget(self.boton_cancelar, 0, Qt.AlignmentFlag.AlignCenter)

        aplicar_elevacion(self.panel, tokens.ELEVACION_3, tema)
        fila.addWidget(self.panel)
        fila.addStretch(1)
        layout.addLayout(fila)
        layout.addStretch(1)
        self.hide()

    def actualizar_tema(self, tema: str | None) -> None:
        aplicar_elevacion(self.panel, tokens.ELEVACION_3, tema)

    def mostrar(
        self,
        mensaje: str = "Procesando…",
        detalle: str = "",
        al_cancelar: Callable[[], None] | None = None,
    ) -> None:
        self.etiqueta.setText(mensaje)
        self.detalle.setText(detalle)
        self.detalle.setVisible(bool(detalle))
        self._al_cancelar = al_cancelar
        self.boton_cancelar.setVisible(al_cancelar is not None)
        self.setGeometry(self._contenedor.rect())
        self.raise_()
        # Lectores de pantalla: se anuncia el cambio de estado.
        self.setAccessibleName(f"Procesando: {mensaje}")
        desvanecer_entrada(self, duracion=tokens.DURACION_RAPIDA)

    def actualizar_mensaje(self, mensaje: str, detalle: str = "") -> None:
        self.etiqueta.setText(mensaje)
        if detalle:
            self.detalle.setText(detalle)
            self.detalle.setVisible(True)

    def establecer_progreso(self, valor: int | None, maximo: int = 100) -> None:
        """`None` deja la barra indeterminada; un valor la vuelve determinada."""
        if valor is None:
            self.barra.setRange(0, 0)
            return
        self.barra.setRange(0, int(maximo))
        self.barra.setValue(int(valor))

    def ocultar(self) -> None:
        self._al_cancelar = None
        desvanecer_salida(self, duracion=tokens.DURACION_RAPIDA)

    def reposicionar(self) -> None:
        if self.isVisible():
            self.setGeometry(self._contenedor.rect())

    def _cancelar(self) -> None:
        if self._al_cancelar is not None:
            self.boton_cancelar.setEnabled(False)
            self.etiqueta.setText("Cancelando…")
            self._al_cancelar()


__all__ = ["VeloCarga"]
