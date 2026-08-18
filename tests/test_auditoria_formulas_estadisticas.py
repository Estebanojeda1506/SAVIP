"""Auditoría de fórmulas estadísticas contra valores calculados a mano.

Cada prueba fija el resultado esperado de forma independiente del código
(cálculo manual o propiedad matemática) para que un cambio accidental en una
fórmula se detecte de inmediato. Documento de respaldo:
documentacion_latex/criterios_estadisticos_aplicacion/main.tex
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.metricas import (
    calcular_escala_naive_insample,
    calcular_mae,
    calcular_mape,
    calcular_mase,
    calcular_rmse,
    calcular_sesgo_medio,
    calcular_smape,
)
from app_icociv.estadistica.diagnostico_residuos import durbin_watson
from app_icociv.estadistica.modelos_interpretables import ajustar_modelo_interpretable
from app_icociv.validacion.backtesting import ejecutar_backtesting
from app_icociv.estadistica.criterios import matriz_criterios


Y_REAL = [100.0, 102.0, 104.0, 106.0]
Y_PRED = [101.0, 101.0, 105.0, 104.0]  # errores: -1, +1, -1, +2


def test_mae_rmse_sesgo_a_mano() -> None:
    assert abs(calcular_mae(Y_REAL, Y_PRED) - 1.25) < 1e-12
    assert abs(calcular_rmse(Y_REAL, Y_PRED) - np.sqrt(1.75)) < 1e-12
    assert abs(calcular_sesgo_medio(Y_REAL, Y_PRED) - 0.25) < 1e-12


def test_mape_a_mano_y_manejo_de_ceros() -> None:
    esperado = (1 / 100 + 1 / 102 + 1 / 104 + 2 / 106) / 4 * 100
    assert abs(calcular_mape(Y_REAL, Y_PRED) - esperado) < 1e-9
    # Con un observado en cero, el punto se excluye en lugar de dividir por cero.
    con_cero = calcular_mape([0.0, 100.0], [1.0, 101.0])
    assert np.isfinite(con_cero)
    assert abs(con_cero - 1.0) < 1e-9


def test_smape_a_mano_y_cota_teorica() -> None:
    esperado = np.mean([2 * 1 / 201, 2 * 1 / 203, 2 * 1 / 209, 2 * 2 / 210]) * 100
    assert abs(calcular_smape(Y_REAL, Y_PRED) - esperado) < 1e-9
    # sMAPE esta acotado en [0, 200] por construccion.
    assert calcular_smape([100.0], [-100.0]) <= 200.0 + 1e-9


def test_mase_usa_escala_del_entrenamiento() -> None:
    # Entrenamiento [90, 92, 96]: escala naive = mean(|2|, |4|) = 3.
    assert abs(calcular_escala_naive_insample([90.0, 92.0, 96.0]) - 3.0) < 1e-12
    assert abs(calcular_mase(Y_REAL, Y_PRED, [90.0, 92.0, 96.0]) - 1.25 / 3.0) < 1e-12
    # Cambiar el tramo de prueba no debe cambiar la escala (sin fuga).
    otra = calcular_mase([200.0, 204.0], [201.0, 203.0], [90.0, 92.0, 96.0])
    assert abs(otra - 1.0 / 3.0) < 1e-12


def test_durbin_watson_casos_limite() -> None:
    # Residuos alternantes -> DW cerca de 4; residuos muy persistentes -> cerca de 0.
    alternantes = [1.0, -1.0] * 10
    persistentes = list(np.linspace(1.0, 1.01, 20))
    assert durbin_watson(alternantes) > 3.5
    assert durbin_watson(persistentes) < 0.5
    # DW de ruido blanco razonablemente cerca de 2.
    rng = np.random.default_rng(7)
    assert 1.4 < durbin_watson(rng.normal(size=400)) < 2.6


def test_naive_y_drift_predicen_lo_esperado() -> None:
    t = np.arange(1.0, 25.0)
    y = 100.0 + 2.0 * (t - 1.0)  # lineal perfecta, ultimo valor 146
    naive = ajustar_modelo_interpretable("naive", t, y)
    drift = ajustar_modelo_interpretable("drift", t, y)
    # Naive repite el ultimo valor; Drift extrapola el cambio promedio (2/mes).
    assert abs(float(naive["predict"]([27.0])[0]) - 146.0) < 1e-9
    assert abs(float(drift["predict"]([27.0])[0]) - 152.0) < 1e-9


def _serie_mensual(valores: list[float]) -> pd.DataFrame:
    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(len(valores))]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def test_walk_forward_reentrena_y_no_filtra_futuro() -> None:
    """Con Drift sobre una serie lineal, cada predicción es reproducible a mano
    usando SOLO la historia previa al origen; un salto posterior no la altera."""
    n = 40
    valores = [100.0 + 2.0 * i for i in range(n)]
    base = ejecutar_backtesting(_serie_mensual(valores), anio_base=2021, horizonte=1, modelo="drift")
    assert base["ejecutado"] and base["iteraciones"] >= 6
    for _, fila in base["predicciones"].iterrows():
        m = int(fila["Observaciones_entrenamiento"])
        # Drift con historia lineal: y_m + h * (y_m - y_1)/(m-1) = valor exacto.
        esperado = valores[m - 1] + (valores[m - 1] - valores[0]) / (m - 1)
        assert abs(float(fila["Predicho"]) - esperado) < 1e-9

    # Un salto enorme en el ULTIMO punto no cambia ninguna prediccion anterior.
    con_salto = valores[:-1] + [valores[-1] + 500.0]
    alterado = ejecutar_backtesting(_serie_mensual(con_salto), anio_base=2021, horizonte=1, modelo="drift")
    p0 = base["predicciones"]["Predicho"].to_numpy(float)[:-1]
    p1 = alterado["predicciones"]["Predicho"].to_numpy(float)[:-1]
    assert np.allclose(p0, p1)


def test_intervalos_ic80_dentro_de_ic95_y_ancho_crece() -> None:
    """El anidamiento IC80 subset IC95 y el crecimiento del ancho, en el calculo interno.

    P0-C / ESTRATEGIA C2, 15-08-2026. Esta prueba leia los limites de la tabla
    PUBLICA. Desde el retiro, el objeto publico no entrega limites en ningun
    caso: `float(None)` levantaba, y aunque no lo hiciera, la comprobacion habria
    dejado de medir algo.

    La propiedad NO se abandona -es matematica y sigue siendo cierta-: se mide
    donde sigue siendo observable, en el resultado anterior al corte de
    publicacion, reproduciendo la composicion de `ejecutar_proyeccion` sin su
    ultimo paso. Se anade ademas la comprobacion de que el objeto publico no
    entrega ninguno de esos limites, que antes no existia.
    """
    from app_icociv.proyeccion.servicio_proyeccion import (
        _ejecutar_proyeccion_base,
        _estructurar_resultado_horizontes,
        ejecutar_proyeccion,
    )

    rng = np.random.default_rng(11)
    valores = [100.0 + 0.6 * i + float(rng.normal(0, 0.8)) for i in range(60)]
    serie = _serie_mensual(valores)

    interno = _estructurar_resultado_horizontes(
        _ejecutar_proyeccion_base(
            serie_df=serie, year_proj=2026, month_proj=6, anio_base=2021
        ),
        "predeterminado",
    )
    proy = interno.get("proyecciones")
    assert isinstance(proy, pd.DataFrame) and not proy.empty
    anchos = []
    for _, fila in proy.iterrows():
        i80, s80 = float(fila["limite_inferior_80"]), float(fila["limite_superior_80"])
        i95, s95 = float(fila["limite_inferior_95"]), float(fila["limite_superior_95"])
        assert i95 <= i80 <= s80 <= s95
        assert i80 <= float(fila["indice_proyectado"]) <= s80
        anchos.append(s95 - i95)
    # El ancho del ultimo horizonte no debe ser menor que el del primero.
    assert anchos[-1] >= anchos[0] - 1e-9

    # Y nada de eso llega al usuario: el objeto publico no entrega limites.
    publico = ejecutar_proyeccion(serie, 2026, 6, 2021)
    for columna in ("limite_inferior_80", "limite_superior_80",
                    "limite_inferior_95", "limite_superior_95"):
        assert publico["proyecciones"][columna].isna().all() or \
            all(v is None for v in publico["proyecciones"][columna]), columna


def test_matriz_criterios_cubre_constantes_clave() -> None:
    """Toda familia de umbrales relevante debe tener entrada auditable."""
    ids = {c.id for c in matriz_criterios()}
    for requerido in (
        "C-DAT-001", "C-WF-001", "C-WF-002", "C-ATI-001", "C-DW-001",
        "C-RES-001", "C-MASE-001", "C-ERR-001",
        "C-INT-001", "C-INT-002", "C-INT-003", "C-HOR-003",
        "C-MOD-001", "C-BEN-001", "C-CAL-001", "C-CAL-002",
        "C-EST-001",
    ):
        assert requerido in ids, f"Falta el criterio {requerido} en la matriz auditable."
    # El ensamble fue retirado: su criterio no debe reaparecer.
    assert "C-ENS-001" not in ids
    # D-8: las bandas de proporcion de errores extremos (15 / 25 / 50 %) se
    # retiraron; su criterio tampoco debe reaparecer.
    assert "C-ERR-002" not in ids
    # D-9: las bandas internas de MAPE, sMAPE y sesgo se retiraron. Solo
    # sobrevive C-MASE-001, la comparacion de MASE frente a 1, que si tiene
    # fuente. Sus criterios no deben reaparecer.
    for retirado in ("C-MAPE-001", "C-SMAPE-001", "C-SES-001"):
        assert retirado not in ids, f"{retirado} reapareció en la matriz"


def test_ets_retirado_del_catalogo() -> None:
    """D-1: ETS retirado (sin statsmodels duplicaba exactamente a Holt amortiguado)."""
    from app_icociv.estadistica.modelos_interpretables import (
        MODELOS_INTERPRETABLES,
        MODELOS_SERIE_TEMPORAL,
    )
    from app_icociv.proyeccion.servicio_proyeccion import (
        CATALOGO_MODELOS_CANDIDATOS,
        MODELOS_PARAMETRO_SIN_SUSTENTO,
    )

    assert "ets" not in MODELOS_INTERPRETABLES
    assert "ets" not in MODELOS_SERIE_TEMPORAL
    assert "ets" not in CATALOGO_MODELOS_CANDIDATOS
    # AUDITORIA 09-08-2026 (P0-B): `MODELOS_NIVEL_2` se retiro -estaba muerta y
    # no coincidia con la lista que el codigo usaba-. La propiedad que esta
    # prueba fija se comprueba ahora sobre el catalogo vivo.
    assert "ets" not in MODELOS_PARAMETRO_SIN_SUSTENTO


def test_ets_ya_no_es_ajustable() -> None:
    t = np.arange(12, dtype=float)
    y = 100.0 + 0.8 * t
    try:
        ajustar_modelo_interpretable("ets", t, y)
    except ValueError:
        return
    raise AssertionError("ETS fue retirado del alcance; no debe ser ajustable.")


def test_holt_sigue_operativo_sin_ets() -> None:
    t = np.arange(24, dtype=float)
    y = 100.0 * (1.004 ** t)
    for nombre in ("holt_lineal", "holt_amortiguado"):
        modelo = ajustar_modelo_interpretable(nombre, t, y)
        proyeccion = modelo["predict"](np.array([24.0, 25.0, 26.0]))
        assert np.all(np.isfinite(proyeccion)), nombre


def test_fuentes_sin_clave_ets_funcional() -> None:
    """Ningún módulo del flujo real debe conservar la clave de modelo "ets"."""
    raiz = ROOT / "app_icociv"
    for relativo in (
        "estadistica/modelos_interpretables.py",
        "proyeccion/servicio_proyeccion.py",
        "reportes/generador_reportes.py",
    ):
        codigo = (raiz / relativo).read_text(encoding="utf-8", errors="ignore")
        assert '"ets"' not in codigo, f"Clave de modelo 'ets' aun presente en {relativo}"


if __name__ == "__main__":
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: auditoria de fórmulas estadísticas.")
