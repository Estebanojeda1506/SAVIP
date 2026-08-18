"""Preparacion, validación y factibilidad estadística de series ICOCIV."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from app_icociv.estadistica.criterios import (
    ADVERTENCIA_MIN_OBS,
    ALPHA_PRUEBAS_RESIDUALES,
    CONSECUENCIA_INFORMATIVA,
    EPS_NUMERICO,
    MIN_ITERACIONES_WF,
    MIN_OBS_MODELACION,
    MIN_OBS_RECOMENDADAS,
    UMBRAL_ESTABILIDAD_INESTABLE,
    UMBRAL_INTERVALO_ADVERTENCIA,
    UMBRAL_MASE_ADVERTENCIA,
    UMBRAL_Z_MODIFICADO_ATIPICO,
)


ESTADO_CORRECTO = "correcto"
ESTADO_ADVERTENCIA = "advertencia"
ESTADO_CRITICO = "critico"

MIN_OBS = MIN_OBS_RECOMENDADAS
MIN_ITERACIONES_BACKTESTING = MIN_ITERACIONES_WF

MENSAJE_AUTOCORRELACION_SEVERA = (
    "La proyección no se genera porque el modelo presenta autocorrelación residual severa. "
    "Esto indica que los errores no son aleatorios y que el modelo no captura adecuadamente "
    "la dinámica temporal de la serie."
)
MENSAJE_MASE_MAYOR_UNO = (
    "MASE > 1 indica que, respecto a la escala naive in-sample, el error no es bajo. "
    "Si el modelo supera a naive o drift en backtesting por horizonte, esta advertencia "
    "se interpreta como auxiliar y no como criterio de descarte."
)
UMBRAL_Z_ATIPICO = UMBRAL_Z_MODIFICADO_ATIPICO


@dataclass(frozen=True)
class ResultadoValidacion:
    """Resultado estructurado de una validación de calidad."""

    criterio: str
    estado: str
    descripcion: str
    impacto_analisis: str
    impacto_proyeccion: str
    recomendacion: str

    def como_dict(self) -> dict[str, str]:
        return {
            "criterio": self.criterio,
            "estado": self.estado,
            "descripcion": self.descripcion,
            "impacto_analisis": self.impacto_analisis,
            "impacto_proyeccion": self.impacto_proyeccion,
            "recomendacion": self.recomendacion,
        }


def normalizar_periodo(periodo: Any) -> str:
    """
    Normaliza etiquetas de periodo a 'YYYY_M'.

    Acepta variantes como '2025_01', '2025_11 ' o valores equivalentes.
    """
    texto = str(periodo).strip()
    match = re.match(r"^(\d{4})[_\-/](\d{1,2})$", texto)
    if not match:
        raise ValueError(f"Periodo inválido: {periodo!r}")
    anio = int(match.group(1))
    mes = int(match.group(2))
    if mes < 1 or mes > 12:
        raise ValueError(f"Mes fuera de rango en periodo {periodo!r}")
    return f"{anio}_{mes}"


def periodo_a_orden(periodo: Any) -> int:
    """Convierte periodo 'YYYY_M' a entero absoluto anio*12+mes."""
    normalizado = normalizar_periodo(periodo)
    anio_txt, mes_txt = normalizado.split("_")
    return int(anio_txt) * 12 + int(mes_txt)


def orden_a_periodo(orden: int) -> str:
    """Convierte entero absoluto anio*12+mes a periodo 'YYYY_M'."""
    anio = (int(orden) - 1) // 12
    mes = int(orden) - anio * 12
    return f"{anio}_{mes}"


def normalizar_serie_mensual(
    serie_df: pd.DataFrame,
    columna_periodo: str = "Periodo",
    columna_valor: str = "Indice",
    metadatos: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Normaliza una serie mensual ICOCIV sin descartar filas silenciosamente.

    Devuelve columnas estándar: Periodo, Índice, anio, mes, orden_temporal.
    """
    if columna_periodo not in serie_df.columns or columna_valor not in serie_df.columns:
        raise ValueError("La serie debe contener columnas de periodo e índice.")

    serie = serie_df[[columna_periodo, columna_valor]].copy()
    serie.columns = ["Periodo_original", "Indice_original"]
    periodos_normalizados: list[str | None] = []
    anios: list[int | None] = []
    meses: list[int | None] = []
    ordenes: list[int | None] = []

    for valor in serie["Periodo_original"]:
        try:
            periodo = normalizar_periodo(valor)
            anio_txt, mes_txt = periodo.split("_")
            orden = periodo_a_orden(periodo)
            periodos_normalizados.append(periodo)
            anios.append(int(anio_txt))
            meses.append(int(mes_txt))
            ordenes.append(orden)
        except Exception:
            periodos_normalizados.append(None)
            anios.append(None)
            meses.append(None)
            ordenes.append(None)

    serie["Periodo"] = periodos_normalizados
    serie["anio"] = anios
    serie["mes"] = meses
    serie["orden_temporal"] = ordenes
    serie["Indice"] = pd.to_numeric(serie["Indice_original"], errors="coerce")
    serie["valor_no_numerico"] = serie["Indice"].isna() & serie["Indice_original"].notna()
    serie = serie.sort_values(["orden_temporal", "Periodo"], na_position="last").reset_index(drop=True)

    metadatos = metadatos or {}
    serie.attrs["nombre_serie"] = metadatos.get("nombre_serie", "")
    serie.attrs["nivel_agregacion"] = metadatos.get("nivel_agregacion", "")
    serie.attrs["ruta_jerarquica"] = metadatos.get("ruta_jerarquica", [])
    serie.attrs["archivo_fuente"] = metadatos.get("archivo_fuente", "")
    serie.attrs["fecha_generacion"] = metadatos.get("fecha_generacion") or datetime.now().isoformat(timespec="seconds")
    return serie


def validar_serie_mensual(serie: pd.DataFrame) -> dict[str, Any]:
    """Ejecuta validaciones estructuradas sobre una serie normalizada."""
    resultados: list[ResultadoValidacion] = []
    periodos_invalidos = int(serie["Periodo"].isna().sum()) if "Periodo" in serie else 0
    resultados.append(
        _validacion(
            "periodos_validos",
            ESTADO_CORRECTO if periodos_invalidos == 0 else ESTADO_CRITICO,
            f"Periodos invalidos detectados: {periodos_invalidos}.",
            "Los periodos definen el eje temporal del análisis.",
            "Periodos invalidos impiden ubicar correctamente la proyección.",
            "Corregir etiquetas de periodo en formato YYYY_M.",
        )
    )

    meses_fuera = 0
    if "mes" in serie:
        meses = pd.to_numeric(serie["mes"], errors="coerce")
        meses_fuera = int(((meses < 1) | (meses > 12)).sum())
    resultados.append(
        _validacion(
            "meses_rango",
            ESTADO_CORRECTO if meses_fuera == 0 else ESTADO_CRITICO,
            f"Meses fuera del rango 1 a 12: {meses_fuera}.",
            "Meses fuera de rango rompen la frecuencia mensual.",
            "No se puede proyectar con calendario inválido.",
            "Revisar los encabezados de periodos del archivo fuente.",
        )
    )

    duplicados = int(serie["Periodo"].dropna().duplicated().sum())
    resultados.append(
        _validacion(
            "duplicados",
            ESTADO_CORRECTO if duplicados == 0 else ESTADO_CRITICO,
            f"Periodos duplicados detectados: {duplicados}.",
            "Los duplicados ponderan artificialmente algunos meses.",
            "La validación temporal queda contaminada por repeticion de periodos.",
            "Eliminar duplicados o verificar la extraccion de la tabla.",
        )
    )

    faltantes = int(serie["Indice"].isna().sum())
    resultados.append(
        _validacion(
            "valores_faltantes",
            ESTADO_CORRECTO if faltantes == 0 else ESTADO_ADVERTENCIA,
            f"Valores faltantes del índice: {faltantes}.",
            "Los faltantes reducen la información útil y pueden romper continuidad.",
            "Si los faltantes son intermedios, la proyección debe restringirse.",
            "Revisar si el dato falta en el anexo oficial o en la lectura.",
        )
    )

    no_numericos = int(serie.get("valor_no_numerico", pd.Series(dtype=bool)).sum())
    resultados.append(
        _validacion(
            "valores_no_numericos",
            ESTADO_CORRECTO if no_numericos == 0 else ESTADO_CRITICO,
            f"Valores no numéricos detectados: {no_numericos}.",
            "Valores no numéricos impiden cálculos estadísticos confiables.",
            "El modelo no debe ajustarse con datos no numéricos.",
            "Verificar celdas de índice en el archivo fuente.",
        )
    )

    valores_validos = serie.dropna(subset=["Periodo", "Indice"]).copy()
    no_positivos = int((valores_validos["Indice"] <= 0).sum())
    resultados.append(
        _validacion(
            "valores_no_positivos",
            ESTADO_CORRECTO if no_positivos == 0 else ESTADO_ADVERTENCIA,
            f"Valores negativos o cero: {no_positivos}.",
            "Afectan variaciones porcentuales e impiden transformaciones logaritmicas.",
            "Modelos o intervalos que usan logaritmos deben deshabilitarse o advertirse.",
            "Revisar si corresponden a error de lectura o a un nivel no válido del índice.",
        )
    )

    continuidad = _evaluar_continuidad(valores_validos)
    resultados.append(
        _validacion(
            "continuidad_mensual",
            continuidad["estado"],
            continuidad["descripcion"],
            "La continuidad garantiza que la distancia entre observaciones sea mensual.",
            "Saltos temporales reducen la confiabilidad del forecasting.",
            continuidad["recomendacion"],
        )
    )

    n = int(len(valores_validos))
    if n < MIN_OBS_MODELACION:
        # P0-G REABIERTO, 14-08-2026: deja de ser CRITICO -que bloqueaba la
        # modelacion- y pasa a advertencia. La estimabilidad la decide el catalogo
        # por modelo (P0-B), no un minimo global sin fuente.
        estado_longitud = ESTADO_ADVERTENCIA
    elif n < ADVERTENCIA_MIN_OBS:
        estado_longitud = ESTADO_ADVERTENCIA
    elif n < MIN_OBS:
        estado_longitud = ESTADO_ADVERTENCIA
    else:
        estado_longitud = ESTADO_CORRECTO
    resultados.append(
        _validacion(
            "longitud_serie",
            estado_longitud,
            f"Observaciones numéricas válidas: {n}. Mínimo recomendado: {MIN_OBS}.",
            "Series cortas limitan el diagnostico y el backtesting.",
            "Con pocas observaciones la proyección puede no ser defendible.",
            "Usar un nivel de agregación con mas historia o esperar nuevos periodos publicados.",
        )
    )

    archivo_fuente = str(serie.attrs.get("archivo_fuente", ""))
    resultados.append(
        _validacion(
            "trazabilidad_archivo",
            ESTADO_CORRECTO if archivo_fuente else ESTADO_ADVERTENCIA,
            f"Archivo fuente registrado: {archivo_fuente or 'No registrado'}.",
            "La trazabilidad permite reproducir el análisis.",
            "Sin archivo fuente se debilita el soporte documental del pronostico.",
            "Registrar la ruta o nombre del archivo oficial usado.",
        )
    )

    criticos = [r for r in resultados if r.estado == ESTADO_CRITICO]
    advertencias = [r for r in resultados if r.estado == ESTADO_ADVERTENCIA]
    return {
        "resultados": [r.como_dict() for r in resultados],
        "errores_criticos": [r.descripcion for r in criticos],
        "advertencias": [r.descripcion for r in advertencias],
        # P0-G REABIERTO: sin el termino de longitud minima global.
        "valida_modelacion": len(criticos) == 0,
        "observaciones": n,
        "valores_faltantes": faltantes,
        "duplicados": duplicados,
        "periodos_invalidos": periodos_invalidos,
        "valores_no_numericos": no_numericos,
        "valores_no_positivos": no_positivos,
        "continuidad_temporal": "OK" if continuidad["estado"] == ESTADO_CORRECTO else "REVISAR",
        "orden_cronologico": "OK",
        "longitud_minima": "OK" if n >= MIN_OBS else "REVISAR",
        "periodos_faltantes": continuidad["periodos_faltantes"],
        "primer_periodo": valores_validos["Periodo"].iloc[0] if n else "",
        "ultimo_periodo": valores_validos["Periodo"].iloc[-1] if n else "",
    }


def calcular_variables_derivadas(serie: pd.DataFrame) -> dict[str, Any]:
    """Calcula descriptivos y variaciones usadas por UI e informes."""
    datos = serie.dropna(subset=["Periodo", "Indice"]).copy()
    datos = datos.sort_values("orden_temporal").reset_index(drop=True)
    y = datos["Indice"].to_numpy(dtype=float)
    if len(datos) == 0:
        return {"serie": datos, "estadisticas": {}}

    datos["diferencia_simple"] = datos["Indice"].diff()
    datos["variacion_mensual_pct"] = datos["Indice"].pct_change() * 100.0
    datos["variacion_anual_pct"] = datos["Indice"].pct_change(12) * 100.0
    datos["variacion_anio_corrido_pct"] = _variacion_anio_corrido(datos)
    if np.all(y > 0):
        datos["diferencia_logaritmica"] = np.log(datos["Indice"]).diff()
    else:
        datos["diferencia_logaritmica"] = np.nan

    media = float(np.mean(y))
    desv = float(np.std(y, ddof=1)) if len(y) > 1 else 0.0
    estadisticas = {
        "media": media,
        "mediana": float(np.median(y)),
        "minimo": float(np.min(y)),
        "maximo": float(np.max(y)),
        "desviacion_estandar": desv,
        "coeficiente_variacion": float(desv / media) if abs(media) > EPS_NUMERICO else float("nan"),
        "observaciones": int(len(y)),
        "primer_periodo": str(datos["Periodo"].iloc[0]),
        "ultimo_periodo": str(datos["Periodo"].iloc[-1]),
        "valor_inicial": float(y[0]),
        "valor_final": float(y[-1]),
    }
    return {"serie": datos, "estadisticas": estadisticas}


def detectar_valores_atipicos_mad(
    serie: pd.DataFrame,
    columnas: tuple[str, ...] = ("variacion_mensual_pct", "diferencia_simple", "diferencia_logaritmica"),
    umbral_atipico: float = UMBRAL_Z_ATIPICO,
    **compatibilidad: Any,
) -> list[dict[str, Any]]:
    """Detecta posibles atípicos con z robusto (mediana y MAD) y los clasifica.

    El umbral documentado es |M_i| > 3.5 (NIST/SEMATECH e-Handbook, 1.3.5.17).
    Las detecciones de las tres escalas se consolidan en una alerta por
    periodo (decisión aprobada D-4) y cada alerta se clasifica como:

    * ``patron_calendario``: enero que cumple los criterios confirmados del
      módulo de salto anual; se mantiene en la serie y NO cuenta como atípico.
    * ``posible_error_datos``: pico extremo (|z| > 2 x umbral) que revierte al
      mes siguiente; se reporta para verificación contra el anexo oficial.
    * ``posible_cambio_nivel``: salto que persiste en los meses siguientes.
    * ``posible_atipico_aislado``: el resto.

    Ningun valor se elimina, interpola ni suaviza.
    """
    _ = compatibilidad
    crudas: list[dict[str, Any]] = []
    informativas: list[dict[str, Any]] = []
    for columna in columnas:
        if columna not in serie.columns:
            continue
        valores = pd.to_numeric(serie[columna], errors="coerce")
        validos = valores.dropna()
        if len(validos) < 6:
            continue
        mediana = float(validos.median())
        mad = float(np.median(np.abs(validos.to_numpy(dtype=float) - mediana)))
        if mad <= EPS_NUMERICO:
            informativas.append(
                {
                    "periodo": "",
                    "columna": columna,
                    "variable": columna,
                    "escala": columna,
                    "valor": float("nan"),
                    "z_robusto": float("nan"),
                    "severidad": "mad_cero",
                    "criterio_id": "C-ATI-001",
                    "tipo_criterio": "bibliografico",
                    "umbral_atipico": float(umbral_atipico),
                    "mensaje": (
                        "No se aplica detección robusta de atípicos porque MAD=0; "
                        "la serie no presenta dispersion suficiente en esta escala."
                    ),
                }
            )
            continue
        z = 0.6745 * (valores - mediana) / mad
        for idx, valor_z in z.dropna().items():
            abs_z = abs(float(valor_z))
            if abs_z <= umbral_atipico:
                continue
            crudas.append(
                {
                    "idx": idx,
                    "periodo": str(serie.at[idx, "Periodo"]),
                    "escala": columna,
                    "valor": float(serie.at[idx, columna]),
                    "z_robusto": float(valor_z),
                }
            )
    return _consolidar_alertas_atipicos(serie, crudas, float(umbral_atipico)) + informativas


def _consolidar_alertas_atipicos(
    serie: pd.DataFrame,
    crudas: list[dict[str, Any]],
    umbral_atipico: float,
) -> list[dict[str, Any]]:
    """Deduplica detecciones por periodo y asigna la clasificación cuadruple."""
    if not crudas:
        return []
    from app_icociv.estadistica.calendario_anual import perfil_salto_anual

    perfil = perfil_salto_anual(serie)
    por_periodo: dict[str, list[dict[str, Any]]] = {}
    for alerta in crudas:
        por_periodo.setdefault(alerta["periodo"], []).append(alerta)

    variaciones = pd.to_numeric(
        serie.get("variacion_mensual_pct", pd.Series(dtype=float)), errors="coerce"
    )
    consolidadas: list[dict[str, Any]] = []
    for periodo in sorted(por_periodo, key=periodo_a_orden):
        grupo = por_periodo[periodo]
        principal = max(grupo, key=lambda a: abs(a["z_robusto"]))
        clasificacion = _clasificar_alerta(
            serie=serie,
            idx=principal["idx"],
            z_abs=abs(float(principal["z_robusto"])),
            umbral=umbral_atipico,
            perfil=perfil,
            variaciones=variaciones,
        )
        severidad = "patron_calendario" if clasificacion == "patron_calendario" else "posible_atipico"
        consolidadas.append(
            {
                "periodo": periodo,
                "columna": principal["escala"],
                "variable": principal["escala"],
                "escala": principal["escala"],
                "escalas_detectadas": [a["escala"] for a in grupo],
                "valor": principal["valor"],
                "z_robusto": float(principal["z_robusto"]),
                "severidad": severidad,
                "clasificacion": clasificacion,
                "criterio_id": "C-ATI-001",
                "tipo_criterio": "bibliografico",
                "umbral_atipico": float(umbral_atipico),
                "mensaje": _mensaje_clasificacion_alerta(clasificacion),
            }
        )
    return consolidadas


def _clasificar_alerta(
    serie: pd.DataFrame,
    idx: Any,
    z_abs: float,
    umbral: float,
    perfil: dict[str, Any],
    variaciones: pd.Series,
) -> str:
    """Aplica en orden: patron calendario, posible error, cambio de nivel, aislado."""
    try:
        variacion = float(variaciones.at[idx])
    except (KeyError, TypeError, ValueError):
        variacion = float("nan")

    mes = _mes_de_fila(serie, idx)
    gamma = perfil.get("gamma")
    if (
        mes == 1
        and perfil.get("hay_evidencia")
        and isinstance(gamma, float)
        and math.isfinite(gamma)
        and math.isfinite(variacion)
        and (variacion > 0) == (gamma > 0)
    ):
        return "patron_calendario"

    # Reversion observada en los 1-2 meses siguientes, como fraccion del salto.
    posicion = serie.index.get_loc(idx)
    siguientes: list[float] = []
    for paso in (1, 2):
        if posicion + paso < len(serie.index):
            valor = variaciones.iloc[posicion + paso]
            siguientes.append(float(valor) if math.isfinite(_float_o_nan(valor)) else 0.0)
        else:
            siguientes.append(0.0)
    if not math.isfinite(variacion) or abs(variacion) <= EPS_NUMERICO:
        return "posible_atipico_aislado"
    reversion_1 = max(0.0, -siguientes[0] / variacion)
    reversion_2 = max(reversion_1, -(siguientes[0] + siguientes[1]) / variacion)
    if z_abs > 2.0 * umbral and reversion_1 >= 0.5:
        return "posible_error_datos"
    if reversion_2 < 0.5:
        return "posible_cambio_nivel"
    return "posible_atipico_aislado"


def _mes_de_fila(serie: pd.DataFrame, idx: Any) -> int:
    if "mes" in serie.columns:
        try:
            return int(serie.at[idx, "mes"])
        except (TypeError, ValueError):
            pass
    try:
        return int(normalizar_periodo(serie.at[idx, "Periodo"]).split("_")[1])
    except Exception:
        return 0


def _mensaje_clasificacion_alerta(clasificacion: str) -> str:
    mensajes = {
        "patron_calendario": (
            "Comportamiento recurrente de cambio de año (patron calendario confirmado). "
            "El valor se mantiene en la serie y no se contabiliza como atípico."
        ),
        "posible_error_datos": (
            "Pico extremo que revierte al mes siguiente; posible error de datos o de lectura. "
            "Verificar contra el anexo oficial; el valor no se elimina automáticamente."
        ),
        "posible_cambio_nivel": (
            "Salto que persiste en los meses siguientes; posible cambio de nivel de la serie. "
            "Requiere revisión técnica; el valor no se elimina automáticamente."
        ),
        "posible_atipico_aislado": (
            "Valor atípico aislado; requiere revisión técnica porque puede corresponder a un "
            "comportamiento real de la serie o a una anomalía de lectura."
        ),
    }
    return mensajes.get(clasificacion, mensajes["posible_atipico_aislado"])


def evaluar_factibilidad_proyeccion(
    serie: pd.DataFrame,
    validacion: dict[str, Any],
    outliers: list[dict[str, Any]] | None = None,
    diagnostico: dict[str, Any] | None = None,
    backtesting: dict[str, Any] | None = None,
    comparacion_benchmarks: dict[str, Any] | None = None,
    evaluacion_intervalos: dict[str, Any] | None = None,
    horizonte_solicitado: int = 1,
) -> dict[str, Any]:
    """Decide factibilidad de forma gradual: datos, modelado y proyección."""
    outliers = outliers or []
    diagnostico = diagnostico or {}
    backtesting = backtesting or {}
    comparacion_benchmarks = comparacion_benchmarks or {}
    evaluacion_intervalos = evaluacion_intervalos or {}
    n = int(validacion.get("observaciones", 0))
    razones: list[str] = []
    advertencias: list[str] = []
    bloqueos_proyeccion: list[str] = []
    estado_datos = evaluar_calidad_datos(validacion, outliers)

    if not estado_datos["analizable"]:
        razones.extend(estado_datos["razones"])
    elif n < ADVERTENCIA_MIN_OBS:
        bloqueos_proyeccion.append("La serie no cuenta con longitud suficiente para validación temporal defendible.")
    elif n < MIN_OBS:
        advertencias.append("La serie esta por debajo del mínimo recomendado de 24 observaciones.")
    if validacion.get("continuidad_temporal") != "OK" and estado_datos["analizable"]:
        bloqueos_proyeccion.append("Existen saltos temporales o datos faltantes que afectan la continuidad mensual.")

    bt_metricas = backtesting.get("metricas", {}) if backtesting else {}
    estado_modelado = evaluar_capacidad_modelado(diagnostico, backtesting)
    if backtesting and not backtesting.get("ejecutado", False):
        bloqueos_proyeccion.append("No fue posible ejecutar backtesting temporal con iteraciones suficientes.")
    elif bt_metricas:
        mape = _float_o_nan(bt_metricas.get("mape"))
        smape = _float_o_nan(bt_metricas.get("smape"))
        mase = _float_o_nan(bt_metricas.get("mase"))
        rmse = _float_o_nan(bt_metricas.get("rmse"))
        mae = _float_o_nan(bt_metricas.get("mae"))
        sesgo = _float_o_nan(bt_metricas.get("sesgo_medio", bt_metricas.get("error_medio")))
        estabilidad = _float_o_nan(bt_metricas.get("estabilidad_error"))
        extremos = _float_o_nan(bt_metricas.get("porcentaje_errores_extremos"))
        iteraciones = int(backtesting.get("iteraciones", 0) or bt_metricas.get("iteraciones", 0) or 0)
        # P0-G, 12-08-2026: RETIRADO como bloqueo. `MIN_ITERACIONES_WF = 6` no
        # tiene fuente -el propio comentario de `servicio_proyeccion` lo llama
        # «un corte interno sin fuente»- y alli dejo de degradar el 08-08-2026.
        # Aqui habia quedado VIVO como veto, forzando horizonte_maximo = 0 y
        # confianza «no recomendable», mientras el otro modulo lo trataba como
        # simple advertencia: el mismo numero con dos tratamientos opuestos
        # (REQ 24 y REQ 25). Se conserva como ADVERTENCIA DESCRIPTIVA, que es lo
        # que REQ 5 permite, y el numero de ventanas se publica por horizonte.
        if iteraciones < MIN_ITERACIONES_BACKTESTING:
            advertencias.append(
                f"El backtesting de referencia tiene {iteraciones} ventanas de validación. "
                "El número de ventanas se publica por horizonte; no existe un mínimo "
                "metodológicamente sustentado para declarar validada la capacidad predictiva."
            )
        if math.isfinite(mase) and mase > UMBRAL_MASE_ADVERTENCIA:
            advertencias.append(MENSAJE_MASE_MAYOR_UNO)
        # D-9: se retiran las bandas de MAPE (8 / 15 / 25 %) y de sMAPE (20 / 30 %).
        # No proceden de ninguna fuente: convertian el error relativo en
        # advertencia o bloqueo. MAPE y sMAPE se siguen calculando y publicando
        # con sus valores; la unica lectura comparativa conservada es MASE frente
        # a 1, que es el sentido con el que la metrica esta definida.
        if math.isfinite(estabilidad) and estabilidad > UMBRAL_ESTABILIDAD_INESTABLE:
            advertencias.append("Los errores de backtesting son inestables entre ventanas temporales.")
        # D-8: la proporcion de errores inusuales no bloquea ni advierte. Los
        # cortes 15 % y 25 % eran porcentajes internos sin fuente. La deteccion
        # individual se conserva y se publica como dato descriptivo.
        # D-9: se retira la advertencia por |sesgo| > 0,75 x MAE. El factor 0,75
        # era interno y sin fuente. El sesgo medio se publica con su signo y su
        # magnitud, que es lo que permite juzgar si el error es direccional.
        if not math.isfinite(rmse) or not math.isfinite(mae):
            bloqueos_proyeccion.append("No fue posible calcular errores MAE/RMSE válidos en backtesting.")

    # D-2: se retiran los cortes fijos de Durbin-Watson (0,8 / 3,2 / 1,5 / 2,5).
    # No proceden de Durbin y Watson (1951) ni de ningun manual: el contraste se
    # resuelve con las tablas d_L y d_U, que dependen de n y del numero de
    # regresores y que la aplicacion no implementa. El estadistico se sigue
    # calculando y publicando como dato descriptivo; lo que se retira es la
    # advertencia categorica que reducia la confianza declarada.
    #
    # Ljung-Box SE CONSERVA como diagnostico, con su advertencia y su valor p.

    # D-7: los diagnosticos residuales se comunican como contrastes, sin afirmar
    # la hipotesis nula y sin cortes propios distintos del nivel de significancia.
    ljung_box = diagnostico.get("ljung_box") or {}
    lb_p = _float_o_nan(ljung_box.get("p_value"))
    if math.isfinite(lb_p) and lb_p < ALPHA_PRUEBAS_RESIDUALES:
        advertencias.append(
            "Ljung-Box: se rechazó la hipótesis nula de ausencia de autocorrelación conjunta "
            "al nivel seleccionado."
        )

    hetero = diagnostico.get("heterocedasticidad") or {}
    if hetero.get("calculable") and _float_o_nan(hetero.get("p_value")) < ALPHA_PRUEBAS_RESIDUALES:
        advertencias.append(
            "Breusch-Pagan: se rechazó la hipótesis nula de varianza constante al nivel "
            "seleccionado."
        )

    media_residual = diagnostico.get("media_residual") or {}
    if media_residual.get("calculable") and _float_o_nan(media_residual.get("p_value")) < ALPHA_PRUEBAS_RESIDUALES:
        advertencias.append(
            "Media residual: se rechazó la hipótesis nula de media cero al nivel seleccionado."
        )

    jb_p = _float_o_nan(diagnostico.get("jb_p"))
    if math.isfinite(jb_p) and jb_p < ALPHA_PRUEBAS_RESIDUALES:
        advertencias.append(
            "Jarque-Bera: se rechazó la hipótesis nula de normalidad al nivel seleccionado."
        )

    acf = diagnostico.get("acf") or []
    acf_criticos = [
        item for item in acf[:6]
        if math.isfinite(_float_o_nan(item.get("valor"))) and abs(_float_o_nan(item.get("valor"))) >= 0.75
    ]
    if acf_criticos:
        advertencias.append("Los residuos muestran un patron temporal evidente en la ACF.")

    if comparacion_benchmarks:
        # CIERRE 08-08-2026: la comparacion con los benchmarks deja de bloquear
        # la factibilidad. El corte que la disparaba -1,25- no tiene fuente
        # identificada. El error relativo se sigue calculando y se publica como
        # advertencia con su valor; el modelo lo elige el desempeno OOS.
        if comparacion_benchmarks.get("modelo_no_supera_benchmarks"):
            advertencias.append(
                "El modelo seleccionado tiene mayor RMSE fuera de muestra que el benchmark naive "
                "en el horizonte evaluado (rRMSE > 1); se informa como comparacion."
            )
        elif comparacion_benchmarks.get("peor_que_naive_rmse") or comparacion_benchmarks.get("peor_que_drift_rmse"):
            advertencias.append("El modelo seleccionado no domina todos los benchmarks; se justifica cautela.")

    # `evaluacion_intervalos` ya no aporta nada a esta funcion. Historia del
    # retiro, en tres pasos, porque cada uno cerro una ruta distinta:
    #
    # P0-G, 16-08-2026 (V-CODEX-3). La criticidad de la BANDA entraba en
    #   `bloqueos_proyeccion` cuando el horizonte solicitado era 1, y
    #   `bloqueos_proyeccion` fuerza `horizonte_maximo = 0` mas abajo: una banda
    #   invalida cancelaba el PUNTO. Paso a advertencia en todos los horizontes.
    # P0-C / C2, 15-08-2026. Se retiro «El intervalo de prediccion es amplio
    #   frente al valor proyectado (ancho relativo maximo X %)».
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Se retira la ultima rama, que
    #   volcaba `evaluacion_intervalos["razones"]` en la lista publicada. Dos de
    #   esas razones llevan el ancho relativo con su valor, y el ancho relativo
    #   multiplicado por el punto -que es publico y debe serlo- devuelve el
    #   SEMIANCHO de la banda retirada: es una representacion equivalente del
    #   intervalo. Las demas describen estados de un objeto que no se entrega.
    #
    # El parametro se conserva en la firma: el ancho y el estado de banda siguen
    # calculandose y viajando como diagnostico interno, y quitarlo obligaria a
    # tocar a todos los llamadores sin cambiar ningun resultado.

    outliers_relevantes = [item for item in outliers if item.get("severidad") == "posible_atipico"]
    if outliers_relevantes:
        advertencias.append(
            f"Se detectaron {len(outliers_relevantes)} posibles valores atípicos según Z robusto modificado."
        )

    razones = _deduplicar_textos(razones)
    advertencias = _deduplicar_textos(advertencias)
    bloqueos_proyeccion = _deduplicar_textos(bloqueos_proyeccion)

    horizonte_maximo = _horizonte_base_por_longitud(n)
    if validacion.get("continuidad_temporal") != "OK":
        horizonte_maximo = min(horizonte_maximo, 3)
    if any("autocorrelación" in a.lower() for a in advertencias + razones):
        horizonte_maximo = min(horizonte_maximo, 6)
    # D-9: se retiran los recortes de horizonte por MAPE > 8 % y por MASE >= 0,8.
    # Ambos cortes eran internos y sin fuente.
    # P0-G, 16-08-2026 (V-CODEX-3). Aqui el ANCHO de la banda recortaba el
    # horizonte maximo a seis. El ancho es una magnitud del intervalo retirado y
    # no puede decidir hasta donde se publica el punto; el corte, ademas, no
    # tenia fuente. Se retira el recorte. El ancho se sigue calculando como
    # diagnostico interno y se comunica como advertencia donde corresponde.
    if not estado_datos["proyectable"]:
        horizonte_maximo = 0
    elif bloqueos_proyeccion:
        horizonte_maximo = 0

    # P0-G, 12-08-2026: RETIRADA la escalera de confianza «alto / medio / bajo /
    # no recomendable».
    #
    # Estaba gobernada por SEIS literales sin fuente -3, 24, 48, 12, mas el 18 y
    # el 6 que heredaba- y su nombre, «nivel de confianza metodologica», sugiere
    # una probabilidad o un nivel de cobertura que no es: era una clasificacion
    # ordinal de cuatro categorias. El proyecto ya habia aplicado este mismo
    # criterio dos veces -la decision V-C de los intervalos y el 0,90 convertido
    # en descriptivo-, sustituyendo nombres que afirmaban cobertura por
    # identificadores neutros; aqui no se habia hecho.
    #
    # NO se sustituye por otra escala, score, semaforo ni porcentaje: se publica
    # el HECHO verificable -si hay o no advertencias- y las magnitudes que las
    # sostienen, que ya se calculan todas y viajan por separado.
    if not estado_datos["proyectable"]:
        estado = "No proyectable por errores criticos de datos"
        confianza = "sin evaluacion: datos no admiten modelacion"
        factible = False
        razones.extend(estado_datos["razones"])
    elif advertencias:
        estado = "Calculable con advertencias"
        confianza = "descriptivo: ver advertencias y magnitudes publicadas"
        factible = True
    else:
        estado = "Calculable sin advertencias"
        confianza = "descriptivo: sin advertencias registradas"
        factible = True

    if factible and horizonte_solicitado > horizonte_maximo:
        advertencias.append(
            "El horizonte solicitado supera el rango estadísticamente defendible con la información disponible."
        )

    puede_informe = True
    explicacion = (
        _explicacion_no_proyeccion(razones)
        if not factible
        else _explicacion_factible(estado, horizonte_maximo, advertencias)
    )
    return {
        "factible": bool(factible),
        "estado": estado,
        "estado_datos": estado_datos,
        "estado_modelado": estado_modelado,
        "estado_proyeccion": {
            "estado": estado,
            "bloqueos": bloqueos_proyeccion,
            "horizonte_maximo": int(horizonte_maximo),
        },
        "nivel_confianza_metodologica": confianza,
        "razones_tecnicas": razones,
        "advertencias": advertencias,
        "horizonte_maximo_sugerido": int(horizonte_maximo),
        "puede_generarse_informe": puede_informe,
        "explicacion": explicacion,
    }


# `determinar_horizonte_maximo` se retiro el 04-08-2026. Estaba exportada en
# `app_icociv.estadistica.__init__` y no tenia ningun invocador: la ruta viva
# usa `servicio_proyeccion.determinar_horizonte_maximo_estadistico`. Arrastraba
# consigo el unico consumidor de UMBRAL_INTERVALO_CRITICO y unos recortes de
# horizonte por Ljung-Box y por benchmarks que nunca llegaron a ejecutarse.



def _variacion_anio_corrido(datos: pd.DataFrame) -> pd.Series:
    valores: list[float] = []
    por_anio: dict[int, float] = {}
    for _, fila in datos.iterrows():
        anio = int(fila["anio"])
        valor = float(fila["Indice"])
        if anio not in por_anio:
            por_anio[anio] = valor
            valores.append(float("nan"))
        else:
            base = por_anio[anio]
            valores.append(((valor / base) - 1.0) * 100.0 if abs(base) > EPS_NUMERICO else float("nan"))
    return pd.Series(valores, index=datos.index)


def _evaluar_continuidad(serie: pd.DataFrame) -> dict[str, Any]:
    if serie.empty:
        return {
            "estado": ESTADO_CRITICO,
            "descripcion": "No hay periodos válidos para evaluar continuidad.",
            "periodos_faltantes": [],
            "recomendacion": "Verificar lectura del archivo fuente.",
        }
    ordenes = sorted(int(v) for v in serie["orden_temporal"].dropna().unique())
    faltantes = [orden_a_periodo(v) for v in range(ordenes[0], ordenes[-1] + 1) if v not in ordenes]
    if not faltantes:
        return {
            "estado": ESTADO_CORRECTO,
            "descripcion": "La serie presenta frecuencia mensual continua.",
            "periodos_faltantes": [],
            "recomendacion": "Continuar con análisis estadístico.",
        }
    estado = ESTADO_ADVERTENCIA if len(faltantes) <= 2 else ESTADO_CRITICO
    return {
        "estado": estado,
        "descripcion": f"Se detectaron saltos temporales: {faltantes[:12]}.",
        "periodos_faltantes": faltantes,
        "recomendacion": "Revisar si los meses faltantes existen en el anexo oficial.",
    }


def _validacion(
    criterio: str,
    estado: str,
    descripcion: str,
    impacto_analisis: str,
    impacto_proyeccion: str,
    recomendacion: str,
) -> ResultadoValidacion:
    return ResultadoValidacion(
        criterio=criterio,
        estado=estado,
        descripcion=descripcion,
        impacto_analisis=impacto_analisis,
        impacto_proyeccion=impacto_proyeccion,
        recomendacion=recomendacion,
    )


def _float_o_nan(valor: Any) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return float("nan")
    return numero if math.isfinite(numero) else float("nan")


def evaluar_calidad_datos(validacion: dict[str, Any], outliers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Evalua solo calidad de datos, sin juzgar aun el modelo."""
    outliers = outliers or []
    n = int(validacion.get("observaciones", 0))
    errores = list(validacion.get("errores_criticos", []) or [])
    razones = list(errores)
    advertencias = list(validacion.get("advertencias", []) or [])
    outliers_relevantes = [item for item in outliers if item.get("severidad") == "posible_atipico"]
    if n < MIN_OBS_MODELACION:
        # P0-G REABIERTO, 14-08-2026. `MIN_OBS_MODELACION = 8` era una PUERTA
        # GLOBAL sin fuente identificada, superpuesta a la comprobacion que P0-B
        # ya resolvio: la estimabilidad se decide POR MODELO -minimos de 2, 4 o 6
        # observaciones segun el estimador, y positividad para los logaritmicos-,
        # y un candidato que no sea estimable queda excluido con su error
        # registrado, que es el mecanismo general de elegibilidad. Medido con
        # n = 8: los modelos lineal, drift y naive ajustan y proyectan un punto
        # finito. Pasa de razon de bloqueo a advertencia.
        advertencias.append(
            f"La serie tiene menos de {MIN_OBS_MODELACION} observaciones numéricas válidas: "
            "solo se consideran los modelos que resulten estimables con esa longitud, y la "
            "evidencia fuera de muestra disponible es mínima."
        )
    elif n < ADVERTENCIA_MIN_OBS:
        advertencias.append("La serie es corta para validación predictiva; usar solo análisis descriptivo o cautela extrema.")
    if outliers_relevantes:
        advertencias.append(
            f"Se detectaron {len(outliers_relevantes)} posibles atípicos sobre variaciones; no se eliminan automáticamente."
        )
    # P0-G REABIERTO: retirado tambien aqui el termino `n >= MIN_OBS_MODELACION`,
    # por el mismo motivo que arriba. Lo que decide es que no queden razones
    # criticas; la longitud minima por si sola no es una de ellas.
    analizable = len(razones) == 0
    # P0-G, 12-08-2026: RETIRADO `n >= ADVERTENCIA_MIN_OBS` de esta condicion.
    #
    # Pese a su nombre, la constante funcionaba como VETO: con n = 17 la serie
    # dejaba de ser proyectable, aunque todos los modelos del catalogo son
    # estimables desde 6 observaciones y esa serie produce once ventanas fuera
    # de muestra en h=1. No tiene fuente, y FPP3 13.7 desautoriza expresamente
    # este tipo de minimo muestral: «misleading and unsubstantiated in theory or
    # practice». La constante SIGUE generando su advertencia, que es su nombre y
    # su alcance legitimo.
    #
    # Lo que si es una imposibilidad -no poder estimar, no tener pares fuera de
    # muestra- ya lo cubren `MIN_OBS_MODELACION` y el piso de ventanas por
    # horizonte. No se sustituye 18 por ningun otro numero.
    proyectable = len(errores) == 0 and validacion.get("continuidad_temporal") == "OK"
    if not analizable:
        estado = "No analizable por errores criticos de datos"
    elif not proyectable:
        estado = "Analizable, no proyectable por datos"
    elif advertencias:
        estado = "Datos aptos con advertencias"
    else:
        estado = "Datos aptos"
    return {
        "estado": estado,
        "analizable": bool(analizable),
        "proyectable": bool(proyectable),
        "razones": _deduplicar_textos(razones),
        "advertencias": _deduplicar_textos(advertencias),
    }


def evaluar_capacidad_modelado(diagnostico: dict[str, Any], backtesting: dict[str, Any]) -> dict[str, Any]:
    """Evalua si existe información suficiente para modelar sin decidir proyección final."""
    razones: list[str] = []
    advertencias: list[str] = []
    metricas = backtesting.get("metricas", {}) if backtesting else {}
    if not backtesting or not backtesting.get("ejecutado"):
        razones.append("No hay backtesting ejecutado para evaluar capacidad de modelado.")
    elif int(backtesting.get("iteraciones", 0) or metricas.get("iteraciones", 0) or 0) < MIN_ITERACIONES_BACKTESTING:
        razones.append("El backtesting no tiene iteraciones suficientes para evaluar modelos.")
    if not math.isfinite(_float_o_nan(metricas.get("rmse"))) or not math.isfinite(_float_o_nan(metricas.get("mae"))):
        razones.append("MAE/RMSE de backtesting no son finitos.")
    # D-2: sin cortes fijos de Durbin-Watson. El valor se reporta; no genera
    # advertencia categorica basada en umbrales sin fuente.
    if diagnostico.get("alertas"):
        advertencias.extend(str(item) for item in diagnostico.get("alertas", []))
    return {
        "estado": "Modelado viable" if not razones else "Modelado no confiable",
        "modelable": not razones,
        "razones": _deduplicar_textos(razones),
        "advertencias": _deduplicar_textos(advertencias),
    }


def _mejora_la_referencia_naive(metricas_bt: dict[str, Any], diagnostico: dict[str, Any]) -> bool:
    """Comprueba la única lectura comparativa sustentada: MASE frente a 1.

    D-9: la versión anterior componía tres cortes internos sin fuente ---MAPE
    < 3 %, MASE < 0,8 y estabilidad <= 0,75--- para declarar «confianza alta».
    Se conserva únicamente la comparación de MASE respecto de 1, que es el
    sentido con el que la métrica fue definida: por debajo de 1 el modelo mejora
    en promedio al pronóstico ingenuo de la escala de entrenamiento
    (Hyndman y Koehler, 2006). No sustituye a los ratios rRMSE/rMAE frente a los
    benchmarks reales de backtesting, que se reportan aparte.

    D-2: Durbin-Watson no interviene en esta clasificación.
    """
    if not metricas_bt:
        return False
    mase = _float_o_nan(metricas_bt.get("mase"))
    return bool(math.isfinite(mase) and mase < UMBRAL_MASE_ADVERTENCIA)


def _horizonte_base_por_longitud(n: int) -> int:
    if n < ADVERTENCIA_MIN_OBS:
        return 0
    if n < MIN_OBS:
        return 3
    if n < 36:
        return 6
    if n < 60:
        return 12
    if n < 84:
        return 18
    return 24


def _explicacion_no_proyeccion(razones: list[str]) -> str:
    if not razones:
        return "La proyección no se genera porque la serie no cumple criterios mínimos de factibilidad."
    if any(MENSAJE_AUTOCORRELACION_SEVERA in razon for razon in razones):
        return MENSAJE_AUTOCORRELACION_SEVERA
    if any(MENSAJE_MASE_MAYOR_UNO in razon for razon in razones):
        return MENSAJE_MASE_MAYOR_UNO
    principales = razones[:3]
    return "La proyección no se genera porque " + " ".join(principales)


def _explicacion_factible(estado: str, horizonte: int, advertencias: list[str]) -> str:
    if estado == "Proyectable":
        return "La serie es proyectable: datos completos, backtesting estable e intervalos razonables."
    if estado == "Solo proyección de corto plazo":
        return (
            f"Se permite proyección de corto plazo hasta {horizonte} mes(es) porque existe evidencia "
            "predictiva limitada; no se recomienda ampliar el horizonte."
        )
    if advertencias:
        return "Se permite proyección con cautela: " + " ".join(advertencias[:2])
    return "Se permite proyección con cautela bajo las restricciones metodologicas registradas."


def _deduplicar_textos(textos: list[str]) -> list[str]:
    vistos: set[str] = set()
    salida: list[str] = []
    for texto in textos:
        limpio = str(texto).strip()
        if not limpio or limpio in vistos:
            continue
        vistos.add(limpio)
        salida.append(limpio)
    return salida
