"""Diagnostico de residuos para modelos de series economicas.

`statsmodels` es dependencia **obligatoria** desde julio de 2026 y se importa
aquí sin `try/except`: si falta, la aplicación no arranca. Antes se importaba de
forma condicional y su presencia o ausencia cambiaba resultados en silencio
(hallazgo H-01 de la auditoría independiente).

Su uso está acotado al diagnóstico —en concreto Ljung-Box—. No interviene en
modelos, backtesting, métricas, selección, salvaguarda, intervalos ni ajuste de
calendario.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import ttest_1samp
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan

from app_icociv.estadistica.criterios import (
    ALPHA_PRUEBAS_RESIDUALES,
    CONSECUENCIA_INFORMATIVA,
    EPS_NUMERICO,
    MAX_LAG_LJUNG_BOX,
    MODEL_DF_LJUNG_BOX,
    MIN_RESIDUOS_DIAGNOSTICO,
)
from app_icociv.utilidades.utilidades import (
    curtosis_exceso,
    estadistico_jarque_bera,
    valor_p_jarque_bera,
    version_statsmodels,
)


def durbin_watson(residuos: Any) -> float:
    """Calcula el estadístico Durbin-Watson."""
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return float("nan")
    denominador = float(np.sum(r ** 2))
    if denominador <= EPS_NUMERICO:
        return 2.0
    return float(np.sum(np.diff(r) ** 2) / denominador)


def autocorrelacion(valores: Any, lag: int = 1) -> float:
    """Autocorrelacion simple para un rezago dado."""
    x = np.asarray(valores, dtype=float)
    x = x[np.isfinite(x)]
    if lag <= 0 or len(x) <= lag:
        return float("nan")
    x0 = x[:-lag] - np.mean(x[:-lag])
    x1 = x[lag:] - np.mean(x[lag:])
    denom = float(np.sqrt(np.sum(x0 ** 2) * np.sum(x1 ** 2)))
    if denom <= EPS_NUMERICO:
        return 0.0
    return float(np.sum(x0 * x1) / denom)


def calcular_acf(valores: Any, max_lag: int = 12) -> list[dict[str, float]]:
    """Calcula ACF hasta max_lag sin depender de statsmodels."""
    x = np.asarray(valores, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return []
    max_lag = min(max_lag, len(x) - 2)
    return [{"lag": lag, "valor": autocorrelacion(x, lag)} for lag in range(1, max_lag + 1)]


def calcular_pacf(valores: Any, max_lag: int = 12) -> list[dict[str, float]]:
    """
    Calcula una PACF aproximada usando regresion OLS por rezagos.

    Para cada lag k, se estima y_t contra y_{t-1}...y_{t-k}; la PACF es el
    coeficiente del rezago k. Es suficiente como diagnostico ligero para DOCX.
    """
    x = np.asarray(valores, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return []
    max_lag = min(max_lag, max(1, len(x) // 3), len(x) - 2)
    resultados: list[dict[str, float]] = []
    for lag in range(1, max_lag + 1):
        y = x[lag:]
        columnas = [x[lag - j - 1: len(x) - j - 1] for j in range(lag)]
        X = np.column_stack(columnas)
        X = np.column_stack([np.ones(len(X)), X])
        try:
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            valor = float(coef[-1])
        except np.linalg.LinAlgError:
            valor = float("nan")
        resultados.append({"lag": lag, "valor": valor})
    return resultados


def evaluar_residuos(residuos: Any, max_lag: int = 12, tipo_modelo: str | None = None) -> dict[str, Any]:
    """Evalua media, dispersion, normalidad aproximada y autocorrelacion."""
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {
            "n": 0,
            "media": float("nan"),
            "desviacion": float("nan"),
            "durbin_watson": float("nan"),
            "jb_p": float("nan"),
            "kurt_ex": float("nan"),
            "acf": [],
            "pacf": [],
            "durbin_watson_alcance": _alcance_durbin_watson(tipo_modelo),
            "durbin_watson_interpretacion": "Sin residuos válidos.",
            "alertas": ["No hay residuos válidos para diagnostico."],
        }

    dw = durbin_watson(r)
    media = float(np.mean(r))
    desv = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
    jb, jb_asimetria, jb_curtosis = estadistico_jarque_bera(r)
    jb_p = valor_p_jarque_bera(r)
    kurt = curtosis_exceso(r)

    ljung_box = calcular_ljung_box(r, max_lag=max_lag)
    # D-7: dos contrastes formales sustituyen a las comprobaciones por corte fijo.
    media_residual = contrastar_media_residual(r)
    hetero = contrastar_heterocedasticidad(r)

    alcance_dw = _alcance_durbin_watson(tipo_modelo)
    interpretacion_dw = _interpretar_durbin_watson(dw)
    alertas: list[str] = []
    if alcance_dw == "descriptivo_no_ols":
        alertas.append(
            "Durbin-Watson se reporta como diagnostico descriptivo para este modelo; "
            "no se interpreta como prueba formal concluyente."
        )
    # D-2: sin alertas por cortes fijos de Durbin-Watson. El estadistico se
    # reporta; su contraste formal exige las tablas d_L y d_U de Durbin y Watson
    # (1951), que dependen de n y del numero de regresores y no estan
    # implementadas. La autocorrelacion se contrasta con Ljung-Box, que si
    # produce un valor p.
    #
    # D-7: los mensajes no afirman la hipotesis nula. Un valor p alto no
    # demuestra independencia, normalidad ni homocedasticidad; solo indica que
    # no hay evidencia suficiente para rechazarlas al nivel elegido.
    if math.isfinite(jb_p) and jb_p < ALPHA_PRUEBAS_RESIDUALES:
        alertas.append(
            "Jarque-Bera: se rechazo la hipotesis nula de normalidad al nivel seleccionado."
        )
    if media_residual.get("calculable") and media_residual["p_value"] < ALPHA_PRUEBAS_RESIDUALES:
        alertas.append(
            "Media residual: se rechazo la hipotesis nula de media cero al nivel seleccionado."
        )
    if ljung_box.get("p_value") is not None and ljung_box["p_value"] < ALPHA_PRUEBAS_RESIDUALES:
        alertas.append(
            "Ljung-Box: se rechazo la hipotesis nula de ausencia de autocorrelacion conjunta "
            "al nivel seleccionado."
        )
    if hetero.get("calculable") and hetero["p_value"] < ALPHA_PRUEBAS_RESIDUALES:
        alertas.append(
            "Breusch-Pagan: se rechazo la hipotesis nula de varianza constante al nivel "
            "seleccionado."
        )
    if len(r) < MIN_RESIDUOS_DIAGNOSTICO:
        alertas.append(
            f"Muestra de {len(r)} residuos: los contrastes asintoticos pierden exactitud "
            "por debajo de " + str(MIN_RESIDUOS_DIAGNOSTICO) + " observaciones."
        )

    return {
        "n": int(len(r)),
        "media": media,
        "desviacion": desv,
        "durbin_watson": dw,
        "durbin_watson_rango": "[0, 4]",
        "durbin_watson_alcance": alcance_dw,
        "durbin_watson_interpretacion": interpretacion_dw,
        "durbin_watson_region_critica": "Interpretación aproximada; no se aplican regiones d_L/d_U.",
        "jb": jb,
        "jb_p": jb_p,
        "jb_asimetria": jb_asimetria,
        "jb_curtosis": jb_curtosis,
        "jb_n": int(len(r)),
        "jb_hipotesis_nula": "Los residuos proceden de una distribución normal.",
        "jb_mensaje": _redactar_contraste(jb_p, ALPHA_PRUEBAS_RESIDUALES),
        "kurt_ex": kurt,
        "ljung_box": ljung_box,
        "media_residual": media_residual,
        "heterocedasticidad": hetero,
        "consecuencia_operativa": CONSECUENCIA_INFORMATIVA,
        "acf": calcular_acf(r, max_lag=max_lag),
        "pacf": calcular_pacf(r, max_lag=max_lag),
        "alertas": alertas,
    }


def _alcance_durbin_watson(tipo_modelo: str | None) -> str:
    """Distingue uso formal aproximado OLS de uso descriptivo."""
    nombre = (tipo_modelo or "").lower()
    modelos_ols = {
        "lineal",
        "logaritmico",
        "exponencial_log_lineal",
        "huber",
    }
    return "formal_ols_aproximado" if nombre in modelos_ols else "descriptivo_no_ols"


def _interpretar_durbin_watson(dw: float) -> str:
    """Lectura descriptiva del estadistico, sin veredicto por cortes fijos.

    D-2: la version anterior clasificaba el valor en cinco categorias usando los
    cortes 0,8 / 1,5 / 2,5 / 3,2, que no proceden de Durbin y Watson (1951) ni
    de ningun manual consultado. El contraste formal se resuelve con las tablas
    d_L y d_U, que dependen del tamano muestral y del numero de regresores y que
    la aplicacion no implementa. Se informa el sentido de la desviacion respecto
    del valor de referencia 2 y se remite a Ljung-Box para el contraste con
    valor p.
    """
    valor = float(dw)
    if not math.isfinite(valor):
        return "No calculable."
    sentido = (
        "por debajo de 2, lo que apunta a autocorrelacion positiva"
        if valor < 2.0
        else "por encima de 2, lo que apunta a autocorrelacion negativa"
        if valor > 2.0
        else "igual a 2"
    )
    return (
        f"Valor {valor:.4f}, {sentido}. Lectura descriptiva: el contraste formal "
        "requiere las tablas d_L/d_U, no implementadas. La autocorrelacion se "
        "contrasta con Ljung-Box."
    )


def calcular_ljung_box(residuos: np.ndarray, max_lag: int = MAX_LAG_LJUNG_BOX) -> dict[str, Any]:
    """Prueba de Ljung-Box sobre autocorrelación conjunta de los residuos.

    Especificación (fijada tras la auditoría de julio de 2026):

    * **Función**: ``statsmodels.stats.diagnostic.acorr_ljungbox``, dependencia
      obligatoria. No hay ruta alternativa: si falta, la importación falla y la
      aplicación no arranca.
    * **Rezagos**: uno solo, ``min(max_lag, n // 5)``. La fuente recomienda
      ``h = 10`` para datos no estacionales y acota ese valor a ``T/5``
      (Hyndman y Athanasopoulos, 2021, §5.4). La versión anterior usaba ``n/4``,
      que no coincidía con la referencia citada y admitía más rezagos de los que
      ella recomienda para una muestra dada (decisión D-10).
    * **model_df**: 0. Los residuos que llegan aquí no provienen de un ARMA
      ajustado, de modo que no hay parámetros de autocorrelación que descontar.
      Se declara explícitamente en lugar de aceptar el valor por omisión.
    * **Nivel de significancia**: ``ALPHA_PRUEBAS_RESIDUALES`` (0,05), solo para
      emitir una advertencia.
    * **Muestra insuficiente**: la condición es ``n > rezagos efectivos``,
      derivada de lo que el estadístico necesita para existir. Sustituye al
      mínimo fijo de doce residuos, que no procedía de ninguna fuente y que
      además no coincidía con esa derivación (decisión D-10).
    * **Residuos constantes**: dispersión nula impide calcular la
      autocorrelación; se devuelve «no calculable».

    **Alcance de la prueba.** Es diagnóstico. Su resultado se comunica como
    advertencia y **no** cambia por sí solo el modelo seleccionado, el
    pronóstico, el intervalo de predicción ni el horizonte admisible.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    n = len(r)

    # D-10: rezagos segun la fuente citada, h = min(10, T/5) para datos no
    # estacionales, y minimo derivado de lo que el contraste necesita: n mayor
    # que el numero de rezagos.
    rezagos = int(min(int(max_lag), n // 5))
    if rezagos < 1 or n <= rezagos:
        return {
            "disponible": False,
            "p_value": None,
            "estadistico": None,
            "rezagos": rezagos if rezagos >= 1 else None,
            "model_df": MODEL_DF_LJUNG_BOX,
            "mensaje": (
                f"No calculable: con {n} residuos los rezagos derivados de "
                f"min({int(max_lag)}, n/5) son {rezagos}, y el contraste exige "
                "mas residuos que rezagos."
            ),
        }
    if float(np.std(r)) <= 0.0:
        return {
            "disponible": False,
            "p_value": None,
            "estadistico": None,
            "rezagos": rezagos,
            "model_df": MODEL_DF_LJUNG_BOX,
            "mensaje": "No calculable: los residuos son constantes.",
        }

    resultado = acorr_ljungbox(
        r, lags=[rezagos], model_df=MODEL_DF_LJUNG_BOX, return_df=True
    )
    estadistico = float(resultado["lb_stat"].iloc[-1])
    p_value = float(resultado["lb_pvalue"].iloc[-1])
    if not math.isfinite(estadistico) or not math.isfinite(p_value):
        return {
            "disponible": False,
            "p_value": None,
            "estadistico": None,
            "rezagos": rezagos,
            "model_df": MODEL_DF_LJUNG_BOX,
            "mensaje": "No calculable: el estadístico no resultó finito.",
        }
    return {
        "disponible": True,
        "estadistico": estadistico,
        "p_value": p_value,
        "rezagos": rezagos,
        "model_df": MODEL_DF_LJUNG_BOX,
        "mensaje": (
            f"Ljung-Box con {rezagos} rezago(s) y model_df={MODEL_DF_LJUNG_BOX}, "
            f"calculado con statsmodels {version_statsmodels()}."
        ),
    }


def contrastar_media_residual(residuos: np.ndarray) -> dict[str, Any]:
    """Contrasta H0: la media poblacional de los residuos es cero.

    Decisión D-7. La versión anterior comparaba ``|media| > 0,25·s``, un corte
    de implementación sin fuente que no era un contraste: no daba estadístico,
    ni grados de libertad, ni valor p, y su resultado dependía de una constante
    arbitraria.

    Se emplea la prueba t de una muestra
    (``scipy.stats.ttest_1samp``, bilateral):

    ``t = (media - 0) / (s / sqrt(n))`` con ``n - 1`` grados de libertad.

    Requiere al menos dos residuos y dispersión no nula. Su validez descansa en
    la aproximación normal de la media muestral; con muestras pequeñas la
    aproximación es más débil y así se declara.

    **Alcance.** Informativo. No modifica el modelo, el pronóstico, el intervalo
    ni el horizonte.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    n = int(r.size)
    base: dict[str, Any] = {
        "prueba": "t de una muestra sobre la media residual",
        "hipotesis_nula": "La media poblacional de los residuos es cero.",
        "hipotesis_alternativa": "La media poblacional de los residuos es distinta de cero.",
        "alfa": float(ALPHA_PRUEBAS_RESIDUALES),
        "n": n,
        "media": float(np.mean(r)) if n else float("nan"),
        "error_estandar": float("nan"),
        "estadistico": None,
        "grados_libertad": None,
        "p_value": None,
        "calculable": False,
        "mensaje": "",
    }
    if n < 2:
        base["mensaje"] = f"El contraste no fue calculable: se requieren al menos 2 residuos y hay {n}."
        return base
    desviacion = float(np.std(r, ddof=1))
    if desviacion <= EPS_NUMERICO:
        base["mensaje"] = "El contraste no fue calculable: los residuos no presentan dispersión."
        return base

    resultado = ttest_1samp(r, popmean=0.0)
    estadistico = float(resultado.statistic)
    p_value = float(resultado.pvalue)
    if not (math.isfinite(estadistico) and math.isfinite(p_value)):
        base["mensaje"] = "El contraste no fue calculable: el estadístico no resultó finito."
        return base

    base.update(
        {
            "error_estandar": desviacion / math.sqrt(n),
            "estadistico": estadistico,
            "grados_libertad": n - 1,
            "p_value": p_value,
            "calculable": True,
            "mensaje": _redactar_contraste(p_value, ALPHA_PRUEBAS_RESIDUALES),
        }
    )
    return base


def contrastar_heterocedasticidad(residuos: np.ndarray) -> dict[str, Any]:
    """Contrasta H0: varianza residual constante, con Breusch-Pagan.

    Decisión D-7. La versión anterior calculaba la correlación entre ``|e|`` y
    el tiempo y avisaba si superaba 0,55. No era un contraste: el 0,55 carecía
    de fuente y no producía estadístico ni valor p.

    Se emplea la prueba de Breusch y Pagan (1979) en la forma implementada por
    ``statsmodels.stats.diagnostic.het_breuschpagan``: regresa ``e²`` sobre la
    matriz de regresores y contrasta la nulidad conjunta de sus pendientes. El
    estadístico LM sigue asintóticamente una ``chi²`` con tantos grados de
    libertad como regresores distintos de la constante.

    Se usa Breusch-Pagan y no White porque la matriz de regresores disponible es
    el índice temporal, con un único regresor: la versión de White exigiría
    además sus cuadrados y productos cruzados, lo que multiplicaría los grados
    de libertad sin más información y perdería potencia con las longitudes de
    serie que maneja la aplicación.

    **Alcance.** Informativo. No modifica el modelo, el pronóstico, el intervalo
    ni el horizonte.
    """
    r = np.asarray(residuos, dtype=float)
    r = r[np.isfinite(r)]
    n = int(r.size)
    base: dict[str, Any] = {
        "prueba": "Breusch-Pagan sobre el índice temporal",
        "fuente": "Breusch y Pagan (1979); statsmodels.stats.diagnostic.het_breuschpagan",
        "hipotesis_nula": "La varianza de los residuos es constante (homocedasticidad).",
        "hipotesis_alternativa": "La varianza de los residuos depende de los regresores.",
        "alfa": float(ALPHA_PRUEBAS_RESIDUALES),
        "regresores": ["constante", "indice temporal t"],
        "n": n,
        "estadistico": None,
        "grados_libertad": None,
        "p_value": None,
        "calculable": False,
        "limitacion": "",
        "mensaje": "",
        "consecuencia": CONSECUENCIA_INFORMATIVA,
    }
    # El contraste regresa e² sobre [1, t]: necesita mas observaciones que
    # parametros estimados en esa regresion auxiliar.
    if n < 3:
        base["mensaje"] = (
            f"El contraste no fue calculable: la regresión auxiliar sobre [1, t] "
            f"exige más de 2 observaciones y hay {n}."
        )
        return base
    if float(np.std(r)) <= EPS_NUMERICO:
        base["mensaje"] = "El contraste no fue calculable: los residuos son constantes."
        return base

    exog = np.column_stack([np.ones(n), np.arange(n, dtype=float)])
    try:
        estadistico, p_value, _, _ = het_breuschpagan(r, exog)
    except Exception as exc:  # matriz singular u otro fallo numerico
        base["mensaje"] = f"El contraste no fue calculable: {exc}"
        return base
    if not (math.isfinite(float(estadistico)) and math.isfinite(float(p_value))):
        base["mensaje"] = "El contraste no fue calculable: el estadístico no resultó finito."
        return base

    base.update(
        {
            "estadistico": float(estadistico),
            "grados_libertad": 1,
            "p_value": float(p_value),
            "calculable": True,
            "limitacion": (
                f"Resultado asintótico: con {n} residuos la aproximación chi² es débil."
                if n < MIN_RESIDUOS_DIAGNOSTICO
                else ""
            ),
            "mensaje": _redactar_contraste(float(p_value), ALPHA_PRUEBAS_RESIDUALES),
        }
    )
    return base


def _redactar_contraste(p_value: float, alfa: float) -> str:
    """Redacta el resultado sin afirmar la hipótesis nula (D-7)."""
    if not math.isfinite(p_value):
        return "El contraste no fue calculable."
    if p_value < alfa:
        return f"Se rechazó la hipótesis nula al nivel seleccionado (alfa = {alfa:g})."
    return f"No se rechazó la hipótesis nula al nivel seleccionado (alfa = {alfa:g})."


def generar_interpretacion_estadistica(
    validacion_serie: dict[str, Any],
    analisis_serie: dict[str, Any],
    diagnostico_residuos: dict[str, Any],
    backtesting: dict[str, Any],
    estadisticas_modelo: dict[str, Any],
) -> list[str]:
    """Redacta conclusiones técnicas automaticas y auditables."""
    textos: list[str] = []

    observaciones = validacion_serie.get("observaciones", 0)
    if validacion_serie.get("valida_modelacion"):
        textos.append(
            f"La serie cuenta con {observaciones} observaciones válidas y cumple condiciones básicas de continuidad temporal para modelacion."
        )
    else:
        textos.append(
            f"La serie cuenta con {observaciones} observaciones; se recomienda revisar las advertencias de calidad antes de interpretar la proyección."
        )

    tendencia = analisis_serie.get("tendencia", "no determinada")
    volatilidad = analisis_serie.get("volatilidad_pct_promedio")
    if math.isfinite(float(volatilidad or float("nan"))):
        textos.append(
            f"La serie presenta tendencia {tendencia} y una volatilidad media mensual aproximada de {float(volatilidad):.3f}%."
        )
    else:
        textos.append(f"La serie presenta tendencia {tendencia}.")

    dw = diagnostico_residuos.get("durbin_watson")
    jb = diagnostico_residuos.get("jb_p")
    if math.isfinite(float(dw or float("nan"))):
        textos.append(
            f"El diagnostico residual reporta Durbin-Watson de {float(dw):.3f} y Jarque-Bera p-value de {_formato_float(jb)}."
        )

    metricas_bt = backtesting.get("metricas", {}) if backtesting else {}
    mape = metricas_bt.get("mape")
    if mape is not None:
        mase = _numero_o_nan(metricas_bt.get("mase"))
        # D-9: se retira la banda 0,8 / 1,0. Se conserva la comparacion con 1,
        # que es el sentido con el que MASE esta definido.
        if math.isfinite(mase) and mase > 1.0:
            lectura = (
                "El MASE supera 1 frente a la escala naive in-sample; se reporta como advertencia auxiliar "
                "y debe contrastarse con el desempeño frente a naive/drift en backtesting por horizonte."
            )
        elif math.isfinite(mase) and mase < 1.0:
            lectura = (
                "El MASE es menor que 1 frente a la escala naive in-sample; en promedio el modelo mejora "
                "ese pronostico ingenuo. La comparacion decisiva es la de rRMSE/rMAE frente a los "
                "benchmarks de backtesting por horizonte."
            )
        elif math.isfinite(mase):
            lectura = "El MASE es igual a 1: el error iguala al del pronostico ingenuo de la escala de entrenamiento."
        else:
            lectura = "No fue posible interpretar MASE; se revisan MAE, RMSE y diagnosticos residuales."
        textos.append(
            "Durante el backtesting temporal, el modelo obtuvo "
            f"MAPE de {_formato_float(mape)}%, RMSE de {_formato_float(metricas_bt.get('rmse'))} "
            f"y MAE de {_formato_float(metricas_bt.get('mae'))}. {lectura}"
        )
    else:
        textos.append("No fue posible ejecutar backtesting temporal con el tamaño disponible de la serie.")

    aicc = estadisticas_modelo.get("aicc")
    r2_adj = estadisticas_modelo.get("r2_ajustado")
    textos.append(
        "La selección del modelo no se basa solamente en R2; considera parsimonia "
        f"(AICc {_formato_float(aicc)}), R2 ajustado {_formato_float(r2_adj)}, "
        "diagnostico residual, coherencia de tendencia y validación predictiva temporal."
    )

    return textos


def _formato_float(valor: Any) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "No aplica"
    if not math.isfinite(numero):
        return "No aplica"
    return f"{numero:.3f}"


def _numero_o_nan(valor: Any) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return float("nan")
    return numero if math.isfinite(numero) else float("nan")
