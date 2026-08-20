"""Pruebas dirigidas del cierre manual de alertas (fix-ui-pre-v1).

Detectado en prueba manual: el boton Cerrar/x de las alertas inferiores
derechas no respondia al clic. La causa mas defendible encontrada en revision
de codigo es que `VeloCarga` cubre TODO el contenedor `cuerpo` -la misma
esquina donde aparecen las alertas- y se eleva sobre sus hermanos al
mostrarse; una alerta ya visible antes de esa elevacion queda detras del velo
mientras este se desvanece (el desvanecimiento no bloquea clics, la
ocultacion real si). El fix reeleva las alertas activas (`reposicionar()`)
cada vez que `_establecer_ocupado` cambia el estado del velo. Estas pruebas
verifican el cierre en si (senal/callback, viudos invisibles, autocierre) y
la regresion concreta que motivo el fix.
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

from app_icociv.interfaz.animaciones import establecer_movimiento_reducido
from app_icociv.interfaz.componentes import GestorNotificaciones, VeloCarga
from app_icociv.interfaz.tema import hoja_estilos

_app: QApplication | None = None


def _aplicacion() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
        _app.setStyleSheet(hoja_estilos("claro"))
    return _app


_lienzos: list[QWidget] = []


def _lienzo() -> QWidget:
    base = QWidget()
    base.resize(1280, 800)
    base.show()
    _lienzos.append(base)
    return base


def test_una_alerta_se_cierra_con_su_boton() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    gestor = GestorNotificaciones(_lienzo())
    aviso = gestor.informacion("Aviso único")
    assert aviso in gestor._activas
    aviso.boton_cerrar.click()
    assert aviso not in gestor._activas
    assert not aviso.isVisible()
    establecer_movimiento_reducido(False)


def test_varias_alertas_el_cierre_es_individual() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    gestor = GestorNotificaciones(_lienzo())
    a = gestor.informacion("Primera")
    b = gestor.informacion("Segunda")
    c = gestor.informacion("Tercera")
    assert {a, b, c} <= set(gestor._activas)

    b.boton_cerrar.click()
    assert b not in gestor._activas
    assert a in gestor._activas and c in gestor._activas
    assert a.isVisible() and c.isVisible()
    # Ningun widget fantasma queda interceptando: los que cierran se ocultan.
    assert not b.isVisible()
    establecer_movimiento_reducido(False)


def test_cierre_manual_no_lanza_excepcion_si_se_repite() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    gestor = GestorNotificaciones(_lienzo())
    aviso = gestor.informacion("Repetido")
    aviso.boton_cerrar.click()
    # Un segundo clic (doble clic accidental, o la senal disparandose de nuevo
    # antes de que Qt destruya el widget) no debe fallar ni reintroducirlo.
    aviso.boton_cerrar.click()
    assert aviso not in gestor._activas
    establecer_movimiento_reducido(False)


def test_autocierre_programado_sigue_funcionando() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    gestor = GestorNotificaciones(_lienzo())
    aviso = gestor.mostrar("Se autocierra", permanencia=1)
    assert aviso in gestor._activas
    from PySide6.QtTest import QTest

    QTest.qWait(30)
    _aplicacion().processEvents()
    assert aviso not in gestor._activas, "El temporizador de autocierre no disparó cerrar()"
    establecer_movimiento_reducido(False)


def test_error_no_se_autocierra_y_su_boton_si_cierra() -> None:
    _aplicacion()
    establecer_movimiento_reducido(True)
    gestor = GestorNotificaciones(_lienzo())
    aviso = gestor.error("Error grave", "detalle")
    from PySide6.QtTest import QTest

    QTest.qWait(30)
    _aplicacion().processEvents()
    assert aviso in gestor._activas, "Un error no debe cerrarse solo"
    aviso.boton_cerrar.click()
    assert aviso not in gestor._activas
    establecer_movimiento_reducido(False)


def test_alerta_ya_visible_sigue_clicable_tras_ciclo_de_velo() -> None:
    """Regresión del fix: una alerta mostrada ANTES de una operación con velo
    de carga debe seguir siendo la que recibe el clic en su posición mientras
    el velo se desvanece, no solo después de que termine de ocultarse.

    Con animaciones REALES (no `movimiento_reducido`), porque el bug real
    ocurre durante los ~140 ms en que `VeloCarga.ocultar()` se desvanece: el
    efecto de opacidad no vuelve clicable lo que hay debajo, así que sin el
    fix el velo, aunque ya casi invisible, sigue interceptando el clic sobre
    el botón de cierre hasta que termina de ocultarse del todo.
    """
    _aplicacion()
    from PySide6.QtTest import QTest

    base = _lienzo()
    velo = VeloCarga(base)
    gestor = GestorNotificaciones(base)

    aviso = gestor.informacion("Visible antes del velo")
    QTest.qWait(300)  # que termine de deslizarse a su posición final
    boton = aviso.boton_cerrar
    punto = boton.mapTo(base, boton.rect().center())
    assert base.childAt(punto) is boton

    # El velo cubre todo `base` (mismo contenedor) y se eleva al mostrarse,
    # tal como hace VeloCarga.mostrar() sobre `cuerpo` en la ventana real.
    velo.mostrar("Ejecutando...")
    QTest.qWait(50)
    assert base.childAt(punto) is not boton, (
        "Con el velo activo la alerta debe quedar cubierta: así se reproduce "
        "la condición que dejaba el botón sin recibir clics."
    )

    velo.ocultar()
    # `_establecer_ocupado` llama a esto tras cada cambio del velo. Sin el
    # fix, aquí y durante el desvanecimiento el velo seguiría por delante.
    gestor.reposicionar()
    assert base.childAt(punto) is boton, (
        "Justo tras ocultar el velo (aún desvaneciéndose) la alerta ya debe "
        "recibir el clic en su posición."
    )
    QTest.qWait(60)
    assert base.childAt(punto) is boton, (
        "Mientras el velo termina de desvanecerse, la alerta debe seguir "
        "siendo la que recibe el clic."
    )
    aviso.boton_cerrar.click()
    assert aviso not in gestor._activas


if __name__ == "__main__":
    _aplicacion()
    fallos = 0
    pruebas = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    for nombre, funcion in pruebas:
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {nombre}: {exc}")
    print()
    print("todas las pruebas pasan" if not fallos else f"{fallos} fallo(s) de {len(pruebas)}")
    raise SystemExit(1 if fallos else 0)
