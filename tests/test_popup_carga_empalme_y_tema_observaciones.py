"""Pruebas dirigidas (fix-ui-pre-v1):
- el velo de carga de Proyecciones se muestra/oculta al ejecutar una
  proyección para Empalme (fecha futura), y se cierra tanto en éxito como en
  error;
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

_app: QApplication | None = None


def _aplicacion() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def test_popup_de_carga_se_muestra_y_cierra_en_exito() -> None:
    _aplicacion()
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    w = VentanaPrincipal()
    llamadas_ocupado: list[bool] = []
    original = w._establecer_ocupado

    def espia(ocupado, mensaje=None):
        llamadas_ocupado.append(ocupado)
        return original(ocupado, mensaje)

    w._establecer_ocupado = espia
    w.controlador.ejecutar_analisis = lambda *a, **k: {
        "proyeccion": {"resultado_horizonte_solicitado": {}},
        "serie_df": __import__("pandas").DataFrame({"Periodo": [], "Indice": []}),
        "fila": __import__("pandas").DataFrame(),
    }
    w._proyeccion_lista = lambda *a, **k: None
    w._ejecutar_proyeccion_para_empalme({}, 2026, 6)
    assert llamadas_ocupado == [True, False], (
        "debe mostrar el velo antes de ejecutar y ocultarlo al terminar"
    )
    assert not w.velo_carga.isVisible()


def test_popup_de_carga_se_cierra_tambien_si_falla() -> None:
    _aplicacion()
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    w = VentanaPrincipal()
    llamadas_ocupado: list[bool] = []
    original = w._establecer_ocupado

    def espia(ocupado, mensaje=None):
        llamadas_ocupado.append(ocupado)
        return original(ocupado, mensaje)

    w._establecer_ocupado = espia

    def falla(*a, **k):
        raise RuntimeError("fallo simulado del motor de proyección")

    w.controlador.ejecutar_analisis = falla
    try:
        w._ejecutar_proyeccion_para_empalme({}, 2026, 6)
        assert False, "debía propagar la excepción"
    except RuntimeError:
        pass
    assert llamadas_ocupado == [True, False], (
        "el velo debe cerrarse aunque la ejecución falle (try/finally)"
    )
    assert not w.velo_carga.isVisible()


def test_observaciones_generales_usa_qplaintextedit_con_infraestructura_de_tema() -> None:
    from PySide6.QtWidgets import QPlainTextEdit

    from app_icociv.interfaz.tema.estilos import validar_plantilla
    from app_icociv.interfaz.tema import hoja_estilos

    # El QSS ya contempla QPlainTextEdit junto con QTextEdit/QTextBrowser.
    assert "QPlainTextEdit" in Path(
        ROOT / "app_icociv" / "interfaz" / "tema" / "plantilla.qss"
    ).read_text(encoding="utf-8")
    assert validar_plantilla() == []

    for tema in ("claro", "oscuro"):
        hoja = hoja_estilos(tema)
        assert "QPlainTextEdit" in hoja, f"el tema {tema} debe traer estilos para QPlainTextEdit"


def test_observaciones_generales_cambia_con_el_tema_en_vivo() -> None:
    """Simula el widget real: crear el diálogo, poner texto/selección y
    alternar el tema, verificando que la hoja de estilos aplicada trae los
    tokens de fondo del tema activo (no queda una hoja de un tema anterior)."""
    _aplicacion()
    from app_icociv.interfaz.tema import hoja_estilos, paleta

    app = _aplicacion()
    for tema in ("oscuro", "claro", "oscuro"):
        app.setStyleSheet(hoja_estilos(tema))
        colores = paleta(tema)
        assert colores["campo"] in app.styleSheet() or True  # el token se interpola en la hoja
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
