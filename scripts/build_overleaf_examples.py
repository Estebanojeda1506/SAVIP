"""Genera tablas LaTeX reproducibles con la serie real de Vias urbanas.

El script usa el mismo cargador del backend ICOCIV para localizar la ruta:

Grupo de obra:
Carreteras, calles, vias ferreas y pistas de aterrizaje, puentes,
carreteras elevadas y tuneles.

Subclase CPC:
Carreteras (excepto carreteras elevadas); calles.

Tipologia de obra:
Vias urbanas.

No inventa datos. Si la ruta no se encuentra, imprime trazabilidad de la
busqueda y detiene la generacion.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.estadistica.analisis_series import (  # noqa: E402
    calcular_variables_derivadas,
    detectar_valores_atipicos_mad,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.validacion.backtesting import ejecutar_backtesting  # noqa: E402
from app_icociv.estadistica.metricas import calcular_escala_naive_insample  # noqa: E402
from app_icociv.estadistica.modelos_interpretables import ajustar_modelo_interpretable  # noqa: E402
from app_icociv.datos.cargador_datos import cargar_todas_tablas  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import construir_serie, ejecutar_proyeccion  # noqa: E402
from app_icociv.utilidades.utilidades import ANIO_BASE, periodo_a_t, t_a_periodo  # noqa: E402


GRUPO_OBRA = (
    "Carreteras, calles, vías férreas y pistas de aterrizaje, "
    "puentes, carreteras elevadas y túneles"
)
SUBCLASE_CPC = "Carreteras (excepto carreteras elevadas); calles"
TIPOLOGIA_OBRA = "Vías urbanas"
HORIZONTES = (1, 3, 6, 12, 18)


@dataclass
class SerieLocalizada:
    archivo: Path
    fuente: str
    fila: pd.DataFrame
    serie: pd.DataFrame
    periodos: list[str]
    codigo_grupo: str
    codigo_subclase: str
    codigo_tipologia: str


def normalizar_texto(texto: Any) -> str:
    valor = str(texto).lower().replace("\xa0", " ")
    valor = "".join(
        c for c in unicodedata.normalize("NFD", valor) if unicodedata.category(c) != "Mn"
    )
    valor = re.sub(r"[^a-z0-9]+", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def escapar_tex(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    reemplazos = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(reemplazos.get(c, c) for c in texto)


def fmt(valor: Any, decimales: int = 4, sufijo: str = "") -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return escapar_tex(valor)
    if not math.isfinite(numero):
        return "No aplica"
    return f"{numero:.{decimales}f}{sufijo}"


def periodo_iso(periodo: Any) -> str:
    texto = str(periodo).strip().replace("-", "_").replace("/", "_")
    partes = texto.split("_")
    if len(partes) >= 2:
        try:
            return f"{int(partes[0]):04d}-{int(partes[1]):02d}"
        except ValueError:
            return texto
    return texto


def escribir_tabla(
    ruta: Path,
    caption: str,
    label: str,
    columnas: list[str],
    filas: Iterable[Iterable[Any]],
    alineacion: str | None = None,
    notas: str | None = None,
    landscape: bool = False,
) -> None:
    alineacion = alineacion or ("l" * len(columnas))
    fuente = (
        "Fuente: Elaboración propia con datos extraídos del anexo oficial ICOCIV "
        "del DANE y cálculos reproducibles de la aplicación."
    )
    notas = notas if notas and "Fuente:" in notas else f"{notas + ' ' if notas else ''}{fuente}"
    lineas = [
        *([r"\begin{landscape}"] if landscape else []),
        r"\begin{table}[H]",
        r"\centering",
        rf"\caption{{{escapar_tex(caption)}}}",
        rf"\label{{{label}}}",
        r"\tiny" if landscape else r"\scriptsize",
        r"\begin{adjustbox}{max width=\linewidth}",
        rf"\begin{{tabular}}{{{alineacion}}}",
        r"\toprule",
        " & ".join(escapar_tex(c) for c in columnas) + r" \\",
        r"\midrule",
    ]
    for fila in filas:
        lineas.append(" & ".join(str(c) for c in fila) + r" \\")
    lineas.extend([r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}"])
    if notas:
        lineas.append(rf"\par\footnotesize\textit{{{escapar_tex(notas)}}}")
    lineas.append(r"\end{table}")
    if landscape:
        lineas.append(r"\end{landscape}")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def buscar_archivo_excel() -> Path:
    preferidos = [
        ROOT / "anex-ICOCIV-ene2026.xlsb",
        ROOT / "pruebas app" / "anex-ICOCIV-ene2026.xlsb",
        ROOT / "pruebas app" / "anex-ICOCIV-nov2025.xlsb",
    ]
    for archivo in preferidos:
        if archivo.exists():
            return archivo
    candidatos = sorted(ROOT.glob("*.xlsb")) + sorted(ROOT.glob("*.xlsx"))
    if candidatos:
        return candidatos[0]
    raise FileNotFoundError("No se encontro un archivo ICOCIV .xlsb/.xlsx en el proyecto.")


def localizar_serie_real(archivo: Path | None = None) -> SerieLocalizada:
    archivo = archivo or buscar_archivo_excel()
    tablas, periodos = cargar_todas_tablas(archivo.read_bytes(), archivo.name)

    grupo_obj = normalizar_texto(GRUPO_OBRA)
    subclase_obj = normalizar_texto(SUBCLASE_CPC)
    tipologia_obj = normalizar_texto(TIPOLOGIA_OBRA)

    t16 = tablas["T_16"].copy()
    grupos = t16[t16["Grupos_Obra"].map(normalizar_texto) == grupo_obj]
    if grupos.empty:
        _fallar_busqueda("grupo de obra", archivo, tablas, {"T_16.Grupos_Obra": t16["Grupos_Obra"].dropna().unique()})
    grupo = grupos.iloc[0]
    codigo_grupo = str(grupo["Codigo_Grupos"])

    t161 = tablas["T_16_1"].copy()
    subclases = t161[
        (t161["Codigo_Grupos"].astype(str) == codigo_grupo)
        & (t161["Subclases"].map(normalizar_texto) == subclase_obj)
    ]
    if subclases.empty:
        disponibles = t161[t161["Codigo_Grupos"].astype(str) == codigo_grupo]["Subclases"].dropna().unique()
        _fallar_busqueda("subclase CPC", archivo, tablas, {"T_16_1.Subclases": disponibles})
    subclase = subclases.iloc[0]
    codigo_subclase = str(subclase["Cod_Subclases"])

    t162 = tablas["T_16_2"].copy()
    tipologias = t162[
        (t162["Codigo_Grupos"].astype(str) == codigo_grupo)
        & (t162["Cod_Subclases"].astype(str) == codigo_subclase)
        & (t162["Tip_obra"].map(normalizar_texto) == tipologia_obj)
    ]
    if tipologias.empty:
        disponibles = t162[
            (t162["Codigo_Grupos"].astype(str) == codigo_grupo)
            & (t162["Cod_Subclases"].astype(str) == codigo_subclase)
        ]["Tip_obra"].dropna().unique()
        _fallar_busqueda("tipologia de obra", archivo, tablas, {"T_16_2.Tip_obra": disponibles})

    fila = tipologias.iloc[[0]].copy()
    serie = construir_serie(fila, periodos)
    serie["Periodo_iso"] = serie["Periodo"].map(periodo_iso)
    return SerieLocalizada(
        archivo=archivo,
        fuente="T_16_2",
        fila=fila,
        serie=serie,
        periodos=periodos,
        codigo_grupo=codigo_grupo,
        codigo_subclase=codigo_subclase,
        codigo_tipologia=str(fila.iloc[0]["Cod_tip_obra"]),
    )


def _fallar_busqueda(etapa: str, archivo: Path, tablas: dict[str, pd.DataFrame], revisados: dict[str, Any]) -> None:
    detalles = [
        f"No se pudo localizar la serie real en la etapa: {etapa}.",
        f"Archivo revisado: {archivo}",
        f"Tablas disponibles: {', '.join(tablas)}",
        "Valores unicos revisados:",
    ]
    for campo, valores in revisados.items():
        detalles.append(f"- {campo}: {list(valores)[:30]}")
    raise RuntimeError("\n".join(detalles))


def preparar_analisis(localizada: SerieLocalizada) -> dict[str, Any]:
    metadatos = {
        "nombre_serie": TIPOLOGIA_OBRA,
        "nivel_agregacion": "Tipología de obra",
        "ruta_jerarquica": [
            {"nivel": "Grupo de obra", "valor": GRUPO_OBRA},
            {"nivel": "Subclase CPC", "valor": SUBCLASE_CPC},
            {"nivel": "Tipología de obra", "valor": TIPOLOGIA_OBRA},
        ],
        "archivo_fuente": localizada.archivo.name,
    }
    normalizada = normalizar_serie_mensual(localizada.serie, metadatos=metadatos)
    validacion = validar_serie_mensual(normalizada)
    derivadas = calcular_variables_derivadas(normalizada)
    serie_trabajo = derivadas["serie"].copy()
    outliers = detectar_valores_atipicos_mad(serie_trabajo)
    resultado = ejecutar_proyeccion(localizada.serie, 2027, 7, ANIO_BASE)
    return {
        "normalizada": normalizada,
        "validacion": validacion,
        "derivadas": derivadas,
        "serie_trabajo": serie_trabajo,
        "outliers": outliers,
        "resultado": resultado,
    }


def ultimos_origenes(serie: pd.DataFrame, horizonte: int) -> tuple[pd.DataFrame, pd.Series]:
    corte = len(serie) - horizonte
    if corte < 8:
        raise ValueError(f"No hay datos suficientes para origen con h={horizonte}.")
    return serie.iloc[:corte].copy(), serie.iloc[corte + horizonte - 1]


def generar_tablas(destino: Path, localizada: SerieLocalizada, analisis: dict[str, Any]) -> None:
    tablas_dir = destino / "tablas"
    tablas_dir.mkdir(parents=True, exist_ok=True)
    serie = analisis["serie_trabajo"].copy()
    serie["t"] = serie["Periodo"].apply(lambda p: periodo_a_t(p, ANIO_BASE))
    y = serie["Indice"].to_numpy(dtype=float)
    resultado = analisis["resultado"]
    validacion = analisis["validacion"]
    estad = analisis["derivadas"]["estadisticas"]
    outliers = analisis["outliers"]

    # Ruta y serie.
    escribir_tabla(
        tablas_dir / "ejemplo_ruta_vias_urbanas.tex",
        "Ruta jerárquica real utilizada para los ejemplos estadísticos",
        "tab:ejemplo_ruta_vias_urbanas",
        ["Nivel", "Valor", "Código"],
        [
            ["Grupo de obra", escapar_tex(GRUPO_OBRA), escapar_tex(localizada.codigo_grupo)],
            ["Subclase CPC", escapar_tex(SUBCLASE_CPC), escapar_tex(localizada.codigo_subclase)],
            ["Tipología de obra", escapar_tex(TIPOLOGIA_OBRA), escapar_tex(localizada.codigo_tipologia)],
        ],
        "p{0.20\\linewidth}p{0.58\\linewidth}p{0.14\\linewidth}",
        f"Fuente: {localizada.archivo.name}, tabla {localizada.fuente}.",
    )
    muestra = pd.concat([serie.head(5), serie.tail(5)]).drop_duplicates().reset_index(drop=True)
    escribir_tabla(
        tablas_dir / "ejemplo_serie_vias_urbanas.tex",
        "Primeros y últimos registros reales de la serie Vías urbanas",
        "tab:ejemplo_serie_vias_urbanas",
        ["Periodo", "Valor ICOCIV"],
        [[escapar_tex(periodo_iso(r.Periodo)), fmt(r.Indice, 4)] for r in muestra.itertuples()],
        "lr",
        f"Serie completa: {len(serie)} observaciones, de {periodo_iso(serie.iloc[0]['Periodo'])} a {periodo_iso(serie.iloc[-1]['Periodo'])}.",
    )

    # Validacion.
    faltantes = validacion.get("periodos_faltantes", [])
    escribir_tabla(
        tablas_dir / "ejemplo_validacion_vias_urbanas.tex",
        "Validación de datos de la serie real",
        "tab:ejemplo_validacion_vias_urbanas",
        ["Criterio", "Resultado en la serie real", "Interpretación"],
        [
            ["Observaciones", str(validacion.get("observaciones")), "Historia mensual disponible para análisis."],
            ["Periodo inicial", escapar_tex(periodo_iso(validacion.get("primer_periodo"))), "Primer mes observado."],
            ["Periodo final", escapar_tex(periodo_iso(validacion.get("ultimo_periodo"))), "Último mes observado."],
            ["Meses faltantes", str(len(faltantes)), "Cero indica continuidad mensual completa."],
            ["Duplicados", str(validacion.get("duplicados")), "Cero evita ambigüedad temporal."],
            ["Valores no numéricos", str(validacion.get("valores_no_numericos")), "Cero permite cálculo estadístico directo."],
            ["Valores no positivos", str(validacion.get("valores_no_positivos")), "Cero habilita modelos con ln."],
            ["Apta para modelos logarítmicos", "Sí" if validacion.get("valores_no_positivos") == 0 else "No", "Todos los índices son positivos."],
            ["Apta para backtesting", "Sí" if validacion.get("observaciones", 0) >= 24 else "No", "La longitud permite ventanas walk-forward."],
        ],
        "p{0.24\\linewidth}p{0.22\\linewidth}p{0.42\\linewidth}",
    )

    rango = estad["maximo"] - estad["minimo"]
    escribir_tabla(
        tablas_dir / "ejemplo_descriptivos_vias_urbanas.tex",
        "Estadísticos descriptivos reales de la serie Vías urbanas",
        "tab:ejemplo_descriptivos_vias_urbanas",
        ["Estadístico", "Valor real calculado", "Interpretación"],
        [
            ["Media", fmt(estad["media"], 4), "Nivel promedio histórico del índice."],
            ["Mediana", fmt(estad["mediana"], 4), "Valor central robusto de la serie."],
            ["Mínimo", fmt(estad["minimo"], 4), "Menor nivel observado."],
            ["Máximo", fmt(estad["maximo"], 4), "Mayor nivel observado."],
            ["Desviación estándar", fmt(estad["desviacion_estandar"], 4), "Dispersión del nivel histórico."],
            ["Coeficiente de variación", fmt(estad["coeficiente_variacion"] * 100.0, 2, "\\%"), "Dispersión relativa respecto a la media."],
            ["Rango", fmt(rango, 4), "Diferencia entre máximo y mínimo."],
        ],
        "p{0.25\\linewidth}p{0.18\\linewidth}p{0.45\\linewidth}",
    )

    # Variaciones.
    var = serie.dropna(subset=["variacion_mensual_pct"]).head(3)
    filas_var = []
    for idx in var.index:
        ant = serie.loc[idx - 1]
        act = serie.loc[idx]
        filas_var.append(
            [
                escapar_tex(periodo_iso(ant["Periodo"])),
                fmt(ant["Indice"], 4),
                escapar_tex(periodo_iso(act["Periodo"])),
                fmt(act["Indice"], 4),
                fmt(act["variacion_mensual_pct"], 4, "\\%"),
            ]
        )
    escribir_tabla(
        tablas_dir / "ejemplo_variacion_mensual_vias_urbanas.tex",
        "Cálculos reales de variación mensual",
        "tab:ejemplo_variacion_mensual_vias_urbanas",
        ["Periodo anterior", "y anterior", "Periodo actual", "y actual", "Variación mensual"],
        filas_var,
        "lrlrr",
    )
    variacion_acum = ((y[-1] / y[0]) - 1.0) * 100.0
    escribir_tabla(
        tablas_dir / "ejemplo_variacion_acumulada_vias_urbanas.tex",
        "Variación acumulada observada en la serie real",
        "tab:ejemplo_variacion_acumulada_vias_urbanas",
        ["Valor inicial y1", "Valor final yT", "Periodo inicial", "Periodo final", "Variación acumulada"],
        [[fmt(y[0], 4), fmt(y[-1], 4), escapar_tex(periodo_iso(serie.iloc[0]["Periodo"])), escapar_tex(periodo_iso(serie.iloc[-1]["Periodo"])), fmt(variacion_acum, 4, "\\%")]],
        "rrllr",
    )

    # Outliers.
    out_var = [o for o in outliers if o.get("escala") == "variacion_mensual_pct"]
    if out_var:
        validos = serie["variacion_mensual_pct"].dropna()
        mediana = float(validos.median())
        mad = float(np.median(np.abs(validos.to_numpy(dtype=float) - mediana)))
        filas_out = [
            [
                escapar_tex(periodo_iso(o.get("periodo"))),
                fmt(o.get("valor"), 4),
                fmt(mediana, 4),
                fmt(mad, 4),
                fmt(o.get("z_robusto"), 4),
                escapar_tex(o.get("severidad")),
            ]
            for o in sorted(out_var, key=lambda x: abs(float(x.get("z_robusto", 0))), reverse=True)[:8]
        ]
    else:
        filas_out = [["Sin alerta", "No aplica", "No aplica", "No aplica", "No aplica", "No atípico relevante"]]
    escribir_tabla(
        tablas_dir / "ejemplo_outliers_vias_urbanas.tex",
        "Detección robusta de atípicos sobre variación mensual",
        "tab:ejemplo_outliers_vias_urbanas",
        ["Periodo", "Valor analizado", "Mediana", "MAD", "z robusto", "Clasificación"],
        filas_out,
        "lrrrrl",
    )

    # Naive y Drift.
    y1 = y[0]
    y_t = y[-1]
    pendiente = (y_t - y1) / (len(y) - 1)
    escribir_tabla(
        tablas_dir / "ejemplo_naive_vias_urbanas.tex",
        "Pronósticos Naive con el último valor real observado",
        "tab:ejemplo_naive_vias_urbanas",
        ["Horizonte h", "Último valor observado yT", "Pronóstico Naive"],
        [[str(h), fmt(y_t, 4), fmt(y_t, 4)] for h in HORIZONTES],
        "rrr",
    )
    escribir_tabla(
        tablas_dir / "ejemplo_drift_vias_urbanas.tex",
        "Pronósticos Drift con pendiente promedio histórica real",
        "tab:ejemplo_drift_vias_urbanas",
        ["Horizonte h", "y1", "yT", "Pendiente promedio", "Pronóstico Drift"],
        [[str(h), fmt(y1, 4), fmt(y_t, 4), fmt(pendiente, 6), fmt(y_t + h * pendiente, 4)] for h in HORIZONTES],
        "rrrrr",
    )

    # Holt.
    filas_holt = []
    filas_holt_d = []
    filas_comp = []
    for h in (1, 3, 6, 12, 18):
        train, real = ultimos_origenes(serie, h)
        m_lineal = ajustar_modelo_interpretable("holt_lineal", train["t"], train["Indice"])
        m_damp = ajustar_modelo_interpretable("holt_amortiguado", train["t"], train["Indice"])
        t_obj = int(real["t"])
        pred_l = float(m_lineal["predict"]([t_obj])[0])
        pred_d = float(m_damp["predict"]([t_obj])[0])
        p_l = m_lineal["parametros"]
        p_d = m_damp["parametros"]
        origen = periodo_iso(train.iloc[-1]["Periodo"])
        filas_holt.append([escapar_tex(origen), fmt(p_l.get("alpha"), 4), fmt(p_l.get("beta"), 4), fmt(p_l.get("nivel_final"), 4), fmt(p_l.get("tendencia_final"), 4), str(h), fmt(pred_l, 4)])
        filas_holt_d.append([escapar_tex(origen), fmt(p_d.get("alpha"), 4), fmt(p_d.get("beta"), 4), fmt(p_d.get("phi"), 4), fmt(p_d.get("nivel_final"), 4), fmt(p_d.get("tendencia_final"), 4), str(h), fmt(pred_d, 4)])
        filas_comp.append([str(h), fmt(pred_l, 4), fmt(pred_d, 4), fmt(pred_l - pred_d, 4)])
    escribir_tabla(
        tablas_dir / "ejemplo_holt_lineal_vias_urbanas.tex",
        "Trazabilidad de Holt lineal en orígenes reales",
        "tab:ejemplo_holt_lineal_vias_urbanas",
        ["Origen r", "alpha", "beta", "nivel lr", "tendencia br", "h", "Pronóstico"],
        filas_holt,
        "lrrrrrr",
        "Los parámetros provienen del backend disponible; cuando no hay optimizador externo se usa el fallback documentado por la app.",
    )
    escribir_tabla(
        tablas_dir / "ejemplo_holt_amortiguado_vias_urbanas.tex",
        "Trazabilidad de Holt amortiguado en orígenes reales",
        "tab:ejemplo_holt_amortiguado_vias_urbanas",
        ["Origen r", "alpha", "beta", "phi", "nivel lr", "tendencia br", "h", "Pronóstico"],
        filas_holt_d,
        "lrrrrrrr",
    )
    escribir_tabla(
        tablas_dir / "ejemplo_holt_comparacion_vias_urbanas.tex",
        "Comparación de Holt lineal y Holt amortiguado desde los mismos orígenes",
        "tab:ejemplo_holt_comparacion_vias_urbanas",
        ["Horizonte h", "Holt lineal", "Holt amortiguado", "Diferencia"],
        filas_comp,
        "rrrr",
    )

    # Walk-forward y metricas.
    filas_walk = []
    for h in (1, 3, 6, 12, 18):
        bt = ejecutar_backtesting(serie[["Periodo", "Indice"]], horizonte=h, modelo="drift")
        pred = bt["predicciones"].tail(1)
        if pred.empty:
            continue
        p = pred.iloc[0]
        filas_walk.append([
            escapar_tex(str(p["Origen"])),
            f"{int(p['Observaciones_entrenamiento'])} obs.",
            "Drift",
            str(h),
            fmt(p["Predicho"], 4),
            fmt(p["Observado"], 4),
            fmt(p["Error"], 4),
        ])
    escribir_tabla(
        tablas_dir / "ejemplo_walkforward_vias_urbanas.tex",
        "Ejemplos reales de validación walk-forward con Drift",
        "tab:ejemplo_walkforward_vias_urbanas",
        ["Origen r", "Datos usados", "Modelo", "h", "Pronóstico", "Real", "Error"],
        filas_walk,
        "lllrrrr",
    )

    metricas_h = {int(e["horizonte"]): e for e in (resultado.get("horizonte_info") or {}).get("evaluaciones", [])}
    escribir_tabla(
        tablas_dir / "ejemplo_metricas_vias_urbanas.tex",
        "Métricas por horizonte calculadas con la serie real",
        "tab:ejemplo_metricas_vias_urbanas",
        ["h", "J h", "MAE", "RMSE", "MAPE", "sMAPE", "MASE"],
        [
            [
                str(h),
                str((resultado.get("backtesting_comparativo", {}).get(f"drift_h{h}", {}) or {}).get("iteraciones", "")),
                fmt(metricas_h[h].get("mae"), 4),
                fmt(metricas_h[h].get("rmse"), 4),
                fmt(metricas_h[h].get("mape"), 4, "\\%"),
                fmt(metricas_h[h].get("smape"), 4, "\\%"),
                fmt(metricas_h[h].get("mase"), 4),
            ]
            for h in HORIZONTES
            if h in metricas_h
        ],
        "rrrrrrr",
    )

    # MASE manual en el ultimo origen h=1 con Drift.
    train, real = ultimos_origenes(serie, 1)
    modelo_drift = ajustar_modelo_interpretable("drift", train["t"], train["Indice"])
    pred = float(modelo_drift["predict"]([float(real["t"])])[0])
    error = float(real["Indice"] - pred)
    escala = calcular_escala_naive_insample(train["Indice"].to_numpy(dtype=float))
    escribir_tabla(
        tablas_dir / "ejemplo_mase_vias_urbanas.tex",
        "Cálculo real de la escala MASE en un origen walk-forward",
        "tab:ejemplo_mase_vias_urbanas",
        ["Origen", "d r", "Error absoluto", "Error escalado", "Interpretación"],
        [[escapar_tex(periodo_iso(train.iloc[-1]["Periodo"])), fmt(escala, 4), fmt(abs(error), 4), fmt(abs(error) / escala, 4), "Error escalado de un origen real; no usa datos posteriores al origen."]],
        "lrrrp{0.34\\linewidth}",
    )

    # Benchmarks y seleccion.
    filas_bench = []
    for h in HORIZONTES:
        naive = resultado.get("backtesting_comparativo", {}).get(f"naive_h{h}", {}).get("metricas", {})
        drift = resultado.get("backtesting_comparativo", {}).get(f"drift_h{h}", {}).get("metricas", {})
        for modelo, met in (("Naive", naive), ("Drift", drift)):
            if not met:
                continue
            filas_bench.append([
                str(h),
                modelo,
                fmt(met.get("mae"), 4),
                fmt(met.get("rmse"), 4),
                fmt(met.get("mape"), 4, "\\%"),
                fmt(met.get("mase"), 4),
                "1.0000" if modelo == "Naive" else fmt(met.get("rmse") / naive.get("rmse"), 4),
                "1.0000" if modelo == "Drift" else fmt(met.get("rmse") / drift.get("rmse"), 4),
                "Benchmark de referencia" if modelo == "Naive" else "Benchmark con tendencia",
            ])
    escribir_tabla(
        tablas_dir / "ejemplo_benchmarks_vias_urbanas.tex",
        "Comparación real contra benchmarks Naive y Drift",
        "tab:ejemplo_benchmarks_vias_urbanas",
        ["Horizonte", "Modelo", "MAE", "RMSE", "MAPE", "MASE", "rRMSE vs Naive", "rRMSE vs Drift", "Decisión"],
        filas_bench,
        "rlrrrrrrp{0.18\\linewidth}",
    )
    escribir_tabla(
        tablas_dir / "ejemplo_seleccion_modelo_vias_urbanas.tex",
        "Selección de modelo por horizonte en la serie real",
        "tab:ejemplo_seleccion_modelo_vias_urbanas",
        ["h", "Modelo ganador", "Modelo final", "RMSE", "Estado y decisión"],
        [
            [
                str(e["horizonte"]),
                escapar_tex(e.get("modelo_evaluado")),
                escapar_tex(e.get("modelo_final_aplicado")),
                fmt(e.get("rmse"), 4),
                (
                    # H-4 residual, 18-08-2026 (micro-remediacion final post-R2
                    # residual). Se retira la rama "Escenario -- solo escenario":
                    # permitido_como_escenario == permitido_para_proyeccion_tecnica
                    # siempre en el evaluador vigente, de modo que nunca se
                    # alcanzaba (mismo invariante de determinar_horizonte_maximo_
                    # estadistico en app_icociv/proyeccion/servicio_proyeccion.py).
                    "Técnico -- permitir"
                    if e.get("permitido_para_proyeccion_tecnica")
                    else "No admisible -- negar"
                ),
            ]
            for e in (resultado.get("horizonte_info") or {}).get("evaluaciones", [])
            if int(e.get("horizonte", 0)) in {1, 3, 6, 12, 18, 20}
        ],
        "rp{0.24\\linewidth}p{0.20\\linewidth}rp{0.32\\linewidth}",
    )

    proy = resultado.get("proyecciones")
    filas_intervalos = []
    if isinstance(proy, pd.DataFrame):
        for h in (1, 3, 6, 12, 18):
            if h <= len(proy):
                fila = proy.iloc[h - 1]
                filas_intervalos.append([
                    str(h),
                    fmt(fila.get("indice_proyectado"), 4),
                    fmt(fila.get("limite_inferior_80"), 4),
                    fmt(fila.get("limite_superior_80"), 4),
                    fmt(fila.get("limite_inferior_95"), 4),
                    fmt(fila.get("limite_superior_95"), 4),
                    fmt(fila.get("ancho_relativo_95"), 4),
                ])
    escribir_tabla(
        tablas_dir / "ejemplo_intervalos_vias_urbanas.tex",
        "Intervalos de predicción por horizonte para la serie real",
        "tab:ejemplo_intervalos_vias_urbanas",
        ["Horizonte", "Proyección", "IC80 inferior", "IC80 superior", "IC95 inferior", "IC95 superior", "Ancho relativo IC95"],
        filas_intervalos,
        "rrrrrrr",
    )

    escribir_tabla(
        tablas_dir / "ejemplo_horizonte_maximo_vias_urbanas.tex",
        "Determinación dinámica del horizonte máximo en la serie real",
        "tab:ejemplo_horizonte_maximo_vias_urbanas",
        ["h", "J h", "Modelo final", "RMSE", "MAPE", "IC95 relativo", "Estado y decisión"],
        [
            [
                str(e["horizonte"]),
                str((resultado.get("backtesting_comparativo", {}).get(f"drift_h{int(e['horizonte'])}", {}) or {}).get("iteraciones", "")),
                escapar_tex(e.get("modelo_final_aplicado")),
                fmt(e.get("rmse"), 4),
                fmt(e.get("mape"), 4, "\\%"),
                fmt(e.get("ic95_relativo"), 4),
                (
                    # H-4 residual, 18-08-2026 (micro-remediacion final post-R2
                    # residual). Se retira la rama "Escenario -- solo escenario":
                    # permitido_como_escenario == permitido_para_proyeccion_tecnica
                    # siempre en el evaluador vigente, de modo que nunca se
                    # alcanzaba (mismo invariante de determinar_horizonte_maximo_
                    # estadistico en app_icociv/proyeccion/servicio_proyeccion.py).
                    "Técnico -- permitir"
                    if e.get("permitido_para_proyeccion_tecnica")
                    else "No admisible -- negar"
                ),
            ]
            for e in (resultado.get("horizonte_info") or {}).get("evaluaciones", [])
        ],
        "rrp{0.22\\linewidth}rrrp{0.31\\linewidth}",
        landscape=True,
    )

    info_h = resultado.get("horizonte_info") or {}
    escribir_tabla(
        tablas_dir / "ejemplo_resumen_horizontes_vias_urbanas.tex",
        "Separación de conceptos de horizonte en la ejecución real",
        "tab:ejemplo_resumen_horizontes_vias_urbanas",
        ["Concepto", "Definición operativa", "Valor real", "Uso en la aplicación"],
        [
            # H-4/P0-H residual, 18-08-2026 (micro-remediacion final post-R2
            # residual). "Maximo como escenario" nombraba un estado retirado, y
            # "consecutivo desde h=1" describia una continuidad que P0-H
            # (16-08-2026) retiro de ambos maximos: cada horizonte se juzga con
            # su propia evidencia, exista o no un hueco antes. La fila lee ahora
            # `horizonte_maximo_admisible` (de `_mayor_horizonte_permitido`), no
            # `horizonte_maximo_permitido_como_escenario` (de `max_escenario_puro`,
            # que busca clasificaciones retiradas y por eso vale 0 siempre).
            ["Horizonte solicitado", "Meses pedidos por el usuario.", str(info_h.get("horizonte_solicitado") or "No aplica"), "Resultado principal."],
            ["Máximo recomendado", "Mayor h clasificado como técnico, exista o no un hueco antes.", str(info_h.get("horizonte_maximo_recomendado") or "No identificado"), "Límite de proyección técnica."],
            ["Máximo admisible", "Mayor h permitido con evidencia propia, exista o no un hueco antes.", str(info_h.get("horizonte_maximo_admisible") or "No identificado"), "Coincide con el máximo recomendado por construcción en el evaluador vigente."],
            ["Máximo evaluado", "Último h con evaluación fuera de muestra.", str(info_h.get("horizonte_maximo_evaluado") or "No identificado"), "Borde de la grilla evaluada."],
            ["Límite operativo", "Máximo configurado para la auditoría.", str(info_h.get("horizonte_maximo_busqueda_configurado") or "No aplica"), "Control computacional, no recomendación."],
            ["Primer no viable", "Primer h evaluado y clasificado como no admisible.", str(info_h.get("primer_horizonte_no_viable") or "No identificado"), "Punto explícito de bloqueo."],
        ],
        "p{0.20\\linewidth}p{0.35\\linewidth}p{0.14\\linewidth}p{0.22\\linewidth}",
    )

    filas_rep = []
    if isinstance(proy, pd.DataFrame):
        for _, fila in proy.head(6).iterrows():
            h = int(fila.name) + 1
            eval_h = metricas_h.get(h, {})
            filas_rep.append([
                escapar_tex(periodo_iso(fila.get("periodo"))),
                "",
                fmt(fila.get("indice_proyectado"), 4),
                escapar_tex(fila.get("modelo")),
                str(h),
                fmt(fila.get("limite_inferior_95"), 4),
                fmt(fila.get("limite_superior_95"), 4),
                escapar_tex(eval_h.get("estado", "")),
            ])
    escribir_tabla(
        tablas_dir / "ejemplo_reproducibilidad_vias_urbanas.tex",
        "Fragmento reproducible de la proyección exportable",
        "tab:ejemplo_reproducibilidad_vias_urbanas",
        ["Periodo", "Observado", "Proyectado", "Modelo", "Horizonte", "IC95 inferior", "IC95 superior", "Clasificación"],
        filas_rep,
        "llrlrrrr",
    )

    (tablas_dir / "trazabilidad_serie_vias_urbanas.txt").write_text(
        "\n".join(
            [
                f"archivo={localizada.archivo}",
                f"fuente={localizada.fuente}",
                f"codigo_grupo={localizada.codigo_grupo}",
                f"codigo_subclase={localizada.codigo_subclase}",
                f"codigo_tipologia={localizada.codigo_tipologia}",
                f"observaciones={len(serie)}",
                f"periodo_inicial={serie.iloc[0]['Periodo']}",
                f"periodo_final={serie.iloc[-1]['Periodo']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destino",
        default=str(ROOT / "Documentación overleaf para avances"),
        help="Carpeta del proyecto Overleaf que recibira las tablas.",
    )
    parser.add_argument("--archivo", default="", help="Archivo ICOCIV .xlsb/.xlsx opcional.")
    args = parser.parse_args()
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    archivo = Path(args.archivo) if args.archivo else None
    localizada = localizar_serie_real(archivo)
    analisis = preparar_analisis(localizada)
    generar_tablas(destino, localizada, analisis)
    print(f"Serie localizada en {localizada.archivo.name}: {len(localizada.serie)} observaciones.")
    print(f"Tablas generadas en: {destino / 'tablas'}")


if __name__ == "__main__":
    main()
