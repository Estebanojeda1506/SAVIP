"""Sincronización bidireccional de los parámetros de proyección.

Cubre el defecto detectado el 19 de julio de 2026: al editar manualmente año y
mes, los controles superiores no se actualizaban y "Ejecutar proyección" usaba
el valor viejo del desplegable (por ejemplo, 1 mes en vez de 18).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402


def _ventana(ultimo_periodo: str = "2026_5"):
    """Ventana con periodos simulados; no requiere cargar un anexo real."""
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    QApplication.instance() or QApplication([])
    ventana = VentanaPrincipal()
    anio, mes = (int(x) for x in ultimo_periodo.split("_"))
    total = anio * 12 + (mes - 1)
    ventana.controlador.periodos = [
        f"{(total - i) // 12}_{(total - i) % 12 + 1}" for i in range(24, -1, -1)
    ]
    ventana._ajustar_periodo_por_defecto(ventana.controlador.periodos)
    return ventana


def test_combo_actualiza_fecha_objetivo() -> None:
    v = _ventana("2026_5")
    for horizonte, (anio, mes) in {1: (2026, 6), 3: (2026, 8), 18: (2027, 11)}.items():
        v.combo_horizonte.setCurrentIndex(v.combo_horizonte.findData(horizonte))
        assert v.spin_anio.value() == anio, (horizonte, v.spin_anio.value())
        assert v.spin_mes.value() == mes, (horizonte, v.spin_mes.value())
        assert v.spin_horizonte_personalizado.value() == horizonte
        assert v._horizonte_solicitado() == horizonte


def test_fecha_objetivo_actualiza_horizonte() -> None:
    """Caso reportado: editar año/mes debe recalcular el horizonte."""
    v = _ventana("2026_5")
    v.combo_horizonte.setCurrentIndex(v.combo_horizonte.findData(1))
    assert v._horizonte_solicitado() == 1

    v.spin_anio.setValue(2027)
    v.spin_mes.setValue(11)
    # 2026-05 -> 2027-11 son 18 meses.
    assert v._horizonte_solicitado() == 18, v._horizonte_solicitado()
    assert v.spin_horizonte_personalizado.value() == 18
    assert v.combo_horizonte.currentData() in (18, None)


def test_meses_personalizados_actualizan_fecha() -> None:
    v = _ventana("2026_5")
    v.combo_horizonte.setCurrentIndex(v.combo_horizonte.findData(None))
    v.spin_horizonte_personalizado.setValue(9)
    assert (v.spin_anio.value(), v.spin_mes.value()) == (2027, 2)
    assert v._horizonte_solicitado() == 9


def test_fecha_anterior_da_horizonte_no_positivo() -> None:
    v = _ventana("2026_5")
    v.spin_anio.setValue(2025)
    v.spin_mes.setValue(1)
    assert v._horizonte_solicitado() <= 0
    assert "posterior" in v.lbl_horizonte_recomendado.text().lower()


def test_cambio_de_serie_recalcula_fecha() -> None:
    v = _ventana("2026_5")
    v.combo_horizonte.setCurrentIndex(v.combo_horizonte.findData(3))
    assert (v.spin_anio.value(), v.spin_mes.value()) == (2026, 8)
    # Nueva serie que termina antes.
    v.controlador.periodos = [f"2025_{i}" for i in range(1, 13)]
    v._ajustar_periodo_por_defecto(v.controlador.periodos)
    v.combo_horizonte.setCurrentIndex(v.combo_horizonte.findData(3))
    assert (v.spin_anio.value(), v.spin_mes.value()) == (2026, 3), (
        v.spin_anio.value(), v.spin_mes.value()
    )


def test_sin_ciclos_infinitos() -> None:
    """La sincronización cruzada debe estabilizarse, no oscilar."""
    v = _ventana("2026_5")
    v.spin_anio.setValue(2027)
    v.spin_mes.setValue(6)
    horizonte = v._horizonte_solicitado()
    anio, mes = v.spin_anio.value(), v.spin_mes.value()
    # Reaplicar el mismo horizonte no debe mover la fecha.
    v._sincronizar_periodo_desde_horizonte()
    assert (v.spin_anio.value(), v.spin_mes.value()) == (anio, mes)
    assert v._horizonte_solicitado() == horizonte
    assert v._sincronizando is False


if __name__ == "__main__":
    test_combo_actualiza_fecha_objetivo()
    test_fecha_objetivo_actualiza_horizonte()
    test_meses_personalizados_actualizan_fecha()
    test_fecha_anterior_da_horizonte_no_positivo()
    test_cambio_de_serie_recalcula_fecha()
    test_sin_ciclos_infinitos()
    print("Pruebas de sincronizacion de horizonte OK")
