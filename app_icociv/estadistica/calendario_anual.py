"""Detección del salto de cambio de año en series ICOCIV. El ajuste NO se aplica.

Muchas series ICOCIV presentan un salto recurrente en la transición
diciembre--enero (actualización anual del índice). Los modelos de tendencia
reparten ese salto de forma uniforme entre los doce meses, de modo que
subestiman enero y sobrestiman el resto del año. El fenómeno está medido y es
contundente.

P0-F, 12-08-2026. **El tratamiento se retiró del producto.**
``_ajustar_salto_anual`` fija ``aplicado = False`` de forma incondicional: la
trayectoria que la aplicación entrega es la del modelo base, sin factor de
calendario. Este encabezado describía el ajuste como vigente y condicionado a una
validación retrospectiva; se corrige el 17-08-2026 (V-CODEX-R3, residual 5).

Por qué se retiró: ningún componente tenía sustento completo. ``gamma`` no está
sustentado como estimador del salto FUTURO; la forma ``f_j = exp(gamma·(n_j −
j/12))`` carece de fuente y su término ``−j/12`` es falso para ``naive``, que no
reparte crecimiento a lo largo del año; las puertas ``K>=2``, ``razon>1,5`` y
``consistencia>=0,6`` se calibraron sobre el mismo anexo con el que después se
evaluaba el resultado; y el conjunto de validación ``(1, 3, 6)`` es una elección
interna. No se introduce reemplazo: añadir uno sería incorporar un candidato más
al catálogo sin sustento.

Qué SIGUE haciendo este módulo: **medir y publicar** el perfil. ``gamma``, la
razón, la consistencia de signo y el número de transiciones son propiedades de la
serie observada y se reportan como diagnóstico. Lo que no hacen es modificar el
pronóstico.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from app_icociv.estadistica.criterios import (
    CONSISTENCIA_SIGNO_SALTO_ANUAL,
    MIN_TRANSICIONES_SALTO_ANUAL,
    RATIO_SALTO_ANUAL,
    TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO,
)

MESES_ANIO = 12


def _mes_de_periodo(periodo: Any) -> int:
    """Extrae el mes de una etiqueta 'AAAA_M' o 'AAAA-MM'; 0 si no aplica."""
    partes = str(periodo).replace("-", "_").split("_")
    if len(partes) >= 2 and partes[1].strip().isdigit():
        return int(partes[1])
    return 0


def perfil_salto_anual(serie: pd.DataFrame) -> dict[str, Any]:
    r"""Caracteriza el salto diciembre--enero de una serie mensual.

    Usa variaciones logarítmicas r_t = ln(y_t / y_{t-1}) porque el salto es
    proporcional al nivel del índice. La magnitud se resume con la mediana
    (robusta frente a un único año extremo) y se contrasta contra el movimiento
    mensual típico m = mediana(|r_t|) de los meses restantes.
    """
    vacio = {
        "evaluable": False,
        "hay_evidencia": False,
        "transiciones": 0,
        "gamma": float("nan"),
        "movimiento_tipico": float("nan"),
        "ratio": float("nan"),
        "consistencia_signo": float("nan"),
        "saltos": [],
        "motivo": "Serie insuficiente para evaluar el salto de cambio de año.",
    }
    if not isinstance(serie, pd.DataFrame) or serie.empty:
        return vacio
    if not {"Periodo", "Indice"}.issubset(serie.columns):
        return vacio

    y = pd.to_numeric(serie["Indice"], errors="coerce").to_numpy(dtype=float)
    meses = [_mes_de_periodo(p) for p in serie["Periodo"]]
    if len(y) < 14 or np.isnan(y).any() or (y <= 0).any() or 0 in meses:
        return vacio

    r = np.log(y[1:] / y[:-1])
    es_salto = [meses[i] == 12 and meses[i + 1] == 1 for i in range(len(r))]
    saltos = np.array([r[i] for i in range(len(r)) if es_salto[i]], dtype=float)
    otros = np.array([r[i] for i in range(len(r)) if not es_salto[i]], dtype=float)
    if saltos.size == 0 or otros.size == 0:
        return vacio

    gamma = float(np.median(saltos))
    movimiento = float(np.median(np.abs(otros)))
    if movimiento <= 1e-12:
        return {**vacio, "evaluable": True, "motivo": "Movimiento mensual típico nulo."}

    ratio = abs(gamma) / movimiento
    consistencia = (
        float(np.mean(np.sign(saltos) == np.sign(gamma))) if gamma != 0 else 0.0
    )
    perfil = {
        "evaluable": True,
        "transiciones": int(saltos.size),
        "gamma": gamma,
        "movimiento_tipico": movimiento,
        "ratio": ratio,
        "consistencia_signo": consistencia,
        "saltos": [float(s) for s in saltos],
        "hay_evidencia": False,
        "motivo": "",
    }

    if saltos.size < MIN_TRANSICIONES_SALTO_ANUAL:
        perfil["motivo"] = (
            f"Solo {saltos.size} transición(es) diciembre--enero observadas; "
            f"se requieren {MIN_TRANSICIONES_SALTO_ANUAL}."
        )
        return perfil
    if ratio <= RATIO_SALTO_ANUAL:
        perfil["motivo"] = (
            f"El salto de cambio de año ({gamma:.2%}) no supera "
            f"{RATIO_SALTO_ANUAL} veces el movimiento mensual típico ({movimiento:.2%})."
        )
        return perfil
    if consistencia < CONSISTENCIA_SIGNO_SALTO_ANUAL:
        perfil["motivo"] = (
            f"Los saltos de cambio de año no mantienen un signo consistente "
            f"({consistencia:.0%} coincide con la mediana)."
        )
        return perfil

    perfil["hay_evidencia"] = True
    perfil["motivo"] = (
        f"Patrón recurrente: {saltos.size} transiciones diciembre--enero con salto "
        f"mediano de {gamma:.2%}, {ratio:.1f} veces el movimiento mensual típico."
    )
    return perfil


def eneros_en_horizonte(mes_origen: int, horizonte: int) -> int:
    """Cuántos pasos del horizonte caen en enero desde un mes de origen."""
    mes = int(mes_origen)
    if not 1 <= mes <= MESES_ANIO or int(horizonte) <= 0:
        return 0
    return sum(1 for k in range(1, int(horizonte) + 1) if ((mes - 1 + k) % MESES_ANIO) + 1 == 1)


def factor_ajuste_calendario(gamma: float, mes_origen: int, horizonte: int) -> float:
    r"""Factor multiplicativo que reconcentra el salto anual en enero.

        f_h = exp( gamma * (n_h - h/12) )

    donde n_h es el número de eneros dentro del horizonte. El término h/12
    descuenta la porción del salto que el modelo base ya repartió de forma
    uniforme; por eso en h=12 el factor vale exactamente 1 y el crecimiento
    anual del modelo no se altera.
    """
    if not math.isfinite(gamma) or int(horizonte) <= 0:
        return 1.0
    n_eneros = eneros_en_horizonte(mes_origen, horizonte)
    exponente = gamma * (n_eneros - int(horizonte) / MESES_ANIO)
    return float(math.exp(exponente))


def evaluar_ajuste_en_backtesting(
    serie: pd.DataFrame,
    predicciones: pd.DataFrame,
    horizonte: int,
) -> dict[str, Any]:
    """Compara el desempeño con y sin ajuste sobre las ventanas reales.

    Reutiliza las predicciones walk-forward ya calculadas por la aplicación.
    Para cada origen, ``gamma`` se reestima **solo con la historia disponible
    hasta ese origen**, de modo que la comparación no incorpora información
    futura.
    """
    salida = {
        "evaluado": False,
        "mejora_mae": float("nan"),
        "mejora_rmse": float("nan"),
        "mae_base": float("nan"),
        "mae_ajustado": float("nan"),
        "rmse_base": float("nan"),
        "rmse_ajustado": float("nan"),
        "ventanas": 0,
        "recomendado": False,
    }
    if not isinstance(predicciones, pd.DataFrame) or predicciones.empty:
        return salida
    requeridas = {"Origen", "Observado", "Predicho", "Observaciones_entrenamiento"}
    if not requeridas.issubset(predicciones.columns):
        return salida

    errores_base: list[float] = []
    errores_ajustados: list[float] = []
    for _, fila in predicciones.iterrows():
        try:
            observado = float(fila["Observado"])
            base = float(fila["Predicho"])
            n_train = int(fila["Observaciones_entrenamiento"])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(observado) and math.isfinite(base)):
            continue
        historia = serie.iloc[:n_train]
        perfil = perfil_salto_anual(historia)
        if perfil.get("hay_evidencia"):
            factor = factor_ajuste_calendario(
                perfil["gamma"], _mes_de_periodo(fila["Origen"]), horizonte
            )
            ajustado = base * factor
        else:
            ajustado = base
        errores_base.append(observado - base)
        errores_ajustados.append(observado - ajustado)

    if not errores_base:
        return salida

    eb = np.asarray(errores_base, dtype=float)
    ea = np.asarray(errores_ajustados, dtype=float)
    mae_b, mae_a = float(np.mean(np.abs(eb))), float(np.mean(np.abs(ea)))
    rmse_b = float(np.sqrt(np.mean(eb ** 2)))
    rmse_a = float(np.sqrt(np.mean(ea ** 2)))
    salida.update(
        {
            "evaluado": True,
            "ventanas": int(eb.size),
            "mae_base": mae_b,
            "mae_ajustado": mae_a,
            "rmse_base": rmse_b,
            "rmse_ajustado": rmse_a,
            "mejora_mae": (mae_b - mae_a) / mae_b * 100.0 if mae_b > 0 else 0.0,
            "mejora_rmse": (rmse_b - rmse_a) / rmse_b * 100.0 if rmse_b > 0 else 0.0,
        }
    )
    # Se acepta si no deteriora de forma relevante ninguna de las dos métricas.
    tolerancia = TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO
    salida["recomendado"] = bool(
        mae_b > 0
        and rmse_b > 0
        and mae_a <= mae_b * tolerancia
        and rmse_a <= rmse_b * tolerancia
    )
    return salida


def aplicar_ajuste_calendario(
    valores_base: Sequence[float],
    periodos_proyectados: Sequence[Any],
    mes_origen: int,
    gamma: float,
) -> list[float]:
    """Aplica el factor calendario a cada paso de la trayectoria proyectada."""
    ajustados: list[float] = []
    for paso, valor in enumerate(valores_base, start=1):
        try:
            base = float(valor)
        except (TypeError, ValueError):
            ajustados.append(valor)
            continue
        factor = factor_ajuste_calendario(gamma, mes_origen, paso)
        ajustados.append(base * factor)
    _ = periodos_proyectados  # los periodos se derivan del mes de origen
    return ajustados


def _estado_visible(patron_detectado: bool, aplicado: bool, eneros: int) -> str:
    """Etiqueta única para interfaz, informes y CSV.

    Separa el hecho de que la serie tenga patrón del hecho de que ese patrón
    tenga efecto en el horizonte pedido.
    """
    # P0-F, 12-08-2026: el tratamiento esta RETIRADO del camino productivo. El
    # texto no debe afirmar que el fenomeno no existe -esta medido y es
    # contundente- sino que el METODO no tiene sustento.
    _ = aplicado, eneros
    if not patron_detectado:
        return "Patrón de cambio de año no identificado en la serie (diagnóstico)"
    return (
        "Patrón de cambio de año identificado en la serie; "
        "tratamiento no aplicado: método sin sustento metodológico"
    )


def resumen_trazabilidad(
    perfil: dict[str, Any],
    validacion: dict[str, Any],
    aplicado: bool,
    horizonte: int,
    mes_origen: int,
) -> dict[str, Any]:
    """Estructura la trazabilidad del ajuste para interfaz y reportes.

    Distingue dos cosas que antes se comunicaban como una sola y que la
    auditoría independiente señaló como contradictorias (H-10):

    * **patrón detectado en la serie**: el perfil de cambio de año existe y
      cumple las tres condiciones. Es una propiedad de la serie, no del
      horizonte, y por eso se evalúa con independencia de cuántos meses se
      pidan;
    * **efecto dentro del horizonte solicitado**: solo hay corrección efectiva
      si el horizonte contiene al menos un enero. Con cero eneros el factor es
      neutro y la trayectoria no se desplaza.

    El ajuste se aplica **por paso**, de modo que los meses comunes valen lo
    mismo al pedir 3, 6, 12 o 18 meses. No se reintroduce ninguna condición
    sobre el horizonte total.
    """
    eneros = eneros_en_horizonte(mes_origen, horizonte)
    patron_detectado = bool(perfil.get("hay_evidencia"))
    efecto_en_horizonte = bool(aplicado and eneros > 0)
    return {
        "ajuste_calendario_aplicado": bool(aplicado),
        "patron_detectado_en_serie": patron_detectado,
        "efecto_en_horizonte_solicitado": efecto_en_horizonte,
        "estado_calendario_visible": _estado_visible(patron_detectado, aplicado, eneros),
        "hay_evidencia_calendario": patron_detectado,
        "transiciones_diciembre_enero": int(perfil.get("transiciones", 0) or 0),
        "salto_mediano_log": perfil.get("gamma"),
        "salto_mediano_pct": (
            (math.exp(perfil["gamma"]) - 1.0) * 100.0
            if isinstance(perfil.get("gamma"), float) and math.isfinite(perfil.get("gamma"))
            else None
        ),
        "movimiento_mensual_tipico_pct": (
            perfil.get("movimiento_tipico") * 100.0
            if isinstance(perfil.get("movimiento_tipico"), float)
            and math.isfinite(perfil.get("movimiento_tipico"))
            else None
        ),
        "ratio_salto_movimiento": perfil.get("ratio"),
        "consistencia_signo": perfil.get("consistencia_signo"),
        "criterio": perfil.get("motivo", ""),
        "eneros_en_horizonte": eneros,
        "horizonte_cruza_cambio_anio": eneros > 0,
        "validacion_backtesting": validacion,
        "mensaje": _mensaje_usuario(perfil, validacion, aplicado, mes_origen, horizonte),
    }


def _mensaje_usuario(
    perfil: dict[str, Any],
    validacion: dict[str, Any],
    aplicado: bool,
    mes_origen: int,
    horizonte: int,
) -> str:
    """Explicación breve y honesta para la interfaz y los informes.

    P0-F, 12-08-2026: el tratamiento está retirado. El mensaje describe el
    diagnóstico y dice **por qué** no se aplica, sin negar el fenómeno.
    """
    if not aplicado:
        if perfil.get("hay_evidencia"):
            return (
                "Se identificó un patrón de cambio de año en la serie "
                f"({perfil.get('transiciones', 0)} transiciones diciembre-enero, salto mediano "
                f"{(math.exp(perfil['gamma']) - 1) * 100:.2f}%). **No se aplica ninguna corrección**: "
                "el método de ajuste que la aplicación usaba —estimación del efecto por la mediana "
                "de los saltos y aplicación multiplicativa por paso— no tiene sustento metodológico "
                "completo, y se retiró el 12 de agosto de 2026. El patrón se publica como "
                "diagnóstico descriptivo de la serie; el pronóstico es el del modelo seleccionado, "
                "sin tratamientos adicionales."
            )
        return (
            "No se identificó un patrón recurrente de cambio de año en la serie. "
            "El pronóstico es el del modelo seleccionado, sin tratamientos adicionales. "
            + str(perfil.get("motivo", ""))
        ).strip()
    if aplicado:
        eneros = eneros_en_horizonte(mes_origen, horizonte)
        detalle_eneros = (
            f"El horizonte solicitado cruza {eneros} mes(es) de enero."
            if eneros
            else "El horizonte solicitado no cruza enero: en esos meses el ajuste descuenta la "
            "porción del salto anual que el modelo base había repartido de forma uniforme."
        )
        return (
            "Se detectó un patrón recurrente de cambio de año en la serie "
            f"({perfil.get('transiciones', 0)} transiciones diciembre-enero, salto mediano "
            f"{(math.exp(perfil['gamma']) - 1) * 100:.2f}%). La proyección reconcentra ese salto "
            "en enero paso a paso, y la validación retrospectiva confirmó que no deteriora el "
            f"desempeño. {detalle_eneros} El crecimiento anual del modelo no se altera y el valor "
            "de un mes dado no depende del horizonte que se solicite."
        )
    if not perfil.get("hay_evidencia"):
        return (
            "No se detectó evidencia suficiente de salto anual recurrente. "
            "La proyección se calcula con el modelo base. "
            + str(perfil.get("motivo", ""))
        ).strip()
    if validacion.get("evaluado") and not validacion.get("recomendado"):
        return (
            "Se observaron saltos en el cambio de año, pero no se aplicó ajuste automático "
            "porque la validación retrospectiva no mejoró el desempeño del modelo "
            f"(MAE {validacion.get('mejora_mae', 0):+.1f}%, RMSE {validacion.get('mejora_rmse', 0):+.1f}%)."
        )
    return (
        "Se observaron saltos en el cambio de año, pero no se aplicó ajuste automático "
        "por falta de validación retrospectiva suficiente."
    )


if __name__ == "__main__":  # pragma: no cover - comprobación manual
    import sys as _sys
    from pathlib import Path as _Path

    _RAIZ = _Path(__file__).resolve().parents[2]
    if str(_RAIZ) not in _sys.path:
        _sys.path.insert(0, str(_RAIZ))

    # Comprobación mínima con series sintéticas.
    def _serie(valores):
        periodos = [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(len(valores))]
        return pd.DataFrame({"Periodo": periodos, "Indice": valores})

    # Serie con salto de 5% cada enero y 0.2% el resto de meses.
    vals, nivel = [], 100.0
    for i in range(60):
        mes = i % 12 + 1
        nivel *= 1.05 if mes == 1 and i > 0 else 1.002
        vals.append(nivel)
    perfil = perfil_salto_anual(_serie(vals))
    assert perfil["hay_evidencia"], perfil
    assert perfil["transiciones"] == 4, perfil["transiciones"]
    assert abs(math.exp(perfil["gamma"]) - 1.05) < 1e-6, perfil["gamma"]

    # Serie suave: sin patrón.
    suave = _serie([100 * (1.004 ** i) for i in range(60)])
    assert not perfil_salto_anual(suave)["hay_evidencia"]

    # Menos de dos transiciones: no evaluable como patrón.
    corta = _serie(vals[:14])
    assert not perfil_salto_anual(corta)["hay_evidencia"]

    # El factor es neutro en un ciclo completo y solo actúa si cruza enero.
    assert abs(factor_ajuste_calendario(0.05, 5, 12) - 1.0) < 1e-12
    assert abs(factor_ajuste_calendario(0.05, 1, 6) - 1.0) > 0  # 6 meses desde enero
    assert eneros_en_horizonte(12, 1) == 1
    assert eneros_en_horizonte(1, 6) == 0
    assert factor_ajuste_calendario(0.05, 2, 0) == 1.0
    print("OK calendario_anual")
