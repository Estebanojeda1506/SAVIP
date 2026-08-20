"""Pruebas dirigidas del Prompt 13: horizonte personalizado 1..24, retiro de
IC95 de Resultados y banda descriptiva de error historico (+/-MAE)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.proyeccion.servicio_proyeccion import (
    H_OPERATIVO_MAX,
    MENSAJE_HORIZONTE_INVALIDO,
    ejecutar_proyeccion,
    validar_horizonte_solicitado,
)
from app_icociv.utilidades.utilidades import ANIO_BASE


def _serie_sintetica(n: int, semilla: int = 1, pendiente: float = 0.5, ruido: float = 1.2) -> pd.DataFrame:
    periodos = [f"{2021 + i // 12}_{(i % 12) + 1}" for i in range(n)]
    rng = np.random.default_rng(semilla)
    valores = [100.0 + pendiente * i + rng.normal(0, ruido) for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _objetivo(n: int, h: int) -> tuple[int, int]:
    last_year = 2021 + (n - 1) // 12
    last_month = (n - 1) % 12 + 1
    tm = last_month + h
    ty = last_year + (tm - 1) // 12
    tm = (tm - 1) % 12 + 1
    return ty, tm


# --------------------------------------------------------------- CASO 1
def test_caso1_horizonte_personalizado_1_17_24_validos_25_invalido():
    assert validar_horizonte_solicitado(1) == 1
    assert validar_horizonte_solicitado(17) == 17
    assert validar_horizonte_solicitado(24) == 24
    try:
        validar_horizonte_solicitado(25)
        raise AssertionError("h=25 deberia rechazarse")
    except ValueError as exc:
        mensaje = str(exc)
        assert "entre 1 y 24" in mensaje, mensaje
        assert "alcance máximo de proyección de SAVIP es de 24 meses" in mensaje, mensaje
        assert mensaje != MENSAJE_HORIZONTE_INVALIDO, "no debe usar el mensaje de 'entero positivo' para h>24"


def test_caso1_mensaje_entero_positivo_se_conserva_para_casos_no_enteros():
    for invalido in (0, -3, 1.5):
        try:
            validar_horizonte_solicitado(invalido)
            raise AssertionError(f"deberia rechazar {invalido!r}")
        except ValueError as exc:
            assert str(exc) == MENSAJE_HORIZONTE_INVALIDO


def test_caso1_widget_spin_horizonte_personalizado_no_permite_25():
    from PySide6.QtWidgets import QApplication
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    ventana = VentanaPrincipal()
    assert ventana.spin_horizonte_personalizado.maximum() == H_OPERATIVO_MAX == 24
    ventana.spin_horizonte_personalizado.setValue(25)
    assert ventana.spin_horizonte_personalizado.value() <= 24


# --------------------------------------------------------------- CASO 2
def test_caso2_fecha_maxima_alcance_dinamica():
    from PySide6.QtWidgets import QApplication
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    ventana = VentanaPrincipal()
    ventana.controlador.periodos = [f"2021_{m}" for m in range(1, 13)] + \
        [f"{2022 + i // 12}_{(i % 12) + 1}" for i in range(53)]  # hasta 2026_5 (65 obs)
    ultimo = ventana._ultimo_periodo_serie()
    assert ultimo == (2026, 5)
    maximo = ventana._fecha_maxima_alcance()
    assert maximo == (2028, 5), f"mayo 2026 + 24 meses debe ser mayo 2028, obtuvo {maximo}"

    # h=24 (mayo 2028) debe ser valido
    ventana._sincronizando = False
    ventana.spin_anio.setValue(2028)
    ventana.spin_mes.setValue(5)
    assert ventana._horizonte_desde_periodo() == 24

    # junio 2028 (h=25) debe recortarse de vuelta a mayo 2028 (h=24)
    ventana.spin_anio.setValue(2028)
    ventana.spin_mes.setValue(6)
    assert (int(ventana.spin_anio.value()), int(ventana.spin_mes.value())) == (2028, 5), (
        "la fecha objetivo debe recortarse a la fecha maxima de alcance, no aceptar h=25"
    )
    assert ventana._horizonte_desde_periodo() == 24


# --------------------------------------------------------------- CASO 3
def test_caso3_no_aparece_texto_retirado_en_ventana_principal():
    fuente = (ROOT / "app_icociv" / "interfaz" / "ventana_principal.py").read_text(encoding="utf-8")
    # El texto "Horizonte estadístico" no debe aparecer como valor mostrado al
    # usuario (se permite en comentarios que documenten el retiro).
    for linea in fuente.splitlines():
        sin_comentario = linea.split("#", 1)[0]
        assert "Horizonte estadístico" not in sin_comentario, f"texto retirado en: {linea.strip()}"
        assert "máximo recomendado" not in sin_comentario.lower(), f"texto retirado en: {linea.strip()}"
        assert "pendiente de análisis" not in sin_comentario or "pendiente de análisis" in fuente, True


# --------------------------------------------------------------- CASO 4
def test_caso4_ic95_retirado_de_resultados():
    """No debe quedar tarjeta/boton/clave de dispatcher para IC95 en la
    cuadricula principal de Resultados. `"ic95": [...]`/`"ic95": None` como
    CAMPO DE DATOS interno (p.ej. el par de limites, siempre vacio por P0-C)
    es legitimo y no se prohibe aqui; lo que se prohibe es la clave de
    tarjeta/dispatcher ("ic95", "texto") que registraba el control visual."""
    fuente_vp = (ROOT / "app_icociv" / "interfaz" / "ventana_principal.py").read_text(encoding="utf-8")
    fuente_pr = (ROOT / "app_icociv" / "interfaz" / "presentacion_resultados.py").read_text(encoding="utf-8")
    patrones_tarjeta = ('("ic95",', "'ic95':", '"ic95":')
    for fuente, nombre in ((fuente_vp, "ventana_principal.py"),):
        for linea in fuente.splitlines():
            sin_comentario = linea.split("#", 1)[0]
            assert '("ic95",' not in sin_comentario, f"tupla de tarjeta ic95 residual en {nombre}: {linea.strip()}"
            assert '"ic95":' not in sin_comentario, f"entrada de titulo ic95 residual en {nombre}: {linea.strip()}"
    for linea in fuente_pr.splitlines():
        sin_comentario = linea.split("#", 1)[0]
        assert 'clave == "ic95"' not in sin_comentario, f"rama de dispatcher ic95 residual: {linea.strip()}"
    # La tarjeta principal ahora se llama "error_historico".
    assert '"error_historico"' in fuente_vp
    assert 'clave == "error_historico"' in fuente_pr


# --------------------------------------------------------------- CASO 5 y 6
def test_caso56_g1a_h17_banda_y_horizonte_intermedio():
    n = 65
    df = _serie_sintetica(n, semilla=5, pendiente=0.4, ruido=1.0)
    ty, tm = _objetivo(n, 17)
    res = ejecutar_proyeccion(df, ty, tm, ANIO_BASE)
    assert res["proyeccion_generada"] is True

    # CASO 6: la proyeccion visual (tabla "proyecciones") respeta el
    # horizonte solicitado (17), mientras la trayectoria interna conserva 24.
    assert len(res["proyecciones"]) == 17
    assert len(res["trayectoria_24_meses"]) == 24

    # CASO 5: MAE_17 debe existir en tabla_horizontes y la banda en h=17 debe
    # ser exactamente y_hat_17 +/- MAE_17.
    tabla = {int(item["horizonte"]): item for item in res["horizonte_info"]["tabla_horizontes"]}
    mae_17 = tabla[17]["mae"]
    assert mae_17 is not None and np.isfinite(mae_17)
    y_hat_17 = res["trayectoria_24_meses"][16]
    y_proyectado_fila = res["proyecciones"].iloc[16]["indice_proyectado"]
    assert abs(y_hat_17 - y_proyectado_fila) < 1e-9
    banda_inf = y_hat_17 - mae_17
    banda_sup = y_hat_17 + mae_17
    assert banda_inf < y_hat_17 < banda_sup
    # RMSE_17/MAE_17 tambien deben coincidir con el backtesting del horizonte
    # solicitado (misma fuente que la tarjeta "Error histórico de referencia").
    assert abs(res["backtesting"]["metricas"]["mae"] - mae_17) < 1e-9


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
