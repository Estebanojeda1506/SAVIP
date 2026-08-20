"""Pruebas dirigidas del horizonte de proyección en Empalme (fix-ui-pre-v1).

`_preparar_icociv_para_empalme` reutiliza la misma semántica de horizonte que
el módulo Proyecciones (meses entre el último periodo real y la fecha
objetivo, acotados a H_OPERATIVO_MAX=24): +24 meses se ejecuta con normalidad,
+25 se rechaza sin ejecutar ninguna proyección, con un mensaje claro que cita
el máximo operativo, y sin tocar los datos ya cargados en `opcion`.
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


def _widget() -> WidgetEmpalmeICCPICOCIV:
    _aplicacion()
    return WidgetEmpalmeICCPICOCIV()


def _opcion(ultimo_periodo: str = "2026_1") -> dict:
    # Serie mensual sintetica de 65 observaciones que termina en ultimo_periodo,
    # suficiente para que el ultimo real sea ese periodo.
    anio, mes = (int(p) for p in ultimo_periodo.split("_"))
    indices = {ultimo_periodo: 140.2}
    return {
        "ruta": "Vías urbanas",
        "ruta_estructurada": [],
        "indices": indices,
        "seleccion": {"idx_g": 0},
    }


def test_sin_proyeccion_fecha_dentro_de_lo_observado() -> None:
    """La fecha final ya está en la serie: no se llama al callback."""
    widget = _widget()
    llamadas: list[tuple] = []
    widget.configurar_proyeccion_icociv(lambda *a: llamadas.append(a) or {"proyeccion": {}})
    opcion = _opcion("2026_1")
    resultado = widget._preparar_icociv_para_empalme(opcion, "2026_1")
    assert not llamadas
    assert resultado["metadata_proyeccion"]["icociv_final_es_proyectado"] is False


def test_mas_1_mes_ejecuta_normalmente() -> None:
    widget = _widget()
    llamadas: list[tuple] = []

    def callback(seleccion, anio, mes):
        llamadas.append((anio, mes))
        return {
            "proyeccion": {
                "resultado_horizonte_solicitado": {
                    "proyeccion_generada": True,
                    "indice_proyectado": 141.0,
                    "modelo_aplicado": "Drift",
                    "horizonte_solicitado": 1,
                    "estado": "proyeccion_tecnica",
                    "periodo_proyectado": "2026_2",
                    "razones_tecnicas": [],
                },
                "model_name": "Drift",
            }
        }

    widget.configurar_proyeccion_icociv(callback)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    opcion = _opcion("2026_1")
    resultado = widget._preparar_icociv_para_empalme(opcion, "2026_2")
    assert llamadas == [(2026, 2)]
    assert resultado["metadata_proyeccion"]["icociv_final_es_proyectado"] is True
    assert resultado["indices"]["2026_2"] == 141.0


def test_mas_24_meses_permitido() -> None:
    widget = _widget()
    llamadas: list[tuple] = []

    def callback(seleccion, anio, mes):
        llamadas.append((anio, mes))
        return {
            "proyeccion": {
                "resultado_horizonte_solicitado": {
                    "proyeccion_generada": True,
                    "indice_proyectado": 160.0,
                    "modelo_aplicado": "Huber (robusta)",
                    "horizonte_solicitado": H_OPERATIVO_MAX,
                    "estado": "proyeccion_tecnica",
                    "periodo_proyectado": "2028_1",
                    "razones_tecnicas": [],
                },
                "model_name": "Huber (robusta)",
            }
        }

    widget.configurar_proyeccion_icociv(callback)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    opcion = _opcion("2026_1")
    # 2026_1 + 24 meses = 2028_1.
    resultado = widget._preparar_icociv_para_empalme(opcion, "2028_1")
    assert llamadas, "+24 meses debe ejecutar la proyección"
    assert resultado["metadata_proyeccion"]["icociv_final_es_proyectado"] is True


def test_mas_25_meses_rechazado_sin_ejecutar() -> None:
    widget = _widget()
    llamadas: list[tuple] = []
    widget.configurar_proyeccion_icociv(lambda *a: llamadas.append(a) or {})
    opcion = _opcion("2026_1")
    opcion_original = dict(opcion)
    try:
        # 2026_1 + 25 meses = 2028_2.
        widget._preparar_icociv_para_empalme(opcion, "2028_2")
        assert False, "debe rechazar +25 meses con ValueError"
    except ValueError as exc:
        mensaje = str(exc)
        assert str(H_OPERATIVO_MAX) in mensaje
        assert "máximo operativo" in mensaje or "horizonte operativo máximo" in mensaje
    assert not llamadas, "no debe ejecutarse ninguna proyección si excede el máximo operativo"
    # Los datos de entrada no se tocan: la excepción se lanza antes de mutar nada.
    assert opcion == opcion_original


def test_sin_callback_conectado_no_ejecuta_y_avisa() -> None:
    widget = _widget()
    opcion = _opcion("2026_1")
    try:
        widget._preparar_icociv_para_empalme(opcion, "2026_2")
        assert False, "sin callback debe rechazarse"
    except ValueError:
        pass


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
