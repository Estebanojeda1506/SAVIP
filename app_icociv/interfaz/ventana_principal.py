"""Ventana principal PySide6 para la aplicación ICOCIV."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.controladores.controlador_principal import ControladorPrincipal
from app_icociv.interfaz.controladores.trabajadores import TrabajadorFuncion
from app_icociv.interfaz.estilos.constantes_visuales import (
    ALTURA_CHECKBOX,
    ALTURA_CONTROL,
    ANCHO_BOTON_INCREMENTO,
    ESPACIADO_GRUPOS,
    ESPACIADO_PANEL,
    GRAFICA_MIN_HEIGHT,
    GRAFICA_MIN_WIDTH,
    MARGEN_PANEL,
    PANEL_MAX_WIDTH,
    PANEL_MIN_WIDTH,
    PANEL_SCROLL_MAX_WIDTH,
    PANEL_SCROLL_MIN_WIDTH,
    TOOLTIPS_TECNICOS,
    VENTANA_MIN_HEIGHT,
    VENTANA_MIN_WIDTH,
    hoja_estilos,
    normalizar_tema,
    paleta_tema,
)
from app_icociv.interfaz.tema import tokens
from app_icociv.interfaz.animaciones import (
    aplicar_elevacion,
    aplicar_preferencia_sistema,
    detener_todas,
    elevar_tarjetas,
    establecer_movimiento_reducido,
    establecer_sombras,
    movimiento_reducido,
    transicion_vista,
)
from app_icociv.interfaz.componentes import (
    CabeceraApp,
    GestorNotificaciones,
    NavegacionLateral,
    PantallaInicio,
    VeloCarga,
)
from app_icociv.interfaz.efectos import alto_contraste_activo, preparar_ventana
from app_icociv.interfaz.presentacion_resultados import (
    construir_html_detalle_horizonte,
    construir_html_explicacion_tarjeta,
    construir_html_resultados,
)
from app_icociv.interfaz.widgets.modelo_tabla import ModeloTablaPandas
from app_icociv.interfaz.widgets.empalme_iccp_icociv import WidgetEmpalmeICCPICOCIV
from app_icociv.interfaz.widgets.proyecciones_icociv import WidgetProyeccionesICOCIV
from app_icociv.persistencia.gestor_sesiones import (
    cargar_sesion,
    generar_nombre_sesion,
    guardar_sesion,
)
from app_icociv.interfaz.widgets.dialogo_informe import pedir_configuracion
from app_icociv.reportes.generador_reportes import (
    generar_csv_reproducibilidad,
    generar_nombre_reproducibilidad_csv,
    generar_reporte_pdf,
    generar_reporte_proyeccion,
)
from app_icociv.reportes.modelo import nombre_archivo_informe
from app_icociv.utilidades.utilidades import ANIO_BASE, t_a_periodo
from app_icociv.utilidades.nomenclatura_icociv import (
    ETIQUETA_TABLA_ACTIVA,
    NOMBRE_SECCION_SELECCION,
    TEXTO_TABLA_SIN_SELECCION,
    nombre_nivel,
    nombre_tabla_icociv,
    texto_checkbox,
)
from app_icociv.config.rutas import (
    CARPETA_REPORTES,
    CARPETA_SESIONES,
    VERSION,
    asegurar_carpeta,
    carpeta_logs,
    es_ejecutable_congelado,
    ruta_recurso,
)
from app_icociv.interfaz.widgets.controles import ComboBoxSinRueda, SpinEnteroSinRueda
from app_icociv.interfaz.widgets.visor_grafica import (
    VisorGraficaDialog,
    configurar_ejes_dinamicos,
)


class TarjetaInteractiva(QFrame):
    """Tarjeta KPI activable con mouse o teclado."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("tarjeta_kpi")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - firma Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - firma Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def periodo_a_iso(periodo: Any) -> str:
    """Convierte etiquetas de periodo a formato visible AAAA-MM."""
    texto = str(periodo).strip().replace("/", "_").replace("-", "_")
    partes = texto.split("_")
    if len(partes) >= 2:
        try:
            return f"{int(partes[0]):04d}-{int(partes[1]):02d}"
        except ValueError:
            return str(periodo).strip()
    return str(periodo).strip()


def _pixmap_logo(lado: int) -> QPixmap | None:
    """Carga el logo de SAVIP escalado a ``lado`` px, conservando proporciones."""
    ruta = ruta_recurso("app_icociv/interfaz/recursos/savip_logo.png")
    if not ruta.is_file():
        return None
    pixmap = QPixmap(str(ruta))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        lado,
        lado,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def icono_savip() -> QIcon | None:
    """Devuelve el icono de la aplicación para ventanas y barra de tareas."""
    ruta = ruta_recurso("app_icociv/interfaz/recursos/savip_icono.png")
    if ruta.is_file():
        icono = QIcon(str(ruta))
        if not icono.isNull():
            return icono
    return None


class VentanaPrincipal(QMainWindow):
    """Interfaz principal ligera basada en Qt Widgets."""

    def __init__(self) -> None:
        super().__init__()
        self.controlador = ControladorPrincipal()
        self.trabajador: TrabajadorFuncion | None = None
        self.usuario_actual = ""
        self.nombre_sesion_actual: str | None = None
        self.sesion_pendiente: dict[str, Any] | None = None
        self.botones_periodo: list[QPushButton] = []
        self.preferencias = QSettings("ICOCIV", "ICOCIV")
        self.tema_actual = normalizar_tema(self.preferencias.value("tema", "oscuro"))
        # Evita ciclos infinitos en la sincronización bidireccional de los
        # parámetros de proyección (horizonte, meses, año y mes).
        self._sincronizando = False
        self.resultado_ui_actual: dict[str, Any] | None = None
        self.detalles_horizonte: dict[int, dict[str, Any]] = {}
        self.horizonte_detalle_actual: int | None = None

        self.setWindowTitle(f"SAVIP — Sistema de Análisis de Variaciones de Precios  ·  v{VERSION}")
        _icono = icono_savip()
        if _icono is not None:
            self.setWindowIcon(_icono)
        self.resize(1500, 900)
        self.setMinimumSize(VENTANA_MIN_WIDTH, VENTANA_MIN_HEIGHT)

        # Preferencias de accesibilidad antes de construir: si el sistema pide
        # reducir movimiento, los componentes nacen ya en su estado final.
        self.movimiento_reducido_sistema = aplicar_preferencia_sistema()
        self.alto_contraste = alto_contraste_activo()
        if self.alto_contraste:
            # En alto contraste manda la legibilidad: sin sombras ni movimiento.
            establecer_sombras(False)
            establecer_movimiento_reducido(True)

        self._crear_acciones()
        self._crear_interfaz()
        self._cargar_estilos()
        self._actualizar_controles_habilitados(False)
        # Material de fondo de la ventana; degrada a opaco si no está disponible.
        self.capacidades_ventana = preparar_ventana(self, self.tema_actual)

    def _crear_acciones(self) -> None:
        menu_archivo = self.menuBar().addMenu("Archivo")
        accion_cargar = menu_archivo.addAction("Cargar Excel")
        accion_cargar.triggered.connect(self.seleccionar_archivo)
        menu_archivo.addSeparator()
        menu_archivo.addAction("Salir", self.close)

        menu_sesion = self.menuBar().addMenu("Sesiones")
        menu_sesion.addAction("Abrir sesión", self.abrir_sesion)
        menu_sesion.addAction("Guardar sesión", self.guardar_sesion_actual)

        menu_reporte = self.menuBar().addMenu("Reportes")
        menu_reporte.addAction("Generar informe DOCX", self.generar_informe)
        menu_reporte.addAction("Generar informe PDF", self.generar_informe_pdf)
        menu_reporte.addAction("Exportar datos reproducibles CSV", self.exportar_reproducibilidad_csv)

        menu_ayuda = self.menuBar().addMenu("Ayuda")
        menu_ayuda.addAction("Acerca de SAVIP", self._mostrar_acerca_de)
        menu_ayuda.addAction("Abrir carpeta de registros", self._abrir_carpeta_logs)

        menu_vista = self.menuBar().addMenu("Vista")
        self.accion_modo_oscuro = menu_vista.addAction("Modo oscuro")
        self.accion_modo_oscuro.setCheckable(True)
        self.accion_modo_oscuro.setChecked(self.tema_actual == "oscuro")
        self.accion_modo_oscuro.triggered.connect(
            lambda activo: self._aplicar_tema("oscuro" if activo else "claro")
        )

        # Interruptor de tema en la barra superior (esquina derecha del menú).
        self.boton_tema_toggle = QToolButton()
        self.boton_tema_toggle.setObjectName("boton_tema")
        self.boton_tema_toggle.setCheckable(True)
        self.boton_tema_toggle.setChecked(self.tema_actual == "oscuro")
        self.boton_tema_toggle.setToolTip("Cambiar entre tema claro y oscuro")
        self._actualizar_texto_toggle_tema()
        self.boton_tema_toggle.clicked.connect(
            lambda: self._aplicar_tema("oscuro" if self.boton_tema_toggle.isChecked() else "claro")
        )
        self.menuBar().setCornerWidget(self.boton_tema_toggle, Qt.Corner.TopRightCorner)

    def _actualizar_texto_toggle_tema(self) -> None:
        oscuro = self.tema_actual == "oscuro"
        self.boton_tema_toggle.setText("🌙  Oscuro" if oscuro else "☀  Claro")

    def _crear_interfaz(self) -> None:
        self.logo_marca = QLabel()
        self.logo_marca.setObjectName("logo_marca")
        self.logo_marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _logo = _pixmap_logo(72)
        if _logo is not None:
            self.logo_marca.setPixmap(_logo)

        titulo = QLabel("SAVIP")
        titulo.setObjectName("titulo_app")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitulo = QLabel("Sistema de Análisis de Variaciones de Precios")
        subtitulo.setObjectName("subtitulo_app")
        subtitulo.setWordWrap(True)
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.etiqueta_archivo = QLabel("Sin archivo cargado")
        self.etiqueta_archivo.setWordWrap(True)
        self.etiqueta_archivo.setToolTip(TOOLTIPS_TECNICOS["archivo"])
        self.etiqueta_estado = QLabel("Seleccione un archivo Excel/.xlsb para comenzar.")
        self.etiqueta_estado.setObjectName("estado")
        self.etiqueta_estado.setWordWrap(True)

        self.boton_cargar = QPushButton("Cargar archivo Excel")
        self.boton_cargar.setToolTip(TOOLTIPS_TECNICOS["archivo"])
        self.boton_cargar.clicked.connect(self.seleccionar_archivo)

        self.combo_grupo = ComboBoxSinRueda()
        self._configurar_combo(self.combo_grupo, TOOLTIPS_TECNICOS["grupo_obra"])
        self.combo_grupo.currentIndexChanged.connect(lambda _: self._reiniciar_desde_nivel2())

        self.chk_t16 = QCheckBox(texto_checkbox("t16_costos"))
        self._configurar_checkbox(self.chk_t16, TOOLTIPS_TECNICOS["costos_globales"])
        self.chk_t16.stateChanged.connect(lambda _: self._reiniciar_desde_nivel2())

        self.chk_t16_1 = QCheckBox(texto_checkbox("subclase_costos"))
        self._configurar_checkbox(self.chk_t16_1, TOOLTIPS_TECNICOS["costos_subclase"])
        self.chk_t16_1.stateChanged.connect(lambda _: self._reiniciar_desde_nivel3())

        self.chk_t16_2 = QCheckBox(texto_checkbox("tipologia_costos"))
        self._configurar_checkbox(self.chk_t16_2, TOOLTIPS_TECNICOS["costos_tipologia"])
        self.chk_t16_2.stateChanged.connect(lambda _: self._reiniciar_desde_nivel4())

        self.chk_t16_3 = QCheckBox(texto_checkbox("capitulo_costos"))
        self._configurar_checkbox(self.chk_t16_3, TOOLTIPS_TECNICOS["costos_capitulo"])
        self.chk_t16_3.stateChanged.connect(lambda _: self._reiniciar_desde_nivel5())

        self.combo_nivel2 = self._crear_combo_nivel(lambda: self._reiniciar_desde_nivel3())
        self.combo_nivel3 = self._crear_combo_nivel(lambda: self._reiniciar_desde_nivel4())
        self.combo_nivel4 = self._crear_combo_nivel(lambda: self._reiniciar_desde_nivel5())
        self.combo_nivel5 = self._crear_combo_nivel(lambda: self._reiniciar_desde_nivel6())
        self.combo_nivel6 = self._crear_combo_nivel(lambda: self._actualizar_jerarquia())

        self.lbl_nivel2 = QLabel("Nivel 2")
        self.lbl_nivel3 = QLabel("Nivel 3")
        self.lbl_nivel4 = QLabel("Nivel 4")
        self.lbl_nivel5 = QLabel("Nivel 5")
        self.lbl_nivel6 = QLabel("Nivel 6")
        self.lbl_tabla_activa = QLabel(TEXTO_TABLA_SIN_SELECCION)
        self.lbl_tabla_activa.setObjectName("tabla_activa")
        self.lbl_tabla_activa.setWordWrap(True)
        self.lbl_ruta_jerarquica = QLabel("Ruta jerárquica: sin selección")
        self.lbl_ruta_jerarquica.setObjectName("ruta_jerarquica")
        self.lbl_ruta_jerarquica.setWordWrap(True)
        self.lbl_ruta_jerarquica.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_ruta_jerarquica.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.scroll_ruta_jerarquica = QScrollArea()
        self.scroll_ruta_jerarquica.setObjectName("ruta_scroll")
        self.scroll_ruta_jerarquica.setWidgetResizable(True)
        self.scroll_ruta_jerarquica.setMaximumHeight(150)
        self.scroll_ruta_jerarquica.setMinimumHeight(72)
        self.scroll_ruta_jerarquica.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_ruta_jerarquica.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_ruta_jerarquica.setWidget(self.lbl_ruta_jerarquica)
        self.scroll_ruta_jerarquica.setToolTip(
            "Ruta jerárquica seleccionada. Use el scroll del recuadro si el texto supera el espacio visible."
        )

        self.spin_anio = SpinEnteroSinRueda()
        self.spin_anio.setRange(2021, 2100)
        self.spin_anio.setValue(2026)
        self.spin_anio.setAccelerated(True)
        self.spin_anio.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_anio.setMinimumHeight(ALTURA_CONTROL)
        self.spin_anio.setToolTip(TOOLTIPS_TECNICOS["anio"])
        self.spin_mes = SpinEnteroSinRueda()
        self.spin_mes.setRange(1, 12)
        self.spin_mes.setValue(6)
        self.spin_mes.setAccelerated(True)
        self.spin_mes.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_mes.setMinimumHeight(ALTURA_CONTROL)
        self.spin_mes.setToolTip(TOOLTIPS_TECNICOS["mes"])
        # Sincronización inversa: la fecha objetivo actualiza el horizonte.
        self.spin_anio.valueChanged.connect(lambda _: self._periodo_objetivo_cambiado())
        self.spin_mes.valueChanged.connect(lambda _: self._periodo_objetivo_cambiado())
        self.control_anio = self._crear_control_incremental(
            self.spin_anio,
            self.spin_anio.stepDown,
            self.spin_anio.stepUp,
        )
        self.control_mes = self._crear_control_incremental(
            self.spin_mes,
            self._disminuir_mes,
            self._aumentar_mes,
        )
        self.combo_horizonte = ComboBoxSinRueda()
        self._configurar_combo(self.combo_horizonte, TOOLTIPS_TECNICOS.get("horizonte", "Horizonte de proyección en meses."))
        for texto, valor in (("1 mes", 1), ("3 meses", 3), ("6 meses", 6), ("12 meses", 12), ("18 meses", 18), ("Personalizado", None)):
            self.combo_horizonte.addItem(texto, valor)
        self.combo_horizonte.currentIndexChanged.connect(lambda _: self._horizonte_predefinido_cambiado())

        self.spin_horizonte_personalizado = SpinEnteroSinRueda()
        self.spin_horizonte_personalizado.setRange(1, 60)
        self.spin_horizonte_personalizado.setValue(18)
        self.spin_horizonte_personalizado.setMinimumHeight(ALTURA_CONTROL)
        self.spin_horizonte_personalizado.setEnabled(False)
        self.spin_horizonte_personalizado.setToolTip(
            "Horizonte personalizado en meses; puede restringirse si la evidencia estadística no lo respalda."
        )
        self.spin_horizonte_personalizado.valueChanged.connect(lambda _: self._meses_personalizados_cambiados())

        self.lbl_horizonte_recomendado = QLabel("Horizonte estadístico: pendiente de análisis")
        self.lbl_horizonte_recomendado.setObjectName("horizonte_recomendado")
        self.lbl_horizonte_recomendado.setWordWrap(True)

        self.boton_ejecutar = QPushButton("Ejecutar proyección")
        self.boton_ejecutar.setToolTip(TOOLTIPS_TECNICOS["ejecutar"])
        self.boton_ejecutar.clicked.connect(self.ejecutar_proyeccion)
        self.boton_guardar_sesion = QPushButton("Guardar sesión")
        self.boton_guardar_sesion.setObjectName("boton_secundario")
        self.boton_guardar_sesion.setToolTip(TOOLTIPS_TECNICOS["sesion"])
        self.boton_guardar_sesion.clicked.connect(self.guardar_sesion_actual)
        self.boton_abrir_sesion = QPushButton("Abrir sesión")
        self.boton_abrir_sesion.setObjectName("boton_secundario")
        self.boton_abrir_sesion.setToolTip(TOOLTIPS_TECNICOS["sesion"])
        self.boton_abrir_sesion.clicked.connect(self.abrir_sesion)
        # Selector de exportación (DOCX / PDF / CSV) para la barra superior derecha.
        self.boton_exportar_informe = QToolButton()
        self.boton_exportar_informe.setObjectName("boton_exportar_informe")
        self.boton_exportar_informe.setText("Generar informe ")
        self.boton_exportar_informe.setToolTip(TOOLTIPS_TECNICOS["reporte"])
        self.boton_exportar_informe.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_exportar = QMenu(self.boton_exportar_informe)
        menu_exportar.addAction("Generar informe DOCX", self.generar_informe)
        menu_exportar.addAction("Generar informe PDF", self.generar_informe_pdf)
        menu_exportar.addAction("Exportar archivo CSV", self.exportar_reproducibilidad_csv)
        self.boton_exportar_informe.setMenu(menu_exportar)

        # La navegación entre módulos se separa del formulario de selección: en
        # el diseño anterior competían por la atención dentro del mismo panel.
        self.navegacion = NavegacionLateral(
            [
                ("inicio", "Inicio", "Resumen del archivo cargado y accesos rápidos"),
                ("resultados", "Resultados", "Panel de análisis, métricas y proyección"),
                ("proyecciones", "Proyecciones ICOCIV", "Calculadora y tablas acumulativas"),
                ("empalme", "Empalme ICCP-ICOCIV", "Actualización de precios por empalme"),
            ]
        )
        self.navegacion.seleccion_cambiada.connect(self._cambiar_seccion)
        # Compatibilidad con el código que aún consulta los botones por índice.
        self.botones_navegacion = self.navegacion.botones
        self.navegacion.setFixedWidth(tokens.NAVEGACION_ANCHO_EXPANDIDO)

        panel = QFrame()
        panel.setObjectName("panel_controles")
        self.panel_lateral = panel
        panel.setMinimumWidth(PANEL_MIN_WIDTH)
        panel.setMaximumWidth(PANEL_MAX_WIDTH)
        layout_panel = QVBoxLayout(panel)
        layout_panel.setContentsMargins(MARGEN_PANEL, MARGEN_PANEL, MARGEN_PANEL, MARGEN_PANEL)
        layout_panel.setSpacing(ESPACIADO_PANEL)
        # La identidad vive en la cabecera superior; las acciones de archivo y
        # sesión pasan al panel de navegación, de modo que no quede una segunda
        # columna vertical dedicada solo a cargar, abrir y guardar.
        self.logo_marca.setVisible(False)
        titulo.setVisible(False)
        subtitulo.setVisible(False)

        self.grupo_archivo = QGroupBox(NOMBRE_SECCION_SELECCION)
        form = QFormLayout(self.grupo_archivo)
        form.setContentsMargins(12, 14, 12, 12)
        form.setSpacing(ESPACIADO_GRUPOS)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(self.lbl_tabla_activa)
        form.addRow(self.scroll_ruta_jerarquica)
        form.addRow(nombre_nivel("grupo_obra"), self.combo_grupo)
        form.addRow(self.chk_t16)
        form.addRow(self.lbl_nivel2, self.combo_nivel2)
        form.addRow(self.chk_t16_1)
        form.addRow(self.lbl_nivel3, self.combo_nivel3)
        form.addRow(self.chk_t16_2)
        form.addRow(self.lbl_nivel4, self.combo_nivel4)
        form.addRow(self.chk_t16_3)
        form.addRow(self.lbl_nivel5, self.combo_nivel5)
        form.addRow(self.lbl_nivel6, self.combo_nivel6)
        # El selector jerárquico ya no vive en el panel lateral: se monta dentro
        # del módulo de Proyecciones ICOCIV más abajo (montar_controles_seleccion).

        self.grupo_parametros = QGroupBox("Parámetros de proyección")
        form_param = QFormLayout(self.grupo_parametros)
        form_param.setContentsMargins(12, 14, 12, 12)
        form_param.setSpacing(ESPACIADO_GRUPOS)
        form_param.addRow("Horizonte", self.combo_horizonte)
        form_param.addRow("Meses personalizados", self.spin_horizonte_personalizado)
        form_param.addRow("Año", self.control_anio)
        form_param.addRow("Mes", self.control_mes)
        form_param.addRow(self.lbl_horizonte_recomendado)

        # Archivo y sesión viven en el panel de navegación, debajo de los
        # módulos: son acciones de apoyo y no deben leerse antes que ellos.
        # Cargar es la acción principal de su grupo; abrir y guardar quedan como
        # secundarias para no competir con la navegación.
        self.boton_abrir_sesion.setObjectName("boton_secundario")
        self.boton_guardar_sesion.setObjectName("boton_secundario")
        self.navegacion.agregar_accion(
            self.boton_cargar, "＋", "Carga un anexo ICOCIV en Excel o XLSB"
        )
        self.navegacion.agregar_accion(
            self.boton_abrir_sesion, "↥", "Abre una sesión guardada"
        )
        self.navegacion.agregar_accion(
            self.boton_guardar_sesion, "↧", "Guarda la sesión actual"
        )
        self.etiqueta_archivo.setObjectName("nav_archivo")
        self.etiqueta_archivo.setWordWrap(True)
        self.navegacion.agregar_accion(self.etiqueta_archivo)
        self.etiqueta_estado.setWordWrap(True)
        self.navegacion.agregar_al_pie(self.etiqueta_estado)
        layout_panel.addStretch()

        panel_scroll = QScrollArea()
        panel_scroll.setObjectName("panel_scroll")
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel_scroll.setMinimumWidth(PANEL_SCROLL_MIN_WIDTH)
        panel_scroll.setMaximumWidth(PANEL_SCROLL_MAX_WIDTH)
        panel_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        panel_scroll.setWidget(panel)
        self.panel_scroll = panel_scroll

        self.texto_resultados = QTextBrowser()
        self.texto_resultados.setReadOnly(True)
        self.texto_resultados.setMinimumHeight(120)
        self.texto_resultados.setOpenLinks(False)
        self.texto_resultados.anchorClicked.connect(self._mostrar_detalle_horizonte)
        self.texto_resultados.setToolTip("")
        self.texto_resultados.viewport().setToolTip("")
        self.texto_resultados.setMouseTracking(False)
        self.texto_resultados.viewport().setMouseTracking(False)
        self.texto_resultados.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.texto_resultados.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.texto_resultados.setObjectName("visor_resultados")

        panel_resultados = QWidget()
        layout_resultados = QVBoxLayout(panel_resultados)
        layout_resultados.setContentsMargins(0, 0, 0, 0)
        layout_resultados.setSpacing(8)
        layout_resultados.addWidget(self.texto_resultados, 1)

        # Modelos de datos para Serie histórica y Fila fuente; se muestran en
        # ventanas emergentes desde los botones bajo las tarjetas.
        self.modelo_serie = ModeloTablaPandas()
        self.modelo_fila = ModeloTablaPandas()

        self.widget_proyecciones = WidgetProyeccionesICOCIV()
        # El selector jerárquico, los parámetros y el botón de ejecución se
        # integran dentro del módulo de proyecciones (antes en el panel lateral).
        self.widget_proyecciones.montar_controles_seleccion(
            self.grupo_archivo, self.grupo_parametros, self.boton_ejecutar
        )
        self.widget_empalme = WidgetEmpalmeICCPICOCIV()
        self.widget_empalme.configurar_proyeccion_icociv(self._ejecutar_proyeccion_para_empalme)

        self.pantalla_inicio = PantallaInicio(VERSION, self.tema_actual)
        self.pantalla_inicio.agregar_acceso(
            "Cargar anexo ICOCIV",
            "Selecciona el archivo Excel o XLSB publicado por el DANE",
            self.seleccionar_archivo,
        )
        self.pantalla_inicio.agregar_acceso(
            "Abrir sesión guardada",
            "Recupera una sesión previa con su selección y resultados",
            self.abrir_sesion,
        )
        self.pantalla_inicio.agregar_acceso(
            "Ir a resultados",
            "Abre el panel de análisis con la serie seleccionada",
            lambda: self._cambiar_seccion(self.INDICE_RESULTADOS),
        )
        self.pantalla_inicio.finalizar_accesos()

        self.tabs_principales = QTabWidget()
        self.tabs_principales.setDocumentMode(True)
        self.tabs_principales.addTab(self.pantalla_inicio, "Inicio")
        self.tabs_principales.addTab(panel_resultados, "Resultados")
        self.tabs_principales.addTab(self.widget_proyecciones, "Proyecciones ICOCIV")
        self.tabs_principales.addTab(self.widget_empalme, "Empalme ICCP-ICOCIV")
        self.tabs_principales.tabBar().hide()
        self.tabs_principales.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        cabecera = QFrame()
        cabecera.setObjectName("dashboard_cabecera")
        self.cabecera_dashboard = cabecera
        layout_cabecera = QHBoxLayout(cabecera)
        layout_cabecera.setContentsMargins(18, 14, 18, 14)
        textos_cabecera = QVBoxLayout()
        titulo_dashboard = QLabel("Panel de análisis ICOCIV")
        titulo_dashboard.setObjectName("titulo_dashboard")
        self.lbl_dashboard_ruta = QLabel("Seleccione una ruta jerárquica para iniciar.")
        self.lbl_dashboard_ruta.setObjectName("ruta_dashboard")
        self.lbl_dashboard_ruta.setWordWrap(True)
        self.lbl_dashboard_estado = QLabel("Sin análisis ejecutado")
        self.lbl_dashboard_estado.setObjectName("estado_dashboard")
        textos_cabecera.addWidget(titulo_dashboard)
        textos_cabecera.addWidget(self.lbl_dashboard_ruta)
        textos_cabecera.addWidget(self.lbl_dashboard_estado)
        layout_cabecera.addLayout(textos_cabecera, 1)
        acciones_cabecera = QHBoxLayout()
        self.acciones_cabecera = acciones_cabecera
        acciones_cabecera.addWidget(self.boton_exportar_informe)
        layout_cabecera.addLayout(acciones_cabecera)

        tarjetas = QFrame()
        tarjetas.setObjectName("panel_tarjetas")
        self.tarjetas_dashboard = tarjetas
        layout_tarjetas = QGridLayout(tarjetas)
        layout_tarjetas.setContentsMargins(0, 0, 0, 0)
        layout_tarjetas.setHorizontalSpacing(10)
        layout_tarjetas.setVerticalSpacing(10)
        self.valores_kpi: dict[str, QLabel] = {}
        self.tarjetas_kpi: dict[str, TarjetaInteractiva] = {}
        for indice, (clave, etiqueta) in enumerate(
            (
                ("indice", "Índice proyectado"),
                ("horizonte", "Horizonte solicitado"),
                ("modelo", "Modelo seleccionado"),
                ("estado", "Estado del horizonte"),
                # P0-C / C2: la tarjeta anunciaba el intervalo del 95 %. Se
                # renombra: un rotulo con ese titulo y «No aplica» debajo se lee
                # como un dato que falta, no como una decision metodologica.
                ("ic95", "Intervalo de predicción"),
                ("maximo", "Máximo recomendado"),
            )
        ):
            tarjeta, valor = self._crear_tarjeta_kpi(etiqueta)
            self.valores_kpi[clave] = valor
            self.tarjetas_kpi[clave] = tarjeta
            tarjeta.clicked.connect(lambda c=clave: self._mostrar_explicacion_tarjeta(c))
            layout_tarjetas.addWidget(tarjeta, indice // 3, indice % 3)

        # Fila de botones con ventanas emergentes, debajo de las tarjetas.
        fila_popups = QFrame()
        fila_popups.setObjectName("fila_popups")
        self.fila_popups = fila_popups
        layout_popups = QHBoxLayout(fila_popups)
        layout_popups.setContentsMargins(0, 0, 0, 0)
        layout_popups.setSpacing(10)
        self.boton_popup_serie = QPushButton("Serie histórica")
        self.boton_popup_serie.setObjectName("boton_secundario")
        self.boton_popup_serie.setToolTip(TOOLTIPS_TECNICOS["serie"])
        self.boton_popup_serie.clicked.connect(self._abrir_popup_serie)
        self.boton_popup_fila = QPushButton("Fila fuente")
        self.boton_popup_fila.setObjectName("boton_secundario")
        self.boton_popup_fila.setToolTip(TOOLTIPS_TECNICOS["fila"])
        self.boton_popup_fila.clicked.connect(self._abrir_popup_fila)
        self.boton_popup_grafica = QPushButton("Gráfica")
        self.boton_popup_grafica.setObjectName("boton_secundario")
        self.boton_popup_grafica.setToolTip(TOOLTIPS_TECNICOS["grafica"])
        self.boton_popup_grafica.clicked.connect(self._abrir_popup_grafica)
        for boton in (self.boton_popup_serie, self.boton_popup_fila, self.boton_popup_grafica):
            boton.setEnabled(False)
            layout_popups.addWidget(boton)
        layout_popups.addStretch()

        dashboard = QFrame()
        dashboard.setObjectName("dashboard_principal")
        layout_dashboard = QVBoxLayout(dashboard)
        layout_dashboard.setContentsMargins(14, 14, 14, 14)
        layout_dashboard.setSpacing(12)
        layout_dashboard.addWidget(cabecera)
        layout_dashboard.addWidget(tarjetas)
        layout_dashboard.addWidget(fila_popups)
        layout_dashboard.addWidget(self.tabs_principales, 1)

        # El panel de archivo y sesión se vació al pasar sus acciones a la
        # navegación: se conserva el objeto por compatibilidad, pero no se monta.
        panel_scroll.setVisible(False)
        self.panel_scroll_lateral = panel_scroll
        self.splitter_principal = None

        # Cabecera propia con identidad, vista activa y estado del archivo.
        self.cabecera_app = CabeceraApp(_pixmap_logo(tokens.ESPACIO_7))
        self.cabecera_app.agregar_accion(self.boton_tema_toggle)

        cuerpo = QWidget()
        layout_cuerpo = QHBoxLayout(cuerpo)
        layout_cuerpo.setContentsMargins(0, 0, 0, 0)
        layout_cuerpo.setSpacing(0)
        layout_cuerpo.addWidget(self.navegacion)
        layout_cuerpo.addWidget(dashboard, 1)

        central = QWidget()
        layout_central = QVBoxLayout(central)
        layout_central.setContentsMargins(0, 0, 0, 0)
        layout_central.setSpacing(0)
        layout_central.addWidget(self.cabecera_app)
        layout_central.addWidget(cuerpo, 1)
        self.setCentralWidget(central)

        # Superposiciones: cubren el área de trabajo sin tapar la cabecera.
        self.velo_carga = VeloCarga(cuerpo, self.tema_actual)
        self.notificaciones = GestorNotificaciones(cuerpo, self.tema_actual)
        self._contenedor_superposiciones = cuerpo

        self._elevar_superficies()
        self._ordenar_tabulacion()
        self._cambiar_seccion(0)
        self._ocultar_niveles()

    def _ordenar_tabulacion(self) -> None:
        """El recorrido con Tab sigue el orden visual del panel, no el de creación."""
        secuencia: list[QWidget] = [
            *self.navegacion.botones,
            self.boton_cargar,
            self.boton_abrir_sesion,
            self.boton_guardar_sesion,
            self.navegacion.boton_contraer,
        ]
        secuencia = [w for w in secuencia if w is not None]
        for anterior, siguiente in zip(secuencia, secuencia[1:]):
            self.setTabOrder(anterior, siguiente)

    @staticmethod
    def _crear_tarjeta_kpi(etiqueta: str) -> tuple[TarjetaInteractiva, QLabel]:
        tarjeta = TarjetaInteractiva()
        tarjeta.setAccessibleName(f"{etiqueta}. Abrir explicación")
        tarjeta.setToolTip("Abrir explicación")
        layout = QVBoxLayout(tarjeta)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        titulo = QLabel(etiqueta)
        titulo.setObjectName("etiqueta_kpi")
        valor = QLabel("—")
        valor.setObjectName("valor_kpi")
        valor.setWordWrap(True)
        accion = QLabel("Ver explicación")
        accion.setObjectName("accion_kpi")
        layout.addWidget(titulo)
        layout.addWidget(valor)
        layout.addWidget(accion)
        return tarjeta, valor

    # Índice de pestaña -> (nombre visible, muestra el panel de selección).
    SECCIONES = (
        ("Inicio", False),
        ("Resultados", True),
        ("Proyecciones ICOCIV", True),
        ("Empalme ICCP-ICOCIV", True),
    )
    INDICE_RESULTADOS = 1

    def _cambiar_seccion(self, indice: int) -> None:
        indice = max(0, min(int(indice), len(self.SECCIONES) - 1))
        transicion_vista(self.tabs_principales, indice)
        nombre, muestra_seleccion = self.SECCIONES[indice]

        # El encabezado de análisis solo aplica a la pestaña de Resultados.
        es_resultados = indice == self.INDICE_RESULTADOS
        for atributo in ("cabecera_dashboard", "tarjetas_dashboard", "fila_popups"):
            if hasattr(self, atributo):
                getattr(self, atributo).setVisible(es_resultados)
        _ = muestra_seleccion  # el panel lateral independiente se retiró
        if hasattr(self, "cabecera_app"):
            self.cabecera_app.establecer_vista(nombre)
        if hasattr(self, "navegacion"):
            self.navegacion.marcar_seleccion(indice)
        if indice == 0 and hasattr(self, "pantalla_inicio"):
            self._actualizar_pantalla_inicio()

    def _elevar_superficies(self) -> None:
        """Aplica la elevación de tarjeta a las superficies de primer nivel."""
        superficies = [
            getattr(self, nombre, None)
            for nombre in ("cabecera_dashboard", "grupo_archivo", "grupo_parametros")
        ]
        elevar_tarjetas(
            [s for s in superficies if s is not None], tokens.ELEVACION_1, self.tema_actual
        )
        for tarjeta in getattr(self, "tarjetas_kpi", {}).values():
            aplicar_elevacion(tarjeta, tokens.ELEVACION_1, self.tema_actual)

    def _actualizar_pantalla_inicio(self) -> None:
        """Vuelca en la portada el estado real de la sesión."""
        if not hasattr(self, "pantalla_inicio"):
            return
        archivo = self.etiqueta_archivo.text() if hasattr(self, "etiqueta_archivo") else ""
        serie_df = getattr(self.controlador, "serie_actual", None)
        periodo = observaciones = ""
        valores: list[float] = []
        if serie_df is not None and getattr(serie_df, "empty", True) is False:
            try:
                periodo = periodo_a_iso(serie_df["Periodo"].iloc[-1])
                observaciones = str(len(serie_df))
                valores = [float(v) for v in serie_df["Indice"].tolist()]
            except Exception:
                periodo, observaciones, valores = "", "", []
        ruta = self.lbl_ruta_jerarquica.text() if hasattr(self, "lbl_ruta_jerarquica") else ""
        if "sin selección" in ruta.lower():
            ruta = ""  # la portada tiene su propio texto para el estado vacío
        self.pantalla_inicio.actualizar_estado(
            archivo=archivo,
            periodo=periodo,
            serie=ruta,
            observaciones=observaciones,
            valores=valores,
        )

    def _actualizar_tarjetas(self, proyeccion: dict[str, Any]) -> None:
        solicitado = proyeccion.get("resultado_horizonte_solicitado") or {}
        info = proyeccion.get("analisis_horizontes_completo") or proyeccion.get("horizonte_info") or {}
        generado = bool(solicitado.get("proyeccion_generada"))
        indice = solicitado.get("indice_proyectado")
        maximo = info.get("horizonte_maximo_recomendado")
        maximo_texto = f"{int(maximo)} meses" if maximo else "No identificado"
        if maximo and info.get("maximo_recomendado_es_limite_observado"):
            maximo_texto += " (dentro de grilla evaluada)"
        self.valores_kpi["indice"].setText(
            self._formatear_metrica(indice) if generado else "No generado"
        )
        self.valores_kpi["horizonte"].setText(
            f"{int(solicitado.get('horizonte_solicitado'))} meses"
            if solicitado.get("horizonte_solicitado")
            else "No disponible"
        )
        self.valores_kpi["modelo"].setText(
            str(solicitado.get("modelo_aplicado") or "No aplica")
        )
        self.valores_kpi["estado"].setText(
            {
                "proyeccion_tecnica": "Proyección técnica",
                "escenario": "Escenario",
                "no_admisible": "No admisible",
            }.get(str(solicitado.get("estado")), "No evaluado")
        )
        # P0-C / C2: el intervalo no se publica. No se formatea la pareja
        # -que ya viaja vacia desde el servicio- ni se deja «No aplica», que
        # sugeriria que el dato no existe para este caso concreto.
        self.valores_kpi["ic95"].setText("No se publica en esta versión")
        self.valores_kpi["maximo"].setText(maximo_texto)

    def _crear_combo_nivel(self, accion_cambio) -> QComboBox:
        combo = ComboBoxSinRueda()
        self._configurar_combo(combo)
        combo.currentIndexChanged.connect(lambda _: accion_cambio())
        return combo

    def _configurar_combo(self, combo: QComboBox, tooltip_base: str | None = None) -> None:
        combo.setProperty("tooltip_base", tooltip_base or "")
        combo.setMinimumHeight(ALTURA_CONTROL)
        combo.setMinimumContentsLength(18)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMaxVisibleItems(18)
        combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        combo.view().setMouseTracking(True)
        combo.view().entered.connect(lambda indice, c=combo: self._actualizar_tooltip_opcion_combo(c, indice))
        combo.currentTextChanged.connect(lambda texto, c=combo: self._actualizar_tooltip_combo(c, texto))
        if tooltip_base:
            combo.setToolTip(tooltip_base)

    def _actualizar_tooltip_opcion_combo(self, combo: QComboBox, indice) -> None:
        texto = str(indice.data() or "")
        if texto:
            combo.view().setToolTip(texto)

    def _actualizar_tooltip_combo(self, combo: QComboBox, texto: str | None = None) -> None:
        base = str(combo.property("tooltip_base") or "")
        texto_actual = texto if texto is not None else combo.currentText()
        if base and texto_actual:
            combo.setToolTip(f"{base}\n\nSelección actual: {texto_actual}")
        else:
            combo.setToolTip(base or texto_actual or "")

    @staticmethod
    def _formatear_metrica(valor: Any, decimales: int = 4) -> str:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return "No aplica"
        return f"{numero:.{decimales}f}" if numero == numero else "No aplica"

    @staticmethod
    def _formatear_porcentaje(valor: Any) -> str:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return "No aplica"
        return f"{numero:.2%}" if numero == numero else "No aplica"

    def _configurar_checkbox(self, checkbox: QCheckBox, tooltip: str) -> None:
        checkbox.setMinimumHeight(ALTURA_CHECKBOX)
        checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        checkbox.setToolTip(tooltip)
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)

    def _crear_control_incremental(self, spin: QSpinBox, accion_menos, accion_mas) -> QWidget:
        contenedor = QWidget()
        layout = QHBoxLayout(contenedor)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        boton_menos = QPushButton("-")
        boton_mas = QPushButton("+")
        for boton in (boton_menos, boton_mas):
            boton.setObjectName("boton_incremento")
            boton.setFixedWidth(ANCHO_BOTON_INCREMENTO)
            boton.setMinimumHeight(ALTURA_CONTROL)
            boton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.botones_periodo.append(boton)

        boton_menos.clicked.connect(accion_menos)
        boton_mas.clicked.connect(accion_mas)
        layout.addWidget(boton_menos)
        layout.addWidget(spin, 1)
        layout.addWidget(boton_mas)
        return contenedor

    def _aumentar_mes(self) -> None:
        if self.spin_mes.value() < 12:
            self.spin_mes.stepUp()
            return
        self.spin_mes.setValue(1)
        if self.spin_anio.value() < self.spin_anio.maximum():
            self.spin_anio.stepUp()

    def _disminuir_mes(self) -> None:
        if self.spin_mes.value() > 1:
            self.spin_mes.stepDown()
            return
        if self.spin_anio.value() > self.spin_anio.minimum():
            self.spin_anio.stepDown()
            self.spin_mes.setValue(12)

    # ------------------------------------------------------------------
    # Sincronización bidireccional de los parámetros de proyección.
    # Fuente de verdad: el horizonte en meses, materializado en la fecha
    # objetivo (año/mes). Los cuatro controles se mantienen coherentes en
    # todo momento; `_sincronizando` evita ciclos infinitos de señales.
    # ------------------------------------------------------------------

    def _ultimo_periodo_serie(self) -> tuple[int, int] | None:
        """Último periodo observado de la serie cargada, como (año, mes)."""
        periodos = getattr(self.controlador, "periodos", None)
        if not periodos:
            return None
        try:
            anio, mes = [int(parte) for parte in str(periodos[-1]).strip().split("_")[:2]]
        except (TypeError, ValueError):
            return None
        return anio, mes

    def _horizonte_desde_controles(self) -> int:
        """Horizonte que indican el desplegable y el spin de meses."""
        valor = self.combo_horizonte.currentData()
        if valor is None:
            return int(self.spin_horizonte_personalizado.value())
        return int(valor)

    def _horizonte_desde_periodo(self) -> int | None:
        """Meses entre el último periodo observado y la fecha objetivo."""
        base = self._ultimo_periodo_serie()
        if base is None:
            return None
        anio_base, mes_base = base
        total_base = anio_base * 12 + (mes_base - 1)
        total_objetivo = int(self.spin_anio.value()) * 12 + (int(self.spin_mes.value()) - 1)
        return total_objetivo - total_base

    def _horizonte_solicitado(self) -> int:
        """Horizonte efectivo que se usa para ejecutar y reportar.

        Se deriva de la fecha objetivo porque es la que se entrega al motor
        estadístico; si aún no hay serie cargada, se usan los controles.
        """
        horizonte = self._horizonte_desde_periodo()
        return self._horizonte_desde_controles() if horizonte is None else horizonte

    # Compatibilidad con llamadas existentes.
    def _horizonte_actual_meses(self) -> int:
        return self._horizonte_solicitado()

    def _horizonte_predefinido_cambiado(self) -> None:
        personalizado = self.combo_horizonte.currentData() is None
        self.spin_horizonte_personalizado.setEnabled(personalizado)
        self._actualizar_tooltip_combo(self.combo_horizonte)
        if self._sincronizando:
            return
        self._sincronizando = True
        try:
            # Un horizonte predefinido también fija los meses personalizados.
            valor = self.combo_horizonte.currentData()
            if valor is not None and 1 <= int(valor) <= self.spin_horizonte_personalizado.maximum():
                self.spin_horizonte_personalizado.setValue(int(valor))
            self._aplicar_horizonte_a_periodo(self._horizonte_desde_controles())
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()

    def _meses_personalizados_cambiados(self) -> None:
        """El spin de meses manda: actualiza fecha objetivo y desplegable."""
        if self._sincronizando:
            return
        self._sincronizando = True
        try:
            horizonte = int(self.spin_horizonte_personalizado.value())
            self._seleccionar_horizonte_en_combo(horizonte)
            self._aplicar_horizonte_a_periodo(horizonte)
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()

    def _periodo_objetivo_cambiado(self) -> None:
        """El usuario editó año o mes: recalcula horizonte y controles."""
        if self._sincronizando:
            return
        horizonte = self._horizonte_desde_periodo()
        if horizonte is None:
            return
        self._sincronizando = True
        try:
            if 1 <= horizonte <= self.spin_horizonte_personalizado.maximum():
                self.spin_horizonte_personalizado.setValue(int(horizonte))
            self._seleccionar_horizonte_en_combo(horizonte)
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()

    def _seleccionar_horizonte_en_combo(self, horizonte: int) -> None:
        """Marca el horizonte predefinido equivalente o 'Personalizado'."""
        indice = self.combo_horizonte.findData(int(horizonte))
        if indice < 0:
            indice = self.combo_horizonte.findData(None)  # Personalizado
        if indice >= 0 and indice != self.combo_horizonte.currentIndex():
            self.combo_horizonte.setCurrentIndex(indice)
        self.spin_horizonte_personalizado.setEnabled(self.combo_horizonte.currentData() is None)
        self._actualizar_tooltip_combo(self.combo_horizonte)

    def _aplicar_horizonte_a_periodo(self, horizonte: int) -> None:
        """Traslada un horizonte en meses a la fecha objetivo (año/mes)."""
        base = self._ultimo_periodo_serie()
        if base is None:
            return
        anio_base, mes_base = base
        total = (anio_base * 12 + (mes_base - 1)) + int(horizonte)
        anio_objetivo, mes_objetivo = total // 12, (total % 12) + 1
        if not (self.spin_anio.minimum() <= anio_objetivo <= self.spin_anio.maximum()):
            return
        self.spin_anio.setValue(int(anio_objetivo))
        self.spin_mes.setValue(int(mes_objetivo))

    def _sincronizar_periodo_desde_horizonte(self) -> None:
        """Recalcula la fecha objetivo al cambiar la serie o cargar archivo."""
        if self._sincronizando:
            return
        self._sincronizando = True
        try:
            self._aplicar_horizonte_a_periodo(self._horizonte_desde_controles())
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()

    def _actualizar_etiqueta_horizonte_pendiente(self) -> None:
        """Mantiene coherente el texto de horizonte estadístico antes del análisis."""
        if not hasattr(self, "lbl_horizonte_recomendado"):
            return
        base = self._ultimo_periodo_serie()
        if base is None:
            self.lbl_horizonte_recomendado.setText("Horizonte estadístico: pendiente de análisis")
            return
        horizonte = self._horizonte_solicitado()
        objetivo = f"{int(self.spin_anio.value()):04d}-{int(self.spin_mes.value()):02d}"
        if horizonte <= 0:
            self.lbl_horizonte_recomendado.setText(
                f"Fecha objetivo inválida ({objetivo}): debe ser posterior a "
                f"{base[0]:04d}-{base[1]:02d}, último periodo observado."
            )
            return
        self.lbl_horizonte_recomendado.setText(
            f"Horizonte estadístico: pendiente de análisis para {horizonte} mes(es) (objetivo {objetivo})."
        )

    def seleccionar_archivo(self) -> None:
        ruta_archivo, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo ICOCIV",
            "",
            "Archivos Excel (*.xlsx *.xlsb)",
        )
        if ruta_archivo:
            self._cargar_archivo(ruta_archivo)

    def _cargar_archivo(self, ruta_archivo: str) -> None:
        self._establecer_ocupado(True, "Cargando archivo Excel...")
        self.trabajador = TrabajadorFuncion(self.controlador.cargar_archivo, ruta_archivo)
        self.trabajador.resultado.connect(self._archivo_cargado)
        self.trabajador.error.connect(self._mostrar_error)
        self.trabajador.finished.connect(lambda: self._establecer_ocupado(False))
        self.trabajador.start()

    def _archivo_cargado(self, resultado: dict[str, Any]) -> None:
        nombre_archivo = Path(resultado["archivo"]).name
        self.etiqueta_archivo.setText(nombre_archivo)
        self.etiqueta_archivo.setToolTip(resultado["archivo"])
        periodos = resultado.get("periodos") or []
        if hasattr(self, "cabecera_app"):
            self.cabecera_app.establecer_estado_archivo(nombre_archivo, "cargado")
        if hasattr(self, "notificaciones"):
            ultimo = periodo_a_iso(periodos[-1]) if periodos else ""
            self.notificaciones.exito(
                "Archivo cargado",
                f"{nombre_archivo} · {len(periodos)} periodos" + (f" · hasta {ultimo}" if ultimo else ""),
            )
        self._llenar_combo(self.combo_grupo, self.controlador.opciones_grupo())
        self._ajustar_periodo_por_defecto(resultado["periodos"])
        self._actualizar_controles_habilitados(True)
        self.widget_empalme.actualizar_icociv(self.controlador.tablas, self.controlador.periodos)
        self._actualizar_jerarquia()
        self.etiqueta_estado.setText("Archivo cargado correctamente.")

        if self.sesion_pendiente:
            self._restaurar_sesion_pendiente()

    def ejecutar_proyeccion(self) -> None:
        seleccion = self._seleccion_actual()
        if seleccion.get("idx_g") is None:
            QMessageBox.warning(self, "Validación", f"Debe seleccionar al menos un {nombre_nivel('grupo_obra').lower()}.")
            return

        # El horizonte efectivo se consolida desde la fecha objetivo mostrada,
        # que ya está sincronizada con el desplegable y los meses personalizados.
        # No se sobrescribe: lo que el usuario ve es lo que se ejecuta.
        base = self._ultimo_periodo_serie()
        horizonte = self._horizonte_solicitado()
        if base is not None and horizonte <= 0:
            QMessageBox.warning(
                self,
                "Validación",
                "La fecha objetivo debe ser posterior al último periodo observado de la serie "
                f"({base[0]:04d}-{base[1]:02d}). Ajuste el año, el mes o el horizonte.",
            )
            return
        maximo = self.spin_horizonte_personalizado.maximum()
        if horizonte > maximo:
            QMessageBox.warning(
                self,
                "Validación",
                f"El horizonte solicitado ({horizonte} meses) supera el máximo operativo "
                f"de {maximo} meses. Seleccione una fecha objetivo más cercana.",
            )
            return

        self._establecer_ocupado(True, "Ejecutando proyección...")
        self.trabajador = TrabajadorFuncion(
            self.controlador.ejecutar_analisis,
            seleccion,
            int(self.spin_anio.value()),
            int(self.spin_mes.value()),
            "manual" if self.combo_horizonte.currentData() is None else "predeterminado",
        )
        self.trabajador.resultado.connect(self._proyeccion_lista)
        self.trabajador.error.connect(self._mostrar_error)
        self.trabajador.finished.connect(lambda: self._establecer_ocupado(False))
        self.trabajador.start()

    def _proyeccion_lista(self, resultado: dict[str, Any], registrar: bool = True) -> None:
        proyeccion = resultado["proyeccion"]
        solicitado = proyeccion.get("resultado_horizonte_solicitado") or {}
        self.resultado_ui_actual = resultado
        evaluaciones = (proyeccion.get("analisis_horizontes_completo") or {}).get("tabla_horizontes") or []
        self.detalles_horizonte = {
            int(item.get("horizonte")): item
            for item in evaluaciones
            if item.get("horizonte") is not None
        }
        self.horizonte_detalle_actual = None
        self.modelo_serie.establecer_dataframe(resultado["serie_df"])
        self.modelo_fila.establecer_dataframe(resultado["fila"])
        for boton in (self.boton_popup_serie, self.boton_popup_fila, self.boton_popup_grafica):
            boton.setEnabled(True)
        self._actualizar_tarjetas(proyeccion)
        self._renderizar_resultados_actuales()
        # Alimenta la calculadora ICOCIV; solo acumula una fila cuando el
        # análisis lo inicia el usuario (registrar=True), no el flujo de empalme.
        self.widget_proyecciones.actualizar_contexto(resultado, registrar=registrar)
        if not proyeccion.get("proyeccion_generada", True):
            self.lbl_horizonte_recomendado.setText(
                f"Horizonte solicitado: {solicitado.get('horizonte_solicitado', 'No disponible')} meses. "
                f"{solicitado.get('razon_principal', 'Proyección no generada.')}"
            )
            self.etiqueta_estado.setText("Proyección no generada para el horizonte solicitado.")
            self.lbl_dashboard_estado.setText("Horizonte no admisible · proyección no generada")
            return

        # H-4, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Ambas
        # etiquetas comparaban `solicitado["estado"]` contra el literal
        # "escenario", que `_estructurar_resultado_horizontes` no produce
        # desde el 08-08-2026 (solo entrega "proyeccion_tecnica" o
        # "no_admisible"): la rama nunca se ejecutaba.
        horizonte_info = proyeccion.get("horizonte_info", {})
        self.lbl_horizonte_recomendado.setText(f"Horizonte estadístico: {horizonte_info.get('mensaje', '')}")
        self.etiqueta_estado.setText("Proyección ejecutada correctamente.")
        self.lbl_dashboard_estado.setText("Análisis actualizado correctamente")

    def _ejecutar_proyeccion_para_empalme(self, seleccion: dict[str, Any], anio: int, mes: int) -> dict[str, Any]:
        self.spin_anio.setValue(int(anio))
        self.spin_mes.setValue(int(mes))
        resultado = self.controlador.ejecutar_analisis(seleccion, int(anio), int(mes), "manual")
        self._proyeccion_lista(resultado, registrar=False)
        return resultado

    def guardar_sesion_actual(self) -> None:
        if self.controlador.proyeccion_actual is None:
            self._aviso("Ejecute una proyección antes de guardar la sesión.", nivel="advertencia")
            return

        usuario = self._solicitar_usuario()
        if not usuario:
            return

        seleccion = self._seleccion_actual()
        parametros = {"anio": int(self.spin_anio.value()), "mes": int(self.spin_mes.value()), "horizonte": self._horizonte_actual_meses()}
        ruta_jerarquica = self.controlador.construir_ruta_jerarquica(seleccion)
        nombre = generar_nombre_sesion(
            usuario,
            ruta_jerarquica,
            self.controlador.proyeccion_actual["periodo_proj"],
        )
        ruta_sugerida = asegurar_carpeta(CARPETA_SESIONES) / nombre
        ruta_salida, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar sesión",
            str(ruta_sugerida),
            "Sesión ICOCIV (*.json)",
        )
        if not ruta_salida:
            return

        datos = self.controlador.crear_datos_sesion(usuario, seleccion, parametros, ruta_jerarquica)
        ruta = guardar_sesion(ruta_salida, datos)
        self.nombre_sesion_actual = ruta.name
        self.etiqueta_estado.setText(f"Sesión guardada: {ruta.name}")

    def abrir_sesion(self) -> None:
        ruta_sesion, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir sesión",
            str(asegurar_carpeta(CARPETA_SESIONES)),
            "Sesión ICOCIV (*.json)",
        )
        if not ruta_sesion:
            return

        datos = cargar_sesion(ruta_sesion)
        ruta_excel = datos.get("archivo_excel")
        if not ruta_excel or not Path(ruta_excel).exists():
            QMessageBox.warning(
                self,
                "Sesion",
                "La sesión no contiene un archivo Excel disponible en este equipo.",
            )
            return

        self.sesion_pendiente = datos
        self.nombre_sesion_actual = Path(ruta_sesion).name
        self._cargar_archivo(ruta_excel)

    def generar_informe(self) -> None:
        self._generar_informe("docx")

    def generar_informe_pdf(self) -> None:
        self._generar_informe("pdf")

    def _generar_informe(self, formato: str) -> None:
        """Pide la configuración, el destino y lanza la generación en segundo plano."""
        if self.controlador.proyeccion_actual is None:
            self._aviso("Ejecute el análisis antes de generar el informe.", nivel="advertencia")
            return

        usuario = self._solicitar_usuario()
        if not usuario:
            return

        configuracion = pedir_configuracion(self, tipo_inicial="ejecutivo", formato=formato.upper())
        if configuracion is None:
            return

        seleccion = self._seleccion_actual()
        ruta_jerarquica = self.controlador.construir_ruta_jerarquica(seleccion)
        nombre = nombre_archivo_informe(
            configuracion.tipo, self._referencia_nombre_informe(ruta_jerarquica), formato,
        )
        ruta_sugerida = asegurar_carpeta(CARPETA_REPORTES) / nombre
        filtro = "Documento PDF (*.pdf)" if formato == "pdf" else "Documento Word (*.docx)"
        ruta_salida, _ = QFileDialog.getSaveFileName(self, "Guardar informe", str(ruta_sugerida), filtro)
        if not ruta_salida:
            return

        parametros = {
            "anio": int(self.spin_anio.value()),
            "mes": int(self.spin_mes.value()),
            "horizonte": self._horizonte_actual_meses(),
        }
        funcion = generar_reporte_pdf if formato == "pdf" else generar_reporte_proyeccion
        self._establecer_ocupado(True, f"Generando informe {formato.upper()}...")
        self.trabajador = TrabajadorFuncion(
            funcion,
            ruta_salida,
            usuario,
            str(self.controlador.ruta_archivo or ""),
            seleccion,
            parametros,
            ruta_jerarquica,
            nombre_tabla_icociv(self.controlador.fuente_actual),
            self.controlador.fila_actual,
            self.controlador.serie_actual,
            self.controlador.proyeccion_actual,
            self.controlador.periodos,
            self.nombre_sesion_actual,
            configuracion,
        )
        self.trabajador.resultado.connect(
            lambda ruta: self.etiqueta_estado.setText(f"Informe generado: {Path(ruta).name}")
        )
        self.trabajador.error.connect(self._mostrar_error)
        self.trabajador.finished.connect(lambda: self._establecer_ocupado(False))
        self.trabajador.start()

    def _referencia_nombre_informe(self, ruta_jerarquica: Any) -> str:
        """Último nivel seleccionado; da nombres de archivo reconocibles."""
        items = list(ruta_jerarquica or [])
        utiles = [i for i in items if str(i.get("nivel", "")) != "Tabla ICOCIV" and str(i.get("valor", "")).strip()]
        if utiles:
            return str(utiles[-1].get("valor"))
        return nombre_tabla_icociv(self.controlador.fuente_actual) or "Serie"

    def exportar_reproducibilidad_csv(self) -> None:
        if self.controlador.proyeccion_actual is None:
            self._aviso("Ejecute el análisis antes de exportar datos reproducibles.", nivel="advertencia")
            return
        ruta_sugerida = asegurar_carpeta(CARPETA_REPORTES) / generar_nombre_reproducibilidad_csv()
        ruta_salida, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar datos reproducibles CSV",
            str(ruta_sugerida),
            "Archivo CSV (*.csv)",
        )
        if not ruta_salida:
            return
        self._establecer_ocupado(True, "Exportando CSV reproducible...")
        self.trabajador = TrabajadorFuncion(
            generar_csv_reproducibilidad,
            ruta_salida,
            self.controlador.serie_actual,
            self.controlador.proyeccion_actual,
        )
        self.trabajador.resultado.connect(lambda ruta: self.etiqueta_estado.setText(f"CSV generado: {Path(ruta).name}"))
        self.trabajador.error.connect(self._mostrar_error)
        self.trabajador.finished.connect(lambda: self._establecer_ocupado(False))
        self.trabajador.start()

    def _actualizar_jerarquia(self) -> None:
        if not self.controlador.archivo_cargado:
            return
        seleccion = self._seleccion_actual()
        estado = self.controlador.obtener_estado_jerarquia(seleccion)
        self._actualizar_tabla_activa(seleccion)
        self._actualizar_ruta_visible(seleccion)

        self._rellenar_nivel(self.lbl_nivel2, self.combo_nivel2, estado["nivel2"])
        self._rellenar_nivel(self.lbl_nivel3, self.combo_nivel3, estado["nivel3"])
        self._rellenar_nivel(self.lbl_nivel4, self.combo_nivel4, estado["nivel4"])
        self._rellenar_nivel(self.lbl_nivel5, self.combo_nivel5, estado["nivel5"])
        self._rellenar_nivel(self.lbl_nivel6, self.combo_nivel6, estado["nivel6"])

        self._establecer_visible_checkbox(self.chk_t16_1, estado["mostrar_chk_t16_1"])
        self._establecer_visible_checkbox(self.chk_t16_2, estado["mostrar_chk_t16_2"])
        self._establecer_visible_checkbox(self.chk_t16_3, estado["mostrar_chk_t16_3"])

    def _actualizar_tabla_activa(self, seleccion: dict[str, Any]) -> None:
        nombre = self.controlador.nombre_fuente_seleccion(seleccion)
        if nombre:
            self.lbl_tabla_activa.setText(f"{ETIQUETA_TABLA_ACTIVA}: {nombre}")
        else:
            self.lbl_tabla_activa.setText(TEXTO_TABLA_SIN_SELECCION)

    def _actualizar_ruta_visible(self, seleccion: dict[str, Any]) -> None:
        ruta = self.controlador.construir_ruta_jerarquica(seleccion)
        ruta_sin_tabla = [item for item in ruta if item.get("nivel") != "Tabla ICOCIV"]
        if not ruta_sin_tabla:
            self.lbl_ruta_jerarquica.setText("Ruta jerárquica: sin selección")
            self.lbl_ruta_jerarquica.setToolTip("Ruta jerárquica: sin selección")
            if hasattr(self, "lbl_dashboard_ruta"):
                self.lbl_dashboard_ruta.setText("Seleccione una ruta jerárquica para iniciar.")
            return
        lineas = ["Ruta jerárquica seleccionada:"]
        for item in ruta_sin_tabla:
            lineas.append(f"{item.get('nivel', '')}: {item.get('valor', '')}")
        texto = "\n".join(lineas)
        self.lbl_ruta_jerarquica.setText(texto)
        self.lbl_ruta_jerarquica.setToolTip(texto)
        if hasattr(self, "lbl_dashboard_ruta"):
            self.lbl_dashboard_ruta.setText(" · ".join(item.get("valor", "") for item in ruta_sin_tabla))
            self.lbl_dashboard_ruta.setToolTip(texto)

    def _rellenar_nivel(self, etiqueta: QLabel, combo: QComboBox, descriptor: dict[str, Any] | None) -> None:
        valor_actual = combo.currentData()
        if not descriptor or not descriptor["opciones"]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Sin selección", None)
            combo.setItemData(0, "Sin selección", Qt.ItemDataRole.ToolTipRole)
            self._actualizar_tooltip_combo(combo)
            combo.blockSignals(False)
            etiqueta.setVisible(False)
            combo.setVisible(False)
            return

        etiqueta.setText(descriptor["etiqueta"])
        etiqueta.setVisible(True)
        combo.setVisible(True)
        self._llenar_combo(combo, descriptor["opciones"], valor_actual)

    def _llenar_combo(self, combo: QComboBox, opciones: list[dict[str, Any]], valor_actual: Any = None) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Sin selección", None)
        combo.setItemData(0, "Sin selección", Qt.ItemDataRole.ToolTipRole)
        indice_a_restaurar = 0
        maximo_ancho = combo.minimumWidth()
        for opcion in opciones:
            combo.addItem(opcion["texto"], opcion["indice"])
            indice_item = combo.count() - 1
            combo.setItemData(indice_item, opcion["texto"], Qt.ItemDataRole.ToolTipRole)
            maximo_ancho = max(maximo_ancho, combo.fontMetrics().horizontalAdvance(opcion["texto"]) + 56)
            if opcion["indice"] == valor_actual:
                indice_a_restaurar = combo.count() - 1
        combo.setCurrentIndex(indice_a_restaurar)
        combo.view().setMinimumWidth(min(maximo_ancho, 900))
        self._actualizar_tooltip_combo(combo)
        combo.blockSignals(False)

    def _seleccion_actual(self) -> dict[str, Any]:
        return {
            "idx_g": self.combo_grupo.currentData(),
            "chk_T16": self.chk_t16.isChecked(),
            "idx_l2": self.combo_nivel2.currentData(),
            "idx_l3": self.combo_nivel3.currentData(),
            "idx_l4": self.combo_nivel4.currentData(),
            "idx_l5": self.combo_nivel5.currentData(),
            "idx_l6": self.combo_nivel6.currentData(),
            "chk_T16_1": self.chk_t16_1.isChecked(),
            "chk_T16_2": self.chk_t16_2.isChecked(),
            "chk_T16_3": self.chk_t16_3.isChecked(),
        }

    def _restaurar_sesion_pendiente(self) -> None:
        datos = self.sesion_pendiente or {}
        self.sesion_pendiente = None
        seleccion = datos.get("seleccion", {})
        parametros = datos.get("parametros_proyeccion", {})

        self._establecer_combo_por_data(self.combo_grupo, seleccion.get("idx_g"))
        self.chk_t16.setChecked(bool(seleccion.get("chk_T16", False)))
        self._actualizar_jerarquia()
        self._establecer_combo_por_data(self.combo_nivel2, seleccion.get("idx_l2"))
        self.chk_t16_1.setChecked(bool(seleccion.get("chk_T16_1", False)))
        self._actualizar_jerarquia()
        self._establecer_combo_por_data(self.combo_nivel3, seleccion.get("idx_l3"))
        self.chk_t16_2.setChecked(bool(seleccion.get("chk_T16_2", False)))
        self._actualizar_jerarquia()
        self._establecer_combo_por_data(self.combo_nivel4, seleccion.get("idx_l4"))
        self.chk_t16_3.setChecked(bool(seleccion.get("chk_T16_3", False)))
        self._actualizar_jerarquia()
        self._establecer_combo_por_data(self.combo_nivel5, seleccion.get("idx_l5"))
        self._establecer_combo_por_data(self.combo_nivel6, seleccion.get("idx_l6"))

        # Los cuatro controles se restauran en bloque para que no se
        # sobrescriban entre sí mientras se aplica la sesión guardada.
        horizonte = parametros.get("horizonte")
        self._sincronizando = True
        try:
            if horizonte:
                self._seleccionar_horizonte_en_combo(int(horizonte))
                if 1 <= int(horizonte) <= self.spin_horizonte_personalizado.maximum():
                    self.spin_horizonte_personalizado.setValue(int(horizonte))
            self.spin_anio.setValue(int(parametros.get("anio", self.spin_anio.value())))
            self.spin_mes.setValue(int(parametros.get("mes", self.spin_mes.value())))
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()
        self.etiqueta_estado.setText(f"Sesión abierta: {self.nombre_sesion_actual}")
        self.ejecutar_proyeccion()

    def _establecer_combo_por_data(self, combo: QComboBox, valor: Any) -> None:
        for indice in range(combo.count()):
            if combo.itemData(indice) == valor:
                combo.setCurrentIndex(indice)
                return

    def _reiniciar_desde_nivel2(self) -> None:
        self._limpiar_combos(self.combo_nivel2, self.combo_nivel3, self.combo_nivel4, self.combo_nivel5, self.combo_nivel6)
        self._actualizar_jerarquia()

    def _reiniciar_desde_nivel3(self) -> None:
        self._limpiar_combos(self.combo_nivel3, self.combo_nivel4, self.combo_nivel5, self.combo_nivel6)
        self._actualizar_jerarquia()

    def _reiniciar_desde_nivel4(self) -> None:
        self._limpiar_combos(self.combo_nivel4, self.combo_nivel5, self.combo_nivel6)
        self._actualizar_jerarquia()

    def _reiniciar_desde_nivel5(self) -> None:
        self._limpiar_combos(self.combo_nivel5, self.combo_nivel6)
        self._actualizar_jerarquia()

    def _reiniciar_desde_nivel6(self) -> None:
        self._limpiar_combos(self.combo_nivel6)
        self._actualizar_jerarquia()

    def _limpiar_combos(self, *combos: QComboBox) -> None:
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Sin selección", None)
            combo.blockSignals(False)

    def _ocultar_niveles(self) -> None:
        for widget in (
            self.lbl_nivel2, self.combo_nivel2, self.lbl_nivel3, self.combo_nivel3,
            self.lbl_nivel4, self.combo_nivel4, self.lbl_nivel5, self.combo_nivel5,
            self.lbl_nivel6, self.combo_nivel6, self.chk_t16_1, self.chk_t16_2, self.chk_t16_3,
        ):
            widget.setVisible(False)

    def _establecer_visible_checkbox(self, checkbox: QCheckBox, visible: bool) -> None:
        if not visible:
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        checkbox.setVisible(visible)

    def _ajustar_periodo_por_defecto(self, periodos: list[str]) -> None:
        """Deja los cuatro controles coherentes tras cargar una serie nueva."""
        if not periodos:
            return
        anio, mes = [int(parte) for parte in periodos[-1].split("_")]
        mes += 1
        if mes == 13:
            anio += 1
            mes = 1
        self._sincronizando = True
        try:
            self.combo_horizonte.setCurrentIndex(0)  # 1 mes
            self.spin_horizonte_personalizado.setValue(1)
            self.spin_horizonte_personalizado.setEnabled(False)
            self.spin_anio.setValue(anio)
            self.spin_mes.setValue(mes)
        finally:
            self._sincronizando = False
        self._actualizar_etiqueta_horizonte_pendiente()

    def _dibujar_grafica(self, figura, serie_df, proyeccion: dict[str, Any]) -> list[str]:
        colores = paleta_tema(self.tema_actual)
        figura.clear()
        figura.patch.set_facecolor(colores["grafica"])
        eje = figura.add_subplot(111)
        eje.set_facecolor(colores["grafica"])
        periodos_obs = [periodo_a_iso(p) for p in serie_df["Periodo"].tolist()]
        etiquetas = list(periodos_obs)
        proy_df = proyeccion.get("proyecciones")
        if proyeccion.get("proyeccion_generada", True) and hasattr(proy_df, "empty") and not proy_df.empty:
            for periodo in proy_df["periodo"].tolist():
                etiqueta = periodo_a_iso(periodo)
                if etiqueta not in etiquetas:
                    etiquetas.append(etiqueta)
        indice_x = {etiqueta: idx for idx, etiqueta in enumerate(etiquetas)}
        x_obs = [indice_x[p] for p in periodos_obs]
        # Cada serie tiene además forma propia (marcador y trazo): el color no es
        # el único portador de la distinción, para no depender de verlo bien.
        eje.plot(
            x_obs,
            proyeccion["y_obs"],
            marker="o",
            markersize=3.5,
            linewidth=1.8,
            color=colores["serie_historica"],
            label="Serie observada",
        )
        if proyeccion.get("proyeccion_generada", True):
            periodos_full = [periodo_a_iso(t_a_periodo(int(t), ANIO_BASE)) for t in proyeccion.get("t_full", [])]
            x_full = [indice_x[p] for p in periodos_full if p in indice_x]
            y_fit_full = list(proyeccion.get("y_fit_full", []))[: len(x_full)]
            if x_full and len(y_fit_full) == len(x_full):
                eje.plot(
                    x_full,
                    y_fit_full,
                    linestyle="--",
                    linewidth=1.4,
                    color=colores["serie_ajuste"],
                    label="Ajuste del modelo",
                )
            if hasattr(proy_df, "empty") and not proy_df.empty:
                x_future = [indice_x[periodo_a_iso(p)] for p in proy_df["periodo"].tolist()]
                # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). Misma regla que en la
                # grafica de los informes: un mes no disponible no se une a sus
                # vecinos. La disponibilidad la calcula el servicio una sola vez y
                # viaja en `horizonte_disponible`; aqui solo se enmascara.
                y_future = proy_df["indice_proyectado"].astype(float).to_numpy()
                if "horizonte_disponible" in proy_df.columns:
                    disponible = proy_df["horizonte_disponible"].astype(bool).to_numpy()
                    y_future = np.where(disponible, y_future, np.nan)
                if x_obs and x_future:
                    # Línea divisoria entre lo observado y lo proyectado.
                    eje.axvline(
                        x_obs[-1],
                        color=colores["borde_fuerte"],
                        linewidth=1.0,
                        linestyle=":",
                        alpha=0.9,
                    )
                eje.plot(
                    x_future,
                    y_future,
                    marker="D",
                    markersize=3.5,
                    linewidth=1.8,
                    color=colores["serie_proyeccion"],
                    label="Proyección",
                )
                # P0-C RUTA C2: el intervalo se retira de las salidas. Ninguno de los trece metodos auditados resulto adoptable y REQ 20 prohibe la combinacion que se venia publicando. El calculo interno se conserva como diagnostico; lo que desaparece es su PUBLICACION. No se sustituye por ninguna otra banda.
                if False and {"limite_inferior_95", "limite_superior_95"}.issubset(proy_df.columns):
                    eje.fill_between(
                        x_future,
                        proy_df["limite_inferior_95"].astype(float).to_numpy(),
                        proy_df["limite_superior_95"].astype(float).to_numpy(),
                        color=colores["banda_intervalo"],
                        alpha=0.16,
                        linewidth=0,
                        label="Intervalo de predicción 95%",
                    )
        eje.set_title("Ajuste y proyección del índice ICOCIV", pad=12, fontsize=11, fontweight="600")
        eje.set_xlabel("Periodo (AAAA-MM)")
        eje.set_ylabel("Índice")
        if etiquetas:
            # Ticks dinámicos: se recalculan solos en cada zoom/desplazamiento
            # en lugar de fijarse una única vez (ver widgets/visor_grafica.py).
            configurar_ejes_dinamicos(eje, etiquetas)
        eje.tick_params(colors=colores["texto_secundario"], labelsize=8.5, length=0, pad=6)
        eje.title.set_color(colores["texto"])
        eje.xaxis.label.set_color(colores["texto_secundario"])
        eje.yaxis.label.set_color(colores["texto_secundario"])
        # Marco reducido a los ejes que orientan la lectura.
        for lado in ("top", "right"):
            eje.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eje.spines[lado].set_color(colores["grafica_rejilla"])
        eje.grid(True, axis="y", color=colores["grafica_rejilla"], alpha=0.7, linewidth=0.8)
        eje.set_axisbelow(True)
        leyenda = eje.legend(
            loc="upper left",
            frameon=False,
            fontsize=8.5,
            ncols=2,
        )
        if leyenda:
            for texto in leyenda.get_texts():
                texto.set_color(colores["texto_secundario"])
        figura.tight_layout()
        return etiquetas

    def _abrir_popup_serie(self) -> None:
        if self.controlador.serie_actual is None:
            self._aviso("Ejecute primero un análisis para ver la serie histórica.", nivel="advertencia")
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Serie histórica")
        dialogo.setModal(True)
        dialogo.resize(520, 560)
        dialogo.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialogo)
        etiqueta = QLabel(self._texto_ruta_popup())
        etiqueta.setWordWrap(True)
        tabla = QTableView()
        tabla.setModel(self.modelo_serie)
        tabla.setAlternatingRowColors(True)
        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(etiqueta)
        layout.addWidget(tabla, 1)
        layout.addWidget(boton_cerrar, 0, Qt.AlignmentFlag.AlignRight)
        dialogo.exec()

    def _abrir_popup_fila(self) -> None:
        if self.controlador.fila_actual is None:
            self._aviso("Ejecute primero un análisis para ver la fila fuente.", nivel="advertencia")
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Fila fuente del anexo ICOCIV")
        dialogo.setModal(True)
        dialogo.resize(760, 480)
        dialogo.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialogo)
        etiqueta = QLabel(self._texto_ruta_popup())
        etiqueta.setWordWrap(True)
        tabla = QTableView()
        tabla.setModel(self.modelo_fila)
        tabla.setAlternatingRowColors(True)
        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(etiqueta)
        layout.addWidget(tabla, 1)
        layout.addWidget(boton_cerrar, 0, Qt.AlignmentFlag.AlignRight)
        dialogo.exec()

    def _abrir_popup_grafica(self) -> None:
        if not self.resultado_ui_actual:
            self._aviso("Ejecute primero un análisis para ver la gráfica.", nivel="advertencia")
            return
        # La figura se construye una sola vez; el visor sólo cambia límites de
        # ejes al hacer zoom o desplazar, nunca recalcula la proyección.
        figura = Figure(figsize=(6, 4), dpi=100, facecolor=paleta_tema(self.tema_actual)["grafica"])
        self._dibujar_grafica(figura, self.resultado_ui_actual["serie_df"], self.resultado_ui_actual["proyeccion"])
        visor = VisorGraficaDialog(
            self,
            figura,
            "Gráfica de serie y proyección",
            hoja_estilo=self.styleSheet(),
            subtitulo=self._texto_ruta_popup(),
        )
        visor.canvas.setMinimumSize(GRAFICA_MIN_WIDTH, GRAFICA_MIN_HEIGHT)
        visor.exec()

    def _texto_ruta_popup(self) -> str:
        if not self.resultado_ui_actual:
            return ""
        ruta = self.resultado_ui_actual.get("ruta_jerarquica") or []
        ruta_sin_tabla = [item for item in ruta if item.get("nivel") != "Tabla ICOCIV"]
        tabla = self.resultado_ui_actual.get("fuente_visible", "")
        detalle = " · ".join(item.get("valor", "") for item in ruta_sin_tabla)
        return f"Tabla ICOCIV: {tabla}\nRuta: {detalle}" if detalle else f"Tabla ICOCIV: {tabla}"

    def _solicitar_usuario(self) -> str:
        usuario, ok = QInputDialog.getText(
            self,
            "Nombre de usuario",
            "Ingrese el nombre de usuario:",
            text=self.usuario_actual,
        )
        if not ok:
            return ""
        self.usuario_actual = usuario.strip()
        if not self.usuario_actual:
            QMessageBox.warning(self, "Trazabilidad", "Debe indicar un nombre de usuario.")
            return ""
        return self.usuario_actual

    def _actualizar_controles_habilitados(self, habilitado: bool) -> None:
        for widget in (
            self.combo_grupo, self.chk_t16, self.boton_ejecutar,
            self.boton_guardar_sesion, self.boton_exportar_informe,
            self.combo_horizonte, self.spin_horizonte_personalizado,
        ):
            widget.setEnabled(habilitado)
        if habilitado and self.combo_horizonte.currentData() is not None:
            self.spin_horizonte_personalizado.setEnabled(False)

    def _establecer_ocupado(self, ocupado: bool, mensaje: str | None = None) -> None:
        self.boton_cargar.setEnabled(not ocupado)
        self.boton_ejecutar.setEnabled(not ocupado and self.controlador.archivo_cargado)
        self.boton_guardar_sesion.setEnabled(not ocupado and self.controlador.archivo_cargado)
        self.boton_exportar_informe.setEnabled(not ocupado and self.controlador.archivo_cargado)
        parametros_habilitados = not ocupado
        for widget in (self.spin_anio, self.spin_mes, self.combo_horizonte, self.spin_horizonte_personalizado, *self.botones_periodo):
            widget.setEnabled(parametros_habilitados)
        if parametros_habilitados and self.combo_horizonte.currentData() is not None:
            self.spin_horizonte_personalizado.setEnabled(False)
        if mensaje:
            self.etiqueta_estado.setText(mensaje)
        # El trabajo ya corría en un hilo; ahora además se ve que corre.
        velo = getattr(self, "velo_carga", None)
        if velo is not None:
            if ocupado:
                velo.mostrar(mensaje or "Procesando…", "La aplicación sigue respondiendo.")
            else:
                velo.ocultar()

    # Prefijos técnicos que no aportan nada al usuario y sí ruido al mensaje.
    _RUIDO_ERROR = ("Traceback", "Exception:", "ValueError:", "RuntimeError:", "KeyError:")

    def _mensaje_comprensible(self, mensaje: str) -> str:
        """Convierte un error técnico en una frase útil, sin perder el detalle."""
        texto = str(mensaje).strip()
        minusculas = texto.lower()
        if "no hay suficientes datos" in minusculas or "mínimo 8" in minusculas:
            return "La serie seleccionada no tiene observaciones suficientes para analizarse."
        if "posterior al último periodo" in minusculas:
            return "El periodo solicitado debe ser posterior al último dato publicado."
        if "permission" in minusculas or "denied" in minusculas or "being used" in minusculas:
            return "No se pudo escribir el archivo: ciérrelo si está abierto en otra aplicación."
        if "no such file" in minusculas or "no existe" in minusculas:
            return "No se encontró el archivo indicado."
        primera_linea = texto.splitlines()[0] if texto else "Error desconocido."
        if any(primera_linea.startswith(p) for p in self._RUIDO_ERROR):
            return "La operación no pudo completarse."
        return primera_linea

    def _mostrar_error(self, mensaje: str) -> None:
        self._establecer_ocupado(False)
        self.etiqueta_estado.setText("Ocurrió un error.")
        gestor = getattr(self, "notificaciones", None)
        if gestor is None:
            QMessageBox.critical(self, "Error", mensaje)
            return
        # Texto comprensible a la vista, detalle técnico disponible en el aviso.
        gestor.error(self._mensaje_comprensible(mensaje), str(mensaje))

    def _mostrar_acerca_de(self) -> None:
        """Muestra versión, entorno y ubicaciones de trabajo de la aplicación."""
        dialogo = QMessageBox(self)
        dialogo.setWindowTitle("Acerca de SAVIP")
        dialogo.setTextFormat(Qt.TextFormat.RichText)
        dialogo.setText(
            "<b>SAVIP — Sistema de Análisis de Variaciones de Precios</b><br><br>"
            f"Versión: <b>{VERSION}</b><br>"
            f"Modo: {'ejecutable empaquetado' if es_ejecutable_congelado() else 'código fuente'}<br><br>"
            f"Reportes y exportables:<br><code>{CARPETA_REPORTES}</code><br><br>"
            f"Registros de ejecución:<br><code>{carpeta_logs()}</code><br><br>"
            "Apoyo al análisis de variaciones de precios en contratos de obra civil. "
            "Analiza índices oficiales ICOCIV del DANE y emplea información ICCP cuando "
            "corresponde. Los resultados son estimaciones estadísticas y no reemplazan la "
            "producción oficial del DANE ni el criterio del profesional responsable."
        )
        icono = _pixmap_logo(96)
        if icono is not None:
            dialogo.setIconPixmap(icono)
        dialogo.exec()

    def _abrir_carpeta_logs(self) -> None:
        """Abre la carpeta de registros en el explorador del sistema."""
        carpeta = asegurar_carpeta(carpeta_logs())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(carpeta)))

    def _cargar_estilos(self) -> None:
        """Compone la hoja del tema activo desde los tokens del sistema visual."""
        self.setStyleSheet(hoja_estilos(self.tema_actual))

    def resizeEvent(self, event) -> None:  # noqa: N802 - firma Qt
        """Las superposiciones no participan del layout: se recolocan a mano."""
        super().resizeEvent(event)
        if hasattr(self, "velo_carga"):
            self.velo_carga.reposicionar()
        if hasattr(self, "notificaciones"):
            self.notificaciones.reposicionar()

    def closeEvent(self, event) -> None:  # noqa: N802 - firma Qt
        """Detiene el movimiento en curso para no repintar widgets destruidos."""
        detener_todas()
        super().closeEvent(event)

    def _aviso(self, titulo: str, detalle: str = "", nivel: str = "informacion") -> None:
        """Aviso no modal; recurre al diálogo solo si aún no hay gestor."""
        gestor = getattr(self, "notificaciones", None)
        if gestor is None:
            QMessageBox.information(self, "SAVIP", f"{titulo}\n\n{detalle}".strip())
            return
        gestor.mostrar(titulo, detalle, nivel)

    def _aplicar_tema(self, tema: str, persistir: bool = True) -> None:
        self.tema_actual = normalizar_tema(tema)
        if hasattr(self, "accion_modo_oscuro"):
            self.accion_modo_oscuro.blockSignals(True)
            self.accion_modo_oscuro.setChecked(self.tema_actual == "oscuro")
            self.accion_modo_oscuro.blockSignals(False)
        if hasattr(self, "boton_tema_toggle"):
            self.boton_tema_toggle.blockSignals(True)
            self.boton_tema_toggle.setChecked(self.tema_actual == "oscuro")
            self.boton_tema_toggle.blockSignals(False)
            self._actualizar_texto_toggle_tema()
        self._cargar_estilos()
        # Las sombras llevan el color del tema y los componentes propios tienen
        # su propio estado visual: hay que repintarlos, no solo recargar la hoja.
        self._elevar_superficies()
        for atributo in ("pantalla_inicio", "velo_carga", "notificaciones"):
            componente = getattr(self, atributo, None)
            if componente is not None:
                componente.actualizar_tema(self.tema_actual)
        preparar_ventana(self, self.tema_actual)
        if persistir:
            self.preferencias.setValue("tema", self.tema_actual)
            self.preferencias.sync()
        self._renderizar_resultados_actuales()

    def _renderizar_resultados_actuales(self) -> None:
        if not self.resultado_ui_actual:
            return
        self.texto_resultados.setHtml(
            construir_html_resultados(self.resultado_ui_actual, self.tema_actual)
        )

    def _crear_dialogo_explicacion(self, titulo: str, html: str) -> QDialog:
        dialogo = QDialog(self)
        dialogo.setObjectName("dialogo_explicacion")
        dialogo.setWindowTitle(titulo)
        dialogo.setModal(True)
        dialogo.resize(760, 640)
        dialogo.setMinimumSize(620, 460)
        dialogo.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialogo)
        layout.setContentsMargins(14, 14, 14, 14)
        visor = QTextBrowser(dialogo)
        visor.setObjectName("visor_explicacion")
        visor.setOpenExternalLinks(False)
        visor.setHtml(html)
        boton_cerrar = QPushButton("Cerrar", dialogo)
        boton_cerrar.setObjectName("boton_cerrar_dialogo")
        boton_cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(visor, 1)
        layout.addWidget(boton_cerrar, 0, Qt.AlignmentFlag.AlignRight)
        dialogo.visor_explicacion = visor
        dialogo.boton_cerrar = boton_cerrar
        return dialogo

    def _mostrar_modal_explicacion(self, titulo: str, html: str) -> None:
        self._crear_dialogo_explicacion(titulo, html).exec()

    def _mostrar_explicacion_tarjeta(self, clave: str) -> None:
        titulos = {
            "indice": "Índice proyectado",
            "horizonte": "Horizonte solicitado",
            "modelo": "Selección del modelo",
            "estado": "Estado del horizonte",
            "ic95": "Intervalo de predicción",
            "maximo": "Máximo recomendado",
        }
        html = construir_html_explicacion_tarjeta(
            clave,
            self.resultado_ui_actual,
            self.tema_actual,
        )
        self._mostrar_modal_explicacion(titulos.get(clave, "Información del resultado"), html)

    def _mostrar_detalle_horizonte(self, enlace) -> None:
        texto = enlace.toString()
        if not texto.startswith("detalle-horizonte:"):
            return
        try:
            horizonte = int(texto.rsplit(":", 1)[-1])
        except ValueError:
            return
        evaluacion = self.detalles_horizonte.get(horizonte)
        if evaluacion is None:
            return
        self.horizonte_detalle_actual = horizonte
        self._mostrar_modal_explicacion(
            f"Detalle del horizonte h={horizonte}",
            construir_html_detalle_horizonte(evaluacion, self.tema_actual),
        )


def ejecutar_aplicacion() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SAVIP")
    app.setApplicationDisplayName("SAVIP — Sistema de Análisis de Variaciones de Precios")
    _icono = icono_savip()
    if _icono is not None:
        app.setWindowIcon(_icono)
    ventana = VentanaPrincipal()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(ejecutar_aplicacion())
