"""Pantalla de inicio de SAVIP.

Da contexto antes de trabajar: qué archivo hay cargado, hasta qué periodo llega,
qué serie está seleccionada y qué se puede hacer a continuación. La franja
superior dibuja la propia serie cargada como identidad visual, de modo que el
adorno lo generan los datos del usuario y no una imagen prestada.
"""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.animaciones.microinteracciones import aplicar_elevacion
from app_icociv.interfaz.animaciones.transiciones import entrada_escalonada
from app_icociv.interfaz.tema import tokens
from app_icociv.interfaz.tema.colores import hex_a_rgb, paleta


class FranjaSerie(QFrame):
    """Dibuja la serie cargada como trazo de identidad; vacía no ocupa espacio."""

    def __init__(self, tema: str | None = "claro", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inicio_franja")
        self._valores: list[float] = []
        self._tema = tema
        self.setMinimumHeight(72)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def establecer_serie(self, valores: Sequence[float] | None) -> None:
        self._valores = [float(v) for v in (valores or []) if v == v]
        self.setVisible(len(self._valores) >= 2)
        self.update()

    def actualizar_tema(self, tema: str | None) -> None:
        self._tema = tema
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - firma Qt
        if len(self._valores) < 2:
            return
        colores = paleta(self._tema)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        ancho, alto = self.width(), self.height()
        margen = tokens.ESPACIO_2
        minimo, maximo = min(self._valores), max(self._valores)
        rango = (maximo - minimo) or 1.0
        paso = ancho / max(1, len(self._valores) - 1)

        puntos = [
            QPointF(
                i * paso,
                alto - margen - ((v - minimo) / rango) * (alto - 2 * margen),
            )
            for i, v in enumerate(self._valores)
        ]

        # Relleno degradado bajo la curva: sugiere volumen sin competir con el texto.
        r, g, b = hex_a_rgb(colores["principal"])
        relleno = QPainterPath()
        relleno.moveTo(puntos[0].x(), alto)
        for punto in puntos:
            relleno.lineTo(punto)
        relleno.lineTo(puntos[-1].x(), alto)
        relleno.closeSubpath()
        degradado = QLinearGradient(0, 0, 0, alto)
        degradado.setColorAt(0.0, QColor(r, g, b, 46))
        degradado.setColorAt(1.0, QColor(r, g, b, 0))
        pintor.fillPath(relleno, degradado)

        trazo = QPainterPath()
        trazo.moveTo(puntos[0])
        for punto in puntos[1:]:
            trazo.lineTo(punto)
        pintor.setPen(QPen(QColor(r, g, b, 210), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pintor.drawPath(trazo)
        pintor.end()


class TarjetaDato(QFrame):
    """Par etiqueta/valor compacto para el resumen de inicio."""

    def __init__(self, etiqueta: str, valor: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inicio_tarjeta_dato")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            tokens.ESPACIO_3, tokens.ESPACIO_2, tokens.ESPACIO_3, tokens.ESPACIO_2
        )
        layout.setSpacing(tokens.ESPACIO_1)
        self.etiqueta = QLabel(etiqueta)
        self.etiqueta.setObjectName("inicio_dato_etiqueta")
        layout.addWidget(self.etiqueta)
        self.valor = QLabel(valor)
        self.valor.setObjectName("inicio_dato_valor")
        self.valor.setWordWrap(True)
        # Dos líneas de alto fijo: sin esto las tarjetas de la fila quedan
        # desiguales según lo largo que sea cada valor.
        self.valor.setMinimumHeight(40)
        self.valor.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.valor)

    def establecer(self, valor: str, detalle: str = "") -> None:
        self.valor.setText(str(valor))
        if detalle:
            self.setToolTip(detalle)


class PantallaInicio(QWidget):
    """Vista de bienvenida con estado del análisis y accesos rápidos."""

    def __init__(
        self,
        version: str = "",
        tema: str | None = "claro",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tema = tema

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(
            tokens.ESPACIO_6, tokens.ESPACIO_6, tokens.ESPACIO_6, tokens.ESPACIO_6
        )
        raiz.setSpacing(tokens.ESPACIO_4)

        self.portada = QFrame()
        self.portada.setObjectName("inicio_portada")
        portada_layout = QVBoxLayout(self.portada)
        portada_layout.setContentsMargins(
            tokens.ESPACIO_7, tokens.ESPACIO_6, tokens.ESPACIO_7, tokens.ESPACIO_4
        )
        portada_layout.setSpacing(tokens.ESPACIO_2)

        self.bienvenida = QLabel("SAVIP")
        self.bienvenida.setObjectName("inicio_bienvenida")
        portada_layout.addWidget(self.bienvenida)

        self.descripcion = QLabel(
            "Sistema de Análisis de Variaciones de Precios. Carga un anexo oficial "
            "del DANE para consultar series ICOCIV, validarlas y proyectarlas."
        )
        self.descripcion.setObjectName("inicio_descripcion")
        self.descripcion.setWordWrap(True)
        portada_layout.addWidget(self.descripcion)

        self.franja = FranjaSerie(tema)
        self.franja.setVisible(False)
        portada_layout.addWidget(self.franja)

        aplicar_elevacion(self.portada, tokens.ELEVACION_1, tema)
        raiz.addWidget(self.portada)

        # Resumen del estado actual.
        rejilla = QGridLayout()
        rejilla.setSpacing(tokens.ESPACIO_3)
        self.datos: dict[str, TarjetaDato] = {}
        definiciones = [
            ("archivo", "Archivo ICOCIV"),
            ("periodo", "Último periodo disponible"),
            ("serie", "Serie seleccionada"),
            ("observaciones", "Observaciones de la serie"),
        ]
        for columna, (clave, etiqueta) in enumerate(definiciones):
            tarjeta = TarjetaDato(etiqueta)
            self.datos[clave] = tarjeta
            rejilla.addWidget(tarjeta, 0, columna)
        raiz.addLayout(rejilla)

        # Accesos rápidos.
        self.fila_acciones = QHBoxLayout()
        self.fila_acciones.setSpacing(tokens.ESPACIO_3)
        raiz.addLayout(self.fila_acciones)

        self.avisos = QLabel("")
        self.avisos.setObjectName("descripcion_seccion")
        self.avisos.setWordWrap(True)
        self.avisos.setVisible(False)
        raiz.addWidget(self.avisos)

        raiz.addStretch(1)

        self.version = QLabel(f"SAVIP {version}" if version else "SAVIP")
        self.version.setObjectName("inicio_version")
        raiz.addWidget(self.version, 0, Qt.AlignmentFlag.AlignRight)

    def agregar_acceso(self, texto: str, descripcion: str, accion: Callable[[], None]) -> QPushButton:
        boton = QPushButton(texto)
        boton.setObjectName("boton_secundario")
        boton.setToolTip(descripcion)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.clicked.connect(accion)
        self.fila_acciones.addWidget(boton)
        return boton

    def finalizar_accesos(self) -> None:
        self.fila_acciones.addStretch(1)

    def actualizar_estado(
        self,
        archivo: str = "",
        periodo: str = "",
        serie: str = "",
        observaciones: str = "",
        valores: Sequence[float] | None = None,
        avisos: str = "",
    ) -> None:
        """Refresca el resumen con lo que haya disponible en la sesión."""
        self.datos["archivo"].establecer(archivo or "Sin archivo cargado", archivo)
        self.datos["periodo"].establecer(periodo or "—")
        self.datos["serie"].establecer(serie or "Sin serie seleccionada", serie)
        self.datos["observaciones"].establecer(observaciones or "—")
        self.franja.establecer_serie(valores)
        self.avisos.setText(avisos)
        self.avisos.setVisible(bool(avisos))

    def animar_entrada(self) -> None:
        """Entrada escalonada de la portada y las tarjetas de resumen."""
        entrada_escalonada([self.portada, *self.datos.values()])

    def actualizar_tema(self, tema: str | None) -> None:
        self._tema = tema
        aplicar_elevacion(self.portada, tokens.ELEVACION_1, tema)
        self.franja.actualizar_tema(tema)


__all__ = ["FranjaSerie", "PantallaInicio", "TarjetaDato"]
