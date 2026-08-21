"""Pruebas dirigidas del horizonte de proyección en Empalme (fix-ui-pre-v1,
prompt "corregir definitivamente validación >24 meses y carga").

`calcular()` valida el horizonte (misma semántica que Proyecciones: meses
entre el último periodo ICOCIV real y la fecha objetivo) como PRIMER paso,
antes de construir `entrada` o llamar a cualquier otra validación del
formulario. +24 meses se ejecuta (asíncrono, vía el callback de proyección);
+25 se rechaza con un popup modal específico, sin llamar nunca al callback ni
tocar los datos ya ingresados.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app_icociv.interfaz.widgets.empalme_iccp_icociv import WidgetEmpalmeICCPICOCIV
from app_icociv.proyeccion.servicio_proyeccion import H_OPERATIVO_MAX

_app: QApplication | None = None


def _aplicacion() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _widget_listo(fecha_final_anio: int, fecha_final_mes: int) -> WidgetEmpalmeICCPICOCIV:
    """Widget con los campos mínimos para llegar a `calcular()` sin errores
    de formulario que enmascaren la validación de horizonte."""
    _aplicacion()
    w = WidgetEmpalmeICCPICOCIV()
    w.item.setText("Cemento")
    w.unidad.setCurrentIndex(1)
    w.cantidad.setValue(10)
    w.precio_base.setValue(1000)
    w.combo_tipo_iccp.setCurrentIndex(1)
    w._actualizar_series_iccp()
    w.combo_serie_iccp.setCurrentIndex(1)
    w.fecha_inicial_anio.setValue(2021)
    w.fecha_inicial_mes.setValue(1)
    w.fecha_final_anio.setValue(fecha_final_anio)
    w.fecha_final_mes.setValue(fecha_final_mes)
    return w


def _opcion_falsa(ultimo_periodo: str = "2026_5") -> dict:
    # calcular_empalme_iccp_icociv necesita el índice ICOCIV también en la
    # fecha inicial (2021_1, fija en _widget_listo) además del último real;
    # se cubre todo el rango mensual entre ambas para que el cálculo formal
    # se complete y así aislar la validación de horizonte, que es lo que
    # estas pruebas verifican.
    anio_u, mes_u = (int(p) for p in ultimo_periodo.split("_"))
    indices: dict[str, float] = {}
    anio, mes = 2020, 12
    valor = 100.0
    while (anio, mes) <= (anio_u, mes_u):
        indices[f"{anio}_{mes}"] = valor
        valor += 0.5
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return {
        "ruta": "Vías urbanas",
        "ruta_estructurada": [],
        "indices": indices,
        "seleccion": {"idx_g": 0},
    }


def test_h0_fecha_dentro_de_lo_observado_no_llama_proyeccion() -> None:
    w = _widget_listo(2026, 5)
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")
    llamadas = []
    w.configurar_proyeccion_icociv(lambda *a: llamadas.append(a))
    avisos = []
    QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(a))
    w.calcular()
    assert not llamadas, "h=0 no debe llamar a la proyección"
    assert not avisos, "h=0 no debe mostrar ninguna advertencia de horizonte"
    assert len(w.calculos) == 1
    assert w.calculos[0].get("icociv_final_es_proyectado") is False


def test_h1_permite_y_llama_a_la_proyeccion_una_vez() -> None:
    w = _widget_listo(2026, 6)  # +1 mes desde 2026_5
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")
    llamadas = []

    def callback(seleccion, anio, mes, al_terminar):
        llamadas.append((anio, mes))
        al_terminar(
            {
                "proyeccion": {
                    "resultado_horizonte_solicitado": {
                        "proyeccion_generada": True,
                        "indice_proyectado": 141.0,
                        "modelo_aplicado": "Drift",
                        "horizonte_solicitado": 1,
                        "estado": "proyeccion_tecnica",
                        "periodo_proyectado": "2026_6",
                        "razones_tecnicas": [],
                    },
                    "model_name": "Drift",
                }
            },
            None,
        )

    w.configurar_proyeccion_icociv(callback)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    w.calcular()
    assert llamadas == [(2026, 6)], "h=1 debe llamar exactamente una vez a la proyección"
    assert len(w.calculos) == 1
    assert w.calculos[0]["icociv_final_es_proyectado"] is True
    assert w.boton_calcular.isEnabled(), "el botón debe reactivarse al terminar"


def test_h24_permitido_y_llama_a_la_proyeccion_una_vez() -> None:
    # 2026_5 + 24 meses = 2028_5.
    w = _widget_listo(2028, 5)
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")
    llamadas = []

    def callback(seleccion, anio, mes, al_terminar):
        llamadas.append((anio, mes))
        al_terminar(
            {
                "proyeccion": {
                    "resultado_horizonte_solicitado": {
                        "proyeccion_generada": True,
                        "indice_proyectado": 160.0,
                        "modelo_aplicado": "Huber (robusta)",
                        "horizonte_solicitado": H_OPERATIVO_MAX,
                        "estado": "proyeccion_tecnica",
                        "periodo_proyectado": "2028_5",
                        "razones_tecnicas": [],
                    },
                    "model_name": "Huber (robusta)",
                }
            },
            None,
        )

    w.configurar_proyeccion_icociv(callback)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    w.calcular()
    assert llamadas == [(2028, 5)]
    assert len(w.calculos) == 1
    assert w.calculos[0]["icociv_final_es_proyectado"] is True


def test_h25_rechazado_sin_llamar_a_la_proyeccion() -> None:
    # 2026_5 + 25 meses = 2028_6.
    w = _widget_listo(2028, 6)
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")
    llamadas = []
    w.configurar_proyeccion_icociv(lambda *a: llamadas.append(a))
    avisos = []
    QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(a))
    w.calcular()
    assert not llamadas, "h=25 NO debe llamar nunca a la función de proyección"
    assert len(avisos) == 1
    titulo, mensaje = avisos[0][-2], avisos[0][-1]
    assert titulo == "Horizonte de proyección fuera del alcance de SAVIP"
    assert "25" in mensaje and str(H_OPERATIVO_MAX) in mensaje
    assert not w.calculos, "no debe guardarse ningún cálculo"
    # Los datos ingresados se conservan (nada los tocó).
    assert w.item.text() == "Cemento"
    assert w.fecha_final_anio.value() == 2028 and w.fecha_final_mes.value() == 6


def test_fecha_muy_futura_2036_rechazada_dinamicamente() -> None:
    """La prueba deriva h dinámicamente a partir del último real, sin
    hardcodear que 2036-08 sea >24 meses de nada fijo."""
    w = _widget_listo(2036, 8)
    ultimo = "2026_5"
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa(ultimo)
    h_esperado = w._horizonte_meses_icociv(_opcion_falsa(ultimo), "2036_8")
    assert h_esperado > H_OPERATIVO_MAX, "la fecha de prueba debe exceder el máximo operativo"

    llamadas = []
    w.configurar_proyeccion_icociv(lambda *a: llamadas.append(a))
    avisos = []
    QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(a))
    w.calcular()
    assert not llamadas
    assert len(avisos) == 1
    assert str(h_esperado) in avisos[0][-1]


def test_boton_se_reactiva_si_la_proyeccion_falla() -> None:
    w = _widget_listo(2026, 6)
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")

    def callback(seleccion, anio, mes, al_terminar):
        al_terminar(None, "fallo simulado del motor de proyección")

    w.configurar_proyeccion_icociv(callback)
    avisos = []
    QMessageBox.warning = staticmethod(lambda *a, **k: avisos.append(a))
    w.calcular()
    assert w.boton_calcular.isEnabled(), "el botón debe reactivarse aunque la proyección falle"
    assert not w.calculos
    assert avisos, "debe avisarse del fallo"


def test_boton_se_deshabilita_mientras_la_proyeccion_esta_en_curso() -> None:
    w = _widget_listo(2026, 6)
    w._opcion_icociv_o_vacia = lambda: _opcion_falsa("2026_5")
    estado_boton_durante: list[bool] = []

    def callback(seleccion, anio, mes, al_terminar):
        estado_boton_durante.append(w.boton_calcular.isEnabled())
        # no se llama a al_terminar: simula que sigue en curso.

    w.configurar_proyeccion_icociv(callback)
    w.calcular()
    assert estado_boton_durante == [False], "debe estar deshabilitado durante el cálculo"


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
