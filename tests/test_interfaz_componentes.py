"""Pruebas de los componentes visuales y de la degradación de efectos.

Se ejecutan sin ventana visible (plataforma offscreen). El punto central es que
la interfaz siga siendo utilizable cuando no hay movimiento, ni sombras, ni
material de ventana: con las animaciones desactivadas los widgets deben quedar
directamente en su estado final, no a medio camino.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app_icociv.interfaz.animaciones import (
    animar_ancho,
    aplicar_elevacion,
    desvanecer_entrada,
    desvanecer_salida,
    detener_todas,
    establecer_movimiento_reducido,
    establecer_sombras,
    movimiento_reducido,
    sombras_habilitadas,
)
from app_icociv.interfaz.componentes import (
    CabeceraApp,
    GestorNotificaciones,
    NavegacionLateral,
    PantallaInicio,
    Tarjeta,
    TarjetaMetrica,
    VeloCarga,
)
from app_icociv.interfaz.efectos import detectar_capacidades
from app_icociv.interfaz.tema import hoja_estilos, tokens

_app: QApplication | None = None


def _aplicacion() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
        _app.setStyleSheet(hoja_estilos("claro"))
    return _app


# Sin conservar la referencia, Python recolecta el contenedor y Qt destruye a sus
# hijos: las comprobaciones fallarían con «C++ object already deleted».
_lienzos: list[QWidget] = []


def _lienzo() -> QWidget:
    base = QWidget()
    base.resize(1280, 800)
    _lienzos.append(base)
    return base


def test_tarjeta_metrica_expone_estado_sin_depender_del_color() -> None:
    """El estado se comunica también con un símbolo, no solo con color."""
    _aplicacion()
    tarjeta = TarjetaMetrica("Modelo", "Drift", parent=_lienzo())
    for estado, simbolo in (("exito", "OK"), ("advertencia", "!"), ("error", "×")):
        tarjeta.actualizar(valor="Naive", estado=estado)
        assert tarjeta.property("estado") == estado
        assert tarjeta.indicador_estado.text() == simbolo
    tarjeta.actualizar(estado="neutro")
    assert tarjeta.indicador_estado.text() == ""


def test_tarjeta_metrica_es_accesible_por_teclado() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    _aplicacion()
    tarjeta = TarjetaMetrica("Horizonte", "6", parent=_lienzo())
    assert tarjeta.focusPolicy() == Qt.FocusPolicy.StrongFocus
    recibido: list[bool] = []
    tarjeta.clicked.connect(lambda: recibido.append(True))
    tarjeta.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )
    assert recibido, "La tarjeta debe activarse con Enter"


def test_navegacion_conserva_los_nombres_al_contraerse() -> None:
    """Contraída, cada entrada mantiene su nombre en el tooltip."""
    _aplicacion()
    establecer_movimiento_reducido(True)
    nav = NavegacionLateral(
        [("a", "Inicio", "Resumen"), ("b", "Resultados", "Análisis")], parent=_lienzo()
    )
    nav.establecer_contraccion(True)
    assert nav.esta_contraida()
    for boton, nombre in zip(nav.botones, ("Inicio", "Resultados")):
        assert nombre in boton.toolTip(), f"El tooltip perdió el nombre: {boton.toolTip()}"
    nav.establecer_contraccion(False)
    assert nav.botones[0].text() == "Inicio"
    establecer_movimiento_reducido(False)


def test_navegacion_precede_a_las_acciones_de_archivo() -> None:
    """Los módulos se leen primero; archivo y sesión son acciones de apoyo."""
    from PySide6.QtWidgets import QPushButton

    _aplicacion()
    nav = NavegacionLateral(
        [("a", "Inicio", ""), ("b", "Resultados", "")], parent=_lienzo()
    )
    contenido = nav._area.widget()
    layout = contenido.layout()
    posicion_ultima_entrada = max(
        layout.indexOf(boton) for boton in nav.botones
    )
    posicion_separador = layout.indexOf(nav.separador)
    assert posicion_separador > posicion_ultima_entrada, (
        "El grupo de archivo y sesión debe ir debajo de la navegación"
    )

    boton = QPushButton("Cargar archivo Excel")
    nav.agregar_accion(boton, "＋", "Carga un anexo")
    assert nav.titulo_acciones.text() == "Archivo y sesiones"
    # Al contraer, el rótulo del grupo desaparece y el botón deja su marca corta.
    nav.establecer_contraccion(True)
    assert not nav.titulo_acciones.isVisible()
    assert boton.text() == "＋" and "Carga un anexo" in boton.toolTip()
    nav.establecer_contraccion(False)
    assert boton.text() == "Cargar archivo Excel"


def test_navegacion_se_desplaza_en_ventanas_bajas() -> None:
    """Con poca altura el panel se desplaza en vez de recortar entradas."""
    from PySide6.QtCore import Qt

    _aplicacion()
    nav = NavegacionLateral(
        [(f"m{i}", f"Módulo {i}", "") for i in range(8)], parent=_lienzo()
    )
    nav.resize(nav.width(), 200)
    assert nav._area.widgetResizable()
    assert nav._area.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # El control de contracción vive fuera del área desplazable: siempre visible.
    assert nav.boton_contraer.parent() is nav


def test_navegacion_es_exclusiva_y_emite_indice() -> None:
    _aplicacion()
    nav = NavegacionLateral(
        [("a", "Uno", ""), ("b", "Dos", ""), ("c", "Tres", "")], parent=_lienzo()
    )
    recibidos: list[int] = []
    nav.seleccion_cambiada.connect(recibidos.append)
    nav.seleccionar(2)
    assert nav.indice_actual() == 2
    assert sum(1 for b in nav.botones if b.isChecked()) == 1


def test_cabecera_refleja_el_estado_del_archivo() -> None:
    _aplicacion()
    cabecera = CabeceraApp(parent=_lienzo())
    assert cabecera.estado_archivo.property("estado") == "vacio"
    cabecera.establecer_estado_archivo("anexo.xlsb", "cargado")
    assert cabecera.estado_archivo.text() == "anexo.xlsb"
    assert cabecera.estado_archivo.property("estado") == "cargado"
    cabecera.establecer_vista("Resultados")
    assert cabecera.vista.text() == "Resultados"


def test_notificaciones_limitan_las_visibles_y_los_errores_persisten() -> None:
    """Una cascada de avisos superpuestos sería peor que no avisar."""
    _aplicacion()
    establecer_movimiento_reducido(True)
    base = _lienzo()
    gestor = GestorNotificaciones(base)
    for i in range(6):
        gestor.informacion(f"Aviso {i}")
    assert len(gestor._activas) <= GestorNotificaciones.MAXIMO_VISIBLES

    gestor.cerrar_todas()
    aviso = gestor.error("Error grave", "Traceback interno")
    # Los errores no se retiran solos: exigen que el usuario los lea.
    assert aviso in gestor._activas
    assert "Traceback interno" in aviso.etiqueta_detalle.text()
    assert aviso.accessibleName().startswith("error")
    establecer_movimiento_reducido(False)


def test_velo_de_carga_cubre_y_libera_el_area() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    base = _lienzo()
    base.show()
    velo = VeloCarga(base)
    velo.mostrar("Analizando", "Serie total")
    assert velo.isVisible()
    assert velo.etiqueta.text() == "Analizando"
    assert velo.barra.maximum() == 0, "Sin progreso conocido la barra es indeterminada"
    velo.establecer_progreso(40, 100)
    assert velo.barra.value() == 40
    velo.ocultar()
    assert not velo.isVisible(), "Sin animación el velo debe ocultarse de inmediato"
    establecer_movimiento_reducido(False)


def test_velo_ofrece_cancelar_solo_cuando_es_viable() -> None:
    _aplicacion()
    base = _lienzo()
    velo = VeloCarga(base)
    velo.mostrar("Sin cancelación")
    assert not velo.boton_cancelar.isVisible()
    cancelado: list[bool] = []
    velo.mostrar("Con cancelación", al_cancelar=lambda: cancelado.append(True))
    velo.boton_cancelar.click()
    assert cancelado == [True]


def test_pantalla_inicio_resume_el_estado_de_la_sesion() -> None:
    _aplicacion()
    inicio = PantallaInicio("0.2.0-beta", parent=_lienzo())
    inicio.actualizar_estado(
        archivo="anex-ICOCIV.xlsb",
        periodo="2026-05",
        serie="Total nacional",
        observaciones="65",
        valores=[100.0, 101.5, 103.2, 104.0],
    )
    assert inicio.datos["archivo"].valor.text() == "anex-ICOCIV.xlsb"
    assert inicio.datos["periodo"].valor.text() == "2026-05"
    assert "0.2.0-beta" in inicio.version.text()
    # Sin serie no se dibuja la franja de identidad.
    inicio.actualizar_estado(valores=[])
    assert inicio.datos["archivo"].valor.text() == "Sin archivo cargado"


def test_movimiento_reducido_deja_el_estado_final() -> None:
    """Con el movimiento desactivado nada puede quedar a medio camino."""
    _aplicacion()
    establecer_movimiento_reducido(True)
    base = _lienzo()
    base.show()
    widget = QWidget(base)
    widget.resize(200, 100)

    assert desvanecer_entrada(widget) is None, "No debe crearse animación"
    assert widget.isVisible()
    assert widget.graphicsEffect() is None, "No debe quedar un efecto a medias"

    assert desvanecer_salida(widget) is None
    assert not widget.isVisible()

    assert animar_ancho(widget, 320) is None
    assert widget.maximumWidth() == 320 and widget.minimumWidth() == 320
    establecer_movimiento_reducido(False)


def test_sombras_se_pueden_desactivar_por_completo() -> None:
    """El interruptor de sombras permite degradar en equipos limitados."""
    _aplicacion()
    widget = QWidget(_lienzo())
    assert sombras_habilitadas()
    assert aplicar_elevacion(widget, tokens.ELEVACION_2) is not None

    establecer_sombras(False)
    assert aplicar_elevacion(widget, tokens.ELEVACION_2) is None
    assert widget.graphicsEffect() is None
    establecer_sombras(True)


def test_elevacion_nula_no_crea_efecto() -> None:
    _aplicacion()
    widget = QWidget(_lienzo())
    assert aplicar_elevacion(widget, tokens.ELEVACION_0) is None


def test_capacidades_de_ventana_se_detectan_sin_efectos_secundarios() -> None:
    """La detección debe funcionar en cualquier sistema, sin lanzar."""
    capacidades = detectar_capacidades()
    datos = capacidades.como_dict()
    for clave in ("es_windows", "build", "admite_material", "motivo"):
        assert clave in datos
    assert isinstance(datos["admite_material"], bool)
    assert datos["motivo"], "Siempre debe explicarse la decisión"
    if not datos["es_windows"]:
        assert not datos["admite_material"]


def test_tarjeta_agrupa_contenido() -> None:
    _aplicacion()
    tarjeta = Tarjeta("Resumen", "Descripción breve", parent=_lienzo())
    assert tarjeta.etiqueta_titulo is not None
    assert tarjeta.etiqueta_descripcion is not None
    hijo = QWidget()
    tarjeta.agregar(hijo)
    assert tarjeta.cuerpo().indexOf(hijo) >= 0


def test_detener_todas_no_falla_sin_animaciones() -> None:
    detener_todas()
    assert not movimiento_reducido()


if __name__ == "__main__":
    _aplicacion()
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: componentes y degradación de efectos.")
