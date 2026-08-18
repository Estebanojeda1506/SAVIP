"""Pruebas focales para observaciones de auditoria estadística."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.estadistica.analisis_series import detectar_valores_atipicos_mad
from app_icociv.validacion.backtesting import ejecutar_backtesting
from app_icociv.estadistica.criterios import CRITERIOS_ESTADISTICOS, exportar_matriz_criterios_markdown
from app_icociv.estadistica.diagnostico_residuos import evaluar_residuos
from app_icociv.estadistica.metricas import calcular_escala_naive_insample, calcular_mase_por_origen
from app_icociv.estadistica.modelos_interpretables import ajustar_modelo_interpretable
from app_icociv.proyeccion.servicio_proyeccion import _intervalos_prediccion
from app_icociv.reportes.generador_reportes import (
    construir_dataframe_reproducibilidad,
    generar_reporte_html,
    _lineas_ejemplo_dinamico,
)
from scripts.build_overleaf_examples import localizar_serie_real


def _ruta_guia() -> Path:
    """Guia academica vigente; ver documentacion_latex/LEEME.md."""
    guia = ROOT / "documentacion_latex" / "guia_academica_estadistica"
    if (guia / "main.tex").exists() and (guia / "referencias.bib").exists():
        return guia
    raise AssertionError("No se encontro el proyecto LaTeX de la guia academica.")


def _periodos(n: int) -> list[str]:
    return [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(n)]


def probar_exponencial_log_lineal_con_smearing() -> None:
    t = np.arange(1, 13, dtype=float)
    multiplicador = np.array([1.00, 1.05, 0.98, 1.02, 1.08, 0.97, 1.03, 1.01, 1.04, 0.99, 1.06, 1.02])
    y = np.exp(4.5 + 0.01 * t) * multiplicador
    modelo = ajustar_modelo_interpretable("exponencial_log_lineal", t, y)
    params = modelo["parametros"]
    assert params["metodo_retransformacion"] == "smearing_duan"
    assert params["logaritmo"] == "ln"
    assert params["sigma2_log"] >= 0
    assert params["smearing_factor"] > 0
    futuro = np.array([13.0])
    esperado = math.exp(params["beta_0"] + params["beta_1"] * 13.0) * params["smearing_factor"]
    obtenido = float(modelo["predict"](futuro)[0])
    assert math.isclose(obtenido, esperado, rel_tol=1e-12)

    try:
        ajustar_modelo_interpretable("exponencial_log_lineal", t, np.r_[y[:-1], 0.0])
    except ValueError as exc:
        assert "positivos" in str(exc)
    else:
        raise AssertionError("El modelo log-lineal debe rechazar valores no positivos.")


def probar_mase_por_origen_sin_fuga_futura() -> None:
    entrenamiento = np.array([10.0, 12.0, 15.0, 19.0])
    escala = calcular_escala_naive_insample(entrenamiento)
    assert math.isclose(escala, (2.0 + 3.0 + 4.0) / 3.0)
    mase = calcular_mase_por_origen([3.0, 6.0], [3.0, 4.0])
    assert math.isclose(mase, (1.0 + 1.5) / 2.0)

    serie = pd.DataFrame({"Periodo": _periodos(14), "Indice": np.linspace(100, 130, 14)})
    bt = ejecutar_backtesting(serie, entrenamiento_inicial=6, horizonte=1, modelo="naive")
    pred = bt["predicciones"]
    primera_escala = float(pred.iloc[0]["Escala_naive_insample"])
    escala_manual = calcular_escala_naive_insample(serie["Indice"].iloc[:6].to_numpy(dtype=float))
    assert math.isclose(primera_escala, escala_manual)
    assert "mase_denominador" in bt["metricas"]


def probar_atipicos_z_robusto_y_mad_cero() -> None:
    df = pd.DataFrame(
        {
            "Periodo": _periodos(10),
            "variacion_mensual_pct": [-1, -1, -1, 0, 0, 0, 1, 1, 1, 8],
        }
    )
    alertas = detectar_valores_atipicos_mad(df, columnas=("variacion_mensual_pct",))
    posibles = [a for a in alertas if a.get("severidad") == "posible_atipico"]
    assert posibles and posibles[0]["periodo"] == _periodos(10)[-1]
    assert posibles[0]["escala"] == "variacion_mensual_pct"
    assert posibles[0]["criterio_id"] == "C-ATI-001"
    assert "umbral_moderado" not in posibles[0]
    assert "umbral_fuerte" not in posibles[0]

    df_cero = pd.DataFrame({"Periodo": _periodos(8), "variacion_mensual_pct": [0.0] * 8})
    alertas_cero = detectar_valores_atipicos_mad(df_cero, columnas=("variacion_mensual_pct",))
    assert any(a.get("severidad") == "mad_cero" for a in alertas_cero)


def probar_matriz_criterios_auditable() -> None:
    ids = {criterio.id for criterio in CRITERIOS_ESTADISTICOS}
    assert "C-ATI-001" in ids
    assert "C-ATI-002" in ids
    for criterio in CRITERIOS_ESTADISTICOS:
        assert criterio.tipo
        assert criterio.fuente
        assert criterio.accion
    salida = exportar_matriz_criterios_markdown(ROOT / "docs" / "auditoria_criterios_estadisticos.md")
    texto = salida.read_text(encoding="utf-8")
    assert "operativo_interno" in texto
    assert "no deben presentarse como verdades universales" in texto
    assert "3.5-4.5; 4.5-5.0; >5.0" in texto
    tex = (_ruta_guia() / "main.tex").read_text(encoding="utf-8")
    assert "3.5<|M_i|\\leq 4.5" not in tex
    assert "|M_i|>5.0" not in tex


def probar_durbin_watson_descriptivo_y_rangos() -> None:
    positivo = evaluar_residuos(np.arange(1, 30, dtype=float), tipo_modelo="lineal")
    assert positivo["durbin_watson"] < 0.8
    assert "positiva" in positivo["durbin_watson_interpretacion"]

    alternante = evaluar_residuos(np.array([1.0, -1.0] * 20), tipo_modelo="holt_lineal")
    assert alternante["durbin_watson"] > 3.2
    assert alternante["durbin_watson_alcance"] == "descriptivo_no_ols"
    assert "negativa" in alternante["durbin_watson_interpretacion"]


def probar_intervalos_por_horizonte_y_metodos() -> None:
    """Cada paso usa los errores de su propio horizonte; sin bandas fabricadas."""
    errores = {
        1: np.array([-3.0, -1.0, 0.0, 1.0, 2.0, 4.0]),
        2: np.array([-5.0, -2.0, 0.0, 2.0, 3.0, 6.0]),
    }
    intervalos = _intervalos_prediccion(
        y_futuro=np.array([120.0, 121.0]),
        errores_por_horizonte=errores,
    )
    primero, segundo = intervalos[0], intervalos[1]
    # AUDITORIA 09-08-2026 (P0-C): el codigo de metodo cambia al adoptarse la
    # construccion completa de FPP3 5.5 en lugar del max(cuantil, t).
    assert primero["metodo_codigo"] == "fpp3_sigma_h"
    assert int(primero["errores_oos_disponibles"]) == 6
    assert int(primero["horizonte_errores"]) == 1
    assert int(segundo["horizonte_errores"]) == 2
    # El horizonte 2 tiene errores mas dispersos: su banda no puede ser mas estrecha.
    ancho_1 = float(primero["limite_superior_95"]) - float(primero["limite_inferior_95"])
    ancho_2 = float(segundo["limite_superior_95"]) - float(segundo["limite_inferior_95"])
    assert ancho_2 >= ancho_1
    # AUDITORIA 09-08-2026 (P0-C): la advertencia dejo de hablar de la cola del
    # cuantil, porque esa construccion se retiro.
    #
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residuales 1 y 2). Dos cambios:
    #
    #  * la advertencia dejo de publicar sigma_h, el nivel nominal y la cobertura
    #    del intervalo retirado: eran cinco superficies publicas caracterizando un
    #    objeto que no se entrega;
    #  * su disparo dejo de ser `n < 8` -un corte referido a la estabilidad de
    #    sigma_h- y paso a ser el tramo descriptivo de evidencia OOS. Con
    #    exactamente seis errores el paso ya esta en el tramo superior, de modo
    #    que NO se advierte, y eso es lo correcto: no hay nada limitado que
    #    declarar.
    #
    # Se comprueban las dos direcciones: el borde superior no advierte, y una
    # muestra menor si lo hace, declarando su tamano y sin vocabulario retirado.
    assert not str(primero["advertencia_evidencia_oos"]).strip(), (
        "seis errores estan en el tramo superior: no debe advertirse. "
        f"{primero['advertencia_evidencia_oos']}"
    )
    _corto = _intervalos_prediccion(
        y_futuro=np.array([120.0]),
        # Tres es el minimo con que `_intervalos_prediccion` construye la banda
        # interna; por debajo se niega a fabricarla y levanta, que es el contrato
        # de P0-G y no se toca aqui.
        errores_por_horizonte={1: np.asarray(errores[1], dtype=float)[:3]},
    )[0]
    _adv = str(_corto["advertencia_evidencia_oos"]).lower()
    assert "limitada" in _adv, _corto["advertencia_evidencia_oos"]
    assert "n=3" in _adv, _corto["advertencia_evidencia_oos"]
    for _retirado in ("σ", "nivel nominal", "cobertura"):
        assert _retirado not in _adv, _corto["advertencia_evidencia_oos"]

    # Un paso sin errores del horizonte no produce banda inventada.
    try:
        _intervalos_prediccion(y_futuro=np.array([120.0, 121.0]), errores_por_horizonte={1: errores[1]})
    except ValueError as exc:
        assert "paso 2" in str(exc)
    else:
        raise AssertionError("Debe rechazarse un paso sin errores OOS suficientes.")


def probar_holt_condicional_y_arima_retirado() -> None:
    t = np.arange(1, 49, dtype=float)
    y = 100.0 + 0.35 * t + 0.6 * np.sin(t / 5.0)
    holt = ajustar_modelo_interpretable("holt_lineal", t, y)
    params_holt = holt["parametros"]
    assert "alpha" in params_holt and "beta" in params_holt
    assert "criterio_estimacion" in params_holt
    amortiguado = ajustar_modelo_interpretable("holt_amortiguado", t, y)
    assert "phi" in amortiguado["parametros"]

    try:
        ajustar_modelo_interpretable("arima_simple", t, y)
    except ValueError as exc:
        assert "no soportado" in str(exc)
    else:
        raise AssertionError("arima_simple fue retirado del alcance y no debe ser ajustable.")


def probar_csv_y_latex_con_trazabilidad_metodologica() -> None:
    serie = pd.DataFrame({"Periodo": ["2026_1", "2026_2"], "Indice": [138.64, 139.1]})
    proy = pd.DataFrame(
        [
            {
                "periodo": "2026_2",
                "indice_proyectado": 139.0,
                "limite_inferior_80": 138.0,
                "limite_superior_80": 140.0,
                "limite_inferior_95": 137.0,
                "limite_superior_95": 141.0,
                "factor_actualizacion": 139.0 / 138.64,
                "variacion_acumulada_pct": ((139.0 / 138.64) - 1.0) * 100.0,
                "modelo": "exponencial_log_lineal",
                "metodo_intervalo": "intervalo empírico centrado con errores out-of-sample de backtesting para h=1",
                "ventanas_oos_horizonte": 8,
                "paso_exacto_errores_oos": 1,
                "sigma_h_intervalo": 0.7,
                "q80_intervalo": np.nan,
                "q95_intervalo": np.nan,
                "percentil_80_inf_intervalo": -0.8,
                "percentil_80_sup_intervalo": 0.8,
                "percentil_95_inf_intervalo": -1.2,
                "percentil_95_sup_intervalo": 1.2,
                "advertencia_evidencia_oos": "",
                "ancho_relativo_95": 0.03,
            }
        ]
    )
    resultado = {
        "nombre_serie": "Vias urbanas",
        "model_name": "Exponencial/log-lineal",
        "modelo_codigo": "exponencial_log_lineal",
        "horizonte_permitido": 1,
        "horizonte_solicitado": 1,
        "parametros_modelo": {"metodo_retransformacion": "smearing_duan", "sigma2_log": 0.01, "smearing_factor": 1.02},
        "proyecciones": proy,
        "horizonte_info": {
            "horizonte_maximo_recomendado": 1,
            "evaluaciones": [{"horizonte": 1, "estado": "Confiabilidad media", "modelo_final_aplicado": "Exponencial/log-lineal"}],
        },
    }
    ruta = [
        {"nivel": "Grupo de obra", "valor": "Carreteras, calles, vias ferreas y pistas de aterrizaje"},
        {"nivel": "Subclase CPC", "valor": "Carreteras (excepto carreteras elevadas); calles"},
        {"nivel": "Tipologia de obra", "valor": "Vias urbanas"},
    ]
    csv_df = construir_dataframe_reproducibilidad(serie, resultado, ruta)
    assert "metodo_retransformacion" in csv_df.columns
    assert "ventanas_oos_horizonte" in csv_df.columns
    assert "ruta_jerarquica" in csv_df.columns
    assert csv_df.iloc[-1]["metodo_retransformacion"] == "smearing_duan"
    assert "Vias urbanas" in str(csv_df.iloc[-1]["ruta_jerarquica"])

    ejemplo = _lineas_ejemplo_dinamico(serie, resultado, ruta)
    assert any("serie seleccionada" in linea.lower() for linea in ejemplo)
    assert any("Vias urbanas" in linea for linea in ejemplo)

    guia = _ruta_guia()
    tex = (guia / "main.tex").read_text(encoding="utf-8")
    bib = (guia / "referencias.bib").read_text(encoding="utf-8")
    assert "smearing" in tex
    assert "MASE_h" in tex
    assert "1.2816" in tex and "1.96" in tex
    assert "\\ln" in tex
    assert "Matriz de trazabilidad conceptual" in tex
    ruta_tex = (guia / "tablas" / "ejemplo_ruta_vias_urbanas.tex").read_text(encoding="utf-8")
    assert "Carreteras, calles" in ruta_tex and "urbanas" in ruta_tex
    assert "duan1983" in bib


def probar_overleaf_usa_serie_real_y_diagramas_divididos() -> None:
    localizada = localizar_serie_real()
    assert len(localizada.serie) == 61
    assert localizada.codigo_grupo == "530201"
    assert localizada.codigo_subclase == "53211"
    assert localizada.codigo_tipologia == "53211_07"
    assert localizada.serie.iloc[0]["Periodo"] == "2021_1"
    assert localizada.serie.iloc[-1]["Periodo"] == "2026_1"

    guia = _ruta_guia()
    tex = (guia / "main.tex").read_text(encoding="utf-8")
    assert "Ejemplo aplicado con una serie ilustrativa" not in tex
    assert "ejemplo_serie_vias_urbanas" in tex
    assert "fig:flujo_preparacion_modelado" in tex
    assert "fig:flujo_validacion_exportacion" in tex
    assert (guia / "figuras" / "flujo_preparacion_modelado.tex").exists()
    assert (guia / "figuras" / "flujo_validacion_exportacion.tex").exists()
    for nombre in [
        "ejemplo_validacion_vias_urbanas.tex",
        "ejemplo_metricas_vias_urbanas.tex",
        "ejemplo_horizonte_maximo_vias_urbanas.tex",
        "ejemplo_reproducibilidad_vias_urbanas.tex",
    ]:
        contenido = (guia / "tablas" / nombre).read_text(encoding="utf-8")
        assert "No aplica" not in contenido


def probar_html_exportable_dinamico() -> None:
    import tempfile

    serie = pd.DataFrame({"Periodo": ["2026_1", "2026_2"], "Indice": [138.64, 139.1]})
    resultado = {
        "model_name": "Drift",
        "modelo_codigo": "drift",
        "horizonte_permitido": 1,
        "horizonte_solicitado": 1,
        "proyeccion_generada": False,
        "validacion_serie": {"observaciones": 2, "continuidad_temporal": "OK", "duplicados": 0, "valores_faltantes": 0, "valores_no_numericos": 0, "longitud_minima": "REVISAR"},
        "factibilidad": {"factible": False, "estado": "No proyectable", "nivel_confianza_metodologica": "bajo", "advertencias": [], "razones_tecnicas": []},
        "horizonte_info": {"horizonte_maximo_recomendado": 1, "evaluaciones": [{"horizonte": 1, "estado": "Cautela", "modelo_final_aplicado": "Drift"}]},
    }
    ruta = [{"nivel": "Tipologia de obra", "valor": "Vias urbanas"}]
    salida = Path(tempfile.gettempdir()) / "icociv_prueba_html.html"
    generar_reporte_html(salida, "Esteban", "fuente.xlsb", {}, {}, ruta, "A16", pd.DataFrame(), serie, resultado, [])
    html = salida.read_text(encoding="utf-8")
    assert "Ejemplo explicativo con la serie seleccionada" in html
    assert "Vias urbanas" in html


if __name__ == "__main__":
    probar_exponencial_log_lineal_con_smearing()
    probar_mase_por_origen_sin_fuga_futura()
    probar_atipicos_z_robusto_y_mad_cero()
    probar_matriz_criterios_auditable()
    probar_durbin_watson_descriptivo_y_rangos()
    probar_intervalos_por_horizonte_y_metodos()
    probar_holt_condicional_y_arima_retirado()
    probar_csv_y_latex_con_trazabilidad_metodologica()
    probar_overleaf_usa_serie_real_y_diagramas_divididos()
    probar_html_exportable_dinamico()
    print("OK auditoria estadística app/docs")
