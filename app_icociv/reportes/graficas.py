"""Gráficas de los informes SAVIP, con la identidad visual de la aplicación.

Cada función devuelve PNG en bytes o ``None`` cuando no hay datos suficientes.
Devolver ``None`` es parte del contrato: el constructor de contenido omite la
sección entera y así nunca queda un título con un hueco debajo.

Ninguna función calcula estadística: solo dibuja lo que el resultado de la
proyección ya trae resuelto.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from app_icociv.reportes.modelo import PALETA, periodo_corto

# Sin efectos 3D ni decoración: rejilla tenue, dos o tres colores del tema y
# etiquetas legibles. El resto es ruido en un informe impreso.
_DPI = 160
_ALPHA_REJILLA = 0.22


def _figura(ancho: float = 8.6, alto: float = 4.2) -> tuple[Figure, Any]:
    figura = Figure(figsize=(ancho, alto), dpi=_DPI, facecolor="white")
    eje = figura.add_subplot(111)
    eje.set_facecolor("white")
    eje.grid(True, alpha=_ALPHA_REJILLA, color=PALETA["borde"], linewidth=0.7)
    for lado in ("top", "right"):
        eje.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        eje.spines[lado].set_color(PALETA["borde_fuerte"])
        eje.spines[lado].set_linewidth(0.8)
    eje.tick_params(colors=PALETA["texto_secundario"], labelsize=8)
    return figura, eje


def _exportar(figura: Figure) -> bytes:
    figura.tight_layout()
    memoria = io.BytesIO()
    figura.savefig(memoria, format="png", bbox_inches="tight", facecolor="white")
    return memoria.getvalue()


def _marcas_periodo(eje: Any, etiquetas: list[str], maximo: int = 10) -> None:
    if not etiquetas:
        return
    paso = max(1, len(etiquetas) // max(1, maximo - 1))
    marcas = list(range(0, len(etiquetas), paso))
    if len(etiquetas) - 1 not in marcas:
        marcas.append(len(etiquetas) - 1)
    eje.set_xticks(marcas)
    eje.set_xticklabels([etiquetas[i] for i in marcas], rotation=40, ha="right")


def _titulo(eje: Any, texto: str) -> None:
    eje.set_title(texto, color=PALETA["texto"], fontsize=10.5, pad=10, loc="left")


def grafica_principal(
    serie_df: pd.DataFrame,
    resultado: dict[str, Any],
    con_intervalo: bool = True,
) -> bytes | None:
    """Serie histórica, proyección, intervalo 95 % y divisoria observado/proyectado."""
    if not isinstance(serie_df, pd.DataFrame) or serie_df.empty or "Indice" not in serie_df:
        return None

    etiquetas_obs = [periodo_corto(p) for p in serie_df.get("Periodo", pd.Series(range(len(serie_df))))]
    y_obs = pd.to_numeric(serie_df["Indice"], errors="coerce").to_numpy(dtype=float)

    proyecciones = resultado.get("proyecciones")
    hay_proyeccion = isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty

    figura, eje = _figura(alto=4.4)
    x_obs = list(range(len(y_obs)))
    eje.plot(
        x_obs, y_obs,
        color=PALETA["marca"], linewidth=1.9, marker="o", markersize=3.0,
        label="Índice observado",
    )

    if hay_proyeccion:
        etiquetas_proy = [periodo_corto(p) for p in proyecciones["periodo"]]
        x_proy = list(range(len(y_obs) - 1, len(y_obs) - 1 + len(etiquetas_proy) + 1))
        y_proy = [float(y_obs[-1])] + _trayectoria_con_huecos(proyecciones)
        eje.plot(
            x_proy, y_proy,
            color=PALETA["acento"], linewidth=2.0, marker="o", markersize=3.4,
            linestyle="--", label="Índice proyectado",
        )
        # P0-H: un mes no disponible se marca en el eje y NO se une a sus vecinos.
        if _hay_hueco(proyecciones):
            eje.plot(
                [], [], linestyle="none", marker="x", markersize=5,
                color=PALETA["aviso"], label="Mes no disponible (sin valor publicado)",
            )
            for posicion, disponible in enumerate(proyecciones["horizonte_disponible"].tolist()):
                if not bool(disponible):
                    eje.axvline(
                        len(y_obs) + posicion,
                        color=PALETA["aviso"], linewidth=1.0, linestyle="-.", alpha=0.55,
                    )
        # P0-C RUTA C2: el intervalo se retira de las salidas; el calculo interno se conserva como diagnostico. La grafica de los informes deja de sombrear la banda.
        if False and con_intervalo and {"limite_inferior_95", "limite_superior_95"}.issubset(proyecciones.columns):
            inferior = [float(y_obs[-1])] + [float(v) for v in proyecciones["limite_inferior_95"]]
            superior = [float(y_obs[-1])] + [float(v) for v in proyecciones["limite_superior_95"]]
            eje.fill_between(
                x_proy, inferior, superior,
                color=PALETA["acento"], alpha=0.15, linewidth=0,
                label="Intervalo de predicción 95 %",
            )
        # Divisoria explícita entre lo observado y lo proyectado (§5.4).
        eje.axvline(len(y_obs) - 1, color=PALETA["borde_fuerte"], linewidth=1.1, linestyle=":")
        eje.annotate(
            "Último dato observado",
            xy=(len(y_obs) - 1, float(np.nanmax(y_obs))),
            xytext=(4, -2), textcoords="offset points",
            fontsize=7.5, color=PALETA["texto_secundario"],
        )
        etiquetas = etiquetas_obs + etiquetas_proy
    else:
        etiquetas = etiquetas_obs

    _titulo(eje, "Índice observado y proyección")
    eje.set_xlabel("Periodo", fontsize=8.5, color=PALETA["texto_secundario"])
    eje.set_ylabel("Índice", fontsize=8.5, color=PALETA["texto_secundario"])
    _marcas_periodo(eje, etiquetas)
    leyenda = eje.legend(loc="upper left", frameon=False, fontsize=8.5)
    for texto in leyenda.get_texts():
        texto.set_color(PALETA["texto"])
    return _exportar(figura)


def grafica_comparacion_modelos(resultado: dict[str, Any]) -> bytes | None:
    """RMSE de validación temporal por modelo evaluado."""
    filas = _filas_modelos(resultado)
    if len(filas) < 2:
        return None
    filas = sorted(filas, key=lambda f: f[1])[:10]
    nombres = [f[0] for f in filas]
    valores = [f[1] for f in filas]
    seleccionado = str(
        resultado.get("modelo_final_aplicado") or resultado.get("model_name") or ""
    ).strip().lower()

    figura, eje = _figura(alto=max(2.6, 0.42 * len(nombres) + 1.3))
    colores = [
        PALETA["marca"] if nombre.strip().lower() == seleccionado else PALETA["borde_fuerte"]
        for nombre in nombres
    ]
    posiciones = list(range(len(nombres)))[::-1]
    eje.barh(posiciones, valores, color=colores, height=0.62)
    eje.set_yticks(posiciones)
    eje.set_yticklabels(nombres, fontsize=8.5)
    eje.grid(True, axis="x", alpha=_ALPHA_REJILLA, color=PALETA["borde"], linewidth=0.7)
    eje.grid(False, axis="y")
    _titulo(eje, "RMSE por modelo en validación temporal (menor es mejor)")
    eje.set_xlabel("RMSE", fontsize=8.5, color=PALETA["texto_secundario"])
    for posicion, valor in zip(posiciones, valores):
        eje.annotate(
            f"{valor:,.4f}".replace(",", " ").replace(".", ","),
            xy=(valor, posicion), xytext=(4, 0), textcoords="offset points",
            va="center", fontsize=7.5, color=PALETA["texto_secundario"],
        )
    return _exportar(figura)


def _filas_modelos(resultado: dict[str, Any]) -> list[tuple[str, float]]:
    catalogo = resultado.get("catalogo_modelos") or []
    filas: list[tuple[str, float]] = []
    for item in catalogo:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("modelo") or item.get("nombre") or item.get("name") or "").strip()
        valor = item.get("rmse_backtesting", item.get("rmse"))
        if nombre and _finito(valor):
            filas.append((nombre, float(valor)))
    return filas


def grafica_errores_horizonte(resultado: dict[str, Any]) -> bytes | None:
    """Error de validación temporal según el horizonte de pronóstico."""
    info = resultado.get("analisis_horizontes_completo") or resultado.get("horizonte_info") or {}
    evaluaciones = info.get("tabla_horizontes") or info.get("evaluaciones") or []
    puntos = [
        (int(item["horizonte"]), float(item["rmse"]))
        for item in evaluaciones
        if isinstance(item, dict) and _finito(item.get("horizonte")) and _finito(item.get("rmse"))
    ]
    if len(puntos) < 2:
        return None
    puntos.sort()
    # P0-H, 17-08-2026 (V-CODEX-R3, residual 3). Un horizonte sin RMSE no aparecía
    # en la lista y `plot` unía sus vecinos con una recta, sugiriendo un error
    # medido donde no hay ninguno. Se rellena el tramo con `nan` para que la línea
    # se corte; el hueco pasa a verse como lo que es.
    medidos = dict(puntos)
    horizontes = list(range(puntos[0][0], puntos[-1][0] + 1))
    errores = [medidos.get(h, float("nan")) for h in horizontes]

    figura, eje = _figura(alto=3.4)
    eje.plot(horizontes, errores, color=PALETA["marca"], linewidth=1.9, marker="o", markersize=4)
    maximo = info.get("horizonte_maximo_recomendado")
    if _finito(maximo):
        eje.axvline(float(maximo), color=PALETA["aviso"], linewidth=1.2, linestyle="--")
        eje.annotate(
            f"Máximo recomendado: {int(float(maximo))} meses",
            xy=(float(maximo), float(np.nanmax(errores))), xytext=(5, -8), textcoords="offset points",
            fontsize=7.5, color=PALETA["aviso"],
        )
    _titulo(eje, "Error de validación temporal por horizonte")
    eje.set_xlabel("Horizonte (meses)", fontsize=8.5, color=PALETA["texto_secundario"])
    eje.set_ylabel("RMSE", fontsize=8.5, color=PALETA["texto_secundario"])
    return _exportar(figura)


def grafica_residuos(resultado: dict[str, Any]) -> bytes | None:
    """Residuos del ajuste a lo largo del tiempo.

    RA-03: en una serie bloqueada no hay ajuste, de modo que ``y_fit_obs`` llega
    vacio o con otra longitud que ``y_obs``. Restar ambos vectores levantaba un
    ``ValueError`` de broadcasting que rompia toda la exportacion DOCX/PDF. La
    grafica se omite de forma controlada: no se rellena ni se recorta nada, no
    se inventa un ajuste, y el contrato de devolver ``None`` deja la seccion
    fuera del informe.
    """
    y_obs = resultado.get("y_obs")
    y_fit = resultado.get("y_fit_obs")
    if y_obs is None or y_fit is None:
        return None
    observado = np.asarray(y_obs, dtype=float).ravel()
    ajustado = np.asarray(y_fit, dtype=float).ravel()
    if observado.size == 0 or observado.size != ajustado.size:
        return None
    residuos = observado - ajustado
    residuos = residuos[np.isfinite(residuos)]
    if residuos.size < 4:
        return None

    figura, eje = _figura(alto=3.2)
    eje.axhline(0, color=PALETA["borde_fuerte"], linewidth=1.0)
    eje.plot(range(len(residuos)), residuos, color=PALETA["marca"], linewidth=1.4, marker="o", markersize=3)
    _titulo(eje, "Residuos del modelo aplicado")
    eje.set_xlabel("Observación", fontsize=8.5, color=PALETA["texto_secundario"])
    eje.set_ylabel("Residuo", fontsize=8.5, color=PALETA["texto_secundario"])
    return _exportar(figura)


def grafica_atipicos(serie_df: pd.DataFrame, resultado: dict[str, Any]) -> bytes | None:
    """Serie con los periodos señalados como posible valor atípico.

    El patrón calendario se excluye a propósito: por decisión del proyecto un
    enero que cumple los criterios confirmados no es un valor atípico.
    """
    if not isinstance(serie_df, pd.DataFrame) or serie_df.empty or "Indice" not in serie_df:
        return None
    marcados = [
        item for item in (resultado.get("outliers") or [])
        if isinstance(item, dict) and item.get("severidad") == "posible_atipico"
    ]
    if not marcados:
        return None

    y = pd.to_numeric(serie_df["Indice"], errors="coerce").to_numpy(dtype=float)
    etiquetas = [periodo_corto(p) for p in serie_df.get("Periodo", pd.Series(range(len(serie_df))))]
    indices = [
        int(item["posicion"]) - 1
        for item in marcados
        if _finito(item.get("posicion")) and 0 <= int(item["posicion"]) - 1 < len(y)
    ]
    if not indices:
        return None

    figura, eje = _figura(alto=3.6)
    eje.plot(range(len(y)), y, color=PALETA["marca"], linewidth=1.6, label="Índice observado")
    eje.scatter(
        indices, [y[i] for i in indices],
        color=PALETA["error"], s=48, zorder=5, marker="D", label="Posible valor atípico",
    )
    _titulo(eje, "Periodos señalados como posible valor atípico")
    eje.set_xlabel("Periodo", fontsize=8.5, color=PALETA["texto_secundario"])
    eje.set_ylabel("Índice", fontsize=8.5, color=PALETA["texto_secundario"])
    _marcas_periodo(eje, etiquetas)
    leyenda = eje.legend(loc="upper left", frameon=False, fontsize=8.5)
    for texto in leyenda.get_texts():
        texto.set_color(PALETA["texto"])
    return _exportar(figura)


def grafica_calendario(serie_df: pd.DataFrame, resultado: dict[str, Any]) -> bytes | None:
    """Variación diciembre -> enero frente al movimiento mensual típico."""
    calendario = resultado.get("ajuste_calendario") or {}
    if not calendario.get("hay_evidencia_calendario") and not calendario.get("ajuste_calendario_aplicado"):
        return None
    if not isinstance(serie_df, pd.DataFrame) or serie_df.empty or "Periodo" not in serie_df:
        return None

    valores = pd.to_numeric(serie_df["Indice"], errors="coerce").to_numpy(dtype=float)
    etiquetas: list[str] = []
    saltos: list[float] = []
    for posicion in range(1, len(valores)):
        periodo = periodo_corto(serie_df["Periodo"].iloc[posicion])
        if not periodo.endswith("-01") or not math.isfinite(valores[posicion]) or valores[posicion - 1] <= 0:
            continue
        etiquetas.append(periodo[:4])
        saltos.append((valores[posicion] / valores[posicion - 1] - 1.0) * 100.0)
    if not saltos:
        return None

    tipico = calendario.get("movimiento_mensual_tipico_pct")
    figura, eje = _figura(alto=3.2)
    eje.bar(range(len(saltos)), saltos, color=PALETA["marca"], width=0.55)
    if _finito(tipico):
        eje.axhline(
            float(tipico), color=PALETA["aviso"], linewidth=1.2, linestyle="--",
            label="Movimiento mensual típico",
        )
        leyenda = eje.legend(loc="upper left", frameon=False, fontsize=8.5)
        for texto in leyenda.get_texts():
            texto.set_color(PALETA["texto"])
    eje.set_xticks(range(len(etiquetas)))
    eje.set_xticklabels(etiquetas, fontsize=8.5)
    _titulo(eje, "Variación de diciembre a enero por año")
    eje.set_xlabel("Enero de", fontsize=8.5, color=PALETA["texto_secundario"])
    eje.set_ylabel("Variación (%)", fontsize=8.5, color=PALETA["texto_secundario"])
    return _exportar(figura)


def _hay_hueco(proyecciones: pd.DataFrame) -> bool:
    """¿Algún paso de la trayectoria está marcado como no disponible?"""
    if "horizonte_disponible" not in proyecciones.columns:
        return False
    return not bool(proyecciones["horizonte_disponible"].astype(bool).all())


def _trayectoria_con_huecos(proyecciones: pd.DataFrame) -> list[float]:
    """Trayectoria con ``nan`` en los pasos no disponibles.

    P0-H, 17-08-2026 (V-CODEX-R3, residual 3). Matplotlib interrumpe la línea en
    un ``nan``, de modo que un mes no disponible deja de quedar unido a sus
    vecinos. Sin esto la gráfica dibujaba un segmento recto sobre el hueco, y ese
    trazo afirma visualmente un valor para un mes que el informe declara no
    disponible en la misma página. No es una interpolación distinta: es no
    dibujar.

    La disponibilidad la decide `horizonte_disponible`, calculada una sola vez en
    `_estructurar_resultado_horizontes`. Si la columna no viaja -tablas antiguas,
    resultados construidos a mano- se dibuja todo, que es el comportamiento
    anterior.
    """
    valores = [float(v) for v in proyecciones["indice_proyectado"]]
    if "horizonte_disponible" not in proyecciones.columns:
        return valores
    disponibles = proyecciones["horizonte_disponible"].tolist()
    return [
        valor if bool(disponible) else float("nan")
        for valor, disponible in zip(valores, disponibles)
    ]


def _finito(valor: Any) -> bool:
    if isinstance(valor, bool):
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False
