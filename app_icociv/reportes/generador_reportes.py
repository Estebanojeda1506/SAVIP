"""Cálculo y fragmentos de texto de los informes, más las entradas públicas.

Tras el rediseño de julio de 2026 este módulo dejó de componer documentos. Se
conserva como capa de datos:

* nombres de archivo y CSV reproducible;
* fragmentos de texto (``_lineas_*``) que alimentan el informe HTML;
* las funciones públicas ``generar_reporte_proyeccion``,
  ``generar_reporte_pdf`` y ``generar_informe_empalme``, que delegan en
  ``contenido`` + ``docx_render`` / ``pdf_render``.

La composición visual vive en esos módulos; aquí no se abre ningún documento.
"""

from __future__ import annotations

import math
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app_icociv.persistencia.gestor_sesiones import sanitizar_nombre_archivo
from app_icociv.utilidades.nomenclatura_icociv import (
    nombre_tabla_icociv,
    ruta_sin_tabla,
)


def esta_docx_disponible() -> bool:
    """Devuelve True si python-docx está instalado."""
    from app_icociv.reportes import docx_render

    return docx_render.esta_disponible()


def esta_pdf_disponible() -> bool:
    """Devuelve True si reportlab está instalado."""
    from app_icociv.reportes import pdf_render

    return pdf_render.esta_disponible()


def construir_ruta_jerarquica(
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
) -> list[tuple[str, str]]:
    """Normaliza la ruta jerárquica para tablas, sesiones e informes."""
    if ruta_jerarquica is None:
        return []
    if isinstance(ruta_jerarquica, dict):
        return [(str(k), str(v)) for k, v in ruta_jerarquica.items() if v not in (None, "")]

    ruta: list[tuple[str, str]] = []
    for item in ruta_jerarquica:
        nivel = item.get("nivel") or item.get("etiqueta") or item.get("campo") or ""
        valor = item.get("valor") or item.get("texto") or ""
        if valor:
            ruta.append((str(nivel), str(valor)))
    return ruta


def generar_nombre_reporte(
    usuario: str,
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
    periodo_proyectado: str,
    fecha: datetime | None = None,
) -> str:
    """Genera un nombre inteligente para el informe DOCX."""
    fecha = fecha or datetime.now()
    ruta = construir_ruta_jerarquica(ruta_sin_tabla(ruta_jerarquica))
    primer_nivel = ruta[0][1] if ruta else "analisis"
    ultimo_nivel = ruta[-1][1] if ruta else "icociv"
    partes = [
        usuario,
        primer_nivel[:48],
        ultimo_nivel[:48],
        periodo_proyectado,
        fecha.strftime("%Y-%m-%d_%H%M"),
    ]
    return sanitizar_nombre_archivo("_".join(filter(None, partes))) + ".docx"


def generar_nombre_reporte_pdf() -> str:
    """Nombre por defecto solicitado para informe PDF."""
    return "informe_metodologico_estadistico_icociv.pdf"


def generar_nombre_reporte_docx() -> str:
    """Nombre por defecto solicitado para informe DOCX."""
    return "informe_metodologico_estadistico_icociv.docx"


def generar_nombre_reproducibilidad_csv() -> str:
    """Nombre por defecto para datos reproducibles de la proyección."""
    return "datos_reproducibilidad_icociv.csv"


def construir_dataframe_reproducibilidad(
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None = None,
) -> pd.DataFrame:
    """Construye una tabla exportable para replicar la gráfica en otras herramientas."""
    filas: list[dict[str, Any]] = []
    ruta_normalizada = construir_ruta_jerarquica(ruta_jerarquica or resultado_proyeccion.get("ruta_jerarquica"))
    ruta_texto = " > ".join(f"{nivel}: {valor}" for nivel, valor in ruta_normalizada)
    nombre_serie = resultado_proyeccion.get("nombre_serie") or resultado_proyeccion.get("serie_nombre") or ""
    fecha_analisis = resultado_proyeccion.get("fecha_analisis") or datetime.now().strftime("%Y-%m-%d %H:%M")
    y_fit = np.asarray(resultado_proyeccion.get("y_fit_obs", []), dtype=float)
    horizonte_info = _analisis_horizontes_completo(resultado_proyeccion)
    evaluaciones_lista = horizonte_info.get("tabla_horizontes", [])
    evaluaciones = {
        int(item.get("horizonte", 0) or 0): item
        for item in evaluaciones_lista
    }
    evaluacion_final = evaluaciones.get(int(resultado_proyeccion.get("horizonte_permitido") or 0), {})
    parametros_modelo = resultado_proyeccion.get("parametros_modelo") or (resultado_proyeccion.get("stats") or {}).get("parametros_modelo") or {}
    metodo_retransformacion = parametros_modelo.get("metodo_retransformacion", "")
    sigma2_log = parametros_modelo.get("sigma2_log", "")
    smearing_factor = parametros_modelo.get("smearing_factor", "")
    for idx, fila in serie_df.reset_index(drop=True).iterrows():
        filas.append(
            {
                "tipo_registro": "observado",
                "periodo": _periodo_iso(fila.get("Periodo")),
                "serie_seleccionada": nombre_serie,
                "ruta_jerarquica": ruta_texto,
                "fecha_analisis": fecha_analisis,
                "valor_observado": fila.get("Indice"),
                "valor_ajustado": float(y_fit[idx]) if idx < len(y_fit) else "",
                "valor_proyectado": "",
                "modelo_usado": resultado_proyeccion.get("model_name", ""),
                "modelo_ganador_por_horizonte": "",
                "modelo_final_aplicado": resultado_proyeccion.get("model_name", ""),
                "modelo_final_difiere_ganador": "",
                "metricas_reportadas": "",
                "estado_horizonte": "",
                "clasificacion_horizonte": "",
                "confianza_horizonte": "",
                "permitido_para_proyeccion_tecnica": "",
                "permitido_como_escenario": "",
                "no_recomendable": "",
                "razon_decision": "",
                "mensaje_no_recomendables": horizonte_info.get("mensaje_no_recomendables", ""),
                "horizontes_evaluados": ",".join(str(h) for h in horizonte_info.get("horizontes_evaluados", [])),
                "horizonte_maximo_recomendado": horizonte_info.get("horizonte_maximo_recomendado", ""),
                "horizonte_maximo_con_cautela": horizonte_info.get("horizonte_maximo_con_cautela", ""),
                "horizonte_maximo_escenario": horizonte_info.get("horizonte_maximo_escenario", ""),
                "primer_horizonte_no_viable": horizonte_info.get("primer_horizonte_no_viable", ""),
                "rmse_horizonte": "",
                "mae_horizonte": "",
                "mape_horizonte": "",
                "smape_horizonte": "",
                "mase_horizonte": "",
                "sesgo_horizonte": "",
                "estabilidad_error_horizonte": "",
                "iteraciones_backtesting_horizonte": "",
                "horizonte": 0,
                "factor_actualizacion": "",
                "variacion_acumulada": "",
                "ventanas_oos_horizonte": "",
                "paso_exacto_errores_oos": "",
                "advertencia_evidencia_oos": "",
                "metodo_retransformacion": metodo_retransformacion,
                "sigma2_log": sigma2_log,
                "smearing_factor": smearing_factor,
            }
        )

    proyecciones = resultado_proyeccion.get("proyecciones")
    if isinstance(proyecciones, pd.DataFrame):
        for idx, fila in proyecciones.reset_index(drop=True).iterrows():
            horizonte = int(idx + 1)
            evaluacion = evaluaciones.get(horizonte, evaluacion_final)
            filas.append(
                {
                    "tipo_registro": "proyectado",
                    "periodo": _periodo_iso(fila.get("periodo")),
                    "serie_seleccionada": nombre_serie,
                    "ruta_jerarquica": ruta_texto,
                    "fecha_analisis": fecha_analisis,
                    "valor_observado": "",
                    "valor_ajustado": "",
                    "valor_proyectado": fila.get("indice_proyectado"),
                    # P0-C RUTA C2: el intervalo se retira de las salidas. Ninguno de los trece metodos auditados resulto adoptable y REQ 20 prohibe la combinacion que se venia publicando. El calculo interno se conserva como diagnostico; lo que desaparece es su PUBLICACION. No se sustituye por ninguna otra banda.
                    "modelo_usado": fila.get("modelo", resultado_proyeccion.get("model_name", "")),
                    "modelo_ganador_por_horizonte": evaluacion.get("modelo_evaluado", evaluacion.get("modelo", "")),
                    "modelo_final_aplicado": evaluacion.get("modelo_final_aplicado", resultado_proyeccion.get("model_name", "")),
                    "modelo_final_difiere_ganador": evaluacion.get("modelo_final_difiere_ganador", ""),
                    "metricas_reportadas": evaluacion.get("metricas_reportadas", ""),
                    "estado_horizonte": evaluacion.get("estado", ""),
                    "clasificacion_horizonte": evaluacion.get("clasificacion", ""),
                    "confianza_horizonte": evaluacion.get("confianza", ""),
                    "permitido_para_proyeccion_tecnica": evaluacion.get("permitido_para_proyeccion_tecnica", ""),
                    "permitido_como_escenario": evaluacion.get("permitido_como_escenario", ""),
                    "no_recomendable": evaluacion.get("no_recomendable", ""),
                    "razon_decision": evaluacion.get("razon_decision", evaluacion.get("motivo", "")),
                    "mensaje_no_recomendables": horizonte_info.get("mensaje_no_recomendables", ""),
                    "horizontes_evaluados": ",".join(str(h) for h in horizonte_info.get("horizontes_evaluados", [])),
                    "horizonte_maximo_recomendado": horizonte_info.get("horizonte_maximo_recomendado", ""),
                    "horizonte_maximo_con_cautela": horizonte_info.get("horizonte_maximo_con_cautela", ""),
                    "horizonte_maximo_escenario": horizonte_info.get("horizonte_maximo_escenario", ""),
                    "primer_horizonte_no_viable": horizonte_info.get("primer_horizonte_no_viable", ""),
                    "rmse_horizonte": evaluacion.get("rmse", ""),
                    "mae_horizonte": evaluacion.get("mae", ""),
                    "mape_horizonte": evaluacion.get("mape", ""),
                    "smape_horizonte": evaluacion.get("smape", ""),
                    "mase_horizonte": evaluacion.get("mase", ""),
                    "sesgo_horizonte": evaluacion.get("sesgo", ""),
                    "estabilidad_error_horizonte": evaluacion.get("estabilidad_error", ""),
                    "iteraciones_backtesting_horizonte": evaluacion.get("W", ""),
                    "horizonte": horizonte,
                    "factor_actualizacion": fila.get("factor_actualizacion"),
                    "variacion_acumulada": fila.get("variacion_acumulada_pct"),
                    "ventanas_oos_horizonte": fila.get("ventanas_oos_horizonte"),
                    "paso_exacto_errores_oos": fila.get("paso_exacto_errores_oos"),
                    "advertencia_evidencia_oos": fila.get("advertencia_evidencia_oos"),
                    "metodo_retransformacion": metodo_retransformacion,
                    "sigma2_log": sigma2_log,
                    "smearing_factor": smearing_factor,
                }
            )
    for evaluacion in evaluaciones_lista:
        filas.append(
            {
                "tipo_registro": "decision_horizonte",
                "periodo": "",
                "serie_seleccionada": nombre_serie,
                "ruta_jerarquica": ruta_texto,
                "fecha_analisis": fecha_analisis,
                "valor_observado": "",
                "valor_ajustado": "",
                "valor_proyectado": "",
                "modelo_usado": evaluacion.get("modelo_final_aplicado", resultado_proyeccion.get("model_name", "")),
                "modelo_ganador_por_horizonte": evaluacion.get("modelo_evaluado", evaluacion.get("modelo", "")),
                "modelo_final_aplicado": evaluacion.get("modelo_final_aplicado", resultado_proyeccion.get("model_name", "")),
                "modelo_final_difiere_ganador": evaluacion.get("modelo_final_difiere_ganador", ""),
                "metricas_reportadas": evaluacion.get("metricas_reportadas", ""),
                "estado_horizonte": evaluacion.get("estado", ""),
                "clasificacion_horizonte": evaluacion.get("clasificacion", ""),
                "confianza_horizonte": evaluacion.get("confianza", ""),
                "permitido_para_proyeccion_tecnica": evaluacion.get("permitido_para_proyeccion_tecnica", ""),
                "permitido_como_escenario": evaluacion.get("permitido_como_escenario", ""),
                "no_recomendable": evaluacion.get("no_recomendable", ""),
                "razon_decision": evaluacion.get("razon_decision", evaluacion.get("motivo", "")),
                "mensaje_no_recomendables": horizonte_info.get("mensaje_no_recomendables", ""),
                "horizontes_evaluados": ",".join(str(h) for h in horizonte_info.get("horizontes_evaluados", [])),
                "horizonte_maximo_recomendado": horizonte_info.get("horizonte_maximo_recomendado", ""),
                "horizonte_maximo_con_cautela": horizonte_info.get("horizonte_maximo_con_cautela", ""),
                "horizonte_maximo_escenario": horizonte_info.get("horizonte_maximo_escenario", ""),
                "primer_horizonte_no_viable": horizonte_info.get("primer_horizonte_no_viable", ""),
                "rmse_horizonte": evaluacion.get("rmse", ""),
                "mae_horizonte": evaluacion.get("mae", ""),
                "mape_horizonte": evaluacion.get("mape", ""),
                "smape_horizonte": evaluacion.get("smape", ""),
                "mase_horizonte": evaluacion.get("mase", ""),
                "sesgo_horizonte": evaluacion.get("sesgo", ""),
                "estabilidad_error_horizonte": evaluacion.get("estabilidad_error", ""),
                "iteraciones_backtesting_horizonte": evaluacion.get("W", ""),
                "horizonte": evaluacion.get("horizonte", ""),
                "factor_actualizacion": "",
                "variacion_acumulada": "",
                "ventanas_oos_horizonte": "",
                "paso_exacto_errores_oos": "",
                "advertencia_evidencia_oos": "",
                "metodo_retransformacion": metodo_retransformacion,
                "sigma2_log": sigma2_log,
                "smearing_factor": smearing_factor,
            }
        )
    salida = pd.DataFrame(filas)
    solicitado = _resultado_horizonte_solicitado(resultado_proyeccion)
    fecha_final_serie, fecha_inicial_proy, fecha_final_proy = _ventana_proyeccion(serie_df, resultado_proyeccion)
    salida["fecha_final_serie"] = fecha_final_serie
    salida["fecha_inicial_proyeccion"] = fecha_inicial_proy
    salida["fecha_final_proyeccion"] = fecha_final_proy
    salida["serie_final"] = nombre_serie or (ruta_normalizada[-1][1] if ruta_normalizada else "")
    salida["item_usuario"] = resultado_proyeccion.get("item_usuario", "") or (nombre_serie or "")
    salida["horizonte_solicitado"] = solicitado.get("horizonte_solicitado", "")
    salida["origen_horizonte"] = solicitado.get("origen_horizonte", "")
    salida["estado_horizonte_solicitado"] = solicitado.get("estado", "")
    salida["accion_global"] = solicitado.get("accion", "")
    salida["proyeccion_solicitada_generada"] = solicitado.get("proyeccion_generada", False)
    salida["razon_parada_horizontes"] = horizonte_info.get("razon_parada", "")
    salida["horizonte_maximo_evaluado"] = horizonte_info.get("horizonte_maximo_evaluado", "")
    salida["horizonte_maximo_permitido_como_escenario"] = horizonte_info.get(
        "horizonte_maximo_permitido_como_escenario", ""
    )
    salida["horizonte_maximo_admisible"] = horizonte_info.get("horizonte_maximo_admisible", "")
    salida["base_horizonte_maximo_recomendado"] = horizonte_info.get(
        "base_horizonte_maximo_recomendado", ""
    )
    salida["base_horizonte_maximo_escenario"] = horizonte_info.get(
        "base_horizonte_maximo_escenario", ""
    )
    salida["advertencia_metodologica_horizontes"] = horizonte_info.get(
        "advertencia_metodologica_horizontes", ""
    )
    salida["horizonte_maximo_evaluable_por_datos"] = horizonte_info.get("horizonte_maximo_evaluable_por_datos", "")
    salida["limite_operativo_auditoria"] = horizonte_info.get("horizonte_maximo_busqueda_configurado", "")
    salida["horizonte_solicitado_cubierto"] = horizonte_info.get("horizonte_solicitado_cubierto", False)
    salida["firma_serie_sha256"] = (horizonte_info.get("trazabilidad") or {}).get("firma_serie_sha256", "")
    salida["version_criterios"] = (horizonte_info.get("trazabilidad") or {}).get("version_criterios", "")
    # P0-G, 14-08-2026: los cuatro campos metodologicos viajaban en el resultado y
    # NO llegaban al CSV reproducible, de modo que un archivo pensado para auditar
    # omitia precisamente los bloqueos vigentes. No se introduce ninguna decision:
    # se serializa lo que el resultado ya declaro. Los bloqueos se ordenan
    # alfabeticamente y se unen con "|" para que el CSV sea reproducible byte a
    # byte entre ejecuciones (REQ 24).
    bloqueos = resultado_proyeccion.get("bloqueos_metodologicos") or {}
    salida["estado_metodologico"] = resultado_proyeccion.get("estado_metodologico", "")
    salida["bloqueos_metodologicos"] = "|".join(sorted(str(c) for c in bloqueos))
    salida["intervalo_sustentado"] = resultado_proyeccion.get("intervalo_sustentado", "")
    salida["motivo_intervalo_no_sustentado"] = resultado_proyeccion.get(
        "motivo_intervalo_no_sustentado", ""
    )
    salida["evidencia_oos_provisional"] = resultado_proyeccion.get(
        "evidencia_oos_provisional", ""
    )

    calendario = resultado_proyeccion.get("ajuste_calendario") or {}
    validacion_calendario = calendario.get("validacion_backtesting") or {}
    salida["ajuste_cambio_anio_aplicado"] = calendario.get("ajuste_calendario_aplicado", "")
    salida["evidencia_salto_anual"] = calendario.get("hay_evidencia_calendario", "")
    # El patron es propiedad de la serie; el efecto depende del horizonte pedido.
    salida["patron_cambio_anio_detectado_en_serie"] = calendario.get("patron_detectado_en_serie", "")
    salida["efecto_cambio_anio_en_horizonte_solicitado"] = calendario.get(
        "efecto_en_horizonte_solicitado", ""
    )
    salida["estado_cambio_anio"] = calendario.get("estado_calendario_visible", "")
    salida["transiciones_diciembre_enero"] = calendario.get("transiciones_diciembre_enero", "")
    salida["salto_cambio_anio_pct"] = calendario.get("salto_mediano_pct", "")
    salida["ratio_salto_movimiento"] = calendario.get("ratio_salto_movimiento", "")
    salida["eneros_en_horizonte"] = calendario.get("eneros_en_horizonte", "")
    salida["mejora_mae_ajuste_calendario"] = validacion_calendario.get("mejora_mae", "")
    salida["mejora_rmse_ajuste_calendario"] = validacion_calendario.get("mejora_rmse", "")
    clasificacion_intervalo = resultado_proyeccion.get("clasificacion_intervalo") or {}
    # RA-01: el CSV reproducible expone el paso exacto y el tamano de su
    # evidencia. Ambas describen la trayectoria, no la banda, y se conservan.
    paso = resultado_proyeccion.get("verificabilidad_paso_exacto") or {}
    salida["paso_exacto_solicitado"] = paso.get("paso_exacto", "")
    salida["errores_oos_paso_exacto"] = paso.get("n_errores_oos", "")
    # HGRID y P0-H, 17-08-2026 (V-CODEX-R3). El CSV debe decir lo mismo que la
    # interfaz y la tesis (REQ 25): cuantas ventanas existen para el horizonte
    # pedido, en que tramo cae ese numero, con que formula se cuenta y que el
    # primer origen sigue siendo provisional.
    traza_horizontes = (resultado_proyeccion.get("horizonte_info") or {}).get("trazabilidad") or {}
    for clave in (
        "ventanas_oos_horizonte_solicitado",
        "tramo_evidencia_oos_horizonte_solicitado",
        "evidencia_oos_horizonte_solicitado",
        "horizonte_maximo_evidencia_oos_no_limitada",
        "formula_ventanas_oos",
        "primer_origen_provisional",
        "entrenamiento_inicial",
    ):
        salida[clave] = traza_horizontes.get(clave, "")
    # P0-C / ESTRATEGIA C2, 15-08-2026. Se retiran del CSV las columnas que
    # caracterizaban la banda o su cobertura: la clasificacion del intervalo del
    # 95 % y sus tres columnas asociadas, el metodo con que se evaluo la
    # cobertura, el recuento x/y por horizonte, el nivel nominal, el tipo de
    # banda, la limitacion de cobertura, la consecuencia operativa y la
    # verificabilidad del paso. Todas describen un intervalo que ya no se
    # entrega. El calculo permanece; lo que se retira es la publicacion.
    #
    # `verificabilidad_paso_exacto` tambien se retira: dice si la COBERTURA de
    # ese paso podia verificarse, y publicar «No verificable» invita a leer una
    # banda que no esta. El hecho sustantivo -cuantos errores fuera de muestra
    # reune el horizonte- sigue en `errores_oos_paso_exacto`.
    salida["intervalo_publicado"] = "No"
    # P0-C / ESTRATEGIA C2, 15-08-2026. Las columnas de COBERTURA de la banda se
    # vacian. Median el desempeno de un intervalo que esta version ya no publica:
    # cobertura del paso exacto, minimo global, dónde cae ese minimo y con
    # cuantos contrastes, la advertencia de consistencia entre horizontes, el
    # recuento x/y, la distancia al nivel nominal, la lectura descriptiva con las
    # seis magnitudes y el papel del valor 0,90.
    #
    # Sin banda publicada, esas cifras no son un resultado: son diagnostico del
    # metodo retirado, y siguen calculandose. NO se afirma que la cobertura sea
    # invalida; se deja de publicarla.
    #
    # Aqui las columnas se RETIRAN, no se vacian. En el objeto publico se
    # conservan porque hay consumidores que comprueban la forma del contrato;
    # de estas no depende ninguno, y una columna siempre vacia que se llama
    # `cobertura_observada_publicada` promete un dato que no esta y sigue
    # nombrando la cobertura en la cabecera del CSV.
    salida["limitacion_muestra"] = clasificacion_intervalo.get("limitacion_muestra", "")
    salida["intervalo_publicado"] = "No"
    return salida


def _texto_o_vacio(valor: Any) -> Any:
    """Deja el valor tal cual y convierte la ausencia en celda vacia.

    Un 0 es un dato: no puede colapsarse a cadena vacia, que es lo que haria
    un ``or ""``.
    """
    return "" if valor is None else valor


def generar_csv_reproducibilidad(
    ruta_salida: str | Path,
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None = None,
) -> Path:
    """Exporta observado, ajustado, proyección e intervalos a CSV."""
    ruta = Path(ruta_salida)
    if ruta.suffix.lower() != ".csv":
        ruta = ruta.with_suffix(".csv")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    construir_dataframe_reproducibilidad(serie_df, resultado_proyeccion, ruta_jerarquica).to_csv(
        ruta,
        index=False,
        encoding="utf-8-sig",
    )
    return ruta


def _formatear_numero(valor: Any, decimales: int = 4) -> str:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "" if valor is None else str(valor)
    if math.isfinite(numero):
        return f"{numero:.{decimales}f}"
    return "No aplica"


def _periodo_iso(periodo: Any) -> str:
    texto = str(periodo).strip().replace("/", "_").replace("-", "_")
    partes = texto.split("_")
    if len(partes) >= 2:
        try:
            return f"{int(partes[0]):04d}-{int(partes[1]):02d}"
        except ValueError:
            return str(periodo).strip()
    return str(periodo).strip()


def _filas_ajuste_calendario(resultado: dict) -> list[tuple[str, Any]]:
    """Trazabilidad del ajuste de cambio de año (diciembre-enero)."""
    traza = resultado.get("ajuste_calendario") or {}
    if not traza:
        return []
    validacion = traza.get("validacion_backtesting") or {}
    filas: list[tuple[str, Any]] = [
        ("Estado del patrón de cambio de año", traza.get("estado_calendario_visible") or "No evaluado"),
        ("Patrón detectado en la serie", "Si" if traza.get("patron_detectado_en_serie") else "No"),
        ("Efecto dentro del horizonte solicitado",
         "Si" if traza.get("efecto_en_horizonte_solicitado") else "No"),
        ("Ajuste de cambio de año aplicado", "Si" if traza.get("ajuste_calendario_aplicado") else "No"),
        ("Evidencia de salto anual", "Si" if traza.get("hay_evidencia_calendario") else "No"),
        ("Transiciones diciembre-enero observadas", traza.get("transiciones_diciembre_enero")),
        ("Salto mediano de cambio de año (%)", _redondear_trazable(traza.get("salto_mediano_pct"))),
        ("Movimiento mensual tipico (%)", _redondear_trazable(traza.get("movimiento_mensual_tipico_pct"))),
        ("Razón salto/movimiento", _redondear_trazable(traza.get("ratio_salto_movimiento"))),
        ("Consistencia de signo", _redondear_trazable(traza.get("consistencia_signo"))),
        ("Eneros dentro del horizonte", traza.get("eneros_en_horizonte")),
        ("Criterio de detección", traza.get("criterio") or "No aplica"),
    ]
    if validacion.get("evaluado"):
        filas.extend(
            [
                ("Ventanas de validación del ajuste", validacion.get("ventanas")),
                ("Mejora en MAE por el ajuste (%)", _redondear_trazable(validacion.get("mejora_mae"))),
                ("Mejora en RMSE por el ajuste (%)", _redondear_trazable(validacion.get("mejora_rmse"))),
            ]
        )
    filas.append(("Nota sobre cambio de año", traza.get("mensaje")))
    return filas


def _redondear_trazable(valor: Any) -> Any:
    """Redondea a cuatro decimales cuando el valor es numérico."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "No aplica" if valor is None else valor
    return round(numero, 4) if math.isfinite(numero) else "No aplica"


def _formatear_valor_corto(valor: Any) -> str:
    if isinstance(valor, (int, float)):
        return _formatear_numero(valor)
    if valor is None:
        return ""
    return str(valor)


def _ventana_proyeccion(serie_df: pd.DataFrame, resultado: dict[str, Any]) -> tuple[str, str, str]:
    """(fecha final de serie, primer periodo proyectado, último periodo proyectado) en ISO."""
    fecha_final_serie = ""
    if isinstance(serie_df, pd.DataFrame) and not serie_df.empty and "Periodo" in serie_df.columns:
        fecha_final_serie = _periodo_iso(serie_df["Periodo"].iloc[-1])
    proy = resultado.get("proyecciones")
    if isinstance(proy, pd.DataFrame) and not proy.empty and "periodo" in proy.columns:
        periodos = [str(p) for p in proy["periodo"].tolist() if str(p).strip()]
        if periodos:
            return fecha_final_serie, _periodo_iso(periodos[0]), _periodo_iso(periodos[-1])
    if isinstance(proy, list) and proy:
        periodos = [str(f.get("periodo", "")) for f in proy if isinstance(f, dict) and f.get("periodo")]
        if periodos:
            return fecha_final_serie, _periodo_iso(periodos[0]), _periodo_iso(periodos[-1])
    solicitado = _resultado_horizonte_solicitado(resultado)
    horizonte = solicitado.get("horizonte_solicitado") or resultado.get("horizonte_solicitado")
    if fecha_final_serie and horizonte:
        try:
            anio, mes = (int(x) for x in fecha_final_serie.split("-"))
            base = anio * 12 + (mes - 1)
            ini = base + 1
            fin = base + int(horizonte)
            return fecha_final_serie, f"{ini // 12:04d}-{ini % 12 + 1:02d}", f"{fin // 12:04d}-{fin % 12 + 1:02d}"
        except (TypeError, ValueError):
            pass
    return fecha_final_serie, "", ""


def _resultado_horizonte_solicitado(resultado: dict[str, Any]) -> dict[str, Any]:
    bloque = resultado.get("resultado_horizonte_solicitado")
    if isinstance(bloque, dict) and bloque:
        return bloque
    generado = bool(resultado.get("proyeccion_generada", True))
    return {
        "horizonte_solicitado": resultado.get("horizonte_solicitado"),
        "origen_horizonte": resultado.get("origen_horizonte", "predeterminado"),
        "estado": "proyeccion_tecnica" if generado else "no_admisible",
        "accion": "permitir" if generado else "negar",
        "proyeccion_generada": generado,
        "indice_proyectado": resultado.get("y_proj") if generado else None,
        "periodo_proyectado": resultado.get("periodo_proj") if generado else None,
        "modelo_aplicado": resultado.get("model_name") if generado else None,
        "ic95": [resultado.get("ci95_lo", resultado.get("ci_lo")), resultado.get("ci95_hi", resultado.get("ci_hi"))] if generado else None,
        "nivel_confianza": (resultado.get("factibilidad") or {}).get("nivel_confianza_metodologica"),
        "razon_principal": resultado.get("explicacion"),
    }


def _analisis_horizontes_completo(resultado: dict[str, Any]) -> dict[str, Any]:
    info = resultado.get("analisis_horizontes_completo") or resultado.get("horizonte_info") or {}
    if "tabla_horizontes" not in info:
        info = {**info, "tabla_horizontes": info.get("evaluaciones") or []}
    return info


def _estado_horizonte_visible(estado: Any) -> str:
    # H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Se
    # retira la entrada "escenario": `_estructurar_resultado_horizontes` ya no
    # produce ese estado (ver su comentario H-4 residual); mantenerla aqui
    # presentaba un estado inalcanzable como si fuera una salida posible.
    return {
        "proyeccion_tecnica": "Proyección técnica",
        "no_admisible": "No admisible",
    }.get(str(estado), str(estado or "No disponible"))


def _intervalo_bloque(valores: Any) -> str:
    return _intervalo_docx(*valores) if isinstance(valores, (list, tuple)) and len(valores) == 2 else "No aplica"


def _filas_resumen_ejecutivo(resultado: dict[str, Any]) -> list[tuple[str, Any]]:
    solicitado = _resultado_horizonte_solicitado(resultado)
    generado = bool(solicitado.get("proyeccion_generada"))
    return [
        ("Horizonte solicitado", f"{solicitado.get('horizonte_solicitado', '')} meses"),
        ("Origen del horizonte", str(solicitado.get("origen_horizonte") or "No disponible").capitalize()),
        ("Estado del horizonte solicitado", _estado_horizonte_visible(solicitado.get("estado"))),
        ("Acción del sistema", str(solicitado.get("accion") or "No disponible").capitalize()),
        ("Proyección generada", "Sí" if generado else "No"),
        ("Índice proyectado", solicitado.get("indice_proyectado") if generado else "No generado"),
        ("Periodo proyectado", solicitado.get("periodo_proyectado") if generado else "No aplica"),
        ("Modelo aplicado", solicitado.get("modelo_aplicado") if generado else "No aplica"),
        # P0-C / C2: el resumen entregaba aqui la pareja [inferior, superior].
        ("Intervalo de predicción", "No se publica en esta versión"),
        ("Nivel de confianza", solicitado.get("nivel_confianza") or "No recomendable"),
        ("Razón principal", solicitado.get("razon_principal") or "No disponible"),
    ]


def _intervalo_docx(inferior: Any, superior: Any) -> str:
    if inferior in (None, "") and superior in (None, ""):
        return "No aplica"
    return f"[{_formatear_numero(inferior)}, {_formatear_numero(superior)}]"


def _advertencias_principales(resultado: dict[str, Any], max_items: int = 8) -> list[str]:
    categorias = resultado.get("advertencias_categorizadas") or {}
    factibilidad = resultado.get("factibilidad") or {}
    items: list[str] = []
    for clave in (
        "advertencias_factibilidad_global",
        "advertencias_datos",
        "advertencias_modelo_seleccionado",
        "advertencias_horizonte",
        "advertencias_intervalo",
    ):
        for item in categorias.get(clave, []) or []:
            texto = str(item).strip()
            if texto and texto not in items:
                items.append(texto)
    for item in factibilidad.get("advertencias", []) or []:
        texto = str(item).strip()
        if texto and texto not in items:
            items.append(texto)
    return items[:max_items]


def _lineas_resumen_ejecutivo(resultado: dict[str, Any]) -> list[str]:
    """Resumen ejecutivo reutilizable para PDF y HTML."""
    lineas = [f"{campo}: {_formatear_valor_corto(valor)}" for campo, valor in _filas_resumen_ejecutivo(resultado)]
    advertencias = _advertencias_principales(resultado, max_items=5)
    if advertencias:
        lineas.append("Advertencias principales:")
        lineas.extend(f"- {item}" for item in advertencias)
    else:
        lineas.append("Advertencias principales: no se registran advertencias principales para el resultado mostrado.")
    return lineas


def _datos_informe(
    usuario: str,
    archivo_excel: str,
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    year_month: list[str],
    nombre_sesion: str | None,
) -> Any:
    from app_icociv.reportes.contenido import DatosProyeccion

    return DatosProyeccion(
        resultado=resultado_proyeccion,
        serie_df=serie_df,
        fuente_label=fuente_label,
        archivo_excel=archivo_excel,
        ruta_jerarquica=ruta_jerarquica,
        fila=fila,
        year_month=list(year_month or []),
        usuario=usuario,
        nombre_sesion=nombre_sesion,
    )


def generar_reporte_proyeccion(
    ruta_salida: str | Path,
    usuario: str,
    archivo_excel: str,
    seleccion: dict[str, Any],
    parametros_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    year_month: list[str],
    nombre_sesion: str | None = None,
    configuracion: Any = None,
) -> Path:
    """Genera y guarda el informe DOCX según la configuración de contenido.

    Sin ``configuracion`` se emite el informe técnico completo, que es el
    comportamiento histórico de esta función.
    """
    from app_icociv.reportes import docx_render
    from app_icociv.reportes.contenido import construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme

    configuracion = configuracion or ConfiguracionInforme.desde_tipo("tecnico")
    datos = _datos_informe(
        usuario, archivo_excel, ruta_jerarquica, fuente_label,
        fila, serie_df, resultado_proyeccion, year_month, nombre_sesion,
    )
    informe = construir_informe_proyeccion(datos, configuracion)
    return docx_render.guardar(informe, ruta_salida)


def generar_reporte_pdf(
    ruta_salida: str | Path,
    usuario: str,
    archivo_excel: str,
    seleccion: dict[str, Any],
    parametros_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    year_month: list[str],
    nombre_sesion: str | None = None,
    configuracion: Any = None,
) -> Path:
    """Genera el informe PDF paginado, con índice navegable y marcadores."""
    from app_icociv.reportes import pdf_render
    from app_icociv.reportes.contenido import construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme

    configuracion = configuracion or ConfiguracionInforme.desde_tipo("tecnico")
    datos = _datos_informe(
        usuario, archivo_excel, ruta_jerarquica, fuente_label,
        fila, serie_df, resultado_proyeccion, year_month, nombre_sesion,
    )
    informe = construir_informe_proyeccion(datos, configuracion)
    return pdf_render.guardar(informe, ruta_salida)


def generar_informe_empalme(
    ruta_salida: str | Path,
    calculos: list[dict[str, Any]],
    generales: dict[str, str] | None = None,
    configuracion: Any = None,
    formato: str = "docx",
) -> Path:
    """Genera el informe de ajuste ICCP-ICOCIV en DOCX o PDF."""
    from app_icociv.reportes import docx_render, pdf_render
    from app_icociv.reportes.contenido_empalme import construir_informe_empalme
    from app_icociv.reportes.modelo import ConfiguracionInforme

    configuracion = configuracion or ConfiguracionInforme.desde_tipo("empalme")
    informe = construir_informe_empalme(calculos, generales, configuracion)
    if str(formato).lower() == "pdf":
        return pdf_render.guardar(informe, ruta_salida)
    return docx_render.guardar(informe, ruta_salida)


def generar_reporte_html(
    ruta_salida: str | Path,
    usuario: str,
    archivo_excel: str,
    seleccion: dict[str, Any],
    parametros_proyeccion: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    resultado_proyeccion: dict[str, Any],
    year_month: list[str],
    nombre_sesion: str | None = None,
) -> Path:
    """Genera un informe HTML liviano con la misma trazabilidad del PDF/DOCX."""
    ruta = Path(ruta_salida)
    if ruta.suffix.lower() not in {".html", ".htm"}:
        ruta = ruta.with_suffix(".html")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    fecha = datetime.now()
    fuente_visible = nombre_tabla_icociv(fuente_label)
    factibilidad = resultado_proyeccion.get("factibilidad", {})
    filas_resumen = "".join(
        f"<tr><th>{html_escape(str(campo).rstrip(':') + ':')}</th><td>{html_escape(_formatear_valor_corto(valor))}</td></tr>"
        for campo, valor in _filas_resumen_ejecutivo(resultado_proyeccion)
    )
    resumen_html = (
        "<div class='resumen-grid'>"
        "<section class='card principal'><h2>Resumen ejecutivo</h2>"
        f"<table>{filas_resumen}</table>"
        "</section>"
        "<section class='card'><h2>Lectura inmediata</h2>"
        + "".join(f"<p>{html_escape(linea)}</p>" for linea in _lineas_resumen_ejecutivo(resultado_proyeccion)[-6:])
        + "</section></div>"
    )
    secciones = [
        ("Contexto metodológico del ICOCIV", [
            "El ICOCIV es una operación estadística del DANE. La app no modifica la metodología oficial; analiza la serie oficial seleccionada por el usuario.",
            f"Tabla de índices ICOCIV: {fuente_visible}.",
        ]),
        ("Ruta jerárquica seleccionada", [f"{nivel}: {valor}" for nivel, valor in construir_ruta_jerarquica(ruta_jerarquica)]),
        ("Ejemplo explicativo con la serie seleccionada", _lineas_ejemplo_dinamico(serie_df, resultado_proyeccion, ruta_jerarquica)),
        ("Validación de datos", _lineas_validacion(resultado_proyeccion.get("validacion_serie", {}))),
        ("Factibilidad de proyección", _lineas_factibilidad(factibilidad, resultado_proyeccion)),
        ("Resumen del análisis dinámico de horizontes", _lineas_determinacion_horizonte(resultado_proyeccion)),
        ("Modelos evaluados y selección", _lineas_modelos(resultado_proyeccion)),
        ("Evaluación completa por horizonte", _lineas_horizontes(resultado_proyeccion)),
        ("Proyección del índice", _lineas_proyeccion(resultado_proyeccion)),
        ("Uso de la proyección en obras civiles", _lineas_uso_obras_civiles()),
    ]

    filas_serie = []
    if {"Periodo", "Indice"}.issubset(serie_df.columns):
        muestra = pd.concat([serie_df.head(6), serie_df.tail(6)]).drop_duplicates().reset_index(drop=True)
        for _, item in muestra.iterrows():
            filas_serie.append(
                f"<tr><td>{html_escape(_periodo_iso(item.get('Periodo')))}</td><td>{html_escape(_formatear_numero(item.get('Indice')))}</td></tr>"
            )
    tabla_serie = (
        "<table><thead><tr><th>Periodo</th><th>Indice</th></tr></thead><tbody>"
        + "".join(filas_serie)
        + "</tbody></table>"
    )

    cuerpo = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<title>Informe metodológico y estadístico ICOCIV</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;line-height:1.45;color:#1f2937}"
        "h1,h2{color:#17324d}table{border-collapse:collapse;width:100%;margin:12px 0;table-layout:auto}"
        "th,td{border:1px solid #d0d5dd;padding:6px;text-align:left}th{background:#eef4ff}"
        "td{word-break:break-word}.meta{background:#f8fafc;border:1px solid #d0d5dd;padding:12px;margin-bottom:18px}"
        ".resumen-grid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:14px;margin:16px 0}"
        ".card{background:#fff;border:1px solid #d0d5dd;border-radius:8px;padding:14px;box-shadow:0 1px 2px rgba(16,24,40,.05)}"
        ".card.principal{border-left:5px solid #2457a6}"
        "@media(max-width:760px){.resumen-grid{grid-template-columns:1fr}}</style>",
        "</head><body>",
        "<h1>Informe metodológico y estadístico ICOCIV</h1>",
        "<div class='meta'>",
        f"<p><strong>Usuario:</strong> {html_escape(str(usuario))}</p>",
        f"<p><strong>Fecha:</strong> {fecha:%Y-%m-%d %H:%M}</p>",
        f"<p><strong>Archivo fuente:</strong> {html_escape(Path(archivo_excel).name if archivo_excel else '')}</p>",
        f"<p><strong>Sesión:</strong> {html_escape(nombre_sesion or 'No aplica')}</p>",
        "</div>",
        resumen_html,
        "<h2>Serie observada utilizada</h2>",
        tabla_serie,
    ]
    for titulo, lineas in secciones:
        cuerpo.append(f"<h2>{html_escape(titulo)}</h2>")
        for linea in lineas:
            cuerpo.append(f"<p>{html_escape(str(linea))}</p>")
    cuerpo.append("</body></html>")
    ruta.write_text("\n".join(cuerpo), encoding="utf-8")
    return ruta


def _lineas_ejemplo_dinamico(
    serie_df: pd.DataFrame,
    resultado: dict[str, Any],
    ruta_jerarquica: list[dict[str, str]] | dict[str, str] | None,
) -> list[str]:
    """Construye un ejemplo pedagogico con la serie efectivamente seleccionada."""
    if serie_df.empty or not {"Periodo", "Indice"}.issubset(serie_df.columns):
        return ["No hay información suficiente para construir un ejemplo aplicado con la serie seleccionada."]

    serie = serie_df[["Periodo", "Indice"]].copy()
    serie["Indice"] = pd.to_numeric(serie["Indice"], errors="coerce")
    serie = serie.dropna(subset=["Indice"]).reset_index(drop=True)
    if len(serie) < 2:
        return ["La serie seleccionada tiene menos de dos observaciones válidas; no es posible ilustrar variaciones ni modelos de referencia."]

    ruta = construir_ruta_jerarquica(ruta_jerarquica)
    primer_periodo = _periodo_iso(serie.loc[0, "Periodo"])
    ultimo_periodo = _periodo_iso(serie.loc[len(serie) - 1, "Periodo"])
    y1 = float(serie.loc[0, "Indice"])
    y_t = float(serie.loc[len(serie) - 1, "Indice"])
    observaciones = len(serie)
    variacion_total = ((y_t / y1) - 1.0) * 100.0 if y1 else math.nan
    cambio_promedio = (y_t - y1) / (observaciones - 1) if observaciones > 1 else math.nan
    variacion_mensual_1 = ((float(serie.loc[1, "Indice"]) / y1) - 1.0) * 100.0 if y1 else math.nan
    naive_h1 = y_t
    drift_h1 = y_t + cambio_promedio if math.isfinite(cambio_promedio) else math.nan

    horizonte_info = resultado.get("horizonte_info") or {}
    horizonte_solicitado = resultado.get("horizonte_solicitado", horizonte_info.get("horizonte_solicitado", ""))
    horizonte_permitido = resultado.get("horizonte_permitido", horizonte_info.get("horizonte_permitido", ""))
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12). No existe ya un
    # "maximo recomendado": el alcance operativo es fijo (H_OPERATIVO_MAX=24)
    # y el modelo se selecciona una sola vez por RMSE OOS sobre 1..24.
    alcance_maximo = horizonte_info.get("alcance_maximo_proyeccion", "")
    rmse_seleccion = horizonte_info.get("rmse_seleccion_oos", "")
    no_recomendables = horizonte_info.get("horizontes_no_recomendables") or []
    evaluaciones = horizonte_info.get("evaluaciones") or []
    try:
        horizonte_objetivo = int(horizonte_permitido or horizonte_solicitado or -1)
    except (TypeError, ValueError):
        horizonte_objetivo = -1
    evaluacion_objetivo = next(
        (item for item in evaluaciones if int(item.get("horizonte", -1) or -1) == horizonte_objetivo),
        {},
    )
    modelo = evaluacion_objetivo.get("modelo_final_aplicado") or resultado.get("model_name", "No seleccionado")
    estado = evaluacion_objetivo.get("estado") or (resultado.get("factibilidad") or {}).get("estado", "")
    motivo = evaluacion_objetivo.get("razon_decision") or evaluacion_objetivo.get("motivo") or resultado.get("explicacion", "")

    lineas = [
        "Este apartado convierte el análisis en un ejemplo reproducible con la serie seleccionada en esta ejecución. No modifica la metodología oficial del DANE; solo ilustra como se analizan los valores oficiales extraidos.",
    ]
    if ruta:
        lineas.append("Ruta jerárquica usada en el ejemplo:")
        lineas.extend([f"- {nivel}: {valor}" for nivel, valor in ruta])
    lineas.extend(
        [
            f"La serie inicia en {primer_periodo} con índice {_formatear_numero(y1)} y termina en {ultimo_periodo} con índice {_formatear_numero(y_t)}.",
            f"Número de observaciones mensuales usadas: {observaciones}.",
            f"La variación acumulada observada entre el primer y último periodo es {_formatear_numero(variacion_total, 2)}%.",
            f"Como ejemplo de variación mensual, entre {primer_periodo} y {_periodo_iso(serie.loc[1, 'Periodo'])} la variación fue {_formatear_numero(variacion_mensual_1, 2)}%.",
            f"Benchmark naive para h=1: pronostica {_formatear_numero(naive_h1)} porque conserva el último índice observado.",
            f"Benchmark drift para h=1: usa una pendiente histórica promedio de {_formatear_numero(cambio_promedio)} puntos de índice por mes y pronostica {_formatear_numero(drift_h1)}.",
            f"Horizonte solicitado: {horizonte_solicitado}. Horizonte finalmente permitido: {horizonte_permitido}. "
            f"Alcance máximo de proyección de SAVIP: {alcance_maximo} meses.",
            f"Modelo seleccionado: {modelo}. RMSE OOS usado en la selección (1–24 meses): {rmse_seleccion}. "
            f"Estado del horizonte: {estado}.",
        ]
    )
    if motivo:
        lineas.append(f"Razón técnica de la decisión: {motivo}")
    if no_recomendables:
        lineas.append(f"Horizontes evaluados como no recomendables: {no_recomendables}.")
    proyecciones = resultado.get("proyecciones")
    if isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty:
        ultima = proyecciones.tail(1).iloc[0]
        lineas.append(
            "Para el último periodo proyectado, el informe reporta índice puntual "
            f"{_formatear_numero(ultima.get('indice_proyectado'))}, factor de actualización "
            f"{_formatear_numero(ultima.get('factor_actualizacion'))} y variación acumulada "
            f"{_formatear_numero(ultima.get('variacion_acumulada_pct'), 2)}%."
        )
    else:
        lineas.append("No se genero proyección puntual; el ejemplo queda limitado a validación, benchmarks y diagnostico.")
    return lineas


def _lineas_validacion(validacion: dict[str, Any]) -> list[str]:
    lineas = [
        f"Observaciones: {validacion.get('observaciones', '')}",
        f"Continuidad temporal: {validacion.get('continuidad_temporal', '')}",
        f"Duplicados: {validacion.get('duplicados', '')}",
        f"Valores faltantes: {validacion.get('valores_faltantes', '')}",
        f"Valores no numéricos: {validacion.get('valores_no_numericos', '')}",
        f"Longitud mínima: {validacion.get('longitud_minima', '')}",
    ]
    for item in validacion.get("errores_criticos", []):
        lineas.append(f"Critico: {item}")
    for item in validacion.get("advertencias", []):
        lineas.append(f"Advertencia: {item}")
    return lineas


def _lineas_factibilidad(factibilidad: dict[str, Any], resultado: dict[str, Any]) -> list[str]:
    estado_datos = factibilidad.get("estado_datos") or {}
    estado_modelado = factibilidad.get("estado_modelado") or {}
    horizonte_info = resultado.get("horizonte_info") or {}
    lineas = [
        f"Estado general: {factibilidad.get('estado') or ('Proyectable' if factibilidad.get('factible') else 'No proyectable')}",
        f"Estado de datos: {estado_datos.get('estado', '')}",
        f"Estado de modelado: {estado_modelado.get('estado', '')}",
        f"Factible: {'Si' if factibilidad.get('factible') else 'No'}",
        f"Confianza metodológica: {factibilidad.get('nivel_confianza_metodologica', '')}",
        f"Horizonte solicitado: {resultado.get('horizonte_solicitado', '')}",
        f"Horizonte permitido: {resultado.get('horizonte_permitido', '')}",
        # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12). Metodologia
        # N0=12/H=24: no hay clasificacion por horizonte; el alcance operativo
        # es fijo y el modelo se selecciona una sola vez sobre 1..24.
        f"Alcance máximo de proyección de SAVIP: {horizonte_info.get('alcance_maximo_proyeccion') or 'No identificado'} meses",
        f"Primer origen del backtesting (N0): {horizonte_info.get('n0_backtesting') or 'No identificado'}",
        f"Modelo seleccionado: {horizonte_info.get('modelo_seleccionado') or 'No identificado'}",
        f"RMSE OOS usado en la selección (1–24 meses): {horizonte_info.get('rmse_seleccion_oos') or 'No identificado'}",
        f"Segundo modelo: {horizonte_info.get('modelo_segundo') or 'No aplica'}",
        f"Explicación: {factibilidad.get('explicacion', resultado.get('explicacion', ''))}",
    ] + [f"{etiqueta}: {valor}" for etiqueta, valor in _filas_ajuste_calendario(resultado)]
    proyeccion_generada = bool(resultado.get("proyeccion_generada"))
    def _visible_global(texto: Any) -> bool:
        limpio = str(texto)
        if proyeccion_generada and "no se permite proyección" in limpio.lower() and not limpio.lower().startswith("horizonte h="):
            return False
        return True

    lineas.extend([f"Razón: {r}" for r in factibilidad.get("razones_tecnicas", []) if _visible_global(r)])
    lineas.extend([f"Advertencia: {a}" for a in factibilidad.get("advertencias", []) if _visible_global(a)])
    categorias = resultado.get("advertencias_categorizadas") or {}
    etiquetas = {
        "advertencias_datos": "datos",
        "advertencias_modelo_seleccionado": "modelo seleccionado",
        "advertencias_modelos_descartados": "modelos descartados",
        "advertencias_horizonte": "horizonte",
        "advertencias_intervalo": "intervalo",
        "advertencias_factibilidad_global": "factibilidad global",
    }
    for categoria in etiquetas:
        items = categorias.get(categoria, [])
        for item in items:
            if _visible_global(item) or categoria == "advertencias_horizonte":
                lineas.append(f"Advertencia {etiquetas[categoria]}: {item}")
    return lineas


def _lineas_modelos(resultado: dict[str, Any]) -> list[str]:
    lineas = [f"Modelo seleccionado: {resultado.get('model_name', 'No seleccionado')}"]
    lineas.append(str(resultado.get("justificacion_modelo", "")))
    politica = resultado.get("politica_modelos") or (resultado.get("stats") or {}).get("politica_modelos") or {}
    for razon in politica.get("razones", []):
        lineas.append(f"Politica progresiva: {razon}")
    for item in (resultado.get("descartes_modelos") or (resultado.get("stats") or {}).get("descartes_modelos") or [])[:8]:
        razones = item.get("razones") or [item.get("razon", "")]
        lineas.append(f"Modelo descartado {item.get('nombre', '')}: {'; '.join(str(r) for r in razones if r)}")
    ranking = (resultado.get("stats") or {}).get("ranking_backtesting") or {}
    if ranking:
        for etiqueta, campo in (
            ("Mejor modelo por RMSE", "mejor_rmse"),
            ("Mejor modelo por MAE", "mejor_mae"),
            ("Mejor modelo por MAPE", "mejor_mape"),
        ):
            item = ranking.get(campo) or {}
            if item:
                lineas.append(f"{etiqueta}: {item.get('modelo')} ({_formatear_numero(item.get('valor'))}).")
    candidatos = (resultado.get("stats") or {}).get("all_candidates") or []
    for candidato in candidatos[:12]:
        lineas.append(
            f"{candidato.get('name')}: AICc={_formatear_numero(candidato.get('aicc'))}, "
            f"MAPE BT={_formatear_numero(candidato.get('mape_backtesting'))}, "
            f"RMSE BT={_formatear_numero(candidato.get('rmse_backtesting'))}, "
            f"MASE={_formatear_numero(candidato.get('mase_backtesting'))}, "
            f"rRMSE naive={_formatear_numero(candidato.get('rrmse_naive'))}, "
            f"rRMSE drift={_formatear_numero(candidato.get('rrmse_drift'))}."
        )
    return lineas


def _lineas_horizontes(resultado: dict[str, Any]) -> list[str]:
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12 - sincronizar reportes).
    # Bajo N0=12/H=24 rectangular no hay clasificacion por horizonte
    # (permitido/tecnico/escenario/no_recomendable); la tabla es evidencia
    # descriptiva del modelo YA seleccionado por RMSE OOS agregado 1..24.
    info = _analisis_horizontes_completo(resultado)
    lineas = [
        f"Horizonte solicitado: {info.get('horizonte_solicitado', resultado.get('horizonte_solicitado', ''))}",
        f"Alcance máximo de proyección de SAVIP: {info.get('alcance_maximo_proyeccion', '')} meses",
        f"Primer origen del backtesting (N0): {info.get('n0_backtesting', '')}",
        f"Modelo seleccionado: {info.get('modelo_seleccionado', '')}",
        f"RMSE OOS usado en la selección (1–24 meses): {_formatear_numero(info.get('rmse_seleccion_oos'))}",
        f"Segundo modelo: {info.get('modelo_segundo') or 'No aplica'}",
        f"RMSE OOS del segundo modelo: {_formatear_numero(info.get('rmse_segundo_oos'))}",
        f"Diferencia frente al segundo modelo (descriptiva, no prueba de significancia): "
        f"{_formatear_numero(info.get('diferencia_porcentual_segundo'))}%",
    ]
    for item in info.get("tabla_horizontes", []):
        lineas.append(
            f"h={item.get('horizonte')} meses | W_h={item.get('W')} | "
            f"RMSE_h={_formatear_numero(item.get('rmse'))} | MAE_h={_formatear_numero(item.get('mae'))} | "
            f"sMAPE_h={_formatear_numero(item.get('smape'))}% | MASE_h={_formatear_numero(item.get('mase'))} | "
            f"sesgo_h={_formatear_numero(item.get('sesgo'))}"
        )
    return lineas


def _lineas_determinacion_horizonte(resultado: dict[str, Any]) -> list[str]:
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12 - sincronizar reportes).
    # Retirada la semantica triangular (maximo recomendado/admisible/como
    # escenario, primer horizonte no viable, huecos). El alcance operativo de
    # SAVIP es fijo (24 meses, decision institucional, no frontera
    # estadistica) y el modelo se selecciona una unica vez sobre el dominio
    # comun 1..24; el horizonte solicitado por el usuario solo determina que
    # segmento de la trayectoria interna se presenta.
    info = _analisis_horizontes_completo(resultado)
    trazabilidad = info.get("trazabilidad") or {}
    lineas = [
        (
            f"Alcance máximo de proyección de SAVIP: {info.get('alcance_maximo_proyeccion', '')} meses. "
            "Este límite corresponde al alcance operativo definido para la herramienta y no constituye "
            "una frontera estadística universal de predictibilidad."
        ),
        (
            "SAVIP compara los modelos candidatos mediante validación temporal fuera de muestra sobre un "
            "dominio común de 1 a 24 meses, usando los mismos orígenes históricos para todos los "
            "horizontes y modelos. El modelo seleccionado es el de menor RMSE OOS sobre esa matriz común."
        ),
        f"Horizonte solicitado: {info.get('horizonte_solicitado', resultado.get('horizonte_solicitado', ''))} meses.",
        f"Primer origen del backtesting (N0): {info.get('n0_backtesting', '')} observaciones.",
        f"Modelo seleccionado: {info.get('modelo_seleccionado', '')}.",
        f"RMSE OOS usado en la selección (1–24 meses): {_formatear_numero(info.get('rmse_seleccion_oos'))}.",
        f"Segundo modelo: {info.get('modelo_segundo') or 'No aplica'}.",
        f"RMSE OOS del segundo modelo: {_formatear_numero(info.get('rmse_segundo_oos'))}.",
        (
            "Consistencia metodológica: "
            f"firma de serie={trazabilidad.get('firma_serie_sha256', 'No disponible')}; "
            f"versión de criterios={trazabilidad.get('version_criterios', 'No disponible')}."
        ),
    ]
    return [linea for linea in lineas if str(linea).strip()]


def _lineas_uso_obras_civiles() -> list[str]:
    return [
        "La proyección corresponde al índice ICOCIV seleccionado por el usuario y no a toda la operación estadística.",
        "La trayectoria central es un escenario base para análisis técnico de actualización.",
        # P0-C / C2, 15-08-2026: ninguna banda se reporta ya. La frase anterior
        # afirmaba lo contrario y anunciaba una cobertura que tampoco se publica.
        "Esta versión no publica intervalo de predicción: su método no está sustentado, de modo que ni sus límites ni su cobertura forman parte de la salida.",
        "En horizontes largos se debe hablar de escenario estadístico, no de valor definitivo.",
        "La incertidumbre del pronóstico no viene acotada; debe considerarse con criterio profesional antes de usar el resultado en obras civiles.",
    ]


#: Como se describe el metodo de evaluacion de cobertura en las salidas. El
#: texto se elige a partir del resultado; NUNCA se escribe fijo, porque el
#: metodo puede cambiar y una frase fija lo convertiria en una afirmacion falsa.
DESCRIPCION_METODO_COBERTURA = {
    "particion_temporal": "Evaluación mediante partición temporal fija.",
    "origen_movil": "Evaluación mediante origen móvil.",
    "no_evaluable": "Cobertura no evaluable.",
}


def describir_metodo_cobertura(resultado: dict[str, Any]) -> str:
    """Frase del metodo de evaluacion de cobertura, tomada del resultado.

    Se lee `cobertura_empirica["metodo_evaluacion"]`. Si el resultado no
    declara metodo y la cobertura no es verificable, se dice justamente eso;
    nunca se supone un metodo.
    """
    cobertura = resultado.get("cobertura_empirica") or {}
    declarado = str(cobertura.get("metodo_evaluacion") or "").strip().lower()
    if declarado:
        for clave, texto in DESCRIPCION_METODO_COBERTURA.items():
            if clave in declarado:
                return texto
        return f"Evaluación mediante {declarado.replace('_', ' ')}."
    if not cobertura.get("verificable"):
        return DESCRIPCION_METODO_COBERTURA["no_evaluable"]
    return DESCRIPCION_METODO_COBERTURA["particion_temporal"]


def _cobertura_x_sobre_y(resultado: dict[str, Any]) -> str:
    """Cobertura observada como aciertos/evaluaciones por horizonte."""
    filas = (resultado.get("cobertura_empirica") or {}).get("por_horizonte") or []
    partes: list[str] = []
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        try:
            proporcion = float(fila["cobertura_95"])
            n_prueba = int(fila.get("n_prueba") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if n_prueba:
            partes.append(f"h={int(fila['horizonte'])}: {int(round(proporcion * n_prueba))}/{n_prueba}")
    return "; ".join(partes)


def _lineas_fundamento_estadistico(resultado: dict[str, Any]) -> list[str]:
    politica = resultado.get("politica_modelos") or (resultado.get("stats") or {}).get("politica_modelos") or {}
    # AUDITORIA 09-08-2026, P0-B: el escalonado por "niveles" se retiro. El
    # catalogo se define por estimabilidad matematica; lo unico que excluye a un
    # modelo, ademas de no poder ajustarse, es tener un parametro propio sin
    # fuente. Se publica el criterio real, no el concepto retirado.
    criterio_catalogo = str(
        politica.get("criterio_elegibilidad")
        or "Elegibilidad por estimabilidad matematica del modelo."
    )
    excluidos = politica.get("modelos_excluidos_por_parametro_sin_sustento") or []
    modelo = str(resultado.get("model_name", "No seleccionado"))
    lineas = [
        "El análisis trata el índice ICOCIV como una serie temporal económica mensual; por ello la validación se realiza con walk-forward validation, respetando la relación pasado-futuro y evitando particiones aleatorias.",
        "MAE, RMSE, MAPE, sMAPE y MASE resumen error absoluto, error cuadratico, error porcentual y desempeño relativo frente a una escala naive.",
        "MASE se calcula con denominador naive no estacional dentro de cada ventana de entrenamiento: promedio de |y_t - y_{t-1}|. Se interpreta como métrica auxiliar y no como veto único.",
        "La comparación contra naive y drift permite verificar si un modelo agrega valor frente a reglas simples de pronostico. Un modelo simple puede ser preferible si ofrece menor error fuera de muestra y mayor trazabilidad.",
        # P0-C / ESTRATEGIA C2, 15-08-2026. Estas dos lineas describian el
        # intervalo que se entregaba y anunciaban que su cobertura se publicaba.
        # Esta version no publica ni la banda ni su cobertura: mantenerlas
        # describiria una salida que el informe ya no contiene.
        "Esta versión no publica intervalo de predicción. La construcción completa del método no está sustentada bajo los requisitos metodológicos del proyecto, de modo que ni sus límites ni su cobertura forman parte de la salida. Retirarlo no afirma que la incertidumbre no exista: afirma que no se puede acotar con un método sustentado. El pronóstico puntual se publica cuando es calculable.",
        "Durbin-Watson se interpreta principalmente en residuos de modelos OLS; para Holt u otros metodos se reporta como diagnostico descriptivo, no como prueba formal concluyente.",
        "Las regresiones sobre el nivel del índice se tratan como referencias predictivas e interpretables. Debido a posible tendencia o no estacionariedad, sus coeficientes no se leen como relaciones estructurales sin diagnostico adicional.",
        "En los modelos logaritmicos, log se entiende como logaritmo natural ln.",
        "Los umbrales de clasificación, escalamiento de modelos e incertidumbre se tratan como criterios internos documentados y configurables; no se presentan como reglas estadísticas universales.",
        f"Criterio de catalogo: {criterio_catalogo}"
        + (
            f" Modelos no elegibles por tener un parametro propio sin fuente identificada: "
            f"{', '.join(excluidos)}."
            if excluidos
            else ""
        )
        + f" Modelo/metodo seleccionado: {modelo}.",
    ]
    return lineas


def _lineas_parametros_reproducibles(resultado: dict[str, Any], serie_df: pd.DataFrame) -> list[str]:
    modelo = str(resultado.get("modelo_codigo", ""))
    params = resultado.get("parametros_modelo") or (resultado.get("stats") or {}).get("parametros_modelo") or {}
    lineas = [
        f"Nombre del modelo: {resultado.get('model_name', 'No seleccionado')}.",
        f"Escala usada: {_escala_modelo(modelo)}.",
        "Definición temporal: t es el índice mensual real derivado del periodo año-mes; el primer dato observado actua como origen de la serie histórica.",
        "Factor de actualización = indice_proyectado / ultimo_indice_observado.",
        "Variación acumulada = (factor_actualizacion - 1) * 100.",
        # P0-C / C2: la ficha describia como se construia el intervalo que se
        # entregaba. Ya no se entrega; describir su construccion invita a
        # buscarlo en el informe.
        "Esta versión no publica intervalo de predicción: su construcción no está sustentada y ni sus límites ni su cobertura forman parte de la salida.",
    ]
    if modelo == "drift":
        lineas.append("Ecuacion drift: y_hat(T+h) = y_T + h * ((y_T - y_1) / (T - 1)).")
        pendiente = params.get("pendiente_mensual", params.get("pendiente"))
        lineas.append(f"Pendiente mensual estimada: {_formatear_numero(pendiente)}.")
        lineas.append("Ejemplo: y_hat(T+1) = y_T + 1 * pendiente_mensual.")
    elif modelo == "naive":
        lineas.append("Ecuacion naive: y_hat(T+h) = y_T.")
    elif modelo == "lineal":
        lineas.append("Ecuacion lineal: y_hat_t = beta_0 + beta_1 * t.")
    elif modelo == "logaritmico":
        lineas.append("Ecuacion logarítmica temporal: y_hat_t = beta_0 + beta_1 * ln(t + desplazamiento).")
    elif modelo == "exponencial_log_lineal":
        metodo = params.get("metodo_retransformacion", "smearing_duan")
        lineas.append("Ecuacion log-lineal: ln(y_t) = beta_0 + beta_1 * t + error_t.")
        if metodo == "lognormal":
            lineas.append("Retransformación usada: y_hat_t = exp(beta_0 + beta_1 * t + sigma2_log / 2).")
        else:
            lineas.append("Retransformación usada: y_hat_t = exp(beta_0 + beta_1 * t) * smearing_factor de Duan.")
        lineas.append(
            f"sigma2_log={_formatear_numero(params.get('sigma2_log'))}; "
            f"smearing_factor={_formatear_numero(params.get('smearing_factor'))}; "
            f"metodo={metodo}."
        )
    elif modelo in {"holt_lineal", "holt_amortiguado"}:
        lineas.append("Ecuacion general Holt: pronostico = nivel_final + factor_h * tendencia_final, con parámetros de suavizamiento estimados.")
        lineas.append(
            f"alpha={_formatear_numero(params.get('alpha'))}; beta={_formatear_numero(params.get('beta'))}; "
            f"phi={_formatear_numero(params.get('phi'))}; criterio={params.get('criterio_estimacion', '')}."
        )
    else:
        lineas.append("La fórmula específica del modelo seleccionado se documenta mediante sus parámetros y la tabla de proyección exportable.")
    return lineas


def _lineas_receta_reproduccion(resultado: dict[str, Any]) -> list[str]:
    return [
        "1. Ordenar la serie por periodo año-mes en frecuencia mensual.",
        "2. Tomar el primer valor observado y_1 y el último valor observado y_T.",
        "3. Definir t como índice temporal mensual y h como horizonte de proyección en meses.",
        "4. Aplicar la ecuacion del modelo seleccionado con los parámetros reportados.",
        "5. Calcular factor_actualizacion = indice_proyectado / y_T.",
        "6. Calcular variacion_acumulada = (factor_actualizacion - 1) * 100.",
        # P0-C / C2: el paso 7 pedia construir el intervalo, y el 8 graficarlo.
        # Reproducir el resultado publicado no requiere ninguno de los dos.
        "7. Graficar la serie observada, la curva ajustada y la proyección central usando el archivo CSV de reproducibilidad. Esta versión no publica intervalo de predicción, de modo que no hay banda que reproducir.",
        f"8. Usar el modelo reportado: {resultado.get('model_name', 'No seleccionado')}; horizonte permitido: {resultado.get('horizonte_permitido', 0)} mes(es).",
    ]


def _escala_modelo(modelo: str) -> str:
    if modelo in {"variacion_lineal"}:
        return "variación mensual reconstruida al nivel del índice"
    if modelo in {"log_variacion"}:
        return "log-variación mensual reconstruida al nivel del índice"
    if modelo == "exponencial_log_lineal":
        return "ln del nivel del índice con reconstrucción exponencial corregida"
    return "nivel del índice"


def _referencias_estadisticas(resultado: dict[str, Any]) -> list[str]:
    modelos = set((resultado.get("politica_modelos") or {}).get("modelos_evaluados", []))
    for item in resultado.get("catalogo_modelos", []) or []:
        if item.get("ejecutado") == "Si":
            modelos.add(str(item.get("codigo", "")))
    modelos.add(str(resultado.get("modelo_codigo", "") or ""))
    diag = resultado.get("diagnostico_residuos") or {}
    stats = resultado.get("stats") or {}
    refs = [
        "DANE. (2021). Metodología General Índice de Costos de la Construcción de Obras Civiles - ICOCIV.",
        "Hyndman, R. J., & Athanasopoulos, G. (2021). Forecasting: Principles and Practice.",
        "Hyndman, R. J., & Koehler, A. B. (2006). Another look at measures of forecast accuracy. International Journal of Forecasting, 22(4), 679-688.",
    ]
    if any(m in modelos for m in {"holt_lineal", "holt_amortiguado"}):
        refs.append("Holt, C. C. (1957). Forecasting seasonals and trends by exponentially weighted moving averages. Carnegie Institute of Technology.")
        refs.append("Gardner, E. S., & McKenzie, E. (1985). Forecasting trends in time series. Management Science, 31(10), 1237-1246.")
        refs.append("Gardner, E. S. (1985). Exponential smoothing: The state of the art. Journal of Forecasting, 4(1), 1-28.")
    if "huber" in modelos:
        refs.append("Huber, P. J. (1964). Robust estimation of a location parameter. The Annals of Mathematical Statistics, 35(1), 73-101.")
    if any(m in modelos for m in {"lineal", "logaritmico", "exponencial_log_lineal"}):
        refs.append("Wooldridge, J. M. (2016). Introductory Econometrics: A Modern Approach.")
        refs.append("Gujarati, D. N., & Porter, D. C. (2009). Basic Econometrics.")
        refs.append("Granger, C. W. J., & Newbold, P. (1974). Spurious regressions in econometrics. Journal of Econometrics, 2(2), 111-120.")
    if "exponencial_log_lineal" in modelos:
        refs.append("Duan, N. (1983). Smearing estimate: a nonparametric retransformation method. Journal of the American Statistical Association, 78(383), 605-610.")
        refs.append("Manning, W. G., & Mullahy, J. (2001). Estimating log models: to transform or not to transform? Journal of Health Economics, 20(4), 461-494.")
    if resultado.get("outliers"):
        refs.append("Iglewicz, B., & Hoaglin, D. C. (1993). How to Detect and Handle Outliers. ASQC Quality Press.")
    if _valor_finito_reporte(diag.get("durbin_watson")):
        refs.append("Durbin, J., & Watson, G. S. (1950, 1951). Testing for serial correlation in least squares regression.")
    if _valor_finito_reporte((diag.get("ljung_box") or {}).get("p_value")):
        refs.append("Ljung, G. M., & Box, G. E. P. (1978). On a measure of lack of fit in time series models. Biometrika, 65(2), 297-303.")
    if _valor_finito_reporte(diag.get("jb_p")):
        refs.append("Jarque, C. M., & Bera, A. K. (1980). Efficient tests for normality, homoscedasticity and serial independence of regression residuals. Economics Letters, 6(3), 255-259.")
    if (diag.get("heterocedasticidad") or {}).get("calculable"):
        refs.append("Breusch, T. S., & Pagan, A. R. (1979). A simple test for heteroscedasticity and random coefficient variation. Econometrica, 47(5), 1287-1294.")
    if _valor_finito_reporte(stats.get("aic")):
        refs.append("Akaike, H. (1974). A new look at the statistical model identification. IEEE Transactions on Automatic Control, 19(6), 716-723.")
    if _valor_finito_reporte(stats.get("aicc")):
        refs.append("Hurvich, C. M., & Tsai, C. L. (1989). Regression and time series model selection in small samples. Biometrika, 76(2), 297-307.")
    return list(dict.fromkeys(refs))


def _valor_finito_reporte(valor: Any) -> bool:
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


def _lineas_cobertura_empirica(resultado: dict[str, Any]) -> list[str]:
    """Evidencia OOS del horizonte y salvaguarda aplicada.

    P0-C / ESTRATEGIA C2, 15-08-2026. Este bloque publicaba la cobertura
    observada del paso exacto, el mínimo global y la cobertura por horizonte con
    sus advertencias. Todas describen el desempeño de un intervalo que esta
    versión ya no publica; sin banda publicada dejan de ser un resultado y
    quedan como diagnóstico interno, que se sigue calculando. NO se afirma que
    esa cobertura sea inválida: se deja de publicarla.

    Se conserva el tamaño de la evidencia del paso —cuántos errores fuera de
    muestra reúne ese horizonte—, que describe la trayectoria y no la banda, y
    la salvaguarda con benchmarks, que es una decisión sobre el MODELO.
    """
    lineas: list[str] = []
    paso = resultado.get("verificabilidad_paso_exacto") or {}
    if paso.get("paso_exacto"):
        lineas.append(
            f"Evidencia fuera de muestra del paso exacto solicitado h={paso.get('paso_exacto')}: "
            f"{paso.get('n_errores_oos')} errores fuera de muestra."
        )
    lineas.append(
        "Intervalo de predicción: no se publica en esta versión. Su método no está sustentado, "
        "de modo que ni sus límites ni su cobertura forman parte de la salida."
    )
    salvaguarda = resultado.get("salvaguarda_benchmark") or {}
    if salvaguarda.get("intentada"):
        # H-2A, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Las dos
        # ramas que aqui existian describian una sustitucion ("se aplico X a
        # toda la trayectoria...") y afirmaban sin comprobarlo que "los
        # benchmarks tampoco los cumplieron". `activada` nunca es True en el
        # codigo vigente -la salvaguarda es diagnostica desde el 08-08-2026,
        # nunca sustituye el modelo ni cambia el horizonte admisible- y la
        # rama alcanzable ignoraba `benchmark_habria_ampliado`.
        habria_ampliado = bool(salvaguarda.get("benchmark_habria_ampliado"))
        lineas.append(
            f"Salvaguarda con benchmarks (diagnóstico, no sustitución): el modelo principal "
            f"({salvaguarda.get('modelo_principal')}) no fue recomendable en algún horizonte "
            f"({salvaguarda.get('razon_fallo_principal')}). " + (
                "Al menos un benchmark alcanzaría un horizonte mayor, pero el modelo publicado sigue "
                "siendo el de la selección por RMSE fuera de muestra."
                if habria_ampliado
                else "Ningún benchmark alcanzaría un horizonte mayor que el modelo principal."
            )
        )
        for item in salvaguarda.get("benchmarks_evaluados", []):
            lineas.append(
                f"Benchmark evaluado {item.get('nombre')}: "
                f"RMSE relativo ponderado={_formatear_numero(item.get('rmse_ponderado'))}, "
                f"horizonte admisible={item.get('h_max_admisible')}, "
                f"{'cumple' if item.get('cumple') else 'no cumple'}."
            )
    return [linea for linea in lineas if str(linea).strip()]


def _lineas_proyeccion(resultado: dict[str, Any]) -> list[str]:
    if not resultado.get("proyeccion_generada"):
        factibilidad = resultado.get("factibilidad", {})
        lineas = [
            "La proyección no fue generada.",
            str(resultado.get("explicacion", "")),
            "Resultado de factibilidad de proyección: no proyectable.",
            "El informe conserva validación, descriptivos y diagnosticos disponibles.",
        ]
        lineas.extend([f"Diagnostico fallido: {r}" for r in factibilidad.get("razones_tecnicas", [])])
        lineas.append(
            "Recomendación: revisar continuidad, longitud histórica, valores atípicos, "
            "desempeño frente a benchmarks y estructura residual antes de usar un pronostico."
        )
        return lineas
    proyecciones = resultado.get("proyecciones")
    lineas = [
        f"Periodo solicitado: {resultado.get('periodo_solicitado')}",
        f"Horizonte permitido: {resultado.get('horizonte_permitido')} meses",
        f"Modelo usado: {resultado.get('model_name')}",
    ]
    if isinstance(proyecciones, pd.DataFrame):
        if not proyecciones.empty:
            primera = proyecciones.iloc[0]
            # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). Se retira «Metodo de
            # intervalos calculado internamente (no publicado): pronóstico ± c·σ̂_h
            # ...». Nombrar la receta de la banda en el informe HTML publica su
            # construcción, que es justamente lo que P0-C retira, y el sufijo «no
            # publicado» no lo vuelve privado: el informe ES la publicación.
            #
            # Se conserva el hecho sustantivo, que describe la trayectoria y no la
            # banda: cuántas ventanas fuera de muestra reúne el paso.
            lineas.append(
                f"Evidencia fuera de muestra del paso entregado: "
                f"{primera.get('ventanas_oos_horizonte', '')} ventana(s) de origen móvil "
                f"para el paso h={primera.get('paso_exacto_errores_oos', '')}."
            )
            if str(primera.get("advertencia_evidencia_oos", "")).strip():
                lineas.append(f"Advertencia de evidencia fuera de muestra: {primera.get('advertencia_evidencia_oos')}")
        lineas.extend(_lineas_cobertura_empirica(resultado))
        for _, fila in proyecciones.iterrows():
            lineas.append(
                f"{fila['periodo']}: índice={_formatear_numero(fila['indice_proyectado'])}, "
                f"factor={_formatear_numero(fila.get('factor_actualizacion'))}, "
                f"variación acumulada={_formatear_numero(fila['variacion_acumulada_pct'])}%"
                # P0-C / C2: aqui se emitia el intervalo del 95 % con sus dos
                # limites en cada paso de la trayectoria. Se retira: el metodo
                # de esa banda no esta sustentado.
            )
    permitido = int(resultado.get("horizonte_permitido") or 0)
    for item in (resultado.get("horizonte_info") or {}).get("evaluaciones", []):
        h = int(item.get("horizonte") or 0)
        if h > permitido and not item.get("permitido"):
            lineas.append(
                f"El horizonte h={h} fue evaluado, pero no se proyecta porque fue clasificado como no recomendable. "
                f"Motivo: {item.get('motivo') or item.get('mensaje') or item.get('recomendacion')}."
            )
    return lineas


def construir_bytes_reporte_docx(
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    projection: dict,
    year_month: list[str],
) -> bytes:
    """Compatibilidad: devuelve el informe técnico DOCX como bytes."""
    from app_icociv.reportes import docx_render
    from app_icociv.reportes.contenido import construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme

    datos = _datos_informe(
        "No especificado", "", None, fuente_label, fila, serie_df, projection, year_month, None,
    )
    informe = construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo("tecnico"))
    return docx_render.a_bytes(informe)


def guardar_reporte_docx(
    output_path: str,
    fuente_label: str,
    fila: pd.DataFrame,
    serie_df: pd.DataFrame,
    projection: dict,
    year_month: list[str],
) -> None:
    """Compatibilidad: genera el reporte y lo guarda directamente."""
    datos = construir_bytes_reporte_docx(
        fuente_label=fuente_label,
        fila=fila,
        serie_df=serie_df,
        projection=projection,
        year_month=year_month,
    )
    ruta = Path(output_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
