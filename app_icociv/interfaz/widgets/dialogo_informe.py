"""Selector de contenido que se muestra antes de exportar un informe.

El informe dejó de ser una descarga de todo lo disponible: aquí el usuario elige
el tipo, marca las secciones y gráficas que quiere y, si le sirve, diligencia los
campos institucionales. Ninguno de esos campos es obligatorio.

Elegir un tipo aplica su plantilla de casillas; tocar cualquier casilla pasa el
tipo a «Personalizado», porque a partir de ahí la selección ya no coincide con
ninguna plantilla.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_icociv.interfaz.widgets.controles import ComboBoxSinRueda
from app_icociv.reportes.modelo import (
    CamposInstitucionales,
    ConfiguracionInforme,
    GRAFICAS_DISPONIBLES,
    GRAFICAS_EJECUTIVO,
    GRAFICAS_TECNICO,
    MONEDAS,
    PRESET_EJECUTIVO,
    PRESET_EMPALME,
    PRESET_TECNICO,
    SECCIONES_DISPONIBLES,
)

TIPOS = (
    ("ejecutivo", "Ejecutivo", "3 a 6 páginas. Resultado, interpretación y advertencias."),
    ("tecnico", "Técnico", "8 a 15 páginas. Añade metodología, backtesting y diagnóstico."),
    ("empalme", "Ajuste ICCP–ICOCIV", "Fórmulas, sustitución numérica y advertencias contractuales."),
    ("personalizado", "Personalizado", "Marque libremente las secciones y gráficas."),
)

PRESETS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "ejecutivo": (PRESET_EJECUTIVO, GRAFICAS_EJECUTIVO),
    "tecnico": (PRESET_TECNICO, GRAFICAS_TECNICO),
    "empalme": (PRESET_EMPALME, frozenset()),
}

CAMPOS_INSTITUCIONALES = (
    ("entidad", "Entidad"),
    ("dependencia", "Dependencia"),
    ("proyecto", "Proyecto"),
    ("contrato", "Contrato"),
    ("objeto", "Objeto"),
    ("contratista", "Contratista"),
    ("supervisor", "Supervisor"),
    ("interventor", "Interventor"),
    ("responsable", "Responsable del informe"),
)

FORMATOS_LOGO = "Imagen (*.png *.jpg *.jpeg)"
LOGO_MAXIMO_BYTES = 4 * 1024 * 1024


class DialogoConfiguracionInforme(QDialog):
    """Diálogo modal que devuelve una :class:`ConfiguracionInforme`."""

    def __init__(
        self,
        padre: QWidget | None = None,
        tipo_inicial: str = "ejecutivo",
        formato: str = "DOCX",
        solo_empalme: bool = False,
    ) -> None:
        super().__init__(padre)
        self.setObjectName("dialogo_informe")
        self.setWindowTitle(f"Configurar informe {formato.upper()}")
        self.setModal(True)
        self.resize(760, 660)
        self.setMinimumSize(620, 520)
        if padre is not None:
            self.setStyleSheet(padre.styleSheet())

        self._solo_empalme = solo_empalme
        self._aplicando_preset = False
        self._logo: bytes | None = None
        self._nombre_logo = ""
        self.casillas_seccion: dict[str, QCheckBox] = {}
        self.casillas_grafica: dict[str, QCheckBox] = {}
        self.campos: dict[str, QLineEdit] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.setSpacing(12)
        raiz.addWidget(self._bloque_tipo(tipo_inicial))

        pestanas = QTabWidget(self)
        if not solo_empalme:
            pestanas.addTab(self._pestana_contenido(), "Contenido")
        pestanas.addTab(self._pestana_institucional(), "Datos institucionales")
        raiz.addWidget(pestanas, 1)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Generar informe")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

        self._aplicar_preset(tipo_inicial)

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def _bloque_tipo(self, tipo_inicial: str) -> QWidget:
        grupo = QGroupBox("Tipo de informe", self)
        disposicion = QHBoxLayout(grupo)
        self.combo_tipo = ComboBoxSinRueda(grupo)
        self.combo_tipo.setObjectName("combo_tipo_informe")
        for clave, etiqueta, _ in TIPOS:
            if self._solo_empalme and clave != "empalme":
                continue
            self.combo_tipo.addItem(etiqueta, clave)
        indice = max(0, self.combo_tipo.findData(tipo_inicial))
        self.combo_tipo.setCurrentIndex(indice)
        self.combo_tipo.currentIndexChanged.connect(self._cambio_tipo)

        self.etiqueta_tipo = QLabel(grupo)
        self.etiqueta_tipo.setWordWrap(True)
        self.etiqueta_tipo.setObjectName("descripcion_tipo_informe")

        disposicion.addWidget(self.combo_tipo, 0)
        disposicion.addWidget(self.etiqueta_tipo, 1)
        return grupo

    def _pestana_contenido(self) -> QWidget:
        contenedor = QWidget(self)
        disposicion = QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 8, 0, 0)

        # post-r1-metodologia-12-24, 19-08-2026 (Prompt UI 01). "Seleccionar
        # todas" marca de un clic todas las casillas habilitadas de Secciones
        # y Gráficas; se convierte en "Deseleccionar todas" cuando ya están
        # todas marcadas.
        self.boton_seleccionar_todas = QPushButton("Seleccionar todas", contenedor)
        self.boton_seleccionar_todas.setObjectName("boton_secundario")
        self.boton_seleccionar_todas.clicked.connect(self._alternar_seleccionar_todas)
        fila_seleccionar_todas = QHBoxLayout()
        fila_seleccionar_todas.addWidget(self.boton_seleccionar_todas)
        fila_seleccionar_todas.addStretch(1)
        disposicion.addLayout(fila_seleccionar_todas)

        disposicion.addWidget(self._grupo_casillas(
            "Secciones", SECCIONES_DISPONIBLES, self.casillas_seccion, columnas=2,
        ))
        disposicion.addWidget(self._grupo_casillas(
            "Gráficas", GRAFICAS_DISPONIBLES, self.casillas_grafica, columnas=2,
        ))

        self.casilla_anexo_backtesting = QCheckBox("Incluir anexo con las ventanas de backtesting", contenedor)
        self.casilla_anexo_backtesting.setToolTip(
            "Tabla extensa de validación temporal. Fuera del anexo, el informe solo resume el backtesting."
        )
        disposicion.addWidget(self.casilla_anexo_backtesting)
        disposicion.addStretch(1)

        return self._con_scroll(contenedor)

    def _grupo_casillas(
        self,
        titulo: str,
        definiciones: tuple[tuple[str, str], ...],
        destino: dict[str, QCheckBox],
        columnas: int,
    ) -> QGroupBox:
        grupo = QGroupBox(titulo, self)
        rejilla = QGridLayout(grupo)
        rejilla.setHorizontalSpacing(18)
        rejilla.setVerticalSpacing(4)
        for indice, (clave, etiqueta) in enumerate(definiciones):
            casilla = QCheckBox(etiqueta, grupo)
            casilla.toggled.connect(self._marca_personalizado)
            casilla.toggled.connect(lambda _=None: self._actualizar_texto_seleccionar_todas())
            destino[clave] = casilla
            rejilla.addWidget(casilla, indice // columnas, indice % columnas)
        return grupo

    def _casillas_seleccionables(self) -> list[QCheckBox]:
        """Todas las casillas de Secciones y Gráficas que el usuario puede tocar."""
        return [
            casilla
            for casilla in (*self.casillas_seccion.values(), *self.casillas_grafica.values())
            if casilla.isEnabled()
        ]

    def _pestana_institucional(self) -> QWidget:
        contenedor = QWidget(self)
        disposicion = QVBoxLayout(contenedor)
        disposicion.setContentsMargins(0, 8, 0, 0)

        aviso = QLabel("Todos los campos son opcionales. Los que queden vacíos no aparecen en el informe.", contenedor)
        aviso.setWordWrap(True)
        disposicion.addWidget(aviso)

        grupo = QGroupBox("Identificación", contenedor)
        rejilla = QGridLayout(grupo)
        for indice, (clave, etiqueta) in enumerate(CAMPOS_INSTITUCIONALES):
            entrada = QLineEdit(grupo)
            entrada.setPlaceholderText(etiqueta)
            self.campos[clave] = entrada
            rejilla.addWidget(QLabel(f"{etiqueta}:", grupo), indice, 0)
            rejilla.addWidget(entrada, indice, 1)
        disposicion.addWidget(grupo)

        grupo_extra = QGroupBox("Presentación", contenedor)
        rejilla_extra = QGridLayout(grupo_extra)

        self.combo_moneda = ComboBoxSinRueda(grupo_extra)
        for codigo in MONEDAS:
            self.combo_moneda.addItem(codigo, codigo)
        rejilla_extra.addWidget(QLabel("Moneda:", grupo_extra), 0, 0)
        rejilla_extra.addWidget(self.combo_moneda, 0, 1)

        self.boton_logo = QPushButton("Seleccionar logo institucional…", grupo_extra)
        self.boton_logo.clicked.connect(self._elegir_logo)
        self.etiqueta_logo = QLabel("Sin logo", grupo_extra)
        self.etiqueta_logo.setWordWrap(True)
        rejilla_extra.addWidget(self.boton_logo, 1, 0)
        rejilla_extra.addWidget(self.etiqueta_logo, 1, 1)

        self.casilla_firmas = QCheckBox("Incluir bloque de firmas (Elaboró / Revisó / Aprobó)", grupo_extra)
        rejilla_extra.addWidget(self.casilla_firmas, 2, 0, 1, 2)
        disposicion.addWidget(grupo_extra)

        grupo_obs = QGroupBox("Observaciones generales", contenedor)
        disposicion_obs = QVBoxLayout(grupo_obs)
        self.observaciones = QPlainTextEdit(grupo_obs)
        self.observaciones.setPlaceholderText("Texto libre que aparecerá en la portada del informe.")
        self.observaciones.setMaximumHeight(110)
        disposicion_obs.addWidget(self.observaciones)
        disposicion.addWidget(grupo_obs)
        disposicion.addStretch(1)

        return self._con_scroll(contenedor)

    def _con_scroll(self, contenido: QWidget) -> QScrollArea:
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(contenido)
        return area

    # ------------------------------------------------------------------
    # Comportamiento
    # ------------------------------------------------------------------

    def _cambio_tipo(self) -> None:
        self._aplicar_preset(self.combo_tipo.currentData())

    def _aplicar_preset(self, tipo: str) -> None:
        descripciones = {clave: texto for clave, _, texto in TIPOS}
        self.etiqueta_tipo.setText(descripciones.get(tipo, ""))
        if tipo == "personalizado" or self._solo_empalme:
            return
        secciones, graficas = PRESETS.get(tipo, (PRESET_EJECUTIVO, GRAFICAS_EJECUTIVO))
        self._aplicando_preset = True
        try:
            for clave, casilla in self.casillas_seccion.items():
                casilla.setChecked(clave in secciones)
            for clave, casilla in self.casillas_grafica.items():
                casilla.setChecked(clave in graficas)
            self.casilla_anexo_backtesting.setChecked(False)
        finally:
            self._aplicando_preset = False
        self._actualizar_texto_seleccionar_todas()

    def _alternar_seleccionar_todas(self) -> None:
        """Un clic marca todas las casillas habilitadas; si ya estaban todas
        marcadas, el mismo botón las desmarca."""
        casillas = self._casillas_seleccionables()
        if not casillas:
            return
        marcar = not all(casilla.isChecked() for casilla in casillas)
        self._aplicando_preset = True
        try:
            for casilla in casillas:
                casilla.setChecked(marcar)
        finally:
            self._aplicando_preset = False
        self._marca_personalizado()
        self._actualizar_texto_seleccionar_todas()

    def _actualizar_texto_seleccionar_todas(self) -> None:
        if not hasattr(self, "boton_seleccionar_todas"):
            return
        casillas = self._casillas_seleccionables()
        todas_marcadas = bool(casillas) and all(casilla.isChecked() for casilla in casillas)
        self.boton_seleccionar_todas.setText("Deseleccionar todas" if todas_marcadas else "Seleccionar todas")

    def _marca_personalizado(self) -> None:
        """Una selección que ya no coincide con la plantilla deja de ser esa plantilla."""
        if self._aplicando_preset or self._solo_empalme:
            return
        indice = self.combo_tipo.findData("personalizado")
        if indice >= 0 and self.combo_tipo.currentIndex() != indice:
            self.combo_tipo.blockSignals(True)
            self.combo_tipo.setCurrentIndex(indice)
            self.combo_tipo.blockSignals(False)
            self.etiqueta_tipo.setText({clave: texto for clave, _, texto in TIPOS}["personalizado"])

    def _elegir_logo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar logo institucional", "", FORMATOS_LOGO)
        if not ruta:
            return
        archivo = Path(ruta)
        try:
            datos = archivo.read_bytes()
        except OSError as error:
            self.etiqueta_logo.setText(f"No se pudo leer el archivo: {error}")
            return
        if len(datos) > LOGO_MAXIMO_BYTES:
            self.etiqueta_logo.setText("El logo supera 4 MB; elija una imagen más liviana.")
            return
        self._logo = datos
        self._nombre_logo = archivo.name
        self.etiqueta_logo.setText(archivo.name)

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------

    def configuracion(self) -> ConfiguracionInforme:
        institucional = CamposInstitucionales(
            **{clave: self.campos[clave].text().strip() for clave, _ in CAMPOS_INSTITUCIONALES},
            observaciones=self.observaciones.toPlainText().strip(),
            logo=self._logo,
            incluir_firmas=self.casilla_firmas.isChecked(),
        )
        tipo = self.combo_tipo.currentData() or "ejecutivo"
        if self._solo_empalme:
            base = ConfiguracionInforme.desde_tipo("empalme")
            secciones, graficas = base.secciones, base.graficas
            anexo = False
        else:
            secciones = frozenset(c for c, casilla in self.casillas_seccion.items() if casilla.isChecked())
            graficas = frozenset(c for c, casilla in self.casillas_grafica.items() if casilla.isChecked())
            anexo = self.casilla_anexo_backtesting.isChecked()
        return ConfiguracionInforme(
            tipo=tipo,
            secciones=secciones,
            graficas=graficas,
            institucional=institucional,
            moneda=self.combo_moneda.currentData() or "COP",
            incluir_anexo_backtesting=anexo,
        )


def pedir_configuracion(
    padre: QWidget | None,
    tipo_inicial: str = "ejecutivo",
    formato: str = "DOCX",
    solo_empalme: bool = False,
) -> ConfiguracionInforme | None:
    """Muestra el diálogo y devuelve la configuración, o ``None`` si se cancela."""
    dialogo = DialogoConfiguracionInforme(padre, tipo_inicial, formato, solo_empalme)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialogo.configuracion()


__all__: list[Any] = ["DialogoConfiguracionInforme", "pedir_configuracion"]
