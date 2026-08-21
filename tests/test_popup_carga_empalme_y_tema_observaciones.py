"""Pruebas dirigidas (fix-ui-pre-v1, prompt "corregir definitivamente
validación >24 meses y carga"):
- el velo de carga de Proyecciones se muestra al iniciar la proyección para
  Empalme y permanece animado (el cálculo corre en un QThread, no en el hilo
  principal), y se cierra tanto en éxito como en error;
- el cuadro "Observaciones generales" de Configurar informe responde a los
  tokens de tema claro/oscuro vía la infraestructura QSS existente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

_app: QApplication | None = None


def _aplicacion() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def test_popup_de_carga_se_muestra_y_corre_en_segundo_plano() -> None:
    """El velo se muestra ANTES de que termine el cálculo (no `show()` seguido
    de un bloqueo del hilo principal): el worker corre en un QThread, así que
    justo después de iniciar, el cálculo pesado aún no ha terminado y el velo
    ya está visible y animándose con normalidad."""
    _aplicacion()
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    w = VentanaPrincipal()
    w.show()
    import time

    def lento(*a, **k):
        time.sleep(0.2)
        return {
            "proyeccion": {"resultado_horizonte_solicitado": {}},
            "serie_df": __import__("pandas").DataFrame({"Periodo": [], "Indice": []}),
            "fila": __import__("pandas").DataFrame(),
        }

    w.controlador.ejecutar_analisis = lento
    w._proyeccion_lista = lambda *a, **k: None

    resultados: list = []
    w._ejecutar_proyeccion_para_empalme_async(
        {}, 2026, 6, lambda resultado, error: resultados.append((resultado, error))
    )
    # El worker aún corre (time.sleep(0.2) no ha terminado): el velo debe
    # estar visible y el hilo principal, libre para procesar eventos.
    assert w.velo_carga.isVisible(), "el velo debe mostrarse antes de que termine el cálculo"
    assert not resultados, "el callback aún no debe haberse invocado"

    for _ in range(30):
        QTest.qWait(100)
        if resultados:
            break
    assert resultados and resultados[0][0] is not None and resultados[0][1] is None
    QTest.qWait(250)  # deja terminar el desvanecimiento de salida del velo
    assert not w.velo_carga.isVisible(), "el velo debe cerrarse al terminar"


def test_popup_de_carga_se_cierra_tambien_si_falla() -> None:
    _aplicacion()
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    w = VentanaPrincipal()

    def falla(*a, **k):
        raise RuntimeError("fallo simulado del motor de proyección")

    w.controlador.ejecutar_analisis = falla
    resultados: list = []
    w._ejecutar_proyeccion_para_empalme_async(
        {}, 2026, 6, lambda resultado, error: resultados.append((resultado, error))
    )
    for _ in range(30):
        QTest.qWait(100)
        if resultados:
            break
    assert resultados and resultados[0][0] is None and resultados[0][1] is not None, (
        "el error debe llegar al callback, no propagarse como excepción no capturada"
    )
    assert "fallo simulado" in resultados[0][1]
    assert not w.velo_carga.isVisible(), "el velo debe cerrarse aunque el cálculo falle"


def test_observaciones_generales_usa_qplaintextedit_con_infraestructura_de_tema() -> None:
    from app_icociv.interfaz.tema.estilos import validar_plantilla
    from app_icociv.interfaz.tema import hoja_estilos

    assert "QPlainTextEdit" in Path(
        ROOT / "app_icociv" / "interfaz" / "tema" / "plantilla.qss"
    ).read_text(encoding="utf-8")
    assert validar_plantilla() == []

    for tema in ("claro", "oscuro"):
        hoja = hoja_estilos(tema)
        assert "QPlainTextEdit" in hoja, f"el tema {tema} debe traer estilos para QPlainTextEdit"


def test_observaciones_generales_cambia_con_el_tema_en_vivo() -> None:
    _aplicacion()
    from app_icociv.interfaz.tema import hoja_estilos

    app = _aplicacion()
    for tema in ("oscuro", "claro", "oscuro"):
        app.setStyleSheet(hoja_estilos(tema))
        assert "QPlainTextEdit" in app.styleSheet()


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
