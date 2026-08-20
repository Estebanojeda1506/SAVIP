"""Backtesting temporal para proyecciones ICOCIV."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app_icociv.estadistica.criterios import (
    EPS_NUMERICO,
    UMBRAL_MASE_ADVERTENCIA,
)
from app_icociv.estadistica.metricas import (
    calcular_escala_naive_insample,
    calcular_mae,
    calcular_mape,
    calcular_mase_por_origen,
    calcular_rmse,
    calcular_sesgo_medio,
    calcular_smape,
    detectar_errores_extremos,
)
from app_icociv.estadistica.modelos_interpretables import (
    MODELOS_INTERPRETABLES,
    MODELOS_ESTADISTICOS,
    ajustar_modelo_interpretable,
    observaciones_minimas_catalogo,
)
from app_icociv.utilidades.utilidades import ANIO_BASE, periodo_a_t


def ejecutar_backtesting(
    serie_df: pd.DataFrame,
    anio_base: int = ANIO_BASE,
    entrenamiento_inicial: int | None = None,
    horizonte: int = 1,
    modelo: str = "seleccion_automatica",
    modelos_catalogo: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """
    Ejecuta walk-forward validation con ventana expansiva.

    Si modelo='seleccion_automatica', en cada corte se comparan modelos
    interpretables y se usa el de menor MAPE/AICc disponible para ese corte.

    ``modelos_catalogo`` son los candidatos que se comparan entre si. Fija el
    primer origen comun a todos ellos (P0-E): sin el, cada llamada calcularia
    su propio origen y los modelos dejarian de compararse sobre las mismas
    observaciones.
    """
    serie = _preparar_serie(serie_df, anio_base)
    n = len(serie)
    minimo = observaciones_minimas_catalogo(modelos_catalogo)
    if n < minimo + 1:
        # Derivada, no literal: hace falta el entrenamiento minimo mas al menos
        # una observacion posterior para que exista un solo par (objetivo, h).
        return _resultado_sin_backtesting(
            f"La serie tiene menos de {minimo + 1} observaciones para backtesting."
        )

    horizonte = max(1, int(horizonte))
    entrenamiento_inicial = _entrenamiento_inicial(n, entrenamiento_inicial, modelos_catalogo)
    if entrenamiento_inicial + horizonte > n:
        return _resultado_sin_backtesting("No hay datos suficientes para el horizonte de backtesting solicitado.")

    predicciones: list[dict[str, Any]] = []
    errores: list[str] = []

    for corte in range(entrenamiento_inicial, n - horizonte + 1):
        entrenamiento = serie.iloc[:corte]
        prueba = serie.iloc[corte + horizonte - 1]
        t_train = entrenamiento["t"].to_numpy(dtype=float)
        y_train = entrenamiento["Indice"].to_numpy(dtype=float)
        t_objetivo = int(prueba["t"])

        try:
            if modelo == "seleccion_automatica":
                modelo_ajustado = _seleccionar_en_corte(t_train, y_train, t_objetivo)
            else:
                modelo_ajustado = ajustar_modelo_interpretable(
                    modelo, t_train, y_train, calcular_diagnostico_residuos=False
                )
            y_pred = float(modelo_ajustado["predict"]([t_objetivo])[0])
        except Exception as exc:
            errores.append(f"Fallo en corte {corte}: {exc}")
            continue

        y_real = float(prueba["Indice"])
        error = y_real - y_pred
        escala_mase = calcular_escala_naive_insample(y_train)
        if np.isfinite(escala_mase) and abs(escala_mase) > EPS_NUMERICO:
            error_escalado_abs = abs(error) / escala_mase
        else:
            error_escalado_abs = float("nan")
        predicciones.append(
            {
                "Periodo": str(prueba["Periodo"]),
                "t": t_objetivo,
                "Origen": str(serie.iloc[corte - 1]["Periodo"]),
                "Horizonte": int(horizonte),
                "Observado": y_real,
                "Predicho": y_pred,
                "Error": error,
                "Error_abs": abs(error),
                "Error_pct": abs(error / y_real) * 100.0 if abs(y_real) > 1e-12 else float("nan"),
                "Modelo": modelo_ajustado.get("nombre_visible", modelo_ajustado.get("name", modelo)),
                "Modelo_codigo": modelo_ajustado.get("nombre", modelo),
                "Observaciones_entrenamiento": int(len(entrenamiento)),
                "Escala_naive_insample": escala_mase,
                "Error_escalado_abs": error_escalado_abs,
            }
        )

    if not predicciones:
        return _resultado_sin_backtesting("No fue posible obtener predicciones de backtesting.", errores)

    pred_df = pd.DataFrame(predicciones)
    metricas = _metricas_backtesting(
        pred_df["Observado"].to_numpy(dtype=float),
        pred_df["Predicho"].to_numpy(dtype=float),
        serie["Indice"].iloc[:entrenamiento_inicial].to_numpy(dtype=float),
        pred_df["Error"].to_numpy(dtype=float),
        pred_df["Error_escalado_abs"].to_numpy(dtype=float),
        pred_df["Escala_naive_insample"].to_numpy(dtype=float),
        pred_df["Periodo"].tolist(),
    )
    metricas["iteraciones"] = int(len(pred_df))
    metricas["horizonte"] = int(horizonte)

    return {
        "ejecutado": True,
        "metodo": "Walk-forward validation con ventana expansiva",
        "entrenamiento_inicial": int(entrenamiento_inicial),
        "horizonte": int(horizonte),
        "iteraciones": int(len(pred_df)),
        "metricas": metricas,
        "predicciones": pred_df,
        "errores": errores,
        "interpretacion": interpretar_backtesting(metricas),
    }


def ejecutar_backtesting_multi_horizonte(
    serie_df: pd.DataFrame,
    horizontes: tuple[int, ...],
    anio_base: int = ANIO_BASE,
    entrenamiento_inicial: int | None = None,
    modelo: str = "seleccion_automatica",
    modelos_catalogo: tuple[str, ...] | list[str] | None = None,
) -> dict[int, dict[str, Any]]:
    """Walk-forward de un modelo para varios horizontes, ajustando cada origen
    UNA sola vez y reutilizando ese ajuste para todos los horizontes.

    La prediccion en un origen concreto depende solo de los datos disponibles
    hasta ese origen (t_train, y_train), no del horizonte al que se evalue
    -el mismo principio que ya documenta `_matriz_rectangular_12_24`-. Antes de
    esta funcion, `ejecutar_backtesting_comparativo` reajustaba el modelo en el
    mismo origen una vez por cada horizonte de 1 a 24, es decir 24 ajustes
    identicos para producir 24 predicciones distintas del mismo modelo ya
    entrenado. Perfilado 20-08-2026: eran fits/origen redundantes, la mayor
    fuente de tiempo de una proyeccion completa junto al diagnostico de
    residuos ya evitado en el walk-forward (ver `ajustar_modelo_interpretable`).

    Para cada horizonte devuelve exactamente el mismo resultado -mismas
    predicciones, mismas metricas- que llamar a `ejecutar_backtesting` una vez
    por horizonte con el mismo `entrenamiento_inicial`.
    """
    serie = _preparar_serie(serie_df, anio_base)
    n = len(serie)
    minimo = observaciones_minimas_catalogo(modelos_catalogo)
    entrenamiento_inicial = _entrenamiento_inicial(n, entrenamiento_inicial, modelos_catalogo)

    resultados: dict[int, dict[str, Any]] = {}
    if n < minimo + 1:
        msg = f"La serie tiene menos de {minimo + 1} observaciones para backtesting."
        for h in horizontes:
            resultados[int(h)] = _resultado_sin_backtesting(msg)
        return resultados

    horizontes_validos = [int(h) for h in horizontes if entrenamiento_inicial + int(h) <= n]
    for h in horizontes:
        if int(h) not in horizontes_validos:
            resultados[int(h)] = _resultado_sin_backtesting(
                "No hay datos suficientes para el horizonte de backtesting solicitado."
            )
    if not horizontes_validos:
        return resultados

    predicciones_por_h: dict[int, list[dict[str, Any]]] = {h: [] for h in horizontes_validos}
    errores_por_h: dict[int, list[str]] = {h: [] for h in horizontes_validos}

    for corte in range(entrenamiento_inicial, n):
        entrenamiento = serie.iloc[:corte]
        t_train = entrenamiento["t"].to_numpy(dtype=float)
        y_train = entrenamiento["Indice"].to_numpy(dtype=float)
        escala_mase = calcular_escala_naive_insample(y_train)

        try:
            if modelo == "seleccion_automatica":
                # El desempate por finitud de la prediccion depende del t
                # objetivo, que varia con el horizonte: se conserva sin
                # consolidar para no alterar la seleccion en ese modo.
                modelo_ajustado = None
            else:
                modelo_ajustado = ajustar_modelo_interpretable(
                    modelo, t_train, y_train, calcular_diagnostico_residuos=False
                )
        except Exception as exc:
            for h in horizontes_validos:
                if corte + h - 1 < n:
                    errores_por_h[h].append(f"Fallo en corte {corte}: {exc}")
            continue

        for h in horizontes_validos:
            idx_objetivo = corte + h - 1
            if idx_objetivo >= n:
                continue
            prueba = serie.iloc[idx_objetivo]
            t_objetivo = int(prueba["t"])
            try:
                if modelo_ajustado is None:
                    ajuste_h = _seleccionar_en_corte(t_train, y_train, t_objetivo)
                else:
                    ajuste_h = modelo_ajustado
                y_pred = float(ajuste_h["predict"]([t_objetivo])[0])
            except Exception as exc:
                errores_por_h[h].append(f"Fallo en corte {corte}: {exc}")
                continue
            y_real = float(prueba["Indice"])
            error = y_real - y_pred
            if np.isfinite(escala_mase) and abs(escala_mase) > EPS_NUMERICO:
                error_escalado_abs = abs(error) / escala_mase
            else:
                error_escalado_abs = float("nan")
            predicciones_por_h[h].append(
                {
                    "Periodo": str(prueba["Periodo"]),
                    "t": t_objetivo,
                    "Origen": str(serie.iloc[corte - 1]["Periodo"]),
                    "Horizonte": int(h),
                    "Observado": y_real,
                    "Predicho": y_pred,
                    "Error": error,
                    "Error_abs": abs(error),
                    "Error_pct": abs(error / y_real) * 100.0 if abs(y_real) > 1e-12 else float("nan"),
                    "Modelo": ajuste_h.get("nombre_visible", ajuste_h.get("name", modelo)),
                    "Modelo_codigo": ajuste_h.get("nombre", modelo),
                    "Observaciones_entrenamiento": int(len(entrenamiento)),
                    "Escala_naive_insample": escala_mase,
                    "Error_escalado_abs": error_escalado_abs,
                }
            )

    for h in horizontes_validos:
        predicciones = predicciones_por_h[h]
        if not predicciones:
            resultados[h] = _resultado_sin_backtesting(
                "No fue posible obtener predicciones de backtesting.", errores_por_h[h]
            )
            continue
        pred_df = pd.DataFrame(predicciones)
        metricas = _metricas_backtesting(
            pred_df["Observado"].to_numpy(dtype=float),
            pred_df["Predicho"].to_numpy(dtype=float),
            serie["Indice"].iloc[:entrenamiento_inicial].to_numpy(dtype=float),
            pred_df["Error"].to_numpy(dtype=float),
            pred_df["Error_escalado_abs"].to_numpy(dtype=float),
            pred_df["Escala_naive_insample"].to_numpy(dtype=float),
            pred_df["Periodo"].tolist(),
        )
        metricas["iteraciones"] = int(len(pred_df))
        metricas["horizonte"] = int(h)
        resultados[h] = {
            "ejecutado": True,
            "metodo": "Walk-forward validation con ventana expansiva",
            "entrenamiento_inicial": int(entrenamiento_inicial),
            "horizonte": int(h),
            "iteraciones": int(len(pred_df)),
            "metricas": metricas,
            "predicciones": pred_df,
            "errores": errores_por_h[h],
            "interpretacion": interpretar_backtesting(metricas),
        }
    return resultados


def ejecutar_backtesting_comparativo(
    serie_df: pd.DataFrame,
    modelos: tuple[str, ...] = MODELOS_INTERPRETABLES,
    horizontes: tuple[int, ...] = (1,),
    anio_base: int = ANIO_BASE,
    entrenamiento_inicial: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Ejecuta backtesting para cada modelo y horizonte solicitado.

    El primer origen se calcula **una sola vez** para todo el banco y se pasa
    explicito a cada ejecucion, de modo que los candidatos se comparan sobre
    exactamente los mismos origenes (P0-E). No hay origen por modelo.

    Cada modelo se ajusta una sola vez por origen (`ejecutar_backtesting_multi_horizonte`)
    y ese ajuste se reutiliza para todos los horizontes solicitados.
    """
    resultados: dict[str, dict[str, Any]] = {}
    catalogo = tuple(modelos)
    for modelo in modelos:
        por_horizonte = ejecutar_backtesting_multi_horizonte(
            serie_df=serie_df,
            horizontes=tuple(int(h) for h in horizontes),
            anio_base=anio_base,
            entrenamiento_inicial=entrenamiento_inicial,
            modelo=modelo,
            modelos_catalogo=catalogo,
        )
        for horizonte in horizontes:
            resultados[f"{modelo}_h{int(horizonte)}"] = por_horizonte[int(horizonte)]
    return resultados


def seleccionar_mejor_modelo(
    nombre_modelo: str,
    estadisticas_modelo: dict[str, Any],
    backtesting: dict[str, Any],
) -> str:
    """Describe el criterio de selección realmente aplicado por la aplicación.

    CORREGIDO el 09-08-2026 (auditoria de fundamentacion, hallazgo F-05). Hasta
    esta fecha el texto describia DOS reglas que ya no existian:

    * la ponderacion ``1/h`` sobre el RMSE relativo al mejor de cada horizonte,
      retirada el 08-08-2026 y sustituida por C-SEL-001;
    * la salvaguarda por benchmark «antes de cualquier bloqueo», que dejo de
      sustituir el modelo el 08-08-2026 (C-SAL-001).

    El texto viaja a `justificacion_modelo` y de ahi a la interfaz, al DOCX y al
    PDF, de modo que el producto publicaba una descripcion falsa de su propia
    regla de seleccion. La sonda de la auditoria lo confirmo en 4 de 4 series.

    El criterio operante es C-SEL-001: el modelo entregado es el que minimiza el
    RMSE fuera de muestra GLOBAL sobre la muestra comun de pares
    (periodo objetivo, horizonte), calculado por validacion de origen movil con
    ventana expansiva. No hay pesos por horizonte, umbrales ni sustituciones
    posteriores. AICc, R2 ajustado y Durbin-Watson se reportan como
    diagnosticos y no deciden la seleccion.
    """
    _ = estadisticas_modelo
    metricas_bt = backtesting.get("metricas", {}) if backtesting else {}
    detalle_bt = ""
    if metricas_bt:
        rmse = metricas_bt.get("rmse")
        mape = metricas_bt.get("mape")
        if rmse is not None and mape is not None:
            try:
                detalle_bt = (
                    f" En el horizonte reportado alcanza RMSE={float(rmse):.4f} y MAPE={float(mape):.3f}%."
                )
            except (TypeError, ValueError):
                detalle_bt = ""
    return (
        f"El modelo seleccionado fue {nombre_modelo}. La selección automática se decide por el "
        "RMSE fuera de muestra global (C-SEL-001): se minimiza la raíz del error cuadrático medio "
        "sobre la muestra común de pares (periodo objetivo, horizonte) en los que todos los "
        "candidatos tienen error finito, calculada por validación temporal de origen móvil con "
        "ventana expansiva. La regla no tiene pesos por horizonte, umbrales ni exenciones por "
        "identidad del modelo, y esa muestra depende solo de la serie, de modo que el modelo es "
        "una propiedad de la serie y no cambia con el horizonte que se solicite. Los benchmarks "
        "Naive y Drift compiten en igualdad de condiciones y no sustituyen al modelo elegido: la "
        "salvaguarda por benchmark es solo un diagnóstico. La agregación entre horizontes es la "
        "función objetivo adoptada y pondera implícitamente más los horizontes con mayor error. "
        "AICc, R2 ajustado y Durbin-Watson se reportan como diagnosticos complementarios y no "
        "intervienen en la eleccion; tampoco se usa R2 como criterio." + detalle_bt
    )


def interpretar_backtesting(metricas: dict[str, Any]) -> str:
    """Reporta las métricas y la única lectura comparativa sustentada.

    D-9: la versión anterior devolvía una etiqueta de «calidad predictiva
    alta/media/baja» construida con cortes internos sin fuente (MASE 0,8;
    MAPE 3 % y 8 %; estabilidad 0,75). Se sustituye por el reporte de los
    valores con sus unidades más la comparación de MASE respecto de 1, que es
    el sentido con el que la métrica está definida (Hyndman y Koehler, 2006).
    """
    mape = metricas.get("mape")
    rmse = metricas.get("rmse")
    mae = metricas.get("mae")
    mase = metricas.get("mase")
    try:
        mape_float = float(mape)
        mase_float = float(mase)
    except (TypeError, ValueError):
        return "Backtesting ejecutado, pero no fue posible interpretar MAPE/MASE."

    if mase_float < UMBRAL_MASE_ADVERTENCIA:
        lectura = (
            "MASE < 1: en promedio el modelo mejora al pronóstico ingenuo de la escala "
            "de entrenamiento. La comparación decisiva es rRMSE/rMAE frente a los "
            "benchmarks de backtesting por horizonte"
        )
    elif mase_float > UMBRAL_MASE_ADVERTENCIA:
        lectura = (
            "MASE > 1: en promedio el modelo no mejora al pronóstico ingenuo de la escala "
            "de entrenamiento; debe contrastarse con rRMSE/rMAE frente a los benchmarks "
            "de backtesting por horizonte"
        )
    else:
        lectura = "MASE = 1: el error iguala al del pronóstico ingenuo de la escala de entrenamiento"

    return (
        "El backtesting temporal registra "
        f"MAPE={mape_float:.3f}%, MASE={mase_float:.3f}, "
        f"RMSE={float(rmse):.3f}, MAE={float(mae):.3f}; {lectura}."
    )


def _preparar_serie(serie_df: pd.DataFrame, anio_base: int) -> pd.DataFrame:
    serie = serie_df.copy()
    if "t" not in serie.columns:
        serie["t"] = serie["Periodo"].apply(lambda p: periodo_a_t(p, anio_base=anio_base))
    serie["Indice"] = pd.to_numeric(serie["Indice"], errors="coerce")
    return serie.dropna(subset=["Indice"]).sort_values("t").reset_index(drop=True)


def _entrenamiento_inicial(
    n: int,
    entrenamiento_inicial: int | None,
    modelos: tuple[str, ...] | list[str] | None = None,
) -> int:
    """Primer origen del backtesting. Valor PROVISIONAL: P0-E sigue abierto (E3).

    CORREGIDO 17-08-2026 (V-CODEX-R3, residual 4). Este encabezado decia «DERIVADO
    de la estimabilidad del catalogo». Lo derivado son las dos COTAS que se
    describen mas abajo; el VALOR que se elige entre ellas no lo esta, y decide el
    modelo entregado por C-SEL-001: 6 de 10 series cambian de ganador segun N0, y
    11 de 59 combinaciones N0-serie. Llamarlo derivado afirmaba un cierre que no
    existe. `N0 = 6` es el valor provisional actualmente implementado, y la
    eleccion del primer origen permanece como limitacion metodologica declarada
    (C-WF-002 = pendiente_de_decision; `evidencia_oos_provisional = True`).

    AUDITORIA 12-08-2026, P0-E. Hasta esta fecha era

        max( 8, min( max(18, floor(0,60 n)), n - 1 ) )

    tres literales sin fuente que decidian cuantos origenes existen, cuantos
    pares fuera de muestra produce cada horizonte y, por C-SEL-001, **el modelo
    que la aplicacion entrega**. La tabla de criterios los atribuia ademas a
    «Hyndman y Athanasopoulos», atribucion que no resiste la verificacion:
    FPP3 5.10 -el procedimiento que se aplica aqui- **no da ninguna
    proporcion**, y la unica del libro, 5.8, es «about 20 %» de conjunto de
    PRUEBA para una particion unica, es decir 80 % de entrenamiento, no 60 %.

    QUE ENTRA. `N0 = max_m N_MIN(m)` sobre los candidatos que compiten, con el
    minimo de cada modelo derivado de su formulacion en
    `OBSERVACIONES_MINIMAS_MODELO`. Hoy el binding es Holt amortiguado: cinco
    parametros, luego seis observaciones para identificarlos.

    LAS DOS COTAS QUE SI TIENEN ORIGEN.

    * `N0 >= max_m N_MIN(m)` es **comparabilidad**: ver
      `observaciones_minimas_catalogo`.
    * `N0 <= n - 1` es **disponibilidad**: sin una observacion posterior no
      existe ningun par (objetivo, horizonte) y no hay nada que evaluar.

    Entre ambas cotas las fuentes **no eligen**. Se toma la inferior porque
    cualquier otro valor es `N0_min + delta` con un `delta` sin procedencia que
    decidiria el modelo entregado, y eso es lo que esta remediacion retira.

    LIMITACION DECLARADA. FPP3 5.10 excluye las primeras observaciones «since it
    is not possible to obtain a reliable forecast based on a small training
    set», pero **no operacionaliza «pequeno»** y esto tampoco. Los primeros
    origenes pronostican desde ventanas cortas y sus errores son grandes; la
    diferencia es que ahora eso esta **medido en la evidencia** en vez de
    escondido en una constante.
    """
    if entrenamiento_inicial is None:
        entrenamiento_inicial = observaciones_minimas_catalogo(modelos)
    return max(1, min(int(entrenamiento_inicial), n - 1))


def _seleccionar_en_corte(t_train: np.ndarray, y_train: np.ndarray, t_objetivo: int) -> dict[str, Any]:
    mejores: list[tuple[float, dict[str, Any]]] = []
    for nombre in MODELOS_ESTADISTICOS:
        try:
            modelo = ajustar_modelo_interpretable(
                nombre, t_train, y_train, calcular_diagnostico_residuos=False
            )
            pred = float(modelo["predict"]([t_objetivo])[0])
            error_ultimo = abs(float(y_train[-1]) - float(modelo["yhat"][-1]))
            aicc = float(modelo.get("metricas_ajuste", {}).get("aicc", 1e9))
            score = error_ultimo + max(aicc, -1000.0) * 0.001
            if nombre in {"naive", "drift", "promedio_movil", "variacion_reciente"}:
                score += 0.5
            if not np.isfinite(pred):
                continue
            mejores.append((score, modelo))
        except Exception:
            continue
    if not mejores:
        raise ValueError("No fue posible ajustar modelos en el corte.")
    mejores.sort(key=lambda item: item[0])
    return mejores[0][1]


def _metricas_backtesting(
    observado: np.ndarray,
    predicho: np.ndarray,
    entrenamiento: np.ndarray,
    errores: np.ndarray,
    errores_escalados: np.ndarray | None = None,
    escalas_mase: np.ndarray | None = None,
    periodos: Any = None,
) -> dict[str, Any]:
    abs_err = np.abs(errores[np.isfinite(errores)])
    # D-8: deteccion por puntaje z modificado (Iglewicz y Hoaglin, 1993), el
    # mismo criterio de atipico que la serie. Salida descriptiva.
    detalle_extremos = detectar_errores_extremos(errores, periodos)
    extremos = detalle_extremos["proporcion"]
    if len(abs_err) == 0:
        estabilidad = float("nan")
    else:
        estabilidad = float(np.std(abs_err, ddof=1) / np.mean(abs_err)) if len(abs_err) > 1 and np.mean(abs_err) > 0 else 0.0
    mase = calcular_mase_por_origen(np.abs(errores), escalas_mase) if escalas_mase is not None else float("nan")
    if not np.isfinite(mase) and errores_escalados is not None:
        esc = np.asarray(errores_escalados, dtype=float)
        esc = esc[np.isfinite(esc)]
        mase = float(np.mean(esc)) if len(esc) else float("nan")
    escalas_validas = np.asarray(escalas_mase, dtype=float) if escalas_mase is not None else np.asarray([], dtype=float)
    escalas_validas = escalas_validas[np.isfinite(escalas_validas) & (np.abs(escalas_validas) > EPS_NUMERICO)]
    advertencia_mase = ""
    if len(escalas_validas) == 0:
        advertencia_mase = "MASE no estable: escala naive in-sample nula o no disponible en las ventanas."

    return {
        "mae": calcular_mae(observado, predicho),
        "rmse": calcular_rmse(observado, predicho),
        "mape": calcular_mape(observado, predicho),
        "smape": calcular_smape(observado, predicho),
        "mase": mase,
        "mase_denominador": "naive no estacional por origen walk-forward",
        "mase_denominador_promedio": float(np.mean(escalas_validas)) if len(escalas_validas) else float("nan"),
        "mase_denominadores_validos": int(len(escalas_validas)),
        "mase_advertencia": advertencia_mase,
        "sesgo_medio": calcular_sesgo_medio(observado, predicho),
        "error_medio": calcular_sesgo_medio(observado, predicho),
        "desviacion_error": float(np.std(errores, ddof=1)) if len(errores) > 1 else 0.0,
        "porcentaje_errores_extremos": extremos,
        "errores_extremos": detalle_extremos,
        "estabilidad_error": estabilidad,
    }


def _resultado_sin_backtesting(mensaje: str, errores: list[str] | None = None) -> dict[str, Any]:
    return {
        "ejecutado": False,
        "metodo": "Walk-forward validation con ventana expansiva",
        "entrenamiento_inicial": None,
        "horizonte": None,
        "iteraciones": 0,
        "metricas": {},
        "predicciones": pd.DataFrame(
            columns=[
                "Periodo",
                "t",
                "Origen",
                "Horizonte",
                "Observado",
                "Predicho",
                "Error",
                "Error_abs",
                "Error_pct",
                "Modelo",
                "Modelo_codigo",
                "Observaciones_entrenamiento",
                "Escala_naive_insample",
                "Error_escalado_abs",
            ]
        ),
        "errores": errores or [mensaje],
        "interpretacion": mensaje,
    }
