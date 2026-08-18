"""Visor interactivo de la gráfica de serie y proyección ICOCIV.

Agrega zoom (rueda del mouse y botones), desplazamiento (arrastre) y recálculo
dinámico de los ticks de ambos ejes. La interacción sólo modifica los límites de
los ejes y redibuja el lienzo: nunca vuelve a ejecutar la proyección ni ningún
cálculo estadístico.

El eje X es categórico (índices enteros 0..n-1 que representan periodos
mensuales), por eso se usa un localizador propio que traduce el rango visible a
índices de periodo. El eje Y usa el localizador automático de Matplotlib.
"""

from __future__ import annotations

import math

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import FuncFormatter, Locator, MaxNLocator
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


# Máximo de etiquetas simultáneas en el eje X para evitar superposición.
MAX_TICKS_X = 12
# Factor de zoom por muesca de rueda o pulsación de botón.
FACTOR_ZOOM = 1.25
# Amplitud mínima del eje X en índices de periodo (evita zoom infinito).
SPAN_MINIMO_X = 2.0
# Fracción mínima del rango original permitida en el eje Y.
FRACCION_MINIMA_Y = 0.005


class LocalizadorPeriodos(Locator):
    """Localizador de ticks para un eje X de periodos mensuales categóricos.

    Según el nivel de zoom escoge, en orden:
      1. todos los meses visibles (zoom alto);
      2. sólo inicios y finales de año (enero y diciembre);
      3. sólo inicios de año (enero);
      4. eneros espaciados, o un muestreo uniforme si no hay eneros.
    """

    def __init__(self, periodos: list[str], max_ticks: int = MAX_TICKS_X) -> None:
        self.periodos = list(periodos)
        self.max_ticks = max(2, int(max_ticks))
        self._meses = [_mes_de_periodo(p) for p in self.periodos]

    def __call__(self) -> list[float]:
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin: float, vmax: float) -> list[float]:
        total = len(self.periodos)
        if total == 0:
            return []
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        inicio = max(0, int(math.floor(vmin)))
        fin = min(total - 1, int(math.ceil(vmax)))
        if fin < inicio:
            return []
        visibles = list(range(inicio, fin + 1))

        # 1. Zoom alto: cabe un tick por mes.
        if len(visibles) <= self.max_ticks:
            return [float(i) for i in visibles]

        # 2/3. Priorizar inicios y finales de año.
        for meses_clave in ((1, 12), (1,)):
            candidatos = [i for i in visibles if self._meses[i] in meses_clave]
            if candidatos and len(candidatos) <= self.max_ticks:
                return [float(i) for i in candidatos]

        # 4. Demasiados años visibles: espaciar los eneros.
        eneros = [i for i in visibles if self._meses[i] == 1]
        base = eneros or visibles
        paso = max(1, math.ceil(len(base) / self.max_ticks))
        return [float(i) for i in base[::paso]]


def _mes_de_periodo(periodo: str) -> int:
    """Extrae el mes de una etiqueta 'AAAA-MM'; 0 si no es reconocible."""
    partes = str(periodo).replace("_", "-").split("-")
    if len(partes) >= 2 and partes[1].isdigit():
        return int(partes[1])
    return 0


def configurar_ejes_dinamicos(eje, etiquetas: list[str]) -> None:
    """Instala localizadores/formateadores que se recalculan al hacer zoom.

    Sustituye los ticks fijos por un localizador dinámico: Matplotlib vuelve a
    consultar el localizador en cada redibujado con el rango visible actual, de
    modo que los ticks se ajustan solos al nivel de zoom.
    """
    eje.xaxis.set_major_locator(LocalizadorPeriodos(etiquetas))
    eje.xaxis.set_major_formatter(FuncFormatter(_formatear_periodo(etiquetas)))
    # El eje Y conserva el localizador automático: al reducir el rango visible
    # genera divisiones más finas y al ampliarlo vuelve a divisiones amplias.
    eje.yaxis.set_major_locator(MaxNLocator(nbins="auto", min_n_ticks=3))
    # La rotación se fija en el eje (no en las etiquetas) para que sobreviva a
    # cada recálculo de ticks.
    eje.tick_params(axis="x", labelrotation=30)


def _formatear_periodo(etiquetas: list[str]):
    """Devuelve un formateador índice -> 'AAAA-MM'."""

    def formato(valor: float, _posicion: int) -> str:
        indice = int(round(valor))
        if 0 <= indice < len(etiquetas):
            return etiquetas[indice]
        return ""

    return formato


class VisorGraficaDialog(QDialog):
    """Ventana emergente con la gráfica y controles de zoom/desplazamiento."""

    def __init__(self, parent, figura, titulo: str, hoja_estilo: str = "", subtitulo: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.resize(900, 640)
        self.setMinimumSize(560, 420)
        if hoja_estilo:
            self.setStyleSheet(hoja_estilo)

        self.figura = figura
        self.eje = figura.axes[0] if figura.axes else None
        self.canvas = FigureCanvas(figura)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)

        # Límites originales: sirven de tope al alejar y al desplazarse.
        self._limites_base = self._leer_limites()
        self._panorama_activo = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        if subtitulo:
            etiqueta = QLabel(subtitulo)
            etiqueta.setWordWrap(True)
            etiqueta.setObjectName("ruta_dashboard")
            layout.addWidget(etiqueta)

        layout.addWidget(self.canvas, 1)

        controles = QHBoxLayout()
        ayuda = QLabel("Rueda del mouse: zoom · Arrastrar: desplazar")
        ayuda.setObjectName("ruta_dashboard")
        controles.addWidget(ayuda)
        controles.addStretch()
        self.boton_alejar = self._boton_zoom("−", "Alejar (Zoom Out)", self.alejar)
        self.boton_acercar = self._boton_zoom("+", "Acercar (Zoom In)", self.acercar)
        self.boton_restablecer = self._boton_zoom("⟲", "Restablecer vista completa", self.restablecer_vista)
        for boton in (self.boton_alejar, self.boton_acercar, self.boton_restablecer):
            controles.addWidget(boton)
        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.setObjectName("boton_cerrar_dialogo")
        boton_cerrar.clicked.connect(self.accept)
        controles.addWidget(boton_cerrar)
        layout.addLayout(controles)

        # Eventos nativos de Matplotlib (sin librerías externas).
        self._conexiones = [
            self.canvas.mpl_connect("scroll_event", self._al_desplazar_rueda),
            self.canvas.mpl_connect("button_press_event", self._al_presionar),
            self.canvas.mpl_connect("motion_notify_event", self._al_mover),
            self.canvas.mpl_connect("button_release_event", self._al_soltar),
        ]

    # ------------------------------------------------------------ controles
    @staticmethod
    def _boton_zoom(texto: str, ayuda: str, accion) -> QPushButton:
        boton = QPushButton(texto)
        boton.setObjectName("boton_zoom")
        boton.setToolTip(ayuda)
        boton.setFixedSize(34, 30)
        boton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        boton.clicked.connect(accion)
        return boton

    def acercar(self) -> None:
        """Zoom in centrado en la vista actual (mismo efecto que la rueda)."""
        self._aplicar_zoom(1.0 / FACTOR_ZOOM)

    def alejar(self) -> None:
        """Zoom out centrado en la vista actual (mismo efecto que la rueda)."""
        self._aplicar_zoom(FACTOR_ZOOM)

    def restablecer_vista(self) -> None:
        """Vuelve a los límites originales calculados al dibujar la serie."""
        if self.eje is None or self._limites_base is None:
            return
        (x0, x1), (y0, y1) = self._limites_base
        self.eje.set_xlim(x0, x1)
        self.eje.set_ylim(y0, y1)
        self.canvas.draw_idle()

    # -------------------------------------------------------------- eventos
    def _al_desplazar_rueda(self, evento) -> None:
        """Zoom respecto al cursor: hacia adelante acerca, hacia atrás aleja."""
        if self.eje is None or evento.inaxes is not self.eje:
            return
        pasos = evento.step if evento.step else (1 if evento.button == "up" else -1)
        escala = FACTOR_ZOOM ** (-pasos)
        self._aplicar_zoom(escala, evento.xdata, evento.ydata)

    def _al_presionar(self, evento) -> None:
        """Inicia el desplazamiento con el botón izquierdo o el central."""
        if self.eje is None or evento.inaxes is not self.eje:
            return
        if evento.button not in (1, 2):
            return
        # start_pan/drag_pan/end_pan son la API nativa que usa la barra de
        # navegación de Matplotlib; maneja correctamente la transformación.
        self.eje.start_pan(evento.x, evento.y, evento.button)
        self._panorama_activo = True
        self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _al_mover(self, evento) -> None:
        if not self._panorama_activo or self.eje is None:
            return
        self.eje.drag_pan(1, evento.key, evento.x, evento.y)
        self._ajustar_a_limites()
        self.canvas.draw_idle()

    def _al_soltar(self, evento) -> None:
        if not self._panorama_activo or self.eje is None:
            return
        self.eje.end_pan()
        self._panorama_activo = False
        self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    # --------------------------------------------------------------- zoom
    def _aplicar_zoom(self, escala: float, x_centro=None, y_centro=None) -> None:
        """Escala los límites alrededor de un punto y redibuja.

        ``escala`` < 1 acerca y ``escala`` > 1 aleja. Si no se indica un punto,
        se usa el centro de la vista actual (caso de los botones).
        """
        if self.eje is None:
            return
        x0, x1 = self.eje.get_xlim()
        y0, y1 = self.eje.get_ylim()
        if x_centro is None:
            x_centro = (x0 + x1) / 2.0
        if y_centro is None:
            y_centro = (y0 + y1) / 2.0

        nuevo_x = (x_centro - (x_centro - x0) * escala, x_centro + (x1 - x_centro) * escala)
        nuevo_y = (y_centro - (y_centro - y0) * escala, y_centro + (y1 - y_centro) * escala)
        self.eje.set_xlim(*self._acotar(nuevo_x, self._limites_base[0], SPAN_MINIMO_X))
        self.eje.set_ylim(*self._acotar(nuevo_y, self._limites_base[1], None))
        self.canvas.draw_idle()

    def _ajustar_a_limites(self) -> None:
        """Impide que el desplazamiento salga del rango de datos."""
        self.eje.set_xlim(*self._acotar(self.eje.get_xlim(), self._limites_base[0], SPAN_MINIMO_X))
        self.eje.set_ylim(*self._acotar(self.eje.get_ylim(), self._limites_base[1], None))

    @staticmethod
    def _acotar(rango, base, span_minimo) -> tuple[float, float]:
        """Recorta un rango para que quepa dentro del rango base."""
        lo, hi = float(rango[0]), float(rango[1])
        base_lo, base_hi = float(base[0]), float(base[1])
        span_base = base_hi - base_lo
        if span_base <= 0:
            return base_lo, base_hi
        minimo = span_minimo if span_minimo is not None else span_base * FRACCION_MINIMA_Y

        span = hi - lo
        if span >= span_base:  # no alejar más allá de los datos
            return base_lo, base_hi
        if span < minimo:  # no acercar indefinidamente
            centro = (lo + hi) / 2.0
            lo, hi = centro - minimo / 2.0, centro + minimo / 2.0
        if lo < base_lo:
            hi += base_lo - lo
            lo = base_lo
        if hi > base_hi:
            lo -= hi - base_hi
            hi = base_hi
        return max(lo, base_lo), min(hi, base_hi)

    def _leer_limites(self):
        if self.eje is None:
            return ((0.0, 1.0), (0.0, 1.0))
        return (tuple(self.eje.get_xlim()), tuple(self.eje.get_ylim()))


if __name__ == "__main__":
    # Comprobación del localizador dinámico en distintos niveles de zoom.
    periodos = [f"{2021 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(61)]
    localizador = LocalizadorPeriodos(periodos)

    # Zoom alto (8 meses visibles): un tick por mes.
    ticks = localizador.tick_values(10, 17)
    assert ticks == [float(i) for i in range(10, 18)], ticks

    # Zoom medio (2 años): inicios y finales de año.
    ticks = [int(t) for t in localizador.tick_values(0, 24)]
    assert all(_mes_de_periodo(periodos[i]) in (1, 12) for i in ticks), ticks
    assert len(ticks) <= MAX_TICKS_X

    # Vista completa (61 meses): inicios y finales de año, sin superposición.
    ticks = [int(t) for t in localizador.tick_values(0, 60)]
    assert all(_mes_de_periodo(periodos[i]) in (1, 12) for i in ticks), ticks
    assert len(ticks) <= MAX_TICKS_X, ticks

    # 8 años: enero+diciembre ya no cabe, se conservan sólo los eneros.
    ocho = [f"{2010 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(12 * 8)]
    ticks = [int(t) for t in LocalizadorPeriodos(ocho).tick_values(0, len(ocho) - 1)]
    assert all(_mes_de_periodo(ocho[i]) == 1 for i in ticks), ticks
    assert len(ticks) <= MAX_TICKS_X, ticks

    # Rango muy amplio: se espacian los eneros sin exceder el máximo.
    largos = [f"{2000 + i // 12:04d}-{i % 12 + 1:02d}" for i in range(12 * 40)]
    ticks = LocalizadorPeriodos(largos).tick_values(0, len(largos) - 1)
    assert len(ticks) <= MAX_TICKS_X, len(ticks)

    # Fuera de rango y rangos invertidos no rompen.
    assert localizador.tick_values(-50, -10) == []
    assert localizador.tick_values(30, 20) == localizador.tick_values(20, 30)

    # Acotado: no aleja más allá de los datos ni acerca sin límite.
    assert VisorGraficaDialog._acotar((-5.0, 100.0), (0.0, 60.0), 2.0) == (0.0, 60.0)
    lo, hi = VisorGraficaDialog._acotar((10.0, 10.2), (0.0, 60.0), 2.0)
    assert math.isclose(hi - lo, 2.0), (lo, hi)
    lo, hi = VisorGraficaDialog._acotar((-3.0, 7.0), (0.0, 60.0), 2.0)
    assert (lo, hi) == (0.0, 10.0), (lo, hi)
    print("OK visor_grafica")
