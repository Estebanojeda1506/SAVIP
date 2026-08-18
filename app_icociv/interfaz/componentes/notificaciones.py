"""Avisos no modales de SAVIP.

Sustituye al cuadro de diálogo para todo mensaje que no exija una decisión: el
aviso aparece sobre la esquina inferior derecha del área de contenido, se
desvanece solo y no interrumpe el trabajo. Los diálogos quedan para las
confirmaciones reales.

Los errores muestran un texto comprensible y guardan el detalle técnico en el
tooltip, de modo que siga disponible para diagnóstico sin invadir la lectura.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.animaciones.microinteracciones import aplicar_elevacion
from app_icociv.interfaz.animaciones.transiciones import (
    deslizar_a,
    desvanecer_salida,
    movimiento_reducido,
)
from app_icociv.interfaz.tema import tokens

NIVELES = ("informacion", "exito", "advertencia", "error")

_SIMBOLOS = {
    "informacion": "i",
    "exito": "OK",
    "advertencia": "!",
    "error": "×",
}


class Notificacion(QFrame):
    """Aviso individual con título, detalle opcional y cierre manual."""

    def __init__(
        self,
        titulo: str,
        detalle: str = "",
        nivel: str = "informacion",
        tema: str | None = "claro",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("notificacion")
        nivel_valido = nivel if nivel in NIVELES else "informacion"
        self.setProperty("nivel", nivel_valido)
        self.setMaximumWidth(tokens.ANCHO_MAXIMO_NOTIFICACION)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            tokens.ESPACIO_3, tokens.ESPACIO_3, tokens.ESPACIO_2, tokens.ESPACIO_3
        )
        layout.setSpacing(tokens.ESPACIO_3)

        simbolo = QLabel(_SIMBOLOS[nivel_valido])
        simbolo.setObjectName("notificacion_titulo")
        simbolo.setFixedWidth(tokens.LADO_ICONO)
        simbolo.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(simbolo)

        columna = QVBoxLayout()
        columna.setSpacing(tokens.ESPACIO_1)
        self.etiqueta_titulo = QLabel(titulo)
        self.etiqueta_titulo.setObjectName("notificacion_titulo")
        self.etiqueta_titulo.setWordWrap(True)
        columna.addWidget(self.etiqueta_titulo)
        if detalle:
            self.etiqueta_detalle = QLabel(detalle)
            self.etiqueta_detalle.setObjectName("notificacion_detalle")
            self.etiqueta_detalle.setWordWrap(True)
            columna.addWidget(self.etiqueta_detalle)
        layout.addLayout(columna, 1)

        self.boton_cerrar = QPushButton("×")
        self.boton_cerrar.setObjectName("notificacion_cerrar")
        self.boton_cerrar.setFixedSize(tokens.ESPACIO_6, tokens.ESPACIO_6)
        self.boton_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_cerrar.setToolTip("Cerrar aviso")
        layout.addWidget(self.boton_cerrar, 0, Qt.AlignmentFlag.AlignTop)

        # Lectores de pantalla: el aviso se anuncia completo.
        self.setAccessibleName(f"{nivel_valido}: {titulo}")
        if detalle:
            self.setAccessibleDescription(detalle)
        aplicar_elevacion(self, tokens.ELEVACION_2, tema)


class GestorNotificaciones(QObject):
    """Coloca y retira los avisos dentro de un contenedor.

    Los apila desde la esquina inferior derecha del área de contenido y limita
    cuántos se ven a la vez: una cascada de avisos superpuestos es peor que no
    avisar.
    """

    MAXIMO_VISIBLES = 3

    def __init__(self, contenedor: QWidget, tema: str | None = "claro") -> None:
        super().__init__(contenedor)
        self._contenedor = contenedor
        self._tema = tema
        self._activas: list[Notificacion] = []

    def actualizar_tema(self, tema: str | None) -> None:
        self._tema = tema
        for aviso in self._activas:
            aplicar_elevacion(aviso, tokens.ELEVACION_2, tema)

    def mostrar(
        self,
        titulo: str,
        detalle: str = "",
        nivel: str = "informacion",
        permanencia: int = tokens.PERMANENCIA_NOTIFICACION,
    ) -> Notificacion:
        """Muestra un aviso y programa su retirada."""
        aviso = Notificacion(titulo, detalle, nivel, self._tema, self._contenedor)
        aviso.boton_cerrar.clicked.connect(lambda: self.cerrar(aviso))
        self._activas.append(aviso)
        while len(self._activas) > self.MAXIMO_VISIBLES:
            self.cerrar(self._activas[0])

        aviso.adjustSize()
        aviso.show()
        self._reubicar(entrante=aviso)

        # Los errores permanecen hasta que el usuario los cierra.
        if permanencia > 0 and nivel != "error":
            QTimer.singleShot(int(permanencia), lambda: self.cerrar(aviso))
        return aviso

    def informacion(self, titulo: str, detalle: str = "") -> Notificacion:
        return self.mostrar(titulo, detalle, "informacion")

    def exito(self, titulo: str, detalle: str = "") -> Notificacion:
        return self.mostrar(titulo, detalle, "exito")

    def advertencia(self, titulo: str, detalle: str = "") -> Notificacion:
        return self.mostrar(titulo, detalle, "advertencia")

    def error(self, titulo: str, detalle: str = "") -> Notificacion:
        return self.mostrar(titulo, detalle, "error", permanencia=0)

    def cerrar(self, aviso: Notificacion) -> None:
        if aviso not in self._activas:
            return
        self._activas.remove(aviso)
        desvanecer_salida(aviso, al_terminar=aviso.deleteLater)
        self._reubicar()

    def cerrar_todas(self) -> None:
        for aviso in list(self._activas):
            self.cerrar(aviso)

    def reposicionar(self) -> None:
        """Se llama al redimensionar la ventana."""
        self._reubicar()

    def _reubicar(self, entrante: Notificacion | None = None) -> None:
        margen = tokens.ESPACIO_5
        ancho_contenedor = self._contenedor.width()
        alto_contenedor = self._contenedor.height()
        ancho_aviso = min(tokens.ANCHO_MAXIMO_NOTIFICACION, max(240, ancho_contenedor - 2 * margen))
        y = alto_contenedor - margen
        for aviso in reversed(self._activas):
            # El ancho se fija antes de medir: si no, `adjustSize` calcula la
            # altura sobre una línea única y el texto ajustado se recorta abajo.
            aviso.setFixedWidth(ancho_aviso)
            aviso.adjustSize()
            aviso.setFixedHeight(aviso.sizeHint().height())
            y -= aviso.height()
            x = ancho_contenedor - aviso.width() - margen
            if aviso is entrante and not movimiento_reducido():
                # Entra deslizándose desde fuera del borde derecho.
                aviso.move(ancho_contenedor, y)
                deslizar_a(aviso, x, y)
            else:
                aviso.move(x, y)
            aviso.raise_()
            y -= tokens.ESPACIO_2


__all__ = ["GestorNotificaciones", "Notificacion", "NIVELES"]
