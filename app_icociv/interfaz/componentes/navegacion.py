"""Navegación lateral y cabecera de SAVIP.

La navegación se separa del formulario de selección: antes competían por la
atención dentro del mismo panel. Puede contraerse a una tira de iconos, y en ese
estado cada entrada conserva su nombre en el tooltip.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.animaciones.transiciones import animar_ancho
from app_icociv.interfaz.tema import tokens


class NavegacionLateral(QFrame):
    """Lista vertical de módulos con estado seleccionado y modo contraído."""

    seleccion_cambiada = Signal(int)
    contraccion_cambiada = Signal(bool)

    def __init__(
        self,
        entradas: list[tuple[str, str, str]],
        parent: QWidget | None = None,
    ) -> None:
        """`entradas` son ternas (clave, texto, descripción para el tooltip)."""
        super().__init__(parent)
        self.setObjectName("navegacion_lateral")
        self.setFixedWidth(tokens.NAVEGACION_ANCHO_EXPANDIDO)

        self._contraida = False
        self._entradas = list(entradas)
        self.botones: list[QPushButton] = []
        # post-r1-metodologia-12-24, 19-08-2026 (Prompt UI 01). Marca si una
        # entrada tiene contenido disponible (p. ej. "Resultados" con una
        # proyección ya calculada), independiente de si está seleccionada.
        self._destacados: list[bool] = []
        # Acciones de archivo y sesión: viven aquí, no en una segunda columna.
        self._acciones: list[tuple[QWidget, str, str]] = []
        self._widgets_solo_expandido: list[QWidget] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # Con poca altura el panel se desplaza en lugar de recortar entradas.
        self._area = QScrollArea()
        self._area.setObjectName("navegacion_scroll")
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenido = QWidget()
        self._area.setWidget(contenido)
        raiz.addWidget(self._area, 1)

        layout = QVBoxLayout(contenido)
        layout.setContentsMargins(
            tokens.ESPACIO_2, tokens.ESPACIO_3, tokens.ESPACIO_2, tokens.ESPACIO_3
        )
        layout.setSpacing(tokens.ESPACIO_1)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        for indice, (_clave, texto, descripcion) in enumerate(self._entradas):
            boton = QPushButton(texto)
            boton.setObjectName("boton_navegacion")
            boton.setCheckable(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setToolTip(descripcion or texto)
            boton.setAccessibleName(texto)
            boton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._grupo.addButton(boton, indice)
            layout.addWidget(boton)
            self.botones.append(boton)
            self._destacados.append(False)

        # Grupo secundario: archivo y sesión, DESPUÉS de la navegación. Arriba
        # competían con los módulos por la primera lectura del panel.
        layout.addSpacing(tokens.ESPACIO_4)
        self.separador = QFrame()
        self.separador.setObjectName("separador_horizontal")
        self.separador.setFixedHeight(1)
        self.separador.setVisible(False)
        layout.addWidget(self.separador)

        self.titulo_acciones = QLabel("Archivo y sesiones")
        self.titulo_acciones.setObjectName("nav_grupo")
        self.titulo_acciones.setVisible(False)
        layout.addSpacing(tokens.ESPACIO_2)
        layout.addWidget(self.titulo_acciones)

        self.zona_acciones = QVBoxLayout()
        self.zona_acciones.setSpacing(tokens.ESPACIO_2)
        layout.addLayout(self.zona_acciones)

        layout.addStretch(1)

        # Pie: mensaje de estado y control de contracción.
        self.zona_pie = QVBoxLayout()
        self.zona_pie.setSpacing(tokens.ESPACIO_2)
        layout.addLayout(self.zona_pie)

        self.boton_contraer = QPushButton("‹  Contraer")
        self.boton_contraer.setObjectName("boton_contraer_navegacion")
        self.boton_contraer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_contraer.setToolTip("Contrae el panel de navegación")
        self.boton_contraer.clicked.connect(self.alternar_contraccion)
        raiz.addWidget(self.boton_contraer)

        self._grupo.idClicked.connect(self.seleccion_cambiada.emit)
        if self.botones:
            self.botones[0].setChecked(True)

    def agregar_accion(
        self,
        widget: QWidget,
        texto_contraido: str = "",
        descripcion: str = "",
    ) -> None:
        """Añade una acción de archivo o sesión sobre las entradas de navegación.

        `texto_contraido` es la marca corta que sustituye al texto cuando el
        panel se contrae; si va vacío, el widget se oculta en ese estado.
        """
        self.zona_acciones.addWidget(widget)
        self.separador.setVisible(True)
        self.titulo_acciones.setVisible(not self._contraida)
        if isinstance(widget, QPushButton):
            original = widget.text()
            self._acciones.append((widget, original, texto_contraido))
            if descripcion:
                widget.setToolTip(descripcion)
        else:
            self._widgets_solo_expandido.append(widget)

    def agregar_al_pie(self, widget: QWidget) -> None:
        """Widget informativo al final del panel; se oculta al contraer."""
        self.zona_pie.addWidget(widget)
        self._widgets_solo_expandido.append(widget)

    def seleccionar(self, indice: int) -> None:
        """Selecciona una entrada y notifica el cambio.

        `setChecked` por sí solo no emite `idClicked`, que Qt reserva a los clics
        del usuario; sin esta emisión los accesos rápidos marcaban la entrada
        pero no llegaban a cambiar de vista.
        """
        if 0 <= indice < len(self.botones) and indice != self.indice_actual():
            self.botones[indice].setChecked(True)
            self.seleccion_cambiada.emit(indice)
        elif 0 <= indice < len(self.botones):
            self.botones[indice].setChecked(True)

    def marcar_seleccion(self, indice: int) -> None:
        """Actualiza solo el estado visual, sin emitir la señal de navegación."""
        if 0 <= indice < len(self.botones):
            self.botones[indice].setChecked(True)

    def establecer_destacado(self, indice: int, destacado: bool) -> None:
        """Marca (o quita) el indicador de "hay contenido disponible" de una
        entrada, sin tocar cuál está seleccionada. Reutiliza el patrón de
        propiedad dinámica + repolish ya usado en CabeceraApp/TarjetaKPI."""
        if not (0 <= indice < len(self.botones)):
            return
        destacado = bool(destacado)
        if self._destacados[indice] == destacado:
            return
        self._destacados[indice] = destacado
        boton = self.botones[indice]
        boton.setProperty("destacado", destacado)
        boton.style().unpolish(boton)
        boton.style().polish(boton)
        self._actualizar_texto_boton(indice)

    def _actualizar_texto_boton(self, indice: int) -> None:
        """Aplica texto y tooltip de una entrada según contracción y destacado.

        El color nunca es la única señal: en modo expandido se añade un
        símbolo textual (●) y el tooltip lo confirma en palabras.
        """
        _clave, texto, descripcion = self._entradas[indice]
        boton = self.botones[indice]
        destacado = self._destacados[indice]
        if self._contraida:
            boton.setText(texto[:1].upper())
            tooltip = f"{texto}. {descripcion}" if descripcion else texto
        else:
            boton.setText(f"{texto} ●" if destacado else texto)
            tooltip = descripcion or texto
        if destacado:
            tooltip = f"{tooltip} (hay resultados disponibles)" if tooltip else "Hay resultados disponibles"
        boton.setToolTip(tooltip)

    def indice_actual(self) -> int:
        return self._grupo.checkedId()

    def esta_contraida(self) -> bool:
        return self._contraida

    def alternar_contraccion(self) -> None:
        self.establecer_contraccion(not self._contraida)

    def establecer_contraccion(self, contraida: bool) -> None:
        """Contrae a tira de iconos o restituye el ancho completo."""
        self._contraida = bool(contraida)
        ancho = (
            tokens.NAVEGACION_ANCHO_CONTRAIDO
            if self._contraida
            else tokens.NAVEGACION_ANCHO_EXPANDIDO
        )
        for indice in range(len(self.botones)):
            self._actualizar_texto_boton(indice)
        # Las acciones de archivo y sesión se contraen con el resto del panel:
        # el texto deja paso a una marca corta y el nombre pasa al tooltip.
        for widget, texto_original, marca in self._acciones:
            if self._contraida:
                widget.setText(marca or texto_original[:1].upper())
                if not widget.toolTip():
                    widget.setToolTip(texto_original)
            else:
                widget.setText(texto_original)
        for widget in self._widgets_solo_expandido:
            widget.setVisible(not self._contraida)
        if self._acciones or self._widgets_solo_expandido:
            self.titulo_acciones.setVisible(not self._contraida)
        self.boton_contraer.setText("›" if self._contraida else "‹  Contraer")
        self.boton_contraer.setToolTip(
            "Expande el panel de navegación" if self._contraida else "Contrae el panel de navegación"
        )
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        animar_ancho(self, ancho, al_terminar=lambda: self.setFixedWidth(ancho))
        self.contraccion_cambiada.emit(self._contraida)


class CabeceraApp(QFrame):
    """Barra superior: identidad, vista actual, estado del archivo y acciones."""

    def __init__(
        self,
        logo: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cabecera_app")
        self.setFixedHeight(tokens.CABECERA_ALTURA)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            tokens.ESPACIO_4, tokens.ESPACIO_2, tokens.ESPACIO_4, tokens.ESPACIO_2
        )
        layout.setSpacing(tokens.ESPACIO_3)

        self.logo = QLabel()
        self.logo.setObjectName("cabecera_logo")
        if logo is not None and not logo.isNull():
            self.logo.setPixmap(logo)
        self.logo.setFixedSize(tokens.ESPACIO_7, tokens.ESPACIO_7)
        self.logo.setScaledContents(True)
        self.logo.setAccessibleName("Logotipo de SAVIP")
        layout.addWidget(self.logo)

        columna = QVBoxLayout()
        columna.setSpacing(0)
        self.titulo = QLabel("SAVIP")
        self.titulo.setObjectName("cabecera_titulo")
        self.titulo.setToolTip("SAVIP — Sistema de Análisis de Variaciones de Precios")
        columna.addWidget(self.titulo)
        self.vista = QLabel("Inicio")
        self.vista.setObjectName("cabecera_vista")
        columna.addWidget(self.vista)
        layout.addLayout(columna)

        layout.addStretch(1)

        self.estado_archivo = QLabel("Sin archivo cargado")
        self.estado_archivo.setObjectName("cabecera_estado")
        self.estado_archivo.setProperty("estado", "vacio")
        layout.addWidget(self.estado_archivo)

        self.contenedor_acciones = QHBoxLayout()
        self.contenedor_acciones.setSpacing(tokens.ESPACIO_2)
        layout.addLayout(self.contenedor_acciones)

    def agregar_accion(self, widget: QWidget) -> None:
        self.contenedor_acciones.addWidget(widget)

    def establecer_vista(self, nombre: str) -> None:
        self.vista.setText(nombre)

    def establecer_estado_archivo(self, texto: str, estado: str = "vacio") -> None:
        """`estado` admite vacio, cargado o advertencia y ajusta el color."""
        self.estado_archivo.setText(texto)
        self.estado_archivo.setProperty("estado", estado)
        self.estado_archivo.setToolTip(texto)
        self.estado_archivo.style().unpolish(self.estado_archivo)
        self.estado_archivo.style().polish(self.estado_archivo)


__all__ = ["CabeceraApp", "NavegacionLateral"]
