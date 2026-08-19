"""
servicio_proyeccion.py
Orquesta la selecciÃ³n jerÃ¡rquica de tablas A16.x y ejecuta la proyecciÃ³n
del Ã­ndice ICOCIV para la fila/nivel seleccionado.

La selecciÃ³n jerÃ¡rquica se modela como parÃ¡metros explÃ­citos
(sin st.session_state).  El consumidor (UI o script) es responsable
de recolectar esos parÃ¡metros antes de llamar a estas funciones.
"""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import numpy as np

from app_icociv.estadistica.criterios import (
    EPS_NUMERICO,
    HORIZONTE_LARGO,
    MIN_ERRORES_COBERTURA_EMPIRICA,
    COBERTURA_IC95_ACEPTABLE,
    COBERTURA_IC95_ADVERTENCIA,
    TOLERANCIA_COBERTURA_IC95,
    MIN_ITERACIONES_WF_ESCENARIO,
    UMBRAL_ESTABILIDAD_INESTABLE,
    UMBRAL_IC95_REL_CORTO,
    UMBRAL_IC95_REL_EXTENDIDO,
    UMBRAL_IC95_REL_EXTENDIDO_CERCANO,
    UMBRAL_IC95_REL_EXPLORATORIO,
    UMBRAL_IC95_REL_LARGO,
    UMBRAL_IC95_REL_MEDIO,
    UMBRAL_IC95_REL_OPERATIVO,
    UMBRAL_MASE_ADVERTENCIA,
    UMBRAL_RRMSE_PEOR_BENCHMARK,
    TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO,
    TOLERANCIA_RRMSE_BENCHMARK,
)
from app_icociv.utilidades.utilidades import (
    ANIO_BASE,
    filtrar_dataframe,
    periodo_a_t,
    t_a_periodo,
)

from app_icociv.validacion.backtesting import (
    _entrenamiento_inicial,
    ejecutar_backtesting_comparativo,
    seleccionar_mejor_modelo,
)
from app_icociv.estadistica.calendario_anual import (
    _mes_de_periodo,
    aplicar_ajuste_calendario,
    eneros_en_horizonte,
    evaluar_ajuste_en_backtesting,
    perfil_salto_anual,
    resumen_trazabilidad,
)
from app_icociv.estadistica.diagnostico_residuos import (
    evaluar_residuos,
    generar_interpretacion_estadistica,
)
from app_icociv.estadistica.metricas import (
    calcular_escala_naive_insample,
    calcular_mae,
    calcular_mape,
    calcular_mase_por_origen,
    calcular_metricas,
    calcular_rmse,
    calcular_sesgo_medio,
    calcular_smape,
)
from app_icociv.estadistica.analisis_series import (
    MIN_ITERACIONES_BACKTESTING,
    calcular_variables_derivadas,
    detectar_valores_atipicos_mad,
    evaluar_factibilidad_proyeccion,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.estadistica.modelos_interpretables import (
    MODELOS_INTERPRETABLES,
    ajustar_modelos_candidatos,
    observaciones_minimas_catalogo,
    proyectar_modelo,
)
from app_icociv.estadistica.validacion_series import (
    analizar_serie_temporal,
)


# Horizontes de referencia para validar el ajuste calendario. Son fijos a proposito:
# la decision de aplicar el ajuste debe ser una propiedad de la serie y del modelo,
# no del horizonte que solicite el usuario. Cubren el corto plazo, donde mas se
# consulta la proyeccion y donde hay mas ventanas walk-forward disponibles.
HORIZONTES_VALIDACION_CALENDARIO = (1, 3, 6)

#: AUDITORIA 09-08-2026, P0-B. `MODELOS_NIVEL_1`, `MODELOS_NIVEL_2` y
#: `MODELOS_BENCHMARK_DESCRIPTIVO` gobernaban un escalonado del catalogo con
#: literales sin fuente. Se retiran: la elegibilidad es ahora estimabilidad
#: matematica. `MODELOS_NIVEL_2` estaba ademas MUERTA -definida y nunca leida- y
#: no coincidia con la lista que el codigo usaba en linea.
#:
#: Modelos excluidos por tener un PARAMETRO PROPIO SIN SUSTENTO: la ventana de
#: seis periodos de `promedio_movil` y `variacion_reciente` no tiene fuente
#: identificada. Un parametro de esa categoria no puede decidir un resultado
#: publicado, de modo que el modelo no compite mientras no se estime o se
#: sustente. No es un filtro de conveniencia: es una razon metodologica, y es
#: reversible.
MODELOS_PARAMETRO_SIN_SUSTENTO = frozenset({"promedio_movil", "variacion_reciente"})


def _catalogo_activo() -> tuple[str, ...]:
    """Candidatos que realmente compiten. Fija el primer origen comun (P0-E)."""
    return tuple(m for m in MODELOS_INTERPRETABLES if m not in MODELOS_PARAMETRO_SIN_SUSTENTO)


CATALOGO_MODELOS_CANDIDATOS = {
    "naive": ("Naive último valor", "Benchmark sobre nivel", "Referencia mínima: último valor observado."),
    "drift": ("Drift", "Benchmark con tendencia", "Extiende el cambio promedio entre primer y último dato."),
    "holt_lineal": ("Holt lineal", "Suavizamiento exponencial", "Modelo base de nivel y tendencia."),
    "holt_amortiguado": ("Holt tendencia amortiguada", "Suavizamiento exponencial", "Modelo base con tendencia amortiguada."),
    "lineal": ("Lineal (OLS)", "Regresion sobre nivel", "Referencia interpretable de tendencia lineal del índice."),
    "logaritmico": ("Logarítmica temporal (OLS)", "Regresion sobre nivel", "Referencia interpretable de tendencia decreciente/curva logarítmica temporal."),
    "exponencial_log_lineal": ("Exponencial/log-lineal", "Regresion sobre nivel transformado", "Referencia de crecimiento proporcional; requiere índices positivos."),
    "variacion_lineal": ("Modelo sobre variación mensual", "Modelo sobre variación", "Modela variación mensual y reconstruye el índice."),
    "log_variacion": ("Modelo sobre log-variación mensual", "Modelo sobre log-variación", "Modela log-variación mensual; no equivale a regresion logarítmica temporal."),
    "huber": ("Huber (robusta)", "Regresion robusta", "Se activa ante outliers relevantes."),
    "promedio_movil": ("Promedio movil", "Benchmark descriptivo", "Contraste simple; no se privilegia como modelo principal."),
}



# ==============================
# SELECCIÃ“N JERÃRQUICA
# ==============================

def resolver_fila_seleccionada(
    tables: dict[str, pd.DataFrame],
    year_month: list[str],
    selection: dict,
) -> tuple[str, pd.DataFrame]:
    """
    Determina la fila fuente para el reporte segÃºn el Ã¡rbol de selecciÃ³n.

    La lÃ³gica replica exactamente la ramificaciÃ³n original:
      Nivel 1  â†’ T_16  (Grupos_Obra)
      chk_T16  â†’ Rama A: T_16_6 â†’ T_16_7
      ~chk_T16 â†’ Rama B:
          T_16_1 (Subclases)
          chk_T16_1 â†’ T_16_8 â†’ T_16_9
          ~chk_T16_1 â†’ T_16_2 (Tip_obra)
              chk_T16_2 â†’ T_16_10 â†’ T_16_11
              ~chk_T16_2 â†’ T_16_3 (Cap_const)
                  chk_T16_3 â†’ T_16_12 â†’ T_16_13

    Args:
        tables: dict de DataFrames (resultado de cargar_todas_tablas).
        year_month: lista de etiquetas de periodos.
        selection: diccionario con las claves de selecciÃ³n.
            Claves posibles:
              idx_g          (int)  Ã­ndice en T_16 â€” requerido
              chk_T16        (bool) rama costos/insumos global
              idx_l2         (int|None)
              idx_l3         (int|None)
              idx_l4         (int|None)
              idx_l5         (int|None)
              idx_l6         (int|None)
              chk_T16_1      (bool) rama costos subclase
              chk_T16_2      (bool) rama costos tipologÃ­a
              chk_T16_3      (bool) rama costos capÃ­tulo

    Returns:
        (fuente, fila) donde fuente es el identificador de tabla
        ('T_16', 'T_16_1', ...) y fila es el DataFrame de 1 fila.

    Raises:
        ValueError: si idx_g no estÃ¡ presente.
    """
    idx_g = selection.get("idx_g")
    if idx_g is None:
        raise ValueError("Debes seleccionar al menos el Grupo (T_16).")

    chk_T16   = bool(selection.get("chk_T16", False))
    chk_T16_1 = bool(selection.get("chk_T16_1", False))
    chk_T16_2 = bool(selection.get("chk_T16_2", False))
    chk_T16_3 = bool(selection.get("chk_T16_3", False))

    idx_l2 = selection.get("idx_l2")
    idx_l3 = selection.get("idx_l3")
    idx_l4 = selection.get("idx_l4")
    idx_l5 = selection.get("idx_l5")
    idx_l6 = selection.get("idx_l6")

    T_16 = tables["T_16"]
    fuente = "T_16"
    fila = T_16.loc[[idx_g]].copy()

    codigo_grupo = T_16.at[idx_g, "Codigo_Grupos"]

    # ---- RAMA A: chk_T16 ----
    if chk_T16:
        if idx_l3 is not None:
            T_16_7 = tables["T_16_7"]
            df_l3 = filtrar_dataframe(
                T_16_7,
                {"Codigo_Grupos": codigo_grupo},
                dropna_col="Insumos",
            )
            if not df_l3.empty and idx_l3 < len(df_l3):
                fuente = "T_16_7"
                fila = df_l3.loc[[idx_l3]].copy()
                return fuente, fila

        if idx_l2 is not None:
            T_16_6 = tables["T_16_6"]
            df_l2 = filtrar_dataframe(
                T_16_6,
                {"Codigo_Grupos": codigo_grupo},
                dropna_col="Grupo_Costos",
            )
            if not df_l2.empty and idx_l2 < len(df_l2):
                fuente = "T_16_6"
                fila = df_l2.loc[[idx_l2]].copy()
        return fuente, fila

    # ---- RAMA B: ~chk_T16 ----
    if idx_l2 is None:
        return fuente, fila

    T_16_1 = tables["T_16_1"]
    df_l2_base = filtrar_dataframe(
        T_16_1,
        {"Codigo_Grupos": codigo_grupo},
        dropna_col="Subclases",
    )
    if df_l2_base.empty or idx_l2 >= len(df_l2_base):
        return fuente, fila

    cod_subclase = df_l2_base.at[idx_l2, "Cod_Subclases"]

    # ---- B1: chk_T16_1 ----
    if chk_T16_1:
        if idx_l4 is not None:
            df_l4 = filtrar_dataframe(
                tables["T_16_9"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase},
                dropna_col="Insumos",
            )
            if not df_l4.empty and idx_l4 < len(df_l4):
                return "T_16_9", df_l4.loc[[idx_l4]].copy()

        if idx_l3 is not None:
            df_l3 = filtrar_dataframe(
                tables["T_16_8"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase},
                dropna_col="Grupos_costos",
            )
            if not df_l3.empty and idx_l3 < len(df_l3):
                return "T_16_8", df_l3.loc[[idx_l3]].copy()

        return "T_16_1", df_l2_base.loc[[idx_l2]].copy()

    # ---- B2: ~chk_T16_1 ----
    if idx_l3 is None:
        return "T_16_1", df_l2_base.loc[[idx_l2]].copy()

    df_l3_tip = filtrar_dataframe(
        tables["T_16_2"],
        {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase},
        dropna_col="Tip_obra",
    )
    if df_l3_tip.empty or idx_l3 >= len(df_l3_tip):
        return "T_16_1", df_l2_base.loc[[idx_l2]].copy()

    cod_tip_obra = df_l3_tip.at[idx_l3, "Cod_tip_obra"]

    # ---- B2a: chk_T16_2 ----
    if chk_T16_2:
        if idx_l5 is not None:
            df_l5 = filtrar_dataframe(
                tables["T_16_11"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase,
                 "Cod_tip_obra": cod_tip_obra},
                dropna_col="Insumos",
            )
            if not df_l5.empty and idx_l5 < len(df_l5):
                return "T_16_11", df_l5.loc[[idx_l5]].copy()

        if idx_l4 is not None:
            df_l4 = filtrar_dataframe(
                tables["T_16_10"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase,
                 "Cod_tip_obra": cod_tip_obra},
                dropna_col="Grupo_Costos",
            )
            if not df_l4.empty and idx_l4 < len(df_l4):
                return "T_16_10", df_l4.loc[[idx_l4]].copy()

        return "T_16_2", df_l3_tip.loc[[idx_l3]].copy()

    # ---- B2b: ~chk_T16_2 â†’ T_16_3 ----
    if idx_l4 is None:
        return "T_16_2", df_l3_tip.loc[[idx_l3]].copy()

    df_l4_cap = filtrar_dataframe(
        tables["T_16_3"],
        {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase,
         "Cod_tip_obra": cod_tip_obra},
        dropna_col="Cap_const",
    )
    if df_l4_cap.empty or idx_l4 >= len(df_l4_cap):
        return "T_16_2", df_l3_tip.loc[[idx_l3]].copy()

    cod_agreg_niv_cap = df_l4_cap.at[idx_l4, "cod_agreg_niv_obra_cap"]

    # ---- chk_T16_3 ----
    if chk_T16_3:
        if idx_l6 is not None:
            df_l6 = filtrar_dataframe(
                tables["T_16_13"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase,
                 "Cod_tip_obra": cod_tip_obra,
                 "cod_agreg_nivel_obra_capitulo": cod_agreg_niv_cap},
                dropna_col="Insumos",
            )
            if not df_l6.empty and idx_l6 < len(df_l6):
                return "T_16_13", df_l6.loc[[idx_l6]].copy()

        if idx_l5 is not None:
            df_l5 = filtrar_dataframe(
                tables["T_16_12"],
                {"Codigo_Grupos": codigo_grupo, "Cod_Subclases": cod_subclase,
                 "Cod_tip_obra": cod_tip_obra,
                 "cod_agreg_nivel_obra_capitulo": cod_agreg_niv_cap},
                dropna_col="Grupo_Costos",
            )
            if not df_l5.empty and idx_l5 < len(df_l5):
                return "T_16_12", df_l5.loc[[idx_l5]].copy()

        return "T_16_3", df_l4_cap.loc[[idx_l4]].copy()

    return "T_16_3", df_l4_cap.loc[[idx_l4]].copy()


# ==============================
# CONSTRUCCIÃ“N DE LA SERIE HISTÃ“RICA
# ==============================

def construir_serie(fila: pd.DataFrame, year_month: list[str]) -> pd.DataFrame:
    """
    Extrae la serie histÃ³rica de la fila seleccionada.

    Args:
        fila: DataFrame de 1 fila con columnas fijas + year_month.
        year_month: lista de etiquetas de periodos.

    Returns:
        DataFrame con columnas ['Periodo', 'Índice'] sin NaN al final,
        ordenado cronolÃ³gicamente.

    Raises:
        ValueError: si la serie no contiene ningÃºn dato numÃ©rico.

    P0-B, 16-08-2026 (auditorÃ­a independiente V-CODEX-3). AquÃ­ habÃ­a
    `len(serie) < 8 -> ValueError`. Ocho no tiene fuente -el propio catÃ¡logo lo
    tipa `operativo_interno_sin_sustento`- y decidÃ­a la admisibilidad ANTES de
    consultar la estimabilidad propia de cada candidato: una serie de siete
    observaciones quedaba negada aunque varios modelos produjeran un pronÃ³stico
    finito. Extraer la serie es una operaciÃ³n de datos, no una decisiÃ³n
    estadÃ­stica; el Ãºnico fallo real es que no haya dato alguno. QuÃ© modelos
    pueden ajustarse lo decide `OBSERVACIONES_MINIMAS_MODELO` por candidato.
    """
    month_cols = [c for c in year_month if c in fila.columns]
    tabla_serie = fila[month_cols]
    serie = tabla_serie.T.reset_index()
    serie.columns = ["Periodo", "Indice"]
    serie["Indice"] = pd.to_numeric(serie["Indice"], errors="coerce")
    serie = serie.dropna(subset=["Indice"]).reset_index(drop=True)

    if serie.empty:
        raise ValueError("La serie seleccionada no contiene datos numÃ©ricos.")
    return serie


# ==============================
# PROYECCIÃ“N COMPLETA
# ==============================

MENSAJE_HORIZONTE_INVALIDO = "El horizonte solicitado debe ser un número entero positivo de meses."
#: Limite de ENTRADA del producto: horizonte maximo que el usuario puede pedir.
#: P0-H, 12-08-2026: se conserva y se RECLASIFICA. Verificado que su unico uso es
#: `validar_horizonte_solicitado`, es decir la validacion del dato de entrada; NO
#: interviene en ningun calculo estadistico ni en la rejilla evaluada. No tiene
#: fuente y NO debe presentarse como «maximo estadisticamente valido»: es un
#: limite operativo del producto.
HORIZONTE_MAXIMO_OPERATIVO = 60

#: Estado metodológico del resultado (P0-G, 12-08-2026).
#:
#: Separa lo que hasta ahora colapsaba en una sola magnitud: **poder calcular**
#: no es **tener evidencia cerrada**, y ninguna de las dos es **estar
#: metodológicamente sustentado**. Los cuatro valores se derivan de hechos que la
#: aplicación ya calcula; **ninguno introduce un umbral**.
#:
#: Con P0-C abierto y P0-E bloqueado, los dos últimos estados quedan definidos y
#: **vacíos**: no se alcanzan por decreto.
ESTADO_NO_CALCULABLE = "no_calculable"
ESTADO_CALCULABLE_PENDIENTE = "calculable_metodologia_pendiente"
ESTADO_PUNTUAL_SIN_INTERVALO = "puntual_disponible_intervalo_no_sustentado"
ESTADO_SUSTENTADO = "resultado_metodologicamente_sustentado"

ESTADOS_METODOLOGICOS = (
    ESTADO_NO_CALCULABLE,
    ESTADO_CALCULABLE_PENDIENTE,
    ESTADO_PUNTUAL_SIN_INTERVALO,
    ESTADO_SUSTENTADO,
)

#: Bloqueos metodológicos vigentes que impiden declarar un resultado sustentado.
#: Cada entrada nombra el bloque de la reauditoría y por qué sigue abierto.
BLOQUEOS_METODOLOGICOS_VIGENTES = {
    "P0-C": (
        "No existe una construcción de intervalos de predicción adoptable bajo la "
        "configuración actual. La banda que la aplicación calcula NO tiene método "
        "sustentado y no se publica como intervalo institucional."
    ),
    "P0-E": (
        "El primer origen de la validación temporal no está determinado por ninguna "
        "fuente ni derivación suficiente. Toda la evidencia fuera de muestra es "
        "PROVISIONAL mientras esa decisión siga abierta."
    ),
}


def estado_metodologico(punto_disponible: bool) -> str:
    """Estado metodológico del resultado. Sin umbrales.

    Mientras existan bloqueos vigentes, un resultado calculable no puede
    declararse sustentado: la evidencia que lo respaldaría depende de una
    decisión metodológica abierta. Eso **no** lo convierte en «no calculable»,
    que es una afirmación distinta y falsa.
    """
    if not punto_disponible:
        return ESTADO_NO_CALCULABLE
    if "P0-E" in BLOQUEOS_METODOLOGICOS_VIGENTES:
        return ESTADO_CALCULABLE_PENDIENTE
    if "P0-C" in BLOQUEOS_METODOLOGICOS_VIGENTES:
        return ESTADO_PUNTUAL_SIN_INTERVALO
    return ESTADO_SUSTENTADO
#: P0-H, 12-08-2026: RETIRADO `HORIZONTE_MAXIMO_AUDITORIA = 30`. Era un tope sin
#: fuente que recortaba la rejilla evaluada y, a traves de ella, el horizonte
#: publicado. La rejilla la fija ahora la disponibilidad de datos.
VERSION_CRITERIOS_HORIZONTE = "icociv-horizontes-v2"


def validar_horizonte_solicitado(valor: Any, maximo: int = HORIZONTE_MAXIMO_OPERATIVO) -> int:
    """Válida la entrada manual sin aceptar decimales, vacíos o valores absurdos."""
    if isinstance(valor, bool) or valor is None or str(valor).strip() == "":
        raise ValueError(MENSAJE_HORIZONTE_INVALIDO)
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(MENSAJE_HORIZONTE_INVALIDO) from exc
    if not np.isfinite(numero) or numero != int(numero) or numero <= 0 or numero > int(maximo):
        raise ValueError(MENSAJE_HORIZONTE_INVALIDO)
    return int(numero)


def ejecutar_proyeccion(
    serie_df: pd.DataFrame,
    year_proj: int,
    month_proj: int,
    anio_base: int,
    origen_horizonte: str = "predeterminado",
) -> dict:
    """Ejecuta la proyección y separa el resultado solicitado del análisis completo."""
    resultado = _ejecutar_proyeccion_base(
        serie_df=serie_df,
        year_proj=year_proj,
        month_proj=month_proj,
        anio_base=anio_base,
    )
    return _retirar_intervalo_de_publicacion(
        _estructurar_resultado_horizontes(resultado, origen_horizonte)
    )


#: P0-C / ESTRATEGIA C2, 15-08-2026. Claves y columnas del objeto público que
#: entregaban los límites de la banda del 95 % (y del 80 %, retirada de las
#: salidas al usuario el 26-07-2026 pero aún viva aquí).
CLAVES_LIMITE_PUBLICAS = ("ci_lo", "ci_hi", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi")
#: Claves cuyo valor era la pareja `[inferior, superior]` en la ficha del
#: horizonte solicitado: es la superficie que el lector ve primero.
CLAVES_PAREJA_PUBLICAS = ("ic80", "ic95")
COLUMNAS_LIMITE_PUBLICAS = (
    "limite_inferior", "limite_superior",
    "limite_inferior_80", "limite_superior_80",
    "limite_inferior_95", "limite_superior_95",
)

#: P0-C, 16-08-2026 (auditoría independiente V-CODEX-3). Vaciar los extremos NO
#: retiraba el intervalo: la fórmula productiva es
#:
#:      base   = punto / factor_calendario
#:      limite = (base + offset) * factor_calendario
#:
#: de modo que basta publicar la pareja de offsets percentiles —o `sigma_h` con
#: su cuantil, o directamente el ancho— para RECONSTRUIR los límites exactos con
#: el punto y el factor, que sí son públicos y deben serlo.
#:
#: Codex lo verificó numéricamente: con los extremos en `None` coexistían
#: `width95 = 0.3730222350477561`, `sigma_h = 0.09282708861214928`,
#: `q95 = 2.0345152974493383` y offsets `±0.18651111752386804`, y la fórmula
#: reprodujo los límites de esa misma ejecución.
COLUMNAS_RECONSTRUCTIVAS = (
    "sigma_h_intervalo",
    "q80_intervalo", "q95_intervalo",
    "percentil_80_inf_intervalo", "percentil_80_sup_intervalo",
    "percentil_95_inf_intervalo", "percentil_95_sup_intervalo",
    "ancho_relativo_80", "ancho_relativo_95", "ancho_relativo_intervalo",
    "ic95_relativo",
    # El método es la receta de construcción de la banda retirada; publicarlo
    # junto a sus parámetros completa la trazabilidad de un objeto que no se
    # entrega.
    "metodo_intervalo", "metodo_intervalo_codigo",
)
#: Claves de `stats` con la misma capacidad reconstructiva.
CLAVES_STATS_RECONSTRUCTIVAS = ("width95", "width80", "ancho_relativo_intervalo_max")

#: P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Vaciar los extremos, los offsets y
#: el método NO retiró el intervalo: la tabla de ventanas de backtesting seguía
#: publicando el VECTOR COMPLETO de errores fuera de muestra, y la fórmula
#: productiva del intervalo es
#:
#:      sigma_h = sqrt( mean( e_oos ** 2 ) )
#:      limite  = punto ± c(n) · sigma_h
#:
#: donde `punto` y `c(n)` son públicos y deben serlo. Con el vector, cualquiera
#: reproduce los límites EXACTOS del intervalo retirado. Codex lo verificó con
#: n=48, h=6: 37 errores públicos y el punto devolvieron el IC95 completo.
#:
#: Ninguna de estas columnas puede quedar en una superficie pública, porque
#: TODAS reconstruyen `sigma_h`:
#:
#:   * `Error`                -> directamente;
#:   * `Observado`/`Predicho` -> su diferencia ES `Error`;
#:   * `Error_abs`            -> `sigma_h` no depende del signo;
#:   * `Error_pct`            -> con `Observado` devuelve `Error_abs`;
#:   * `Error_escalado_abs` y `Escala_naive_insample` -> su producto es
#:     `Error_abs`.
#:
#: SE CONSERVA el DISEÑO de la validación, que es lo que el REQ 16 exige
#: documentar y no permite reconstruir nada: origen, periodo objetivo, paso,
#: modelo ajustado en ese corte y tamaño del entrenamiento. Y se conservan los
#: AGREGADOS -RMSE, MAE, MASE, MAPE/sMAPE, sesgo, `iteraciones`-, que sostienen
#: la sustentación: de un promedio de cuadrados no se recupera la muestra, y sin
#: ellos el trabajo no podría defender su evaluación fuera de muestra.
#:
#: El vector NO se borra: sigue en el resultado interno de `ejecutar_backtesting`
#: y alimenta métricas, calendario y diagnósticos dentro de
#: `_ejecutar_proyeccion_base`. Este corte es posterior a todos ellos.
COLUMNAS_OOS_RECONSTRUCTIVAS = (
    "Observado", "Predicho", "Error", "Error_abs", "Error_pct",
    "Error_escalado_abs", "Escala_naive_insample",
)

#: Las mismas magnitudes viajan replicadas en la tabla de estado por horizonte,
#: dentro de `horizonte_info` y `analisis_horizontes_completo`. El ancho relativo
#: multiplicado por el punto —que sí es público y debe serlo— devuelve el ancho
#: absoluto de la banda retirada, de modo que también es reconstructivo.
CLAVES_ANCHO_POR_HORIZONTE = (
    "ancho_relativo_80", "ancho_relativo_95", "ancho_relativo_intervalo",
    "ancho_relativo", "ancho_relativo_maximo",
    "ancho_relativo_80_maximo", "ancho_relativo_95_maximo",
    "ic95_relativo",
)


def _vaciar_claves_en_arbol(objeto: Any, claves: tuple[str, ...], vistos: set[int] | None = None) -> None:
    """Pone a ``None`` las claves indicadas en cualquier nivel de la estructura.

    Las magnitudes de la banda no viajan en un solo sitio: se replican por
    horizonte dentro de `horizonte_info`, y `analisis_horizontes_completo`
    comparte esos mismos objetos. Vaciarlas una a una por ruta dejaría copias
    vivas en cuanto alguien añadiera un bloque nuevo; recorrer el árbol vacía
    todas y no depende de la forma actual del resultado.
    """
    vistos = vistos if vistos is not None else set()
    if id(objeto) in vistos:
        return
    if isinstance(objeto, dict):
        vistos.add(id(objeto))
        for clave in list(objeto):
            if clave in claves:
                objeto[clave] = None
            else:
                _vaciar_claves_en_arbol(objeto[clave], claves, vistos)
    elif isinstance(objeto, list):
        vistos.add(id(objeto))
        for item in objeto:
            _vaciar_claves_en_arbol(item, claves, vistos)


def _retirar_intervalo_de_publicacion(resultado: dict[str, Any]) -> dict[str, Any]:
    """Deja de entregar los límites de una banda cuyo método no está sustentado.

    P0-C sigue abierto: la construcción completa del intervalo no cumple el §20
    de la constitución, y el propio resultado lo declara con
    ``intervalo_sustentado = False``. Entregar sus límites con nueve decimales
    mientras se declara que no están sustentados es la incoherencia que la
    estrategia C2 retira.

    Se retira la PUBLICACIÓN, no el cálculo. La banda se sigue calculando
    dentro de ``_ejecutar_proyeccion_base``, y este corte va DESPUÉS de todos
    sus lectores -por eso vive en ``ejecutar_proyeccion`` y no en
    ``_construir_tabla_proyecciones``-, de modo que no puede alterar ninguna
    decisión estadística: es una restricción de implementación de la
    categoría D del §3, no una regla metodológica.

    CORREGIDO 18-08-2026 (H-8, auditoria final V-CODEX-R2). Decia "sigue
    siendo decisoria donde lo era". Eso fue cierto hasta el 12-08-2026 (P0-G):
    desde entonces la amplitud, la cobertura y los límites de la banda NO
    deciden nada -ni el punto ni la clasificación del horizonte-. Lo único que
    sobrevive es que la comprobación de finitud de la banda incluye al propio
    pronóstico puntual (ver ``_clasificar_evidencia_horizonte``), de modo que
    un punto no finito bloquea; eso es una imposibilidad del punto, detectada
    de paso por ese cálculo, no una decisión de la banda sobre sí misma.

    Las claves y columnas se conservan con valor ``None``. Ni se eliminan -hay
    consumidores legítimos que comprueban la forma del contrato sin publicar el
    número- ni se rellenan con un estado textual que obligaría a un caso
    especial en cada lector. ``None`` ya es el «sin valor» del proyecto.

    NO se sustituye por otra banda, no se renombra el intervalo y no se afirma
    que la incertidumbre no exista: ``intervalo_sustentado``,
    ``motivo_intervalo_no_sustentado`` y ``bloqueos_metodologicos`` siguen
    viajando y publicándose. El pronóstico puntual no se toca.
    """
    for clave in CLAVES_LIMITE_PUBLICAS:
        if clave in resultado:
            resultado[clave] = None
    solicitado = resultado.get("resultado_horizonte_solicitado")
    if isinstance(solicitado, dict):
        for clave in CLAVES_PAREJA_PUBLICAS:
            if clave in solicitado:
                solicitado[clave] = None
    tabla = resultado.get("proyecciones")
    if isinstance(tabla, pd.DataFrame):
        for columna in (*COLUMNAS_LIMITE_PUBLICAS, *COLUMNAS_RECONSTRUCTIVAS):
            if columna in tabla.columns:
                tabla[columna] = None

    # P0-C, 16-08-2026 (V-CODEX-3). Lo anterior vaciaba los extremos; esto retira
    # lo que permitía reconstruirlos y lo que caracterizaba la banda.
    estadisticas = resultado.get("stats")
    if isinstance(estadisticas, dict):
        for clave in CLAVES_STATS_RECONSTRUCTIVAS:
            if clave in estadisticas:
                estadisticas[clave] = None

    # La cobertura y la clasificación describen el desempeño de la banda
    # retirada. Que una clave se llame «no publicado» no la vuelve privada: todo
    # lo que devuelve `ejecutar_proyeccion` ES la salida pública. El cálculo
    # permanece dentro de `_ejecutar_proyeccion_base`, donde es diagnóstico.
    for clave in ("cobertura_empirica", "clasificacion_intervalo",
                  "diagnostico_cobertura_no_publicado", "degradacion_por_cobertura"):
        if clave in resultado:
            resultado[clave] = None

    # Del bloque del paso exacto se conserva SOLO el tamaño de la evidencia
    # —cuántos errores fuera de muestra reúne el horizonte—, que describe la
    # trayectoria y no la banda, y es información legítima (§ REQ 16). Se retiran
    # la cobertura observada, el mínimo global y la verificabilidad, que califican
    # el intervalo.
    paso = resultado.get("verificabilidad_paso_exacto")
    if isinstance(paso, dict):
        resultado["verificabilidad_paso_exacto"] = {
            "paso_exacto": paso.get("paso_exacto"),
            "n_errores_oos": paso.get("n_errores_oos"),
        }

    # Y por último las réplicas por horizonte: `horizonte_info` y
    # `analisis_horizontes_completo` llevan el ancho relativo de la banda en cada
    # fila de `estado_por_horizonte`.
    for bloque in ("horizonte_info", "analisis_horizontes_completo"):
        _vaciar_claves_en_arbol(resultado.get(bloque), CLAVES_ANCHO_POR_HORIZONTE)

    # P0-C, 17-08-2026 (V-CODEX-R3). El vector de errores fuera de muestra. Es la
    # última superficie que reconstruía los límites exactos, y la más silenciosa:
    # no lleva la palabra «intervalo» en ninguna clave. Ver
    # `COLUMNAS_OOS_RECONSTRUCTIVAS`.
    _retirar_errores_oos_de_publicacion(resultado.get("backtesting"))
    comparativo = resultado.get("backtesting_comparativo")
    if isinstance(comparativo, dict):
        # Un candidato por modelo y horizonte: cada uno lleva su propio vector, y
        # el del modelo seleccionado es exactamente el que alimenta la fórmula.
        for entrada in comparativo.values():
            _retirar_errores_oos_de_publicacion(entrada)
    return resultado


def _retirar_errores_oos_de_publicacion(backtesting: Any) -> None:
    """Deja la tabla de ventanas sin los errores que reconstruyen el intervalo.

    Se recorta la copia que viaja en el resultado; el bloque interno del que
    proceden las métricas ya se consumió antes de llegar aquí. Las columnas se
    ELIMINAN en vez de vaciarse -al contrario que las claves del intervalo- porque
    una columna de errores llena de ``None`` en una tabla de sesenta ventanas es
    un formulario vacío, no un dato: el lector no necesita saber que ahí había un
    número. Las columnas de diseño y el recuento de ventanas se conservan.
    """
    if not isinstance(backtesting, dict):
        return
    tabla = backtesting.get("predicciones")
    if not isinstance(tabla, pd.DataFrame):
        return
    sobrantes = [c for c in COLUMNAS_OOS_RECONSTRUCTIVAS if c in tabla.columns]
    if sobrantes:
        backtesting["predicciones"] = tabla.drop(columns=sobrantes)


def _ejecutar_proyeccion_base(
    serie_df: pd.DataFrame,
    year_proj: int,
    month_proj: int,
    anio_base: int,
) -> dict:
    """Ejecuta validación, selección de modelo, backtesting y proyección."""
    if not 1 <= int(month_proj) <= 12:
        raise ValueError("El mes de proyección debe estar entre 1 y 12.")

    serie_normalizada = normalizar_serie_mensual(serie_df)
    validacion_serie = validar_serie_mensual(serie_normalizada)
    derivadas = calcular_variables_derivadas(serie_normalizada)
    serie_trabajo = derivadas["serie"].copy()
    serie_trabajo["t"] = serie_trabajo["Periodo"].apply(lambda p: periodo_a_t(p, anio_base=anio_base))
    outliers = detectar_valores_atipicos_mad(serie_trabajo)
    analisis_serie = analizar_serie_temporal(serie_trabajo.rename(columns={"Indice": "Indice"}))

    if serie_trabajo.empty:
        return _resultado_sin_proyeccion(
            periodo_solicitado=f"{year_proj}_{month_proj}",
            validacion_serie=validacion_serie,
            analisis_serie=analisis_serie,
            variables_derivadas=derivadas,
            outliers=outliers,
            explicacion="La proyección no se genera porque no existen valores numéricos válidos.",
        )

    t_obs = serie_trabajo["t"].to_numpy(dtype=float)
    y_obs = serie_trabajo["Indice"].to_numpy(dtype=float)
    t_ultimo = int(np.max(t_obs))
    t_solicitado = (int(year_proj) - anio_base) * 12 + (int(month_proj) - 1)
    periodo_solicitado = f"{int(year_proj)}_{int(month_proj)}"
    if t_solicitado <= t_ultimo:
        raise ValueError("La proyección debe ser posterior al último periodo observado.")

    horizonte_solicitado = validar_horizonte_solicitado(t_solicitado - t_ultimo)
    # P0-B, 16-08-2026 (V-CODEX-3). Retirado el segundo termino de esta puerta,
    # `observaciones < 8`. Era el veto global que Codex demostro decisorio: una
    # serie mensual lineal de siete datos devolvia `proyeccion_generada=False`
    # aunque los candidatos activos producian un punto finito para h=1. El ocho
    # no tiene fuente y el propio catalogo lo tipa
    # `operativo_interno_sin_sustento`. La estimabilidad la decide ahora cada
    # candidato por su `N_min`; si ninguno puede ajustarse, el bloqueo llega mas
    # abajo y se justifica por ausencia de candidato, que si es una razon real.
    # Los errores criticos de la serie SI siguen bloqueando: son datos invalidos,
    # no una carencia de longitud.
    if validacion_serie.get("errores_criticos"):
        factibilidad = evaluar_factibilidad_proyeccion(
            serie=serie_trabajo,
            validacion=validacion_serie,
            outliers=outliers,
            horizonte_solicitado=horizonte_solicitado,
        )
        return _resultado_sin_proyeccion(
            periodo_solicitado=periodo_solicitado,
            horizonte_solicitado=horizonte_solicitado,
            validacion_serie=validacion_serie,
            analisis_serie=analisis_serie,
            variables_derivadas=derivadas,
            outliers=outliers,
            factibilidad=factibilidad,
            explicacion=factibilidad.get("explicacion"),
        )

    horizontes_eval = _horizontes_evaluacion(horizonte_solicitado, len(y_obs))
    metadatos_auditoria = _metadatos_auditoria_horizontes(
        serie_trabajo,
        horizonte_solicitado,
        origen_horizonte="interno",
    )
    modelos_evaluados, politica_modelos = _modelos_para_analisis(
        serie_trabajo=serie_trabajo,
        horizonte_solicitado=horizonte_solicitado,
        validacion_serie=validacion_serie,
        outliers=outliers,
    )
    candidatos = ajustar_modelos_candidatos(t_obs, y_obs, modelos=modelos_evaluados)
    backtesting_comparativo = ejecutar_backtesting_comparativo(
        serie_trabajo[["Periodo", "Indice"]],
        modelos=modelos_evaluados,
        horizontes=horizontes_eval,
        anio_base=anio_base,
    )
    # Un unico modelo por serie: se fija antes de evaluar horizontes para que la
    # clasificacion de admisibilidad, las metricas, los intervalos y la
    # trayectoria correspondan todos al mismo modelo.
    modelo_consistente = _modelo_consistente_desde_comparativo(backtesting_comparativo, horizontes_eval)
    evaluaciones_horizonte = _evaluar_horizontes_proyeccion(
        candidatos=candidatos,
        backtesting_comparativo=backtesting_comparativo,
        horizontes=horizontes_eval,
        serie_trabajo=serie_trabajo,
        validacion_serie=validacion_serie,
        outliers=outliers,
        t_ultimo=t_ultimo,
        y_obs=y_obs,
        anio_base=anio_base,
        modelo_fijo=modelo_consistente,
    )
    # Salvaguarda conservadora (D-3): si el modelo fijo produce un horizonte no
    # viable por causas del modelo, se prueban Drift y Naive antes de bloquear.
    evaluaciones_horizonte, modelo_consistente, salvaguarda_benchmark = _aplicar_salvaguarda_benchmarks(
        evaluaciones=evaluaciones_horizonte,
        modelo_consistente=modelo_consistente,
        candidatos=candidatos,
        backtesting_comparativo=backtesting_comparativo,
        horizontes=horizontes_eval,
        serie_trabajo=serie_trabajo,
        validacion_serie=validacion_serie,
        outliers=outliers,
        t_ultimo=t_ultimo,
        y_obs=y_obs,
        anio_base=anio_base,
        horizonte_solicitado=horizonte_solicitado,
    )
    seleccion_horizonte = _seleccionar_horizonte_permitido(evaluaciones_horizonte, horizonte_solicitado)
    if seleccion_horizonte is None:
        mejor_no_permitida = evaluaciones_horizonte[0] if evaluaciones_horizonte else {}
        modelo_np = mejor_no_permitida.get("modelo")
        # HGRID, 17-08-2026 (V-CODEX-R3, residual 2). Cuando la rejilla queda vacia
        # -`n <= N0`, ningun horizonte con una sola ventana- el motivo NO es que los
        # modelos no tengan «respaldo suficiente en backtesting»: eso enuncia un
        # juicio de calidad sobre una evaluacion que no llego a existir. El motivo
        # es la inexistencia del dato, causa (2), y se dice con el vocabulario de
        # evidencia OOS.
        #
        # Se cita el minimo del CATALOGO, no `_entrenamiento_inicial`: este ultimo
        # aplica el acotado de disponibilidad `N0 <= n-1` y devolveria un origen
        # -1 con n=2- que el backtesting nunca llega a usar, porque retorna antes
        # por no alcanzar el minimo de estimabilidad. El numero honesto es el que
        # realmente ata.
        if horizontes_eval:
            motivo_base = "Ningun modelo evaluado tuvo respaldo suficiente en backtesting."
        else:
            minimo_catalogo = observaciones_minimas_catalogo(_catalogo_activo())
            motivo_base = (
                f"{_texto_evidencia_oos(0)} Con {len(y_obs)} observaciones y un primer "
                f"origen de {minimo_catalogo} -provisional-, ningun horizonte reune un "
                f"solo error de origen movil: hacen falta al menos {minimo_catalogo + 1} "
                "observaciones para que exista un par (objetivo, horizonte)."
            )
        factibilidad_np = mejor_no_permitida.get("factibilidad") or {
            "factible": False,
            "estado": "No recomendable",
            "nivel_confianza_metodologica": "no recomendable",
            "razones_tecnicas": [motivo_base],
            "advertencias": [],
            "horizonte_maximo_sugerido": 0,
            "puede_generarse_informe": True,
            "explicacion": motivo_base,
        }
        catalogo_np = _catalogo_modelos_reporte(
            modelos_evaluados=modelos_evaluados,
            candidatos=candidatos,
            backtesting_por_modelo=mejor_no_permitida.get("backtesting_por_modelo", {}),
            modelo_seleccionado=modelo_np,
            horizonte=mejor_no_permitida.get("horizonte"),
            serie_trabajo=serie_trabajo,
        )
        horizonte_info_np = determinar_horizonte_maximo_estadistico(
            serie=serie_trabajo,
            modelos=candidatos,
            backtesting=backtesting_comparativo,
            intervalos=evaluaciones_horizonte,
            diagnosticos=mejor_no_permitida.get("diagnostico_residuos", {}),
            horizonte_solicitado=horizonte_solicitado,
            metadatos_auditoria=metadatos_auditoria,
        )
        horizonte_info_np["salvaguarda_benchmark"] = salvaguarda_benchmark
        if salvaguarda_benchmark.get("intentada"):
            # H-2B, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Esta
            # razon afirmaba sin comprobarlo "los benchmarks Drift y Naive
            # tampoco cumplieron los criterios minimos": no leia
            # `benchmark_habria_ampliado`, de modo que el texto podia
            # contradecir la propia tabla de benchmarks evaluados. La
            # salvaguarda es diagnostica (no sustituye), de ahi que el
            # bloqueo del horizonte se mantenga incluso si un benchmark
            # habria alcanzado mas alcance.
            if salvaguarda_benchmark.get("benchmark_habria_ampliado"):
                razon_bench = (
                    "Al menos un benchmark evaluado como referencia diagnóstica alcanzaría un "
                    "horizonte mayor, pero eso no sustituye al modelo principal: el bloqueo de este "
                    "horizonte se mantiene según la evidencia propia del modelo seleccionado."
                )
            else:
                razon_bench = (
                    "Los benchmarks Drift y Naive, evaluados como referencia diagnóstica, tampoco "
                    "alcanzarían un horizonte mayor que el modelo principal."
                )
            factibilidad_np.setdefault("razones_tecnicas", []).append(razon_bench)
        return _resultado_sin_proyeccion(
            periodo_solicitado=periodo_solicitado,
            horizonte_solicitado=horizonte_solicitado,
            validacion_serie=validacion_serie,
            analisis_serie=analisis_serie,
            variables_derivadas=derivadas,
            outliers=outliers,
            factibilidad=factibilidad_np,
            modelo=modelo_np,
            candidatos=candidatos,
            diagnostico_residuos=mejor_no_permitida.get("diagnostico_residuos", {}),
            backtesting=mejor_no_permitida.get("backtesting", {}),
            backtesting_comparativo=backtesting_comparativo,
            backtesting_por_modelo=mejor_no_permitida.get("backtesting_por_modelo", {}),
            politica_modelos=politica_modelos,
            catalogo_modelos=catalogo_np,
            horizonte_info=horizonte_info_np,
            explicacion=factibilidad_np.get("explicacion"),
        )

    # El modelo ya viene fijado desde la evaluacion de horizontes.
    modelo = seleccion_horizonte["modelo"]
    comparacion_benchmarks = modelo.get("comparacion_benchmarks", {})
    model_name = modelo["nombre_visible"]
    y_fit_obs = np.asarray(modelo["yhat"], dtype=float)
    residuos = np.asarray(modelo["residuos"], dtype=float)
    metricas_ajuste = modelo.get("metricas_ajuste", {})
    diagnostico_residuos = modelo.get("diagnostico_residuos")
    if not diagnostico_residuos:
        diagnostico_residuos = evaluar_residuos(residuos, tipo_modelo=modelo.get("nombre"))
    backtesting = seleccion_horizonte["backtesting"]
    backtesting_por_modelo = seleccion_horizonte["backtesting_por_modelo"]
    factibilidad = seleccion_horizonte["factibilidad"]
    horizonte_permitido = int(seleccion_horizonte["horizonte"])
    catalogo_modelos = _catalogo_modelos_reporte(
        modelos_evaluados=modelos_evaluados,
        candidatos=candidatos,
        backtesting_por_modelo=backtesting_por_modelo,
        modelo_seleccionado=modelo,
        horizonte=horizonte_permitido,
        serie_trabajo=serie_trabajo,
    )
    horizonte_info = determinar_horizonte_maximo_estadistico(
        serie=serie_trabajo,
        modelos=candidatos,
        backtesting=backtesting_comparativo,
        intervalos=evaluaciones_horizonte,
        diagnosticos=diagnostico_residuos,
        horizonte_solicitado=horizonte_solicitado,
        metadatos_auditoria=metadatos_auditoria,
    )
    horizonte_info["salvaguarda_benchmark"] = salvaguarda_benchmark
    horizonte_reconciliado = int(horizonte_info.get("horizonte_finalmente_permitido") or 0)
    if horizonte_reconciliado <= 0:
        factibilidad_bloqueada = dict(factibilidad)
        factibilidad_bloqueada.update(
            {
                "factible": False,
                "estado": "No recomendable",
                "nivel_confianza_metodologica": "no recomendable",
                "explicacion": (
                    "La proyección no se genera porque el modelo final aplicado no conserva "
                    "un horizonte consecutivo con evidencia estadística suficiente."
                ),
            }
        )
        return _resultado_sin_proyeccion(
            periodo_solicitado=periodo_solicitado,
            horizonte_solicitado=horizonte_solicitado,
            validacion_serie=validacion_serie,
            analisis_serie=analisis_serie,
            variables_derivadas=derivadas,
            outliers=outliers,
            factibilidad=factibilidad_bloqueada,
            modelo=modelo,
            candidatos=candidatos,
            diagnostico_residuos=diagnostico_residuos,
            backtesting=backtesting,
            backtesting_comparativo=backtesting_comparativo,
            backtesting_por_modelo=backtesting_por_modelo,
            politica_modelos=politica_modelos,
            catalogo_modelos=catalogo_modelos,
            horizonte_info=horizonte_info,
            explicacion=factibilidad_bloqueada["explicacion"],
        )
    if horizonte_reconciliado != horizonte_solicitado:
        explicacion_restriccion = (
            f"La proyección para h={horizonte_solicitado} no fue generada porque supera el máximo "
            f"permitido como escenario (h={horizonte_reconciliado})."
        )
        factibilidad_restringida = dict(factibilidad)
        factibilidad_restringida.update(
            {
                "factible": False,
                "estado": "No admisible",
                "nivel_confianza_metodologica": "no recomendable",
                "explicacion": explicacion_restriccion,
                "razones_tecnicas": _deduplicar_local(
                    list(factibilidad.get("razones_tecnicas", [])) + [explicacion_restriccion]
                ),
            }
        )
        return _resultado_sin_proyeccion(
            periodo_solicitado=periodo_solicitado,
            horizonte_solicitado=horizonte_solicitado,
            validacion_serie=validacion_serie,
            analisis_serie=analisis_serie,
            variables_derivadas=derivadas,
            outliers=outliers,
            factibilidad=factibilidad_restringida,
            candidatos=candidatos,
            diagnostico_residuos=diagnostico_residuos,
            backtesting=backtesting,
            backtesting_comparativo=backtesting_comparativo,
            backtesting_por_modelo=backtesting_por_modelo,
            politica_modelos=politica_modelos,
            catalogo_modelos=catalogo_modelos,
            horizonte_info=horizonte_info,
            explicacion=explicacion_restriccion,
        )
    horizonte_info["razones"] = _deduplicar_local(list(horizonte_info.get("razones", [])))
    factibilidad["horizonte_maximo_sugerido"] = int(horizonte_info.get("horizonte_maximo_recomendado") or 0)
    factibilidad["estado_proyeccion"] = {
        "estado": factibilidad.get("estado"),
        "horizonte_maximo_recomendado": horizonte_info.get("horizonte_maximo_recomendado"),
        "horizonte_maximo_permitido": horizonte_info.get("horizonte_maximo_permitido"),
        "horizonte_maximo_permitido_como_escenario": horizonte_info.get("horizonte_maximo_permitido_como_escenario"),
        "horizonte_maximo_admisible": horizonte_info.get("horizonte_maximo_admisible"),
        "horizonte_maximo_evaluado": horizonte_info.get("horizonte_maximo_evaluado"),
        "limite_operativo_evaluacion": horizonte_info.get("horizonte_maximo_busqueda_configurado"),
        "accion": horizonte_info.get("accion"),
    }
    if horizonte_permitido >= horizonte_solicitado:
        factibilidad["advertencias"] = [
            a for a in factibilidad.get("advertencias", [])
            if "horizonte solicitado supera" not in str(a).lower()
        ]
    t_permitido = t_ultimo + horizonte_permitido
    periodo_proj = t_a_periodo(t_permitido, anio_base).strip()
    t_futuro = np.arange(t_ultimo + 1, t_permitido + 1, dtype=float)
    last_obs = float(y_obs[-1])
    y_futuro = proyectar_modelo(modelo, t_futuro, forzar_desde=None)

    calendario = _ajustar_salto_anual(
        serie=serie_trabajo,
        y_futuro=y_futuro,
        backtesting_comparativo=backtesting_comparativo,
        modelo_codigo=str(modelo.get("nombre", "")),
        horizonte=horizonte_permitido,
    )
    factores_calendario = np.asarray(calendario["factores"], dtype=float)
    y_futuro = calendario["y_futuro"]
    trazabilidad_calendario = calendario["trazabilidad"]
    # Se advierte solo si hay patrón y no se ajustó; el caso aplicado se informa
    # en el bloque propio de la interfaz y en la trazabilidad de los reportes.
    if trazabilidad_calendario.get("hay_evidencia_calendario") and not trazabilidad_calendario.get(
        "ajuste_calendario_aplicado"
    ):
        factibilidad.setdefault("advertencias", []).append(trazabilidad_calendario["mensaje"])

    t_full = np.arange(int(t_obs.min()), int(t_permitido) + 1, dtype=float)
    y_fit_full = np.concatenate([y_fit_obs, y_futuro])

    errores_oos_modelo = _errores_por_horizonte(
        backtesting_comparativo,
        str(modelo.get("nombre", "")),
        tuple(range(1, int(horizonte_permitido) + 1)),
    )
    # P0-G REABIERTO, 14-08-2026. `_intervalos_prediccion` levanta cuando algun
    # paso no reune errores fuera de muestra suficientes: se niega -con razon- a
    # fabricar una banda sin respaldo. Esa negativa pertenece al EJE INTERVALO y
    # no debe cancelar el pronostico puntual, que ya esta calculado en `y_futuro`.
    #
    # Antes esto no se veia porque `_clasificar_evidencia_horizonte` bloqueaba el
    # horizonte mucho antes y la excepcion nunca se alcanzaba. Retirado aquel veto
    # (caso G9 de la revision independiente), el flujo llega hasta aqui y la
    # excepcion cancelaria toda la proyeccion: exactamente el acoplamiento que se
    # esta separando. Se captura, se registra el motivo y se continua SIN banda.
    #
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). El motivo se registra como
    # DIAGNOSTICO INTERNO y deja de entrar en `factibilidad["advertencias"]`, que
    # es el canal publicado. Anunciar «no se construye el intervalo de predicción»
    # en la interfaz y en los informes describe la ausencia de un objeto que esta
    # version no entrega en ningún caso: le dice al lector que le falta algo que
    # nunca iba a recibir, y de paso publica el mínimo de ventanas de la banda
    # como si condicionara el resultado. Lo que sí necesita saber -cuántas
    # ventanas fuera de muestra sostienen el horizonte- lo dice
    # `_texto_evidencia_oos`, con el número y sin vocabulario de intervalo.
    diagnostico_intervalo_no_publicado: list[str] = []
    intervalo_no_construible = ""
    try:
        intervalos = _intervalos_prediccion(
            y_futuro=y_futuro,
            errores_por_horizonte=errores_oos_modelo,
            factores_calendario=factores_calendario,
        )
    except ValueError as exc:
        intervalos = []
        intervalo_no_construible = str(exc)
        diagnostico_intervalo_no_publicado.append(
            "No se construye intervalo de predicción: " + intervalo_no_construible
        )
    # RA-01: la verificabilidad se mide sobre el paso que realmente se entrega,
    # que es el ultimo de la trayectoria proyectada, no sobre el conjunto.
    # Las observaciones llevan origen, fecha objetivo, pronostico y real: sin
    # ellas la evaluacion por origen movil no podria declarar QUE se evaluo.
    observaciones_oos_modelo = _observaciones_por_horizonte(
        backtesting_comparativo,
        str(modelo.get("nombre", "")),
        tuple(range(1, int(horizonte_permitido) + 1)),
    )
    cobertura_empirica = _cobertura_empirica_intervalos(
        errores_oos_modelo,
        paso_exacto=int(horizonte_permitido),
        observaciones_por_horizonte=observaciones_oos_modelo,
    )
    # P0-C / ESTRATEGIA C2, 15-08-2026. Las advertencias de COBERTURA dejan de
    # entrar en `factibilidad["advertencias"]`, que es el canal publicado: de ahi
    # viajan a la interfaz, a los informes y a la columna `advertencias` del CSV.
    # Todas describen el desempeno de una banda que esta version ya no entrega.
    # No se borran: se recogen aparte, como diagnostico, para que la decision de
    # retirarlas siga siendo auditable.
    # 17-08-2026: un solo canal interno para TODO lo que caracteriza la banda
    # retirada -construcción, ancho y cobertura-, declarado antes del primer
    # productor para que ninguno quede fuera por orden de aparición.
    diagnostico_intervalo_no_publicado.extend(cobertura_empirica.get("advertencias") or [])
    # Decision autorizada sobre H-05: el calculo del intervalo no cambia; lo que
    # cambia es como se comunica y hasta donde se permite usarlo.
    # El estado de la banda del paso que se entrega -el ultimo de la
    # trayectoria- decide si hay banda que tipificar (V-C, `banda_no_calculable`).
    clasificacion_intervalo = clasificar_intervalo_por_cobertura(
        cobertura_empirica,
        errores_oos_modelo,
        estado_banda_paso=(
            str(intervalos[-1].get("estado_banda") or BANDA_VALIDA) if intervalos else None
        ),
    )
    if clasificacion_intervalo.get("advertencia"):
        diagnostico_intervalo_no_publicado.append(str(clasificacion_intervalo["advertencia"]))
    # G-2: la advertencia de consistencia entre horizontes sigue calculandose,
    # localizada (horizonte y numero de contrastes) y viajando en
    # `clasificacion_intervalo`. Deja de PUBLICARSE porque enuncia la cobertura
    # observada de la banda retirada. La regla que G-2 fijo -que el estado del
    # horizonte solicitado lo decide su propia evidencia y no el minimo global-
    # no se toca: vive en `_clasificar_evidencia_horizonte`, no en este canal.
    if clasificacion_intervalo.get("advertencia_consistencia"):
        diagnostico_intervalo_no_publicado.append(str(clasificacion_intervalo["advertencia_consistencia"]))
    proyecciones_df = _construir_tabla_proyecciones(
        t_futuro=t_futuro,
        y_futuro=y_futuro,
        intervalos=intervalos,
        ultimo_observado=last_obs,
        anio_base=anio_base,
        modelo=model_name,
        confianza=factibilidad.get("nivel_confianza_metodologica", "medio"),
        advertencias=factibilidad.get("advertencias", []),
    )
    evaluacion_intervalos = _evaluar_intervalos_prediccion(proyecciones_df, horizonte=horizonte_permitido)
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Estas advertencias son las del
    # ANCHO de la banda: «La incertidumbre del intervalo 95% es excesiva para h=3
    # (ancho relativo máximo 50,8 %)». Publicaban dos cosas prohibidas a la vez:
    # el vocabulario de un intervalo retirado y, con el ancho relativo junto al
    # punto -que sí es público-, su ancho ABSOLUTO, es decir el semiancho de la
    # banda. Pasan al diagnóstico interno, como ya habían pasado las de cobertura.
    if evaluacion_intervalos.get("advertencias"):
        diagnostico_intervalo_no_publicado.extend(evaluacion_intervalos["advertencias"])
    stats = {
        "r2": metricas_ajuste.get("r2"),
        "r2_ajustado": metricas_ajuste.get("r2_ajustado"),
        "aic": metricas_ajuste.get("aic"),
        "aicc": metricas_ajuste.get("aicc"),
        "mae_ajuste": metricas_ajuste.get("mae"),
        "rmse_ajuste": metricas_ajuste.get("rmse"),
        "mape_ajuste": metricas_ajuste.get("mape"),
        "smape_ajuste": metricas_ajuste.get("smape"),
        "mase_ajuste": metricas_ajuste.get("mase"),
        "sesgo_medio_ajuste": metricas_ajuste.get("sesgo_medio"),
        "jb_p": diagnostico_residuos.get("jb_p"),
        "kurt_ex": diagnostico_residuos.get("kurt_ex"),
        "durbin_watson": diagnostico_residuos.get("durbin_watson"),
        "n": int(len(y_obs)),
        "width95": float(proyecciones_df["limite_superior"].iloc[-1] - proyecciones_df["limite_inferior"].iloc[-1]),
        "ancho_relativo_intervalo_max": evaluacion_intervalos.get("ancho_relativo_maximo"),
        "all_candidates": _candidatos_serializables(candidatos, backtesting_por_modelo),
        "ranking_backtesting": modelo.get("ranking_backtesting", {}),
        "modelos_evaluados": list(modelos_evaluados),
        "politica_modelos": politica_modelos,
        "descartes_modelos": modelo.get("descartes_modelos", []),
        "catalogo_modelos": catalogo_modelos,
        "parametros_modelo": modelo.get("parametros", {}),
    }

    justificacion_modelo = modelo.get("justificacion") or seleccionar_mejor_modelo(model_name, stats, backtesting)
    interpretacion_estadistica = generar_interpretacion_estadistica(
        validacion_serie=validacion_serie,
        analisis_serie=analisis_serie,
        diagnostico_residuos=diagnostico_residuos,
        backtesting=backtesting,
        estadisticas_modelo=stats,
    )

    return {
        "proyeccion_generada": True,
        "periodo_solicitado": periodo_solicitado,
        "periodo_proj": periodo_proj,
        "t_proj": int(t_permitido),
        "horizonte_solicitado": horizonte_solicitado,
        "horizonte_permitido": horizonte_permitido,
        "horizonte_info": horizonte_info,
        "model_name": model_name,
        "modelo_codigo": modelo.get("nombre"),
        # P0-G: el estado metodológico y los bloqueos vigentes viajan con el
        # resultado, de modo que interfaz, informes y CSV puedan decir lo que la
        # aplicación puede y no puede sostener.
        "estado_metodologico": estado_metodologico(True),
        "bloqueos_metodologicos": dict(BLOQUEOS_METODOLOGICOS_VIGENTES),
        # P0-C sigue abierto: la banda se calcula pero NO es un intervalo
        # institucional sustentado, y así debe publicarse.
        "intervalo_sustentado": False,
        "motivo_intervalo_no_sustentado": BLOQUEOS_METODOLOGICOS_VIGENTES["P0-C"],
        "evidencia_oos_provisional": True,
        "motivo_evidencia_provisional": BLOQUEOS_METODOLOGICOS_VIGENTES["P0-E"],
        "y_proj": float(y_futuro[-1]),
        "ci_lo": float(proyecciones_df["limite_inferior"].iloc[-1]),
        "ci_hi": float(proyecciones_df["limite_superior"].iloc[-1]),
        "ci80_lo": float(proyecciones_df["limite_inferior_80"].iloc[-1]),
        "ci80_hi": float(proyecciones_df["limite_superior_80"].iloc[-1]),
        "ci95_lo": float(proyecciones_df["limite_inferior_95"].iloc[-1]),
        "ci95_hi": float(proyecciones_df["limite_superior_95"].iloc[-1]),
        "factor_actualizacion": float(proyecciones_df["factor_actualizacion"].iloc[-1]),
        "variacion_acumulada": float(proyecciones_df["variacion_acumulada_pct"].iloc[-1]),
        "stats": stats,
        "t_obs": t_obs,
        "y_obs": y_obs,
        "y_fit_obs": y_fit_obs,
        "y_fit_full": y_fit_full,
        "t_full": t_full,
        "predict_func": modelo["predict"],
        "validacion_serie": validacion_serie,
        "analisis_serie": analisis_serie,
        "variables_derivadas": derivadas,
        "outliers": outliers,
        "factibilidad": factibilidad,
        "metricas_ajuste": metricas_ajuste,
        "diagnostico_residuos": diagnostico_residuos,
        "backtesting": backtesting,
        "backtesting_comparativo": backtesting_comparativo,
        "ajuste_calendario": trazabilidad_calendario,
        "cobertura_empirica": cobertura_empirica,
        "clasificacion_intervalo": clasificacion_intervalo,
        # P0-C / C2: advertencias de cobertura de la banda retirada. Se conservan
        # como diagnostico -no se borran- y NO se publican en ninguna salida.
        "diagnostico_cobertura_no_publicado": list(diagnostico_intervalo_no_publicado),
        # RA-01: bloque explicito del paso exacto solicitado. La cobertura minima
        # global viaja aparte, como informacion complementaria, y no sustituye la
        # verificabilidad de este paso.
        "verificabilidad_paso_exacto": {
            "paso_exacto": int(horizonte_permitido),
            "n_errores_oos": int(cobertura_empirica.get("n_errores_paso_exacto") or 0),
            "min_errores_exigidos": int(MIN_ERRORES_COBERTURA_EMPIRICA),
            "verificable": bool(cobertura_empirica.get("verificable_paso_exacto")),
            "cobertura_95": cobertura_empirica.get("cobertura_95_paso_exacto"),
            # D-Z1: `is not None`, para que un minimo global de 0,0 se publique
            # como 0,0 y no como ausencia de dato.
            "cobertura_95_minima_global": _numero_finito_o_none(
                cobertura_empirica.get("cobertura_95_minima")
            ),
            "clasificacion": clasificacion_intervalo.get("clasificacion"),
        },
        "proyecciones": proyecciones_df,
        "descartes_modelos": modelo.get("descartes_modelos", []),
        "politica_modelos": politica_modelos,
        "catalogo_modelos": catalogo_modelos,
        "parametros_modelo": modelo.get("parametros", {}),
        "salvaguarda_benchmark": salvaguarda_benchmark,
        "advertencias_categorizadas": _categorizar_advertencias(
            validacion_serie=validacion_serie,
            outliers=outliers,
            modelo=modelo,
            factibilidad=factibilidad,
            horizonte_info=horizonte_info,
            evaluacion_intervalos=evaluacion_intervalos,
        ),
        "justificacion_modelo": justificacion_modelo,
        "interpretacion_estadistica": interpretacion_estadistica,
        "explicacion": "Proyección generada dentro del horizonte estadísticamente permitido.",
    }


def _estructurar_resultado_horizontes(resultado: dict[str, Any], origen_horizonte: str) -> dict[str, Any]:
    """Añade los dos bloques públicos sin romper las claves históricas."""
    origen = "manual" if str(origen_horizonte).strip().lower() == "manual" else "predeterminado"
    info = dict(resultado.get("horizonte_info") or {})
    salvaguarda_info = info.get("salvaguarda_benchmark")
    resultado.setdefault(
        "salvaguarda_benchmark",
        salvaguarda_info if isinstance(salvaguarda_info, dict) else {"intentada": False, "activada": False},
    )
    solicitado = int(resultado.get("horizonte_solicitado") or info.get("horizonte_solicitado") or 0)
    evaluaciones = list(info.get("evaluaciones") or [])
    por_horizonte = {
        int(item.get("horizonte", 0) or 0): item
        for item in evaluaciones
        if int(item.get("horizonte", 0) or 0) > 0
    }
    evaluacion_solicitada = por_horizonte.get(solicitado, {})
    no_evaluados = list(info.get("horizontes_no_evaluados") or [])
    maximo_datos = int(info.get("horizonte_maximo_evaluable_por_datos") or 0)
    primer_no_viable = int(info.get("primer_horizonte_no_viable") or 0)
    tabla_horizontes = list(evaluaciones)
    tabla_horizontes.extend(
        {
            "horizonte": int(horizonte),
            "estado": "No evaluado",
            "decision": "No evaluado",
            "clasificacion": "no_evaluado",
            "permitido": False,
            "permitido_para_proyeccion_tecnica": False,
            "permitido_como_escenario": False,
            "no_recomendable": False,
            # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). RETIRADA la rama «No
            # evaluado después del primer horizonte no viable h=X»: presuponía que
            # un fallo cancela la evaluación de todo lo posterior, que es la
            # cascada retirada. Hoy la rejilla evalúa todos los horizontes con al
            # menos una ventana, de modo que un horizonte solo queda sin evaluar
            # cuando no existe su evidencia -causa (2)- o por alcance operativo.
            "razon_decision": (
                _texto_evidencia_oos(0)
                if maximo_datos and int(horizonte) > maximo_datos
                else "No evaluado: queda fuera del alcance operativo de entrada."
            ),
            "recomendacion": "No inferir validez para este horizonte.",
        }
        for horizonte in no_evaluados
    )
    tabla_horizontes.sort(key=lambda item: int(item.get("horizonte", 0) or 0))

    generado = bool(resultado.get("proyeccion_generada")) and int(resultado.get("horizonte_permitido") or 0) == solicitado
    tecnico = bool(evaluacion_solicitada.get("permitido_para_proyeccion_tecnica"))

    # Decision autorizada sobre H-05: una cobertura no verificable o por debajo
    # del umbral de advertencia degrada el horizonte a escenario. No se toca el
    # pronostico ni el ancho de la banda: solo deja de presentarse como
    # proyeccion tecnica principal.
    clasificacion_intervalo = resultado.get("clasificacion_intervalo") or {}
    degrada = bool(clasificacion_intervalo.get("degrada_a_escenario"))
    if degrada and tecnico:
        tecnico = False
        resultado["degradacion_por_cobertura"] = {
            "aplicada": True,
            "clasificacion": clasificacion_intervalo.get("clasificacion"),
            # La clave de decision acompana al identificador publicado: sin ella
            # el registro dice QUE banda se entrego, pero no POR QUE se degrado.
            "clasificacion_interna": clasificacion_intervalo.get("clasificacion_interna"),
            "cobertura_minima": clasificacion_intervalo.get("cobertura_minima"),
            "umbral_aplicado": clasificacion_intervalo.get("umbral_aplicado"),
            "motivo": clasificacion_intervalo.get("advertencia"),
        }
    else:
        resultado.setdefault("degradacion_por_cobertura", {"aplicada": False})

    # H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual).
    # Se retira la rama `estado == "escenario"`: con `degrada_a_escenario`
    # fijo en False en todo `clasificar_intervalo_por_cobertura` (P0-F) y
    # `permitido_como_escenario == permitido_para_proyeccion_tecnica` siempre
    # (mismo invariante que ya elimino la rama equivalente en
    # `_estado_global` y en el resumen por horizonte), la condicion
    # `escenario = (permitido_como_escenario or degrada) and not tecnico` es
    # `tecnico and not tecnico`: nunca True. El estado y la advertencia de
    # "escenario estadistico de alta incertidumbre" que dependian de ella no
    # llegaban a publicarse por esta via.
    if generado and tecnico:
        estado = "proyeccion_tecnica"
        accion = "permitir"
    else:
        estado = "no_admisible"
        accion = "negar"

    razones = _deduplicar_local(
        [
            evaluacion_solicitada.get("razon_decision"),
            evaluacion_solicitada.get("motivo"),
            evaluacion_solicitada.get("mensaje"),
            evaluacion_solicitada.get("recomendacion"),
            *((resultado.get("factibilidad") or {}).get("razones_tecnicas") or []),
            *(info.get("razones") or []),
        ]
    )
    maximo_admisible = int(
        info.get("horizonte_maximo_admisible")
        or info.get("horizonte_maximo_permitido")
        or 0
    )
    maximo_datos_traza = int((info.get("trazabilidad") or {}).get("horizonte_maximo_evaluable_por_datos") or 0)
    # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). LA RAMA QUE FALTABA. Todo el
    # encadenamiento que sigue redacta el motivo de una NEGATIVA, y se ejecutaba
    # tambien cuando el horizonte pedido SI se entregaba. Con h1 permitido, h2 no
    # viable y h3 permitido, la salida decia a la vez:
    #
    #     proyeccion_generada = True, estado = proyeccion_tecnica, accion = permitir
    #     razon_principal = «La evidencia estadistica se corta en h=2 ... Por eso no
    #                        puede sostenerse un horizonte de 3 meses. Use hasta 3.»
    #
    # Tres afirmaciones falsas en una linea: la evidencia no se corta -h3 tiene la
    # suya-, h3 si se sostiene -se esta entregando- y «use hasta 3» contradice al
    # «no puede sostenerse 3» de la frase anterior. Codex lo tipifico como
    # regresion semantica productiva, y es el nucleo del residual: la conducta era
    # correcta y el mensaje la negaba.
    #
    # El hueco NO se oculta ni se interpola: se nombra como hueco, con su causa, y
    # se dice que el horizonte pedido se evalua con su propia muestra de errores,
    # que es el contrato que P0-H fijo. El horizonte fallido sigue marcado como no
    # permitido en `estado_por_horizonte` y en `primer_horizonte_no_viable`.
    huecos = sorted(
        int(item.get("horizonte", 0) or 0)
        for item in tabla_horizontes
        if 0 < int(item.get("horizonte", 0) or 0) < solicitado
        and not item.get("permitido_para_proyeccion_tecnica")
        and not item.get("permitido_como_escenario")
    )
    if estado != "no_admisible":
        entrega = (
            f"El horizonte solicitado (h={solicitado}) se entrega con su propia evidencia "
            f"fuera de muestra"
        )
        if huecos:
            lista = ", ".join(f"h={x}" for x in huecos)
            detalle_hueco = next(
                (
                    str(item.get("razon_decision") or item.get("motivo") or item.get("mensaje") or "").strip()
                    for item in tabla_horizontes
                    if int(item.get("horizonte", 0) or 0) == huecos[0]
                ),
                "",
            )
            razon_principal = (
                f"{entrega}. La trayectoria tiene {'un hueco' if len(huecos) == 1 else 'huecos'} "
                f"en {lista}: {'ese horizonte no está disponible' if len(huecos) == 1 else 'esos horizontes no están disponibles'}"
                + (f" ({detalle_hueco})" if detalle_hueco else "")
                + f". No se interpola ningún valor para {lista}. Cada horizonte se evalúa con su "
                "propia muestra de errores de origen móvil, de modo que el hueco no invalida los "
                "horizontes posteriores."
            )
        else:
            razon_principal = f"{entrega}."
    elif solicitado in no_evaluados and maximo_datos_traza and solicitado > maximo_datos_traza:
        # Caso frecuente en series cortas: no se bloquea por mal desempeño sino
        # porque la serie no alcanza para abrir ventanas de validación.
        razon_principal = (
            f"No hay ventanas de validación suficientes para evaluar h={solicitado}: "
            f"con {(info.get('trazabilidad') or {}).get('numero_observaciones', 'las')} observaciones "
            f"y un entrenamiento inicial de {(info.get('trazabilidad') or {}).get('entrenamiento_inicial', 'N')}, "
            f"el máximo evaluable es h={maximo_datos_traza}. "
            "Seleccione un horizonte menor o amplíe la serie histórica."
        )
    elif primer_no_viable and solicitado >= primer_no_viable:
        # El horizonte pedido NO se entrega y hay al menos un horizonte anterior no
        # viable. Se explica el fallo del horizonte pedido y se nombra el hueco.
        #
        # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). RETIRADO «La evidencia
        # estadística se corta en h=X. Por eso no puede sostenerse un horizonte de
        # N meses». Presuponía el prefijo: que un fallo en h=X explique el estado
        # de todo h>X es exactamente la cascada que P0-H retiró como criterio, y la
        # frase la reintroducía en la salida pública aunque el cálculo ya no la
        # aplicara. Peor: el «Use hasta M» final podía traer un M mayor que X,
        # contradiciendo la misma frase.
        #
        # Ahora el motivo es el del horizonte SOLICITADO -su propia evidencia-, y
        # el hueco anterior se menciona como lo que es: otro horizonte sin
        # evidencia, no la causa de este.
        detalle = next(
            (
                item
                for item in tabla_horizontes
                if int(item.get("horizonte", 0) or 0) == int(solicitado)
            ),
            {},
        )
        motivo = str(
            detalle.get("razon_decision") or detalle.get("motivo") or detalle.get("mensaje") or ""
        ).strip()
        maximo_admisible_info = int(
            info.get("horizonte_maximo_admisible") or info.get("horizonte_maximo_permitido") or 0
        )
        razon_principal = (
            f"El horizonte solicitado (h={solicitado}) no está disponible"
            + (f": {motivo}" if motivo else " con la evidencia fuera de muestra de ese horizonte.")
            + (
                f" Otros horizontes tampoco lo están ({', '.join(f'h={x}' for x in huecos)}); "
                "cada uno se evalúa por separado, de modo que ninguno explica el estado de los demás."
                if huecos
                else ""
            )
            + (
                f" El mayor horizonte disponible en esta serie es h={maximo_admisible_info}."
                if maximo_admisible_info
                else " Ningún horizonte de esta serie reúne evidencia fuera de muestra."
            )
        )
    elif maximo_admisible and solicitado > maximo_admisible:
        razon_principal = (
            f"El horizonte solicitado ({solicitado} meses) supera el máximo admisible "
            f"({maximo_admisible} meses) según la evidencia por horizonte."
        )
    elif solicitado in no_evaluados:
        razon_principal = "No evaluado por falta de evidencia fuera de muestra suficiente."
    elif razones:
        razon_principal = razones[0]
    else:
        razon_principal = (
            (resultado.get("factibilidad") or {}).get("explicacion")
            or resultado.get("explicacion")
            or "El horizonte solicitado no tiene respaldo estadístico suficiente."
        )
    if solicitado in no_evaluados:
        razones = _deduplicar_local(razones + [_texto_evidencia_oos(0)])
    razones = _deduplicar_local([razon_principal] + razones)

    # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). Disponibilidad POR PASO de la
    # trayectoria, en una sola columna y en un solo sitio.
    #
    # La trayectoria se calcula para 1..H de forma continua -el modelo evalúa todos
    # los pasos-, de modo que un horizonte no disponible en el medio TIENE un valor
    # en la tabla. Dibujarlo unido a sus vecinos hace que la gráfica afirme
    # visualmente un valor para un mes que la aplicación declara no disponible: el
    # lector no ve el hueco. Con esta columna, la gráfica del informe y la de la
    # interfaz cortan la línea en el mismo punto sin duplicar la regla, y las tablas
    # pueden marcar la fila.
    #
    # El valor NO se borra ni se interpola: sigue en `indice_proyectado`, porque el
    # cálculo existe y ocultarlo sería tan falso como unirlo. Lo que se publica es
    # que ese paso no está disponible.
    tabla_proyecciones = resultado.get("proyecciones")
    if isinstance(tabla_proyecciones, pd.DataFrame) and not tabla_proyecciones.empty:
        disponibles = [
            bool(
                (por_horizonte.get(paso, {}) or {}).get("permitido_para_proyeccion_tecnica")
                or (por_horizonte.get(paso, {}) or {}).get("permitido_como_escenario")
            )
            # Un paso sin evaluación propia no se declara no disponible: no se
            # evaluó, que es distinto. Solo se marca el hueco cuando existe una
            # evaluación y dice que no.
            if paso in por_horizonte
            else True
            for paso in range(1, len(tabla_proyecciones) + 1)
        ]
        tabla_proyecciones["horizonte_disponible"] = disponibles

    resultado_solicitado = {
        "horizonte_solicitado": solicitado,
        "origen_horizonte": origen,
        "estado": estado,
        "accion": accion,
        "proyeccion_generada": generado,
        "indice_proyectado": _numero_finito_o_none(resultado.get("y_proj")) if generado else None,
        "periodo_proyectado": resultado.get("periodo_proj") if generado else None,
        "modelo_aplicado": resultado.get("model_name") if generado else None,
        "ic80": [
            _numero_finito_o_none(resultado.get("ci80_lo")),
            _numero_finito_o_none(resultado.get("ci80_hi")),
        ] if generado else None,
        "ic95": [
            _numero_finito_o_none(resultado.get("ci95_lo", resultado.get("ci_lo"))),
            _numero_finito_o_none(resultado.get("ci95_hi", resultado.get("ci_hi"))),
        ] if generado else None,
        "nivel_confianza": (
            evaluacion_solicitada.get("confianza")
            or (resultado.get("factibilidad") or {}).get("nivel_confianza_metodologica")
            or "no recomendable"
        ),
        "razon_principal": str(razon_principal),
        "razones_tecnicas": razones,
    }

    analisis = {
        **info,
        "horizonte_solicitado": solicitado,
        "tabla_horizontes": tabla_horizontes,
        "evaluaciones": evaluaciones,
    }
    trazabilidad = dict(analisis.get("trazabilidad") or {})
    trazabilidad.update(
        {
            "horizonte_solicitado": solicitado,
            "origen_horizonte": origen,
        }
    )
    analisis["trazabilidad"] = trazabilidad
    resultado["origen_horizonte"] = origen
    resultado["resultado_horizonte_solicitado"] = resultado_solicitado
    resultado["analisis_horizontes_completo"] = analisis
    resultado["horizonte_info"] = analisis
    return resultado


def _numero_finito_o_none(valor: Any) -> float | None:
    numero = _numero_finito(valor)
    return float(numero) if np.isfinite(numero) else None


def ventanas_oos_disponibles(n_obs: int, horizonte: int, primer_origen: int | None = None) -> int:
    """``W = n - N0 - h + 1``: cuántos errores OOS existen para ese horizonte.

    HGRID, 17-08-2026 (V-CODEX-R3, residual 2). Es la MISMA cuenta que hace el
    bucle de `ejecutar_backtesting`: recorre ``range(N0, n - h + 1)``, cuya
    longitud es exactamente ``n - N0 - h + 1``. Se expone aquí para que la rejilla
    y el backtesting no puedan discrepar (REQ 24 y REQ 25) y para poder
    comprobarlo con una prueba conductual en los bordes.

    Devuelve ``0`` cuando la cuenta es negativa: no hay «menos de cero ventanas»,
    hay ninguna. **Esto es una condición de EXISTENCIA, no de calidad**: ``W>=1``
    dice que hay al menos un error fuera de muestra, no que el horizonte esté
    validado. El vocabulario correspondiente está en `_texto_evidencia_oos`.

    ``N0`` es el primer origen vigente, provisional (P0-E, limitación declarada).

    Se replican las DOS salidas tempranas de `ejecutar_backtesting`, porque sin
    ellas la cuenta no coincide con el bucle en los bordes cortos:

    1. ``n < N0 + 1`` -> el catálogo no llega a estimarse y el backtesting
       devuelve cero ventanas ANTES de acotar el origen. Sin esta guarda, el
       acotado de disponibilidad ``N0 <= n-1`` haría que n=2 pareciera tener una
       ventana con un origen de una sola observación que nunca se usa.
    2. ``N0 + h > n`` -> el objetivo del último corte cae fuera de la serie.
    """
    n = max(0, int(n_obs or 0))
    h = max(1, int(horizonte or 1))
    catalogo = _catalogo_activo()
    if primer_origen is None and n < observaciones_minimas_catalogo(catalogo) + 1:
        return 0
    origen = _entrenamiento_inicial(n, primer_origen, catalogo)
    if origen + h > n:
        return 0
    return max(0, n - origen - h + 1)


#: HGRID, 17-08-2026 (V-CODEX-R3, residual 2). Tramos con que se comunica cuánta
#: evidencia fuera de muestra reúne un horizonte. NINGUNO es un umbral de
#: aceptación: los tres describen el mismo hecho -el tamaño de la muestra de
#: errores- y ninguno niega ni degrada nada. El corte 3 procede de
#: `MIN_ITERACIONES_WF_ESCENARIO` y se conserva SOLO como frontera descriptiva
#: entre «muy limitada» y «disponible»; convertirlo en requisito volvería a
#: reintroducir el piso que P0-G retiró.
#:
#: Vocabulario PROHIBIDO en estos textos: «validado», «validado por datos»,
#: «suficiente», «robusto», «certificado». Una ventana es una ventana.
TRAMO_OOS_SIN_EVIDENCIA = "sin_evidencia_oos"
TRAMO_OOS_MUY_LIMITADA = "evidencia_oos_muy_limitada"
TRAMO_OOS_DISPONIBLE = "evidencia_oos_disponible"


def tramo_evidencia_oos(ventanas: Any) -> str:
    """Clasifica el tamaño de la muestra de errores OOS en uno de los tres tramos."""
    try:
        w = int(ventanas or 0)
    except (TypeError, ValueError):
        w = 0
    if w <= 0:
        return TRAMO_OOS_SIN_EVIDENCIA
    if w < MIN_ITERACIONES_WF_ESCENARIO:
        return TRAMO_OOS_MUY_LIMITADA
    return TRAMO_OOS_DISPONIBLE


def _texto_evidencia_oos(ventanas: Any) -> str:
    """Redacción única de los tres tramos. Ver `TRAMO_OOS_SIN_EVIDENCIA`."""
    try:
        w = int(ventanas or 0)
    except (TypeError, ValueError):
        w = 0
    if w <= 0:
        return "Sin evidencia fuera de muestra disponible para este horizonte bajo el diseño vigente."
    if w < MIN_ITERACIONES_WF_ESCENARIO:
        return f"Evidencia fuera de muestra disponible pero muy limitada (n={w})."
    return f"Evidencia fuera de muestra disponible (n={w})."


def _limites_auditoria_horizontes(n_obs: int) -> tuple[int, int, int, int]:
    """Devuelve los límites de auditoría por disponibilidad de ventanas OOS.

    Se distinguen dos techos porque no es lo mismo "no se pudo medir" que
    "se midió y salió mal":

    * ``maximo_evidencia_no_limitada``: último horizonte cuyo número de ventanas
      alcanza el tramo descriptivo superior (``MIN_ITERACIONES_BACKTESTING``).
      **No certifica nada**: ver la nota de vocabulario más abajo.
    * ``maximo_por_datos``: último horizonte con AL MENOS UNA ventana, es decir el
      último para el que existe algún error fuera de muestra.

    Devuelve ``(entrenamiento_inicial, maximo_por_datos, limite, maximo_evidencia_no_limitada)``.

    P0-E, 12-08-2026: el primer origen ya no se recalcula aqui. Hasta esta fecha
    este modulo llevaba una **segunda copia** de la formula -sin el acotado que
    si tenia `backtesting`-, de modo que con `n < 19` la rejilla se construia con
    un origen que el backtesting no usaba. Ahora ambos llaman a la misma
    funcion: una sola definicion (REQ 24 y REQ 25).

    HGRID, 17-08-2026 (V-CODEX-R3, residual 2). RETIRADO el ``max(1, ...)`` que
    forzaba un piso de un horizonte. Con ``N0=6`` y ``n=2..6`` la cuenta da
    ``W<=0`` -cero ventanas, y el backtesting devuelve cero: se comprobo en los
    bordes n=2..8 x h=1..3-, pero la rejilla publicaba ``[1]`` y la aplicacion
    anunciaba h=1 como evaluable. Es decir: afirmaba evidencia fuera de muestra
    donde no existe ninguna, que es lo contrario de lo que la cota deriva.

    El cero se publica tal cual. No es un bloqueo elegido: es la inexistencia del
    dato -causa (2) de las cuatro admitidas-, y se comunica con
    `_texto_evidencia_oos`.

    La cuenta se delega en `ventanas_oos_disponibles`, que replica las salidas
    tempranas del backtesting. Reproducirla aquí con la fórmula suelta era
    justamente el origen del desajuste: el acotado de disponibilidad
    ``N0 <= n-1`` daba un origen que el backtesting nunca usa en series cortas.
    """
    n = max(0, int(n_obs or 0))
    entrenamiento_inicial = _entrenamiento_inicial(n, None, _catalogo_activo())

    def _maximo_con(min_ventanas: int) -> int:
        """Mayor horizonte con al menos ``min_ventanas`` errores fuera de muestra."""
        objetivo = max(1, int(min_ventanas))
        for h in range(n, 0, -1):
            if ventanas_oos_disponibles(n, h) >= objetivo:
                return h
        return 0

    maximo_validado = _maximo_con(MIN_ITERACIONES_BACKTESTING)
    # P0-G, 16-08-2026 (V-CODEX-3). La rejilla se acotaba con
    # `MIN_ITERACIONES_WF_ESCENARIO = 3`, un minimo cuya propia ficha declara que
    # procede de poder estimar la dispersion y verificar la cobertura del
    # INTERVALO. Es decir: un requisito de la BANDA recortaba los horizontes en
    # que se puede entregar el PUNTO. Codex lo demostro end-to-end: con n=8 y
    # h=2 la rejilla quedaba en (1,), la reconciliacion negaba la entrega y
    # `proyeccion_generada` era False, aunque el modelo seleccionado producia un
    # punto finito para h=2.
    #
    # El limite pasa a ser la COTA ARITMETICA de la evidencia: para evaluar un
    # horizonte h con ventana expansiva hacen falta `n - N0 - h + 1 >= 1`
    # ventanas, luego `h <= n - N0`. Por debajo de una ventana no hay ningun
    # error fuera de muestra: no es un umbral elegido, es la inexistencia del
    # dato. Con una sola ventana ya existe RMSE calculable.
    #
    # `MIN_ITERACIONES_WF_ESCENARIO` NO desaparece: sigue siendo el corte
    # DESCRIPTIVO con que se comunica cuanta evidencia sostiene el horizonte.
    # Deja de recortar la rejilla y deja de negar la entrega.
    maximo_por_datos = _maximo_con(1)
    # P0-H, 12-08-2026: RETIRADO el tope `min(HORIZONTE_MAXIMO_AUDITORIA, ...)`.
    #
    # `HORIZONTE_MAXIMO_AUDITORIA = 30` no tenia fuente y habia pasado de inerte
    # a VINCULANTE: con el primer origen anterior el limite lo ponia el dato
    # (65-39-3+1 = 24 < 30), y al cambiar ese origen el dato paso a permitir 57,
    # de modo que la constante se convirtio en el UNICO decisor efectivo del
    # horizonte publicado. Medido: hmax = 30 en las diez series del anexo.
    #
    # La rejilla la fija ahora la DISPONIBILIDAD DE DATOS. El alcance de
    # producto sigue acotado por `HORIZONTE_MAXIMO_OPERATIVO` en la validacion
    # de la ENTRADA, que es donde corresponde y no interviene en ningun calculo.
    return (
        entrenamiento_inicial,
        maximo_por_datos,
        maximo_por_datos,
        maximo_validado,
    )


def _metadatos_auditoria_horizontes(
    serie_trabajo: pd.DataFrame,
    horizonte_solicitado: int,
    origen_horizonte: str,
) -> dict[str, Any]:
    """Firma la entrada y documenta los límites que hacen reproducible la auditoría."""
    serie_firma = serie_trabajo[["Periodo", "Indice"]].copy()
    firma = hashlib.sha256(
        pd.util.hash_pandas_object(serie_firma, index=False).to_numpy().tobytes()
    ).hexdigest()
    entrenamiento, maximo_datos, limite, maximo_validado = _limites_auditoria_horizontes(len(serie_firma))
    n_obs = int(len(serie_firma))
    ventanas_solicitado = ventanas_oos_disponibles(n_obs, int(horizonte_solicitado))
    return {
        "firma_serie_sha256": firma,
        "fecha_inicial_serie": str(serie_firma["Periodo"].iloc[0]) if not serie_firma.empty else "",
        "fecha_final_serie": str(serie_firma["Periodo"].iloc[-1]) if not serie_firma.empty else "",
        "numero_observaciones": n_obs,
        "horizonte_solicitado": int(horizonte_solicitado),
        "origen_horizonte": str(origen_horizonte),
        # P0-H: ya no hay tope configurado; la busqueda la fija el dato.
        "horizonte_maximo_busqueda_configurado": int(maximo_datos),
        "horizonte_maximo_evaluable_por_datos": int(maximo_datos),
        # HGRID, 17-08-2026 (V-CODEX-R3, residual 2). RENOMBRADO desde
        # `horizonte_maximo_validado_por_datos`. Aquel nombre convertia una cota de
        # EXISTENCIA en una afirmacion de VALIDACION: con n=7 la aplicacion
        # publicaba a la vez «horizonte maximo validado por datos: 1» y «ventanas
        # minimas requeridas: 6», teniendo UNA sola ventana. Ninguna fuente
        # sustenta llamar validado a un horizonte por tener una observacion fuera
        # de muestra, y el numero de ventanas exigido no es un requisito: es el
        # tramo descriptivo superior. El campo se conserva porque el dato -hasta
        # donde la muestra de errores deja de ser muy limitada- es informacion
        # legitima; lo que se retira es la palabra.
        "horizonte_maximo_evidencia_oos_no_limitada": int(maximo_validado),
        "horizonte_maximo_auditoria": int(limite),
        "entrenamiento_inicial": int(entrenamiento),
        # RENOMBRADAS: no son requisitos que haya que cumplir, son las fronteras de
        # los tres tramos con que se comunica el tamano de la muestra de errores.
        "ventanas_tramo_evidencia_disponible": int(MIN_ITERACIONES_WF_ESCENARIO),
        "ventanas_tramo_evidencia_no_limitada": int(MIN_ITERACIONES_BACKTESTING),
        # Cuenta y vocabulario del horizonte que se pidio, para que la salida no
        # obligue a reconstruir `W` desde n y N0.
        "ventanas_oos_horizonte_solicitado": int(ventanas_solicitado),
        "tramo_evidencia_oos_horizonte_solicitado": tramo_evidencia_oos(ventanas_solicitado),
        "evidencia_oos_horizonte_solicitado": _texto_evidencia_oos(ventanas_solicitado),
        "formula_ventanas_oos": "W = n - N0 - h + 1; existe evidencia OOS si W >= 1, luego h <= n - N0",
        "primer_origen_provisional": True,
        "version_criterios": VERSION_CRITERIOS_HORIZONTE,
        "timestamp_ejecucion_utc": datetime.now(timezone.utc).isoformat(),
    }


def _numero_parametros_modelo(nombre_modelo: str) -> int:
    """Número aproximado de parámetros para AIC/R2 ajustado."""
    nombre = nombre_modelo.lower()
    if "polin" in nombre:
        return 3
    return 2


def _horizontes_evaluacion(horizonte_solicitado: int, n_obs: int) -> tuple[int, ...]:
    """Horizontes a validar con evidencia temporal mensual.

    Las opciones 1, 3, 6, 12 y 18 son atajos operativos de UI. Para decidir
    factibilidad estadística se evalua una grilla mensual continua hasta el
    mayor horizonte defendible con ventanas walk-forward suficientes.
    """
    # ponytail: el horizonte pedido no participa; la serie y las ventanas OOS fijan la auditoría.
    _ = horizonte_solicitado
    _, _, limite, _ = _limites_auditoria_horizontes(n_obs)
    return tuple(range(1, int(limite) + 1))


def _modelos_para_analisis(
    serie_trabajo: pd.DataFrame,
    horizonte_solicitado: int,
    validacion_serie: dict,
    outliers: list[dict],
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Catalogo de candidatos: ELEGIBILIDAD POR ESTIMABILIDAD Y SUSTENTO.

    AUDITORIA 09-08-2026, P0-B. Hasta esta fecha el catalogo lo gobernaban siete
    literales sin ninguna fuente -`horizonte>=7`, `volatilidad>0.035`,
    `n_obs>=48`, `MIN_OBS_NIVEL_2=24`, `volatilidad>0.05`, `horizonte<=6 and
    n_obs>=24` y `MIN_OBS_HUBER=8`- que decidian QUE MODELOS COMPETIAN y por
    tanto cual podia ganar. Los requisitos metodologicos del proyecto prohiben
    que un literal sin sustento decida un resultado.

    Se sustituyen por dos criterios, ambos admisibles:

    1. ESTIMABILIDAD MATEMATICA. Un modelo compite si puede ajustarse con los
       datos disponibles. No hace falta ninguna puerta nueva: cada modelo ya
       declara su propio requisito y lo hace cumplir levantando excepcion
       -`n>=2` global, `y>0` para las transformaciones logaritmicas, `n>=4` y
       tres variaciones finitas para los modelos de variacion-, y
       `ajustar_modelos_candidatos` la captura. La derivacion vive donde debe:
       en el modelo.

    2. SUSTENTO DE SUS PARAMETROS PROPIOS. Un modelo cuyo parametro no tiene
       fuente no puede decidir un resultado publicado. `promedio_movil` y
       `variacion_reciente` llevan una ventana de 6 periodos SIN SUSTENTO, de
       modo que quedan fuera por esa razon metodologica -no por un filtro
       arbitrario- y volveran a competir en cuanto la ventana se estime o se
       sustente. Hoy ya estaban excluidos de hecho, asi que la exclusion no
       cambia ningun resultado: lo que cambia es que pasa a tener una razon.

    Medicion previa (10 series, catalogo completo de 12 modelos): la muestra
    comun se mantiene igual a la union -perdida 0,00 %-, C-SEL-001 no devuelve
    `None` ninguna vez y NINGUN ganador cambia. El unico efecto real es que
    Huber, que era estimable en las diez series, deja de excluirse en dos.
    """
    n_obs = int(validacion_serie.get("observaciones", len(serie_trabajo)))
    # HGRID, 17-08-2026 (V-CODEX-R3, residual 2). La rejilla puede quedar VACIA:
    # con `n <= N0` ningun horizonte tiene una sola ventana fuera de muestra, y
    # desde que se retiro el piso `max(1, ...)` eso se publica como cero en vez de
    # anunciar un h=1 inexistente. Aqui se indexaba `[-1]` sin comprobar y una
    # serie de dos observaciones levantaba `IndexError` en vez de bloquear con su
    # razon. El valor es puramente descriptivo -viaja en `horizonte_auditoria` y
    # no elige ningun modelo-, de modo que un cero es su lectura correcta:
    # ningun horizonte auditable.
    rejilla = _horizontes_evaluacion(horizonte_solicitado, n_obs)
    horizonte = rejilla[-1] if rejilla else 0
    indices = pd.to_numeric(serie_trabajo.get("Indice", pd.Series(dtype=float)), errors="coerce")
    variacion = indices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    volatilidad = float(variacion.std(ddof=1)) if len(variacion) > 2 else 0.0
    hay_outliers_relevantes = any(
        str(item.get("severidad", "")).lower() == "posible_atipico" for item in outliers
    )

    modelos_unicos = tuple(
        m for m in MODELOS_INTERPRETABLES if m not in MODELOS_PARAMETRO_SIN_SUSTENTO
    )
    return modelos_unicos, {
        "modelos_evaluados": list(modelos_unicos),
        "criterio_elegibilidad": (
            "Estimabilidad matematica del modelo con los datos disponibles. Cada modelo "
            "declara su propio dominio y su minimo de observaciones y los hace cumplir; "
            "un modelo que no puede ajustarse queda excluido con su error registrado."
        ),
        "modelos_excluidos_por_parametro_sin_sustento": sorted(MODELOS_PARAMETRO_SIN_SUSTENTO),
        "motivo_exclusion": (
            "ventana de 6 periodos sin fuente identificada; un parametro sin sustento no "
            "puede decidir un resultado publicado"
        ),
        "razones": [
            "Catalogo por estimabilidad: compiten todos los modelos ajustables cuyos "
            "parametros esten estimados de los datos o sustentados por fuente.",
        ],
        # Se conservan como DESCRIPTIVOS: se publican en la trazabilidad pero ya no
        # gobiernan el catalogo.
        "horizonte_auditoria": horizonte,
        "observaciones": n_obs,
        "volatilidad_mensual": volatilidad,
        "outliers_relevantes": hay_outliers_relevantes,
    }


def _catalogo_modelos_reporte(
    modelos_evaluados: tuple[str, ...] | list[str],
    candidatos: list[dict],
    backtesting_por_modelo: dict[str, dict],
    modelo_seleccionado: dict[str, Any] | None,
    horizonte: int | None,
    serie_trabajo: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Resume modelos ejecutados, no ejecutados y descartados para trazabilidad."""
    evaluados = set(modelos_evaluados)
    candidatos_por_nombre = {c.get("nombre", c.get("name")): c for c in candidatos}
    seleccionado = (modelo_seleccionado or {}).get("nombre")
    descartes = {
        item.get("nombre"): "; ".join(str(r) for r in item.get("razones", []) if r)
        for item in (modelo_seleccionado or {}).get("descartes_modelos", []) or []
    }
    indices = pd.to_numeric(serie_trabajo.get("Indice", pd.Series(dtype=float)), errors="coerce")
    positivos = bool((indices > 0).all()) if len(indices) else False
    filas: list[dict[str, Any]] = []
    for nombre, (visible, tipo, motivo) in CATALOGO_MODELOS_CANDIDATOS.items():
        candidato = candidatos_por_nombre.get(nombre)
        bt = backtesting_por_modelo.get(nombre, {}) if backtesting_por_modelo else {}
        metricas = bt.get("metricas") or {}
        ejecutado = bool(candidato and "predict" in candidato and nombre in evaluados and bt.get("ejecutado", False))
        if nombre == seleccionado:
            estado = "Seleccionado"
            razon = _razon_modelo_seleccionado(nombre, modelo_seleccionado or {}, backtesting_por_modelo)
        elif ejecutado:
            estado = "Descartado"
            razon = descartes.get(nombre) or _razon_descarte_comparativa(nombre, seleccionado, backtesting_por_modelo)
        else:
            estado = "No ejecutado"
            razon = _razon_modelo_no_ejecutado(nombre, evaluados, candidato, positivos)
        filas.append(
            {
                "modelo": visible,
                "codigo": nombre,
                "tipo": tipo,
                "ejecutado": "Si" if ejecutado else "No",
                "motivo_inclusion": motivo,
                "horizonte": int(horizonte or 0) if ejecutado else "",
                # RA-05: fuente unica de metricas. Las seis salen del mismo
                # diccionario de backtesting que alimenta la seccion de
                # metricas del modelo aplicado, para que ninguna tabla pueda
                # declarar «no disponible» lo que el texto vecino si publica.
                "rmse": metricas.get("rmse"),
                "mae": metricas.get("mae"),
                "mape": metricas.get("mape"),
                "smape": metricas.get("smape"),
                "mase": metricas.get("mase"),
                "sesgo_medio": metricas.get("sesgo_medio"),
                "estado": estado,
                "razon": razon,
            }
        )
    return filas


def _razon_modelo_no_ejecutado(nombre: str, evaluados: set[str], candidato: dict | None, positivos: bool) -> str:
    if candidato and candidato.get("error"):
        return str(candidato["error"])
    if nombre == "exponencial_log_lineal" and not positivos:
        return "No ejecutado por valores no positivos en la serie."
    if nombre == "log_variacion" and not positivos:
        return "No ejecutado porque la log-variación requiere índices positivos."
    if nombre == "huber":
        return "No ejecutado porque no se detectaron outliers relevantes que justificaran regresion robusta."
    if nombre not in evaluados:
        return "No ejecutado porque el modo progresivo no lo requirio para este horizonte."
    return "No ejecutado por falla numérica o backtesting insuficiente."


def _razon_descarte_comparativa(nombre: str, seleccionado: str | None, backtesting_por_modelo: dict[str, dict]) -> str:
    if not seleccionado or nombre == seleccionado:
        return "Modelo seleccionado."
    met_sel = (backtesting_por_modelo.get(seleccionado, {}).get("metricas") or {})
    met = (backtesting_por_modelo.get(nombre, {}).get("metricas") or {})
    rmse_sel = _numero_finito(met_sel.get("rmse"))
    rmse = _numero_finito(met.get("rmse"))
    mae_sel = _numero_finito(met_sel.get("mae"))
    mae = _numero_finito(met.get("mae"))
    mape_sel = _numero_finito(met_sel.get("mape"))
    mape = _numero_finito(met.get("mape"))
    if np.isfinite(rmse) and np.isfinite(rmse_sel) and rmse > rmse_sel:
        return (
            "No seleccionado porque el error fuera de muestra fue mayor que el del modelo final "
            f"(RMSE {rmse:.4f} vs {rmse_sel:.4f}; MAE {mae:.4f} vs {mae_sel:.4f}; MAPE {mape:.4f}% vs {mape_sel:.4f}%)."
        )
    return "No seleccionado porque no mejoro de forma suficiente la validación temporal frente al modelo final."


def _razon_modelo_seleccionado(
    nombre: str,
    modelo: dict[str, Any],
    backtesting_por_modelo: dict[str, dict],
) -> str:
    if nombre == "drift":
        return (
            "Drift se selecciono porque proyecto el cambio promedio histórico y obtuvo mejor o suficiente desempeño "
            "fuera de muestra frente a alternativas del horizonte evaluado."
        )
    return str(modelo.get("justificacion", "Seleccionado por validación temporal, parsimonia e interpretabilidad."))


def _backtesting_por_modelo_horizonte(
    backtesting_comparativo: dict[str, dict],
    horizonte: int,
) -> dict[str, dict]:
    sufijo = f"_h{int(horizonte)}"
    return {
        clave.removesuffix(sufijo): valor
        for clave, valor in backtesting_comparativo.items()
        if clave.endswith(sufijo)
    }


def _tipo_uso_horizonte(horizonte: int) -> str:
    """Clasifica el uso comunicacional del horizonte sin imponer un límite rigido."""
    h = int(horizonte)
    if h <= 3:
        return "Proyección operativa"
    if h <= 6:
        return "Proyección técnica de corto/mediano plazo"
    if h <= 12:
        return "Proyección extendida con cautela"
    if h <= HORIZONTE_LARGO:
        return "Escenario estadístico extendido"
    return "Escenario extendido o exploratorio"


def _umbrales_incertidumbre(horizonte: int) -> dict[str, float]:
    """Umbrales configurables por horizonte para el ancho relativo del intervalo de predicción del 95%."""
    h = int(horizonte)
    # En horizontes cortos "cautela" y "no_recomendado" coincidian, de modo que
    # superar el umbral saltaba directo al bloqueo duro y, por cascada, anulaba
    # todos los horizontes siguientes. Se restituye la banda intermedia prevista
    # por el propio diseno: entre "cautela" y "no_recomendado" el horizonte se
    # degrada a escenario con advertencia, nunca a proyeccion tecnica.
    if h <= 3:
        return {
            "aceptable": UMBRAL_IC95_REL_OPERATIVO,
            "cautela": UMBRAL_IC95_REL_CORTO,
            "no_recomendado": UMBRAL_IC95_REL_MEDIO,
        }
    if h <= 6:
        return {
            "aceptable": UMBRAL_IC95_REL_CORTO,
            "cautela": UMBRAL_IC95_REL_MEDIO,
            "no_recomendado": UMBRAL_IC95_REL_LARGO,
        }
    if h <= 12:
        return {
            "aceptable": UMBRAL_IC95_REL_MEDIO,
            "cautela": UMBRAL_IC95_REL_LARGO,
            "no_recomendado": UMBRAL_IC95_REL_EXTENDIDO_CERCANO,
        }
    if h <= HORIZONTE_LARGO:
        # En 13..18 rige ademas el corte explicito de UMBRAL_IC95_REL_EXTENDIDO_CERCANO.
        return {
            "aceptable": UMBRAL_IC95_REL_LARGO,
            "cautela": 0.45,
            "no_recomendado": UMBRAL_IC95_REL_EXTENDIDO,
        }
    return {
        "aceptable": 0.45,
        "cautela": 0.65,
        "no_recomendado": UMBRAL_IC95_REL_EXPLORATORIO,
    }


def _estado_por_horizonte(horizonte: int, ancho_95: float, cautelas: list[str]) -> tuple[str, str]:
    """Etiqueta del horizonte. Depende del HORIZONTE, no de cortes de amplitud.

    CIERRE 08-08-2026: se retiran las tres comparaciones contra
    `_umbrales_incertidumbre`. Eran nueve literales internos sin fuente que
    convertian la anchura del intervalo -una consecuencia de la incertidumbre
    estimada, no un defecto sancionable- en un bloqueo o en una degradacion a
    escenario. El ancho relativo se sigue calculando, se publica con su valor y
    se advierte cuando es grande; ya no decide.

    Lo que queda es una etiqueta objetiva: el tramo de horizonte al que
    pertenece el paso solicitado. `ancho_95` se conserva en la firma porque los
    llamadores la pasan y porque el valor viaja al informe.
    """
    # P0-G, 12-08-2026: RETIRADA tambien aqui la escalera «alto / medio / bajo».
    #
    # Esta segunda escalera vivia por horizonte y SOBRESCRIBIA la de la serie
    # (linea 1827), de modo que retirar solo la primera no habria cambiado nada
    # de lo publicado. Sus cortes -18, 13 y 7- no tienen fuente, y la etiqueta
    # «Alta confiabilidad relativa» afirmaba una fiabilidad que ningun calculo
    # respalda.
    #
    # Se CONSERVA el tramo de horizonte, que si es objetivo -es una propiedad
    # del paso solicitado, no un juicio- y la presencia o ausencia de cautelas,
    # que es un hecho verificable. Lo que desaparece es la categoria ordinal.
    if int(horizonte) >= 13:
        tramo = "Horizonte extendido"
    elif int(horizonte) >= 7:
        tramo = "Horizonte medio"
    else:
        tramo = "Horizonte corto"
    detalle = "con advertencias registradas" if cautelas else "sin advertencias registradas"
    return f"{tramo} ({detalle})", f"descriptivo: {tramo.lower()}, {detalle}"


def _metricas_desde_predicciones(predicciones: pd.DataFrame, entrenamiento: np.ndarray) -> dict[str, float]:
    observado = predicciones["Observado"].to_numpy(dtype=float)
    predicho = predicciones["Predicho"].to_numpy(dtype=float)
    errores = predicciones["Error"].to_numpy(dtype=float)
    abs_err = np.abs(errores[np.isfinite(errores)])
    # D-8: misma deteccion compartida por puntaje z modificado; salida descriptiva.
    periodos = predicciones["Periodo"].tolist() if "Periodo" in predicciones.columns else None
    detalle_extremos = detectar_errores_extremos(errores, periodos)
    extremos = detalle_extremos["proporcion"]
    if len(abs_err) == 0:
        estabilidad = float("nan")
    else:
        estabilidad = float(np.std(abs_err, ddof=1) / np.mean(abs_err)) if len(abs_err) > 1 and np.mean(abs_err) > 0 else 0.0
    if "Escala_naive_insample" in predicciones.columns:
        escalas_mase = pd.to_numeric(predicciones["Escala_naive_insample"], errors="coerce").to_numpy(dtype=float)
    else:
        escala_unica = calcular_escala_naive_insample(entrenamiento)
        escalas_mase = np.full(len(errores), escala_unica, dtype=float)
    mase = calcular_mase_por_origen(np.abs(errores), escalas_mase)
    escalas_validas = escalas_mase[np.isfinite(escalas_mase) & (np.abs(escalas_mase) > EPS_NUMERICO)]
    return {
        "mae": calcular_mae(observado, predicho),
        "rmse": calcular_rmse(observado, predicho),
        "mape": calcular_mape(observado, predicho),
        "smape": calcular_smape(observado, predicho),
        "mase": mase,
        "mase_denominador": "naive no estacional por origen walk-forward",
        "mase_denominador_promedio": float(np.mean(escalas_validas)) if len(escalas_validas) else float("nan"),
        "mase_denominadores_validos": int(len(escalas_validas)),
        "mase_advertencia": "" if len(escalas_validas) else "MASE no estable: escala naive in-sample nula o no disponible.",
        "sesgo_medio": calcular_sesgo_medio(observado, predicho),
        "error_medio": calcular_sesgo_medio(observado, predicho),
        "desviacion_error": float(np.std(errores, ddof=1)) if len(errores) > 1 else 0.0,
        "porcentaje_errores_extremos": extremos,
        "errores_extremos": detalle_extremos,
        "estabilidad_error": estabilidad,
        "iteraciones": int(len(predicciones)),
    }


def peor_que_benchmark_naive(rrmse_naive: Any, es_benchmark: Any) -> bool:
    """Lectura DESCRIPTIVA del error relativo frente a naive (C-BEN-002).

        no es_benchmark  AND  rrmse_naive finito  AND  rrmse_naive > 1

    **No decide nada.** Informa de un hecho comparativo: el modelo tiene mayor
    RMSE fuera de muestra que el metodo de referencia en ese horizonte.

    El corte es **1**, que no es un umbral elegido sino la definicion: el punto
    de equivalencia con el benchmark, sobre el que Hyndman y Koehler (2006)
    construyen los errores relativos.

    Historia, porque explica por que la funcion sigue existiendo:

      * hasta el 08-08-2026 la misma pregunta se hacia dos veces -R-06 y R-07-
        con dos formulas distintas, y **ambas bloqueaban** el horizonte;
      * ese dia se unificaron en una sola puerta con el corte **1,25**;
      * el mismo dia se cerro que **1,25 no tiene fuente identificada**. El
        inventario RC3 (INV-040) ya lo habia declarado «margen de gracia sin
        fuente» y recomendaba «conservar el principio con el corte natural en
        1.0».

    **CIERRE 08-08-2026: se retira 1,25 y se retira el bloqueo.** Lo que la
    definicion publicada sustenta es la metrica y su lectura frente a 1; lo que
    no sustenta es convertir esa lectura en un veto. El modelo lo elige el
    desempeno OOS agregado (`_modelo_trayectoria_consistente`); esta funcion
    solo dice, para cada horizonte, si ese modelo quedo por encima o por debajo
    de su referencia.

    Se exime a los benchmarks porque compararlos consigo mismos no informa.
    """
    ratio = _numero_finito(rrmse_naive)
    return bool(not es_benchmark and np.isfinite(ratio) and ratio > 1.0)


def _comparacion_desde_backtesting(
    backtesting: dict[str, Any],
    backtesting_por_modelo: dict[str, dict],
    es_benchmark: bool = False,
) -> dict[str, Any]:
    metricas = backtesting.get("metricas", {}) if backtesting else {}
    rmse_modelo = _numero_finito(metricas.get("rmse"))
    mae_modelo = _numero_finito(metricas.get("mae"))
    naive = backtesting_por_modelo.get("naive", {})
    drift = backtesting_por_modelo.get("drift", {})
    rmse_naive = _numero_finito((naive.get("metricas") or {}).get("rmse"))
    rmse_drift = _numero_finito((drift.get("metricas") or {}).get("rmse"))
    mae_naive = _numero_finito((naive.get("metricas") or {}).get("mae"))
    mae_drift = _numero_finito((drift.get("metricas") or {}).get("mae"))
    rrmse_naive = _ratio_local(rmse_modelo, rmse_naive)
    rrmse_drift = _ratio_local(rmse_modelo, rmse_drift)
    rmae_naive = _ratio_local(mae_modelo, mae_naive)
    rmae_drift = _ratio_local(mae_modelo, mae_drift)
    return {
        "modelo": backtesting.get("modelo", ""),
        "rmse_modelo": rmse_modelo,
        "mae_modelo": mae_modelo,
        "rmse_naive": rmse_naive,
        "rmse_drift": rmse_drift,
        "mae_naive": mae_naive,
        "mae_drift": mae_drift,
        "rrmse_naive": rrmse_naive,
        "rrmse_drift": rrmse_drift,
        "rmae_naive": rmae_naive,
        "rmae_drift": rmae_drift,
        "supera_naive_rmse": bool(np.isfinite(rrmse_naive) and rrmse_naive < 1.0),
        "supera_drift_rmse": bool(np.isfinite(rrmse_drift) and rrmse_drift < 1.0),
        # CIERRE 08-08-2026: las cuatro claves comparativas usaban 1,10 y 1,25,
        # dos margenes internos sin fuente. Ahora comparan contra **1**, que es
        # el punto de equivalencia con el benchmark y lo unico que la definicion
        # de error relativo sustenta. La clave decia «peor que naive» y era
        # falsa para 1,00 < r <= 1,25.
        "supera_o_iguala_naive_rmse": bool(np.isfinite(rrmse_naive) and rrmse_naive <= 1.0),
        "supera_o_iguala_drift_rmse": bool(np.isfinite(rrmse_drift) and rrmse_drift <= 1.0),
        "peor_que_naive_rmse": bool(np.isfinite(rrmse_naive) and rrmse_naive > 1.0),
        "peor_que_drift_rmse": bool(np.isfinite(rrmse_drift) and rrmse_drift > 1.0),
        # C-BEN-002: lectura DESCRIPTIVA. Ya no bloquea la factibilidad; su
        # consumidor (`analisis_series.py`) la publica como advertencia.
        "modelo_no_supera_benchmarks": peor_que_benchmark_naive(rrmse_naive, es_benchmark),
    }


def _evaluar_horizontes_proyeccion(
    candidatos: list[dict],
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
    serie_trabajo: pd.DataFrame,
    validacion_serie: dict,
    outliers: list[dict],
    t_ultimo: int,
    y_obs: np.ndarray,
    anio_base: int,
    modelo_fijo: str | None = None,
) -> list[dict[str, Any]]:
    """Evalua cada horizonte.

    Si ``modelo_fijo`` viene dado, todos los horizontes se clasifican con ese
    mismo modelo, de modo que clasificación y trayectoria correspondan al mismo
    modelo y los primeros valores proyectados no cambien con el horizonte
    solicitado.
    """
    evaluaciones: list[dict[str, Any]] = []
    ultimo_observado = float(y_obs[-1])
    candidato_fijo = (
        next((c for c in candidatos if c.get("nombre") == modelo_fijo and "predict" in c), None)
        if modelo_fijo
        else None
    )
    for horizonte in horizontes:
        backtesting_por_modelo = _backtesting_por_modelo_horizonte(backtesting_comparativo, horizonte)
        try:
            if candidato_fijo is not None:
                # Se recalcula la comparacion con benchmarks para este horizonte:
                # sin ella el modelo fijo perderia la evidencia relativa que usa
                # la clasificacion.
                modelo = {
                    **candidato_fijo,
                    "comparacion_benchmarks": _comparacion_desde_backtesting(
                        backtesting_por_modelo.get(candidato_fijo["nombre"], {}),
                        backtesting_por_modelo,
                        es_benchmark=bool(candidato_fijo.get("es_benchmark")),
                    ),
                }
            else:
                # AUDITORIA 09-08-2026, P0-A. Hasta esta fecha aqui se invocaba
                # `seleccionar_modelo_por_evidencia`, cuya funcion de puntaje
                # combina once coeficientes sin ninguna fuente e incluye
                # penalizaciones por IDENTIDAD del modelo (promedio_movil +1,2;
                # naive +1,0 si h>3). Los REQUISITOS NO NEGOCIABLES prohiben las
                # dos cosas: pesos arbitrarios y excepciones por identidad como
                # decisores. Ademas la llamada esta DENTRO del bucle de
                # horizontes, de modo que podia devolver modelos distintos por
                # horizonte y romper la garantia de un modelo por trayectoria.
                #
                # C-SEL-001 devuelve None exactamente cuando no hay evidencia
                # fuera de muestra COMPARABLE con la que elegir: ningun modelo
                # produjo errores utilizables, la muestra comun quedo vacia, o
                # todos los RMSE son no finitos. El desempeno OOS es el unico
                # criterio de seleccion sustentado; sin el no existe base para
                # elegir un modelo, y fabricar una con un puntaje sin fuente es
                # justamente lo que se retira.
                #
                # Cuando no hay con que elegir, el horizonte no se entrega y se
                # declara la causa. Medicion previa al cambio: 0 activaciones
                # sobre 10 series x 5 horizontes (50 escenarios), de modo que
                # esta rama no altera ningun resultado observado.
                raise ValueError(
                    "modelo_no_seleccionable: no hay evidencia fuera de muestra "
                    "comparable entre candidatos para elegir un modelo en este "
                    "horizonte (C-SEL-001 sin decision)."
                )
        except Exception as exc:
            evaluaciones.append(
                {
                    "horizonte": horizonte,
                    "permitido": False,
                    "permitido_para_proyeccion_tecnica": False,
                    "permitido_como_escenario": False,
                    "no_recomendable": True,
                    "bloqueo_por_datos": False,
                    "decision": "No recomendable",
                    "clasificacion": "no_viable",
                    "estado": "No recomendable",
                    "razones_horizonte": [f"No fue posible seleccionar modelo para h={horizonte}: {exc}"],
                    "mensaje_horizonte": "No hay modelo seleccionable para este horizonte.",
                    "backtesting_por_modelo": backtesting_por_modelo,
                }
            )
            # P0-H, 12-08-2026: era `break`. Un fallo de seleccion en un
            # horizonte tampoco debe impedir EVALUAR los siguientes: cada paso
            # registra su propio estado. Con `C-SEL-001` el modelo es unico por
            # serie, de modo que en la practica el fallo se repite; la diferencia
            # es que ahora queda constancia por horizonte en vez de una sola
            # entrada y el resto sin medir.
            continue
        backtesting = backtesting_por_modelo.get(modelo["nombre"], {})

        residuos = np.asarray(modelo.get("residuos", []), dtype=float)
        diagnostico = modelo.get("diagnostico_residuos")
        if not diagnostico:
            diagnostico = evaluar_residuos(residuos, tipo_modelo=modelo.get("nombre"))
        t_futuro_eval = np.arange(t_ultimo + 1, t_ultimo + horizonte + 1, dtype=float)
        try:
            y_eval = proyectar_modelo(modelo, t_futuro_eval, forzar_desde=None)
            intervalos = _intervalos_prediccion(
                y_futuro=y_eval,
                errores_por_horizonte=_errores_por_horizonte(
                    backtesting_comparativo,
                    str(modelo.get("nombre", "")),
                    tuple(range(1, int(horizonte) + 1)),
                ),
            )
            tabla_eval = _construir_tabla_proyecciones(
                t_futuro=t_futuro_eval,
                y_futuro=y_eval,
                intervalos=intervalos,
                ultimo_observado=ultimo_observado,
                anio_base=anio_base,
                modelo=modelo.get("nombre_visible", modelo.get("nombre", "")),
                confianza="pendiente",
                advertencias=[],
            )
            evaluacion_intervalos = _evaluar_intervalos_prediccion(tabla_eval, horizonte=horizonte)
        except Exception as exc:
            # Sin errores del paso exacto la banda no es calculable. Es una
            # imposibilidad matematica, no una banda infinitamente ancha: se
            # declara como tal y el ancho queda sin valor, no en infinito.
            sin_errores = isinstance(exc, ValueError) and "errores fuera de muestra" in str(exc)
            estado = BANDA_NO_CALCULABLE if sin_errores else BANDA_LIMITES_NO_FINITOS
            evaluacion_intervalos = {
                "critico": True,
                "advertencias": [],
                "razones": [
                    MOTIVO_BANDA[estado]
                    if sin_errores
                    else f"No se pudo construir la banda para h={horizonte}: {exc}"
                ],
                "clasificacion": estado,
                "estado_banda": estado,
                "banda_valida": False,
                "ancho_relativo_maximo": float("nan"),
                "ancho_relativo_95_maximo": float("nan"),
            }
        factibilidad = evaluar_factibilidad_proyeccion(
            serie=serie_trabajo,
            validacion=validacion_serie,
            outliers=outliers,
            diagnostico=diagnostico,
            backtesting=backtesting,
            comparacion_benchmarks=modelo.get("comparacion_benchmarks", {}),
            evaluacion_intervalos=evaluacion_intervalos,
            horizonte_solicitado=horizonte,
        )
        evidencia = _clasificar_evidencia_horizonte(
            horizonte=horizonte,
            modelo=modelo,
            backtesting=backtesting,
            factibilidad=factibilidad,
            evaluacion_intervalos=evaluacion_intervalos,
        )
        factibilidad["estado"] = evidencia["estado"]
        factibilidad["nivel_confianza_metodologica"] = evidencia["confianza"]
        factibilidad["horizonte_maximo_sugerido"] = horizonte if evidencia["permitido"] else 0
        factibilidad["explicacion"] = evidencia["mensaje"]
        factibilidad["advertencias"] = evidencia["advertencias"]
        evaluaciones.append(
            {
                "horizonte": horizonte,
                "permitido": evidencia["permitido"],
                "permitido_para_proyeccion_tecnica": evidencia["permitido_para_proyeccion_tecnica"],
                "permitido_como_escenario": evidencia["permitido_como_escenario"],
                "no_recomendable": evidencia["no_recomendable"],
                "bloqueo_por_datos": evidencia.get("bloqueo_por_datos", False),
                "decision": evidencia["decision"],
                "clasificacion": evidencia["clasificacion"],
                "estado": evidencia["estado"],
                "confianza": evidencia["confianza"],
                "modelo": modelo,
                "backtesting": backtesting,
                "backtesting_por_modelo": backtesting_por_modelo,
                "diagnostico_residuos": diagnostico,
                "factibilidad": factibilidad,
                "evaluacion_intervalos": evaluacion_intervalos,
                "razones_horizonte": evidencia["razones"],
                "mensaje_horizonte": evidencia["mensaje"],
                "tipo_uso": evidencia["tipo_uso"],
            }
        )
        # P0-H, 12-08-2026: RETIRADA LA PARADA TEMPRANA.
        #
        # Hasta esta fecha aqui habia `if evidencia["no_recomendable"]: break`,
        # de modo que los horizontes posteriores al primer fallo NO SE
        # EVALUABAN. No es que quedaran fuera del prefijo: no se median, y el
        # informe los publicaba como «no evaluados despues del primer horizonte
        # no viable», mezclando «no medido» con «no defendible».
        #
        # Ninguna fuente exige esa parada. FPP3 5.10 evalua la exactitud POR
        # HORIZONTE y publica UNA TABLA con un valor por cada h, sin detenerse
        # cuando uno empeora. Y el criterio de SAVIP no es monotono -mezcla
        # MAPE, sMAPE, MASE, sesgo, estabilidad, ancho del IC95, recuento de
        # ventanas y comparacion con benchmarks-, de modo que nada garantiza
        # que si h falla, h+1 tambien falle.
        #
        # MEDIR NO OBLIGA A PUBLICAR: la continuidad de la trayectoria se
        # resuelve despues, en la regla de publicacion, que es donde
        # corresponde.
    return evaluaciones


def _clasificar_evidencia_horizonte(
    horizonte: int,
    modelo: dict[str, Any],
    backtesting: dict[str, Any],
    factibilidad: dict[str, Any],
    evaluacion_intervalos: dict[str, Any],
) -> dict[str, Any]:
    metricas = backtesting.get("metricas", {}) if backtesting else {}
    comparacion = modelo.get("comparacion_benchmarks", {})
    razones = list(factibilidad.get("razones_tecnicas", []))
    advertencias = list(factibilidad.get("advertencias", []))
    iteraciones = int(backtesting.get("iteraciones", 0) or metricas.get("iteraciones", 0) or 0)
    mape = _numero_finito(metricas.get("mape"))
    smape = _numero_finito(metricas.get("smape"))
    mase = _numero_finito(metricas.get("mase"))
    mae = _numero_finito(metricas.get("mae"))
    sesgo = abs(_numero_finito(metricas.get("sesgo_medio", metricas.get("error_medio"))))
    estabilidad = _numero_finito(metricas.get("estabilidad_error"))
    ancho = _numero_finito(evaluacion_intervalos.get("ancho_relativo_95_maximo", evaluacion_intervalos.get("ancho_relativo_maximo")))
    rrmse_naive = _numero_finito(comparacion.get("rrmse_naive"))
    rrmse_drift = _numero_finito(comparacion.get("rrmse_drift"))
    rmae_naive = _numero_finito(comparacion.get("rmae_naive"))
    rmae_drift = _numero_finito(comparacion.get("rmae_drift"))
    # H-8, 18-08-2026 (auditoria final V-CODEX-R2). Se retira
    # `umbrales = _umbrales_incertidumbre(horizonte)`: se calculaba y no se
    # leia en ningun punto de esta funcion (los nueve cortes que describia
    # dejaron de decidir el 08-08-2026; ver comentario mas abajo).

    permitido = bool(factibilidad.get("factible", False))
    bloqueo_duro = False
    bloqueo_por_datos = False
    # CIERRE 08-08-2026: `forzar_solo_escenario` desaparece. Sus cuatro
    # productores -evidencia reducida, estabilidad, amplitud y V-12- eran cortes
    # internos sin fuente y ahora son advertencias. Un horizonte solo deja de
    # ser proyeccion tecnica cuando NO SE PUEDE CALCULAR, no cuando el resultado
    # es menos comodo.

    # Imposibilidad matematica de la banda: bloquea en CUALQUIER horizonte y por
    # una razon propia, no por amplitud. Se comprueba lo primero, porque una
    # banda que no existe no admite comparaciones de magnitud.
    # CORRECCION 13-08-2026, tras la microauditoria de las nueve fallas.
    #
    # La sesion anterior rompio este bloqueo invocando REQ 14 -«una deficiencia
    # del intervalo no invalida automaticamente el pronostico puntual»-. **Esa
    # aplicacion de REQ 14 era incorrecta y se retira.** Verificado en el codigo:
    #
    #   * `estado_banda` INCLUYE EL PROPIO PRONOSTICO en la comprobacion de
    #     finitud, de modo que `BANDA_LIMITES_NO_FINITOS` se dispara justamente
    #     cuando el PUNTO no es finito. Bloquear ahi no acopla nada: el punto no
    #     existe;
    #   * `BANDA_LIMITES_INVERTIDOS` exige un semiancho NEGATIVO, lo que solo
    #     puede producir un calculo roto. No es una banda de mala calidad: es la
    #     prueba de que la aritmetica que genero ese horizonte fallo;
    #   * `BANDA_NO_CALCULABLE` coincide con la ausencia de errores OOS y el piso
    #     de ventanas ya lo cubre.
    #
    # REQ 14 habla de una DEFICIENCIA del intervalo -ancho excesivo, cobertura
    # baja, metodo no sustentado-, no de una IMPOSIBILIDAD DE CALCULO. El
    # contrato historico -«los dos que quedan son imposibilidades genuinas»- es
    # correcto y se restituye.
    #
    # Lo que P0-G si identifico con razon es distinto y NO se toca: que el
    # INTERVALO cuyo METODO no esta sustentado (P0-C) no debe bloquear el punto.
    # Eso se resuelve con `intervalo_sustentado = False`, que se conserva.
    # P0-G REABIERTO, 14-08-2026 (caso G9 de la revision independiente). De los
    # cuatro estados de banda, solo DOS son imposibilidades del propio calculo:
    #
    #   BANDA_LIMITES_NO_FINITOS  -> el pronostico entra en la comprobacion de
    #                                finitud junto con los limites, de modo que
    #                                este estado detecta un PUNTO no finito;
    #   BANDA_LIMITES_INVERTIDOS  -> el orden invertido indica que el calculo que
    #                                los produjo no es valido.
    #
    # Esos dos siguen bloqueando (clase G-A). En cambio BANDA_NO_CALCULABLE dice
    # «no hay errores fuera de muestra del paso exacto para construir la banda»:
    # es una carencia del INTERVALO, no del punto, que ya existe porque sale del
    # ajuste del modelo. Bloquear con el la entrega de un pronostico finito y
    # coherente es exactamente el acoplamiento que P0-G debia separar, y ademas
    # hace que P0-C -abierto- siga vetando (REQ 14).
    # P0-C C2 PASO 0: el UNICO bloqueo aritmetico que queda es el del propio
    # pronostico. Los estados de banda -no finitos, invertidos, no calculable,
    # semiancho cero- describen un intervalo que C2 retiro del producto: se
    # registran como diagnostico y NO cancelan el punto. Ver `estado_banda`.
    estado_banda_horizonte = str(evaluacion_intervalos.get("estado_banda") or "")
    if estado_banda_horizonte == PUNTO_NO_FINITO:
        permitido = False
        bloqueo_duro = True
        razones.append(MOTIVO_BANDA.get(estado_banda_horizonte, "El pronostico no es finito."))
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Aqui se publicaba el MOTIVO_BANDA
    # del estado -«la banda no existe», «no hay errores fuera de muestra del paso
    # exacto para construir la banda»- mas «el intervalo queda declarado como no
    # sustentado». Los cuatro estados restantes describen una banda que no se
    # entrega en ningun caso, de modo que anunciar su defecto informa sobre un
    # objeto ausente de la salida. El estado se sigue calculando y viaja como
    # diagnostico; lo que se retira es esta advertencia publicada. El punto no
    # finito, que SI bloquea, tiene su propia rama arriba y no se toca.
    # Evidencia OOS por niveles. P0-G REABIERTO: el PUNTO no depende de las
    # ventanas -se calcula del ajuste-, y con una o dos hay evidencia medida (RMSE
    # y MAE finitos), solo que limitada. Convertir «poca evidencia» en «no hay
    # pronostico» era un veto sin fuente. Se informa con el numero de ventanas.
    #
    # 17-08-2026: el texto de estos dos tramos citaba el minimo de ventanas del
    # INTERVALO -«por debajo de 3 no es posible construir ni evaluar el intervalo
    # de prediccion», «su intervalo no»- y presentaba 6 como umbral de estabilidad.
    # Se unifica con el vocabulario de evidencia OOS de `_texto_evidencia_oos`:
    # dice cuantas ventanas hay y que ese numero es el que sostiene las metricas,
    # sin nombrar el intervalo y sin convertir 3 ni 6 en umbral de aceptacion.
    if iteraciones < MIN_ITERACIONES_BACKTESTING:
        advertencias.append(_texto_evidencia_oos(iteraciones) + " Las metricas de este horizonte se calculan sobre esa muestra.")
    # AUDITORIA 09-08-2026 (hallazgo E-03): las metricas PORCENTUALES no finitas
    # dejan de bloquear. MAPE no esta definido si algun valor observado es cero y
    # sMAPE si |y|+|yhat| es cero; eso limita la METRICA, no el pronostico. RMSE,
    # MAE y MASE siguen definidos y son las que sostienen la evidencia. Ninguna
    # fuente sustenta cancelar un pronostico porque una razon porcentual sea
    # indefinida, y el veto se habia declarado «imposibilidad de calculo» cuando
    # lo que es imposible es solo esa metrica. Medicion de la auditoria: 0
    # activaciones sobre 10 series x 24 horizontes, de modo que la retirada no
    # afloja ningun caso observado; retira una regla sin fuente.
    if not np.isfinite(mape):
        advertencias.append(
            "MAPE no calculable para este horizonte (requiere valores observados distintos de "
            "cero). Se reporta como no calculable; la evidencia se lee con RMSE, MAE y MASE."
        )
    if not np.isfinite(smape):
        advertencias.append(
            "sMAPE no calculable para este horizonte. Se reporta como no calculable; la "
            "evidencia se lee con RMSE, MAE y MASE."
        )
    # D-9: se retira el bloqueo por MAPE > 25 % o sMAPE > 30 %. Ambos cortes eran
    # internos y sin fuente. Que la metrica no sea calculable sigue bloqueando,
    # porque entonces no hay evidencia; que sea alta se informa con su valor.
    # D-8: la proporcion de errores inusuales ya no bloquea el horizonte ni lo
    # degrada a escenario. Los cortes 25 % y 50 % eran porcentajes internos sin
    # fuente. La cantidad, la proporcion y el puntaje z por ventana se publican
    # como informacion descriptiva en la interfaz y en los informes.
    # CIERRE 08-08-2026: la AMPLITUD del intervalo deja de bloquear y de
    # degradar. Los nueve cortes de `_umbrales_incertidumbre` eran literales
    # internos sin fuente y con cero activaciones sobre el anexo de mayo.
    #
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Se retira tambien la ADVERTENCIA
    # PUBLICADA. `ancho` es el ancho relativo del IC95, y `ancho x punto` -con el
    # punto publico- devuelve el ancho absoluto de la banda retirada: publicarlo
    # con un decimal la reconstruye con tres cifras significativas, que es una
    # representacion equivalente del intervalo. El ancho se sigue calculando y
    # viaja en `evaluacion_intervalos` como diagnostico interno.
    # CIERRE 08-08-2026: la comparacion con el benchmark deja de ser una puerta.
    # El corte 1,25 no tiene fuente identificada -el propio inventario RC3 lo
    # declaro «margen de gracia sin fuente»- y decidia el estado y disparaba la
    # sustitucion por Drift. Se conserva el RRMSE como metrica y su lectura
    # natural frente a 1, que es la que Hyndman y Koehler (2006) sustentan.
    if np.isfinite(rrmse_naive) and rrmse_naive > 1.0 and not modelo.get("es_benchmark"):
        advertencias.append(
            f"El modelo no supera al benchmark naive en este horizonte "
            f"(rRMSE = {rrmse_naive:.3f} > 1). Se informa como comparación, no bloquea."
        )

    relativo_favorable = any(
        np.isfinite(r) and r <= 1.0
        for r in [rrmse_naive, rrmse_drift, rmae_naive, rmae_drift]
    )
    # El unico piso que sigue vigente es el de evidencia: sin ventanas o sin un
    # error fuera de muestra calculable no hay nada que afirmar. Todo lo demas
    # -amplitud y comparacion con benchmarks- se informa y no condiciona el
    # permiso.
    #
    # AUDITORIA 09-08-2026 (E-03): el piso se lee sobre RMSE y MAE, que son las
    # metricas de error definidas para cualquier serie no degenerada, y ya no
    # sobre MAPE/sMAPE, que son razones porcentuales indefinidas cuando el
    # denominador se anula. Que una razon no exista no es falta de evidencia.
    rmse_h = _numero_finito(metricas.get("rmse"))
    # P0-G, 16-08-2026 (V-CODEX-3). El piso era `iteraciones >=
    # MIN_ITERACIONES_WF_ESCENARIO`, es decir tres ventanas, y ese tres procede
    # de poder estimar la dispersion y verificar la cobertura del INTERVALO. Con
    # una sola ventana ya existe un error fuera de muestra y un RMSE calculable:
    # exigir tres para RECUPERAR el permiso del punto reintroducia por la puerta
    # de atras el acoplamiento banda -> punto que P0-G separo.
    #
    # El piso pasa a ser el de existencia: al menos una ventana y al menos una
    # metrica de error finita. Es la condicion minima para afirmar algo fuera de
    # muestra, y no un umbral elegido.
    evidencia_predictiva_ok = (
        iteraciones >= 1
        and (np.isfinite(rmse_h) or np.isfinite(mae))
    )
    if not permitido and not bloqueo_duro and evidencia_predictiva_ok:
        permitido = True
        # H-1A, 18-08-2026 (auditoria final V-CODEX-R2). Decia "...el desempeño
        # fuera de muestra y los intervalos son razonables": el motivo real,
        # documentado arriba, es la EXISTENCIA de evidencia (>=1 ventana y una
        # metrica de error finita), no los intervalos.
        advertencias.append(
            "La factibilidad base tenia advertencias diagnosticas; se permite el horizonte porque existe evidencia fuera de muestra (ventanas y error finitos)."
        )
    if relativo_favorable:
        advertencias = [
            a for a in advertencias
            if "desempeño inferior al benchmark naive usado como escala" not in str(a)
            and "inferior al benchmark naive" not in str(a)
        ]

    cautelas = list(advertencias)
    if np.isfinite(mase) and mase > UMBRAL_MASE_ADVERTENCIA:
        if relativo_favorable:
            cautelas.append(
                "MASE > 1 se reporta como métrica auxiliar; los errores relativos frente a benchmarks de backtesting son aceptables."
            )
        else:
            cautelas.append("MASE > 1; se usa con cautela porque la escala naive penaliza la serie suave.")
        # D-9: se retira la degradacion por MASE >= 3,0 en horizontes extendidos.
        # El 3,0 era un literal sin fuente. Se conserva la lectura de MASE
        # frente a 1, que si esta sustentada.
    # CIERRE 08-08-2026: las tres cautelas que siguen se CONSERVAN como
    # informacion y pierden su efecto sobre el estado. Ninguna tenia fuente:
    #   * estabilidad > 1 en h>=13   -> corte interno;
    #   * amplitud del IC95          -> los nueve cortes de incertidumbre;
    #   * V-12, benchmark en h>=13   -> nacio en la remediacion del 29-07-2026,
    #     no consulta ningun deterioro medido y castigaba el Drift que la propia
    #     salvaguarda fabricaba.
    if np.isfinite(estabilidad) and estabilidad > UMBRAL_ESTABILIDAD_INESTABLE:
        cautelas.append("Errores inestables entre ventanas.")
    # D-9: se retira la cautela y la degradacion por sesgo > 0,75 x MAE. El
    # factor era interno y sin fuente; el sesgo medio se publica con su valor.
    # P0-C, 17-08-2026 (V-CODEX-R3): misma razon que la advertencia de amplitud.
    # `ancho` reconstruye el semiancho de la banda retirada junto al punto.
    if modelo.get("es_benchmark"):
        cautelas.append("El metodo seleccionado es un benchmark/escenario simple.")

    if not permitido:
        estado = factibilidad.get("estado") or "No recomendable"
        # P0-G: sin categoria ordinal. El motivo va en `razones` y `mensaje`.
        confianza = "descriptivo: horizonte no evaluable con la evidencia disponible"
        permitido_tecnico = False
        permitido_escenario = False
        no_recomendable = True
        decision = "No recomendable"
        clasificacion = "no_viable"
        mensaje = _mensaje_horizonte_no_permitido(
            horizonte=horizonte,
            modelo=modelo,
            razones=_deduplicar_local(razones),
            metricas=metricas,
            evaluacion_intervalos=evaluacion_intervalos,
        )
    elif horizonte <= 3 and cautelas:
        estado = "Horizonte corto (con advertencias registradas)"
        confianza = "descriptivo: horizonte corto, con advertencias registradas"
        permitido_tecnico = True
        permitido_escenario = True
        no_recomendable = False
        decision = "Permitido para proyección técnica"
        clasificacion = "tecnica_cautela"
        # R04, 14-08-2026. El texto anterior decía que el modelo «mostró desempeño
        # ACEPTABLE en backtesting». «Aceptable» supone un criterio de aceptación,
        # y no hay ninguno sustentado: los cortes que lo definían se retiraron por
        # carecer de fuente. Con P0-C abierto y P0-E bloqueado, además, la
        # evidencia es provisional y el intervalo no está sustentado. Se describe
        # lo que hay -continuidad, modelo, evidencia medida- sin calificarla.
        mensaje = (
            f"Punto técnicamente calculable con {modelo.get('nombre_visible')} sobre una serie "
            f"continua, con {iteraciones} ventanas de validación medidas. El intervalo no tiene "
            "sustento adoptado y la evidencia fuera de muestra es provisional mientras P0-C y "
            "P0-E sigan pendientes; las cautelas quedan documentadas."
        )
    else:
        estado, confianza = _estado_por_horizonte(horizonte, ancho, cautelas)
        # H-4, 18-08-2026 (auditoria final V-CODEX-R2). Aqui existian dos ramas
        # que comparaban `estado` contra "Escenario de alta incertidumbre" y
        # contra {"Escenario estadístico extendido", "Proyección extendida"}.
        # `_estado_por_horizonte` no produce esos valores desde el CIERRE
        # 08-08-2026 (devuelve solo el tramo objetivo: "Horizonte corto/medio/
        # extendido (con/sin advertencias)"), de modo que ambas ramas eran
        # inalcanzables y las clasificaciones "escenario_alta_incertidumbre" y
        # "extendida_cautela" nunca llegaban a publicarse, pese a que la tesis
        # las describia como estados posibles. Retiradas.
        permitido_tecnico = True
        permitido_escenario = True
        no_recomendable = False
        if cautelas:
            decision = "Permitido para proyección técnica con cautela"
            clasificacion = "tecnica_cautela"
            mensaje = "Se permite proyección con cautela; las advertencias quedan registradas en el informe."
        else:
            decision = "Permitido para proyección técnica"
            clasificacion = "tecnica_alta"
            # H-1A, 18-08-2026 (auditoria final V-CODEX-R2). Decia "...segun
            # backtesting e intervalos": el intervalo no es fundamento vigente
            # de ninguna decision (P0-C). Sustituido por lo que realmente la
            # sostiene: el backtesting y la evidencia fuera de muestra.
            mensaje = "La proyección es defendible para el horizonte evaluado según backtesting y evidencia fuera de muestra."

    return {
        "permitido": permitido,
        "estado": estado,
        "confianza": confianza,
        "permitido_para_proyeccion_tecnica": permitido_tecnico,
        "permitido_como_escenario": permitido_escenario,
        "no_recomendable": no_recomendable,
        "bloqueo_por_datos": bloqueo_por_datos,
        "decision": decision,
        "clasificacion": clasificacion,
        "razones": _deduplicar_local(razones),
        "advertencias": _deduplicar_local(cautelas),
        "mensaje": mensaje,
        "tipo_uso": _tipo_uso_horizonte(horizonte),
    }


def _sse_exacto(valores: list[float]) -> Fraction:
    """Suma exacta de cuadrados de una lista de flotantes finitos.

    P0-D, 14-08-2026. El selector minimiza

        RMSE_m = sqrt( (1/n) * suma_i e_{m,i}^2 )

    sobre la MISMA muestra comun y con el MISMO n para todos los candidatos.
    Como la raiz cuadrada es estrictamente creciente en [0, inf) y el factor 1/n
    es comun, se cumple

        argmin_m RMSE_m = argmin_m MSE_m = argmin_m SSE_m

    de modo que la eleccion puede decidirse comparando la suma de cuadrados. Eso
    **no cambia la metrica**: es una derivacion, no una metodologia nueva.

    POR QUE HACE FALTA. En coma flotante, `sqrt(sum(e**2)/n)` y
    `hypot(e_1,...,e_n)/sqrt(n)` son algebraicamente iguales pero no redondean
    igual. Medido: con dos candidatos que difieren en una ULP en un solo error,
    la forma directa distingue el menor y `hypot` devuelve **el mismo flotante
    para ambos**, creando un empate que no existe. Con el desempate por orden de
    aparicion, ese empate artificial hace ganar al primer candidato del banco en
    lugar de al de menor error real: el ganador pasaba a depender del redondeo.

    Cada flotante IEEE-754 es exactamente un racional con denominador potencia de
    dos, que `float.as_integer_ratio()` devuelve sin perdida. Se acumula sobre
    enteros de Python -precision arbitraria- y se compone una unica fraccion al
    final, de modo que el resultado es exacto, independiente del orden de suma y
    libre de desbordamiento.

    No interviene ninguna tolerancia, epsilon, `isclose` ni redondeo.
    """
    if not valores:
        return Fraction(0)
    razones = [float(v).as_integer_ratio() for v in valores]
    denominador_comun = max(den for _, den in razones)
    total = 0
    for numerador, den in razones:
        # `den` y `denominador_comun` son potencias de dos, luego la division
        # es exacta y el reescalado no pierde ningun bit.
        factor = denominador_comun // den
        total += (numerador * factor) ** 2
    return Fraction(total, denominador_comun * denominador_comun)


def _rmse_global_estable(valores: list[float]) -> float:
    """RMSE de una lista de errores, evaluado sin desbordar en los intermedios.

    Misma expresion de siempre, escrita de otra forma:

        sqrt((e_1^2 + ... + e_n^2) / n)  =  hypot(e_1, ..., e_n) / sqrt(n)

    HALLAZGO CLASE B, 13-08-2026. La forma anterior era
    ``math.sqrt(sum(e ** 2 for e in valores) / n)``. Con errores
    **individualmente finitos** pero muy grandes -medido: 3,72e155 en la serie
    erratica de 72 observaciones- el cuadrado excede el rango del flotante y, al
    ser `float` de Python, ``**`` levanta ``OverflowError`` en vez de devolver
    ``inf``. La guarda ``np.isfinite`` de quien llama, escrita justamente para
    excluir candidatos divergentes, nunca se alcanzaba: la excepcion abortaba
    `ejecutar_proyeccion` entera con traceback.

    ``math.hypot`` es variadico desde Python 3.8 y calcula la norma euclidea con
    escalado interno, de modo que nunca materializa los cuadrados. Devuelve
    ``inf`` -no excepcion- cuando el resultado real no cabe en un flotante, y
    propaga ``inf``/``nan`` como no finitos, que es lo que la guarda espera.

    La correccion es **puramente numerica**: no cambia la metrica, ni la muestra
    comun, ni los pesos, ni el orden de candidatos, ni el desempate. No hay
    recorte, epsilon, umbral de magnitud, descarte por tamano ni tope de
    horizonte. El cap 30 retirado en P0-H no creo la divergencia: la hizo
    observable, porque antes esos horizontes no se median.
    """
    if not valores:
        return float("nan")
    return math.hypot(*valores) / math.sqrt(len(valores))


def _errores_oos_por_par(
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
) -> dict[str, dict[tuple[int, int], float]]:
    """Errores fuera de muestra de cada modelo, indexados por (objetivo, horizonte).

    El par ``(t, h)`` identifica una observacion concreta: el mismo periodo
    objetivo evaluado al mismo numero de pasos. Es la unidad que permite
    comparar modelos sobre exactamente las mismas observaciones.
    """
    por_modelo: dict[str, dict[tuple[int, int], float]] = {}
    for horizonte in horizontes:
        h = int(horizonte)
        for clave, resultado in backtesting_comparativo.items():
            if not clave.endswith(f"_h{h}") or not (resultado or {}).get("ejecutado"):
                continue
            predicciones = resultado.get("predicciones")
            if not isinstance(predicciones, pd.DataFrame) or predicciones.empty:
                continue
            if "Error" not in predicciones or "t" not in predicciones:
                continue
            nombre = clave[: -len(f"_h{h}")]
            destino = por_modelo.setdefault(nombre, {})
            for objetivo, error in zip(predicciones["t"], predicciones["Error"]):
                valor = _numero_finito(error)
                if np.isfinite(valor):
                    destino[(int(objetivo), h)] = float(valor)
    return por_modelo


def seleccionar_modelo_por_rmse_oos_global(
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
) -> str | None:
    """Elige el modelo que minimiza el RMSE fuera de muestra global (C-SEL-001).

        RMSE_global(m) = sqrt( SUM_{(t,h) in S} e(m,t,h)^2 / |S| )
        m* = argmin_m RMSE_global(m)

    donde ``S`` es la **muestra comun**: los pares ``(t, h)`` en los que todos
    los candidatos tienen un error finito. Comparar sumas sobre conjuntos
    distintos daria ventaja al que tuviera menos observaciones, de modo que la
    comparacion se hace sobre las mismas observaciones para todos. No se imputa
    nada, no se penaliza ningun faltante y no hay minimo de tamano.

    QUE SUSTITUYE. Hasta el 08-08-2026 la seleccion era el promedio del RMSE
    relativo al mejor de cada horizonte, **ponderado con peso 1/h**. Ese peso no
    tenia fuente: la justificacion era operativa -«la evidencia de corto plazo
    es mas confiable y mas usada»-, y cambiaba el modelo entregado. Era la
    ultima heuristica decisoria del producto.

    QUE GANA. La regla nueva no tiene ningun parametro libre. Minimiza la
    perdida cuadratica fuera de muestra realmente observada, que es la magnitud
    que el RMSE mide y sobre la que se construyen los errores relativos
    (Hyndman y Koehler, 2006; Tashman, 2000).

    PONDERACION IMPLICITA, DECLARADA. El RMSE global no es neutral entre
    horizontes, y conviene decir en que sentido no lo es. Cada observacion pesa
    igual, pero los horizontes largos aportan errores mayores: sobre el anexo de
    mayo de 2026, h=18 aporta el 2,6 % de las observaciones y hasta el 8,8 % de
    la suma de cuadrados. El peso, por tanto, lo pone la magnitud del error
    medido, no una constante elegida. Es la direccion contraria a la de 1/h.

    DESEMPATE. Ante empate exacto en coma flotante gana el primer candidato en
    el orden de aparicion del banco, que es estable y reproducible. No se
    prefiere por identidad, complejidad, horizonte ni ninguna metrica auxiliar.

    Si la muestra comun queda vacia devuelve ``None``.

    CORREGIDO 18-08-2026 (H-8, auditoria final V-CODEX-R2). Este parrafo decia
    que, en ese caso, "el llamador cae... en la seleccion por horizonte, que
    es el camino que ya existia". Eso describia `_modelo_trayectoria_consistente`
    (la regla ponderada 1/h, retirada el 08-08-2026), pero el unico llamador
    vigente, `_modelo_consistente_desde_comparativo`, no tiene ningun
    mecanismo de reserva: si esta funcion devuelve ``None``, el llamador
    tambien devuelve ``None``. No existe una "seleccion por horizonte" a la
    que caer.
    """
    errores_por_modelo = _errores_oos_por_par(backtesting_comparativo, horizontes)
    if not errores_por_modelo:
        return None
    # Orden de aparicion en el banco: estable y reproducible.
    candidatos = list(errores_por_modelo)
    comunes: set[tuple[int, int]] | None = None
    for nombre in candidatos:
        pares = set(errores_por_modelo[nombre])
        comunes = pares if comunes is None else (comunes & pares)
    if not comunes:
        return None

    # P0-D, 14-08-2026. La DECISION se toma sobre la suma exacta de cuadrados; el
    # RMSE flotante queda solo como valor reportado. Ver `_sse_exacto` para la
    # derivacion: con la misma muestra comun y el mismo n, argmin RMSE = argmin
    # SSE, de modo que la metrica no cambia y el ganador deja de depender de como
    # redondee la raiz. Se conserva el desempate historico -primer candidato en el
    # orden de aparicion del banco- y solo se aplica ante igualdad EXACTA.
    mejor_nombre: str | None = None
    mejor_sse: Fraction | None = None
    for nombre in candidatos:
        errores = errores_por_modelo[nombre]
        valores = [errores[par] for par in comunes]
        # Los errores ya se filtraron por finitud al extraerlos; se comprueba
        # igualmente, porque un candidato no finito no puede ganar.
        if not all(math.isfinite(float(v)) for v in valores):
            continue
        sse = _sse_exacto(valores)
        if mejor_sse is None or sse < mejor_sse:
            mejor_nombre, mejor_sse = nombre, sse
    return mejor_nombre


def _modelo_consistente_desde_comparativo(
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
) -> str | None:
    """Variante que puntua directamente sobre el backtesting comparativo.

    Permite fijar el modelo antes de evaluar los horizontes, de modo que la
    clasificación de admisibilidad, las métricas, los intervalos y la
    trayectoria correspondan todos al mismo modelo.
    """
    # C-SEL-001: la seleccion es el minimo RMSE fuera de muestra global sobre la
    # muestra comun. Sustituye desde el 08-08-2026 al promedio ponderado con
    # peso 1/h, que era la ultima heuristica decisoria sin fuente del producto.
    return seleccionar_modelo_por_rmse_oos_global(backtesting_comparativo, horizontes)


def _modelo_trayectoria_consistente(evaluaciones: list[dict[str, Any]]) -> str | None:
    """RETIRADA COMO REGLA DE SELECCION el 08-08-2026. Se conserva por historia.

    Elegia un unico modelo para toda la trayectoria puntuando cada uno por su
    RMSE relativo al mejor de cada horizonte y promediando **con peso 1/h**.

    La consistencia de trayectoria que esta funcion introdujo -que el modelo sea
    una propiedad de la serie y no del horizonte que el usuario pida- **se
    conserva y sigue siendo obligatoria**; lo que se retira es la ponderacion.
    El peso `1/h` no tenia fuente: su justificacion era operativa y cambiaba el
    modelo entregado, de modo que era una heuristica decisoria.

    La sustituye `seleccionar_modelo_por_rmse_oos_global`, que minimiza la
    perdida cuadratica fuera de muestra realmente observada, sobre la muestra
    comun a todos los candidatos y sin ningun parametro libre.

    **Ya no la llama nadie en la ruta productiva.** Se mantiene definida porque
    la comparacion entre las dos reglas es parte del registro de auditoria: la
    medicion del 08-08-2026 sobre las diez series del anexo esta en
    `CIERRE_FINAL_H9_RMSE_GLOBAL_SAVIP_2026-08-08`.
    """
    relevantes = [
        ev
        for ev in evaluaciones
        if int(ev.get("horizonte", 0) or 0) >= 1 and ev.get("backtesting_por_modelo")
    ]
    if not relevantes:
        return None

    suma: dict[str, float] = {}
    peso_total: dict[str, float] = {}
    apariciones: dict[str, int] = {}
    for ev in relevantes:
        horizonte = int(ev.get("horizonte", 0) or 0)
        rmse_por_modelo: dict[str, float] = {}
        for nombre, bt in (ev.get("backtesting_por_modelo") or {}).items():
            valor = _numero_finito(((bt or {}).get("metricas") or {}).get("rmse"))
            if np.isfinite(valor) and valor > 0:
                rmse_por_modelo[str(nombre)] = float(valor)
        if not rmse_por_modelo:
            continue
        mejor = min(rmse_por_modelo.values())
        peso = 1.0 / float(horizonte)
        for nombre, valor in rmse_por_modelo.items():
            suma[nombre] = suma.get(nombre, 0.0) + peso * (valor / mejor)
            peso_total[nombre] = peso_total.get(nombre, 0.0) + peso
            apariciones[nombre] = apariciones.get(nombre, 0) + 1

    if not suma:
        return None
    # Solo compiten modelos presentes en todos los horizontes considerados.
    cobertura = max(apariciones.values())
    elegibles = {
        n: suma[n] / peso_total[n]
        for n in suma
        if apariciones[n] == cobertura and peso_total[n] > 0
    }
    if not elegibles:
        elegibles = {n: suma[n] / peso_total[n] for n in suma if peso_total[n] > 0}
    return min(elegibles, key=elegibles.get) if elegibles else None


def _puntaje_rmse_ponderado(
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
    nombre: str,
) -> float:
    """RMSE relativo al mejor modelo de cada horizonte, promediado con peso 1/h.

    Misma métrica que usa `_modelo_trayectoria_consistente`; aquí se calcula
    para un modelo concreto, para ordenar los benchmarks de respaldo del mas
    al menos conservador según el error demostrado fuera de muestra.
    """
    suma = 0.0
    peso_total = 0.0
    for horizonte in horizontes:
        por_modelo = _backtesting_por_modelo_horizonte(backtesting_comparativo, int(horizonte))
        rmse_por_modelo: dict[str, float] = {}
        for otro, bt in por_modelo.items():
            valor = _numero_finito(((bt or {}).get("metricas") or {}).get("rmse"))
            if np.isfinite(valor) and valor > 0:
                rmse_por_modelo[str(otro)] = float(valor)
        valor_modelo = rmse_por_modelo.get(str(nombre))
        if valor_modelo is None:
            continue
        mejor = min(rmse_por_modelo.values())
        peso = 1.0 / float(horizonte)
        suma += peso * (valor_modelo / mejor)
        peso_total += peso
    return float(suma / peso_total) if peso_total > 0 else float("inf")


def _aplicar_salvaguarda_benchmarks(
    evaluaciones: list[dict[str, Any]],
    modelo_consistente: str | None,
    candidatos: list[dict],
    backtesting_comparativo: dict[str, dict],
    horizontes: tuple[int, ...],
    serie_trabajo: pd.DataFrame,
    validacion_serie: dict,
    outliers: list[dict],
    t_ultimo: int,
    y_obs: np.ndarray,
    anio_base: int,
    horizonte_solicitado: int,
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    """Salvaguarda por benchmark: DIAGNOSTICO, no sustitucion.

    Se conserva un unico modelo principal por serie: el que eligio la seleccion
    por RMSE fuera de muestra. Si ese modelo produce un horizonte no
    recomendable por causas atribuibles al modelo (no por falta de ventanas de
    validacion), se reevaluan Drift y Naive y se publica hasta donde llegaria
    cada uno. Esa medicion es INFORMACION, no una decision: la funcion devuelve
    siempre las evaluaciones y el modelo que recibio, sin cambiarlos.

    CORREGIDO 18-08-2026 (PS-01). Hasta esta fecha este docstring afirmaba que
    el primer benchmark que ampliara el horizonte «sustituye al principal para
    TODA la trayectoria». Esa conducta se retiro en el CIERRE del 08-08-2026
    -su criterio de aceptacion era `h_bench > h_antes`, mas horizonte y no menos
    error, sin fuente que lo respaldara- y el cuerpo de la funcion ya no la
    implementa. El docstring habia quedado describiendo la version anterior.
    """
    h_antes = _mayor_horizonte_permitido(evaluaciones)
    salvaguarda: dict[str, Any] = {
        "intentada": False,
        "activada": False,
        "modelo_principal": modelo_consistente,
        "razon_fallo_principal": "",
        "benchmarks_evaluados": [],
        "modelo_final": modelo_consistente,
        "h_max_antes": int(h_antes),
        "h_max_despues": int(h_antes),
    }
    fallo = next(
        (
            ev
            for ev in evaluaciones
            if ev.get("no_recomendable") and not ev.get("bloqueo_por_datos")
        ),
        None,
    )
    if fallo is None:
        return evaluaciones, modelo_consistente, salvaguarda

    salvaguarda["intentada"] = True
    detalle_fallo = str(fallo.get("mensaje_horizonte") or "").strip() or "; ".join(
        str(r) for r in fallo.get("razones_horizonte", [])
    )
    salvaguarda["razon_fallo_principal"] = f"h={fallo.get('horizonte')}: {detalle_fallo}".strip()

    disponibles = {c.get("nombre") for c in candidatos if "predict" in c}
    respaldos = [n for n in ("drift", "naive") if n in disponibles and n != modelo_consistente]
    puntajes = {
        nombre: _puntaje_rmse_ponderado(backtesting_comparativo, horizontes, nombre)
        for nombre in respaldos
    }
    respaldos.sort(key=lambda nombre: puntajes[nombre])
    objetivo = (
        min(int(horizonte_solicitado), max(int(h) for h in horizontes))
        if horizontes
        else int(horizonte_solicitado)
    )

    mejor: tuple[int, list[dict[str, Any]], str | None] = (int(h_antes), evaluaciones, modelo_consistente)
    for nombre in respaldos:
        evals_bench = _evaluar_horizontes_proyeccion(
            candidatos=candidatos,
            backtesting_comparativo=backtesting_comparativo,
            horizontes=horizontes,
            serie_trabajo=serie_trabajo,
            validacion_serie=validacion_serie,
            outliers=outliers,
            t_ultimo=t_ultimo,
            y_obs=y_obs,
            anio_base=anio_base,
            modelo_fijo=nombre,
        )
        h_bench = _mayor_horizonte_permitido(evals_bench)
        registro: dict[str, Any] = {
            "nombre": nombre,
            "rmse_ponderado": float(puntajes[nombre]),
            "h_max_admisible": int(h_bench),
            "cumple": bool(h_bench > h_antes),
        }
        if h_bench <= h_antes:
            primer_fallo = next((ev for ev in evals_bench if ev.get("no_recomendable")), None)
            registro["razones"] = [
                str(r) for r in (primer_fallo or {}).get("razones_horizonte", [])
            ][:4]
        salvaguarda["benchmarks_evaluados"].append(registro)
        if h_bench > mejor[0]:
            mejor = (int(h_bench), evals_bench, nombre)
        if h_bench >= objetivo:
            break

    # CIERRE 08-08-2026: la salvaguarda deja de SUSTITUIR. Sigue evaluando los
    # benchmarks y publicando lo que encuentra, pero no cambia el modelo.
    #
    # Su criterio de aceptacion era `h_bench > h_antes`: mas horizonte, no menos
    # error. No tiene fuente, y sobre el anexo de mayo entregaba un Drift con
    # RMSE peor que el modelo descartado en h=3, 6, 12 y 18 -hasta un 78 % peor
    # en h=18-, ademas de fabricar los benchmarks que V-12 despues castigaba.
    #
    # Con la puerta de 1,25 retirada su disparo casi desaparece; lo que queda es
    # el diagnostico, que es informacion util: dice que horizontes no cubre el
    # modelo principal y hasta donde llegaria un benchmark. El modelo entregado
    # es siempre el que la seleccion por desempeno OOS eligio.
    salvaguarda["h_max_benchmark_disponible"] = int(mejor[0])
    salvaguarda["benchmark_habria_ampliado"] = bool(mejor[0] > h_antes)
    salvaguarda["politica"] = "diagnostico: la salvaguarda no sustituye el modelo"
    return evaluaciones, modelo_consistente, salvaguarda


def _seleccionar_horizonte_permitido(
    evaluaciones: list[dict[str, Any]],
    horizonte_solicitado: int,
) -> dict[str, Any] | None:
    permitidas = [item for item in evaluaciones if item.get("permitido") and int(item.get("horizonte", 0)) <= horizonte_solicitado]
    if not permitidas:
        return None
    permitidas.sort(key=lambda item: int(item["horizonte"]))
    return permitidas[-1]


def determinar_horizonte_maximo_estadistico(
    serie: pd.DataFrame | None,
    modelos: list[dict[str, Any]] | None,
    backtesting: dict[str, Any] | None,
    intervalos: list[dict[str, Any]] | dict[str, Any] | None,
    diagnosticos: dict[str, Any] | None,
    horizonte_solicitado: int | None = None,
    metadatos_auditoria: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Consolida la decisión dinámica de horizonte máximo.

    Acepta las evaluaciones por horizonte generadas por el servicio. Si se entrega
    otra estructura, devuelve un resumen conservador sin bloquear informes.
    """
    evaluaciones = intervalos if isinstance(intervalos, list) else []
    horizonte_solicitado = int(horizonte_solicitado or 0)
    trazabilidad = dict(metadatos_auditoria or {})
    estado_por_horizonte: list[dict[str, Any]] = _serializar_evaluaciones_horizonte(evaluaciones)
    no_recomendables = [item for item in estado_por_horizonte if item.get("no_recomendable")]
    estado_ordenado = sorted(
        estado_por_horizonte,
        key=lambda item: int(item.get("horizonte", 0) or 0),
    )
    horizontes_evaluados = [int(item.get("horizonte", 0) or 0) for item in estado_ordenado if item.get("horizonte") is not None]
    max_evaluado = max(horizontes_evaluados) if horizontes_evaluados else 0
    max_recomendado = _mayor_horizonte_con(estado_ordenado, "permitido_para_proyeccion_tecnica")
    max_admisible = _mayor_horizonte_permitido(estado_ordenado)
    max_con_cautela = _ultimo_horizonte_por_clasificacion(
        estado_ordenado,
        {"tecnica_cautela", "extendida_cautela"},
    )
    max_escenario_puro = _ultimo_horizonte_por_clasificacion(
        estado_ordenado,
        {"escenario_alta_incertidumbre", "escenario_estadistico"},
    )
    horizontes_solo_escenario = [
        int(item["horizonte"])
        for item in estado_ordenado
        if item.get("permitido_como_escenario") and not item.get("permitido_para_proyeccion_tecnica")
    ]
    primer_no_viable = min((int(item["horizonte"]) for item in no_recomendables if item.get("horizonte") is not None), default=0)
    maximo_busqueda = int(trazabilidad.get("horizonte_maximo_busqueda_configurado") or max(max_evaluado, horizonte_solicitado))
    maximo_datos = int(trazabilidad.get("horizonte_maximo_evaluable_por_datos") or max_evaluado)
    horizontes_no_evaluados = list(range(max_evaluado + 1, maximo_busqueda + 1)) if max_evaluado else []
    horizonte_solicitado_cubierto = horizonte_solicitado in horizontes_evaluados
    if primer_no_viable:
        # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). El identificador seguia siendo
        # `primer_horizonte_no_viable` bajo la etiqueta «parada», y el texto se
        # publica como primera frase de `mensaje_ui` y `mensaje_informe`. Pero la
        # evaluacion NO se detiene ahi desde que se retiro el prefijo: sigue y
        # puede permitir horizontes posteriores. Se declara como hueco.
        razon_parada = (
            f"La trayectoria tiene un hueco: h={primer_no_viable} es el primer horizonte no "
            "disponible. La evaluación continúa y los horizontes posteriores conservan su "
            "propia evidencia fuera de muestra."
        )
        tipo_parada = "hueco_en_trayectoria"
    elif max_evaluado >= maximo_datos:
        # CIERRE GLOBAL, 14-08-2026 (control 18/64/60). La condicion anterior era
        # `max_evaluado >= maximo_datos and maximo_datos < maximo_busqueda`, y
        # tenia sentido cuando `maximo_busqueda` era el cap 30: entonces el techo
        # por datos podia quedar por debajo de un tope configurado, y distinguirlos
        # era informativo. Retirado el cap en P0-H, ambos salen de
        # `_limites_auditoria_horizontes` y COINCIDEN siempre, de modo que esta
        # rama no se tomaba nunca y el mensaje caia en la de «limite operativo».
        # Resultado: con una serie de 72 observaciones la aplicacion afirmaba
        # haberse detenido «al alcanzar el limite operativo configurado» en h=64,
        # cuando el limite operativo es 60 y no interviene en la rejilla. Era una
        # afirmacion falsa en una salida que el usuario lee.
        razon_parada = "Evaluación detenida por falta de evidencia fuera de muestra suficiente."
        tipo_parada = "evidencia_oos_insuficiente"
    elif max_evaluado >= maximo_busqueda:
        razon_parada = "Evaluación detenida al alcanzar el límite operativo configurado."
        tipo_parada = "limite_operativo"
    else:
        razon_parada = "Evaluación detenida por una limitación técnica documentada."
        tipo_parada = "limitacion_tecnica"
    advertencia_metodologica = ""
    if not primer_no_viable and tipo_parada == "evidencia_oos_insuficiente":
        advertencia_metodologica = (
            "No se identificó un horizonte no viable dentro de la grilla evaluada, "
            "pero la evaluación se detuvo por falta de evidencia fuera de muestra suficiente; "
            "por tanto, no se puede afirmar validez para horizontes superiores."
        )
    elif not primer_no_viable and tipo_parada == "limite_operativo":
        advertencia_metodologica = (
            "No se identificó un horizonte no viable dentro de la grilla evaluada, "
            "pero la evaluación alcanzó el límite operativo configurado; este límite no "
            "constituye por sí mismo una recomendación estadística."
        )
    elif not primer_no_viable and tipo_parada == "limitacion_tecnica":
        advertencia_metodologica = (
            "No se identificó un horizonte no viable dentro de la grilla evaluada, "
            "pero una limitación técnica detuvo la evaluación; por tanto, no se puede "
            "afirmar validez para horizontes superiores."
        )
    razones: list[str] = []
    advertencias: list[str] = []
    advertencias_por_horizonte: list[str] = []
    # H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Se
    # retiran las dos ramas `elif ... permitido_como_escenario`: con
    # `permitido_como_escenario == permitido_para_proyeccion_tecnica` siempre
    # (mismo invariante verificado en `_estructurar_resultado_horizontes` y de
    # forma empirica sobre 1980 evaluaciones de horizonte), la condicion
    # "permitido_como_escenario and not permitido_para_proyeccion_tecnica" es
    # `tecnico and not tecnico`: nunca True. El texto "permitido solo como
    # escenario de alta incertidumbre" y la accion "permitir como escenario"
    # nunca llegaban a publicarse por esta via.
    for item in estado_por_horizonte:
        if item.get("permitido_para_proyeccion_tecnica"):
            advertencias.append(f"h={item.get('horizonte')} permitido como {item.get('tipo_uso')}.")
        elif item.get("mensaje"):
            advertencias_por_horizonte.append(str(item["mensaje"]))
    item_global = _item_horizonte_global(estado_por_horizonte, horizonte_solicitado, max_recomendado, max_admisible)
    if not max_admisible:
        accion = "bloquear"
        uso = "No recomendable"
    elif horizonte_solicitado and horizonte_solicitado > max_admisible:
        accion = "restringir"
        uso = f"Usar hasta {max_admisible} meses con evidencia disponible."
    elif item_global and int(item_global.get("horizonte", 0) or 0) >= 7:
        accion = "permitir con cautela"
        uso = item_global.get("tipo_uso") or "Proyección extendida con cautela."
    else:
        accion = "permitir"
        uso = (item_global or {}).get("tipo_uso") or _tipo_uso_horizonte(max_recomendado or max_admisible)
    if accion == "bloquear":
        horizonte_finalmente_permitido = 0
    elif horizonte_solicitado and horizonte_solicitado <= max_admisible:
        horizonte_finalmente_permitido = horizonte_solicitado
    else:
        horizonte_finalmente_permitido = max_admisible
    no_rec_txt = ", ".join(f"h={item.get('horizonte')}" for item in no_recomendables)
    if horizontes_no_evaluados:
        motivo_no_evaluados = (
            "no evaluados después del primer horizonte no viable"
            if primer_no_viable
            else "no evaluados por evidencia OOS insuficiente"
        )
        no_rec_txt = (
            (no_rec_txt + ", " if no_rec_txt else "")
            + f"h={horizontes_no_evaluados[0]}..h={horizontes_no_evaluados[-1]} {motivo_no_evaluados}"
        )
    if no_rec_txt:
        mensaje_no_recomendables = f"Horizontes no recomendables o no defendibles: {no_rec_txt}."
    elif max_evaluado:
        mensaje_no_recomendables = (
            f"No se identificaron horizontes no recomendables dentro de la grilla mensual evaluada h=1..h={max_evaluado}. "
            "Horizontes superiores no deben asumirse automáticamente como defendibles sin backtesting específico."
        )
    else:
        mensaje_no_recomendables = "No hubo horizontes evaluados con evidencia suficiente."
    return {
        "horizonte_solicitado": horizonte_solicitado,
        "horizontes_evaluados": horizontes_evaluados,
        "horizonte_maximo_evaluado": int(max_evaluado),
        "horizonte_maximo_recomendado": int(max_recomendado),
        # P0-H, 12-08-2026: el prefijo consecutivo NO es un criterio estadistico.
        # Ninguna fuente exige que los horizontes con evidencia aceptable formen
        # un prefijo desde h=1; FPP3 5.10 publica UNA TABLA por horizonte.
        #
        # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). CORREGIDAS LAS DOS BASES. El
        # 16-08-2026 se retiro el prefijo del CALCULO -ambos maximos pasaron a ser
        # `max(validos)`-, pero estos dos textos siguieron describiendo la conducta
        # anterior: «ultimo mes de la racha continua desde h=1» y «trayectoria
        # mensual sin huecos». Se publican en la interfaz y en los informes, de
        # modo que el producto declaraba una regla de continuidad que ya no aplica
        # y que, si aplicara, seria la cascada retirada. Ahora dicen lo que el
        # codigo hace.
        "base_horizonte_maximo_recomendado": (
            "Mayor horizonte permitido como proyección técnica por su propia evidencia fuera "
            "de muestra. No exige que los horizontes anteriores lo estén: puede haber huecos, "
            "y se declaran en primer_horizonte_no_viable y en estado_por_horizonte"
        ),
        "horizonte_maximo_publicable_continuo": int(max_admisible),
        "base_horizonte_maximo_publicable_continuo": (
            "Mayor horizonte permitido -técnico o escenario- por su propia evidencia. El "
            "nombre conserva «continuo» por compatibilidad del contrato, pero la continuidad "
            "dejó de exigirse: si la trayectoria tiene huecos se publican como no disponibles "
            "y no se interpola ningún valor"
        ),
        "evidencia_horizonte_maximo_recomendado": _evidencia_horizonte(estado_ordenado, max_recomendado),
        "maximo_recomendado_es_limite_observado": bool(
            max_recomendado and max_recomendado == max_evaluado and not primer_no_viable
        ),
        "horizonte_maximo_con_cautela": int(max_con_cautela),
        "horizonte_maximo_escenario": int(max_escenario_puro),
        "horizonte_maximo_permitido_como_escenario": int(max_escenario_puro),
        # P0-H, 17-08-2026 (V-CODEX-R3): «consecutiva antes del corte» describia el
        # recorrido por prefijo de `_ultimo_horizonte_por_clasificacion`, retirado.
        "base_horizonte_maximo_escenario": (
            "Mayor horizonte clasificado como escenario por su propia evidencia; no exige que "
            "los anteriores lo estén"
        ),
        "evidencia_horizonte_maximo_escenario": _evidencia_horizonte(estado_ordenado, max_escenario_puro),
        "horizonte_maximo_admisible": int(max_admisible),
        "horizonte_maximo_permitido": int(max_admisible),
        # ponytail: la clave genérica conserva el significado histórico de "recomendado";
        # el máximo de escenario ya tiene una clave explícita y no debe sustituirlo.
        "horizonte_maximo": int(max_recomendado),
        "horizonte_finalmente_permitido": int(horizonte_finalmente_permitido),
        "primer_horizonte_no_viable": int(primer_no_viable),
        "horizontes_solo_escenario": horizontes_solo_escenario,
        "horizontes_no_recomendables": [int(item["horizonte"]) for item in no_recomendables if item.get("horizonte") is not None],
        "horizontes_no_evaluados": horizontes_no_evaluados,
        "horizontes_no_evaluados_no_recomendables": horizontes_no_evaluados,
        "razon_parada": razon_parada,
        "tipo_parada": tipo_parada,
        "advertencia_metodologica_horizontes": advertencia_metodologica,
        "horizonte_parada": int(max_evaluado),
        "horizonte_maximo_evaluable_por_datos": int(maximo_datos),
        "horizonte_maximo_busqueda_configurado": int(maximo_busqueda),
        "horizonte_solicitado_cubierto": bool(horizonte_solicitado_cubierto),
        "trazabilidad": {
            **trazabilidad,
            "horizontes_efectivamente_evaluados": horizontes_evaluados,
            "razon_parada": razon_parada,
            "tipo_parada": tipo_parada,
            "advertencia_metodologica_horizontes": advertencia_metodologica,
            "horizonte_solicitado_cubierto": bool(horizonte_solicitado_cubierto),
        },
        "mensaje_no_recomendables": mensaje_no_recomendables,
        "estado_por_horizonte": estado_por_horizonte,
        "evaluaciones": estado_por_horizonte,
        "razones": _deduplicar_local(razones),
        "advertencias": _deduplicar_local(advertencias),
        "advertencias_por_horizonte": _deduplicar_local(advertencias_por_horizonte),
        "tipo_uso_recomendado": uso,
        "accion": accion,
        "bloquear": accion == "bloquear",
        "mensaje_ui": (
            f"{razon_parada} "
            f"Máximo recomendado: {max_recomendado or 'no identificado'}. "
            f"Máximo con cautela: {max_con_cautela or 'no identificado'}. "
            f"Máximo clasificado como escenario: {max_escenario_puro or 'no identificado'}. "
            f"Máximo evaluado: {max_evaluado} meses. "
            f"{advertencia_metodologica} "
            f"{mensaje_no_recomendables}"
        ),
        "mensaje_informe": (
            f"{razon_parada} "
            f"Con la evidencia disponible, el máximo recomendado es "
            f"{f'h={max_recomendado}' if max_recomendado else 'no identificado'} y "
            f"el máximo clasificado como escenario es "
            f"{f'h={max_escenario_puro}' if max_escenario_puro else 'no identificado'}. "
            f"El máximo evaluado fue h={max_evaluado}; este valor no sustituye la clasificación. "
            f"{advertencia_metodologica} "
            f"{mensaje_no_recomendables}"
        ),
        "mensaje": (
            f"Horizonte máximo recomendado"
            f"{' dentro de la grilla evaluada' if max_recomendado and max_recomendado == max_evaluado and not primer_no_viable else ''}: "
            f"{max_recomendado or 'no identificado'}; "
            f"horizonte máximo clasificado como escenario: {max_escenario_puro or 'no identificado'}; "
            f"horizonte máximo evaluado: {max_evaluado} meses. {razon_parada} {advertencia_metodologica}"
        ),
    }


def _serializar_evaluaciones_horizonte(evaluaciones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    salida = []
    for item in evaluaciones:
        metricas = (item.get("backtesting") or {}).get("metricas", {})
        metricas_por_modelo: dict[str, dict[str, Any]] = {}
        for codigo, bt_modelo in (item.get("backtesting_por_modelo") or {}).items():
            met_modelo = (bt_modelo or {}).get("metricas") or {}
            if met_modelo:
                metricas_por_modelo[str(codigo)] = dict(met_modelo)
        evaluacion_intervalos = item.get("evaluacion_intervalos") or {}
        modelo_obj = item.get("modelo") or {}
        modelo_visible = modelo_obj.get("nombre_visible") if isinstance(modelo_obj, dict) else str(modelo_obj)
        errores_extremos = metricas.get("porcentaje_errores_extremos")
        permitido = bool(item.get("permitido"))
        mensaje = item.get("mensaje_horizonte") or ""
        permitido_tecnico = bool(item.get("permitido_para_proyeccion_tecnica", permitido))
        permitido_escenario = bool(item.get("permitido_como_escenario", permitido))
        no_recomendable = bool(item.get("no_recomendable", not permitido))
        if no_recomendable:
            motivo = mensaje or "evidencia insuficiente por horizonte"
        else:
            # H-1A, 18-08-2026 (auditoria final V-CODEX-R2). Fallback solo para
            # datos sin `mensaje_horizonte` propio; ya no cita el intervalo
            # retirado como fundamento.
            motivo = mensaje or "backtesting y evidencia fuera de muestra suficientes para proyección técnica"
        salida.append(
            {
                "horizonte": item.get("horizonte"),
                "permitido": permitido,
                "permitido_para_proyeccion_tecnica": permitido_tecnico,
                "permitido_como_escenario": permitido_escenario,
                "no_recomendable": no_recomendable,
                "decision": item.get("decision") or ("Permitido para proyección técnica" if permitido else "No recomendable"),
                "clasificacion": item.get("clasificacion") or ("no_viable" if no_recomendable else "tecnica_cautela"),
                "estado": item.get("estado"),
                "tipo_uso": item.get("tipo_uso") or _tipo_uso_horizonte(int(item.get("horizonte", 1) or 1)),
                "modelo": modelo_visible,
                "modelo_evaluado": modelo_visible,
                "modelo_final_aplicado": modelo_visible,
                "modelo_final_difiere_ganador": False,
                "modelo_evaluado_codigo": modelo_obj.get("nombre") if isinstance(modelo_obj, dict) else "",
                "modelo_final_codigo": modelo_obj.get("nombre") if isinstance(modelo_obj, dict) else "",
                "metricas_reportadas": "modelo_ganador_por_horizonte",
                "metricas_por_modelo": metricas_por_modelo,
                "metricas_modelo_ganador": dict(metricas),
                "mae": metricas.get("mae"),
                "rmse": metricas.get("rmse"),
                "mape": metricas.get("mape"),
                "smape": metricas.get("smape"),
                "mase": metricas.get("mase"),
                "iteraciones": int((item.get("backtesting") or {}).get("iteraciones") or metricas.get("iteraciones") or 0),
                "sesgo_medio": metricas.get("sesgo_medio", metricas.get("error_medio")),
                "estabilidad_error": metricas.get("estabilidad_error"),
                "errores_extremos": errores_extremos,
                # D-8: cantidad y detalle por observacion, salida descriptiva.
                "errores_extremos_cantidad": (metricas.get("errores_extremos") or {}).get("cantidad"),
                "errores_extremos_evaluados": (metricas.get("errores_extremos") or {}).get("n"),
                "errores_extremos_detalle": metricas.get("errores_extremos") or {},
                "ancho_relativo_80": evaluacion_intervalos.get("ancho_relativo_80_maximo"),
                "ancho_relativo_95": evaluacion_intervalos.get("ancho_relativo_95_maximo", evaluacion_intervalos.get("ancho_relativo_maximo")),
                "ancho_relativo_intervalo": evaluacion_intervalos.get("ancho_relativo_95_maximo", evaluacion_intervalos.get("ancho_relativo_maximo")),
                "ic95_relativo": evaluacion_intervalos.get("ancho_relativo_95_maximo", evaluacion_intervalos.get("ancho_relativo_maximo")),
                "mensaje": item.get("mensaje_horizonte"),
                "motivo": motivo,
                "razon_decision": motivo,
                "recomendacion": item.get("mensaje_horizonte"),
                "confianza": item.get("confianza"),
            }
        )
    return salida


def _item_horizonte_global(
    estado_por_horizonte: list[dict[str, Any]],
    horizonte_solicitado: int,
    max_recomendado: int,
    max_admisible: int,
) -> dict[str, Any] | None:
    """El uso global se basa en el horizonte solicitado/permitido, no en el mayor evaluado."""
    if not estado_por_horizonte:
        return None
    por_h = {int(item.get("horizonte", 0) or 0): item for item in estado_por_horizonte}
    if horizonte_solicitado in por_h and (
        por_h[horizonte_solicitado].get("permitido_para_proyeccion_tecnica")
        or por_h[horizonte_solicitado].get("permitido_como_escenario")
    ):
        return por_h[horizonte_solicitado]
    objetivo = max_recomendado or max_admisible
    return por_h.get(objetivo)


def _mayor_horizonte_con(estado_por_horizonte: list[dict[str, Any]], clave: str) -> int:
    """Mayor horizonte que cumple `clave` con su propia evidencia.

    P0-H, 16-08-2026 (V-CODEX-3). Esta función también recorría desde h=1 y
    cortaba en el primer horizonte que no cumpliera. Alimenta
    `horizonte_maximo_recomendado`, que se **publica** en la interfaz y en los
    informes como «máximo recomendado».

    Aunque no niega la entrega —eso lo hacía `_mayor_horizonte_permitido`—,
    dejarlo como prefijo producía una salida contradictoria: con
    h1 técnico, h2 no viable y h3-h4 técnicos, la aplicación entregaría h=4 y a
    la vez publicaría «máximo recomendado: 1».

    Y como enunciado sobre hasta dónde usar el resultado, es una **reducción de
    horizonte**, que exige sustento igual que un bloqueo. Un prefijo continuo no
    lo tiene: cada horizonte se evalúa con su propia muestra de errores.

    Se conserva `primer_horizonte_no_viable`, que sí informa dónde se rompe la
    continuidad, y cada horizonte sigue publicando su estado individual.
    """
    validos = [
        int(item.get("horizonte", 0) or 0)
        for item in estado_por_horizonte
        if int(item.get("horizonte", 0) or 0) > 0 and item.get(clave)
    ]
    return max(validos) if validos else 0


def _mayor_horizonte_permitido(estado_por_horizonte: list[dict[str, Any]]) -> int:
    """Mayor horizonte con evidencia propia suficiente para permitirlo.

    P0-H, 16-08-2026 (auditoria independiente V-CODEX-3). Esta funcion recorria
    los horizontes desde h=1 y **cortaba en el primer hueco o fallo**. Su
    resultado gobierna `max_admisible`, que restringe el horizonte permitido y,
    si difiere del solicitado, hace que la ruta devuelva
    `proyeccion_generada=False`. En consecuencia, con h1 PASS, h2 FAIL y h3 PASS,
    el horizonte 3 quedaba vetado **por el fallo de h2**, no por su propia
    evidencia.

    Ninguna fuente exige que los horizontes validos formen un prefijo. FPP3
    §5.10 publica UNA TABLA POR HORIZONTE, y cada uno tiene su propia muestra de
    errores fuera de muestra: el desempeño en h=2 no es evidencia sobre h=3. La
    etiqueta «continuidad de producto» describia una preferencia de
    presentacion, no un criterio estadistico, y no puede negar una entrega.

    El contrato pasa a ser: **cada horizonte se juzga con su propia evidencia**.
    Se devuelve el mayor horizonte permitido, exista o no un hueco antes.

    La continuidad NO desaparece como informacion: los horizontes no permitidos
    siguen marcados uno a uno en `estado_por_horizonte`, y la interfaz y los
    informes los comunican. Lo que desaparece es su poder de veto sobre los
    posteriores.
    """
    permitidos = [
        int(item.get("horizonte", 0) or 0)
        for item in estado_por_horizonte
        if item.get("permitido_para_proyeccion_tecnica")
        or item.get("permitido_como_escenario")
    ]
    return max(permitidos) if permitidos else 0


def _ultimo_horizonte_por_clasificacion(
    estado_por_horizonte: list[dict[str, Any]],
    clasificaciones: set[str],
) -> int:
    """Mayor horizonte cuya clasificación propia está en ``clasificaciones``.

    P0-H, 17-08-2026 (V-CODEX-R3, residual 3). Era el TERCER recorrido por
    prefijo, y el único que sobrevivió a la remediación del 16-08-2026: partía de
    h=1 y cortaba en el primer horizonte que no encajara. Alimenta
    ``horizonte_maximo_escenario`` y ``horizonte_maximo_con_cautela``, ambos
    publicados en la interfaz, en el CSV y en los informes.

    Con h1 técnico, h2 no viable y h3 escenario admisible, el corte en h2 hacía
    que se publicara «horizonte máximo clasificado como escenario: no
    identificado» mientras h3 se entregaba como escenario. Mismo defecto que ya se
    corrigió en los otros dos máximos, en un descriptivo distinto.

    Ninguna fuente exige contigüidad. Se devuelve el mayor horizonte que cumple,
    exista o no un hueco antes; el hueco se comunica por separado.
    """
    validos = [
        int(item.get("horizonte", 0) or 0)
        for item in estado_por_horizonte
        if int(item.get("horizonte", 0) or 0) > 0
        and not item.get("no_recomendable")
        and str(item.get("clasificacion", "")) in clasificaciones
    ]
    return max(validos) if validos else 0


def _evidencia_horizonte(
    estado_por_horizonte: list[dict[str, Any]],
    horizonte: int,
) -> dict[str, Any]:
    if horizonte <= 0:
        return {}
    item = next(
        (
            fila
            for fila in estado_por_horizonte
            if int(fila.get("horizonte", 0) or 0) == int(horizonte)
        ),
        {},
    )
    return {
        "horizonte": int(horizonte),
        "clasificacion": item.get("clasificacion"),
        "estado": item.get("estado"),
        "decision": item.get("decision"),
        "razon": item.get("razon_decision") or item.get("motivo"),
    }


def _mensaje_horizonte_no_permitido(
    horizonte: int,
    modelo: dict[str, Any],
    razones: list[str],
    metricas: dict[str, Any],
    evaluacion_intervalos: dict[str, Any],
) -> str:
    """Redacta bloqueo por horizonte sin contaminar la factibilidad global."""
    nombre_modelo = modelo.get("nombre_visible") or modelo.get("nombre") or "modelo evaluado"
    ancho = _numero_finito(evaluacion_intervalos.get("ancho_relativo_95_maximo", evaluacion_intervalos.get("ancho_relativo_maximo")))
    detalles: list[str] = []
    # D-8: ya no existe bloqueo por proporcion de errores inusuales, de modo que
    # tampoco hay motivo de bloqueo redactado a partir de esa proporcion.
    if np.isfinite(ancho) and any("intervalos" in str(r).lower() for r in razones):
        detalles.append(f"IC95 relativo {ancho:.1%}")
    if not detalles:
        detalles = razones[:2] or ["evidencia estadística insuficiente"]
    motivo = "; ".join(str(d) for d in detalles)
    return (
        f"Horizonte h={horizonte} no permitido bajo {nombre_modelo}: {motivo}. "
        "Impacto: este resultado se reporta solo para ese horizonte y no bloquea otros horizontes permitidos."
    )


def _deduplicar_local(textos: list[str]) -> list[str]:
    salida: list[str] = []
    vistos: set[str] = set()
    for texto in textos:
        if texto is None:
            continue
        limpio = str(texto).strip()
        if limpio and limpio not in vistos:
            salida.append(limpio)
            vistos.add(limpio)
    return salida


def _categorizar_advertencias(
    validacion_serie: dict,
    outliers: list[dict],
    modelo: dict[str, Any],
    factibilidad: dict,
    horizonte_info: dict,
    evaluacion_intervalos: dict,
) -> dict[str, list[str]]:
    """Separa advertencias por origen para evitar mensajes contradictorios."""
    advertencias_datos = list(validacion_serie.get("advertencias", []))
    etiquetas_clasificacion = {
        "posible_atipico_aislado": "Posible valor atípico aislado",
        "posible_cambio_nivel": "Posible cambio de nivel",
        "posible_error_datos": "Posible error de datos (pico que revierte)",
    }
    for item in outliers:
        periodo = item.get("periodo", item.get("Periodo", ""))
        if not periodo:
            continue
        if str(item.get("severidad")) == "patron_calendario":
            advertencias_datos.append(
                f"Patron calendario de cambio de año en {periodo}; no se contabiliza como atípico."
            )
            continue
        etiqueta = etiquetas_clasificacion.get(
            str(item.get("clasificacion", "")), "Posible valor atípico"
        )
        advertencias_datos.append(f"{etiqueta} en {periodo}.")

    descartes_modelos = []
    for item in modelo.get("descartes_modelos", []) or []:
        nombre = item.get("nombre", "")
        razones = item.get("razones") or [item.get("razon", "")]
        for razon in razones:
            if razon:
                descartes_modelos.append(f"{nombre}: {razon}")

    seleccion = []
    comparacion = modelo.get("comparacion_benchmarks", {}) or {}
    rrmse_naive = _numero_finito(comparacion.get("rrmse_naive"))
    rrmse_drift = _numero_finito(comparacion.get("rrmse_drift"))
    # CIERRE 08-08-2026: la comparacion se hace contra 1, el punto de
    # equivalencia. El margen 1,10 era interno y sin fuente, y hacia que el
    # texto callara justo en el tramo 1,00-1,10, donde el metodo YA es peor.
    if np.isfinite(rrmse_naive) and rrmse_naive > 1.0:
        seleccion.append("El metodo seleccionado no mejora a naive en RMSE de backtesting.")
    if np.isfinite(rrmse_drift) and rrmse_drift > 1.0:
        seleccion.append("El metodo seleccionado no mejora a drift en RMSE de backtesting.")
    seleccion.extend(str(a) for a in (modelo.get("diagnostico_residuos", {}) or {}).get("alertas", []))

    horizonte = list((horizonte_info or {}).get("advertencias_por_horizonte", []))
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). `advertencias_intervalo` se
    # llenaba con `evaluacion_intervalos["advertencias"]` y `["razones"]`, es decir
    # con los motivos de la banda: «Al menos un limite del intervalo no es un
    # numero finito», «ancho relativo máximo 50,8 %». Es una categoría entera
    # dedicada a caracterizar el objeto que P0-C retiró, y viajaba a la interfaz y
    # a los informes. La categoría se conserva vacía -hay lectores que recorren
    # las seis claves y no deben tener que distinguir un caso especial- y su
    # contenido queda en `diagnostico_cobertura_no_publicado`, que no se publica.
    intervalo: list[str] = []
    factibilidad_global = [
        a for a in list(factibilidad.get("advertencias", []))
        if "no se permite proyección" not in str(a).lower()
    ]
    factibilidad_global.extend((horizonte_info or {}).get("razones", []))

    return {
        "advertencias_datos": _deduplicar_local(advertencias_datos),
        "advertencias_modelos_descartados": _deduplicar_local(descartes_modelos),
        "advertencias_modelo_seleccionado": _deduplicar_local(seleccion),
        "advertencias_horizonte": _deduplicar_local(horizonte),
        "advertencias_intervalo": _deduplicar_local(intervalo),
        "advertencias_factibilidad_global": _deduplicar_local(factibilidad_global),
    }


def _resultado_sin_proyeccion(
    periodo_solicitado: str,
    validacion_serie: dict,
    analisis_serie: dict,
    variables_derivadas: dict,
    outliers: list[dict],
    explicacion: str | None = None,
    factibilidad: dict | None = None,
    modelo: dict | None = None,
    candidatos: list[dict] | None = None,
    diagnostico_residuos: dict | None = None,
    backtesting: dict | None = None,
    backtesting_comparativo: dict | None = None,
    backtesting_por_modelo: dict[str, dict] | None = None,
    horizonte_solicitado: int | None = None,
    politica_modelos: dict[str, Any] | None = None,
    catalogo_modelos: list[dict[str, Any]] | None = None,
    horizonte_info: dict[str, Any] | None = None,
) -> dict:
    """Construye un resultado serializable cuando no es defendible proyectar."""
    factibilidad = factibilidad or {
        "factible": False,
        "estado": "No recomendable",
        "nivel_confianza_metodologica": "no recomendable",
        "razones_tecnicas": [explicacion or "La serie no cumple criterios mínimos de factibilidad."],
        "advertencias": [],
        "horizonte_maximo_sugerido": 0,
        "puede_generarse_informe": True,
        "explicacion": explicacion or "La proyección no se genera por criterios metodologicos.",
    }
    metricas_modelo = (modelo or {}).get("metricas_ajuste", {})
    diagnostico_residuos = diagnostico_residuos or (modelo or {}).get("diagnostico_residuos", {})
    stats = {
        "r2": metricas_modelo.get("r2", float("nan")),
        "r2_ajustado": metricas_modelo.get("r2_ajustado", float("nan")),
        "aic": metricas_modelo.get("aic", float("inf")),
        "aicc": metricas_modelo.get("aicc", float("inf")),
        "jb_p": diagnostico_residuos.get("jb_p", float("nan")),
        "kurt_ex": diagnostico_residuos.get("kurt_ex", float("nan")),
        "durbin_watson": diagnostico_residuos.get("durbin_watson", float("nan")),
        "n": validacion_serie.get("observaciones", 0),
        "width95": float("nan"),
        "all_candidates": _candidatos_serializables(candidatos or [], backtesting_por_modelo or {}),
        "politica_modelos": politica_modelos or {},
        "descartes_modelos": (modelo or {}).get("descartes_modelos", []),
        "catalogo_modelos": catalogo_modelos or [],
        "parametros_modelo": (modelo or {}).get("parametros", {}),
    }
    serie_derivada = variables_derivadas.get("serie", pd.DataFrame())
    t_obs = (
        serie_derivada["Periodo"].apply(lambda p: periodo_a_t(p, ANIO_BASE)).to_numpy(dtype=float)
        if not serie_derivada.empty and "Periodo" in serie_derivada
        else np.asarray([], dtype=float)
    )
    y_obs = (
        serie_derivada["Indice"].to_numpy(dtype=float)
        if not serie_derivada.empty and "Indice" in serie_derivada
        else np.asarray([], dtype=float)
    )
    y_fit_obs = np.asarray((modelo or {}).get("yhat", []), dtype=float)
    if len(y_fit_obs) != len(y_obs):
        y_fit_obs = np.asarray([], dtype=float)
    return {
        "proyeccion_generada": False,
        # P0-G REABIERTO, 14-08-2026. Los seis puntos de salida sin proyeccion
        # devolvian el resultado SIN los flags metodologicos, de modo que
        # `estado_metodologico`, `intervalo_sustentado`, `evidencia_oos_provisional`
        # y `bloqueos_metodologicos` valian `None` o vacio justo donde mas
        # importan: un resultado bloqueado es donde el lector necesita saber que
        # P0-C y P0-E siguen pendientes. No se rellena nada inventado -sin punto no
        # hay intervalo que sustentar, y eso es precisamente lo que se declara-.
        "estado_metodologico": estado_metodologico(punto_disponible=False),
        "bloqueos_metodologicos": dict(BLOQUEOS_METODOLOGICOS_VIGENTES),
        "intervalo_sustentado": False,
        "motivo_intervalo_no_sustentado": BLOQUEOS_METODOLOGICOS_VIGENTES["P0-C"],
        "evidencia_oos_provisional": True,
        "periodo_solicitado": periodo_solicitado,
        "periodo_proj": periodo_solicitado,
        "t_proj": None,
        "horizonte_solicitado": horizonte_solicitado,
        "horizonte_permitido": 0,
        "horizonte_info": horizonte_info or {
            "horizonte_maximo": 0,
            "horizonte_maximo_recomendado": 0,
            "horizonte_maximo_permitido_como_escenario": 0,
            "horizonte_maximo_admisible": 0,
            "horizonte_maximo_evaluado": 0,
            "horizonte_maximo_busqueda_configurado": 0,
            "horizonte_finalmente_permitido": 0,
            "primer_horizonte_no_viable": 0,
            "horizontes_evaluados": [],
            "horizontes_no_recomendables": [],
            "horizontes_no_evaluados": [],
            "accion": "bloquear",
            "razones": factibilidad.get("razones_tecnicas", []),
            "mensaje": factibilidad.get("explicacion", ""),
        },
        "model_name": modelo.get("nombre_visible", "No seleccionado") if modelo else "No seleccionado",
        "modelo_codigo": modelo.get("nombre") if modelo else None,
        "y_proj": float("nan"),
        "ci_lo": float("nan"),
        "ci_hi": float("nan"),
        "ci80_lo": float("nan"),
        "ci80_hi": float("nan"),
        "ci95_lo": float("nan"),
        "ci95_hi": float("nan"),
        "factor_actualizacion": float("nan"),
        "variacion_acumulada": float("nan"),
        "stats": stats,
        "t_obs": t_obs,
        "y_obs": y_obs,
        "y_fit_obs": y_fit_obs,
        "y_fit_full": y_fit_obs,
        "t_full": t_obs,
        "predict_func": None,
        "validacion_serie": validacion_serie,
        "analisis_serie": analisis_serie,
        "variables_derivadas": variables_derivadas,
        "outliers": outliers,
        "factibilidad": factibilidad,
        "metricas_ajuste": {},
        "diagnostico_residuos": diagnostico_residuos or {},
        "backtesting": backtesting or {},
        "backtesting_comparativo": backtesting_comparativo or {},
        "proyecciones": pd.DataFrame(
            columns=[
                "periodo",
                "indice_proyectado",
                "variacion_pct_ultimo_observado",
                "variacion_acumulada_pct",
                "factor_actualizacion",
                "limite_inferior_80",
                "limite_superior_80",
                "limite_inferior_95",
                "limite_superior_95",
                "limite_inferior",
                "limite_superior",
                "ancho_relativo_80",
                "ancho_relativo_95",
                "modelo",
                "nivel_confianza_metodologica",
                "advertencias",
            ]
        ),
        "descartes_modelos": (modelo or {}).get("descartes_modelos", []),
        "politica_modelos": politica_modelos or {},
        "catalogo_modelos": catalogo_modelos or [],
        "parametros_modelo": (modelo or {}).get("parametros", {}),
        "advertencias_categorizadas": _categorizar_advertencias(
            validacion_serie=validacion_serie,
            outliers=outliers,
            modelo=modelo or {},
            factibilidad=factibilidad,
            horizonte_info={},
            evaluacion_intervalos={},
        ),
        "justificacion_modelo": factibilidad.get("explicacion", explicacion or ""),
        "interpretacion_estadistica": [factibilidad.get("explicacion", explicacion or "")],
        "explicacion": factibilidad.get("explicacion", explicacion or ""),
    }


def _explicacion_factibilidad(razones: list[str]) -> str:
    if not razones:
        return "La proyección no se genera porque no cumple criterios metodologicos mínimos."
    for razon in razones:
        texto = str(razon)
        if "autocorrelacion residual severa" in texto:
            return texto
    for razon in razones:
        texto = str(razon)
        if "MASE > 1" in texto:
            return texto
    return "La proyección no se genera porque " + " ".join(str(r) for r in razones[:3])


def _numero_finito(valor: Any) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return float("nan")
    return numero if np.isfinite(numero) else float("nan")


def _ratio_local(numerador: float, denominador: float) -> float:
    if not (np.isfinite(numerador) and np.isfinite(denominador)) or abs(float(denominador)) <= EPS_NUMERICO:
        return float("nan")
    return float(numerador / denominador)


def _validar_ajuste_calendario_serie(
    serie: pd.DataFrame,
    backtesting_comparativo: dict[str, dict],
    modelo_codigo: str,
) -> dict:
    """Mide el respaldo retrospectivo del ajuste calendario. **Ya no decide nada.**

    P0-F, 12-08-2026: el tratamiento se retiro del camino productivo, de modo que
    esta funcion produce un DIAGNOSTICO que se publica y no modifica ningun
    pronostico. `_ajustar_salto_anual` fija `aplicado = False` de forma
    incondicional sin consultar este resultado.

    Lo que mide: la validación retrospectiva se agrega sobre un conjunto fijo de
    horizontes de referencia (`HORIZONTES_VALIDACION_CALENDARIO`), de modo que la
    lectura sea una propiedad de la serie y del modelo y no cambie con lo que
    solicite el usuario; se compara contra la tolerancia de deterioro de MAE y
    RMSE, y `gamma` se reestima por origen sin fuga dentro de
    `evaluar_ajuste_en_backtesting`.

    Ese conjunto `(1, 3, 6)` es, el mismo, un literal sin fuente -uno de los
    cuatro motivos de la retirada-, razon de mas para no devolverle efecto.
    """
    mae_base = mae_ajustado = rmse2_base = rmse2_ajustado = 0.0
    ventanas = 0
    detalle: list[dict[str, Any]] = []
    for horizonte in HORIZONTES_VALIDACION_CALENDARIO:
        bt = backtesting_comparativo.get(f"{modelo_codigo}_h{int(horizonte)}") or {}
        parcial = evaluar_ajuste_en_backtesting(
            serie=serie,
            predicciones=bt.get("predicciones"),
            horizonte=int(horizonte),
        )
        if not parcial.get("evaluado"):
            continue
        n = int(parcial.get("ventanas", 0) or 0)
        if n <= 0:
            continue
        ventanas += n
        mae_base += float(parcial["mae_base"]) * n
        mae_ajustado += float(parcial["mae_ajustado"]) * n
        rmse2_base += float(parcial["rmse_base"]) ** 2 * n
        rmse2_ajustado += float(parcial["rmse_ajustado"]) ** 2 * n
        detalle.append({"horizonte": int(horizonte), **{k: parcial[k] for k in ("ventanas", "mejora_mae", "mejora_rmse")}})

    if ventanas == 0:
        return {"evaluado": False, "recomendado": False, "ventanas": 0, "horizontes_validacion": list(HORIZONTES_VALIDACION_CALENDARIO)}

    mae_b, mae_a = mae_base / ventanas, mae_ajustado / ventanas
    rmse_b = float(np.sqrt(rmse2_base / ventanas))
    rmse_a = float(np.sqrt(rmse2_ajustado / ventanas))
    tolerancia = TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO
    return {
        "evaluado": True,
        "ventanas": ventanas,
        "horizontes_validacion": list(HORIZONTES_VALIDACION_CALENDARIO),
        "mae_base": mae_b,
        "mae_ajustado": mae_a,
        "rmse_base": rmse_b,
        "rmse_ajustado": rmse_a,
        "mejora_mae": (mae_b - mae_a) / mae_b * 100.0 if mae_b > 0 else 0.0,
        "mejora_rmse": (rmse_b - rmse_a) / rmse_b * 100.0 if rmse_b > 0 else 0.0,
        "detalle_por_horizonte": detalle,
        "recomendado": bool(mae_b > 0 and rmse_b > 0 and mae_a <= mae_b * tolerancia and rmse_a <= rmse_b * tolerancia),
    }


def _ajustar_salto_anual(
    serie: pd.DataFrame,
    y_futuro: np.ndarray,
    backtesting_comparativo: dict[str, dict],
    modelo_codigo: str,
    horizonte: int,
) -> dict:
    """Mide y publica el perfil de cambio de año. **No aplica ningún ajuste.**

    P0-F, 12-08-2026: `aplicado` vale siempre `False` y `y_ajustado is y_futuro`.
    El perfil -`gamma`, ratio, consistencia de signo y transiciones- se sigue
    midiendo y publicando porque son datos de la serie, pero no modifican el
    pronostico. Los motivos de la retirada estan enumerados en el cuerpo.

    El factor que se aplicaba, conservado aqui solo para documentar que se hacia:

        f_j = exp(gamma * (n_j - j/12))

    Se evaluaba para cada paso j con su propio numero de eneros acumulados n_j, de
    modo que el valor proyectado para un mes dado era identico se pidieran 3, 6,
    12 o 18 meses. **Esa propiedad debe conservarse si alguna vez se restituye un
    tratamiento**: por paso, sin condicionar la activacion al horizonte
    solicitado. El termino j/12 pretendia descontar la porcion del salto que el
    modelo base ya habia repartido de forma uniforme, y es justamente el
    componente que resulto falso para `naive`.
    """
    mes_origen = _mes_de_periodo(serie["Periodo"].iloc[-1]) if not serie.empty else 0
    perfil = perfil_salto_anual(serie)
    validacion: dict = {"evaluado": False, "recomendado": False}
    # P0-F, 12-08-2026: EL TRATAMIENTO SE RETIRA DEL CAMINO PRODUCTIVO.
    #
    # El perfil se sigue MIDIENDO y publicando -gamma, ratio, consistencia y
    # transiciones son datos de la serie- pero ya NO modifica el pronostico.
    # Ningun componente del metodo tenia sustento completo:
    #
    #   * `gamma` como estimador del efecto FUTURO: la robustez de la mediana
    #     esta publicada, usarla como prediccion del salto siguiente no;
    #   * la forma `f_j = exp(gamma (n_j - j/12))`: el termino `-j/12` supone
    #     que el modelo base repartio gamma uniformemente entre doce meses, lo
    #     que es FALSO para `naive` -pronostico plano, no reparte nada- y
    #     distinto para cada modelo, y el factor se aplicaba a los diez por
    #     igual sin mirar cual gano;
    #   * las puertas `>=2`, `>1,5` y `>=0,6`: el comentario de `criterios.py`
    #     reconoce que fueron «calibradas con el diagnostico del 19 de julio de
    #     2026 sobre el anexo ICOCIV», es decir sobre el propio anexo de
    #     aplicacion, que REQ 31 prohibe;
    #   * el conjunto de validacion `(1, 3, 6)`: literal sin fuente.
    #
    # Y el DANE no documenta -en lo consultado- ninguna discontinuidad
    # diciembre-enero del ICOCIV, de modo que el ajuste tampoco podia
    # presentarse como correccion oficial del indice (REQ 28).
    #
    # NO se introduce reemplazo: hacerlo anadiria un candidato al catalogo y
    # reabriria P0-B. El fenomeno esta medido y es contundente; lo que falta es
    # un metodo publicado para tratarlo.
    aplicado = False
    y_ajustado = y_futuro

    base = np.asarray(y_futuro, dtype=float)
    factores = np.where(np.abs(base) > EPS_NUMERICO, np.asarray(y_ajustado, dtype=float) / base, 1.0)
    trazabilidad = resumen_trazabilidad(
        perfil=perfil,
        validacion=validacion,
        aplicado=aplicado,
        horizonte=horizonte,
        mes_origen=mes_origen,
    )
    trazabilidad["factores_por_paso"] = [float(f) for f in factores]
    return {
        "y_futuro": y_ajustado,
        "factores": factores,
        "trazabilidad": trazabilidad,
    }


def _errores_por_horizonte(
    backtesting_comparativo: dict[str, dict],
    modelo_codigo: str,
    horizontes: tuple[int, ...] | list[int],
) -> dict[int, np.ndarray]:
    """Errores OOS del modelo a cada horizonte exacto, del backtesting ya calculado."""
    errores: dict[int, np.ndarray] = {}
    for horizonte in horizontes:
        bt = backtesting_comparativo.get(f"{modelo_codigo}_h{int(horizonte)}") or {}
        predicciones = bt.get("predicciones")
        if isinstance(predicciones, pd.DataFrame) and not predicciones.empty and "Error" in predicciones:
            valores = pd.to_numeric(predicciones["Error"], errors="coerce").dropna().to_numpy(dtype=float)
            if len(valores):
                errores[int(horizonte)] = valores
    return errores


#: Niveles nominales adoptados. El 95 % es el que se publica; el 80 % es
#: diagnostico interno y no aparece en ninguna salida.
NIVEL_NOMINAL_80 = 0.80
NIVEL_NOMINAL_95 = 0.95


def _multiplicador_intervalo(nivel: float, n: int) -> float:
    """Multiplicador `c` de `yhat ± c*sigma_h` (FPP3 5.5) con sigma_h ESTIMADA.

    FPP3 5.5 da la forma `yhat ± c*sigma_h` y tabula `c` con cuantiles de la
    normal, que es el valor correcto cuando `sigma_h` se conoce. Aqui `sigma_h`
    NO se conoce: se estima con los `n` errores fuera de muestra del paso, y con
    `n` pequeno esa incertidumbre no es despreciable.

    Bajo el mismo supuesto de normalidad que la fuente adopta, y siendo la media
    del error CERO por construccion -no se estima, se asume, porque el sesgo se
    corrige en el pronostico y no en el intervalo (FPP3 5.4)-, se tiene

        n * sigma_gorro^2 / sigma^2  ~  chi2_n        con sigma_gorro^2 = SUM e^2 / n
        e_futuro / sigma_gorro       =  Z / sqrt(chi2_n / n)  ~  t_n

    de modo que el multiplicador EXACTO es el cuantil de una t con `n` grados de
    libertad. Es una DERIVACION MATEMATICA del supuesto de la propia fuente, no
    un factor de inflacion elegido: con `n` grande converge al cuantil normal
    que FPP3 tabula.

    No se adopta por mejorar la cobertura. Se adopta porque usar el cuantil
    normal con una sigma estimada de tres o cuatro errores afirma un nivel
    nominal que la construccion no sostiene.
    """
    from scipy.stats import t as _t

    if n < 1:
        return float("nan")
    return float(_t.ppf(0.5 + nivel / 2.0, n))


def _semiancho_conformal(errores_abs: np.ndarray, alpha: float) -> tuple[float, bool]:
    """Cuantil de orden con corrección de muestra finita, inspirado en conformal.

    Se toma el k-esimo |error| mas pequeño con k = ceil((n+1)(1-alpha)), el
    índice que la predicción conformal dividida usa para su cuantil de
    calibración (Lei et al., 2018; Angelopoulos y Bates, 2023). La corrección
    (n+1) evita el sesgo hacia adentro del percentil empírico simple en muestras
    pequenas.

    ATENCIÓN: NO se declara la garantía de cobertura del conformal split. Esa
    garantía exige intercambiabilidad entre los errores de calibración y el
    error futuro, supuesto que los errores walk-forward de una serie temporal no
    cumplen: los origenes comparten historia de entrenamiento, el modelo se
    reestima en cada corte y la varianza del error cambia con el tiempo. Además,
    aquí el score se centra con la media de la propia muestra de calibración, lo
    que rompe la intercambiabilidad estricta que exige el resultado teórico. El
    procedimiento se justifica como criterio conservador de implementacion y su
    cobertura se verifica empiricamente, no por teoria.

    El segundo elemento del par indica si k <= n, es decir, si existe un dato
    observado en esa posición de la cola. Cuando k > n (hace falta
    n >= 1/alpha - 1, o sea 19 errores al 95%) ningun dato alcanza esa cola: se
    devuelve el máximo observado y se marca la muestra como insuficiente para
    estimar el cuantil, de modo que el respaldo paramétrico t domine.
    """
    n = int(len(errores_abs))
    orden = np.sort(errores_abs)
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        return float(orden[-1]), False
    return float(orden[k - 1]), True


def _cuantiles_intervalo(errores: np.ndarray) -> tuple[dict[str, float], str, str, str]:
    """Offsets de intervalo 80/95 para los errores OOS de UN horizonte.

    METODO: Hyndman y Athanasopoulos (2021), *Forecasting: Principles and
    Practice*, 3.a ed., seccion 5.5:

        yhat_(T+h|T) ± c * sigma_h

    donde ``c`` depende de la probabilidad de cobertura y ``sigma_h`` es una
    estimacion de la desviacion tipica de la distribucion de pronostico a h
    pasos, que la fuente estima a partir de los errores como
    ``sigma = sqrt(SUM e^2 / gl)``. Notese que la fuente usa ``SUM e^2`` y NO
    ``SUM (e - media)^2``: la dispersion ya absorbe un eventual sesgo, lo que es
    coherente con centrar la banda en el pronostico.

    Aqui ``sigma_h`` se estima con los errores fuera de muestra del horizonte
    EXACTO h, obtenidos por origen movil, sin reescalar los de otro horizonte.

    AUDITORIA 09-08-2026, P0-C. La construccion anterior tomaba el MAXIMO entre
    un cuantil de orden y una prediccion t, centraba ambas en la media del error
    y despues aplicaba correcciones. Cinco de sus componentes no tenian fuente:

      1. la combinacion ``max(cuantil, t)``;
      2. incluir ``semi80`` dentro del maximo del 95;
      3. el centrado en la media del error;
      4. la correccion posterior que forzaba el pronostico dentro de la banda;
      5. la envolvente monotona entre pasos (en `_intervalos_prediccion`).

    Los requisitos metodologicos del proyecto prohiben combinar metodos por
    ``max()`` sin una fuente para la combinacion, y son explicitos en que ser
    conservador o dar mejor cobertura no es fundamento.

    Sobre el centrado: FPP3 seccion 5.4 es taxativo -«If the residuals have mean
    m, then simply add m to all forecasts and the bias problem is solved»-, de
    modo que el remedio del sesgo corresponde al PRONOSTICO, no al intervalo.
    SAVIP publica `sesgo_medio` y no corrige el punto; al dejar de desplazar la
    banda, ese sesgo deja de quedar disimulado y se ve en la cobertura.

    Tres reglas desaparecen POR CONSTRUCCION, no por conveniencia: al haber una
    sola construccion no hay que combinar nada; al centrar en el pronostico este
    queda dentro de su banda por definicion; y con la misma ``sigma_h`` y
    ``c80 < c95`` el intervalo del 80 % queda contenido en el del 95 %.

    LO QUE GARANTIZA: la cobertura nominal si los supuestos -normalidad
    aproximada de la distribucion de pronostico y errores de media cero- se
    cumplen. LO QUE NO GARANTIZA: cobertura bajo no normalidad, sesgo o
    dependencia temporal. Por eso la cobertura se mide y se publica.

    Los offsets se devuelven como desplazamientos aditivos sobre la prediccion.
    """
    n = int(len(errores))
    sigma = float(np.sqrt(np.mean(errores ** 2))) if n else float("nan")
    c80 = _multiplicador_intervalo(NIVEL_NOMINAL_80, n)
    c95 = _multiplicador_intervalo(NIVEL_NOMINAL_95, n)

    offsets = {
        "lo80": -c80 * sigma,
        "hi80": c80 * sigma,
        "lo95": -c95 * sigma,
        "hi95": c95 * sigma,
        "q80": c80,
        "q95": c95,
    }

    metodo_codigo = "fpp3_sigma_h"
    metodo = (
        f"pronóstico ± c·σ̂_h con σ̂_h la raíz del error cuadrático medio de {n} errores "
        f"fuera de muestra del horizonte exacto (Hyndman y Athanasopoulos, 2021, §5.5)"
    )
    # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Este texto decía «σ̂ se estima
    # con pocos errores», nombraba el nivel nominal y remitía a «la cobertura
    # empírica reportada». Viajaba a `factibilidad.advertencias`, a la columna
    # `advertencia_evidencia_oos` del CSV, a la interfaz y a los informes: cinco
    # superficies públicas caracterizando un intervalo que ya no se entrega, y
    # remitiendo a una cobertura que tampoco se publica.
    #
    # El HECHO que informaba sí es del usuario y sí es público: cuántos errores
    # fuera de muestra reúne ese paso. Se dice con el vocabulario de evidencia OOS
    # -el mismo de `_texto_evidencia_oos`- y sin vocabulario de intervalo. El
    # corte n<8 deja de referirse a la estabilidad de σ̂ y pasa a ser el tramo
    # descriptivo `MIN_ITERACIONES_BACKTESTING`, que es el que la aplicación ya
    # usa para comunicar cuánta evidencia sostiene el horizonte.
    advertencia = ""
    if n < MIN_ITERACIONES_BACKTESTING:
        advertencia = (
            f"Evidencia fuera de muestra limitada en al menos un paso de la trayectoria "
            f"(n={n} error{'es' if n != 1 else ''} de origen móvil). Las métricas de ese "
            f"paso se calculan sobre esa muestra."
        )
    return offsets, metodo, metodo_codigo, advertencia


#: Estados posibles de una banda de prediccion. Son excluyentes y ninguno es un
#: umbral: los tres primeros describen imposibilidades matematicas.
BANDA_VALIDA = "valida"
BANDA_LIMITES_NO_FINITOS = "limites_no_finitos"
BANDA_LIMITES_INVERTIDOS = "limites_invertidos"
BANDA_NO_CALCULABLE = "intervalo_no_calculable"
BANDA_SEMIANCHO_CERO = "semiancho_cero"
#: P0-C C2 PASO 0: imposibilidad aritmetica DEL PRONOSTICO, no de la banda. Es el
#: unico estado de esta familia que sigue bloqueando, porque afecta al objeto que
#: SI se publica. Los demas describen una banda que C2 retiro del producto.
PUNTO_NO_FINITO = "punto_no_finito"

MOTIVO_BANDA = {
    PUNTO_NO_FINITO: (
        "El pronostico puntual no es un numero finito: no hay resultado que publicar."
    ),
    BANDA_LIMITES_NO_FINITOS: (
        "Al menos un limite del intervalo no es un numero finito: la banda no existe."
    ),
    BANDA_LIMITES_INVERTIDOS: (
        "El limite superior del intervalo es menor que el inferior: la banda no es "
        "un intervalo. No se intercambian los limites, porque el orden invertido "
        "indica que el calculo que los produjo no es valido."
    ),
    BANDA_NO_CALCULABLE: (
        "No hay errores fuera de muestra del paso exacto para construir la banda. "
        "No se fabrica un intervalo sin respaldo estadistico."
    ),
    BANDA_SEMIANCHO_CERO: (
        "El intervalo tiene amplitud nula. Se entrega como dato, pero una banda de "
        "amplitud cero no puede sostener el nivel nominal declarado."
    ),
}


def estado_banda(limite_inferior: Any, limite_superior: Any,
                 pronostico: Any = None, n_errores: Any = None) -> str:
    """Clasifica una banda por posibilidad matematica, no por su amplitud.

    Se comprueba ANTES que cualquier comparacion de magnitud. Comparar una
    amplitud contra un corte no detecta que la amplitud no exista: un intervalo
    con los limites invertidos produce un ancho negativo, que es menor que
    cualquier umbral y por tanto pasaba como aceptable.
    """
    # P0-C, RUTA C2 — PASO 0, 14-08-2026. DESACOPLE ARITMETICO.
    #
    # Hasta hoy esta funcion comprobaba la finitud del PRONOSTICO y la de los
    # LIMITES en la misma lista, y devolvia un unico codigo para las dos
    # situaciones:
    #
    #     punto NaN + limites OK  -> limites_no_finitos
    #     punto OK  + limites NaN -> limites_no_finitos
    #
    # Quien lo consumia no podia saber cual de los dos objetos era imposible, y
    # `_clasificar_evidencia_horizonte` bloqueaba en ambos casos. Mientras P0-C
    # publicaba un intervalo eso era CORRECTO: sin banda el producto no podia
    # entregar su resultado completo. Retirado el intervalo del producto (ruta
    # C2), deja de serlo: un fallo aritmetico de un objeto que ya no se publica
    # no puede cancelar un pronostico finito y coherente.
    #
    # Se comprueba PRIMERO el pronostico, por separado. `PUNTO_NO_FINITO` no
    # introduce ningun umbral: es la clasificacion logica de `math.isfinite`.
    if pronostico is not None:
        try:
            if not math.isfinite(float(pronostico)):
                return PUNTO_NO_FINITO
        except (TypeError, ValueError):
            return PUNTO_NO_FINITO
    if n_errores is not None:
        try:
            if int(n_errores) <= 0:
                return BANDA_NO_CALCULABLE
        except (TypeError, ValueError):
            return BANDA_NO_CALCULABLE
    for valor in (limite_inferior, limite_superior):
        try:
            if not math.isfinite(float(valor)):
                return BANDA_LIMITES_NO_FINITOS
        except (TypeError, ValueError):
            return BANDA_LIMITES_NO_FINITOS
    if float(limite_superior) < float(limite_inferior):
        return BANDA_LIMITES_INVERTIDOS
    if float(limite_superior) == float(limite_inferior):
        return BANDA_SEMIANCHO_CERO
    return BANDA_VALIDA


def _intervalos_prediccion(
    y_futuro: np.ndarray,
    errores_por_horizonte: dict[int, np.ndarray],
    factores_calendario: np.ndarray | list[float] | None = None,
) -> list[dict[str, float | str]]:
    """Intervalos de predicción 80/95% con errores OOS del horizonte exacto.

    Cada paso p de la trayectoria usa los errores walk-forward observados a
    horizonte exactamente p (sin reescalar errores de otro horizonte). La
    amplitud se fuerza no decreciente con el paso (envolvente conservadora:
    la incertidumbre declarada a p+1 pasos no puede ser menor que a p pasos).
    Si la trayectoria central lleva ajuste calendario, los límites se escalan
    por el mismo factor. El límite inferior se recorta en 0 (índice positivo).
    Sin al menos MIN_ITERACIONES_WF_ESCENARIO errores para un paso, el paso no
    es calculable: no se fabrica ninguna banda sin respaldo estadístico.
    """
    y = np.asarray(y_futuro, dtype=float)
    n_pasos = len(y)
    if factores_calendario is None:
        factores = np.ones(n_pasos, dtype=float)
    else:
        factores = np.asarray(factores_calendario, dtype=float)
        if len(factores) != n_pasos:
            raise ValueError("factores_calendario debe tener la longitud de la trayectoria.")
    base = np.where(np.abs(factores) > EPS_NUMERICO, y / factores, y)

    offsets_por_paso: list[dict[str, float]] = []
    meta_por_paso: list[tuple[int, float, str, str, str]] = []
    for paso in range(1, n_pasos + 1):
        errores = np.asarray(errores_por_horizonte.get(paso, ()), dtype=float)
        errores = errores[np.isfinite(errores)]
        if len(errores) < MIN_ITERACIONES_WF_ESCENARIO:
            raise ValueError(
                f"Sin errores fuera de muestra suficientes para el paso {paso} "
                f"({len(errores)}; mínimo {MIN_ITERACIONES_WF_ESCENARIO}). "
                "No se fabrica una banda sin respaldo estadístico."
            )
        offsets, metodo, metodo_codigo, advertencia = _cuantiles_intervalo(errores)
        sigma = float(np.std(errores, ddof=1)) if len(errores) > 1 else 0.0
        offsets_por_paso.append(offsets)
        meta_por_paso.append((int(len(errores)), sigma, metodo, metodo_codigo, advertencia))

    # AUDITORIA 09-08-2026, P0-C. Se retira la ENVOLVENTE MONOTONA que forzaba
    # cada lado del intervalo a no decrecer con el paso. No tenia fuente: FPP3
    # 5.5 observa que sigma_h SUELE crecer con el horizonte, que es una
    # constatacion empirica y no una restriccion que deba imponerse. Al
    # imponerla, la anchura declarada en un paso dejaba de depender de la
    # evidencia de ese paso y pasaba a heredar la del anterior, ensanchando la
    # banda sin respaldo. Ahora cada paso declara la incertidumbre que su propia
    # muestra de errores sostiene.

    intervalos: list[dict[str, float | str]] = []
    for idx in range(n_pasos):
        offsets = offsets_por_paso[idx]
        n_errores, sigma, metodo, metodo_codigo, advertencia = meta_por_paso[idx]
        factor = float(factores[idx])
        pred = float(y[idx])
        lo80 = max((float(base[idx]) + offsets["lo80"]) * factor, 0.0)
        hi80 = (float(base[idx]) + offsets["hi80"]) * factor
        lo95 = max((float(base[idx]) + offsets["lo95"]) * factor, 0.0)
        hi95 = (float(base[idx]) + offsets["hi95"]) * factor
        ancho_base = abs(pred)
        # El piso en cero del limite inferior puede invertir la banda cuando el
        # modelo extrapola por debajo de cero: entonces hi95 < 0 = lo95. Se
        # detecta aqui y se declara; no se corrige intercambiando limites.
        estado = estado_banda(lo95, hi95, pred, n_errores)
        intervalos.append(
            {
                "limite_inferior_80": lo80,
                "limite_superior_80": hi80,
                "limite_inferior_95": lo95,
                "limite_superior_95": hi95,
                "limite_inferior": lo95,
                "limite_superior": hi95,
                "estado_banda": estado,
                "banda_valida": estado in (BANDA_VALIDA, BANDA_SEMIANCHO_CERO),
                "motivo_banda": MOTIVO_BANDA.get(estado, ""),
                "metodo": metodo,
                "metodo_codigo": metodo_codigo,
                "errores_oos_disponibles": n_errores,
                "horizonte_errores": int(idx + 1),
                "sigma_h": sigma,
                "q80": offsets["q80"],
                "q95": offsets["q95"],
                "percentil_80_inf": offsets["lo80"],
                "percentil_80_sup": offsets["hi80"],
                "percentil_95_inf": offsets["lo95"],
                "percentil_95_sup": offsets["hi95"],
                "advertencia_evidencia_oos": advertencia,
                "ancho_relativo_80": float((hi80 - lo80) / ancho_base) if ancho_base > EPS_NUMERICO else float("inf"),
                "ancho_relativo_95": float((hi95 - lo95) / ancho_base) if ancho_base > EPS_NUMERICO else float("inf"),
                "ancho_relativo": float((hi95 - lo95) / ancho_base) if ancho_base > EPS_NUMERICO else float("inf"),
            }
        )
    return intervalos


def _minimo_entre_horizontes(
    cobertura_empirica: dict[str, Any],
) -> tuple[float | None, int | None, int | None]:
    """Cobertura minima de la trayectoria, el horizonte donde cae y su n.

    G-2 la conserva y la publica; lo que deja de hacer es decidir con ella el
    estado de un paso distinto. Devolver el horizonte y el conteo junto al
    valor es lo que permite advertir DONDE ocurre en vez de solo cuanto vale.
    """
    # D-Z2: se incluye la cobertura 0,0 y se excluye SOLO la ausencia -None,
    # NaN, infinito-. Con la truthiness anterior, el horizonte que no cubrio
    # ninguna observacion quedaba fuera del calculo del minimo, es decir,
    # desaparecia justo del indicador creado para senalarlo.
    filas = [
        fila for fila in (cobertura_empirica.get("por_horizonte") or [])
        if _numero_finito_o_none(fila.get("cobertura_95")) is not None
    ]
    if not filas:
        minima = _numero_finito_o_none(cobertura_empirica.get("cobertura_95_minima"))
        return (float(minima) if minima is not None else None), None, None
    peor = min(filas, key=lambda fila: float(fila["cobertura_95"]))
    n_prueba = peor.get("n_prueba")
    return (
        float(peor["cobertura_95"]),
        int(peor["horizonte"]),
        int(n_prueba) if n_prueba is not None else None,
    )


def _recuento_del_paso(
    cobertura_empirica: dict[str, Any], paso_exacto: Any
) -> tuple[int | None, int | None]:
    """Aciertos y evaluaciones del paso solicitado, como enteros.

    La proporcion sola induce a error con pocas evaluaciones: 1,000 sobre tres
    contrastes y 1,000 sobre veintiuno se leen igual. Publicar ``x/y`` al lado
    es lo que permite distinguirlos.
    """
    if paso_exacto is None:
        return None, None
    for fila in cobertura_empirica.get("por_horizonte") or []:
        if int(fila.get("horizonte", -1)) != int(paso_exacto):
            continue
        proporcion = _numero_finito_o_none(fila.get("cobertura_95"))
        n_prueba = fila.get("n_prueba")
        if proporcion is None or n_prueba is None:
            return None, None
        total = int(n_prueba)
        return int(round(float(proporcion) * total)), total
    return None, None


def _limitacion_por_muestra(
    cobertura_paso: Any, total_evaluado: int | None, apta: bool
) -> str:
    """Nota para una cobertura medida que no alcanza el criterio operativo.

    Se emite solo cuando hay algo que matizar: una cobertura **medida** que el
    criterio vigente no admite para clasificar. Si no hay medicion no hay nada
    que limitar, y si la muestra es apta tampoco.

    El 16 se nombra como lo que es -un **criterio operativo vigente** del
    proyecto- y nunca como requisito estadistico universal, garantia,
    validacion cientifica ni minimo matematico: no tiene fuente que lo
    respalde, y asi consta desde la revision del 05-08.
    """
    if apta or _numero_finito_o_none(cobertura_paso) is None:
        return ""
    disponibles = (
        f"{int(total_evaluado)} evaluaciones de cobertura"
        if total_evaluado is not None
        else "un numero de evaluaciones inferior al exigido"
    )
    return (
        f"Se dispone de {disponibles}. El resultado observado se publica de forma "
        f"descriptiva; el criterio operativo vigente exige al menos "
        f"{min_errores_cobertura_vigente()} errores fuera de muestra para utilizar "
        f"esta cobertura en la clasificacion del horizonte."
    )


def _diferencia_puntos_frente_al_nominal(cobertura: Any) -> float | None:
    """``d = 100 x (p - nivel nominal)``, en puntos porcentuales.

    Es **estrictamente descriptiva**: dice a que distancia quedo lo observado
    del nivel para el que la banda se calculo. No aprueba, no degrada, no
    bloquea, no promueve y no sustituye a ningun umbral. El estado del
    horizonte lo siguen decidiendo los criterios operativos vigentes.

    Se publica porque el nivel nominal y la cobertura observada son dos
    magnitudes distintas y su distancia es la comparacion natural entre ellas
    -no un corte inventado-, en la linea de la ISO/IEC Guide 98-3 seccion 6.
    """
    proporcion = _numero_finito_o_none(cobertura)
    if proporcion is None:
        return None
    # El redondeo a un decimal evita publicar el ruido de coma flotante:
    # 100*(1,0-0,95) da 5,000000000000004 en aritmetica binaria.
    return round(100.0 * (float(proporcion) - NIVEL_NOMINAL_IC95), 1) + 0.0


#: Nombre legible del procedimiento con que se evaluo la cobertura. Se lee del
#: resultado, nunca se supone: el metodo forma parte de lo que la cifra afirma.
NOMBRE_METODO_EVALUACION = {
    "origen_movil": "origen movil",
    "particion_temporal": "particion temporal",
    "no_evaluable": "no evaluable",
}


def _lectura_descriptiva_cobertura(
    aciertos: int | None,
    total_evaluado: int | None,
    proporcion: Any,
    diferencia_pp: float | None,
    n_errores: Any,
    metodo: Any,
) -> str:
    """Lo observado, dicho con sus propios numeros y sin categorizarlo.

    Reune en una frase las seis magnitudes que permiten leer la cobertura sin
    recurrir a ninguna etiqueta: el recuento ``x/y``, la proporcion, el nivel
    nominal declarado, la distancia entre ambos, el numero de errores fuera de
    muestra del paso y el metodo con el que se evaluo.

    Deliberadamente **no** dice si la cobertura «cumple» un porcentaje.
    Cumplir no es una propiedad de una proporcion observada frente a un corte
    operativo interno: 12/13 y 120/130 dan la misma proporcion y no sostienen
    la misma afirmacion. Por eso el recuento viaja junto a la proporcion y el
    juicio se deja al lector.

    Es el canal por el que 0,90 deja de necesitarse para comunicar: lo que
    antes se resumia en una etiqueta se dice ahora con las magnitudes que la
    sostienen (D-1b, conversion del 07-08-2026).
    """
    p = _numero_finito_o_none(proporcion)
    if p is None:
        return ""
    partes = [
        f"{aciertos}/{total_evaluado}"
        if aciertos is not None and total_evaluado is not None
        else "recuento no disponible",
        f"proporcion {p:.3f}",
        f"nominal declarado {NIVEL_NOMINAL_IC95:.0%}",
    ]
    if diferencia_pp is not None:
        partes.append(f"distancia {diferencia_pp:+.1f} pp")
    n = _numero_finito_o_none(n_errores)
    if n is not None:
        partes.append(f"n = {int(n)} errores fuera de muestra")
    clave = str(metodo or "").strip()
    if clave:
        partes.append(
            f"evaluada por {NOMBRE_METODO_EVALUACION.get(clave, clave)}"
        )
    return "Cobertura observada: " + "; ".join(partes) + "."


#: Papel que conserva ``COBERTURA_IC95_ACEPTABLE`` (0,90) desde el 07-08-2026.
#: Viaja en el propio resultado para que sea auditable sin leer el codigo.
#: Se mantiene por debajo de 180 caracteres: viaja a una celda de tabla del
#: DOCX, donde un texto mas largo deforma la composicion.
PAPEL_UMBRAL_ACEPTACION = (
    "Descriptivo: no decide el estado, ni el tipo de banda, ni la posibilidad de proyectar. "
    "Solo elige la redaccion; el unico corte de cobertura con efecto es el de advertencia."
)


def _advertencia_consistencia_horizontes(
    minimo_global: float | None,
    horizonte_minimo: int | None,
    n_minimo: int | None,
    paso_exacto: Any,
) -> dict[str, Any]:
    """Advertencia de consistencia entre horizontes (G-2, apartado 8.3).

    Se emite cuando OTRO horizonte de la trayectoria cubre por debajo del corte
    de aceptacion. Es informativa: no modifica el estado del paso solicitado,
    y el mensaje lo dice explicitamente para que nadie la lea como una
    degradacion encubierta.
    """
    if minimo_global is None or horizonte_minimo is None or paso_exacto is None:
        return {"aplica": False}
    if minimo_global >= COBERTURA_IC95_ACEPTABLE:
        return {"aplica": False}
    if int(horizonte_minimo) == int(paso_exacto):
        return {"aplica": False}

    conteo = (
        f" sobre {n_minimo} contraste(s)" if n_minimo is not None else ""
    )
    return {
        "aplica": True,
        "titulo": "Advertencia de consistencia entre horizontes",
        "cobertura_minima_global": float(minimo_global),
        "horizonte_minimo_global": int(horizonte_minimo),
        "n_errores_del_horizonte_minimo": n_minimo,
        "mensaje_descriptivo": (
            f"Advertencia de consistencia entre horizontes: la cobertura observada mas baja de "
            f"la trayectoria es {minimo_global:.0%} en h={int(horizonte_minimo)}{conteo}, un "
            f"horizonte distinto del solicitado (h={int(paso_exacto)}). Esto NO invalida "
            f"automaticamente el horizonte solicitado, cuyo estado se decide con su propia "
            f"evidencia, pero la lectura conjunta de la trayectoria requiere cautela: los pasos "
            f"intermedios no cubren igual que el paso entregado."
        ),
        "consecuencia_operativa": (
            "No modifica el estado del horizonte solicitado. Si se van a usar los pasos "
            "intermedios de la trayectoria, revisar la cobertura de cada uno por separado."
        ),
    }


def clasificar_intervalo_por_cobertura(
    cobertura_empirica: dict[str, Any],
    errores_por_horizonte: dict[int, np.ndarray] | None = None,
    estado_banda_paso: str | None = None,
) -> dict[str, Any]:
    """Clasifica el intervalo del 95 % segun la cobertura empirica medida.

    Decision autorizada el 28 de julio de 2026 sobre el hallazgo H-05, como
    combinacion de dos alternativas: **no se cambia el calculo** del intervalo
    (no se ensancha ninguna banda ni se mueve ningun pronostico puntual) y **se
    cambia lo que el sistema afirma** sobre esa banda y hasta donde permite
    usarla.

    Cuatro estados, y **un solo corte con efecto**:

    ==========================  ==========================================
    Cobertura medida            Consecuencia sobre el horizonte
    ==========================  ==========================================
    Banda no calculable         Rango de referencia; horizonte a escenario
    No verificable              Rango de referencia; horizonte a escenario
    >= 0,80                     No se degrada
    < 0,80                      Rango de referencia; horizonte a escenario
    ==========================  ==========================================

    **0,90 no aparece en esa tabla, y desde el 07-08-2026 tampoco en la
    decision.** Conserva su valor y su nombre, pero su unica funcion es elegir
    entre dos redacciones de un resultado que no se degrada en ninguno de los
    dos casos:

    ==========================  ==========================================
    Cobertura medida            Redaccion (misma consecuencia)
    ==========================  ==========================================
    >= 0,90                     sin nota de distancia al nominal
    >= 0,80 y < 0,90            con nota de distancia al nominal
    ==========================  ==========================================

    Ambas producen ``clasificacion = banda_calculada`` y
    ``degrada_a_escenario = False``. Su efecto aislado medido -variante
    E-090-AISLADO, 07-08-2026- fue 0 estados, 0 tipos de banda y 0 cambios
    numericos. La conversion no cambia ese resultado: lo hace estructural,
    sacando la comparacion fuera de la escalera de decision.

    Lo que sustituye a 0,90 como canal de comunicacion es la **lectura
    descriptiva**: recuento ``x/y``, proporcion, nivel nominal declarado,
    distancia en puntos porcentuales, numero de errores del paso y metodo de
    evaluacion. Seis magnitudes en lugar de una categoria.

    «No verificable» significa que **el paso exacto solicitado** no reunio
    ``MIN_ERRORES_COBERTURA_EMPIRICA`` errores fuera de muestra: no se afirma
    una cobertura que no se pudo medir en ese paso.

    Correccion RA-01 (reauditoria de ``0.3.0-rc2``): antes bastaba con que
    *algun* horizonte alcanzara el minimo para declarar el conjunto verificable,
    de modo que un h=12 con 15 errores heredaba la verificabilidad de h=1. La
    verificabilidad se evalua ahora sobre el paso exacto que se entrega.

    La cobertura minima global se conserva como dato complementario y como
    disparador de la advertencia de consistencia (G-2), pero **ya no es la
    magnitud comparada contra los cortes**: desde G-2 (06-08-2026) decide la
    cobertura del paso solicitado. Solo cuando el llamador no informa el paso
    -pruebas historicas y usos sinteticos- se cae al indicador global.

    Los umbrales son **criterios operativos internos**, no reglas estadisticas
    universales. Su sensibilidad esta medida y documentada en
    ``docs/remediacion_auditoria/SENSIBILIDAD_UMBRALES_COBERTURA.md``. Tras la
    conversion del 07-08-2026 quedan **dos con efecto** -el minimo de
    contrastes y el corte de advertencia- y uno descriptivo -0,90-.

    Limitacion declarada: la cobertura mide el error del modelo base. Cuando se
    aplica el ajuste de cambio de anio, la incertidumbre de gamma **no** esta
    incorporada al intervalo.
    """
    minima = cobertura_empirica.get("cobertura_95_minima")
    errores_disponibles = (
        max((len(np.asarray(v, dtype=float)) for v in errores_por_horizonte.values()), default=0)
        if errores_por_horizonte
        else 0
    )

    # El paso exacto manda. Solo cuando el llamador no lo informa (pruebas
    # historicas y usos sinteticos de la funcion) se cae al indicador global.
    paso_exacto = cobertura_empirica.get("paso_exacto")
    if paso_exacto is None:
        verificable = bool(cobertura_empirica.get("verificable"))
        n_paso = errores_disponibles
        detalle_paso = f"maximo disponible: {errores_disponibles}"
        umbral_no_verificable = f"n < {MIN_ERRORES_COBERTURA_EMPIRICA} errores por horizonte"
        sujeto_no_verificable = "ningun horizonte reune"
    else:
        verificable = bool(cobertura_empirica.get("verificable_paso_exacto"))
        n_paso = int(cobertura_empirica.get("n_errores_paso_exacto") or 0)
        detalle_paso = f"h={int(paso_exacto)} tiene {n_paso}"
        umbral_no_verificable = (
            f"n < {MIN_ERRORES_COBERTURA_EMPIRICA} errores en el paso exacto solicitado"
        )
        sujeto_no_verificable = f"el paso exacto solicitado h={int(paso_exacto)} no reune"

    cobertura_paso = cobertura_empirica.get("cobertura_95_paso_exacto")
    # D-Z1: la comprobacion es explicita contra None. `_numero_finito_o_none`
    # DEVUELVE el numero, de modo que la verdad de `not ...` confundia una
    # cobertura de 0,0 -falsy en Python- con una cobertura ausente. Cero
    # aciertos sobre n evaluaciones es una medicion, no una falta de muestra.
    if _numero_finito_o_none(cobertura_paso) is None:
        cobertura_paso = None

    # G-2: el minimo entre horizontes se conserva, se publica y se localiza,
    # pero deja de decidir. Se calcula siempre, tambien cuando no hay nada que
    # advertir, porque es informacion del resultado y no del mensaje.
    minimo_global, horizonte_minimo, n_minimo = _minimo_entre_horizontes(cobertura_empirica)
    advertencia_global = _advertencia_consistencia_horizontes(
        minimo_global, horizonte_minimo, n_minimo, paso_exacto
    )

    # Cobertura descriptiva: el recuento que sostiene la proporcion y su
    # distancia al nivel nominal declarado. Ninguno de los dos interviene en
    # ninguna decision; viajan junto al resto para que la cifra pueda leerse.
    aciertos, total_evaluado = _recuento_del_paso(cobertura_empirica, paso_exacto)
    diferencia_pp = _diferencia_puntos_frente_al_nominal(cobertura_paso)

    comunes = {
        "paso_exacto": int(paso_exacto) if paso_exacto is not None else None,
        "n_errores_paso_exacto": int(n_paso),
        "verificable_paso_exacto": bool(verificable),
        "cobertura_paso_exacto": float(cobertura_paso) if cobertura_paso is not None else None,
        "aciertos": aciertos,
        "total_evaluado": total_evaluado,
        "cobertura_x_y": (
            f"{aciertos}/{total_evaluado}"
            if aciertos is not None and total_evaluado is not None
            else ""
        ),
        "diferencia_pp_frente_nominal": diferencia_pp,
        # Las seis magnitudes en una frase, para que la cobertura pueda leerse
        # sin apoyarse en ninguna etiqueta. Es lo que sustituye a 0,90 como
        # canal de comunicacion (07-08-2026).
        "lectura_descriptiva": _lectura_descriptiva_cobertura(
            aciertos, total_evaluado, cobertura_paso, diferencia_pp, n_paso,
            cobertura_empirica.get("metodo_evaluacion"),
        ),
        # El papel de 0,90 viaja con el resultado, no solo en el codigo: quien
        # audite la salida debe poder comprobar que no decide nada.
        "umbral_aceptacion_descriptivo": float(COBERTURA_IC95_ACEPTABLE),
        "papel_umbral_aceptacion": PAPEL_UMBRAL_ACEPTACION,
        # Que la medicion pueda usarse en la regla productiva es una propiedad
        # distinta de que exista. Se declara aparte para que publicarla no se
        # confunda con habilitarla.
        "cobertura_apta_para_regla": bool(verificable),
        "limitacion_muestra": _limitacion_por_muestra(
            cobertura_paso, total_evaluado, verificable
        ),
        "cobertura_minima_global": minimo_global,
        "horizonte_de_cobertura_minima": horizonte_minimo,
        "n_errores_del_horizonte_minimo": n_minimo,
        "advertencia_consistencia": advertencia_global.get("mensaje_descriptivo", ""),
        "consistencia_entre_horizontes": advertencia_global,
    }

    # V-C: la primera pregunta no es cuanto cubre la banda, sino si la banda
    # EXISTE. Limites no finitos, invertidos o sin errores del paso son
    # imposibilidades matematicas y no admiten ninguna lectura de cobertura.
    # Se comprueba antes que cualquier umbral, porque un umbral aplicado sobre
    # una banda inexistente produciria una etiqueta que afirma de mas.
    if estado_banda_paso is not None and str(estado_banda_paso) not in (
        BANDA_VALIDA,
        BANDA_SEMIANCHO_CERO,
    ):
        return _salida_clasificacion(
            "banda_no_calculable",
            cobertura_minima=None,
            # P0-G REABIERTO: la banda que no existe se declara como tal -y esa
            # declaracion viaja en `advertencia` y en `intervalo_sustentado`-, pero
            # no retira la clasificacion tecnica del PUNTO. Las imposibilidades que
            # si afectan al punto (limites o pronostico no finitos, limites
            # invertidos) siguen bloqueando en `_clasificar_evidencia_horizonte`.
            degrada_a_escenario=False,
            umbral_aplicado="la banda no existe: no se aplica ningun umbral",
            advertencia=MOTIVO_BANDA.get(
                str(estado_banda_paso), "La banda de prediccion no es un intervalo valido."
            ),
            comunes=comunes,
        )

    # G-2 (integrada el 06-08-2026): la magnitud que se compara contra los
    # cortes es la cobertura del PASO SOLICITADO, no el minimo sobre todos los
    # pasos 1..h. Un paso intermedio con cobertura peor ya no degrada el
    # horizonte que el usuario pidio; lo advierte por separado.
    #
    # Cuando el llamador no informa el paso -pruebas historicas y usos
    # sinteticos- se conserva el indicador global, que era el comportamiento
    # anterior y sigue siendo la unica magnitud disponible en ese caso.
    decisoria = cobertura_paso if paso_exacto is not None else minima

    # D-Z1: `is None` en vez de la truthiness. Una cobertura de 0,000 pasa a
    # clasificarse por su VALOR -y cae en `cobertura_insuficiente`- en lugar de
    # informarse como no verificable con un motivo que hablaba del tamano de la
    # muestra aunque la muestra fuera amplia.
    # CIERRE 08-08-2026: se separan dos cosas que viajaban juntas.
    #
    #   (a) La cobertura NO SE PUEDE CALCULAR. No hay numero. Es una
    #       imposibilidad y sigue degradando: no se puede presentar como
    #       proyeccion tecnica una banda cuya cobertura no existe.
    #
    #   (b) La cobertura SI se calcula pero con pocos errores (n < 16). Eso es
    #       una limitacion de muestra, no una imposibilidad, y **deja de
    #       degradar**: el corte 16 es un minimo interno sin fuente. El valor,
    #       el recuento x/y, `n` y la limitacion muestral se publican todos.
    if _numero_finito_o_none(decisoria) is None:
        return _salida_clasificacion(
            "no_calculable",
            cobertura_minima=None,
            # P0-G REABIERTO, 14-08-2026: deja de degradar. Que la cobertura no
            # pueda medirse limita lo que cabe AFIRMAR de la banda, no la
            # existencia del punto, y la propia advertencia de abajo ya lo decia
            # («el pronostico puntual se entrega igualmente»). Mantener la
            # degradacion contradecia ese texto y hacia que P0-C -abierto- siguiera
            # retirando la clasificacion tecnica del horizonte.
            degrada_a_escenario=False,
            umbral_aplicado="la cobertura del paso solicitado no es calculable",
            advertencia=(
                f"La cobertura del intervalo no es calculable para este paso ({detalle_paso}). "
                "El pronostico puntual se entrega igualmente; lo que no existe es una medicion "
                "de cobertura que comunicar, y por eso la banda se presenta como rango de "
                "referencia."
            ),
            comunes=comunes,
        )
    if not verificable:
        return _salida_clasificacion(
            "medida_con_muestra_reducida",
            cobertura_minima=float(decisoria),
            degrada_a_escenario=False,
            umbral_aplicado=(
                f"{umbral_no_verificable}; la cobertura se mide y se publica. "
                f"El minimo de {min_errores_cobertura_vigente()} errores es una referencia "
                "descriptiva de tamano de muestra y no degrada el horizonte."
            ),
            advertencia=(
                f"La cobertura observada del intervalo es {float(decisoria):.0%}, medida sobre "
                f"una muestra reducida: {sujeto_no_verificable} "
                f"{min_errores_cobertura_vigente()} errores fuera de muestra ({detalle_paso}). "
                "El valor es el disponible y debe leerse con esa limitacion de precision."
            ),
            comunes=comunes,
        )

    decisoria = float(decisoria)
    sujeto = (
        f"cobertura del paso solicitado h={int(paso_exacto)}"
        if paso_exacto is not None
        else "cobertura minima entre horizontes"
    )

    # ------------------------------------------------------------------
    # La degradacion se decide UNA sola vez, y SOLO con el corte de
    # advertencia. 0,90 queda deliberadamente fuera de esta linea.
    #
    # Su efecto decisorio aislado, medido el 07-08-2026 con la variante
    # E-090-AISLADO, fue exactamente 0: cero cambios de estado, cero de tipo
    # de banda, cero numericos. La razon esta en el propio codigo y no solo
    # en el dato: las dos ramas que 0,90 separa -`nominal` y
    # `admisible_con_advertencia`- comparten `degrada_a_escenario=False`,
    # comparten `tipo_banda` (`banda_calculada`) y comparten etiqueta
    # visible. Lo unico que 0,90 elegia era la redaccion.
    #
    # Mientras la comparacion vivio DENTRO de la escalera, esa inocuidad era
    # un accidente del orden de los `if`: bastaba reordenar una rama para que
    # 0,90 empezara a decidir, y el texto «>= 0,90» ya se leia como una regla
    # de aprobacion. Sacarla fuera convierte en estructural lo que hasta
    # ahora solo estaba medido.
    #
    # 0,90 NO se sustituye por 0,95 ni por ningun otro corte: se conserva su
    # valor y se le retira la funcion decisoria.
    # ------------------------------------------------------------------
    # CIERRE 08-08-2026: 0,80 deja de degradar. Era el ULTIMO corte de
    # proporcion con efecto y no tiene fuente: ninguna referencia fija una
    # cobertura observada minima por debajo de la cual un intervalo deje de
    # poder comunicarse. Lo que si es informacion es la distancia al nivel
    # nominal, y esa se publica siempre -valor, x/y, n y diferencia_pp-.
    if decisoria < COBERTURA_IC95_ADVERTENCIA:
        return _salida_clasificacion(
            "cobertura_por_debajo_del_nominal",
            cobertura_minima=decisoria,
            degrada_a_escenario=False,
            umbral_aplicado=(
                f"{sujeto} < {COBERTURA_IC95_ADVERTENCIA:.2f}: se advierte. "
                "Ningun corte de cobertura degrada el horizonte."
            ),
            advertencia=(
                f"La cobertura observada del intervalo baja hasta {decisoria:.0%}, muy por debajo del "
                "nivel nominal del 95 %. La banda debe leerse como rango de referencia y no como "
                "un intervalo con la cobertura declarada."
            ),
            comunes=comunes,
        )

    # Aqui la decision YA ESTA TOMADA: el horizonte no se degrada por
    # cobertura. Lo unico que queda por resolver es como se redacta, y esa es
    # la unica competencia que conserva 0,90.
    sin_nota_de_distancia = decisoria >= COBERTURA_IC95_ACEPTABLE
    return _salida_clasificacion(
        "nominal" if sin_nota_de_distancia else "admisible_con_advertencia",
        cobertura_minima=decisoria,
        degrada_a_escenario=False,
        umbral_aplicado=(
            f"{sujeto} >= {COBERTURA_IC95_ADVERTENCIA:.2f}; el horizonte no se degrada por "
            f"cobertura. El valor {COBERTURA_IC95_ACEPTABLE:.2f} no interviene en esta decision: "
            "solo selecciona el texto."
        ),
        advertencia="" if sin_nota_de_distancia else (
            f"La cobertura observada del intervalo baja hasta {decisoria:.0%} frente al nivel "
            "nominal del 95 %. La banda sigue siendo utilizable como referencia tecnica, pero "
            "su cobertura observada es menor que el nivel declarado."
        ),
        comunes=comunes,
    )


#: Nivel nominal de la banda principal. Es el nivel que el metodo DECLARA; la
#: cobertura observada se publica aparte y puede no coincidir con el.
NIVEL_NOMINAL_IC95 = 0.95

#: Vocabulario V-C (integrado el 06-08-2026). Tres identificadores neutros que
#: describen QUE ES la banda entregada. Ninguno afirma cobertura: ni que se
#: cumpla, ni que este verificada, ni que alcance el 95 %. El nivel nominal
#: sigue publicandose en su propio campo, porque es un hecho de la construccion.
#:
#: Reemplazan a `nominal`, `admisible_con_advertencia`, `cobertura_insuficiente`
#: y `no_verificable`, que viajaban al CSV y a las tablas como identificador
#: visible y se leian como un juicio sobre la cobertura.
TIPO_BANDA_CALCULADA = "banda_calculada"
TIPO_RANGO_REFERENCIA = "rango_de_referencia"
TIPO_BANDA_NO_CALCULABLE = "banda_no_calculable"

#: Clave interna de decision -> identificador V-C publicado. La clave interna
#: sobrevive en `clasificacion_interna` para que el criterio aplicado siga
#: siendo auditable; lo que se publica como identificador es el valor V-C.
CLASIFICACION_VC = {
    "nominal": TIPO_BANDA_CALCULADA,
    "admisible_con_advertencia": TIPO_BANDA_CALCULADA,
    # CIERRE 08-08-2026: las dos clasificaciones que antes degradaban el
    # horizonte -cobertura bajo 0,80 y n < 16- se renombran para decir lo que
    # son: mediciones, no veredictos. La banda sigue siendo la calculada; lo que
    # cambia es la nota que la acompana.
    "cobertura_por_debajo_del_nominal": TIPO_RANGO_REFERENCIA,
    "medida_con_muestra_reducida": TIPO_BANDA_CALCULADA,
    # Unica imposibilidad de cobertura: no hay numero que publicar.
    "no_calculable": TIPO_RANGO_REFERENCIA,
    "banda_no_calculable": TIPO_BANDA_NO_CALCULABLE,
}

#: Etiqueta visible por identificador V-C. Describen la banda, no su resultado.
ETIQUETA_VISIBLE_VC = {
    TIPO_BANDA_CALCULADA: "Banda calculada para un nivel nominal del 95 %",
    TIPO_RANGO_REFERENCIA: "Rango de referencia",
    TIPO_BANDA_NO_CALCULABLE: "Banda no calculable",
}

#: Tipo de banda por clasificacion. Es una propiedad de la BANDA y no dice nada
#: sobre el estado del horizonte, que se publica en su propio campo. Se DERIVA
#: del vocabulario V-C para que no exista una segunda fuente que contradiga.
TIPO_BANDA_POR_CLASIFICACION = dict(CLASIFICACION_VC)

#: Etiqueta visible por clasificacion interna, derivada tambien de V-C.
ETIQUETA_VISIBLE_POR_CLASIFICACION = {
    clave: ETIQUETA_VISIBLE_VC[identificador]
    for clave, identificador in CLASIFICACION_VC.items()
}

#: La consecuencia sigue ligada a la clave INTERNA, no al identificador: dos
#: bandas con el mismo tipo pueden tener consecuencias distintas sobre el
#: horizonte, y esa distincion vive en su propio campo (V-C, apartado 7.3).
CONSECUENCIA_POR_CLASIFICACION = {
    "nominal": "El horizonte no se degrada por cobertura.",
    "admisible_con_advertencia": "El horizonte no se degrada por cobertura; se advierte.",
    "cobertura_por_debajo_del_nominal": (
        "El horizonte no se degrada por cobertura; se advierte la distancia al nivel nominal."
    ),
    "medida_con_muestra_reducida": (
        "El horizonte no se degrada; la cobertura se publica con su tamano de muestra."
    ),
    "no_calculable": (
        "No hay medicion de cobertura; la banda se comunica como rango de referencia."
    ),
    "banda_no_calculable": (
        "No se entrega banda; el horizonte no puede sostenerse en un intervalo."
    ),
}

LIMITACION_COBERTURA = (
    "La cobertura observada procede de errores walk-forward de una sola serie, que no son "
    "intercambiables: no es una garantia de cobertura futura. Debe leerse junto al numero de "
    "errores del paso exacto."
)


def _salida_clasificacion(
    clasificacion: str,
    *,
    cobertura_minima: float | None,
    degrada_a_escenario: bool,
    umbral_aplicado: str,
    advertencia: str,
    comunes: dict[str, Any],
) -> dict[str, Any]:
    """Arma la salida de la clasificacion con la etiqueta DERIVADA.

    La etiqueta visible, el tipo de banda y la consecuencia se deducen de
    ``clasificacion``. Antes se escribian a mano en cada rama, y bastaba con
    cambiar la clasificacion sin tocar la etiqueta para que la salida se
    contradijera a si misma.

    V-C: el identificador que se PUBLICA en ``clasificacion`` es el del
    vocabulario neutro. La clave con la que se decidio viaja aparte, en
    ``clasificacion_interna``, para que el criterio siga siendo auditable sin
    que un termino que juzga la cobertura llegue al CSV ni a las tablas.

    **Medir, publicar y decidir son tres cosas distintas.** Se separan en tres
    campos para que no vuelvan a confundirse:

    * ``cobertura_observada``       lo que se MIDIO. Se publica siempre que la
                                    evaluacion exista, aunque el paso no reuna
                                    el minimo de contrastes del criterio;
    * ``cobertura_apta_para_regla`` si esa medicion puede usarse en la regla
                                    productiva vigente;
    * ``cobertura_minima``          la magnitud con la que se DECIDIO. Queda
                                    vacia cuando no se uso ninguna.

    Antes, los tres eran el mismo valor, de modo que un paso con 10 aciertos de
    13 contrastes publicaba ``cobertura_observada = None``: el criterio
    operativo no solo gobernaba la decision, ademas borraba el dato observado.
    """
    identificador = CLASIFICACION_VC[clasificacion]
    # La cobertura del paso es la medicion; `cobertura_minima` solo esta
    # disponible cuando la medicion se uso para decidir. Cuando el llamador no
    # informa un paso -usos historicos y sinteticos- se conserva la segunda.
    medida = comunes.get("cobertura_paso_exacto")
    if medida is None and comunes.get("paso_exacto") is None:
        medida = cobertura_minima
    if clasificacion == "banda_no_calculable":
        # Excepcion deliberada, heredada de V-C. La cobertura por origen movil
        # describe como se comporto el PROCEDIMIENTO sobre los errores previos,
        # no la banda entregada. Cuando esa banda no existe -limites invertidos
        # o no finitos- publicar una cobertura a su lado se la atribuiria, y el
        # lector la leeria como si la banda inexistente hubiera cubierto algo.
        # El caso que esta sesion abre es otro: banda valida con pocos
        # contrastes. Ahi la cifra si describe la banda entregada.
        medida = cobertura_minima
    return {
        "clasificacion": identificador,
        "clasificacion_interna": clasificacion,
        "etiqueta": ETIQUETA_VISIBLE_VC[identificador],
        "etiqueta_visible": ETIQUETA_VISIBLE_VC[identificador],
        "tipo_banda": identificador,
        "nivel_nominal": NIVEL_NOMINAL_IC95,
        "cobertura_observada": medida,
        "cobertura_minima": cobertura_minima,
        "degrada_a_escenario": degrada_a_escenario,
        "umbral_aplicado": umbral_aplicado,
        "advertencia": advertencia,
        "limitacion": LIMITACION_COBERTURA,
        "consecuencia_operativa": CONSECUENCIA_POR_CLASIFICACION[clasificacion],
        **comunes,
    }


def min_errores_cobertura_vigente() -> int:
    """Minimo de errores exigido para verificar la cobertura, leido en ejecucion.

    Existe para que el valor NO quede ligado como argumento por omision. Un
    literal en la firma se evalua al definir la funcion: sustituir despues
    ``MIN_ERRORES_COBERTURA_EMPIRICA`` en el modulo no cambiaba nada, de modo
    que el 16 sobrevivia a su propia retirada y seguia imprimiendose en los
    informes. Leerlo aqui hace que la configuracion vigente mande siempre.

    El comportamiento productivo no cambia: devuelve el mismo 16 de siempre.
    """
    return int(globals().get("MIN_ERRORES_COBERTURA_EMPIRICA", 16))


#: Estados de una observacion dentro de la evaluacion de cobertura. Ninguno es
#: un umbral: los tres primeros describen por que el contraste no existe.
EVAL_CALCULABLE = "resultado_calculable"
EVAL_IMPOSIBLE = "imposibilidad_matematica"
EVAL_EVIDENCIA_LIMITADA = "evidencia_limitada"

MOTIVO_SIN_PREVIOS = "sin errores previos del mismo paso: no hay rango que construir"
MOTIVO_UN_PREVIO = "un solo error previo: la desviacion tipica muestral no existe"
MOTIVO_NO_FINITO = "el error o los limites del rango no son finitos"
MOTIVO_SIN_REAL = "el paso no tiene observacion real con la que contrastar"
MOTIVO_SIN_FECHA = "la observacion no declara origen o fecha objetivo"


def _observaciones_por_horizonte(
    backtesting_comparativo: dict[str, dict],
    modelo_codigo: str,
    horizontes: tuple[int, ...] | list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Observaciones OOS del modelo a cada horizonte exacto, con trazabilidad.

    `_errores_por_horizonte` devuelve solo el vector de errores y descarta el
    origen y la fecha objetivo. La evaluacion por origen movil los necesita: sin
    ellos no se puede declarar QUE observacion se evaluo, contra que rango, ni
    en que orden. Las observaciones se devuelven en el orden en que el
    backtesting recorrio los cortes, que es orden de origen creciente.
    """
    observaciones: dict[int, list[dict[str, Any]]] = {}
    for horizonte in horizontes:
        bt = backtesting_comparativo.get(f"{modelo_codigo}_h{int(horizonte)}") or {}
        predicciones = bt.get("predicciones")
        if not isinstance(predicciones, pd.DataFrame) or predicciones.empty:
            continue
        if "Error" not in predicciones:
            continue
        filas: list[dict[str, Any]] = []
        for _, fila in predicciones.iterrows():
            error = pd.to_numeric(fila.get("Error"), errors="coerce")
            filas.append(
                {
                    "origen": str(fila.get("Origen", "")),
                    "fecha_origen": str(fila.get("Origen", "")),
                    "paso": int(horizonte),
                    "fecha_objetivo": str(fila.get("Periodo", "")),
                    "modelo": str(fila.get("Modelo", "")),
                    "pronostico": float(fila["Predicho"]) if "Predicho" in fila else float("nan"),
                    "real": float(fila["Observado"]) if "Observado" in fila else float("nan"),
                    "error": float(error) if pd.notna(error) else float("nan"),
                    "error_absoluto": abs(float(error)) if pd.notna(error) else float("nan"),
                }
            )
        if filas:
            observaciones[int(horizonte)] = filas
    return observaciones


def evaluacion_cobertura_origen_movil(
    observaciones_por_horizonte: dict[int, list[dict[str, Any]]],
    paso_exacto: int | None = None,
) -> dict[str, Any]:
    """Evalua la cobertura por origen movil, sin particion fija.

    Para cada horizonte, cada error se contrasta contra el rango construido
    EXCLUSIVAMENTE con los errores anteriores del MISMO paso. El error evaluado
    nunca interviene en el rango que lo evalua y no se consulta ningun error
    posterior: el bucle avanza y cada iteracion solo mira hacia atras.

    Frente a la particion fija 50/50, que exige que ambos tramos sean
    utilizables, aqui con n errores se obtienen n-2 evaluaciones. Eso permite
    medir horizontes largos que antes quedaban sin cobertura por no reunir
    muestra para partirse.

    La funcion EVALUA; no calibra el intervalo entregado, que se construye
    aparte en `_cuantiles_intervalo` con todos los errores del paso y no cambia.

    Limitacion declarada: el origen movil amortigua los cambios de regimen,
    porque su rango absorbe el cambio a medida que ocurre. Ante un quiebre
    tardio informara una cobertura mejor que la particion fija.
    """
    filas: list[dict[str, Any]] = []
    trazabilidad: list[dict[str, Any]] = []
    cobertura_paso: float | None = None
    n_evaluados_paso = 0

    for horizonte in sorted(observaciones_por_horizonte):
        observaciones = observaciones_por_horizonte[horizonte]
        errores_previos: list[float] = []
        dentro_80: list[bool] = []
        dentro_95: list[bool] = []

        for observacion in observaciones:
            registro = dict(observacion)
            registro["n_errores_previos"] = len(errores_previos)
            error = float(observacion.get("error", float("nan")))

            motivo = ""
            estado = EVAL_CALCULABLE
            if not observacion.get("origen") or not observacion.get("fecha_objetivo"):
                estado, motivo = EVAL_IMPOSIBLE, MOTIVO_SIN_FECHA
            elif not math.isfinite(observacion.get("real", float("nan"))):
                estado, motivo = EVAL_IMPOSIBLE, MOTIVO_SIN_REAL
            elif not math.isfinite(error):
                estado, motivo = EVAL_IMPOSIBLE, MOTIVO_NO_FINITO
            elif len(errores_previos) == 0:
                estado, motivo = EVAL_IMPOSIBLE, MOTIVO_SIN_PREVIOS
            elif len(errores_previos) < 2:
                estado, motivo = EVAL_IMPOSIBLE, MOTIVO_UN_PREVIO

            if estado is EVAL_CALCULABLE and not motivo:
                # El rango se construye con los anteriores; el error evaluado
                # NO entra en el, y ningun posterior se consulta.
                offsets, _, _, _ = _cuantiles_intervalo(np.asarray(errores_previos, dtype=float))
                lo95, hi95 = float(offsets["lo95"]), float(offsets["hi95"])
                lo80, hi80 = float(offsets["lo80"]), float(offsets["hi80"])
                if not (math.isfinite(lo95) and math.isfinite(hi95)):
                    estado, motivo = EVAL_IMPOSIBLE, MOTIVO_NO_FINITO
                else:
                    acierto = bool(lo95 <= error <= hi95)
                    dentro_95.append(acierto)
                    dentro_80.append(bool(lo80 <= error <= hi80))
                    registro.update(
                        {
                            "limite_inferior_evaluacion": lo95,
                            "limite_superior_evaluacion": hi95,
                            "dentro_del_rango": acierto,
                        }
                    )
                    _, cola_observada = _semiancho_conformal(
                        np.abs(np.asarray(errores_previos, dtype=float)
                               - float(np.mean(errores_previos))),
                        0.05,
                    )
                    if not cola_observada:
                        registro["nota"] = (
                            "el cuantil de orden no existe con los errores previos; "
                            "el rango se sostiene en el respaldo parametrico"
                        )
                        estado = EVAL_EVIDENCIA_LIMITADA

            registro["estado_evaluacion"] = estado
            registro["incluido_evaluacion"] = bool(estado != EVAL_IMPOSIBLE)
            registro["motivo_exclusion"] = motivo
            trazabilidad.append(registro)

            # El error se acumula para las evaluaciones POSTERIORES, nunca para
            # la suya propia: esta linea va despues de evaluarlo.
            if math.isfinite(error):
                errores_previos.append(error)

        if not dentro_95:
            continue
        cobertura_95 = float(np.mean(dentro_95))
        if paso_exacto is not None and int(horizonte) == int(paso_exacto):
            cobertura_paso = cobertura_95
            n_evaluados_paso = len(dentro_95)
        filas.append(
            {
                "horizonte": int(horizonte),
                "n_errores": len(observaciones),
                "n_prueba": len(dentro_95),
                "cobertura_80": float(np.mean(dentro_80)) if dentro_80 else float("nan"),
                "cobertura_95": cobertura_95,
                "metodo": "origen_movil",
            }
        )

    return {
        "filas": filas,
        "trazabilidad": trazabilidad,
        "cobertura_paso": cobertura_paso,
        "n_evaluados_paso": n_evaluados_paso,
    }


def _cobertura_empirica_intervalos(
    errores_por_horizonte: dict[int, np.ndarray],
    min_errores: int | None = None,
    paso_exacto: int | None = None,
    observaciones_por_horizonte: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Comprueba la cobertura empírica del metodo de intervalos por horizonte.

    Evaluacion por **origen movil** (D-12b-C, integrada el 04-08-2026): cada
    error se contrasta contra el rango construido exclusivamente con los errores
    ANTERIORES del mismo paso. El error evaluado no interviene en su propio
    rango y no se consulta ningun error posterior.

    Sustituye a la particion fija 50/50, que exigia que ambos tramos fueran
    utilizables y por eso dejaba sin medir los horizontes largos: con 15 errores
    a h=12 y 9 a h=18 -los tamanos reales del anexo- la cobertura de esos pasos
    no se calculaba nunca, y son los que se consultan para presupuestos anuales.

    Lo que se evalua es la cobertura; el intervalo entregado se construye aparte
    en `_intervalos_prediccion` con todos los errores del paso y **no cambia**.

    ``paso_exacto`` es el horizonte que realmente se entrega. Su verificabilidad
    se mide por separado (RA-01): un paso con menos de ``min_errores`` errores
    fuera de muestra no queda verificado porque otro paso si los tenga. Ese
    minimo y los cortes de clasificacion siguen vigentes: D-1b-B no esta
    integrada.

    ``observaciones_por_horizonte`` aporta la trazabilidad por observacion
    -origen, fecha objetivo, pronostico y real-. Si no se recibe, se reconstruye
    desde los errores y la trazabilidad queda sin fechas.
    """
    # Lectura en tiempo de ejecucion: el llamador puede fijarlo, y si no lo hace
    # manda la configuracion vigente del modulo, no un literal ligado al definir.
    if min_errores is None:
        min_errores = min_errores_cobertura_vigente()

    n_paso_exacto = 0
    if paso_exacto is not None:
        errores_paso = np.asarray(errores_por_horizonte.get(int(paso_exacto), []), dtype=float)
        n_paso_exacto = int(np.isfinite(errores_paso).sum())
    # El minimo y los cortes de clasificacion NO cambian con D-12b-C: siguen
    # decidiendo la verificabilidad del paso. D-1b-B no esta integrada.
    verificable_paso = paso_exacto is not None and n_paso_exacto >= int(min_errores)

    # Si el llamador no aporta las observaciones con su trazabilidad, se
    # reconstruyen desde los errores. El orden de los vectores es el orden de
    # origen creciente que produce el backtesting walk-forward.
    if observaciones_por_horizonte is None:
        observaciones_por_horizonte = {
            int(h): [
                {
                    "origen": f"obs_{i + 1}",
                    "fecha_origen": "",
                    "paso": int(h),
                    "fecha_objetivo": f"paso_{i + 1}",
                    "modelo": "",
                    "pronostico": float("nan"),
                    "real": 0.0,
                    "error": float(e),
                    "error_absoluto": abs(float(e)),
                }
                for i, e in enumerate(np.asarray(v, dtype=float))
            ]
            for h, v in errores_por_horizonte.items()
        }

    evaluacion = evaluacion_cobertura_origen_movil(observaciones_por_horizonte, paso_exacto)
    filas = evaluacion["filas"]
    cobertura_paso = evaluacion["cobertura_paso"]
    trazabilidad = evaluacion["trazabilidad"]

    detalle_paso_exacto = {
        "n_origenes_evaluados_paso_exacto": int(evaluacion["n_evaluados_paso"]),
        "trazabilidad_cobertura": trazabilidad,
        "paso_exacto": int(paso_exacto) if paso_exacto is not None else None,
        "n_errores_paso_exacto": int(n_paso_exacto),
        "min_errores_exigidos": int(min_errores),
        "verificable_paso_exacto": bool(verificable_paso),
        "cobertura_95_paso_exacto": cobertura_paso,
    }
    if filas:
        minima_95 = min(float(fila["cobertura_95"]) for fila in filas)
        advertencias: list[str] = []
        if minima_95 < TOLERANCIA_COBERTURA_IC95:
            horizontes_bajos = [
                int(fila["horizonte"])
                for fila in filas
                if float(fila["cobertura_95"]) < TOLERANCIA_COBERTURA_IC95
            ]
            advertencias.append(
                f"La cobertura empírica del intervalo de predicción del 95% queda por debajo del "
                f"nominal en h={', h='.join(str(h) for h in horizontes_bajos)} "
                f"(mínimo observado {minima_95:.0%}); interpretar las bandas como referencia "
                "estimada y no como cobertura asegurada para esos horizontes."
            )
        if paso_exacto is not None and not verificable_paso:
            advertencias.append(
                f"El horizonte solicitado h={int(paso_exacto)} reune {n_paso_exacto} errores fuera "
                "de muestra, insuficientes para verificar su cobertura. "
                "La cobertura mínima global se informa como dato complementario y no "
                "sustituye la verificación de ese paso."
            )
        return {
            "verificable": True,
            "por_horizonte": filas,
            # El metodo se DECLARA en el resultado para que las salidas lo lean
            # de aqui y no lo den por supuesto en una frase fija.
            "metodo_evaluacion": "origen_movil",
            "cobertura_95_minima": minima_95,
            "advertencias": advertencias,
            "mensaje": (
                f"Cobertura empírica del intervalo de predicción evaluada por origen móvil "
                f"en {len(filas)} horizonte(s); nivel nominal 80% y 95%. "
                f"Cobertura mínima observada al 95%: {minima_95:.0%}."
            ),
            **detalle_paso_exacto,
        }
    return {
        "verificable": False,
        "por_horizonte": [],
        "metodo_evaluacion": "no_evaluable",
        "cobertura_95_minima": float("nan"),
        "advertencias": [
            "La cobertura empírica del intervalo de predicción del 95% no es verificable con la "
            "muestra de errores disponible; no se afirma haber alcanzado la cobertura nominal."
        ],
        "mensaje": "Cobertura empírica no verificable con la muestra disponible.",
        **detalle_paso_exacto,
    }


def _estados_banda_tabla(proyecciones: pd.DataFrame) -> list[str]:
    """Estado de la banda de cada paso de una tabla de proyecciones.

    Si la tabla ya trae la columna `estado_banda` se usa; si no -tablas
    historicas o construidas fuera de `_intervalos_prediccion`- se recalcula
    desde los limites, de modo que la comprobacion no dependa de quien la creo.
    """
    if "estado_banda" in proyecciones:
        return [str(v) for v in proyecciones["estado_banda"].tolist()]
    columnas = ("limite_inferior_95", "limite_superior_95", "indice_proyectado")
    if not all(c in proyecciones for c in columnas[:2]):
        return []
    pronosticos = (
        proyecciones["indice_proyectado"] if "indice_proyectado" in proyecciones
        else [None] * len(proyecciones)
    )
    return [
        estado_banda(inf, sup, pron)
        for inf, sup, pron in zip(
            proyecciones["limite_inferior_95"], proyecciones["limite_superior_95"], pronosticos
        )
    ]


def _evaluar_intervalos_prediccion(proyecciones: pd.DataFrame, horizonte: int | None = None) -> dict[str, Any]:
    """Evalua si los intervalos son defendibles frente al valor puntual."""
    if not isinstance(proyecciones, pd.DataFrame) or proyecciones.empty:
        return {
            "critico": False,
            "advertencias": [],
            "razones": [],
            "ancho_relativo_maximo": float("nan"),
            "ancho_relativo_80_maximo": float("nan"),
            "ancho_relativo_95_maximo": float("nan"),
        }
    if "ancho_relativo_95" in proyecciones:
        relativo95 = pd.to_numeric(proyecciones["ancho_relativo_95"], errors="coerce")
    else:
        ancho = (
            pd.to_numeric(proyecciones["limite_superior"], errors="coerce")
            - pd.to_numeric(proyecciones["limite_inferior"], errors="coerce")
        )
        base = pd.to_numeric(proyecciones["indice_proyectado"], errors="coerce").abs()
        relativo95 = (ancho / base.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    relativo80 = pd.to_numeric(proyecciones.get("ancho_relativo_80", pd.Series(dtype=float)), errors="coerce")
    max_rel95 = float(relativo95.max(skipna=True)) if relativo95.notna().any() else float("nan")
    max_rel80 = float(relativo80.max(skipna=True)) if relativo80.notna().any() else float("nan")
    h = int(horizonte or len(proyecciones))
    umbrales = _umbrales_incertidumbre(h)
    advertencias: list[str] = []
    razones: list[str] = []
    critico = False
    clasificacion = "No evaluado"

    # La validez de la banda se comprueba ANTES que su amplitud. Un intervalo
    # con los limites invertidos tiene ancho negativo y ninguna comparacion
    # `ancho > umbral` lo detecta: pasaba como la banda mas estrecha posible.
    estados = _estados_banda_tabla(proyecciones)
    invalidos = [e for e in estados if e not in (BANDA_VALIDA, BANDA_SEMIANCHO_CERO)]
    if invalidos:
        estado = invalidos[0]
        return {
            "critico": True,
            "advertencias": [],
            "razones": [MOTIVO_BANDA.get(estado, "Banda de prediccion no valida.")],
            "clasificacion": estado,
            "estado_banda": estado,
            "banda_valida": False,
            "ancho_relativo_maximo": float("nan"),
            "ancho_relativo_80_maximo": float("nan"),
            "ancho_relativo_95_maximo": float("nan"),
            "umbrales": umbrales,
        }

    if "advertencia_evidencia_oos" in proyecciones:
        for texto in proyecciones["advertencia_evidencia_oos"].dropna().astype(str).unique().tolist():
            if texto.strip():
                advertencias.append(texto.strip())
    if np.isfinite(max_rel95) and max_rel95 > umbrales["no_recomendado"]:
        critico = True
        clasificacion = "incertidumbre excesiva"
        razones.append(
            f"La incertidumbre del intervalo 95% es excesiva para h={h} (ancho relativo máximo {max_rel95:.1%})."
        )
    elif 13 <= h <= HORIZONTE_LARGO and np.isfinite(max_rel95) and max_rel95 >= UMBRAL_IC95_REL_EXTENDIDO_CERCANO:
        critico = True
        clasificacion = "incertidumbre excesiva"
        razones.append(
            f"La incertidumbre del intervalo 95% esta demasiado cerca del límite técnico para h={h} (ancho relativo máximo {max_rel95:.1%})."
        )
    elif np.isfinite(max_rel95) and max_rel95 > umbrales["cautela"]:
        clasificacion = "alta incertidumbre"
        advertencias.append(
            f"La incertidumbre del intervalo 95% es alta para h={h} (ancho relativo máximo {max_rel95:.1%})."
        )
    elif np.isfinite(max_rel95) and max_rel95 > umbrales["aceptable"]:
        clasificacion = "cautela"
        advertencias.append(
            f"El intervalo 95% requiere cautela para h={h} (ancho relativo máximo {max_rel95:.1%})."
        )
    elif np.isfinite(max_rel95):
        clasificacion = "aceptable"
    return {
        "critico": critico,
        "advertencias": advertencias,
        "razones": razones,
        "clasificacion": clasificacion,
        "ancho_relativo_maximo": max_rel95,
        "ancho_relativo_80_maximo": max_rel80,
        "ancho_relativo_95_maximo": max_rel95,
        "umbrales": umbrales,
    }


def _construir_tabla_proyecciones(
    t_futuro: np.ndarray,
    y_futuro: np.ndarray,
    intervalos: list[dict],
    ultimo_observado: float,
    anio_base: int,
    modelo: str,
    confianza: str,
    advertencias: list[str],
) -> pd.DataFrame:
    # P0-G REABIERTO, 14-08-2026: la tabla puede construirse SIN intervalos. Antes
    # se indexaba `intervalos[idx]` sin comprobar, porque el flujo nunca llegaba
    # aqui sin banda: el veto de ventanas cortaba mucho antes. Retirado ese veto,
    # un punto calculable con intervalo no construible debe seguir tabulandose;
    # las columnas del intervalo quedan vacias o no finitas, que es su valor
    # honesto, y `estado_banda` declara por que. NO se fabrica ninguna banda.
    sin_banda = {"estado_banda": BANDA_NO_CALCULABLE, "limite_inferior": float("nan"),
                 "limite_superior": float("nan")}
    filas = []
    for idx, (t_val, y_val) in enumerate(zip(t_futuro, y_futuro)):
        intervalo = intervalos[idx] if idx < len(intervalos) else sin_banda
        variacion = ((float(y_val) / ultimo_observado) - 1.0) * 100.0 if abs(ultimo_observado) > EPS_NUMERICO else float("nan")
        filas.append(
            {
                "periodo": t_a_periodo(int(t_val), anio_base).strip(),
                "indice_proyectado": float(y_val),
                "variacion_pct_ultimo_observado": variacion,
                "variacion_acumulada_pct": variacion,
                "factor_actualizacion": float(y_val / ultimo_observado) if abs(ultimo_observado) > EPS_NUMERICO else float("nan"),
                "limite_inferior_80": float(intervalo.get("limite_inferior_80", intervalo["limite_inferior"])),
                "limite_superior_80": float(intervalo.get("limite_superior_80", intervalo["limite_superior"])),
                "limite_inferior_95": float(intervalo.get("limite_inferior_95", intervalo["limite_inferior"])),
                "limite_superior_95": float(intervalo.get("limite_superior_95", intervalo["limite_superior"])),
                "limite_inferior": float(intervalo.get("limite_inferior_95", intervalo["limite_inferior"])),
                "limite_superior": float(intervalo.get("limite_superior_95", intervalo["limite_superior"])),
                "metodo_intervalo": intervalo.get("metodo", ""),
                "metodo_intervalo_codigo": intervalo.get("metodo_codigo", ""),
                "ventanas_oos_horizonte": intervalo.get("errores_oos_disponibles", ""),
                "paso_exacto_errores_oos": intervalo.get("horizonte_errores", ""),
                "sigma_h_intervalo": intervalo.get("sigma_h", float("nan")),
                "q80_intervalo": intervalo.get("q80", float("nan")),
                "q95_intervalo": intervalo.get("q95", float("nan")),
                "percentil_80_inf_intervalo": intervalo.get("percentil_80_inf", float("nan")),
                "percentil_80_sup_intervalo": intervalo.get("percentil_80_sup", float("nan")),
                "percentil_95_inf_intervalo": intervalo.get("percentil_95_inf", float("nan")),
                "percentil_95_sup_intervalo": intervalo.get("percentil_95_sup", float("nan")),
                "advertencia_evidencia_oos": intervalo.get("advertencia_evidencia_oos", ""),
                "ancho_relativo_80": intervalo.get("ancho_relativo_80", float("nan")),
                "ancho_relativo_95": intervalo.get("ancho_relativo_95", intervalo.get("ancho_relativo", float("nan"))),
                "ancho_relativo_intervalo": intervalo.get("ancho_relativo_95", intervalo.get("ancho_relativo", float("nan"))),
                "modelo": modelo,
                "nivel_confianza_metodologica": confianza,
                "advertencias": " | ".join(advertencias),
            }
        )
    return pd.DataFrame(filas)


def _candidatos_serializables(candidatos: list[dict], backtesting_por_modelo: dict[str, dict]) -> list[dict]:
    salida = []
    rmse_naive = _numero_finito((backtesting_por_modelo.get("naive", {}).get("metricas") or {}).get("rmse"))
    rmse_drift = _numero_finito((backtesting_por_modelo.get("drift", {}).get("metricas") or {}).get("rmse"))
    mae_naive = _numero_finito((backtesting_por_modelo.get("naive", {}).get("metricas") or {}).get("mae"))
    mae_drift = _numero_finito((backtesting_por_modelo.get("drift", {}).get("metricas") or {}).get("mae"))
    for candidato in candidatos:
        nombre = candidato.get("nombre", candidato.get("name", ""))
        metricas = candidato.get("metricas_ajuste", {})
        diagnostico = candidato.get("diagnostico_residuos", {})
        bt = backtesting_por_modelo.get(nombre, {})
        metricas_bt = bt.get("metricas") or {}
        rmse_bt = _numero_finito(metricas_bt.get("rmse"))
        mae_bt = _numero_finito(metricas_bt.get("mae"))
        salida.append(
            {
                "name": candidato.get("nombre_visible", candidato.get("name", nombre)),
                "nombre": nombre,
                "es_benchmark": bool(candidato.get("es_benchmark", False)),
                "r2": metricas.get("r2"),
                "r2_ajustado": metricas.get("r2_ajustado"),
                "aic": metricas.get("aic"),
                "aicc": metricas.get("aicc"),
                "mae_ajuste": metricas.get("mae"),
                "rmse_ajuste": metricas.get("rmse"),
                "mape_backtesting": metricas_bt.get("mape"),
                "rmse_backtesting": metricas_bt.get("rmse"),
                "mae_backtesting": metricas_bt.get("mae"),
                "smape_backtesting": metricas_bt.get("smape"),
                "mase_backtesting": metricas_bt.get("mase"),
                "sesgo_backtesting": metricas_bt.get("sesgo_medio"),
                "rrmse_naive": _ratio_local(rmse_bt, rmse_naive),
                "rrmse_drift": _ratio_local(rmse_bt, rmse_drift),
                "rmae_naive": _ratio_local(mae_bt, mae_naive),
                "rmae_drift": _ratio_local(mae_bt, mae_drift),
                "iteraciones_backtesting": bt.get("iteraciones"),
                "durbin_watson": diagnostico.get("durbin_watson"),
                "supera_naive_rmse": (candidato.get("comparacion_benchmarks") or {}).get("supera_naive_rmse"),
                "supera_drift_rmse": (candidato.get("comparacion_benchmarks") or {}).get("supera_drift_rmse"),
                "no_recomendado": bool(candidato.get("no_recomendado", False)),
                "alertas_residuos": diagnostico.get("alertas", []),
                "error": candidato.get("error", ""),
            }
        )
    return salida


# ==============================
# FUNCIÃ“N CENTRAL (entry point)
# ==============================

def ejecutar_analisis(
    file_bytes: bytes,
    file_name: str,
    selection: dict,
    year_proj: int,
    month_proj: int,
) -> dict:
    """
    FunciÃ³n central de anÃ¡lisis: carga datos, resuelve la selecciÃ³n jerÃ¡rquica,
    construye la serie histÃ³rica y ejecuta la proyecciÃ³n.

    Args:
        file_bytes: contenido binario del Excel.
        file_name: nombre del archivo.
        selection: parÃ¡metros de selecciÃ³n jerÃ¡rquica (ver resolver_fila_seleccionada).
        year_proj: aÃ±o de la proyecciÃ³n.
        month_proj: mes de la proyecciÃ³n (1-12).

    Returns:
        dict con:
          tables        dict de DataFrames
          year_month    lista de etiquetas
          fuente        str  tabla fuente del reporte
          fila          DataFrame de 1 fila (fila seleccionada)
          serie_df      DataFrame ['Periodo', 'Indice']
          projection    dict (resultado de ejecutar_proyeccion)

    Example::

        with open("ICOCIV.xlsx", "rb") as f:
            result = ejecutar_analisis(
                f.read(), "ICOCIV.xlsx",
                selection={"idx_g": 0, "chk_T16": False, ...},
                year_proj=2026, month_proj=3,
            )
        print(result["projection"]["y_proj"])
    """
    from app_icociv.datos.cargador_datos import cargar_todas_tablas
    from app_icociv.utilidades.utilidades import ANIO_BASE

    tables, year_month = cargar_todas_tablas(file_bytes, file_name)

    fuente, fila = resolver_fila_seleccionada(tables, year_month, selection)
    serie_df = construir_serie(fila, year_month)

    projection = ejecutar_proyeccion(
        serie_df,
        year_proj=year_proj,
        month_proj=month_proj,
        anio_base=ANIO_BASE,
    )

    return {
        "tables":     tables,
        "year_month": year_month,
        "fuente":     fuente,
        "fila":       fila,
        "serie_df":   serie_df,
        "projection": projection,
    }
