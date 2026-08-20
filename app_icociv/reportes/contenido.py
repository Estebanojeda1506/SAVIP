"""Construcción del contenido de los informes de proyección.

Este módulo traduce el resultado de la proyección a un :class:`Informe`
independiente del formato. **No calcula estadística**: solo lee el diccionario
que devuelve ``ejecutar_proyeccion`` y decide qué se cuenta, en qué orden y con
qué palabras.

La interpretación es dinámica por diseño: cada frase se arma con los valores
reales del análisis. Una frase que diría lo mismo con cualquier serie no aporta
nada y no debe escribirse aquí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app_icociv.config.rutas import VERSION
from app_icociv.proyeccion.servicio_proyeccion import nombre_visible_candidato
from app_icociv.reportes import graficas
from app_icociv.reportes.modelo import (
    Aviso,
    ConfiguracionInforme,
    Ficha,
    Firmas,
    Formula,
    Imagen,
    Informe,
    NOMBRE_COMPLETO,
    Parrafo,
    Portada,
    Seccion,
    Tabla,
    Vinetas,
    es_numero,
    fecha_hora_larga,
    formato_entero,
    formato_indice,
    formato_porcentaje,
    identificador_informe,
    periodo_corto,
    periodo_largo,
    texto_o,
    unir,
)
from app_icociv.utilidades.nomenclatura_icociv import nombre_tabla_icociv
from app_icociv.utilidades.utilidades import version_statsmodels


# H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Se
# retiran las entradas "escenario" y "extendida_cautela"/
# "escenario_alta_incertidumbre" de estos dos diccionarios:
# `_estructurar_resultado_horizontes` solo fija `estado` en
# "proyeccion_tecnica" o "no_admisible", y `_clasificar_evidencia_horizonte`
# solo fija `clasificacion` en "tecnica_alta", "tecnica_cautela", "no_viable"
# o "no_evaluado" (ver sus comentarios H-4 residual). Mantener las entradas
# retiradas presentaba estados inalcanzables como si fueran salidas posibles.
ESTADOS_VISIBLES = {
    "proyeccion_tecnica": "Proyección técnica",
    "no_admisible": "No admisible",
}

CLASIFICACIONES_VISIBLES = {
    "tecnica_alta": "Proyección técnica",
    "tecnica_cautela": "Proyección técnica con cautela",
    "no_viable": "No recomendable",
    "no_evaluado": "No evaluado",
}

LIMITACIONES_FIJAS = (
    "SAVIP no sustituye el índice oficial publicado por el DANE.",
    "Las proyecciones son herramientas de análisis y planeación.",
    "No deben utilizarse directamente para liquidar contratos.",
    "Esta versión no publica intervalo de predicción: el método no está sustentado y la "
    "incertidumbre del pronóstico no viene acotada.",
    "Una serie volátil exige mayor precaución al leer la trayectoria central.",
    "El alcance máximo de proyección de SAVIP es de 24 meses; no constituye una frontera estadística "
    "universal de predictibilidad.",
    "El usuario debe revisar las condiciones contractuales aplicables antes de usar el resultado.",
)


@dataclass
class DatosProyeccion:
    """Todo lo que el informe necesita saber del análisis, ya resuelto."""

    resultado: dict[str, Any]
    serie_df: pd.DataFrame
    fuente_label: str = ""
    archivo_excel: str = ""
    ruta_jerarquica: Any = None
    fila: pd.DataFrame | None = None
    year_month: list[str] = field(default_factory=list)
    usuario: str = ""
    nombre_sesion: str | None = None


# ==============================
# LECTURAS DEL RESULTADO
# ==============================


def _solicitado(resultado: dict[str, Any]) -> dict[str, Any]:
    bloque = resultado.get("resultado_horizonte_solicitado")
    if isinstance(bloque, dict) and bloque:
        return bloque
    generado = bool(resultado.get("proyeccion_generada", False))
    return {
        "horizonte_solicitado": resultado.get("horizonte_solicitado"),
        "origen_horizonte": resultado.get("origen_horizonte", "predeterminado"),
        "estado": "proyeccion_tecnica" if generado else "no_admisible",
        "proyeccion_generada": generado,
        "indice_proyectado": resultado.get("y_proj") if generado else None,
        "periodo_proyectado": resultado.get("periodo_proj") if generado else None,
        "modelo_aplicado": resultado.get("model_name") if generado else None,
        "ic95": [resultado.get("ci95_lo"), resultado.get("ci95_hi")] if generado else None,
        "nivel_confianza": (resultado.get("factibilidad") or {}).get("nivel_confianza_metodologica"),
        "razon_principal": resultado.get("explicacion"),
    }


def _horizontes(resultado: dict[str, Any]) -> dict[str, Any]:
    info = resultado.get("analisis_horizontes_completo") or resultado.get("horizonte_info") or {}
    if "tabla_horizontes" not in info:
        info = {**info, "tabla_horizontes": info.get("evaluaciones") or []}
    return info


def _clasificacion_por_horizonte(resultado: dict[str, Any]) -> dict[int, str]:
    salida: dict[int, str] = {}
    for item in _horizontes(resultado).get("tabla_horizontes") or []:
        if not isinstance(item, dict) or not es_numero(item.get("horizonte")):
            continue
        clave = str(item.get("clasificacion") or "")
        salida[int(item["horizonte"])] = CLASIFICACIONES_VISIBLES.get(clave, texto_o(item.get("estado"), "No clasificado"))
    return salida


#: Longitud maxima de una celda de tabla. Por encima de esto el DOCX deja de
#: ser legible: la fila crece y desplaza el resto de la pagina.
MAX_TEXTO_CELDA = 180


def _limitar(texto: str, maximo: int = MAX_TEXTO_CELDA) -> str:
    """Recorta un texto para que quepa en una celda sin deformar la tabla."""
    limpio = " ".join(str(texto).split())
    if len(limpio) <= maximo:
        return limpio
    return limpio[: maximo - 1].rstrip(" ,;.") + "…"


def _intervalo(valores: Any) -> str:
    if isinstance(valores, (list, tuple)) and len(valores) == 2 and any(v is not None for v in valores):
        return f"[{formato_indice(valores[0])} – {formato_indice(valores[1])}]"
    return "No aplica"


def _advertencias(resultado: dict[str, Any], maximo: int = 8) -> list[str]:
    categorias = resultado.get("advertencias_categorizadas") or {}
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
    for item in (resultado.get("factibilidad") or {}).get("advertencias", []) or []:
        texto = str(item).strip()
        if texto and texto not in items:
            items.append(texto)
    return items[:maximo]


def _nombre_serie(datos: DatosProyeccion) -> str:
    ruta = datos.ruta_jerarquica
    items = [{"nivel": k, "valor": v} for k, v in ruta.items()] if isinstance(ruta, dict) else list(ruta or [])
    utiles = [i for i in items if str(i.get("nivel", "")) != "Tabla ICOCIV" and str(i.get("valor", "")).strip()]
    if utiles:
        return str(utiles[-1].get("valor"))
    return nombre_tabla_icociv(datos.fuente_label) if datos.fuente_label else "Serie ICOCIV seleccionada"


def _ultimo_observado(serie_df: pd.DataFrame) -> tuple[str, float | None]:
    if not isinstance(serie_df, pd.DataFrame) or serie_df.empty or "Indice" not in serie_df:
        return "", None
    periodo = str(serie_df["Periodo"].iloc[-1]) if "Periodo" in serie_df else ""
    valor = pd.to_numeric(serie_df["Indice"], errors="coerce").iloc[-1]
    return periodo, (float(valor) if es_numero(valor) else None)


# ==============================
# TEXTO DINÁMICO
# ==============================


def resumen_ejecutivo(datos: DatosProyeccion) -> list[str]:
    """Responde las siete preguntas del §5.2 con los valores reales del análisis."""
    resultado = datos.resultado
    solicitado = _solicitado(resultado)
    info = _horizontes(resultado)
    serie = _nombre_serie(datos)
    horizonte = solicitado.get("horizonte_solicitado")
    alcance = info.get("alcance_maximo_proyeccion")
    generado = bool(solicitado.get("proyeccion_generada"))
    periodo_final, indice_final = _ultimo_observado(datos.serie_df)

    parrafos: list[str] = []

    encabezado = (
        f"Para la serie «{serie}» se solicitó una proyección de {formato_entero(horizonte)} meses "
        f"a partir de {periodo_largo(periodo_final)}, último periodo con dato observado "
        f"(índice {formato_indice(indice_final)})."
    )
    parrafos.append(encabezado)

    if not generado:
        parrafos.append(
            "SAVIP no generó proyección para el horizonte solicitado. "
            + texto_o(solicitado.get("razon_principal"), "El análisis no encontró evidencia suficiente en la validación temporal.")
        )
        parrafos.append(
            "El informe conserva la validación de datos, los descriptivos y el diagnóstico disponibles "
            "para documentar por qué el horizonte no es admisible."
        )
        return parrafos

    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12 - sincronizar reportes).
    # Metodologia vigente: SAVIP compara los candidatos mediante validacion
    # temporal fuera de muestra sobre un dominio comun de 1 a 24 meses, con
    # los mismos origenes historicos para todos los horizontes y modelos. El
    # modelo seleccionado es el de menor RMSE OOS sobre esa matriz comun; no
    # se afirma que sea "el mejor" en sentido absoluto ni estadisticamente
    # superior (Prompt 09: varias competencias resultaron estrechas, sin
    # prueba formal de significancia).
    modelo = texto_o(solicitado.get("modelo_aplicado"), "el modelo seleccionado")
    rmse_seleccion = resultado.get("rmse_seleccion_oos")
    parrafos.append(
        f"El modelo seleccionado es {modelo}: el candidato con menor RMSE fuera de muestra bajo el "
        "criterio común de evaluación (dominio 1–24 meses, mismos orígenes históricos para todos los "
        "modelos)"
        + (f", con RMSE de selección {formato_indice(rmse_seleccion)}." if es_numero(rmse_seleccion) else ".")
        + " Se reajusta con toda la serie histórica y genera una trayectoria interna de 24 meses; el "
        "horizonte solicitado por el usuario no cambia el modelo seleccionado."
    )
    modelo_segundo = resultado.get("modelo_segundo")
    diferencia_pct = resultado.get("diferencia_porcentual_segundo")
    if modelo_segundo and es_numero(diferencia_pct):
        parrafos.append(
            f"La diferencia frente al segundo candidato ({texto_o(_nombre_visible_candidato(modelo_segundo))}) bajo el mismo criterio OOS "
            f"fue de {formato_porcentaje(diferencia_pct)}. Este valor se presenta con fines descriptivos y no "
            "corresponde a una prueba de significancia estadística."
        )

    proyecciones = resultado.get("proyecciones")
    if isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty:
        fila = proyecciones.iloc[-1]
        variacion = fila.get("variacion_acumulada_pct")
        # P0-C / C2, 15-08-2026. Antes esta frase entregaba el intervalo del
        # 95 % con sus dos limites. Se retira: el metodo de esa banda no esta
        # sustentado y el resultado lo declara. Queda el pronostico puntual, que
        # si es publicable, y la advertencia de que no viene acotado.
        parrafos.append(
            f"El índice proyectado para {periodo_largo(fila.get('periodo'))} es "
            f"{formato_indice(fila.get('indice_proyectado'))}. Frente al último dato observado, "
            f"la variación acumulada es {formato_porcentaje(variacion)}. "
            "Esta versión no publica intervalo de predicción: el pronóstico se entrega como valor "
            "puntual y no viene acompañado de una banda de incertidumbre defendible."
        )

    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12 - sincronizar reportes).
    # No existe ya un "maximo recomendado" derivado de una rejilla triangular
    # ni una clasificacion "escenario": bajo N0=12/H=24 rectangular el
    # horizonte solicitado siempre esta dentro del alcance operativo (validado
    # en la entrada) y usa la misma evidencia OOS que decidio el modelo.
    if es_numero(alcance):
        parrafos.append(
            f"Alcance máximo de proyección de SAVIP: {formato_entero(alcance)} meses. Este límite corresponde "
            "al alcance operativo definido para la herramienta y no constituye una frontera estadística "
            "universal de predictibilidad."
        )

    advertencias = _advertencias(resultado, maximo=3)
    if advertencias:
        parrafos.append("Deben tenerse en cuenta las siguientes advertencias: " + unir(advertencias) + ".")
    else:
        parrafos.append("El análisis no registró advertencias principales para el resultado mostrado.")
    return parrafos


def interpretacion(datos: DatosProyeccion) -> list[str]:
    """Interpretación dinámica del §5.5: tendencia, magnitud, horizonte, incertidumbre."""
    resultado = datos.resultado
    solicitado = _solicitado(resultado)
    if not solicitado.get("proyeccion_generada"):
        return [
            "Sin proyección generada no hay trayectoria que interpretar. "
            "La lectura útil es diagnóstica: la serie no reúne la evidencia necesaria para sostener un "
            "pronóstico en el horizonte pedido, y el resultado debe usarse para decidir si se amplía el "
            "histórico o se revisa la continuidad de los datos."
        ]

    parrafos: list[str] = []
    analisis = resultado.get("analisis_serie") or {}
    tendencia = texto_o(analisis.get("tendencia"), "no determinada")
    volatilidad = analisis.get("volatilidad_pct_promedio")
    parrafos.append(
        f"La serie histórica muestra una tendencia {tendencia}"
        + (f", con una volatilidad mensual promedio de {formato_porcentaje(volatilidad)}." if es_numero(volatilidad) else ".")
        + " Ese comportamiento es el que el modelo extiende hacia el futuro."
    )

    proyecciones = resultado.get("proyecciones")
    if isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty:
        fila = proyecciones.iloc[-1]
        variacion = fila.get("variacion_acumulada_pct")
        ancho = fila.get("ancho_relativo_95")
        _, indice_base = _ultimo_observado(datos.serie_df)
        if es_numero(variacion):
            direccion = "un aumento" if float(variacion) > 0 else ("una reducción" if float(variacion) < 0 else "una variación nula")
            parrafos.append(
                f"En magnitud, el escenario central implica {direccion} de {formato_porcentaje(abs(float(variacion)))} "
                f"al final del horizonte: el índice pasaría de {formato_indice(indice_base)} a "
                f"{formato_indice(fila.get('indice_proyectado'))}."
            )
        # P0-C / C2, 15-08-2026. Aquí se publicaba la amplitud de la banda
        # («abarca aproximadamente X % alrededor del valor central»). Es una
        # magnitud del intervalo retirado: decir cuán ancha es una banda que el
        # lector no recibe no le permite hacer nada con el dato, y sugiere que
        # la incertidumbre sí está acotada. El ancho se sigue calculando como
        # diagnóstico interno.
        parrafos.append(
            "Esta versión no publica intervalo de predicción, de modo que el resultado no viene "
            "acompañado de una magnitud de incertidumbre defendible. El pronóstico puntual debe "
            "leerse con criterio profesional y junto con las advertencias del informe."
        )

    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12). Retirado el parrafo
    # "escenario": bajo N0=12/H=24 no existe clasificacion por horizonte ni un
    # "maximo recomendado" que el horizonte solicitado pueda superar (el
    # limite de entrada ya es H_OPERATIVO_MAX=24).

    calendario = resultado.get("ajuste_calendario") or {}
    if calendario.get("ajuste_calendario_aplicado"):
        salto = calendario.get("salto_mediano_pct")
        parrafos.append(
            "La serie presenta un patrón de cambio de año confirmado: el ajuste de precios se concentra en enero"
            + (f", con un salto mediano de {formato_porcentaje(salto)}." if es_numero(salto) else ".")
            + " El modelo reconcentra ese movimiento en enero en lugar de repartirlo entre los meses, "
            "por lo que el escalón de enero es un patrón calendario esperado y no un valor atípico."
        )
    elif calendario.get("hay_evidencia_calendario"):
        parrafos.append(
            "Se detectó indicio de patrón de cambio de año, pero no se cumplieron todas las condiciones para "
            "aplicar el ajuste; la trayectoria reparte el movimiento de forma regular entre los meses."
        )

    # P0-C / C2: las cuatro redacciones remitian al intervalo de predicción como
    # apoyo de lectura. Esta versión no lo publica, de modo que remitir a él
    # enviaría al lector a un dato que no está en el informe.
    # P0-G, 12-08-2026: la escalera alto/medio/bajo se retiro de
    # `_estado_por_horizonte`, que hoy devuelve "descriptivo: <tramo>,
    # <detalle>" en vez de esas tres palabras sueltas. Estas claves solo
    # coinciden por el valor de respaldo "medio"; se conserva el diccionario
    # como texto de respaldo, sin la redaccion "escenario exploratorio" que
    # nombraba el estado retirado.
    confianza = texto_o(solicitado.get("nivel_confianza"), "").lower()
    uso = {
        "alto": "El resultado es utilizable como referencia técnica en planeación y análisis presupuestal.",
        "medio": "El resultado es utilizable con cautela: conviene contrastarlo con criterio profesional antes de tomar decisiones.",
        "bajo": "El resultado debe interpretarse con cautela reforzada, junto con las advertencias del informe.",
    }.get(confianza, "El resultado debe interpretarse junto con las advertencias del informe.")
    parrafos.append(f"Nivel de confianza metodológica: {texto_o(solicitado.get('nivel_confianza'), 'no determinado')}. {uso}")
    return parrafos


# ==============================
# SECCIONES
# ==============================


def _seccion_resumen(datos: DatosProyeccion) -> Seccion:
    return Seccion("resumen", "Resumen ejecutivo", [Parrafo(p) for p in resumen_ejecutivo(datos)])


def _seccion_identificacion(datos: DatosProyeccion) -> Seccion:
    resultado = datos.resultado
    validacion = resultado.get("validacion_serie") or {}
    serie_df = datos.serie_df
    periodo_inicial = str(serie_df["Periodo"].iloc[0]) if isinstance(serie_df, pd.DataFrame) and not serie_df.empty and "Periodo" in serie_df else ""
    periodo_final, _ = _ultimo_observado(serie_df)

    ruta = datos.ruta_jerarquica
    items = [{"nivel": k, "valor": v} for k, v in ruta.items()] if isinstance(ruta, dict) else list(ruta or [])
    filas_ruta = [[texto_o(i.get("nivel"), "Nivel"), texto_o(i.get("valor"), "")] for i in items if str(i.get("valor", "")).strip()]

    bloques: list[Any] = [
        Ficha([
            ("Serie analizada", _nombre_serie(datos)),
            ("Tabla de índices", nombre_tabla_icociv(datos.fuente_label) if datos.fuente_label else "No registrada"),
            ("Archivo fuente", Path(datos.archivo_excel).name if datos.archivo_excel else "No registrado"),
            ("Periodo inicial", periodo_largo(periodo_inicial)),
            ("Periodo final", periodo_largo(periodo_final)),
            ("Frecuencia", "Mensual"),
            ("Valores faltantes", formato_entero(validacion.get("valores_faltantes", 0))),
            ("Duplicados", formato_entero(validacion.get("duplicados", 0))),
            ("Continuidad temporal", texto_o(validacion.get("continuidad_temporal"), "No verificada")),
        ]),
    ]
    if filas_ruta:
        bloques.append(Tabla(
            encabezados=["Nivel de selección", "Valor"],
            filas=filas_ruta,
            titulo="Ruta jerárquica de la selección estadística",
            nota="Corresponde a los niveles del anexo ICOCIV seleccionados en la aplicación.",
        ))
    return Seccion("identificacion", "Identificación de la serie", bloques)


# post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04). Texto comun
# para describir el tratamiento calendario del candidato ganador, reutilizado
# por ficha, seccion de horizonte y seccion de seleccion de modelo.
_TEXTO_ESTRATEGIA_CALENDARIO = {
    "fourier_k1": "Fourier anual (K=1, periodo 12 meses)",
    "seasonal_naive": "Patrón estacional de 12 meses (Seasonal Naive)",
    "ninguna": "Ninguno",
}


def _texto_estrategia_calendario(valor: Any) -> str:
    return _TEXTO_ESTRATEGIA_CALENDARIO.get(str(valor), "No aplica")


# post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 1 de
# auditoria). `_nombre_visible_candidato` ya no duplica el mapeo aqui: usa la
# fuente unica `nombre_visible_candidato` de servicio_proyeccion.py (que a su
# vez lee CATALOGO_MODELOS_CANDIDATOS, el mismo catalogo de 21 candidatos).
_nombre_visible_candidato = nombre_visible_candidato


def _seccion_ficha(datos: DatosProyeccion) -> Seccion:
    resultado = datos.resultado
    solicitado = _solicitado(resultado)
    info = _horizontes(resultado)
    validacion = resultado.get("validacion_serie") or {}
    generado = bool(solicitado.get("proyeccion_generada"))
    periodo_final, indice_final = _ultimo_observado(datos.serie_df)
    periodo_inicial = str(datos.serie_df["Periodo"].iloc[0]) if isinstance(datos.serie_df, pd.DataFrame) and not datos.serie_df.empty and "Periodo" in datos.serie_df else ""
    calendario = resultado.get("ajuste_calendario") or {}
    paso = resultado.get("verificabilidad_paso_exacto") or {}

    # P0-C / C2: la ficha destacaba el intervalo del 95 % junto al punto y al
    # modelo. Se sustituye por la declaracion de que no se publica: dejar el
    # rotulo con un guion insinuaria que el dato falta, cuando lo que ocurre es
    # que el metodo no esta sustentado y por eso no se entrega.
    destacados = [
        ("Índice proyectado final", formato_indice(solicitado.get("indice_proyectado")) if generado else "No generado"),
        ("Intervalo de predicción", "No se publica en esta versión"),
        ("Modelo utilizado", texto_o(solicitado.get("modelo_aplicado"), "No aplica")),
    ]
    filas = [
        ("Serie analizada", _nombre_serie(datos)),
        ("Último índice observado", f"{formato_indice(indice_final)} ({periodo_largo(periodo_final)})"),
        ("Horizonte solicitado", f"{formato_entero(solicitado.get('horizonte_solicitado'))} meses"),
        ("Alcance máximo de proyección de SAVIP", f"{formato_entero(info.get('alcance_maximo_proyeccion'))} meses" if es_numero(info.get("alcance_maximo_proyeccion")) else "No identificado"),
        # post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04). El pool
        # productivo tiene 21 candidatos (10 base + 10 Fourier K=1 + Seasonal
        # Naive); se separa modelo base y tratamiento calendario para no
        # exponer el codigo interno del candidato (p.ej. "fourier_k1__...").
        ("Modelo base seleccionado", texto_o(_nombre_visible_candidato(info.get("modelo_base")) or solicitado.get("modelo_aplicado"), "No aplica")),
        ("Tratamiento calendario", _texto_estrategia_calendario(info.get("estrategia_calendario"))),
        ("RMSE OOS de selección (1–24 meses)", formato_indice(info.get("rmse_seleccion_oos")) if es_numero(info.get("rmse_seleccion_oos")) else "No aplica"),
        ("Estado del horizonte", ESTADOS_VISIBLES.get(str(solicitado.get("estado")), texto_o(solicitado.get("estado"), "No disponible"))),
        ("Periodo proyectado final", periodo_largo(solicitado.get("periodo_proyectado")) if generado else "No aplica"),
        ("Patrón de cambio de año", texto_o(calendario.get("estado_calendario_visible"), "No evaluado")),
        # P0-C / C2: se retiran «Cobertura observada global», «Verificabilidad
        # del horizonte solicitado» y «Clasificación del intervalo». Las tres
        # califican una banda que ya no se entrega. Queda el tamaño de la
        # evidencia del paso, que describe la trayectoria, no el intervalo.
        ("Errores fuera de muestra del horizonte solicitado",
         formato_entero(paso.get("n_errores_oos")) if paso.get("paso_exacto") else "No aplica"),
        ("Número de observaciones", formato_entero(validacion.get("observaciones", len(datos.serie_df) if isinstance(datos.serie_df, pd.DataFrame) else 0))),
        ("Periodo analizado", f"{periodo_largo(periodo_inicial)} – {periodo_largo(periodo_final)}"),
    ]
    return Seccion("ficha", "Ficha de resultados", [Ficha(filas, destacados=destacados)])


def _motivo_ljung_box(ljung: dict[str, Any]) -> str:
    """Frase causal de por qué Ljung–Box no se calculó (RA-04).

    Nunca atribuye la ausencia a la distribución: statsmodels es obligatorio y
    su falta impide arrancar la aplicación.
    """
    mensaje = str(ljung.get("mensaje") or "").strip()
    if "residuos son constantes" in mensaje:
        return "Ljung–Box no se calcula porque los residuos son constantes."
    if "se requieren al menos" in mensaje:
        return f"Ljung–Box no se calcula porque la cantidad de residuos es insuficiente ({mensaje.split(':', 1)[-1].strip()})."
    if "no resultó finito" in mensaje:
        return "Ljung–Box no se calcula porque el estadístico no resultó finito para esta serie."
    if mensaje:
        return f"Ljung–Box no se calcula en esta serie: {mensaje.split(':', 1)[-1].strip()}"
    return "Ljung–Box no se calcula porque el diagnóstico no es aplicable a los residuos de esta serie."


def _texto_verificabilidad_paso(resultado: dict[str, Any]) -> str:
    """Estado de verificabilidad del paso exacto, en una línea (RA-01)."""
    paso = resultado.get("verificabilidad_paso_exacto") or {}
    if not paso.get("paso_exacto"):
        return "No aplica"
    n = formato_entero(paso.get("n_errores_oos"))
    estado = "verificable" if paso.get("verificable") else "no verificable"
    return f"h={formato_entero(paso.get('paso_exacto'))}: {n} errores fuera de muestra, {estado}"


def _resumen_cobertura(cobertura: dict[str, Any]) -> str:
    """Cobertura observada, con el recuento que sostiene el minimo.

    Se publica x/y ademas de la proporcion, porque con pocas evaluaciones la
    proporcion admite muy pocos valores posibles y por si sola induce a error.
    Se muestra el recuento del horizonte MINIMO -el que manda- para que la
    celda quepa en la tabla; el detalle por horizonte va en su propia seccion.
    """
    filas = [
        f for f in cobertura.get("por_horizonte") or []
        if isinstance(f, dict) and es_numero(f.get("cobertura_95"))
    ]
    if not filas:
        return ""
    valores = [float(f["cobertura_95"]) for f in filas]
    media = sum(valores) / len(valores)
    peor = min(filas, key=lambda f: float(f["cobertura_95"]))
    proporcion = float(peor["cobertura_95"])
    n_prueba = int(peor.get("n_prueba") or 0)
    detalle_peor = (
        f" (h={formato_entero(peor.get('horizonte'))}: "
        f"{int(round(proporcion * n_prueba))}/{n_prueba})"
        if n_prueba else ""
    )
    return (
        f"{formato_porcentaje(media * 100.0)} de media y "
        f"{formato_porcentaje(proporcion * 100.0)} como minimo{detalle_peor}, "
        f"sobre un nivel nominal del 95 %; {len(valores)} horizontes evaluados"
    )


def _seccion_grafica(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    imagen = graficas.grafica_principal(
        datos.serie_df, datos.resultado,
        con_intervalo=config.incluye_grafica("intervalo_95"),
    )
    if imagen is None:
        return Seccion("grafica_principal", "Gráfica principal", [])
    solicitado = _solicitado(datos.resultado)
    if solicitado.get("proyeccion_generada"):
        # post-r1-metodologia-12-24, 19-08-2026 (Prompt 13). La grafica ya no
        # deja la banda vacia: dibuja una banda DESCRIPTIVA y_hat_h +/- MAE_h
        # (MAE fuera de muestra por horizonte del modelo seleccionado, mismo
        # rectangulo que decidio la seleccion). No es un intervalo de
        # confianza (P0-C sigue retirado); el pie lo aclara explicitamente.
        pie = (
            "La línea continua es el índice publicado; la línea discontinua, la proyección del modelo. "
            "La línea vertical punteada separa lo observado de lo proyectado. "
            "La banda sombreada es la Referencia de error histórico (±MAE): representa la magnitud media "
            "absoluta de los errores observados durante la validación fuera de muestra por horizonte; no "
            "corresponde a un intervalo de confianza ni de predicción probabilístico."
        )
    else:
        pie = "Serie histórica del índice seleccionado. No se generó proyección para el horizonte solicitado."
    return Seccion("grafica_principal", "Gráfica principal", [Imagen(imagen, pie=pie)])


def _seccion_interpretacion(datos: DatosProyeccion) -> Seccion:
    return Seccion("interpretacion", "Interpretación", [Parrafo(p) for p in interpretacion(datos)])


def _seccion_advertencias(datos: DatosProyeccion) -> Seccion:
    propias = _advertencias(datos.resultado)
    bloques: list[Any] = []
    if propias:
        bloques.append(Aviso("Advertencias del análisis", propias, nivel="advertencia"))
    limitaciones = list(LIMITACIONES_FIJAS)
    if not _solicitado(datos.resultado).get("proyeccion_generada"):
        # RA-03: en un informe bloqueado no hay banda ni trayectoria, de modo que
        # las limitaciones que hablan de «el intervalo mostrado» describirían algo
        # que el documento no publica.
        limitaciones = [
            texto for texto in limitaciones
            if "intervalo mostrado" not in texto and "trayectoria central" not in texto
        ]
        limitaciones.append(
            "Este informe no publica proyección ni intervalo de predicción: el horizonte solicitado "
            "quedó bloqueado y solo se documentan validación, diagnósticos y evaluación de modelos."
        )
    bloques.append(Aviso("Limitaciones de uso", limitaciones, nivel="informacion"))
    pendientes = _bloqueos_metodologicos_visibles(datos.resultado)
    if pendientes:
        bloques.append(Aviso("Estado metodológico del resultado", pendientes, nivel="advertencia"))
    return Seccion("advertencias", "Advertencias y limitaciones", bloques)


def _bloqueos_metodologicos_visibles(resultado: dict[str, Any]) -> list[str]:
    """Publica los bloqueos metodológicos vigentes que el resultado ya declara.

    TANDA 3, 14-08-2026. El resultado transportaba `intervalo_sustentado=False`,
    `evidencia_oos_provisional=True` y `bloqueos_metodologicos={P0-C, P0-E}`, pero
    **ninguno llegaba al informe**: el lector veía métricas e intervalos sin saber
    que su fundamento sigue abierto. Es un defecto de comunicación, no de cálculo:
    no se toca ninguna cifra, se publica el estado que ya estaba decidido.

    REQ 25 —código, UI, CSV, DOCX y PDF deben coincidir— y REQ 26 —una limitación
    que afecta la interpretación institucional debe comunicarse exactamente.
    """
    avisos: list[str] = []
    if resultado.get("intervalo_sustentado") is False:
        motivo = str(resultado.get("motivo_intervalo_no_sustentado") or "").strip()
        avisos.append(
            "Intervalo de predicción NO SUSTENTADO metodológicamente. "
            + (motivo or "La construcción del intervalo no tiene respaldo completo verificable.")
        )
    if resultado.get("evidencia_oos_provisional") is True:
        avisos.append(
            "Evidencia fuera de muestra PROVISIONAL: el primer origen del backtesting no tiene "
            "todavía una justificación cerrada, de modo que las métricas y la evaluación por "
            "horizonte deben leerse como provisionales y no como validadas."
        )
    bloqueos = resultado.get("bloqueos_metodologicos") or {}
    for codigo in sorted(bloqueos):
        detalle = str(bloqueos[codigo] or "").strip()
        if detalle:
            avisos.append(f"{codigo}: {detalle}")
    return avisos


def _seccion_tabla_proyeccion(datos: DatosProyeccion) -> Seccion:
    resultado = datos.resultado
    proyecciones = resultado.get("proyecciones")
    if not isinstance(proyecciones, pd.DataFrame) or proyecciones.empty:
        # RA-03: contrato explícito del informe de una serie bloqueada. No se
        # crea ninguna trayectoria artificial ni banda vacía: se declara la
        # ausencia y por qué.
        solicitado = _solicitado(resultado)
        motivo = texto_o(resultado.get("explicacion"), "No se generó tabla de proyección.")
        bloques: list[Any] = [
            Parrafo(motivo),
            Tabla(
                encabezados=["Elemento del resultado", "Estado"],
                filas=[
                    ["Estado del horizonte solicitado", "Bloqueado: no admisible"],
                    ["Horizonte solicitado", f"{formato_entero(solicitado.get('horizonte_solicitado'))} meses"],
                    ["Trayectoria futura", "No existe: no se generó ningún valor proyectado"],
                    ["Intervalo de predicción", "No se publica en esta versión"],
                    ["Índice proyectado", "No generado"],
                    ["Modelo aplicado a la proyección", "Ninguno: la serie no habilitó proyección"],
                ],
                titulo="Ausencias declaradas del informe bloqueado",
            ),
            Parrafo(
                "SAVIP no publica un pronóstico puntual ni un intervalo para este horizonte. El informe "
                "conserva la identificación de la serie, su periodo disponible, los diagnósticos que sí "
                "fueron calculables, las advertencias y los modelos evaluados, de modo que el bloqueo "
                "quede documentado y sea auditable."
            ),
        ]
        return Seccion("tabla_proyeccion", "Proyección mes a mes", bloques)

    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12). Retirada la columna
    # "Clasificación": bajo N0=12/H=24 no existe clasificacion por horizonte
    # (tecnica/escenario/no viable); todos los meses de la trayectoria
    # provienen del mismo modelo unico, reajustado una sola vez.
    filas: list[list[str]] = []
    for _, fila in proyecciones.iterrows():
        # P0-C RUTA C2: el intervalo se retira de las salidas. Ninguno de los
        # metodos de intervalo auditados resulto adoptable y REQ 20 prohibe la
        # combinacion que se venia publicando. El calculo interno se conserva
        # como diagnostico; lo que desaparece es su PUBLICACION, y no se
        # sustituye por ninguna otra banda.
        filas.append([
            periodo_largo(fila.get("periodo")),
            formato_indice(fila.get("indice_proyectado")),
            _observacion_paso(fila),
        ])
    tabla = Tabla(
        encabezados=["Periodo", "Índice proyectado", "Observación"],
        filas=filas,
        titulo="Proyección mensual",
        nota="Trayectoria del modelo seleccionado, reajustado con toda la serie histórica. Esta versión no publica intervalo de predicción.",
        fuente="Elaboración de SAVIP sobre índices oficiales del DANE.",
        columnas_numericas=(1,),
        anchos=(3.4, 3.4, 6.0),
    )
    return Seccion("tabla_proyeccion", "Proyección mes a mes", [tabla])


def _observacion_paso(fila: pd.Series) -> str:
    variacion = fila.get("variacion_acumulada_pct")
    if es_numero(variacion):
        return f"Variación acumulada {formato_porcentaje(variacion)}"
    return ""


def _seccion_preparacion(datos: DatosProyeccion) -> Seccion:
    validacion = datos.resultado.get("validacion_serie") or {}
    faltantes = validacion.get("periodos_faltantes") or []
    bloques: list[Any] = [
        Parrafo(
            "La serie se construye leyendo la fila del anexo ICOCIV correspondiente a la selección, "
            "convirtiendo cada columna de periodo a formato año-mes, ordenando cronológicamente y "
            "validando la continuidad mensual antes de modelar."
        ),
        Tabla(
            encabezados=["Verificación", "Resultado"],
            filas=[
                ["Observaciones utilizadas", formato_entero(validacion.get("observaciones", 0))],
                ["Valores faltantes", formato_entero(validacion.get("valores_faltantes", 0))],
                ["Periodos duplicados", formato_entero(validacion.get("duplicados", 0))],
                ["Continuidad temporal", texto_o(validacion.get("continuidad_temporal"), "No verificada")],
                ["Orden cronológico", texto_o(validacion.get("orden_cronologico"), "No verificado")],
                ["Longitud mínima", texto_o(validacion.get("longitud_minima"), "No verificada")],
                ["Válida para modelación", "Sí" if validacion.get("valida_modelacion") else "No"],
            ],
            titulo="Validación de la serie",
        ),
        Parrafo(
            "Ningún valor se interpola, se suaviza ni se elimina. Los valores atípicos y los patrones de "
            "cambio de año se documentan, pero la serie que entra al modelo es la publicada."
        ),
    ]
    if faltantes:
        bloques.append(Vinetas([f"Periodo sin dato: {periodo_largo(p)}" for p in faltantes[:12]]))
    errores = [str(e) for e in (validacion.get("errores") or [])]
    if errores:
        bloques.append(Aviso("Errores de validación", errores[:8], nivel="error"))
    return Seccion("preparacion", "Preparación de la serie", bloques)


def _seccion_fundamento(datos: DatosProyeccion) -> Seccion:
    """Base metodológica del análisis, reutilizada del generador de texto técnico."""
    from app_icociv.reportes.generador_reportes import _lineas_fundamento_estadistico

    lineas = [str(l).strip() for l in _lineas_fundamento_estadistico(datos.resultado) if str(l).strip()]
    if not lineas:
        return Seccion("fundamento", "Fundamento estadístico del análisis", [])
    return Seccion("fundamento", "Fundamento estadístico del análisis", [Vinetas(lineas)])


def _seccion_modelos(datos: DatosProyeccion) -> Seccion:
    catalogo = datos.resultado.get("catalogo_modelos") or []
    if not catalogo:
        return Seccion("modelos", "Modelos evaluados", [])
    filas: list[list[str]] = []
    for item in catalogo:
        if not isinstance(item, dict):
            continue
        # RA-05: se leen exactamente las claves que publica
        # `_catalogo_modelos_reporte`, que son las mismas del backtesting que
        # alimenta la seccion de metricas. Las claves `*_backtesting` que se
        # consultaban antes no existian y dejaban toda la tabla en
        # «No disponible» mientras el texto contiguo si informaba RMSE y MAPE.
        filas.append([
            texto_o(item.get("modelo") or item.get("name") or item.get("nombre"), "Sin nombre"),
            formato_indice(item.get("mae")),
            formato_indice(item.get("rmse")),
            formato_indice(item.get("mase")),
            formato_indice(item.get("sesgo_medio")),
            texto_o(item.get("estado") or item.get("razon"), "Evaluado"),
        ])
    tabla = Tabla(
        encabezados=["Modelo", "MAE", "RMSE", "MASE", "Sesgo", "Resultado"],
        filas=filas,
        titulo="Modelos evaluados en validación temporal",
        nota="Las métricas provienen del backtesting walk-forward, no del ajuste dentro de muestra.",
        columnas_numericas=(1, 2, 3, 4),
        anchos=(4.0, 2.2, 2.2, 2.2, 2.2, 4.6),
    )
    return Seccion("modelos", "Modelos evaluados", [tabla])


def _seccion_seleccion_modelo(datos: DatosProyeccion) -> Seccion:
    resultado = datos.resultado
    bloques: list[Any] = []
    justificacion = str(resultado.get("justificacion_modelo") or "").strip()
    # H-7, 18-08-2026 (auditoria final V-CODEX-R2). El fallback decia "...
    # ponderado por horizonte: pesa mas acertar en los primeros meses que en
    # los ultimos", describiendo una ponderacion 1/h que no es el criterio de
    # seleccion vigente (RMSE OOS global sobre muestra comun, sin ponderar).
    bloques.append(Parrafo(justificacion or (
        "El modelo se selecciona por el menor RMSE fuera de muestra sobre la muestra común de todos "
        "los candidatos, sin ponderar por horizonte."
    )))
    salvaguarda = resultado.get("salvaguarda_benchmark") or {}
    if salvaguarda.get("intentada"):
        # H-2, 18-08-2026 (auditoria final V-CODEX-R2). Las dos ramas que aqui
        # existian describian una sustitucion ("se aplico {modelo} a toda la
        # trayectoria", "el horizonte admisible paso de X a Y") que la
        # salvaguarda no realiza: `activada` nunca es True en el codigo
        # vigente y el modelo/horizonte nunca cambian. La rama que SI se
        # ejecutaba afirmaba ademas "ni... cumplieron los criterios" sin
        # comprobar si algun benchmark si habia ampliado el alcance.
        habria_ampliado = bool(salvaguarda.get("benchmark_habria_ampliado"))
        bloques.append(Parrafo(
            "Se evaluó la salvaguarda con benchmarks como referencia diagnóstica: el modelo principal "
            f"({texto_o(salvaguarda.get('modelo_principal'), 'no registrado')}) no fue recomendable en algún "
            "horizonte. " + (
                "Al menos un benchmark alcanzaría un horizonte mayor, pero esto no sustituye el modelo "
                "entregado: el modelo publicado sigue siendo el de la selección por RMSE fuera de muestra."
                if habria_ampliado
                else "Ningún benchmark alcanzaría un horizonte mayor que el modelo principal."
            )
        ))
    descartes = [str(d) for d in (resultado.get("descartes_modelos") or [])]
    if descartes:
        bloques.append(Vinetas(descartes[:10]))
    return Seccion("seleccion_modelo", "Criterio de selección del modelo", bloques)


def _seccion_metricas(datos: DatosProyeccion) -> Seccion:
    metricas = (datos.resultado.get("backtesting") or {}).get("metricas") or {}
    if not metricas:
        return Seccion("metricas", "Métricas del modelo aplicado", [])
    filas = [
        ["MAE", formato_indice(metricas.get("mae")), "Error absoluto medio en puntos de índice."],
        ["RMSE", formato_indice(metricas.get("rmse")), "Penaliza más los errores grandes que el MAE."],
        ["MAPE", formato_porcentaje(metricas.get("mape")), "Error relativo medio."],
        ["sMAPE", formato_porcentaje(metricas.get("smape")), "Error relativo simétrico."],
        ["MASE", formato_indice(metricas.get("mase")), "Menor que 1 significa mejor que el pronóstico ingenuo."],
    ]
    filas = [f for f in filas if f[1] != "No disponible"]
    if not filas:
        return Seccion("metricas", "Métricas del modelo aplicado", [])
    return Seccion("metricas", "Métricas del modelo aplicado", [Tabla(
        encabezados=["Métrica", "Valor", "Lectura"],
        filas=filas,
        titulo="Métricas de error fuera de muestra",
        columnas_numericas=(1,),
        anchos=(2.6, 2.8, 10.0),
    )])


def _seccion_backtesting(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    backtesting = datos.resultado.get("backtesting") or {}
    if not backtesting.get("ejecutado"):
        motivo = texto_o(backtesting.get("interpretacion"), "No se ejecutó backtesting temporal.")
        return Seccion("backtesting", "Validación temporal (backtesting)", [Parrafo(motivo)])

    bloques: list[Any] = [
        Parrafo(
            "La validación es walk-forward con origen móvil: el modelo se reajusta con los datos disponibles "
            "hasta cada origen y pronostica los meses siguientes, que nunca formaron parte del entrenamiento. "
            "Por construcción no hay fuga de información desde el futuro hacia el ajuste."
        ),
        Tabla(
            encabezados=["Parámetro de validación", "Valor"],
            filas=[
                ["Método", texto_o(backtesting.get("metodo"), "Walk-forward")],
                ["Entrenamiento inicial", formato_entero(backtesting.get("entrenamiento_inicial"))],
                ["Orígenes evaluados", formato_entero(backtesting.get("iteraciones"))],
                ["Horizontes evaluados", f"1–{formato_entero(_horizontes(datos.resultado).get('alcance_maximo_proyeccion'))} (dominio común rectangular)"],
            ],
            titulo="Configuración del backtesting",
        ),
    ]
    if config.incluye_grafica("errores_horizonte"):
        imagen = graficas.grafica_errores_horizonte(datos.resultado)
        if imagen is not None:
            bloques.append(Imagen(imagen, pie="RMSE fuera de muestra del modelo seleccionado por horizonte, sobre el rectángulo común 1–24 meses."))
    if config.incluye_grafica("comparacion_modelos"):
        imagen = graficas.grafica_comparacion_modelos(datos.resultado)
        if imagen is not None:
            bloques.append(Imagen(imagen, pie="Modelo aplicado destacado en color de marca."))
    return Seccion("backtesting", "Validación temporal (backtesting)", bloques)


def _seccion_intervalos(datos: DatosProyeccion) -> Seccion:
    """Por qué esta versión no publica intervalo (P0-C, estrategia C2).

    La sección ya no entrega una banda ni su clasificación por cobertura: dice
    que no se publica y por qué. Se conserva la trazabilidad del método —qué se
    calculó internamente y con cuántos errores fuera de muestra—, que no es un
    límite ni una cobertura, para que la decisión de retirarlo sea auditable.
    """
    proyecciones = datos.resultado.get("proyecciones")
    if not isinstance(proyecciones, pd.DataFrame) or proyecciones.empty:
        return Seccion("intervalos", "Incertidumbre del pronóstico", [])
    primera = proyecciones.iloc[0]
    motivo = str(datos.resultado.get("motivo_intervalo_no_sustentado") or "").strip()
    bloques: list[Any] = [
        Parrafo(
            "Esta versión no publica intervalo de predicción. La construcción completa del método "
            "no está sustentada, y entregar sus límites equivaldría a afirmar una precisión que la "
            "aplicación no puede defender." + (f" {motivo}" if motivo else ""),
            enfasis=True,
        ),
        Parrafo(
            "Retirar el intervalo no significa que la incertidumbre no exista ni que el pronóstico "
            "sea exacto: significa que no se puede acotar con un método sustentado. El pronóstico "
            "puntual se publica cuando es calculable, porque una deficiencia del intervalo no "
            "invalida por sí sola el valor puntual."
        ),
        # P0-C, 16-08-2026 (V-CODEX-3). Aqui habia una tabla titulada
        # «Trazabilidad del metodo retirado» que publicaba el METODO del
        # intervalo, su recuento de errores y el horizonte de esos errores.
        # Codex la encontro materialmente en la pagina 9 del DOCX y del PDF,
        # mientras paginas anteriores declaraban que el intervalo no se publica.
        # Describir la receta de construccion de una banda retirada es publicar
        # su trazabilidad: se retira. La evidencia fuera de muestra del horizonte
        # sigue en su propia seccion, sin ligarla al metodo del intervalo.
        Tabla(
            encabezados=["Elemento", "Valor"],
            filas=[["Estado del intervalo", "No publicado en esta versión"]],
            titulo="Estado del intervalo de predicción",
        ),
    ]
    avisos: list[str] = []
    advertencia = str(primera.get("advertencia_evidencia_oos") or "").strip()
    if advertencia:
        avisos.append(advertencia)
    if (datos.resultado.get("ajuste_calendario") or {}).get("efecto_en_horizonte_solicitado"):
        avisos.append(
            "Cuando se aplica el ajuste de cambio de año, la incertidumbre de ese ajuste (gamma) "
            "tampoco estaba incorporada al método retirado."
        )
    if avisos:
        bloques.append(Aviso("Advertencias sobre el método retirado", avisos, nivel="advertencia"))
    return Seccion("intervalos", "Incertidumbre del pronóstico", bloques)


def _bloque_paso_exacto(datos: DatosProyeccion) -> list[Any]:
    """Evidencia fuera de muestra del horizonte exacto solicitado (RA-01).

    P0-C / C2, 15-08-2026. Este bloque publicaba la cobertura de la banda: la
    cobertura observada del paso, su recuento ``x/y``, la distancia al nivel
    nominal, la lectura descriptiva con las seis magnitudes, el papel del valor
    0,90, el mínimo global y la advertencia de consistencia entre horizontes.
    Todas esas cifras miden un intervalo que ya no se entrega. Sin banda
    publicada, su cobertura deja de ser un resultado y queda como diagnóstico
    interno; **no** se afirma que sea inválida, se deja de publicarla.

    Se conserva el **tamaño de la evidencia** del paso —cuántos errores fuera de
    muestra reúne ese horizonte—, que no mide la banda sino la trayectoria, y es
    lo que G-2 usa para decidir el estado del horizonte solicitado.
    """
    paso = datos.resultado.get("verificabilidad_paso_exacto") or {}
    if not paso.get("paso_exacto"):
        return []
    return [Tabla(
        encabezados=["Elemento", "Valor"],
        filas=[
            ["Paso exacto solicitado", f"{formato_entero(paso.get('paso_exacto'))} meses"],
            ["Errores fuera de muestra en ese paso", formato_entero(paso.get("n_errores_oos"))],
        ],
        titulo="Evidencia fuera de muestra del horizonte solicitado",
    )]


def _seccion_cobertura(datos: DatosProyeccion) -> Seccion:
    """Evidencia OOS del horizonte, sin la cobertura de la banda retirada.

    P0-C / C2: la tabla de cobertura por horizonte, el resumen de cobertura
    media y mínima y las advertencias de cobertura describían el desempeño del
    intervalo que esta versión ya no publica. Se retiran de la publicación; el
    cálculo permanece en `cobertura_empirica` como diagnóstico interno.
    """
    return Seccion(
        "cobertura",
        "Evidencia fuera de muestra del horizonte solicitado",
        _bloque_paso_exacto(datos),
    )


def _filas_contraste(contraste: dict[str, Any], etiqueta: str) -> list[list[str]]:
    """Publica estadístico, grados de libertad y valor p, o el motivo (D-7)."""
    if not contraste:
        return []
    if not contraste.get("calculable"):
        return [[etiqueta, "No calculable", texto_o(contraste.get("mensaje"), "El contraste no fue calculable.")]]
    valor = (
        f"estadístico {formato_indice(contraste.get('estadistico'))}; "
        f"gl {contraste.get('grados_libertad')}; "
        f"valor p {formato_indice(contraste.get('p_value'))}"
    )
    lectura = (
        f"H0: {texto_o(contraste.get('hipotesis_nula'), '')} "
        f"n = {contraste.get('n')}, alfa = {contraste.get('alfa')}. "
        f"{texto_o(contraste.get('mensaje'), '')} {texto_o(contraste.get('limitacion'), '')}"
    )
    return [[etiqueta, valor, " ".join(lectura.split())]]


def _seccion_residuos(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    diagnostico = datos.resultado.get("diagnostico_residuos") or {}
    if not diagnostico:
        return Seccion("residuos", "Diagnóstico de residuos", [])
    filas = [
        ["Media residual", formato_indice(diagnostico.get("media")), "Promedio de los errores de ajuste, en puntos de índice."],
        ["Desviación residual", formato_indice(diagnostico.get("desviacion")), "Dispersión del error de ajuste."],
        ["Durbin–Watson", formato_indice(diagnostico.get("durbin_watson")), "Descriptor de autocorrelación de primer orden; su contraste formal exige las tablas d_L/d_U."],
    ]
    jb = diagnostico.get("jb_p")
    if es_numero(jb):
        filas.append(["Jarque–Bera (valor p)", formato_indice(jb), "Contrasta normalidad de los residuos."])
    # D-7: contrastes formales con sus campos completos y su alcance.
    filas.extend(_filas_contraste(diagnostico.get("media_residual") or {}, "Media residual = 0"))
    filas.extend(_filas_contraste(diagnostico.get("heterocedasticidad") or {}, "Breusch–Pagan"))

    bloques: list[Any] = [Tabla(
        encabezados=["Indicador", "Valor", "Lectura"],
        filas=filas,
        # D-7: el alcance de los contrastes se declara en el título de la tabla.
        titulo="Diagnóstico residual — informativo; no modifica automáticamente el pronóstico",
        columnas_numericas=(1,),
        anchos=(3.6, 2.6, 9.2),
    )]

    # §6.7: no se presenta una prueba como ejecutada cuando no está disponible.
    # RA-04: statsmodels es dependencia obligatoria y siempre está instalada. Si
    # falta el valor p es porque el diagnóstico no es calculable en esta serie
    # (muestra corta, residuos constantes, estadístico no finito), no porque la
    # dependencia no exista. El motivo causal lo produce `calcular_ljung_box`.
    ljung = (diagnostico.get("ljung_box") or {})
    if es_numero(ljung.get("p_value")):
        bloques.append(Parrafo(f"Ljung–Box (valor p): {formato_indice(ljung.get('p_value'))}."))
    else:
        bloques.append(Parrafo(
            f"{_motivo_ljung_box(ljung)} La dependencia estadística statsmodels "
            f"{texto_o(version_statsmodels(), 'instalada')} está disponible y es obligatoria en esta "
            "distribución de SAVIP; lo que no es calculable es el diagnóstico para esta serie. "
            "La autocorrelación se valora con el estadístico de Durbin–Watson."
        ))

    alertas = [str(a) for a in (diagnostico.get("alertas") or [])][:8]
    if alertas:
        bloques.append(Vinetas(alertas))
    if config.incluye_grafica("residuos"):
        imagen = graficas.grafica_residuos(datos.resultado)
        if imagen is not None:
            bloques.append(Imagen(imagen, pie="Residuos del ajuste; una nube sin patrón alrededor de cero es el comportamiento deseable."))
    return Seccion("residuos", "Diagnóstico de residuos", bloques)


def _seccion_atipicos(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    outliers = [o for o in (datos.resultado.get("outliers") or []) if isinstance(o, dict)]
    marcados = [o for o in outliers if o.get("severidad") == "posible_atipico"]
    bloques: list[Any] = []
    if not marcados:
        bloques.append(Parrafo("No se identificaron valores atípicos relevantes en la serie analizada."))
        return Seccion("atipicos", "Valores atípicos", bloques)

    bloques.append(Parrafo(
        "Los valores atípicos se detectan con la desviación absoluta mediana. Se señalan para documentarlos, "
        "no para corregirlos: pueden representar choques económicos reales. Ningún valor se elimina, "
        "interpola ni suaviza."
    ))
    bloques.append(Tabla(
        encabezados=["Periodo", "Clasificación", "Detalle"],
        filas=[[
            periodo_largo(o.get("periodo")),
            texto_o(o.get("clasificacion"), "Posible valor atípico"),
            texto_o(o.get("mensaje") or o.get("descripcion"), ""),
        ] for o in marcados[:15]],
        titulo="Periodos señalados",
        anchos=(3.2, 3.6, 8.6),
    ))
    if config.incluye_grafica("atipicos"):
        imagen = graficas.grafica_atipicos(datos.serie_df, datos.resultado)
        if imagen is not None:
            bloques.append(Imagen(imagen, pie="Periodos marcados sobre la serie observada."))
    return Seccion("atipicos", "Valores atípicos", bloques)


def _seccion_calendario(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    calendario = datos.resultado.get("ajuste_calendario") or {}
    if not calendario:
        return Seccion("calendario", "Patrón de cambio de año", [])
    aplicado = bool(calendario.get("ajuste_calendario_aplicado"))
    bloques: list[Any] = [Parrafo(
        texto_o(calendario.get("mensaje"), "No se registró evaluación del patrón de cambio de año.")
    )]
    bloques.append(Tabla(
        encabezados=["Criterio evaluado", "Valor"],
        filas=[
            ["Estado", texto_o(calendario.get("estado_calendario_visible"), "No evaluado")],
            ["Patrón detectado en la serie", "Sí" if calendario.get("patron_detectado_en_serie") else "No"],
            ["Efecto dentro del horizonte solicitado", "Sí" if calendario.get("efecto_en_horizonte_solicitado") else "No"],
            ["Ajuste aplicado", "Sí" if aplicado else "No"],
            ["Transiciones diciembre–enero observadas", formato_entero(calendario.get("transiciones_diciembre_enero"))],
            ["Salto mediano de enero", formato_porcentaje(calendario.get("salto_mediano_pct")) if es_numero(calendario.get("salto_mediano_pct")) else "No disponible"],
            ["Movimiento mensual típico", formato_porcentaje(calendario.get("movimiento_mensual_tipico_pct")) if es_numero(calendario.get("movimiento_mensual_tipico_pct")) else "No disponible"],
            ["Eneros dentro del horizonte", formato_entero(calendario.get("eneros_en_horizonte"))],
        ],
        titulo="Evaluación del cambio de año",
    ))
    if aplicado:
        bloques.append(Parrafo(
            "Un enero que cumple los criterios confirmados es un patrón calendario, no un valor atípico. "
            "El patrón es una propiedad de la serie y se evalúa con independencia del horizonte; el ajuste "
            "se aplica paso a paso, de modo que los meses comunes valen lo mismo al pedir 3, 6, 12 o 18 "
            "meses. Si el horizonte no contiene ningún enero, el factor es neutro y la trayectoria no se "
            "desplaza."
        ))
        bloques.append(Parrafo(
            "Limitación declarada: la incertidumbre de la estimación de gamma no estaba incorporada al "
            "método de intervalo, que medía solo el error del modelo base. Esta versión no publica "
            "ese intervalo, de modo que ninguna de las dos incertidumbres viene acotada."
        ))
    if config.incluye_grafica("calendario"):
        imagen = graficas.grafica_calendario(datos.serie_df, datos.resultado)
        if imagen is not None:
            bloques.append(Imagen(imagen, pie="Variación de diciembre a enero en cada año de la serie."))
    return Seccion("calendario", "Patrón de cambio de año", bloques)


def _seccion_horizonte(datos: DatosProyeccion) -> Seccion:
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12 - sincronizar reportes).
    # Bajo N0=12/H=24 rectangular no hay clasificacion por horizonte
    # (tecnica/escenario/no viable): la tabla de evidencia h=1..24 es
    # descriptiva del modelo YA SELECCIONADO (RMSE_h, MAE_h, sMAPE_h, MASE_h,
    # sesgo_h, W_h), y no decide nada. `rmse_seleccion_oos` -agregado 1..24- es
    # la unica metrica decisiva; se distingue explicitamente de RMSE_h.
    info = _horizontes(datos.resultado)
    evaluaciones = info.get("tabla_horizontes") or []
    bloques: list[Any] = [Parrafo(
        "SAVIP compara los modelos candidatos mediante validación temporal fuera de muestra sobre un "
        "dominio común de 1 a 24 meses, usando los mismos orígenes históricos para todos los horizontes "
        "y modelos. El modelo seleccionado es el de menor RMSE OOS sobre esa matriz común; luego se "
        "reajusta con toda la serie y se genera una trayectoria de 24 meses, de la cual se presenta el "
        "valor correspondiente al horizonte solicitado."
    )]
    filas_metodologia = [
        ["Horizonte solicitado", f"{formato_entero(info.get('horizonte_solicitado'))} meses"],
        ["Alcance máximo de proyección de SAVIP", f"{formato_entero(info.get('alcance_maximo_proyeccion'))} meses"],
        ["Primer origen del backtesting (N0)", f"{formato_entero(info.get('n0_backtesting'))} observaciones"],
        # post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 04). Se
        # separa modelo base y tratamiento calendario para no mostrar el
        # codigo interno del candidato (p.ej. "fourier_k1__holt_lineal").
        ["Modelo base seleccionado", texto_o(_nombre_visible_candidato(info.get("modelo_base") or info.get("modelo_seleccionado")))],
        ["Tratamiento calendario", _texto_estrategia_calendario(info.get("estrategia_calendario"))],
        ["RMSE OOS usado en la selección (1–24 meses)", formato_indice(info.get("rmse_seleccion_oos"))],
        ["Segundo candidato", texto_o(_nombre_visible_candidato(info.get("modelo_segundo")), "No aplica")],
        [
            "Diferencia frente al segundo modelo",
            formato_porcentaje(info.get("diferencia_porcentual_segundo"))
            if es_numero(info.get("diferencia_porcentual_segundo")) else "No aplica",
        ],
    ]
    if info.get("estrategia_calendario") == "fourier_k1":
        filas_metodologia.extend([
            ["Fourier K", formato_entero(info.get("fourier_k"))],
            ["Fourier periodo", f"{formato_entero(info.get('fourier_periodo'))} meses"],
            ["Coeficiente seno (a)", formato_indice(info.get("fourier_coef_sin_1"))],
            ["Coeficiente coseno (b)", formato_indice(info.get("fourier_coef_cos_1"))],
            ["Amplitud", formato_indice(info.get("fourier_amplitud"))],
        ])
    elif info.get("estrategia_calendario") == "seasonal_naive":
        filas_metodologia.append(["Periodo estacional", f"{formato_entero(info.get('fourier_periodo'))} meses"])
    bloques.append(Tabla(
        encabezados=["Concepto", "Valor"],
        filas=filas_metodologia,
        titulo="Metodología de selección (N0=12, H=24)",
        columnas_numericas=(),
    ))
    if evaluaciones:
        # Maximo 6 columnas por legibilidad DOCX (convencion del proyecto).
        # Sesgo_h se conserva en la tarjeta "Error histórico de referencia"
        # de la interfaz; aqui se prioriza RMSE_h/MAE_h/sMAPE_h/MASE_h/W_h.
        bloques.append(Tabla(
            encabezados=["h", "W_h", "RMSE_h", "MAE_h", "sMAPE_h", "MASE_h"],
            filas=[[
                formato_entero(item.get("horizonte")),
                formato_entero(item.get("W")),
                formato_indice(item.get("rmse")),
                formato_indice(item.get("mae")),
                formato_porcentaje(item.get("smape")) if es_numero(item.get("smape")) else "No disponible",
                formato_indice(item.get("mase")) if es_numero(item.get("mase")) else "No disponible",
            ] for item in evaluaciones if isinstance(item, dict)],
            titulo="Evidencia fuera de muestra por horizonte (1–24 meses)",
            nota=(
                "Métricas descriptivas del modelo seleccionado en cada horizonte; no deciden la selección "
                "del modelo, que ya se resolvió con el RMSE OOS agregado sobre el dominio 1–24 meses."
            ),
            columnas_numericas=(0, 1, 2, 3, 4, 5),
            anchos=(1.2, 1.6, 2.2, 2.2, 2.2, 2.2),
        ))
    return Seccion("horizonte", "Metodología y evidencia por horizonte", bloques)


def _motivos_por_clasificacion(resultado: dict[str, Any], evaluaciones: list[Any]) -> list[str]:
    """Un motivo por clasificación, más el del horizonte solicitado.

    La tabla de horizontes da la clasificación pero no el razonamiento. Listar
    los veinte motivos sería ilegible y listar ninguno pierde la trazabilidad,
    así que se toma el primer horizonte de cada clasificación.
    """
    solicitado = _solicitado(resultado).get("horizonte_solicitado")
    vistas: set[str] = set()
    motivos: list[str] = []
    pendiente_solicitado = ""
    for item in evaluaciones:
        if not isinstance(item, dict) or not es_numero(item.get("horizonte")):
            continue
        razon = str(item.get("razon_decision") or item.get("motivo") or "").strip()
        if not razon:
            continue
        horizonte = int(item["horizonte"])
        linea = f"h={horizonte}: {razon}"
        clave = str(item.get("clasificacion") or item.get("estado") or "")
        if clave not in vistas:
            vistas.add(clave)
            motivos.append(linea)
        elif es_numero(solicitado) and horizonte == int(solicitado):
            pendiente_solicitado = linea
    if pendiente_solicitado:
        motivos.append(pendiente_solicitado)
    return motivos


def _seccion_formulas(datos: DatosProyeccion) -> Seccion:
    resultado = datos.resultado
    proyecciones = resultado.get("proyecciones")
    bloques: list[Any] = [Parrafo(
        "Las fórmulas siguientes son las que la aplicación aplica sobre el índice proyectado para derivar "
        "el factor de actualización y la variación acumulada."
    )]
    _, indice_base = _ultimo_observado(datos.serie_df)
    if isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty and es_numero(indice_base):
        fila = proyecciones.iloc[-1]
        proyectado = fila.get("indice_proyectado")
        factor = fila.get("factor_actualizacion")
        bloques.append(Formula(
            etiqueta="Factor de actualización",
            general="F = I_proyectado / I_base",
            sustitucion=[f"F = {formato_indice(proyectado)} / {formato_indice(indice_base)}"],
            resultado=f"F = {formato_indice(factor, 6)}",
        ))
        # Las fórmulas se dibujan en monoespaciada con codificación WinAnsi:
        # se usa el guion ASCII, no el signo menos tipográfico, que no existe ahí.
        bloques.append(Formula(
            etiqueta="Variación acumulada",
            general="V = (I_proyectado / I_base - 1) x 100",
            sustitucion=[f"V = ({formato_indice(proyectado)} / {formato_indice(indice_base)} - 1) x 100"],
            resultado=f"V = {formato_porcentaje(fila.get('variacion_acumulada_pct'), 2)}",
        ))
    return Seccion("formulas", "Fórmulas aplicadas", bloques)


def _seccion_reproducibilidad(
    datos: DatosProyeccion,
    config: ConfiguracionInforme,
    identificador: str,
    momento: datetime,
) -> Seccion:
    resultado = datos.resultado
    solicitado = _solicitado(resultado)
    parametros = resultado.get("parametros_modelo") or {}
    periodo_inicial = str(datos.serie_df["Periodo"].iloc[0]) if isinstance(datos.serie_df, pd.DataFrame) and not datos.serie_df.empty and "Periodo" in datos.serie_df else ""
    periodo_final, _ = _ultimo_observado(datos.serie_df)

    filas = [
        ["Identificador del informe", identificador],
        ["Versión de SAVIP", VERSION],
        ["Fecha de generación", fecha_hora_larga(momento)],
        ["Archivo fuente", Path(datos.archivo_excel).name if datos.archivo_excel else "No registrado"],
        ["Serie analizada", _nombre_serie(datos)],
        ["Modelo aplicado", texto_o(solicitado.get("modelo_aplicado"), "No aplica")],
        ["Horizonte solicitado", f"{formato_entero(solicitado.get('horizonte_solicitado'))} meses"],
        ["Periodo analizado", f"{periodo_corto(periodo_inicial)} a {periodo_corto(periodo_final)}"],
    ]
    # Solo los parámetros numéricos entran en la tabla. Las descripciones largas
    # —como el criterio de estimación— van después, en párrafo: una celda de
    # tabla con cientos de caracteres deforma la maquetación del DOCX.
    numericos = {k: v for k, v in parametros.items() if es_numero(v)}
    if numericos:
        detalle = unir([f"{k} = {formato_indice(v)}" for k, v in list(numericos.items())[:8]], ", ")
        if detalle:
            filas.append(["Parámetros del modelo", _limitar(detalle)])
    if config.csv_solicitado:
        filas.append(["CSV reproducible", "Exportado junto con este informe"])

    bloques: list[Any] = [Tabla(
        encabezados=["Elemento", "Valor"],
        filas=filas,
        titulo="Trazabilidad del informe",
        nota="Con estos datos el análisis puede repetirse y obtener el mismo resultado.",
        anchos=(5.0, 10.4),
    )]
    if config.tipo != "ejecutivo":
        # Import diferido: el generador antiguo importa este módulo al delegar.
        from app_icociv.reportes.generador_reportes import (
            _lineas_parametros_reproducibles,
            _lineas_receta_reproduccion,
            _referencias_estadisticas,
        )

        # Sin la ecuación y la receta el informe no sería reproducible a mano,
        # que es justo lo que promete esta sección.
        parametros_texto = [str(l).strip() for l in _lineas_parametros_reproducibles(resultado, datos.serie_df) if str(l).strip()]
        if parametros_texto:
            bloques.append(Parrafo("Parámetros y ecuación del modelo aplicado:", enfasis=True))
            bloques.append(Vinetas(parametros_texto))

        receta = [str(l).strip() for l in _lineas_receta_reproduccion(resultado) if str(l).strip()]
        if receta:
            bloques.append(Parrafo("Receta de reproducción de la proyección:", enfasis=True))
            bloques.append(Vinetas(receta))

        criterio = str(parametros.get("criterio_estimacion") or "").strip()
        if criterio:
            bloques.append(Parrafo(f"Criterio de estimación: {criterio}"))

        referencias = [str(r) for r in _referencias_estadisticas(resultado) if str(r).strip()]
        if referencias:
            bloques.append(Parrafo("Referencias metodológicas y estadísticas:", enfasis=True))
            bloques.append(Vinetas(referencias))
    if config.institucional.incluir_firmas:
        bloques.append(Firmas(["Elaboró", "Revisó", "Aprobó"]))
    return Seccion("reproducibilidad", "Reproducibilidad y trazabilidad", bloques)


def _seccion_anexos(datos: DatosProyeccion, config: ConfiguracionInforme) -> Seccion:
    bloques: list[Any] = []
    if config.incluir_anexo_backtesting:
        predicciones = (datos.resultado.get("backtesting") or {}).get("predicciones")
        marco = pd.DataFrame(predicciones) if isinstance(predicciones, list) else predicciones
        if isinstance(marco, pd.DataFrame) and not marco.empty:
            # P0-C, 17-08-2026 (V-CODEX-R3, residual 1). El anexo publicaba
            # Observado, Predicho, Error_abs y Error_pct de hasta sesenta ventanas.
            # Cualquiera de esas cuatro reconstruye σ̂ -y con el punto, los límites
            # exactos del intervalo retirado-, de modo que la tabla más discreta del
            # informe era la fuga más completa.
            #
            # Se conserva el DISEÑO de la validación, que es lo que el anexo debe
            # acreditar (REQ 16): desde qué origen se pronosticó, a qué periodo, con
            # qué paso, con qué modelo y con cuántas observaciones de entrenamiento.
            # Los errores agregados de esas mismas ventanas -RMSE, MAE, MASE,
            # MAPE/sMAPE, sesgo- están en la sección de evidencia, con su número de
            # ventanas.
            columnas = [c for c in ("Origen", "Periodo", "Horizonte", "Modelo",
                                    "Observaciones_entrenamiento") if c in marco.columns]
            if columnas:
                bloques.append(Tabla(
                    encabezados=[c.replace("_", " ") for c in columnas],
                    filas=[[periodo_largo(f[c]) if c in ("Origen", "Periodo") else str(f[c])
                            for c in columnas]
                           for _, f in marco.head(60).iterrows()],
                    titulo="Ventanas de validación temporal evaluadas",
                    nota=("Se muestran hasta 60 ventanas. La tabla acredita el diseño de la "
                          "validación por origen móvil; el error de cada ventana no se publica y "
                          "la evidencia se reporta agregada (RMSE, MAE, MASE) con su número de "
                          "ventanas."),
                ))
    serie = datos.serie_df
    if isinstance(serie, pd.DataFrame) and not serie.empty and {"Periodo", "Indice"}.issubset(serie.columns):
        muestra = serie if len(serie) <= 24 else pd.concat([serie.head(12), serie.tail(12)])
        bloques.append(Tabla(
            encabezados=["Periodo", "Índice observado"],
            filas=[[periodo_largo(f["Periodo"]), formato_indice(f["Indice"])] for _, f in muestra.iterrows()],
            titulo="Serie histórica utilizada",
            nota=("Vista compacta: primeros y últimos doce periodos. La serie completa está en el CSV reproducible."
                  if len(serie) > 24 else ""),
            fuente="Anexo oficial ICOCIV del DANE.",
            columnas_numericas=(1,),
            anchos=(6.0, 6.0),
        ))
    return Seccion("anexos", "Anexos", bloques)


# ==============================
# ENSAMBLADO
# ==============================


def _portada(datos: DatosProyeccion, config: ConfiguracionInforme, identificador: str, momento: datetime) -> Portada:
    solicitado = _solicitado(datos.resultado)
    periodo_final, _ = _ultimo_observado(datos.serie_df)
    filas: list[tuple[str, str]] = [
        ("Tipo de análisis", "Proyección de índices ICOCIV con validación temporal"),
        ("Serie analizada", _nombre_serie(datos)),
        ("Horizonte solicitado", f"{formato_entero(solicitado.get('horizonte_solicitado'))} meses"),
        ("Último periodo disponible", periodo_largo(periodo_final)),
        # Solo el nombre del archivo: la ruta interna nunca aparece en el informe (§5.1).
        ("Archivo fuente", Path(datos.archivo_excel).name if datos.archivo_excel else "No registrado"),
        ("Fecha y hora de generación", fecha_hora_larga(momento)),
        ("Versión de SAVIP", VERSION),
        ("Identificador del informe", identificador),
    ]
    filas.extend(config.institucional.pares())
    return Portada(
        titulo=config.titulo_documento(),
        subtitulo=NOMBRE_COMPLETO,
        filas=filas,
        observaciones=config.institucional.observaciones.strip(),
        logo=config.institucional.logo,
    )


def construir_informe_proyeccion(
    datos: DatosProyeccion,
    config: ConfiguracionInforme | None = None,
    momento: datetime | None = None,
) -> Informe:
    """Arma el informe completo respetando la selección de contenido del usuario."""
    config = config or ConfiguracionInforme()
    momento = momento or datetime.now()
    identificador = identificador_informe(momento)

    candidatas: list[Seccion] = []
    if config.incluye("resumen"):
        candidatas.append(_seccion_resumen(datos))
    if config.incluye("identificacion"):
        candidatas.append(_seccion_identificacion(datos))
    if config.incluye("ficha"):
        candidatas.append(_seccion_ficha(datos))
    if config.incluye("grafica_principal") and config.incluye_grafica("historico_proyeccion"):
        candidatas.append(_seccion_grafica(datos, config))
    if config.incluye("interpretacion"):
        candidatas.append(_seccion_interpretacion(datos))
    if config.incluye("advertencias"):
        candidatas.append(_seccion_advertencias(datos))
    if config.incluye("tabla_proyeccion"):
        candidatas.append(_seccion_tabla_proyeccion(datos))
    if config.incluye("preparacion"):
        candidatas.append(_seccion_preparacion(datos))
    if config.incluye("fundamento"):
        candidatas.append(_seccion_fundamento(datos))
    if config.incluye("modelos"):
        candidatas.append(_seccion_modelos(datos))
    if config.incluye("seleccion_modelo"):
        candidatas.append(_seccion_seleccion_modelo(datos))
    if config.incluye("metricas"):
        candidatas.append(_seccion_metricas(datos))
    if config.incluye("backtesting"):
        candidatas.append(_seccion_backtesting(datos, config))
    if config.incluye("intervalos"):
        candidatas.append(_seccion_intervalos(datos))
    if config.incluye("cobertura"):
        candidatas.append(_seccion_cobertura(datos))
    if config.incluye("residuos"):
        candidatas.append(_seccion_residuos(datos, config))
    if config.incluye("atipicos"):
        candidatas.append(_seccion_atipicos(datos, config))
    if config.incluye("calendario"):
        candidatas.append(_seccion_calendario(datos, config))
    if config.incluye("horizonte"):
        candidatas.append(_seccion_horizonte(datos))
    if config.incluye("formulas"):
        candidatas.append(_seccion_formulas(datos))
    if config.incluye("reproducibilidad"):
        candidatas.append(_seccion_reproducibilidad(datos, config, identificador, momento))
    if config.incluye("anexos"):
        candidatas.append(_seccion_anexos(datos, config))

    return Informe(
        portada=_portada(datos, config, identificador, momento) if config.incluye("portada") else None,
        secciones=[s for s in candidatas if not s.vacia()],
        identificador=identificador,
        tipo=config.tipo,
        generado=momento,
        pie=f"{NOMBRE_COMPLETO} · versión {VERSION} · {identificador}",
    )
