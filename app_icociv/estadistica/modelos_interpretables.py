"""Modelos interpretables y benchmarks para series ICOCIV."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression

from app_icociv.estadistica.criterios import (
    EPS_NUMERICO,
    MIN_ITERACIONES_WF,
    UMBRAL_RRMSE_PEOR_BENCHMARK,
    TOLERANCIA_RRMSE_BENCHMARK,
)
from app_icociv.estadistica.diagnostico_residuos import evaluar_residuos
from app_icociv.estadistica.metricas import calcular_metricas
from app_icociv.utilidades.utilidades import forzar_no_decreciente


MODELOS_INTERPRETABLES = (
    "lineal",
    "logaritmico",
    "exponencial_log_lineal",
    "huber",
    "holt_lineal",
    "holt_amortiguado",
    "variacion_lineal",
    "log_variacion",
    "naive",
    "drift",
    "promedio_movil",
    "variacion_reciente",
)

MODELOS_BENCHMARK = {"naive", "drift", "promedio_movil", "variacion_reciente"}
MODELOS_SERIE_TEMPORAL = {
    "holt_lineal",
    "holt_amortiguado",
    "variacion_lineal",
    "log_variacion",
}
MODELOS_ESTADISTICOS = tuple(nombre for nombre in MODELOS_INTERPRETABLES if nombre not in MODELOS_BENCHMARK)
MIN_ITERACIONES_SELECCION = MIN_ITERACIONES_WF

# post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04). Decision final
# de los experimentos de patron calendario (ver
# SAVIP_DECISION_N0_CALENDARIO/DECISION_N0_CALENDARIO_INFORME.txt, Ruta 2):
# N0=12 y H=24 se mantienen; se añade Fourier anual K=1 como estrategia
# calendario candidata sobre cada uno de los 10 modelos que compiten en
# produccion, mas Seasonal Naive (m=12) como benchmark estacional. Los 21
# candidatos resultantes compiten bajo el mismo criterio RMSE OOS rectangular
# comun que ya existia; ninguno tiene prioridad ni veto.
#
# `MODELOS_FOURIER_BASE` debe coincidir con los 10 candidatos que realmente
# compiten en servicio_proyeccion.py (MODELOS_INTERPRETABLES sin
# promedio_movil/variacion_reciente, ver ahi `MODELOS_PARAMETRO_SIN_SUSTENTO`
# y `_catalogo_activo`). Esa exclusion vive en la capa de servicio; se declara
# aqui explicitamente porque `OBSERVACIONES_MINIMAS_MODELO` y el catalogo de
# ajuste viven en esta capa de modelos.
FOURIER_K1_PREFIJO = "fourier_k1__"
CANDIDATO_SEASONAL_NAIVE = "seasonal_naive"
MODELOS_FOURIER_BASE = tuple(
    m for m in MODELOS_INTERPRETABLES if m not in {"promedio_movil", "variacion_reciente"}
)
MODELOS_FOURIER_K1 = tuple(f"{FOURIER_K1_PREFIJO}{m}" for m in MODELOS_FOURIER_BASE)
#: Los 21 candidatos productivos: 10 modelos base + 10 variantes Fourier K=1 +
#: Seasonal Naive. Fuente unica que consume servicio_proyeccion.py.
CATALOGO_POOL_CALENDARIO = MODELOS_FOURIER_BASE + MODELOS_FOURIER_K1 + (CANDIDATO_SEASONAL_NAIVE,)


#: Observaciones minimas de cada modelo, DERIVADAS de su propia formulacion.
#:
#: AUDITORIA 12-08-2026, P0-E. Estas cifras sustituyen a `max(18, 0,60 n)` como
#: origen inicial del backtesting. No son un catalogo de valores elegidos: cada
#: una se deduce del modelo, y la derivacion esta escrita al lado.
#:
#: El criterio es la CARDINALIDAD: numero de parametros mas uno. Con `n = k` el
#: minimo se alcanza con residuo nulo y la solucion no es unica, de ahi
#: `n >= k + 1` para los modelos ajustados. Los modelos cuyos parametros son
#: funcion CERRADA de observaciones concretas -naive y drift- no minimizan nada y
#: solo exigen que esas observaciones existan.
#:
#: CORREGIDO el 16-08-2026 (P0-E). Hasta esta fecha este comentario afirmaba que
#: «el criterio es la IDENTIFICACION» y que un parametro «esta identificado
#: cuando el numero de ecuaciones SUPERA al de incognitas». **Ambas afirmaciones
#: son incorrectas**: contar parametros da una condicion NECESARIA para intentar
#: el ajuste sin interpolar, no una condicion suficiente, y no equivale a
#: identificabilidad estadistica. `criterios.py::C-WF-002` ya se habia corregido
#: en este sentido el 15-08-2026 y este bloque habia quedado contradiciendolo.
#: Los numeros NO cambian; cambia lo que se afirma de ellos.
OBSERVACIONES_MINIMAS_MODELO: dict[str, int] = {
    # yhat = y_T. Ningun parametro estimado: basta que exista la ultima observacion.
    "naive": 1,
    # pendiente = (y_T - y_1)/(T - 1), forma cerrada. Exige t_T != t_1.
    "drift": 2,
    # OLS con beta_0 y beta_1: k = 2, luego n >= 3 para que no interpole.
    "lineal": 3,
    "logaritmico": 3,
    # OLS sobre ln(y) mas el factor smearing, que es media de exp(residuos): k = 2.
    "exponencial_log_lineal": 3,
    # Huber estima ademas la ESCALA: beta_0, beta_1 y sigma, k = 3, luego n >= 4.
    "huber": 4,
    # Excepcion propia del modelo: len(y) >= 4 y al menos 3 variaciones finitas.
    "variacion_lineal": 4,
    "log_variacion": 4,
    # alpha, beta*, l0 y b0 por SSE de un paso: k = 4, luego n >= 5.
    "holt_lineal": 5,
    # alpha, beta*, PHI, l0 y b0: k = 5. Es el maximo del catalogo, luego n >= 6.
    "holt_amortiguado": 6,
    # Excluidos del catalogo por `ventana = 6` sin sustento (P0-B). Su minimo se
    # declara por completitud: no participa mientras no compitan.
    "promedio_movil": 2,
    "variacion_reciente": 3,
}


# post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04). Minimos de
# las variantes calendario, derivados igual que los del resto del catalogo
# (cardinalidad: numero de parametros mas uno).
# - Fourier K=1: la regresion auxiliar y_t = alpha + beta*t + a*sin(2*pi*t/12)
#   + b*cos(2*pi*t/12) tiene k=4 parametros propios, luego exige n>=5 para no
#   interpolar; el modelo base se ajusta despues sobre la serie desestacio-
#   nalizada, que tiene el mismo largo n, por lo que su propio minimo tambien
#   debe cumplirse. El minimo combinado es max(5, minimo_del_modelo_base).
# - Seasonal Naive (m=12): el pronostico de h=1 usa el valor observado 12
#   posiciones atras (mismo mes del año anterior); con menos de 12
#   observaciones ese valor no existe. Minimo = 12.
for _base_fourier in MODELOS_FOURIER_BASE:
    OBSERVACIONES_MINIMAS_MODELO[f"{FOURIER_K1_PREFIJO}{_base_fourier}"] = max(
        5, OBSERVACIONES_MINIMAS_MODELO[_base_fourier]
    )
OBSERVACIONES_MINIMAS_MODELO[CANDIDATO_SEASONAL_NAIVE] = 12
del _base_fourier


def observaciones_minimas_catalogo(modelos: Any = None) -> int:
    """Observaciones minimas para que TODOS los candidatos sean estimables.

    Es el maximo de los minimos, y tomar el maximo se deriva de la
    COMPARABILIDAD. `C-SEL-001` compara sobre la muestra comun: los pares
    (objetivo, horizonte) con error finito en **todos** los candidatos. Si el
    primer origen fuera menor que el minimo de alguno, ese candidato no
    produciria error en los primeros origenes y encogeria la muestra comun **para
    todos**, de modo que la comparacion se decidiria sobre el subconjunto que
    impone el modelo mas fragil.

    LIMITACION DECLARADA (P0-E, abierta). Esa derivacion sustenta que el primer
    origen no puede ser MENOR que este maximo -condicion necesaria-, pero **no
    demuestra que deba ser exactamente este valor**. Ninguna fuente determina
    donde empieza la evaluacion: FPP3 5.10 pide que el entrenamiento no sea
    «pequeno» sin operacionalizar el termino, y Tashman (2000) no fija ventana
    inicial. `N0 = 6` es una decision provisional del diseno del backtesting, y
    su variacion cambia el modelo seleccionado en parte de las series evaluadas.
    No leer esta funcion como el cierre de P0-E.
    """
    nombres = tuple(modelos) if modelos is not None else MODELOS_INTERPRETABLES
    minimos = [OBSERVACIONES_MINIMAS_MODELO[n] for n in nombres if n in OBSERVACIONES_MINIMAS_MODELO]
    return max(minimos) if minimos else 2


def ajustar_modelo_interpretable(
    nombre: str,
    t: Any,
    y: Any,
    forzar_tendencia: bool = False,
) -> dict[str, Any]:
    """Ajusta un modelo por nombre y devuelve predicción, residuos y métricas."""
    t_arr, y_arr = _limpiar_xy(t, y)
    if len(y_arr) < 2:
        raise ValueError("Se requieren al menos dos observaciones para ajustar modelo.")

    nombre = nombre.lower()
    if nombre == "lineal":
        resultado = _ajustar_lineal(t_arr, y_arr)
    elif nombre == "logaritmico":
        resultado = _ajustar_logaritmico(t_arr, y_arr)
    elif nombre == "exponencial_log_lineal":
        resultado = _ajustar_exponencial_log_lineal(t_arr, y_arr)
    elif nombre == "huber":
        resultado = _ajustar_huber(t_arr, y_arr)
    elif nombre == "holt_lineal":
        resultado = _ajustar_holt_lineal(t_arr, y_arr, amortiguado=False)
    elif nombre == "holt_amortiguado":
        resultado = _ajustar_holt_lineal(t_arr, y_arr, amortiguado=True)
    elif nombre == "variacion_lineal":
        resultado = _ajustar_variacion_lineal(t_arr, y_arr, logaritmica=False)
    elif nombre == "log_variacion":
        resultado = _ajustar_variacion_lineal(t_arr, y_arr, logaritmica=True)
    elif nombre == "naive":
        resultado = _ajustar_naive(t_arr, y_arr)
    elif nombre == "drift":
        resultado = _ajustar_drift(t_arr, y_arr)
    elif nombre == "promedio_movil":
        resultado = _ajustar_promedio_movil(t_arr, y_arr)
    elif nombre == "variacion_reciente":
        resultado = _ajustar_variacion_reciente(t_arr, y_arr)
    elif nombre == CANDIDATO_SEASONAL_NAIVE:
        resultado = _ajustar_seasonal_naive(t_arr, y_arr)
    elif nombre.startswith(FOURIER_K1_PREFIJO):
        resultado = _ajustar_fourier_k1(t_arr, y_arr, modelo_base=nombre[len(FOURIER_K1_PREFIJO):])
    else:
        raise ValueError(f"Modelo no soportado: {nombre}")

    yhat = np.asarray(resultado["predict"](t_arr), dtype=float)
    if forzar_tendencia:
        yhat = forzar_no_decreciente(yhat)
    residuos = y_arr - yhat
    k = int(resultado["k"])
    metricas = calcular_metricas(y_arr, yhat, k=k)
    if resultado.get("es_benchmark"):
        # Benchmarks simples no tienen verosimilitud comparable con OLS/Huber.
        metricas["aic"] = float("inf")
        metricas["aicc"] = float("inf")
    diagnostico = evaluar_residuos(residuos, tipo_modelo=nombre)
    resultado.update(
        {
            "t_obs": t_arr,
            "y_obs": y_arr,
            "yhat": yhat,
            "residuos": residuos,
            "metricas_ajuste": metricas,
            "diagnostico_residuos": diagnostico,
            "parametros": resultado.get("parametros", {}),
            "es_benchmark": bool(resultado.get("es_benchmark", False)),
        }
    )
    return resultado


def proyectar_modelo(modelo: dict[str, Any], t_futuro: Any, forzar_desde: float | None = None) -> np.ndarray:
    """Predice con un modelo ajustado y aplica restricción opcional no decreciente."""
    valores = np.asarray(modelo["predict"](np.asarray(t_futuro, dtype=float)), dtype=float)
    if forzar_desde is not None and len(valores):
        valores = forzar_no_decreciente(np.concatenate([[float(forzar_desde)], valores]))[1:]
    return valores


def ajustar_modelos_candidatos(
    t: Any,
    y: Any,
    modelos: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ajusta solo los modelos solicitados, o todos si no se especifican."""
    candidatos: list[dict[str, Any]] = []
    modelos_objetivo = tuple(modelos) if modelos is not None else MODELOS_INTERPRETABLES
    for nombre in modelos_objetivo:
        try:
            # AUDITORIA 09-08-2026, P0-B. Se retira la puerta
            # `len(y) < MIN_OBS_HUBER` (8): era un minimo sin fuente que excluia
            # a Huber en series donde es perfectamente estimable -medido: en 2 de
            # 10 series del anexo-. La regresion de Huber sobre un regresor es
            # estimable desde n>=3; si no lo fuera, el ajuste levanta excepcion y
            # el candidato queda excluido con su error registrado, que es el
            # mecanismo general de elegibilidad.
            candidatos.append(ajustar_modelo_interpretable(nombre, t, y))
        except Exception as exc:
            candidatos.append(
                {
                    "nombre": nombre,
                    "name": nombre,
                    "error": str(exc),
                    "metricas_ajuste": {},
                    "diagnostico_residuos": {},
                    "es_benchmark": nombre in MODELOS_BENCHMARK,
                }
            )
    return candidatos


def seleccionar_modelo_por_evidencia(
    candidatos: list[dict[str, Any]],
    backtesting_por_modelo: dict[str, dict[str, Any]],
    horizonte: int,
) -> dict[str, Any]:
    """RETIRADA COMO SELECTOR el 09-08-2026 (auditoria P0-A). Ya no se invoca.

    Combinaba backtesting, parsimonia, residuos e interpretabilidad en una unica
    funcion de puntaje con ONCE coeficientes sin ninguna fuente:

        score = rmse*1.0 + mae*0.75 + min(mase,3)*4.0 + sesgo*0.5
              + estabilidad*4.0 + max(0, min(rrmse_naive,rrmse_drift)-1)*12.0
              + max(aicc,-1000)*0.001
              + min(|dw-2|,2)*4.0 + n_alertas*(0.8|1.2) + k*0.6
              + 0.8 si es benchmark + 1.2 si es promedio_movil
              + 1.0 si es naive y horizonte > 3

    Dos de esos terminos son **excepciones por identidad del modelo**, que los
    requisitos metodologicos del proyecto prohiben expresamente como decisores,
    igual que los pesos arbitrarios.

    Se invocaba como respaldo cuando C-SEL-001 no podia decidir, y ademas desde
    DENTRO del bucle de horizontes, de modo que podia entregar modelos distintos
    por horizonte. Hoy, cuando no hay evidencia fuera de muestra comparable, el
    horizonte no se entrega y se declara la causa.

    Se conserva la definicion sin llamadas para dejar constancia auditable de lo
    que se retiro; `tests/test_fundamentacion_metodologica.py` verifica que la
    ruta productiva no la invoca.
    """
    evaluables: list[tuple[float, dict[str, Any], list[str], dict[str, Any]]] = []
    descartados: list[dict[str, Any]] = []
    for candidato in candidatos:
        if "predict" not in candidato:
            continue
        nombre = candidato["nombre"]
        bt = backtesting_por_modelo.get(nombre, {})
        metricas_bt = bt.get("metricas", {})
        metricas_ajuste = candidato.get("metricas_ajuste", {})
        diagnostico = candidato.get("diagnostico_residuos", {})

        if not bt.get("ejecutado") or int(bt.get("iteraciones", 0) or metricas_bt.get("iteraciones", 0) or 0) < MIN_ITERACIONES_SELECCION:
            descartados.append(
                {
                    "nombre": nombre,
                    "razones": ["Backtesting insuficiente para seleccionar el modelo."],
                }
            )
            continue

        comparacion = comparar_modelo_con_benchmarks(nombre, backtesting_por_modelo)
        mape = _numero(metricas_bt.get("mape"), default=100.0)
        smape = _numero(metricas_bt.get("smape"), default=100.0)
        rmse = _numero(metricas_bt.get("rmse"), default=1e9)
        mae = _numero(metricas_bt.get("mae"), default=1e9)
        mase = _numero(metricas_bt.get("mase"), default=1e9)
        sesgo = abs(_numero(metricas_bt.get("sesgo_medio", metricas_bt.get("error_medio")), default=1e9))
        estabilidad = _numero(metricas_bt.get("estabilidad_error"), default=1e9)
        aicc = _numero(metricas_ajuste.get("aicc"), default=1e9)
        dw = _numero(diagnostico.get("durbin_watson"), default=2.0)
        k = int(candidato.get("k", 2))

        razones_descartar: list[str] = []
        if not (math.isfinite(rmse) and math.isfinite(mae)):
            razones_descartar.append("Métricas MAE/RMSE no finitas.")
        # D-9: se retira el descarte de candidatos por MAPE > 25 % o sMAPE > 30 %.
        # Ambos cortes eran internos y sin fuente. El descarte por no igualar a
        # los benchmarks reales de backtesting se conserva: esa comparacion si
        # es relativa a una referencia observada.
        if comparacion.get("modelo_no_supera_benchmarks") and not candidato.get("es_benchmark"):
            razones_descartar.append("No iguala razonablemente a naive o drift en RMSE.")
        if razones_descartar:
            descartados.append({"nombre": nombre, "razones": razones_descartar, "comparacion_benchmarks": comparacion})
            continue

        penalizacion_residuos = 0.0
        if math.isfinite(dw) and not candidato.get("es_benchmark") and nombre not in MODELOS_SERIE_TEMPORAL:
            penalizacion_residuos += min(abs(dw - 2.0), 2.0) * 4.0
        if diagnostico.get("alertas"):
            penalizacion_residuos += len(diagnostico["alertas"]) * (0.8 if candidato.get("es_benchmark") else 1.2)
        penalizacion_complejidad = k * 0.6
        penalizacion_benchmark = 0.8 if candidato.get("es_benchmark") else 0.0
        if nombre == "promedio_movil":
            penalizacion_benchmark += 1.2
        if nombre == "naive" and horizonte > 3:
            penalizacion_benchmark += 1.0
        rrmse_naive = _numero(comparacion.get("rrmse_naive"), default=1.0)
        rrmse_drift = _numero(comparacion.get("rrmse_drift"), default=1.0)
        mejor_rrmse = min(rrmse_naive, rrmse_drift)
        score = rmse * 1.0 + mae * 0.75 + min(mase, 3.0) * 4.0 + sesgo * 0.5 + estabilidad * 4.0
        if math.isfinite(mejor_rrmse):
            score += max(0.0, mejor_rrmse - 1.0) * 12.0
        score += max(aicc, -1000.0) * 0.001
        score += penalizacion_residuos + penalizacion_complejidad + penalizacion_benchmark

        razones = [
            f"RMSE backtesting={_fmt(metricas_bt.get('rmse'))}",
            f"MAE backtesting={_fmt(metricas_bt.get('mae'))}",
            f"MASE={_fmt(metricas_bt.get('mase'))}",
            f"rRMSE naive={_fmt(comparacion.get('rrmse_naive'))}",
            f"rRMSE drift={_fmt(comparacion.get('rrmse_drift'))}",
            f"Sesgo medio={_fmt(metricas_bt.get('sesgo_medio', metricas_bt.get('error_medio')))}",
            f"Estabilidad error={_fmt(metricas_bt.get('estabilidad_error'))}",
            f"MAPE backtesting={_fmt(metricas_bt.get('mape'))}%",
            f"AICc={_fmt(metricas_ajuste.get('aicc'))}",
            f"Durbin-Watson={_fmt(dw)}",
            f"Parametros={k}",
        ]
        if candidato.get("es_benchmark"):
            razones.append("Metodo benchmark admitido como escenario principal si valida mejor fuera de muestra.")
        if comparacion.get("supera_o_iguala_naive_rmse"):
            razones.append("Supera o iguala razonablemente benchmark naive en RMSE.")
        if comparacion.get("supera_o_iguala_drift_rmse"):
            razones.append("Supera o iguala razonablemente benchmark drift en RMSE.")
        evaluables.append((score, candidato, razones, comparacion))

    if not evaluables:
        fallback = _mejor_candidato_no_elegible(candidatos, backtesting_por_modelo)
        fallback["no_recomendado"] = True
        fallback["razones_no_recomendado"] = _razones_descartes(descartados) or [
            "Ningun modelo estadístico supera los benchmarks con diagnostico residual aceptable."
        ]
        fallback["comparacion_benchmarks"] = comparar_modelo_con_benchmarks(
            fallback.get("nombre", ""), backtesting_por_modelo
        )
        fallback["score_seleccion"] = float("inf")
        fallback["razones_seleccion"] = fallback["razones_no_recomendado"]
        fallback["justificacion"] = (
            "No se selecciona un modelo proyectable: ningun candidato supera los benchmarks "
            "simples con calidad residual suficiente. "
            + " ".join(fallback["razones_no_recomendado"])
        )
        return fallback

    dominante = _benchmark_dominante(evaluables, backtesting_por_modelo)
    if dominante is not None:
        _, mejor, razones, comparacion = dominante
        mejor["score_seleccion"] = 0.0
        mejor["razones_seleccion"] = razones + ["Benchmark dominante por RMSE, MAE y MAPE del horizonte evaluado."]
        mejor["comparacion_benchmarks"] = comparacion
        mejor["ranking_backtesting"] = resumir_ranking_backtesting(backtesting_por_modelo)
        mejor["descartes_modelos"] = descartados
        mejor["no_recomendado"] = False
        mejor["justificacion"] = (
            f"Se selecciona {mejor['nombre_visible']} porque domina a los modelos candidatos "
            "en RMSE, MAE y MAPE de backtesting para este horizonte. "
            + " ".join(mejor["razones_seleccion"])
        )
        return mejor

    evaluables.sort(key=lambda item: item[0])
    mejor_score, mejor, razones, comparacion = evaluables[0]
    mejor["score_seleccion"] = float(mejor_score)
    mejor["razones_seleccion"] = razones
    mejor["comparacion_benchmarks"] = comparacion
    mejor["ranking_backtesting"] = resumir_ranking_backtesting(backtesting_por_modelo)
    mejor["descartes_modelos"] = descartados
    mejor["no_recomendado"] = False
    mejor["justificacion"] = (
        f"Se selecciona {mejor['nombre_visible']} por equilibrio entre validación temporal, "
        "desempeño frente a benchmarks, MAE/RMSE, MASE, sesgo, estabilidad de errores, "
        "diagnostico residual, parsimonia e interpretabilidad. "
        + " ".join(razones)
    )
    return mejor


def _benchmark_dominante(
    evaluables: list[tuple[float, dict[str, Any], list[str], dict[str, Any]]],
    backtesting_por_modelo: dict[str, dict[str, Any]],
) -> tuple[float, dict[str, Any], list[str], dict[str, Any]] | None:
    """Prioriza drift/naive si dominan claramente fuera de muestra."""
    por_nombre = {item[1].get("nombre"): item for item in evaluables}
    for nombre in ("drift", "naive"):
        item = por_nombre.get(nombre)
        if item is None:
            continue
        metricas_ref = (backtesting_por_modelo.get(nombre, {}).get("metricas") or {})
        rmse_ref = _numero(metricas_ref.get("rmse"), default=float("inf"))
        mae_ref = _numero(metricas_ref.get("mae"), default=float("inf"))
        mape_ref = _numero(metricas_ref.get("mape"), default=float("inf"))
        if not (math.isfinite(rmse_ref) and math.isfinite(mae_ref)):
            continue
        domina = True
        for _, candidato, _, _ in evaluables:
            otro = candidato.get("nombre")
            if otro == nombre:
                continue
            metricas_otro = (backtesting_por_modelo.get(str(otro), {}).get("metricas") or {})
            rmse_otro = _numero(metricas_otro.get("rmse"), default=float("inf"))
            mae_otro = _numero(metricas_otro.get("mae"), default=float("inf"))
            mape_otro = _numero(metricas_otro.get("mape"), default=float("inf"))
            if rmse_ref > rmse_otro * 1.02 or mae_ref > mae_otro * 1.02:
                domina = False
                break
            if math.isfinite(mape_ref) and math.isfinite(mape_otro) and mape_ref > mape_otro * 1.02:
                domina = False
                break
        if domina:
            return item
    return None


def comparar_modelo_con_benchmarks(
    nombre_modelo: str,
    backtesting_por_modelo: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compara un modelo candidato contra naive y drift en backtesting."""
    bt_modelo = backtesting_por_modelo.get(nombre_modelo, {})
    metricas_modelo = bt_modelo.get("metricas", {}) if bt_modelo else {}
    rmse_modelo = _numero(metricas_modelo.get("rmse"), default=float("nan"))
    mae_modelo = _numero(metricas_modelo.get("mae"), default=float("nan"))
    mase_modelo = _numero(metricas_modelo.get("mase"), default=float("nan"))

    naive = backtesting_por_modelo.get("naive", {})
    drift = backtesting_por_modelo.get("drift", {})
    rmse_naive = _numero((naive.get("metricas") or {}).get("rmse"), default=float("nan"))
    rmse_drift = _numero((drift.get("metricas") or {}).get("rmse"), default=float("nan"))
    mae_naive = _numero((naive.get("metricas") or {}).get("mae"), default=float("nan"))
    mae_drift = _numero((drift.get("metricas") or {}).get("mae"), default=float("nan"))

    rrmse_naive = _ratio(rmse_modelo, rmse_naive)
    rrmse_drift = _ratio(rmse_modelo, rmse_drift)
    rmae_naive = _ratio(mae_modelo, mae_naive)
    rmae_drift = _ratio(mae_modelo, mae_drift)

    tolerancia = TOLERANCIA_RRMSE_BENCHMARK
    supera_naive = math.isfinite(rrmse_naive) and rrmse_naive < 1.0
    supera_drift = math.isfinite(rrmse_drift) and rrmse_drift < 1.0
    iguala_naive = math.isfinite(rrmse_naive) and rrmse_naive <= tolerancia
    iguala_drift = math.isfinite(rrmse_drift) and rrmse_drift <= tolerancia
    peor_naive = math.isfinite(rrmse_naive) and rrmse_naive > UMBRAL_RRMSE_PEOR_BENCHMARK
    peor_drift = math.isfinite(rrmse_drift) and rrmse_drift > UMBRAL_RRMSE_PEOR_BENCHMARK
    if nombre_modelo == "naive":
        iguala_naive = True
        peor_naive = False
    if nombre_modelo == "drift":
        iguala_drift = True
        peor_drift = False

    return {
        "modelo": nombre_modelo,
        "rmse_modelo": rmse_modelo,
        "mae_modelo": mae_modelo,
        "mase_modelo": mase_modelo,
        "rmse_naive": rmse_naive,
        "rmse_drift": rmse_drift,
        "mae_naive": mae_naive,
        "mae_drift": mae_drift,
        "rrmse_naive": rrmse_naive,
        "rrmse_drift": rrmse_drift,
        "rmae_naive": rmae_naive,
        "rmae_drift": rmae_drift,
        "supera_naive_rmse": bool(supera_naive),
        "supera_drift_rmse": bool(supera_drift),
        "supera_o_iguala_naive_rmse": bool(iguala_naive),
        "supera_o_iguala_drift_rmse": bool(iguala_drift),
        "peor_que_naive_rmse": bool(peor_naive),
        "peor_que_drift_rmse": bool(peor_drift),
        "modelo_no_supera_benchmarks": bool(peor_naive and (peor_drift or not math.isfinite(rrmse_drift))),
    }


def resumir_ranking_backtesting(backtesting_por_modelo: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Resume ganadores por métrica fuera de muestra."""
    filas: list[dict[str, Any]] = []
    for nombre, resultado in backtesting_por_modelo.items():
        metricas = resultado.get("metricas", {}) if resultado else {}
        if not resultado.get("ejecutado"):
            continue
        filas.append(
            {
                "nombre": nombre,
                "rmse": _numero(metricas.get("rmse"), default=float("nan")),
                "mae": _numero(metricas.get("mae"), default=float("nan")),
                "mape": _numero(metricas.get("mape"), default=float("nan")),
                "smape": _numero(metricas.get("smape"), default=float("nan")),
                "mase": _numero(metricas.get("mase"), default=float("nan")),
            }
        )
    return {
        "mejor_rmse": _mejor_por(filas, "rmse"),
        "mejor_mae": _mejor_por(filas, "mae"),
        "mejor_mape": _mejor_por(filas, "mape"),
        "modelos": filas,
    }


def _mejor_candidato_no_elegible(
    candidatos: list[dict[str, Any]],
    backtesting_por_modelo: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Devuelve el candidato no benchmark con menor RMSE disponible para diagnostico."""
    opciones: list[tuple[float, dict[str, Any]]] = []
    for candidato in candidatos:
        if "predict" not in candidato or candidato.get("es_benchmark"):
            continue
        nombre = candidato.get("nombre", "")
        rmse = _numero((backtesting_por_modelo.get(nombre, {}).get("metricas") or {}).get("rmse"), default=1e12)
        opciones.append((rmse, candidato))
    if opciones:
        opciones.sort(key=lambda item: item[0])
        return opciones[0][1]
    for candidato in candidatos:
        if "predict" in candidato:
            return candidato
    raise ValueError("No hay modelos evaluables para selección.")


def _razones_descartes(descartados: list[dict[str, Any]]) -> list[str]:
    razones: list[str] = []
    for item in descartados:
        nombre = item.get("nombre", "modelo")
        for razon in item.get("razones", []):
            if "Benchmark usado" in str(razon):
                continue
            razones.append(f"{nombre}: {razon}")
    return razones[:12]


def _ajustar_lineal(t: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    model = LinearRegression()
    model.fit(t.reshape(-1, 1), y)

    def predict(tt: Any) -> np.ndarray:
        return model.predict(np.asarray(tt, dtype=float).reshape(-1, 1))

    return {
        "nombre": "lineal",
        "name": "Lineal (OLS)",
        "nombre_visible": "Lineal (OLS)",
        "k": 2,
        "predict": predict,
        "parametros": {"beta_0": float(model.intercept_), "beta_1": float(model.coef_[0])},
        "tendencia_ok": float(model.coef_[0]) >= 0,
    }


def _ajustar_logaritmico(t: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 11 - semantica temporal).
    # `t` aqui es el INDICE_TEMPORAL_DEL_MODELO (tau=1..n dentro de la
    # ventana de entrenamiento), no un "t" calendario anclado en ANIO_BASE ni
    # el periodo base economico del ICOCIV. Con tau>=1 desde el llamador,
    # `desplazamiento` siempre evalua a 0 (min(t)=1 en toda ventana walk-
    # forward expansiva desde el origen de la serie); se conserva la formula
    # -no solo el caso feliz- porque sigue siendo la salvaguarda correcta si
    # algun llamador futuro pasa un `t` que no arranque exactamente en 1.
    desplazamiento = max(0.0, 1.0 - float(np.min(t)))
    X = np.log(t.reshape(-1, 1) + desplazamiento)
    model = LinearRegression()
    model.fit(X, y)

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float).reshape(-1, 1)
        return model.predict(np.log(arr + desplazamiento))

    return {
        "nombre": "logaritmico",
        "name": "Logarítmica temporal (OLS)",
        "nombre_visible": "Logarítmica temporal (OLS)",
        "k": 2,
        "predict": predict,
        "parametros": {
            "beta_0": float(model.intercept_),
            "beta_1": float(model.coef_[0]),
            "desplazamiento_t": float(desplazamiento),
            "logaritmo": "ln",
        },
        "tendencia_ok": float(model.coef_[0]) >= 0,
    }


def _ajustar_exponencial_log_lineal(
    t: np.ndarray,
    y: np.ndarray,
    metodo_retransformacion: str = "smearing_duan",
) -> dict[str, Any]:
    if np.any(y <= 0):
        raise ValueError("La regresion exponencial/log-lineal requiere índices positivos.")
    model = LinearRegression()
    log_y = np.log(y)
    model.fit(t.reshape(-1, 1), log_y)
    log_ajustado = np.asarray(model.predict(t.reshape(-1, 1)), dtype=float)
    residuos_log = log_y - log_ajustado
    sigma2_log = float(np.var(residuos_log, ddof=1)) if len(residuos_log) > 1 else 0.0
    smearing_factor = float(np.mean(np.exp(residuos_log))) if len(residuos_log) else 1.0
    if not np.isfinite(smearing_factor) or smearing_factor <= 0:
        smearing_factor = 1.0
    metodo = (metodo_retransformacion or "smearing_duan").lower()
    if metodo not in {"smearing_duan", "lognormal"}:
        metodo = "smearing_duan"
    factor_retransformacion = float(math.exp(sigma2_log / 2.0)) if metodo == "lognormal" else smearing_factor

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float).reshape(-1, 1)
        pred_log = np.asarray(model.predict(arr), dtype=float)
        return np.exp(pred_log) * factor_retransformacion

    return {
        "nombre": "exponencial_log_lineal",
        "name": "Exponencial/log-lineal",
        "nombre_visible": "Exponencial/log-lineal",
        "k": 2,
        "predict": predict,
        "parametros": {
            "beta_0": float(model.intercept_),
            "beta_1": float(model.coef_[0]),
            "sigma2_log": sigma2_log,
            "smearing_factor": smearing_factor,
            "metodo_retransformacion": metodo,
            "factor_retransformacion": factor_retransformacion,
            "logaritmo": "ln",
            "transformacion": "ln(y_t) = beta_0 + beta_1 * t",
            "prediccion_original": (
                "exp(beta_0 + beta_1 * t) * smearing_factor"
                if metodo == "smearing_duan"
                else "exp(beta_0 + beta_1 * t + sigma2_log / 2)"
            ),
        },
        "tendencia_ok": float(model.coef_[0]) >= 0,
    }


def _ajustar_huber(t: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    model = HuberRegressor(epsilon=1.35, alpha=0.0001, max_iter=2000)
    model.fit(t.reshape(-1, 1), y)

    def predict(tt: Any) -> np.ndarray:
        return model.predict(np.asarray(tt, dtype=float).reshape(-1, 1))

    return {
        "nombre": "huber",
        "name": "Huber (robusta)",
        "nombre_visible": "Huber (robusta)",
        "k": 2,
        "predict": predict,
        "parametros": {"beta_0": float(model.intercept_), "beta_1": float(model.coef_[0])},
        "tendencia_ok": float(model.coef_[0]) >= 0,
    }


#: Cotas de los parámetros de suavizamiento de Holt. **Las tres tienen fuente.**
#:
#: Hyndman y Athanasopoulos (2021), *Forecasting: Principles and Practice*, 3.ª
#: ed., §8.1-8.2:
#:
#: * ``0 <= alpha <= 1`` y ``0 <= beta* <= alpha``;
#: * «The smoothing parameters, alpha and beta*, and the initial values l0 y b0
#:   **are estimated by minimising the SSE** for the one-step training errors»;
#: * «we usually restrict phi to a minimum of 0.8 and a maximum of 0.98».
#:
#: AUDITORÍA DE FUNDAMENTACIÓN, 09-08-2026 (hallazgo C-01). Hasta esta fecha los
#: coeficientes eran constantes fijadas internamente —alpha=0,65, beta=0,20,
#: phi=0,88— sin ninguna fuente que las respaldara, mientras el método se
#: publicaba como «Holt» citando a FPP3. Gardner (2006), *Exponential smoothing:
#: the state of the art — Part II*, es explícito: «there is no longer any excuse
#: for using arbitrary parameters», y Gardner (1985) concluye que es preferible
#: estimar alpha de los datos antes que fijarlo por conjetura.
#:
#: Se sustituyen por la estimación que la fuente define. Lo que queda fijado
#: —las cotas— sí está sustentado.
HOLT_ALPHA_MIN, HOLT_ALPHA_MAX = 1e-4, 1.0 - 1e-4
HOLT_BETA_MIN = 1e-4
#: FPP3 §8.2. Fuera de este rango el amortiguamiento es o demasiado fuerte o
#: indistinguible del caso no amortiguado.
HOLT_PHI_MIN, HOLT_PHI_MAX = 0.80, 0.98

CRITERIO_HOLT = (
    "Parámetros estimados de los datos minimizando el SSE de los errores de un "
    "paso dentro de muestra (Hyndman y Athanasopoulos, 2021, §8.1-8.2). Se "
    "estiman alpha, beta* y los estados iniciales l0 y b0; en la variante "
    "amortiguada se estima además phi dentro del rango [0,80; 0,98] que la "
    "misma fuente recomienda. La restricción 0 < beta* <= alpha es la de la "
    "fuente. La optimización es determinista y no depende del entorno."
)


def _holt_sse_con_estados_optimos(
    y: np.ndarray, alpha: float, beta: float, phi: float
) -> tuple[float, float, float]:
    """SSE mínimo sobre (l0, b0) para unos parámetros de suavizamiento dados.

    Para alpha, beta y phi fijos la recursión de Holt es **afín** en el par de
    estados iniciales: cada nivel y cada tendencia son una constante que depende
    de los datos más una combinación lineal de ``l0`` y ``b0``. Por tanto los
    valores ajustados también lo son y el SSE es una forma cuadrática, cuyo
    mínimo en ``(l0, b0)`` se resuelve por mínimos cuadrados **de forma exacta**,
    sin búsqueda.

    Eso permite estimar los cuatro parámetros de FPP3 §8.1 buscando solo sobre
    los dos (o tres) de suavizamiento, que es lo que hace el optimizador.

    Devuelve ``(sse, l0, b0)``.
    """
    base = _holt_ajustados(y, alpha, beta, phi, 0.0, 0.0)
    col_l = _holt_ajustados(y, alpha, beta, phi, 1.0, 0.0) - base
    col_b = _holt_ajustados(y, alpha, beta, phi, 0.0, 1.0) - base

    objetivo = y - base
    diseno = np.column_stack([col_l, col_b])
    try:
        solucion, *_ = np.linalg.lstsq(diseno, objetivo, rcond=None)
    except np.linalg.LinAlgError:
        return float("inf"), float(y[0]), 0.0
    l0, b0 = float(solucion[0]), float(solucion[1])
    residuos = objetivo - diseno @ solucion
    return float(np.sum(residuos**2)), l0, b0


def estimar_parametros_holt(
    y: np.ndarray, amortiguado: bool
) -> tuple[float, float, float, float, float]:
    """Estima (alpha, beta*, phi, l0, b0) minimizando el SSE de un paso.

    Procedimiento de Hyndman y Athanasopoulos (2021) §8.1-8.2, con las cotas de
    la propia fuente. La búsqueda es **determinista y reproducible**: una rejilla
    gruesa fija seguida de un refinamiento local desde el mejor punto de esa
    rejilla. No hay semilla aleatoria ni dependencia del entorno.

    Se usa rejilla + refinamiento y no un único arranque porque Gardner (2006)
    advierte que la superficie de respuesta del suavizamiento exponencial **no
    es necesariamente convexa** y recomienda explorar varios puntos de partida
    para no quedar atrapado en un mínimo local.

    Devuelve ``(alpha, beta, phi, l0, b0)``.
    """
    from scipy.optimize import minimize

    phis = (1.0,) if not amortiguado else (0.80, 0.86, 0.92, 0.98)
    rejilla_a = np.arange(0.1, 1.0, 0.1)

    mejor = (float("inf"), 0.5, 0.1, phis[0])
    for phi in phis:
        for a in rejilla_a:
            for b in np.arange(0.1, float(a) + 1e-9, 0.1):
                sse, _, _ = _holt_sse_con_estados_optimos(y, float(a), float(b), float(phi))
                if sse < mejor[0]:
                    mejor = (sse, float(a), float(b), float(phi))

    _, a0, b0_par, phi0 = mejor

    def objetivo(p: np.ndarray) -> float:
        a = float(np.clip(p[0], HOLT_ALPHA_MIN, HOLT_ALPHA_MAX))
        b = float(np.clip(p[1], HOLT_BETA_MIN, a))
        ph = float(np.clip(p[2], HOLT_PHI_MIN, HOLT_PHI_MAX)) if amortiguado else 1.0
        sse, _, _ = _holt_sse_con_estados_optimos(y, a, b, ph)
        return sse if math.isfinite(sse) else 1e300

    if amortiguado:
        p0 = np.array([a0, b0_par, phi0], dtype=float)
        cotas = [(HOLT_ALPHA_MIN, HOLT_ALPHA_MAX), (HOLT_BETA_MIN, HOLT_ALPHA_MAX),
                 (HOLT_PHI_MIN, HOLT_PHI_MAX)]
    else:
        p0 = np.array([a0, b0_par, 1.0], dtype=float)
        cotas = [(HOLT_ALPHA_MIN, HOLT_ALPHA_MAX), (HOLT_BETA_MIN, HOLT_ALPHA_MAX),
                 (1.0, 1.0)]

    try:
        res = minimize(objetivo, p0, method="L-BFGS-B", bounds=cotas,
                       options={"maxiter": 200, "ftol": 1e-10})
        candidato = res.x if res.success or np.all(np.isfinite(res.x)) else p0
    except Exception:
        candidato = p0

    alpha = float(np.clip(candidato[0], HOLT_ALPHA_MIN, HOLT_ALPHA_MAX))
    beta = float(np.clip(candidato[1], HOLT_BETA_MIN, alpha))
    phi = float(np.clip(candidato[2], HOLT_PHI_MIN, HOLT_PHI_MAX)) if amortiguado else 1.0

    # El refinamiento solo se acepta si no empeora el SSE de la rejilla.
    sse_ref, l0, b0 = _holt_sse_con_estados_optimos(y, alpha, beta, phi)
    if not math.isfinite(sse_ref) or sse_ref > mejor[0]:
        alpha, beta, phi = a0, b0_par, phi0
        _, l0, b0 = _holt_sse_con_estados_optimos(y, alpha, beta, phi)
    return alpha, beta, phi, l0, b0


#: Memoria de estimaciones por ventana de entrenamiento.
#:
#: El backtesting reajusta el mismo modelo sobre la MISMA ventana para cada
#: horizonte, de modo que sin memoria se repetiría la estimación decenas de
#: veces con idéntico resultado. La clave es el contenido exacto de la ventana,
#: así que la memoria **no puede** devolver el ajuste de otra ventana: no
#: introduce fuga de información entre orígenes.
_MEMORIA_HOLT: dict[tuple[str, bool, bytes], tuple[float, float, float, float, float]] = {}


def _estimar_holt_memoizado(y: np.ndarray, amortiguado: bool):
    clave = ("holt", bool(amortiguado), np.ascontiguousarray(y, dtype=float).tobytes())
    if clave not in _MEMORIA_HOLT:
        if len(_MEMORIA_HOLT) > 4096:
            _MEMORIA_HOLT.clear()
        _MEMORIA_HOLT[clave] = estimar_parametros_holt(y, amortiguado)
    return _MEMORIA_HOLT[clave]


def _ajustar_holt_lineal(t: np.ndarray, y: np.ndarray, amortiguado: bool = False) -> dict[str, Any]:
    """Ajusta Holt estimando sus parámetros de los datos (FPP3 §8.1-8.2).

    La estimación usa **solo** la ventana ``y`` que recibe. En el backtesting esa
    ventana es la historia disponible hasta el origen, de modo que los parámetros
    se reestiman en cada origen sin mirar el futuro; en el pronóstico final es
    toda la historia disponible. No hay una estimación única reutilizada.
    """
    nombre = "holt_amortiguado" if amortiguado else "holt_lineal"
    nombre_visible = "Holt tendencia amortiguada" if amortiguado else "Holt lineal"

    alpha, beta, phi, l0, b0 = _estimar_holt_memoizado(y, amortiguado)
    niveles, tendencias = _holt_suavizado(y, alpha=alpha, beta=beta, phi=phi, l0=l0, b0=b0)
    fitted_values = _holt_ajustados(y, alpha, beta, phi, l0, b0)

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float)
        ultimo_t = float(t[-1])
        ultimo_nivel = float(niveles[-1])
        ultima_tendencia = float(tendencias[-1])
        salida = []
        for objetivo in arr:
            if objetivo <= ultimo_t:
                idx = int(np.argmin(np.abs(t - objetivo)))
                salida.append(float(fitted_values[idx]))
            else:
                h = max(1, int(round(objetivo - ultimo_t)))
                if amortiguado:
                    factor = sum(phi ** i for i in range(1, h + 1))
                else:
                    factor = h
                salida.append(ultimo_nivel + factor * ultima_tendencia)
        return np.asarray(salida, dtype=float)

    parametros = {
        "alpha": alpha,
        "beta": beta,
        "phi": phi,
        "nivel_inicial": float(l0),
        "tendencia_inicial": float(b0),
        "nivel_final": float(niveles[-1]),
        "tendencia_final": float(tendencias[-1]),
        "criterio_estimacion": CRITERIO_HOLT,
        "estimacion": "SSE de un paso, minimizacion determinista",
        "restricciones": (
            f"0 < alpha < 1; 0 < beta <= alpha"
            + (f"; {HOLT_PHI_MIN} <= phi <= {HOLT_PHI_MAX}" if amortiguado else "; phi = 1")
        ),
        "fuente_parametrizacion": "Hyndman y Athanasopoulos (2021), FPP3, secciones 8.1-8.2",
        "observaciones_estimacion": int(len(y)),
        "backend": "interno",
    }
    # alpha, beta y los dos estados iniciales; phi ademas en la variante amortiguada.
    k = 5 if amortiguado else 4

    return {
        "nombre": nombre,
        "name": nombre_visible,
        "nombre_visible": nombre_visible,
        "k": k,
        "predict": predict,
        "parametros": parametros,
        "tendencia_ok": True,
    }


def _ajustar_variacion_lineal(t: np.ndarray, y: np.ndarray, logaritmica: bool = False) -> dict[str, Any]:
    """Modela variaciones mensuales y reconstruye el índice de forma recursiva."""
    if len(y) < 4:
        raise ValueError("Se requieren al menos 4 observaciones para modelar variaciones.")
    if logaritmica and np.any(y <= 0):
        raise ValueError("La log-variación requiere índices positivos.")
    if logaritmica:
        cambios = np.diff(np.log(y))
        nombre = "log_variacion"
        visible = "Modelo sobre log-variación mensual"
    else:
        base = np.where(np.abs(y[:-1]) > EPS_NUMERICO, y[:-1], np.nan)
        cambios = (y[1:] - y[:-1]) / base
        nombre = "variacion_lineal"
        visible = "Modelo sobre variación mensual"
    mask = np.isfinite(cambios)
    t_cambio = t[1:][mask]
    cambios = cambios[mask]
    if len(cambios) < 3:
        raise ValueError("No hay variaciones suficientes para ajustar el modelo.")
    model = LinearRegression()
    model.fit(t_cambio.reshape(-1, 1), cambios)

    def _cambio_predicho(tt: float) -> float:
        return float(model.predict(np.asarray([tt], dtype=float).reshape(-1, 1))[0])

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float)
        salida: list[float] = []
        ultimo_t = float(t[-1])
        for objetivo in arr:
            if objetivo <= ultimo_t:
                idx = int(np.argmin(np.abs(t - objetivo)))
                if idx == 0:
                    salida.append(float(y[0]))
                    continue
                cambio = _cambio_predicho(float(t[idx]))
                salida.append(_aplicar_cambio(float(y[idx - 1]), cambio, logaritmica))
            else:
                valor = float(y[-1])
                paso = ultimo_t + 1
                while paso <= objetivo + 1e-9:
                    valor = _aplicar_cambio(valor, _cambio_predicho(float(paso)), logaritmica)
                    paso += 1
                salida.append(valor)
        return np.asarray(salida, dtype=float)

    return {
        "nombre": nombre,
        "name": visible,
        "nombre_visible": visible,
        "k": 2,
        "predict": predict,
        "parametros": {"beta_0": float(model.intercept_), "beta_1": float(model.coef_[0])},
        "tendencia_ok": True,
    }


def _ajustar_naive(t: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    ultimo = float(y[-1])

    def predict(tt: Any) -> np.ndarray:
        return np.full(len(np.asarray(tt, dtype=float)), ultimo, dtype=float)

    return {
        "nombre": "naive",
        "name": "Naive último valor",
        "nombre_visible": "Naive último valor",
        "k": 1,
        "predict": predict,
        "parametros": {"ultimo_valor": ultimo},
        "es_benchmark": True,
        "tendencia_ok": True,
    }


def _ajustar_drift(t: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    t0, t1 = float(t[0]), float(t[-1])
    y0, y1 = float(y[0]), float(y[-1])
    pendiente = (y1 - y0) / (t1 - t0) if abs(t1 - t0) > EPS_NUMERICO else 0.0

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float)
        return y1 + pendiente * (arr - t1)

    return {
        "nombre": "drift",
        "name": "Drift",
        "nombre_visible": "Drift",
        "k": 2,
        "predict": predict,
        "parametros": {
            "primer_valor": y0,
            "ultimo_valor": y1,
            "t_inicial": t0,
            "t_final": t1,
            "observaciones": int(len(y)),
            "pendiente": float(pendiente),
            "pendiente_mensual": float(pendiente),
        },
        "es_benchmark": True,
        "tendencia_ok": pendiente >= 0,
    }


def _ajustar_promedio_movil(t: np.ndarray, y: np.ndarray, ventana: int = 6) -> dict[str, Any]:
    ventana = max(2, min(int(ventana), len(y)))
    promedio = float(np.mean(y[-ventana:]))
    ultimo_t = float(t[-1])

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float)
        predicciones: list[float] = []
        for objetivo in arr:
            if objetivo <= ultimo_t:
                disponibles = y[t < objetivo]
                base = disponibles if len(disponibles) >= ventana else y[: max(ventana, 1)]
                predicciones.append(float(np.mean(base[-ventana:])))
                continue
            historia = list(float(v) for v in y)
            paso_actual = ultimo_t
            pred = promedio
            while paso_actual < objetivo:
                pred = float(np.mean(historia[-ventana:]))
                historia.append(pred)
                paso_actual += 1.0
            predicciones.append(pred)
        return np.asarray(predicciones, dtype=float)

    return {
        "nombre": "promedio_movil",
        "name": f"Promedio movil {ventana}m",
        "nombre_visible": f"Promedio movil {ventana}m",
        "k": 1,
        "predict": predict,
        "parametros": {"ventana": ventana, "promedio": promedio},
        "es_benchmark": True,
        "tendencia_ok": True,
    }


def _ajustar_variacion_reciente(t: np.ndarray, y: np.ndarray, ventana: int = 6) -> dict[str, Any]:
    ventana = max(2, min(int(ventana), len(y) - 1))
    cambios = np.diff(y[-(ventana + 1):]) / np.where(
        np.abs(y[-(ventana + 1):-1]) > EPS_NUMERICO,
        y[-(ventana + 1):-1],
        np.nan,
    )
    cambios = cambios[np.isfinite(cambios)]
    cambio_medio = float(np.mean(cambios)) if len(cambios) else 0.0
    ultimo_t = float(t[-1])
    ultimo_y = float(y[-1])

    def predict(tt: Any) -> np.ndarray:
        arr = np.asarray(tt, dtype=float)
        pasos = np.maximum(0.0, arr - ultimo_t)
        return ultimo_y * np.power(1.0 + cambio_medio, pasos)

    return {
        "nombre": "variacion_reciente",
        "name": f"Promedio variación reciente {ventana}m",
        "nombre_visible": f"Promedio variación reciente {ventana}m",
        "k": 1,
        "predict": predict,
        "parametros": {"ventana": ventana, "cambio_medio": cambio_medio},
        "es_benchmark": True,
        "tendencia_ok": cambio_medio >= 0,
    }


# ---------------------------------------------------------------------------
# Fourier K=1 (estrategia calendario) y Seasonal Naive (benchmark estacional)
# post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04).
# ---------------------------------------------------------------------------

#: Mapa nombre_base -> (funcion_bare, kwargs) para los 10 modelos que
#: compiten en produccion. Reutilizado por Fourier K=1 para ajustar el
#: modelo base sobre la serie ya desestacionalizada, sin pasar por
#: `ajustar_modelo_interpretable` (evita diagnosticos/metricas intermedios
#: sobre una serie que no es la final).
_DISPATCH_MODELO_BASE: dict[str, tuple[Any, dict[str, Any]]] = {
    "lineal": (_ajustar_lineal, {}),
    "logaritmico": (_ajustar_logaritmico, {}),
    "exponencial_log_lineal": (_ajustar_exponencial_log_lineal, {}),
    "huber": (_ajustar_huber, {}),
    "holt_lineal": (_ajustar_holt_lineal, {"amortiguado": False}),
    "holt_amortiguado": (_ajustar_holt_lineal, {"amortiguado": True}),
    "variacion_lineal": (_ajustar_variacion_lineal, {"logaritmica": False}),
    "log_variacion": (_ajustar_variacion_lineal, {"logaritmica": True}),
    "naive": (_ajustar_naive, {}),
    "drift": (_ajustar_drift, {}),
}

#: Cache de coeficientes Fourier K=1 por ventana exacta (mismo patron que
#: `_MEMORIA_HOLT`, mas abajo). Evita recalcular la regresion auxiliar sen/cos
#: una vez por cada uno de los 10 modelos base cuando comparten el mismo
#: origen y horizonte de backtesting (item 22, Prompt Calendario 04).
_MEMORIA_FOURIER: dict[tuple, tuple[float, float]] = {}
_MEMORIA_FOURIER_LIMITE = 4096


def _fourier_k1_coeficientes(t: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """OLS auxiliar y_t = alpha + beta*t + a*sin(2*pi*t/12) + b*cos(2*pi*t/12).

    Devuelve (a, b): el componente calendario es S_F(t) = a*sin(2*pi*t/12) +
    b*cos(2*pi*t/12). La tendencia auxiliar alpha+beta*t solo evita que los
    terminos armonicos absorban tendencia general; no se publica como
    parametro del componente calendario (item 10, Prompt Calendario 04).
    Fuente: Hyndman & Athanasopoulos, Forecasting: Principles and Practice,
    3a ed., "Dynamic harmonic regression" (terminos de Fourier, K=1,
    periodo=12). https://otexts.com/fpp3/dhr.html
    """
    if len(t) < 5:
        raise ValueError(
            "Fourier K=1 requiere al menos 5 observaciones (4 parametros auxiliares mas 1)."
        )
    # post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 2
    # de auditoria). La clave anterior usaba solo y.tobytes(), ignorando el
    # eje t: dos llamadas con el mismo vector y pero ejes temporales
    # distintos (p.ej. offsets/alineaciones de calendario distintas)
    # reutilizarian coeficientes incorrectos. La clave ahora identifica
    # forma y dtype de ambos arrays ademas de sus bytes, sin incluir objetos
    # mutables (los propios arrays no se guardan como clave).
    clave = (y.shape, y.dtype.str, y.tobytes(), t.shape, t.dtype.str, t.tobytes())
    cacheado = _MEMORIA_FOURIER.get(clave)
    if cacheado is not None:
        return cacheado
    s = np.sin(2.0 * np.pi * t / 12.0)
    c = np.cos(2.0 * np.pi * t / 12.0)
    disenio = np.column_stack([np.ones_like(t), t, s, c])
    coeficientes, *_ = np.linalg.lstsq(disenio, y, rcond=None)
    a, b = float(coeficientes[2]), float(coeficientes[3])
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("Los coeficientes de Fourier K=1 no son finitos.")
    if len(_MEMORIA_FOURIER) >= _MEMORIA_FOURIER_LIMITE:
        _MEMORIA_FOURIER.clear()
    _MEMORIA_FOURIER[clave] = (a, b)
    return a, b


def _componente_fourier_k1(t: np.ndarray, a: float, b: float) -> np.ndarray:
    return a * np.sin(2.0 * np.pi * t / 12.0) + b * np.cos(2.0 * np.pi * t / 12.0)


def _ajustar_fourier_k1(t: np.ndarray, y: np.ndarray, modelo_base: str) -> dict[str, Any]:
    """Fourier anual K=1 sobre `modelo_base`: retira S_F(t), ajusta el modelo
    base sobre la serie desestacionalizada y repone S_F al predecir (item 5,
    Prompt Calendario 04). El error fuera de muestra se calcula siempre
    contra la serie original, porque `predict` ya repone el componente
    calendario antes de devolver el valor."""
    if modelo_base not in _DISPATCH_MODELO_BASE:
        raise ValueError(f"Modelo base no soportado para Fourier K=1: {modelo_base}")
    a, b = _fourier_k1_coeficientes(t, y)
    s_f_hist = _componente_fourier_k1(t, a, b)
    y_estrella = y - s_f_hist
    funcion_base, kwargs_base = _DISPATCH_MODELO_BASE[modelo_base]
    base = funcion_base(t, y_estrella, **kwargs_base)
    predict_base = base["predict"]

    def predict(tt: Any) -> np.ndarray:
        t_futuro = np.asarray(tt, dtype=float)
        return np.asarray(predict_base(t_futuro), dtype=float) + _componente_fourier_k1(t_futuro, a, b)

    nombre_visible_base = base.get("nombre_visible", modelo_base)
    amplitud = math.sqrt(a * a + b * b)
    resultado = dict(base)
    resultado.update(
        {
            "nombre": f"{FOURIER_K1_PREFIJO}{modelo_base}",
            "name": f"Fourier K=1 + {nombre_visible_base}",
            "nombre_visible": f"Fourier K=1 + {nombre_visible_base}",
            "predict": predict,
            "estrategia_calendario": "fourier_k1",
            "modelo_base": modelo_base,
            # post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06,
            # hallazgo 3 de auditoria). k NO interviene en la seleccion RMSE
            # (verificado: _seleccionar_modelo_rectangular no lo usa; el unico
            # consumidor productivo es calcular_metricas -> AIC/AICc/R2
            # ajustado, descriptivos). La regresion auxiliar Fourier estima
            # CUATRO parametros (alpha, beta, a, b) con la misma historia que
            # el modelo base, aunque alpha y beta no se sumen al pronostico
            # final: los cuatro consumen grados de libertad igual. Antes se
            # sumaba +2 (solo a,b); se corrige a +4.
            "k": int(base.get("k", 0)) + 4,
            "parametros": {
                **(base.get("parametros") or {}),
                "fourier_k": 1,
                "fourier_periodo": 12,
                "fourier_coef_sin_1": a,
                "fourier_coef_cos_1": b,
                "fourier_amplitud": amplitud,
                "modelo_base": modelo_base,
            },
        }
    )
    return resultado


def _ajustar_seasonal_naive(t: np.ndarray, y: np.ndarray, m: int = 12) -> dict[str, Any]:
    """Seasonal Naive: cada periodo futuro toma el ultimo valor observado de
    la misma posicion estacional (m=12). Benchmark estandar (item 7, Prompt
    Calendario 04); no tiene prioridad ni veto, compite bajo el mismo
    criterio RMSE que los demas 20 candidatos. Fuente: Hyndman &
    Athanasopoulos, Forecasting: Principles and Practice, 3a ed., "Simple
    methods" (Seasonal naive method). https://otexts.com/fpp3/simple-methods.html
    """
    n = len(y)
    if n < m:
        raise ValueError(f"Seasonal Naive (m={m}) requiere al menos {m} observaciones.")
    ultimo_t = float(t[-1])

    def predict(tt: Any) -> np.ndarray:
        t_futuro = np.asarray(tt, dtype=float)
        salida = np.empty(len(t_futuro), dtype=float)
        for i, objetivo in enumerate(t_futuro):
            if objetivo <= ultimo_t:
                # Valor ajustado in-sample estandar (FPP3): y_t_gorro = y_(t-m).
                # Indefinido para los primeros m periodos, igual que en
                # cualquier libro de texto sobre Seasonal Naive.
                pos_objetivo = int(round(objetivo - t[0]))
                pos_estacional = pos_objetivo - m
                salida[i] = y[pos_estacional] if 0 <= pos_estacional < n else float("nan")
                continue
            h = int(round(objetivo - ultimo_t))
            k = -(-h // m)  # techo de h/m
            idx_t = objetivo - m * k
            pos = int(round(idx_t - t[0]))
            if pos < 0 or pos >= n:
                raise ValueError("Seasonal Naive: posicion estacional fuera de rango.")
            salida[i] = y[pos]
        return salida

    return {
        "nombre": CANDIDATO_SEASONAL_NAIVE,
        "name": "Seasonal Naive (m=12)",
        "nombre_visible": "Seasonal Naive (m=12)",
        "k": 1,
        "predict": predict,
        "parametros": {"periodo": m},
        "es_benchmark": True,
        "estrategia_calendario": CANDIDATO_SEASONAL_NAIVE,
        "modelo_base": None,
        "tendencia_ok": True,
    }


def _limpiar_xy(t: Any, y: Any) -> tuple[np.ndarray, np.ndarray]:
    t_arr = np.asarray(t, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    n = min(len(t_arr), len(y_arr))
    t_arr = t_arr[:n]
    y_arr = y_arr[:n]
    mask = np.isfinite(t_arr) & np.isfinite(y_arr)
    return t_arr[mask], y_arr[mask]


def _holt_suavizado(
    y: np.ndarray,
    alpha: float,
    beta: float,
    phi: float,
    l0: float | None = None,
    b0: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Recursión de Holt con tendencia amortiguada (FPP3 §8.2).

        l_t = alpha*y_t + (1-alpha)*(l_{t-1} + phi*b_{t-1})
        b_t = beta*(l_t - l_{t-1}) + (1-beta)*phi*b_{t-1}

    ``l0`` y ``b0`` son los estados iniciales. Cuando no se pasan se usa la
    inicialización heurística clásica (nivel = primera observación, tendencia =
    primera diferencia), que es la que el proyecto empleaba antes de estimar.
    """
    n = len(y)
    if l0 is None:
        l0 = float(y[0])
    if b0 is None:
        b0 = float(y[1] - y[0]) if n > 1 else 0.0

    niveles = np.empty(n, dtype=float)
    tendencias = np.empty(n, dtype=float)
    nivel_anterior, tendencia_anterior = float(l0), float(b0)
    for i in range(n):
        nivel = alpha * y[i] + (1.0 - alpha) * (nivel_anterior + phi * tendencia_anterior)
        tendencia = beta * (nivel - nivel_anterior) + (1.0 - beta) * phi * tendencia_anterior
        niveles[i] = nivel
        tendencias[i] = tendencia
        nivel_anterior, tendencia_anterior = nivel, tendencia
    return niveles, tendencias


def _holt_ajustados(
    y: np.ndarray, alpha: float, beta: float, phi: float, l0: float, b0: float
) -> np.ndarray:
    """Valores ajustados de un paso: ``yhat_t = l_{t-1} + phi*b_{t-1}``.

    El primero usa los estados iniciales, de modo que **todas** las
    observaciones contribuyen al SSE que se minimiza, como en FPP3 §8.1.
    """
    niveles, tendencias = _holt_suavizado(y, alpha, beta, phi, l0, b0)
    previos_nivel = np.r_[float(l0), niveles[:-1]]
    previos_tendencia = np.r_[float(b0), tendencias[:-1]]
    return previos_nivel + phi * previos_tendencia


def _aplicar_cambio(valor: float, cambio: float, logaritmica: bool) -> float:
    if logaritmica:
        return float(valor * math.exp(cambio))
    return float(valor * (1.0 + cambio))


def _ratio(numerador: float, denominador: float) -> float:
    if not (math.isfinite(numerador) and math.isfinite(denominador)) or abs(denominador) <= EPS_NUMERICO:
        return float("nan")
    return float(numerador / denominador)


def _mejor_por(filas: list[dict[str, Any]], campo: str) -> dict[str, Any]:
    validas = [fila for fila in filas if math.isfinite(_numero(fila.get(campo), default=float("nan")))]
    if not validas:
        return {}
    mejor = min(validas, key=lambda fila: float(fila[campo]))
    return {"modelo": mejor["nombre"], "valor": float(mejor[campo])}


def _numero(valor: Any, default: float) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return default
    return numero if math.isfinite(numero) else default


def _fmt(valor: Any) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "No aplica"
    if not math.isfinite(numero):
        return "No aplica"
    return f"{numero:.4f}"
