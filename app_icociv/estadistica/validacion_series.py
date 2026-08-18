"""Validación y análisis exploratorio de series temporales ICOCIV."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app_icociv.estadistica.diagnostico_residuos import autocorrelacion
from app_icociv.estadistica.metricas import ADVERTENCIA_MIN_OBS, MIN_OBS
from app_icociv.utilidades.utilidades import ANIO_BASE, periodo_a_t, t_a_periodo


def validar_serie(
    serie_df: pd.DataFrame,
    columna_periodo: str = "Periodo",
    columna_valor: str = "Indice",
    anio_base: int = ANIO_BASE,
) -> dict[str, Any]:
    """
    Válida calidad mínima de una serie antes de modelar.

    Revisa continuidad temporal, orden, duplicados, faltantes, longitud y
    outliers extremos por cambio porcentual mensual.
    """
    errores: list[str] = []
    advertencias: list[str] = []

    if columna_periodo not in serie_df.columns or columna_valor not in serie_df.columns:
        return {
            "valida_modelacion": False,
            "observaciones": 0,
            "errores": ["La serie no contiene columnas Periodo e Índice."],
            "advertencias": [],
        }

    serie = serie_df[[columna_periodo, columna_valor]].copy()
    serie[columna_valor] = pd.to_numeric(serie[columna_valor], errors="coerce")
    valores_faltantes = int(serie[columna_valor].isna().sum())
    duplicados = int(serie[columna_periodo].duplicated().sum())

    tiempos: list[int] = []
    periodos_invalidos: list[str] = []
    for periodo in serie[columna_periodo].astype(str):
        try:
            tiempos.append(periodo_a_t(periodo, anio_base=anio_base))
        except Exception:
            periodos_invalidos.append(periodo)

    if periodos_invalidos:
        errores.append(f"Periodos invalidos detectados: {periodos_invalidos[:5]}")

    serie_valida = serie.dropna(subset=[columna_valor]).copy()
    observaciones = int(len(serie_valida))
    if observaciones < 8:
        errores.append("La serie tiene menos de 8 observaciones numéricas; no es modelable.")
    elif observaciones < ADVERTENCIA_MIN_OBS:
        advertencias.append(f"La serie tiene menos de {ADVERTENCIA_MIN_OBS} meses; la proyección es debil.")
    elif observaciones < MIN_OBS:
        advertencias.append(f"La serie tiene menos de {MIN_OBS} meses; {MIN_OBS} es el mínimo recomendado.")

    if valores_faltantes:
        advertencias.append(f"Se detectaron {valores_faltantes} valores faltantes.")
    if duplicados:
        advertencias.append(f"Se detectaron {duplicados} periodos duplicados.")

    continuidad_ok = False
    orden_ok = False
    periodos_faltantes: list[str] = []
    if not periodos_invalidos and tiempos:
        orden_ok = all(tiempos[i] < tiempos[i + 1] for i in range(len(tiempos) - 1))
        tiempos_ordenados = sorted(set(tiempos))
        continuidad_ok = True
        for esperado in range(tiempos_ordenados[0], tiempos_ordenados[-1] + 1):
            if esperado not in tiempos_ordenados:
                periodos_faltantes.append(t_a_periodo(esperado, anio_base))
                continuidad_ok = False
        if not orden_ok:
            advertencias.append("La serie no esta ordenada cronologicamente de forma estricta.")
        if not continuidad_ok:
            advertencias.append(f"Faltan periodos intermedios: {periodos_faltantes[:10]}")

    outliers = detectar_outliers_extremos(serie_valida[columna_valor].to_numpy(dtype=float))
    if outliers:
        advertencias.append(f"Se detectaron {len(outliers)} cambios mensuales extremos.")

    return {
        "valida_modelacion": len(errores) == 0 and observaciones >= 8,
        "observaciones": observaciones,
        "valores_faltantes": valores_faltantes,
        "duplicados": duplicados,
        "continuidad_temporal": "OK" if continuidad_ok else "REVISAR",
        "orden_cronologico": "OK" if orden_ok else "REVISAR",
        "longitud_minima": "OK" if observaciones >= MIN_OBS else "REVISAR",
        "periodos_faltantes": periodos_faltantes,
        "outliers_extremos": outliers,
        "errores": errores,
        "advertencias": advertencias,
    }


def detectar_outliers_extremos(valores: np.ndarray, umbral_iqr: float = 3.0) -> list[dict[str, float]]:
    """Detecta cambios porcentuales mensuales extremos con regla IQR robusta."""
    y = np.asarray(valores, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 6:
        return []
    cambios = np.diff(y) / np.where(np.abs(y[:-1]) > 1e-12, y[:-1], np.nan) * 100.0
    cambios = cambios[np.isfinite(cambios)]
    if len(cambios) < 4:
        return []
    q1, q3 = np.percentile(cambios, [25, 75])
    iqr = q3 - q1
    if iqr <= 0:
        return []
    inferior = q1 - umbral_iqr * iqr
    superior = q3 + umbral_iqr * iqr
    return [
        {"posicion": int(i + 1), "cambio_pct": float(cambio)}
        for i, cambio in enumerate(cambios)
        if cambio < inferior or cambio > superior
    ]


def analizar_serie_temporal(
    serie_df: pd.DataFrame,
    columna_valor: str = "Indice",
) -> dict[str, Any]:
    """Análisis exploratorio ligero: tendencia, volatilidad y dependencia temporal."""
    y = pd.to_numeric(serie_df[columna_valor], errors="coerce").dropna().to_numpy(dtype=float)
    if len(y) < 3:
        return {
            "tendencia": "no determinada",
            "volatilidad_pct_promedio": float("nan"),
            "autocorrelacion_lag1": float("nan"),
            "posible_estacionalidad": False,
            "cambios_bruscos": 0,
        }

    t = np.arange(len(y), dtype=float)
    pendiente = float(np.polyfit(t, y, deg=1)[0])
    if pendiente > 0:
        tendencia = "creciente"
    elif pendiente < 0:
        tendencia = "decreciente"
    else:
        tendencia = "estable"

    cambios_pct = np.diff(y) / np.where(np.abs(y[:-1]) > 1e-12, y[:-1], np.nan) * 100.0
    cambios_pct = cambios_pct[np.isfinite(cambios_pct)]
    volatilidad = float(np.std(cambios_pct, ddof=1)) if len(cambios_pct) > 1 else 0.0
    cambios_bruscos = int(np.sum(np.abs(cambios_pct) > (np.mean(np.abs(cambios_pct)) + 3 * np.std(cambios_pct)))) if len(cambios_pct) else 0
    acf1 = autocorrelacion(y, lag=1)
    acf12 = autocorrelacion(y, lag=12) if len(y) > 14 else float("nan")
    posible_estacionalidad = bool(np.isfinite(acf12) and abs(acf12) >= 0.35)

    return {
        "tendencia": tendencia,
        "pendiente_media": pendiente,
        "volatilidad_pct_promedio": volatilidad,
        "autocorrelacion_lag1": acf1,
        "autocorrelacion_lag12": acf12,
        "posible_estacionalidad": posible_estacionalidad,
        "cambios_bruscos": cambios_bruscos,
    }


def resumen_validacion(validacion: dict[str, Any]) -> str:
    """Resumen textual breve para UI o reporte."""
    estado = "Serie válida para modelacion" if validacion.get("valida_modelacion") else "Serie con advertencias"
    return "\n".join(
        [
            estado,
            f"Observaciones: {validacion.get('observaciones', 0)}",
            f"Valores faltantes: {validacion.get('valores_faltantes', 0)}",
            f"Duplicados: {validacion.get('duplicados', 0)}",
            f"Continuidad temporal: {validacion.get('continuidad_temporal', 'REVISAR')}",
            f"Longitud mínima: {validacion.get('longitud_minima', 'REVISAR')}",
        ]
    )
