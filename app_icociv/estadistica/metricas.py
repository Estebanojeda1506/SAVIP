"""Métricas estadísticas y predictivas para modelos interpretables."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app_icociv.estadistica.criterios import (
    ADVERTENCIA_MIN_OBS,
    EPS_NUMERICO,
    FACTOR_Z_MODIFICADO,
    MIN_OBS_RECOMENDADAS,
    UMBRAL_Z_MODIFICADO_ATIPICO,
)

MIN_OBS = MIN_OBS_RECOMENDADAS


def detectar_errores_extremos(errores: Any, periodos: Any = None) -> dict[str, Any]:
    """Marca errores de backtesting inusuales con el puntaje z modificado.

    Decisión D-8. La versión anterior comparaba ``|e|`` contra
    ``mediana(|e|) + 3 MAD`` —o contra ``3 x mediana(|e|)`` cuando el MAD era
    nulo—, un corte de implementación sin respaldo bibliográfico. Se sustituye
    por el puntaje z modificado de Iglewicz y Hoaglin (1993), recogido en el
    NIST/SEMATECH e-Handbook §1.3.5.17:

    ``M_i = 0.6745 (x_i - mediana) / MAD``,  atípico si ``|M_i| > 3.5``.

    Es la misma regla y el mismo umbral que la aplicación ya emplea para las
    variaciones de la serie, de modo que existe un único criterio de atípico.

    **Alcance.** El resultado es descriptivo. La proporción de errores extremos
    no bloquea, no degrada, no recorta el horizonte y no cambia el modelo, el
    pronóstico ni el intervalo. Se publica para revisión técnica.

    Cuando el MAD es nulo el puntaje no está definido: se declara no calculable
    en lugar de sustituirlo por una regla alternativa.
    """
    e = np.asarray(errores, dtype=float)
    finitos = np.isfinite(e)
    abs_err = np.abs(e[finitos])
    etiquetas: list[str] = []
    if periodos is not None:
        crudas = [str(p) for p in np.asarray(periodos, dtype=object)]
        etiquetas = [crudas[i] for i, ok in enumerate(finitos) if ok] if len(crudas) == len(e) else []

    base = {
        "umbral_z": float(UMBRAL_Z_MODIFICADO_ATIPICO),
        "factor": float(FACTOR_Z_MODIFICADO),
        "n": int(abs_err.size),
        "cantidad": 0,
        "proporcion": float("nan"),
        "observaciones": [],
        "calculable": False,
        "motivo": "",
    }
    if abs_err.size == 0:
        base["motivo"] = "No calculable: no hay errores de backtesting finitos."
        return base

    mediana = float(np.median(abs_err))
    mad = float(np.median(np.abs(abs_err - mediana)))
    if mad <= EPS_NUMERICO:
        base["motivo"] = (
            "No calculable: la desviación absoluta mediana de los errores es nula, "
            "de modo que el puntaje z modificado no está definido."
        )
        return base

    z = FACTOR_Z_MODIFICADO * (abs_err - mediana) / mad
    marcados = np.abs(z) > float(UMBRAL_Z_MODIFICADO_ATIPICO)
    observaciones = [
        {
            "posicion": int(i),
            "periodo": etiquetas[i] if i < len(etiquetas) else "",
            "error_absoluto": float(abs_err[i]),
            "z_modificado": float(z[i]),
            "extremo": bool(marcados[i]),
        }
        for i in range(abs_err.size)
    ]
    base.update(
        {
            "cantidad": int(marcados.sum()),
            "proporcion": float(marcados.mean() * 100.0),
            "mediana_error_absoluto": mediana,
            "mad_error_absoluto": mad,
            "observaciones": observaciones,
            "calculable": True,
            "motivo": "",
        }
    )
    return base


def _como_array_numerico(valores: Any) -> np.ndarray:
    """Convierte una entrada tipo serie/lista a ndarray float sin valores infinitos."""
    arr = np.asarray(valores, dtype=float)
    return arr[np.isfinite(arr)]


def calcular_mae(y_real: Any, y_predicho: Any) -> float:
    y, yhat = _alinear_arrays(y_real, y_predicho)
    if len(y) == 0:
        return float("nan")
    return float(np.mean(np.abs(y - yhat)))


def calcular_rmse(y_real: Any, y_predicho: Any) -> float:
    y, yhat = _alinear_arrays(y_real, y_predicho)
    if len(y) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y - yhat) ** 2)))


def calcular_mape(y_real: Any, y_predicho: Any) -> float:
    y, yhat = _alinear_arrays(y_real, y_predicho)
    mask = np.isfinite(y) & np.isfinite(yhat) & (np.abs(y) > EPS_NUMERICO)
    if not np.any(mask):
        return float("nan")
    return float(np.mean(np.abs((y[mask] - yhat[mask]) / y[mask])) * 100.0)


def calcular_smape(y_real: Any, y_predicho: Any) -> float:
    """Calcula sMAPE en porcentaje, robusto ante escalas distintas de cero."""
    y, yhat = _alinear_arrays(y_real, y_predicho)
    denom = np.abs(y) + np.abs(yhat)
    mask = np.isfinite(y) & np.isfinite(yhat) & (denom > EPS_NUMERICO)
    if not np.any(mask):
        return float("nan")
    return float(np.mean(2.0 * np.abs(y[mask] - yhat[mask]) / denom[mask]) * 100.0)


def calcular_sesgo_medio(y_real: Any, y_predicho: Any) -> float:
    """Calcula el error medio y-yhat; positivo implica subestimacion media."""
    y, yhat = _alinear_arrays(y_real, y_predicho)
    if len(y) == 0:
        return float("nan")
    return float(np.mean(y - yhat))


def calcular_escala_naive_insample(y_entrenamiento: Any) -> float:
    """
    Calcula la escala naive no estacional dentro de muestra.

    Para una ventana de entrenamiento de longitud T:
    escala = (1 / (T - 1)) * sum_{t=2..T} |y_t - y_{t-1}|.
    """
    base = np.asarray(y_entrenamiento, dtype=float)
    base = base[np.isfinite(base)]
    if len(base) < 2:
        return float("nan")
    escala = float(np.mean(np.abs(np.diff(base))))
    if escala <= EPS_NUMERICO:
        return float("nan")
    return escala


def calcular_mase_por_origen(errores_abs: Any, escalas_naive: Any) -> float:
    """Calcula MASE promediando errores escalados por origen walk-forward."""
    errores = np.asarray(errores_abs, dtype=float)
    escalas = np.asarray(escalas_naive, dtype=float)
    n = min(len(errores), len(escalas))
    if n == 0:
        return float("nan")
    errores = errores[:n]
    escalas = escalas[:n]
    mask = np.isfinite(errores) & np.isfinite(escalas) & (np.abs(escalas) > EPS_NUMERICO)
    if not np.any(mask):
        return float("nan")
    return float(np.mean(np.abs(errores[mask]) / escalas[mask]))


def calcular_mase(y_real: Any, y_predicho: Any, y_entrenamiento: Any | None = None) -> float:
    """
    Calcula MASE usando naive no estacional de un periodo como escala.

    Si y_entrenamiento no se proporciona, usa y_real para estimar la escala.
    En backtesting debe preferirse calcular la escala con cada ventana de
    entrenamiento para evitar fuga de información.
    """
    y, yhat = _alinear_arrays(y_real, y_predicho)
    if len(y) == 0:
        return float("nan")
    escala = calcular_escala_naive_insample(y_entrenamiento if y_entrenamiento is not None else y)
    if not math.isfinite(escala):
        return float("nan")
    return float(np.mean(np.abs(y - yhat)) / escala)


def calcular_r2(y_real: Any, y_predicho: Any) -> float:
    y, yhat = _alinear_arrays(y_real, y_predicho)
    if len(y) < 2:
        return float("nan")
    sse = float(np.sum((y - yhat) ** 2))
    sst = float(np.sum((y - np.mean(y)) ** 2))
    if sst <= 0:
        return float("nan")
    return float(1.0 - (sse / sst))


def calcular_r2_ajustado(r2: float, n: int, k: int) -> float:
    if n <= k + 1 or not math.isfinite(float(r2)):
        return float("nan")
    return float(1.0 - (1.0 - r2) * ((n - 1) / (n - k - 1)))


def calcular_aic(sse: float, n: int, k: int) -> float:
    if n <= 0 or sse <= 0:
        return float("inf")
    return float(n * math.log(sse / n) + 2 * k)


def calcular_aicc(sse: float, n: int, k: int) -> float:
    aic = calcular_aic(sse, n, k)
    if n <= k + 1 or not math.isfinite(aic):
        return float("inf")
    return float(aic + (2 * k * (k + 1)) / (n - k - 1))


def calcular_metricas(y_real: Any, y_predicho: Any, k: int = 2) -> dict[str, float]:
    """
    Calcula métricas de ajuste o predicción.

    Args:
        y_real: valores observados.
        y_predicho: valores predichos.
        k: número aproximado de parámetros del modelo.

    Returns:
        Diccionario con MAE, RMSE, MAPE, R2, R2 ajustado, SSE, AIC y AICc.
    """
    y, yhat = _alinear_arrays(y_real, y_predicho)
    n = int(len(y))
    if n == 0:
        return {
            "n": 0,
            "mae": float("nan"),
            "rmse": float("nan"),
            "mape": float("nan"),
            "smape": float("nan"),
            "mase": float("nan"),
            "sesgo_medio": float("nan"),
            "r2": float("nan"),
            "r2_ajustado": float("nan"),
            "sse": float("nan"),
            "aic": float("inf"),
            "aicc": float("inf"),
        }

    resid = y - yhat
    sse = float(np.sum(resid ** 2))
    r2 = calcular_r2(y, yhat)
    return {
        "n": n,
        "mae": calcular_mae(y, yhat),
        "rmse": calcular_rmse(y, yhat),
        "mape": calcular_mape(y, yhat),
        "smape": calcular_smape(y, yhat),
        "mase": calcular_mase(y, yhat),
        "sesgo_medio": calcular_sesgo_medio(y, yhat),
        "r2": r2,
        "r2_ajustado": calcular_r2_ajustado(r2, n, k),
        "sse": sse,
        "aic": calcular_aic(sse, n, k),
        "aicc": calcular_aicc(sse, n, k),
    }


def _alinear_arrays(y_real: Any, y_predicho: Any) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_real, dtype=float)
    yhat = np.asarray(y_predicho, dtype=float)
    n = min(len(y), len(yhat))
    y = y[:n]
    yhat = yhat[:n]
    mask = np.isfinite(y) & np.isfinite(yhat)
    return y[mask], yhat[mask]
