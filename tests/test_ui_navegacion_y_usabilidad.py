"""Pruebas dirigidas del Prompt UI 01: orden del menu lateral, indicador de
Resultados, "Seleccionar todas" en el dialogo de informe, popup de horizonte
>24, glosario de estados del horizonte, y eliminar seleccionado/eliminar todo
en las tablas de Proyecciones ICOCIV y Empalme ICCP-ICOCIV.

No ejecuta la suite global: son pruebas puntuales sobre los widgets tocados
por este prompt, ejecutables con `python tests/test_ui_navegacion_y_usabilidad.py`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication(sys.argv)

from app_icociv.interfaz.ventana_principal import VentanaPrincipal
from app_icociv.interfaz.widgets.dialogo_informe import DialogoConfiguracionInforme
from app_icociv.interfaz.presentacion_resultados import (
    GLOSARIO_ESTADOS_HORIZONTE,
    construir_html_explicacion_tarjeta,
)


# --------------------------------------------------------------- CASO 1
def test_caso1_orden_navegacion_inicio_proyecciones_empalme_resultados():
    ventana = VentanaPrincipal()
    orden_esperado = ["Inicio", "Proyecciones ICOCIV", "Empalme ICCP-ICOCIV", "Resultados"]
    orden_navegacion = [texto for _clave, texto, _desc in ventana.navegacion._entradas]
    assert orden_navegacion == orden_esperado
    orden_tabs = [ventana.tabs_principales.tabText(i) for i in range(ventana.tabs_principales.count())]
    assert orden_tabs == orden_esperado
    orden_secciones = [nombre for nombre, _muestra in ventana.SECCIONES]
    assert orden_secciones == orden_esperado
    assert ventana.INDICE_RESULTADOS == 3
    ventana.deleteLater()


# --------------------------------------------------------------- CASO 2
def test_caso2_indicador_resultados_sin_con_y_tras_eliminar():
    ventana = VentanaPrincipal()
    boton_resultados = ventana.navegacion.botones[ventana.INDICE_RESULTADOS]

    # Sin resultados: neutral.
    assert ventana.resultado_ui_actual is None
    assert boton_resultados.property("destacado") in (None, False)

    # Con resultados: destacado.
    ventana.resultado_ui_actual = {"marca": "resultado de prueba"}
    ventana._actualizar_indicador_resultados()
    assert boton_resultados.property("destacado") is True
    assert "●" in boton_resultados.text()  # marca textual, no solo color

    # Pestaña activa distinguible de "hay resultados": ambas banderas conviven
    # sin pisarse (checked es selección, destacado es disponibilidad).
    ventana._cambiar_seccion(ventana.INDICE_RESULTADOS)
    assert boton_resultados.isChecked() is True
    assert boton_resultados.property("destacado") is True

    # Al vaciar todos los resultados, vuelve a neutral.
    ventana.resultado_ui_actual = None
    ventana._actualizar_indicador_resultados()
    assert boton_resultados.property("destacado") is False
    ventana.deleteLater()


# --------------------------------------------------------------- CASO 3
def test_caso3_seleccionar_todas_marca_solo_habilitadas_y_llega_al_generador():
    dialogo = DialogoConfiguracionInforme(tipo_inicial="personalizado")
    casillas = dialogo._casillas_seleccionables()
    assert casillas, "el dialogo de informe debe tener casillas de seccion/grafica"
    for casilla in casillas:
        assert casilla.isChecked() is False

    dialogo._alternar_seleccionar_todas()
    assert all(c.isChecked() for c in casillas)
    assert dialogo.boton_seleccionar_todas.text() == "Deseleccionar todas"

    dialogo._alternar_seleccionar_todas()
    assert all(not c.isChecked() for c in casillas)
    assert dialogo.boton_seleccionar_todas.text() == "Seleccionar todas"

    # La seleccion llega realmente al generador: ConfiguracionInforme lee
    # directamente el estado de las casillas via configuracion().
    dialogo._alternar_seleccionar_todas()
    configuracion = dialogo.configuracion()
    assert set(configuracion.secciones) == set(dialogo.casillas_seccion.keys())
    dialogo.deleteLater()


# --------------------------------------------------------------- CASO 4
def test_caso4_popup_horizonte_24_valido_25_manual_y_fecha_equivalen_un_popup():
    ventana = VentanaPrincipal()
    llamadas = {"n": 0}
    with patch.object(ventana, "_alertar_horizonte_excedido", side_effect=lambda: llamadas.__setitem__("n", llamadas["n"] + 1)):
        # 24 valido: sin popup.
        ventana._detectar_horizonte_personalizado_excedido("24")
        assert llamadas["n"] == 0

        # Intento manual 25: un popup.
        ventana._detectar_horizonte_personalizado_excedido("25")
        assert llamadas["n"] == 1
        # Repetir el mismo intento sin corregir no debe duplicar el popup.
        ventana._detectar_horizonte_personalizado_excedido("25")
        assert llamadas["n"] == 1
        # Corregir a un valor valido resetea la bandera.
        ventana._detectar_horizonte_personalizado_excedido("24")
        assert ventana._horizonte_popup_mostrado is False

        # Fecha objetivo equivalente a >24 meses: un popup adicional.
        llamadas["n"] = 0
        with patch.object(ventana, "_ultimo_periodo_serie", return_value=(2024, 1)):
            ventana._sincronizando = False
            ventana.spin_anio.blockSignals(True)
            ventana.spin_mes.blockSignals(True)
            ventana.spin_anio.setValue(2026)
            ventana.spin_mes.setValue(3)  # 26 meses de horizonte desde 2024_1
            ventana.spin_anio.blockSignals(False)
            ventana.spin_mes.blockSignals(False)
            ventana._periodo_objetivo_cambiado()
            assert llamadas["n"] == 1
            # El estado final debe quedar dentro de 1..24 (no en 25/26).
            horizonte_final = ventana._horizonte_desde_periodo()
            assert horizonte_final is not None and horizonte_final <= 24
    ventana.deleteLater()


# --------------------------------------------------------------- CASO 5
def test_caso5_glosario_contiene_solo_estados_reales():
    etiquetas = {estado for estado, _significado in GLOSARIO_ESTADOS_HORIZONTE}
    assert "Proyección técnica" in etiquetas
    assert "No admisible" in etiquetas
    assert "Escenario" not in etiquetas  # retirado, nunca lo produce el motor

    texto_completo = " ".join(f"{e} {s}" for e, s in GLOSARIO_ESTADOS_HORIZONTE)
    for prohibido in ("IC95", "IC80", "máximo estadístico", "tolerancia sMAPE", "horizonte recomendado"):
        assert prohibido.lower() not in texto_completo.lower()

    html = construir_html_explicacion_tarjeta("estado", None, "claro")
    assert "Glosario de estados" in html
    assert "Proyección técnica" in html
    assert "No admisible" in html
    for prohibido in ("IC95", "IC80"):
        assert prohibido not in html


# --------------------------------------------------------------- CASO 6
def test_caso6_proyecciones_icociv_eliminar_seleccionado_y_todo():
    ventana = VentanaPrincipal()
    widget = ventana.widget_proyecciones
    widget.proyecciones = [
        {"numero": 1, "item_ruta": "serie-a"},
        {"numero": 2, "item_ruta": "serie-b"},
    ]
    widget._refrescar_tabla_proyecciones()
    assert len(widget.proyecciones) == 2

    # Sin seleccion: no elimina nada (se informa, no se prueba el popup aqui).
    widget.tabla_proyecciones.clearSelection()
    widget.tabla_proyecciones.setCurrentIndex(QModelIndex())
    with patch.object(QMessageBox, "information", return_value=None) as info:
        widget._eliminar_proyeccion()
        assert info.called
    assert len(widget.proyecciones) == 2

    # Con seleccion: elimina solo esa fila.
    widget.tabla_proyecciones.selectRow(0)
    widget._eliminar_proyeccion()
    assert len(widget.proyecciones) == 1
    assert widget.proyecciones[0]["item_ruta"] == "serie-b"

    # Eliminar todo: cancelar conserva, confirmar vacia.
    widget.proyecciones.append({"numero": 2, "item_ruta": "serie-c"})
    widget._refrescar_tabla_proyecciones()
    assert len(widget.proyecciones) == 2
    with patch.object(widget, "_confirmar_eliminar_todo", return_value=False):
        widget._eliminar_todas_proyecciones()
    assert len(widget.proyecciones) == 2
    with patch.object(widget, "_confirmar_eliminar_todo", return_value=True):
        widget._eliminar_todas_proyecciones()
    assert widget.proyecciones == []
    assert widget.modelo_proyecciones.rowCount() == 0
    ventana.deleteLater()


# --------------------------------------------------------------- CASO 7
def test_caso7_empalme_eliminar_seleccionado_y_todo():
    ventana = VentanaPrincipal()
    widget = ventana.widget_empalme
    widget.calculos = [
        {"numero": 1, "item": "insumo-a"},
        {"numero": 2, "item": "insumo-b"},
    ]
    widget._actualizar_tabla()
    assert len(widget.calculos) == 2

    with patch.object(widget, "_fila_seleccionada", return_value=None):
        with patch.object(QMessageBox, "information", return_value=None) as info:
            widget.eliminar_seleccionado()
            assert info.called
    assert len(widget.calculos) == 2

    with patch.object(widget, "_fila_seleccionada", return_value=0):
        widget.eliminar_seleccionado()
    assert len(widget.calculos) == 1
    assert widget.calculos[0]["item"] == "insumo-b"

    widget.calculos.append({"numero": 2, "item": "insumo-c"})
    widget._actualizar_tabla()

    class _CajaCancelar:
        def __init__(self, *a, **k):
            self._boton_eliminar = object()

        def setIcon(self, *a):
            pass

        def setWindowTitle(self, *a):
            pass

        def setText(self, *a):
            pass

        def addButton(self, texto, rol):
            return self._boton_eliminar if texto == "Eliminar" else object()

        def exec(self):
            pass

        def clickedButton(self):
            return object()  # nunca es _boton_eliminar -> cancelar

    with patch("app_icociv.interfaz.widgets.empalme_iccp_icociv.QMessageBox", side_effect=lambda *a, **k: _CajaCancelar()):
        widget.eliminar_todo()
    assert len(widget.calculos) == 2  # cancelar conserva

    with patch.object(widget, "_fila_seleccionada", return_value=None):
        pass  # no-op, solo documenta que eliminar_todo no depende de seleccion

    class _CajaConfirmar(_CajaCancelar):
        def clickedButton(self):
            return self._boton_eliminar

    with patch("app_icociv.interfaz.widgets.empalme_iccp_icociv.QMessageBox", side_effect=lambda *a, **k: _CajaConfirmar()):
        widget.eliminar_todo()
    assert widget.calculos == []
    ventana.deleteLater()


def _principal() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    fallos = 0
    for nombre, funcion in pruebas:
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {nombre}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {nombre}: {type(exc).__name__}: {exc}")
    print()
    print("todas las pruebas pasan" if not fallos else f"{fallos} fallo(s) de {len(pruebas)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_principal())
