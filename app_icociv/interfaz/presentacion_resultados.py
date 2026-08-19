"""Presentación tabular de resultados para la interfaz ICOCIV."""

from __future__ import annotations

import math
from html import escape
from typing import Any

import pandas as pd

from app_icociv.interfaz.estilos.constantes_visuales import paleta_tema
from app_icociv.utilidades.nomenclatura_icociv import nombre_tabla_icociv


NO_DISPONIBLE = "No disponible"
NO_APLICA = "No aplica"
NO_EVALUADO = "No evaluado"

ESTADOS_DESTACADOS = {
    "Alta confiabilidad relativa",
    "Proyección con cautela",
    "Proyección extendida con cautela",
    "Proyección técnica",
    "Escenario de alta incertidumbre",
    "No admisible",
    "No recomendable",
}


def construir_html_resultados(resultado: dict[str, Any], tema: str = "claro") -> str:
    """Organiza resultados calculados por el backend sin alterar su decisión."""
    proyeccion = resultado.get("proyeccion", resultado)
    fuente_visible = resultado.get("fuente_visible") or nombre_tabla_icociv(resultado.get("fuente", ""))
    generado = bool(proyeccion.get("proyeccion_generada", True))

    bloques = [
        _estilos_html(tema),
        "<main class='resultado-icociv'>",
        _encabezado(proyeccion, generado),
        _bloque_estado_metodologico(proyeccion),
        _tabla_resultado_principal(proyeccion, fuente_visible, generado),
        _tabla_horizonte_estadistico(proyeccion),
        _tabla_evaluacion_horizontes(proyeccion),
        _tabla_incertidumbre(proyeccion),
        _bloque_salvaguarda_benchmark(proyeccion),
        _bloque_ajuste_calendario(proyeccion),
        _tabla_parametros_modelo(proyeccion),
        _tabla_criterios_seleccion(proyeccion),
        _bloque_advertencias(proyeccion),
        _tabla_proyecciones(proyeccion),
        _tabla_modelos(proyeccion),
        _detalle_tecnico(proyeccion),
        "</main>",
    ]
    return "\n".join(bloque for bloque in bloques if bloque)


def construir_html_detalle_horizonte(
    evaluacion: dict[str, Any] | None,
    tema: str = "claro",
) -> str:
    """Presenta la razón larga fuera de la tabla compacta."""
    item = evaluacion or {}
    if not item:
        contenido = (
            "<section class='bloque detalle-horizonte'>"
            "<p>Seleccione «Ver detalle» en la tabla de horizontes.</p>"
            "</section>"
        )
        return _estilos_html(tema) + contenido
    advertencias = item.get("advertencias") or item.get("advertencias_horizonte") or []
    razones = (
        item.get("razon_decision")
        or item.get("motivo")
        or item.get("mensaje")
        or item.get("recomendacion")
    )
    criterios = [
        f"Clasificación: {valor_o_no_disponible(item.get('clasificacion'))}",
        f"RMSE: {formatear_valor(item.get('rmse'))}",
        f"MAE: {formatear_valor(item.get('mae'))}",
        f"MAPE: {formatear_porcentaje(item.get('mape'))}",
        f"sMAPE: {formatear_porcentaje(item.get('smape'))}",
        f"MASE: {formatear_valor(item.get('mase'))}",
        # P0-C RUTA C2: intervalo retirado de las salidas

        f"Errores inusuales: {_fmt_entero(item.get('errores_extremos_cantidad'))} de "
        f"{_fmt_entero(item.get('errores_extremos_evaluados'))} "
        f"({formatear_porcentaje(item.get('errores_extremos'))}), descriptivo",
        f"Iteraciones: {_fmt_entero(item.get('iteraciones'))}",
    ]
    filas = [
        ("Horizonte", formatear_horizonte(item.get("horizonte")), ""),
        ("Estado", item.get("estado"), ""),
        ("Decisión", item.get("decision"), ""),
        ("Modelo", item.get("modelo_final_aplicado") or item.get("modelo_evaluado") or item.get("modelo"), ""),
        ("Razón", razones, ""),
        ("Advertencias", advertencias, ""),
        ("Criterios técnicos", criterios, ""),
        ("Observaciones", item.get("recomendacion") or item.get("mensaje"), ""),
    ]
    return _estilos_html(tema) + _tabla_clave_valor("Detalle del horizonte seleccionado", filas)


def construir_html_explicacion_tarjeta(
    clave: str,
    resultado: dict[str, Any] | None,
    tema: str = "claro",
) -> str:
    """Construye explicaciones reutilizables sin exponer estructuras internas."""
    proyeccion = (resultado or {}).get("proyeccion", resultado or {})
    solicitado = _resultado_solicitado(proyeccion)
    info = _analisis_horizontes(proyeccion)
    ultima = _ultima_fila(proyeccion.get("proyecciones"))
    backtesting = _backtesting_relevante(proyeccion)
    metricas = backtesting.get("metricas") or {}
    generado = bool(solicitado.get("proyeccion_generada"))
    evaluaciones = info.get("tabla_horizontes") or info.get("evaluaciones") or []
    evaluacion_solicitada = next(
        (
            item
            for item in evaluaciones
            if _entero(item.get("horizonte")) == _entero(solicitado.get("horizonte_solicitado"))
        ),
        {},
    )

    if clave == "indice":
        filas = [
            ("Índice proyectado", formatear_indice(solicitado.get("indice_proyectado")) if generado else "No generado", ""),
            ("Período calculado", _formatear_periodo(solicitado.get("periodo_proyectado")) if generado else NO_APLICA, ""),
            ("Horizonte correspondiente", formatear_horizonte(solicitado.get("horizonte_solicitado")), ""),
            ("Modelo que lo produjo", solicitado.get("modelo_aplicado") if generado else NO_APLICA, ""),
            ("¿Fue generado?", "Sí" if generado else "No", ""),
            ("Interpretación", solicitado.get("razon_principal"), ""),
            ("Advertencias", solicitado.get("razones_tecnicas") or evaluacion_solicitada.get("advertencias"), ""),
        ]
        nota = "Es una estimación estadística del índice para el período solicitado; no sustituye la metodología oficial del DANE."
        titulo = "Explicación del índice proyectado"
    elif clave == "horizonte":
        filas = [
            ("Horizonte solicitado", formatear_horizonte(solicitado.get("horizonte_solicitado")), ""),
            ("Origen", _texto_oracion(solicitado.get("origen_horizonte")), ""),
            ("Estado", _estado_solicitado_visible(solicitado.get("estado")), ""),
            ("Evaluación completa", "Sí" if info.get("horizonte_solicitado_cubierto") else "No", ""),
            ("Máximo recomendado", formatear_horizonte(info.get("horizonte_maximo_recomendado")), ""),
            ("Máximo evaluado", formatear_horizonte(info.get("horizonte_maximo_evaluado")), ""),
            ("Diferencia clave", "El solicitado es lo pedido; el recomendado es el último h técnico consecutivo; el evaluado es el borde real de la auditoría.", ""),
        ]
        nota = info.get("razon_parada") or "No se registró una razón de parada."
        titulo = "Explicación del horizonte solicitado"
    elif clave == "modelo":
        catalogo = proyeccion.get("catalogo_modelos") or (proyeccion.get("stats") or {}).get("catalogo_modelos") or []
        modelos = [
            item.get("modelo") or item.get("name") or item.get("nombre")
            for item in catalogo
            if item.get("modelo") or item.get("name") or item.get("nombre")
        ]
        if not modelos:
            modelos = list((proyeccion.get("stats") or {}).get("modelos_evaluados") or [])
        comparacion = _comparacion_modelo_seleccionado(proyeccion)
        filas = [
            ("Modelo final aplicado", solicitado.get("modelo_aplicado") or proyeccion.get("model_name"), ""),
            ("Modelos evaluados", modelos or NO_EVALUADO, ""),
            # H-1/H-7, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual).
            # Decia "...MASE, estabilidad, sesgo, intervalos y parsimonia",
            # presentando el intervalo (retirado, P0-C) y otras metricas como
            # criterios de seleccion. El unico criterio de seleccion vigente
            # es el RMSE fuera de muestra global sobre la muestra comun; el
            # resto se publica como informacion complementaria.
            ("Criterio de selección", "RMSE fuera de muestra global sobre la muestra común a todos los candidatos.", ""),
            ("Métricas complementarias (no deciden)", "MAE, MAPE, sMAPE, MASE, estabilidad, sesgo.", ""),
            ("RMSE", formatear_valor(metricas.get("rmse")), ""),
            ("MAE", formatear_valor(metricas.get("mae")), ""),
            ("MAPE", formatear_porcentaje(metricas.get("mape")), ""),
            ("Comparación con Naive", _ratios_benchmark(comparacion, "naive"), ""),
            ("Comparación con Drift", _ratios_benchmark(comparacion, "drift"), ""),
            ("Razón de selección", proyeccion.get("justificacion_modelo") or proyeccion.get("criterio_seleccion"), ""),
            ("Cautelas", (proyeccion.get("factibilidad") or {}).get("advertencias") or evaluacion_solicitada.get("advertencias"), ""),
        ]
        nota = "El modelo final se elige por evidencia fuera de muestra y no solo por ajuste dentro de la muestra."
        titulo = "Cómo se seleccionó el modelo"
    elif clave == "estado":
        filas = [
            ("Estado asignado", _estado_solicitado_visible(solicitado.get("estado")), ""),
            ("Decisión del sistema", _texto_oracion(solicitado.get("accion")), ""),
            ("Razón técnica", solicitado.get("razon_principal"), ""),
            ("Clasificación", evaluacion_solicitada.get("clasificacion"), ""),
            ("Condiciones influyentes", evaluacion_solicitada.get("razon_decision") or solicitado.get("razones_tecnicas"), ""),
            ("Interpretación", _interpretacion_estado(solicitado.get("estado")), ""),
        ]
        nota = "El estado resume si el horizonte puede usarse técnicamente, solo como escenario o si debe negarse."
        titulo = "Explicación del estado del horizonte"
    elif clave == "ic95":
        # P0-C / C2: no se lee la pareja de limites; no se publica.
        # P0-C RUTA C2: el intervalo se retira de las salidas; el calculo interno se conserva como diagnostico. La seccion no se deja vacia: explica por que no hay intervalo.
        filas = [
            ("Intervalo de predicción", "No se publica en esta versión", ""),
            ("Errores OOS medidos", _fmt_entero(ultima.get("ventanas_oos_horizonte")), ""),
            ("Advertencias", ultima.get("advertencia_evidencia_oos") or evaluacion_solicitada.get("advertencias"), ""),
        ]
        nota = (
            "Esta versión publica el pronóstico puntual y la evidencia histórica de error fuera de muestra. No se publica un intervalo de predicción porque no se ha adoptado una construcción metodológicamente sustentada para las condiciones de SAVIP."
        )
        titulo = "Incertidumbre: intervalo no publicado"
    else:
        filas = [
            (
                "Máximo recomendado",
                _horizonte_identificado(info.get("horizonte_maximo_recomendado"))
                + (
                    " (dentro de grilla evaluada)"
                    if info.get("maximo_recomendado_es_limite_observado")
                    else ""
                ),
                "",
            ),
            (
                "Base del máximo recomendado",
                info.get("base_horizonte_maximo_recomendado")
                or "Clasificación técnica consecutiva desde h=1",
                "",
            ),
            (
                "Máximo como escenario",
                _horizonte_identificado(info.get("horizonte_maximo_permitido_como_escenario")),
                "",
            ),
            (
                "Base del máximo como escenario",
                info.get("base_horizonte_maximo_escenario")
                or "Clasificación de escenario consecutiva antes del corte",
                "",
            ),
            ("Máximo evaluado", formatear_horizonte(info.get("horizonte_maximo_evaluado")), ""),
            (
                "Límite operativo",
                formatear_horizonte(info.get("horizonte_maximo_busqueda_configurado"))
                if _entero(info.get("horizonte_maximo_busqueda_configurado"))
                else NO_APLICA,
                "",
            ),
            ("Primer horizonte no viable", _horizonte_no_viable(info.get("primer_horizonte_no_viable")), ""),
            ("Razón de parada", info.get("razon_parada"), ""),
            (
                "Advertencia metodológica",
                info.get("advertencia_metodologica_horizontes")
                or "No se debe inferir validez para horizontes no evaluados.",
                "",
            ),
        ]
        if info.get("maximo_recomendado_es_limite_observado"):
            filas.append(
                (
                    "Significado de «dentro de grilla evaluada»",
                    "Este valor corresponde únicamente a los horizontes efectivamente evaluados. "
                    "No demuestra validez para horizontes superiores.",
                    "",
                )
            )
        nota = (
            "El máximo recomendado no corresponde al límite operativo ni al último horizonte evaluado, "
            "salvo que coincida con la clasificación técnica de la serie."
        )
        titulo = "Explicación del máximo recomendado"
    return _estilos_html(tema) + _tabla_clave_valor(titulo, filas, nota=nota)


def _interpretacion_estado(estado: Any) -> str:
    # H-1/H-4, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). El texto
    # de "proyeccion_tecnica" citaba "sus intervalos" como algo que la
    # proyeccion conserva; esta version no publica intervalo de prediccion
    # (P0-C). La clave "escenario" es ademas inalcanzable: el estado que
    # entrega `_estructurar_resultado_horizontes` solo toma
    # "proyeccion_tecnica" o "no_admisible" desde el 08-08-2026.
    return {
        "proyeccion_tecnica": "Puede usarse como proyección técnica, conservando sus advertencias y su evidencia fuera de muestra.",
        "no_admisible": "La evidencia disponible no respalda generar la proyección solicitada.",
    }.get(str(estado), NO_EVALUADO)


def valor_o_no_disponible(valor: Any) -> str:
    """Evita exponer valores internos, no finitos o contenedores crudos."""
    if _es_valor_nulo(valor):
        return NO_DISPONIBLE
    if isinstance(valor, (dict, set)):
        return NO_DISPONIBLE
    if isinstance(valor, (list, tuple)):
        items = [valor_o_no_disponible(item) for item in valor]
        items = [item for item in items if item != NO_DISPONIBLE]
        return ", ".join(items) if items else NO_DISPONIBLE
    texto = str(valor).strip()
    if not texto or texto.lower() in {
        "none",
        "null",
        "nan",
        "nat",
        "<na>",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "+infinity",
        "-infinity",
        "{}",
        "[]",
    }:
        return NO_DISPONIBLE
    return texto


def formatear_valor(valor: Any, decimales: int = 4) -> str:
    return _fmt_num(valor, decimales)


def formatear_indice(valor: Any) -> str:
    return formatear_valor(valor, 4)


def formatear_porcentaje(valor: Any, *, es_ratio: bool = False) -> str:
    numero = _numero(valor)
    if numero is None:
        return NO_DISPONIBLE
    if es_ratio:
        numero *= 100.0
    return f"{numero:.2f}%"


def formatear_factor(valor: Any) -> str:
    return formatear_valor(valor, 6)


def formatear_intervalo(inferior: Any, superior: Any) -> str:
    if _numero(inferior) is None or _numero(superior) is None:
        return NO_DISPONIBLE
    return f"[{formatear_indice(inferior)}, {formatear_indice(superior)}]"


def formatear_horizonte(valor: Any) -> str:
    numero = _entero(valor)
    if numero is None or numero <= 0:
        return NO_DISPONIBLE
    return f"{numero} mes" if numero == 1 else f"{numero} meses"


def _horizonte_identificado(valor: Any) -> str:
    numero = _entero(valor)
    return formatear_horizonte(numero) if numero and numero > 0 else "No identificado"


def construir_tabla_clave_valor(titulo: str, datos: dict[str, Any] | list[tuple[str, Any]]) -> str:
    filas = list(datos.items()) if isinstance(datos, dict) else list(datos)
    return _tabla_clave_valor(titulo, [(etiqueta, valor, "") for etiqueta, valor in filas])


def construir_badge_estado(estado: Any) -> str:
    texto = valor_o_no_disponible(estado)
    if texto not in ESTADOS_DESTACADOS:
        return f"<span class='estado-texto'>{escape(texto)}</span>"
    clase = {
        "Alta confiabilidad relativa": "estado-ok",
        "Proyección con cautela": "estado-cautela",
        "Proyección extendida con cautela": "estado-cautela",
        "Proyección técnica": "estado-ok",
        "Escenario de alta incertidumbre": "estado-cautela",
        "No admisible": "estado-alerta",
        "No recomendable": "estado-alerta",
    }[texto]
    return f"<span class='chip {clase}'>{escape(texto)}</span>"


def _encabezado(proyeccion: dict[str, Any], generado: bool) -> str:
    solicitado = _resultado_solicitado(proyeccion)
    estado = _estado_solicitado_visible(solicitado.get("estado"))
    confianza = solicitado.get("nivel_confianza")
    mensaje = (
        solicitado.get("razon_principal")
        or proyeccion.get("explicacion")
        or (proyeccion.get("horizonte_info") or {}).get("mensaje_ui")
        or "Análisis ejecutado."
    )
    titulo = "Resultado del horizonte solicitado"
    return (
        "<section class='encabezado'>"
        "<p class='eyebrow'>ICOCIV</p>"
        f"<h1>{escape(titulo)}</h1>"
        f"<p>{escape(_resumir(mensaje, 280))}</p>"
        "<p class='estado-línea'>"
        f"{construir_badge_estado(estado)}"
        f"<span class='confianza'>Nivel de confianza: {escape(_texto_oracion(confianza))}</span>"
        "</p>"
        "</section>"
    )


#: Texto de cada bloqueo metodologico abierto, para la interfaz. No decide nada:
#: describe una limitacion que el resultado ya declara.
_TEXTO_BLOQUEO_UI = {
    "P0-C": "el intervalo de predicción no cuenta con un método sustentado adoptado",
    "P0-E": "la evidencia fuera de muestra es provisional",
}


def _bloque_estado_metodologico(proyeccion: dict[str, Any]) -> str:
    """Publica en la interfaz los cuatro campos metodologicos del resultado.

    P0-G, 14-08-2026. El resultado transportaba `estado_metodologico`,
    `bloqueos_metodologicos`, `intervalo_sustentado` y `evidencia_oos_provisional`,
    y la interfaz **no mostraba ninguno**: el usuario veia un pronostico y unos
    intervalos sin saber que su fundamento sigue abierto. Es el ultimo residuo de
    la reapertura de P0-G.

    No introduce ninguna decision, escala ni semaforo: describe lo que el resultado
    ya decidio. Y distingue las dos situaciones que no deben confundirse: una
    imposibilidad TECNICA de calculo no es lo mismo que una metodologia pendiente.
    """
    estado = str(proyeccion.get("estado_metodologico") or "").strip()
    if not estado:
        return ""
    bloqueos = proyeccion.get("bloqueos_metodologicos") or {}
    intervalo_sustentado = proyeccion.get("intervalo_sustentado")
    provisional = proyeccion.get("evidencia_oos_provisional")

    if estado == "no_calculable":
        cabecera = (
            "El resultado no es técnicamente calculable con los datos disponibles. "
            "Es una limitación del cálculo, distinta de las limitaciones metodológicas "
            "que se enumeran a continuación."
        )
    elif estado == "resultado_metodologicamente_sustentado":
        cabecera = "Resultado con metodología sustentada."
    else:
        cabecera = (
            "Punto técnicamente calculable. El intervalo no cuenta con sustento "
            "metodológico adoptado y la evidencia fuera de muestra es provisional "
            "mientras los bloqueos siguen pendientes."
        )

    filas = [
        ("Estado metodológico", _texto_oracion(estado.replace("_", " ")), ""),
        ("Intervalo con método sustentado", "Sí" if intervalo_sustentado else "No", ""),
        ("Evidencia fuera de muestra", "Provisional" if provisional else "No provisional", ""),
    ]
    if bloqueos:
        detalle = "; ".join(
            f"{codigo}: {_TEXTO_BLOQUEO_UI.get(codigo, str(bloqueos[codigo])[:120])}"
            for codigo in sorted(bloqueos)
        )
        filas.append(("Bloqueos metodológicos abiertos", detalle, ""))

    cuerpo = "".join(
        f"<tr><th>{escape(str(campo))}</th><td>{escape(str(valor))}</td></tr>"
        for campo, valor, _ in filas
    )
    return (
        "<section class='bloque estado-metodologico'>"
        "<h2>Estado metodológico</h2>"
        f"<p>{escape(cabecera)}</p>"
        f"<table class='clave-valor'>{cuerpo}</table>"
        "</section>"
    )


def _tabla_resultado_principal(
    proyeccion: dict[str, Any],
    fuente_visible: str,
    generado: bool,
) -> str:
    solicitado = _resultado_solicitado(proyeccion)
    proyeccion_generada = bool(solicitado.get("proyeccion_generada"))
    filas = [
        ("Horizonte solicitado", formatear_horizonte(solicitado.get("horizonte_solicitado")), ""),
        ("Origen del horizonte", _texto_oracion(solicitado.get("origen_horizonte")), ""),
        ("Estado del horizonte solicitado", _estado_solicitado_visible(solicitado.get("estado")), ""),
        ("Acción del sistema", _texto_oracion(solicitado.get("accion")), "alerta" if not proyeccion_generada else ""),
        ("Índice proyectado", formatear_indice(solicitado.get("indice_proyectado")) if proyeccion_generada else "No generado", "destacado"),
        ("Período proyectado", _formatear_periodo(solicitado.get("periodo_proyectado")) if proyeccion_generada else NO_APLICA, ""),
        ("Modelo aplicado", solicitado.get("modelo_aplicado") if proyeccion_generada else NO_APLICA, ""),
        # P0-C RUTA C2: el intervalo se retira de las salidas; el calculo interno se conserva como diagnostico
        ("Intervalo de predicción", "No se publica en esta versión", ""),
        ("Nivel de confianza", _texto_oracion(solicitado.get("nivel_confianza")), ""),
        ("Razón principal", solicitado.get("razon_principal"), ""),
        ("Tabla ICOCIV", fuente_visible, ""),
    ]
    return _tabla_clave_valor("Resultado del horizonte solicitado", filas, clase="principal")


def _tabla_incertidumbre(proyeccion: dict[str, Any]) -> str:
    if not _resultado_solicitado(proyeccion).get("proyeccion_generada"):
        return ""
    # P0-C RUTA C2: el intervalo se retira de las salidas; el calculo interno se
    # conserva como diagnostico. Una sola fila: antes habia dos identicas.
    motivo = str(proyeccion.get("motivo_intervalo_no_sustentado") or "").strip()
    filas = [
        ("Intervalo de predicción", "No se publica en esta versión", ""),
        ("Motivo", motivo or "El método del intervalo no está sustentado.", ""),
    ]
    # P0-C / C2, 15-08-2026. Se retira tambien la COBERTURA de esa banda. Antes
    # se publicaban aqui la cobertura observada del paso, su recuento x/y, la
    # distancia al nivel nominal, la lectura descriptiva con las seis magnitudes,
    # el criterio aplicado, el papel del valor 0,90, la advertencia de cobertura
    # y el minimo global de la trayectoria. Todas ellas miden una banda que ya no
    # se entrega: sin banda publicada, su cobertura no es un resultado, es un
    # diagnostico del metodo retirado. NO se afirma que la cobertura sea
    # invalida; se deja de publicarla.
    #
    # Lo que SI se conserva es el numero de errores fuera de muestra del paso
    # exacto: es el tamano de la evidencia de ESE horizonte -lo que G-2 usa para
    # decidir su estado- y no una medida de la banda.
    paso = proyeccion.get("verificabilidad_paso_exacto") or {}
    if paso.get("paso_exacto"):
        filas.append((
            "Errores OOS del paso exacto",
            f"{_fmt_entero(paso.get('n_errores_oos'))} en h={int(paso['paso_exacto'])}",
            "",
        ))
    nota = (
        "Esta versión NO publica intervalo de predicción: la construcción completa del método no "
        "está sustentada y, mientras no lo esté, entregar sus límites sería afirmar una precisión "
        "que la aplicación no puede defender. El pronóstico puntual sí se publica cuando es "
        "calculable. La banda y su cobertura se siguen calculando como diagnóstico interno, y no "
        "se afirma que la incertidumbre no exista: se afirma que no se puede acotar con un método "
        "sustentado. Cuando se aplica el ajuste de cambio de año, la incertidumbre de ese ajuste "
        "tampoco estaba incorporada a la banda retirada."
    )
    return _tabla_clave_valor("Incertidumbre", filas, nota=nota)


def _clasificacion_intervalo(proyeccion: dict[str, Any]) -> dict[str, Any]:
    valor = proyeccion.get("clasificacion_intervalo")
    return valor if isinstance(valor, dict) else {}


def _etiqueta_clasificacion_intervalo(proyeccion: dict[str, Any]) -> str:
    return str(_clasificacion_intervalo(proyeccion).get("etiqueta") or "No clasificado")


#: Como se nombra en la interfaz el metodo con que se evaluo la cobertura. El
#: texto sale del resultado; nunca se escribe fijo.
_METODOS_EVALUACION = {
    "particion_temporal": "Evaluación mediante partición temporal fija",
    "origen_movil": "Evaluación mediante origen móvil",
    "no_evaluable": "Cobertura no evaluable",
}


def _texto_metodo_evaluacion(cobertura: dict[str, Any]) -> str:
    declarado = str((cobertura or {}).get("metodo_evaluacion") or "").strip().lower()
    for clave, texto in _METODOS_EVALUACION.items():
        if clave in declarado:
            return texto
    if declarado:
        return f"Evaluación mediante {declarado.replace('_', ' ')}"
    return _METODOS_EVALUACION["no_evaluable"]


def _texto_tipo_banda(proyeccion: dict[str, Any]) -> str:
    """Tipo de banda, que es propiedad del INTERVALO, no del horizonte.

    El texto sale del vocabulario V-C del servicio: aqui no se reescribe, para
    que la interfaz no pueda quedarse con un nombre que el servicio ya cambio.
    """
    from app_icociv.proyeccion.servicio_proyeccion import ETIQUETA_VISIBLE_VC

    tipo = str(_clasificacion_intervalo(proyeccion).get("tipo_banda") or "")
    return ETIQUETA_VISIBLE_VC.get(tipo, NO_APLICA)


def _texto_cobertura_empirica(cobertura: dict[str, Any]) -> str:
    """Cobertura observada como x/y y su proporcion, sin afirmar lo no medido.

    Publica el recuento ademas de la proporcion: con pocas evaluaciones la
    proporcion toma muy pocos valores posibles y por si sola induce a error.
    """
    if not cobertura or not cobertura.get("verificable"):
        return "No verificable con la muestra disponible"
    filas = cobertura.get("por_horizonte") or []
    if not filas:
        return "No verificable con la muestra disponible"
    partes: list[str] = []
    for fila in filas[:6]:
        proporcion = float(fila["cobertura_95"])
        n_prueba = int(fila.get("n_prueba") or 0)
        if n_prueba:
            aciertos = int(round(proporcion * n_prueba))
            partes.append(f"h={int(fila['horizonte'])}: {aciertos}/{n_prueba} ({proporcion:.0%})")
        else:
            partes.append(f"h={int(fila['horizonte'])}: {proporcion:.0%}")
    return "; ".join(partes)


def _tabla_horizonte_estadistico(proyeccion: dict[str, Any]) -> str:
    info = _analisis_horizontes(proyeccion)
    evaluados = info.get("horizontes_evaluados") or [
        item.get("horizonte") for item in info.get("evaluaciones", []) if item.get("horizonte") is not None
    ]
    no_evaluados = info.get("horizontes_no_evaluados") or info.get("horizontes_no_evaluados_no_recomendables") or []
    solicitado = _coalesce(proyeccion.get("horizonte_solicitado"), info.get("horizonte_solicitado"))
    accion = _resultado_solicitado(proyeccion).get("accion")
    filas = [
        ("Horizonte solicitado", formatear_horizonte(solicitado), ""),
        ("Horizontes evaluados", _resumen_horizontes(evaluados), ""),
        (
            "Horizonte máximo recomendado dentro de la grilla evaluada"
            if info.get("maximo_recomendado_es_limite_observado")
            else "Horizonte máximo recomendado",
            _horizonte_identificado(info.get("horizonte_maximo_recomendado")),
            "",
        ),
        (
            "Horizonte máximo permitido como escenario",
            _horizonte_identificado(info.get("horizonte_maximo_permitido_como_escenario")),
            "",
        ),
        ("Máximo horizonte evaluado", formatear_horizonte(info.get("horizonte_maximo_evaluado")), ""),
        ("Límite operativo de auditoría", formatear_horizonte(info.get("horizonte_maximo_busqueda_configurado")), ""),
        ("Primer horizonte no viable", _horizonte_no_viable(info.get("primer_horizonte_no_viable")), ""),
        ("Razón de parada", info.get("razon_parada"), ""),
        (
            "Advertencia metodológica",
            info.get("advertencia_metodologica_horizontes") or NO_APLICA,
            "",
        ),
        ("Máximo evaluable por datos", formatear_horizonte(info.get("horizonte_maximo_evaluable_por_datos")), ""),
        (
            "Horizonte solicitado cubierto",
            "Sí" if info.get("horizonte_solicitado_cubierto") else "No",
            "alerta" if not info.get("horizonte_solicitado_cubierto") else "",
        ),
        ("Horizontes no recomendables", _resumen_horizontes(info.get("horizontes_no_recomendables") or []), ""),
        ("Horizontes no evaluados", _resumen_horizontes(no_evaluados), ""),
        ("Acción global", _texto_oracion(accion), "alerta" if accion == "negar" else ""),
    ]
    nota = (
        "El horizonte solicitado no pudo evaluarse completamente por falta de evidencia OOS suficiente."
        if not info.get("horizonte_solicitado_cubierto")
        and info.get("tipo_parada") == "evidencia_oos_insuficiente"
        else (
            "El máximo recomendado alcanzó el borde de la grilla evaluada; no implica validez para horizontes superiores."
            if info.get("maximo_recomendado_es_limite_observado")
            else "El horizonte solicitado indica hasta dónde desea proyectar el usuario; "
            "la app evalúa si existe respaldo estadístico suficiente."
        )
    )
    return _tabla_clave_valor("Resumen del análisis dinámico de horizontes", filas, nota=nota)


def _tabla_parametros_modelo(proyeccion: dict[str, Any]) -> str:
    modelo = valor_o_no_disponible(proyeccion.get("model_name"))
    parametros = proyeccion.get("parametros_modelo") or (proyeccion.get("stats") or {}).get("parametros_modelo") or {}
    filas: list[tuple[str, Any, str]] = [("Modelo", modelo, "")]

    etiquetas = {
        "primer_valor": "Primer valor observado",
        "y_1": "Primer valor observado",
        "ultimo_valor": "Último valor observado",
        "y_t": "Último valor observado",
        "n": "Número de observaciones",
        "t": "Número de observaciones",
        "pendiente": "Pendiente promedio",
        "pendiente_mensual": "Pendiente promedio",
        "beta_0": "Beta 0",
        "beta_1": "Beta 1",
        "alpha": "Alfa",
        "beta": "Beta",
        "phi": "Phi",
        "nivel_final": "Nivel final",
        "tendencia_final": "Tendencia final",
        "smearing_factor": "Factor smearing",
        "sigma2_log": "Varianza residual log",
        "metodo_retransformacion": "Retransformación",
        "formula": "Fórmula usada",
        "formula_prediccion": "Fórmula usada",
    }
    for clave, valor in parametros.items():
        if clave in {"backend", "componentes", "criterio_estimacion", "transformacion"}:
            continue
        etiqueta = etiquetas.get(clave, clave.replace("_", " ").capitalize())
        filas.append((etiqueta, _fmt_parametro(valor), ""))
    if "drift" in modelo.lower() and not any("formula" in fila[0].lower() for fila in filas):
        filas.append(("Fórmula usada", "y_T + h × pendiente_mensual", ""))
    criterio = parametros.get("criterio_estimacion")
    if criterio:
        filas.append(("Criterio de estimación", _resumir(criterio, 120), ""))
    if len(filas) == 1:
        filas.append(("Parámetros estimados", NO_DISPONIBLE, ""))

    return _tabla_clave_valor("Parámetros del modelo seleccionado", filas)


def _tabla_criterios_seleccion(proyeccion: dict[str, Any]) -> str:
    backtesting = _backtesting_relevante(proyeccion)
    metricas = backtesting.get("metricas") or {}
    comparacion = _comparacion_modelo_seleccionado(proyeccion)
    diagnostico = proyeccion.get("diagnostico_residuos") or {}
    alertas = diagnostico.get("alertas") or []
    rmse = metricas.get("rmse")
    mae = metricas.get("mae")
    filas = [
        ("Backtesting walk-forward", _resumen_iteraciones(backtesting.get("iteraciones")), "Desempeño fuera de muestra por horizonte."),
        ("RMSE", _fmt_num(rmse, 4), "Penaliza con mayor fuerza los errores grandes."),
        ("MAE", _fmt_num(mae, 4), "Error absoluto promedio en unidades del índice."),
        ("MAPE", formatear_porcentaje(metricas.get("mape")), "Error porcentual absoluto medio."),
        ("sMAPE", formatear_porcentaje(metricas.get("smape")), "Error porcentual simétrico."),
        ("MASE", _fmt_num(metricas.get("mase"), 4), "Señal auxiliar frente a la escala naive in-sample."),
        ("Comparación con Naive", _ratios_benchmark(comparacion, "naive"), _interpretar_benchmark(comparacion, "naive")),
        ("Comparación con Drift", _ratios_benchmark(comparacion, "drift"), _interpretar_benchmark(comparacion, "drift")),
        ("Sesgo medio", _fmt_num(metricas.get("sesgo_medio", metricas.get("error_medio")), 4), _interpretar_sesgo(metricas.get("sesgo_medio", metricas.get("error_medio")))),
        ("Estabilidad del error", _fmt_num(metricas.get("estabilidad_error"), 4), _interpretar_estabilidad(metricas.get("estabilidad_error"))),
        ("Errores inusuales de backtesting", _texto_errores_extremos(metricas), _lectura_errores_extremos(metricas)),
        # P0-C RUTA C2: intervalo retirado de las salidas

        ("Diagnóstico residual", f"{len(alertas)} alerta(s)" if alertas else "Sin alertas críticas", _resumir("; ".join(str(a) for a in alertas), 120) if alertas else "Diagnóstico complementario; no sustituye backtesting."),
        ("Razón final de selección", _resumir(proyeccion.get("justificacion_modelo") or proyeccion.get("criterio_seleccion"), 180), "Selección basada en evidencia fuera de muestra, parsimonia y trazabilidad."),
    ]
    return _tabla_tres_columnas("Criterios de selección del modelo", filas)


def _tabla_modelos(proyeccion: dict[str, Any]) -> str:
    catalogo = proyeccion.get("catalogo_modelos") or (proyeccion.get("stats") or {}).get("catalogo_modelos") or []
    candidatos = catalogo or (proyeccion.get("stats") or {}).get("all_candidates") or []
    if not candidatos:
        return ""
    normalizados = []
    for item in candidatos[:16]:
        normalizados.append(
            {
                "modelo": item.get("modelo") or item.get("name") or item.get("nombre"),
                "ejecutado": item.get("ejecutado", "Si" if not item.get("error") else "No"),
                "rmse": item.get("rmse", item.get("rmse_backtesting")),
                "mae": item.get("mae", item.get("mae_backtesting")),
                "mape": item.get("mape", item.get("mape_backtesting")),
                "estado": item.get("estado", "Descartado" if item.get("no_recomendado") else "Evaluado"),
                "razon": _resumir(item.get("razon") or item.get("error") or "Evaluado por backtesting.", 88),
            }
        )
    columnas = [
        ("modelo", "Modelo", "texto"),
        ("ejecutado", "Ejecutado", "texto"),
        ("rmse", "RMSE", "decimal"),
        ("mae", "MAE", "decimal"),
        ("mape", "MAPE", "porcentaje"),
        ("estado", "Estado", "texto"),
        ("razon", "Razon", "texto"),
    ]
    return _tabla_registros("Modelos evaluados", normalizados, columnas, clase="detalle")


def _tabla_evaluacion_horizontes(proyeccion: dict[str, Any]) -> str:
    evaluaciones = _analisis_horizontes(proyeccion).get("tabla_horizontes") or []
    if not evaluaciones:
        return ""
    filas = []
    for item in evaluaciones:
        ganador = item.get("modelo_evaluado") or item.get("modelo")
        filas.append(
            {
                "horizonte": item.get("horizonte"),
                "estado": item.get("estado"),
                "decision": item.get("decision"),
                "modelo": item.get("modelo_final_aplicado") or ganador,
                "rmse": item.get("rmse"),
                "mae": item.get("mae"),
                "mape": item.get("mape"),
                "smape": item.get("smape"),
                "mase": item.get("mase"),
                "ic95": None,  # P0-C RUTA C2: intervalo retirado de las salidas
                "iteraciones": item.get("iteraciones"),
            }
        )
    columnas = [
        ("horizonte", "h", "texto"),
        ("estado", "Estado", "texto"),
        ("decision", "Decisión", "texto"),
        ("modelo", "Modelo", "texto"),
        ("rmse", "RMSE", "decimal"),
        ("mae", "MAE", "decimal"),
        ("mape", "MAPE", "porcentaje"),
        ("smape", "sMAPE", "porcentaje"),
        ("mase", "MASE", "decimal"),
        # P0-C RUTA C2: el intervalo se retira de las salidas; el calculo interno se conserva como diagnostico
        ("iteraciones", "Iter.", "texto"),
        ("horizonte", "Ver detalle", "detalle"),
    ]
    return _tabla_registros(
        "Evaluación completa por horizonte",
        filas,
        columnas,
        clase="detalle",
        clase_tabla="tabla-horizontes",
        nota="Seleccione «Ver detalle» para consultar razones, advertencias y criterios técnicos.",
    )


def _tabla_proyecciones(proyeccion: dict[str, Any]) -> str:
    df = proyeccion.get("proyecciones")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    registros = []
    for fila in df.tail(18).to_dict("records"):
        registros.append(
            {
                **fila,
                "periodo_visible": _formatear_periodo(fila.get("periodo")),
                "ic95": "no publicado",  # P0-C RUTA C2: intervalo retirado de las salidas
            }
        )
    columnas = [
        ("periodo_visible", "Período", "texto"),
        ("indice_proyectado", "Índice", "indice"),
        ("factor_actualizacion", "Factor", "factor"),
        ("variacion_acumulada_pct", "Variación", "porcentaje"),
        # P0-C RUTA C2: el intervalo no se publica; su tipificacion y cobertura son diagnostico interno
    ]
    return _tabla_registros("Tabla de proyecciones", registros, columnas)


def _bloque_advertencias(proyeccion: dict[str, Any]) -> str:
    categorias = proyeccion.get("advertencias_categorizadas") or {}
    factibilidad = proyeccion.get("factibilidad") or {}
    grupos = [
        ("Datos", categorias.get("advertencias_datos") or []),
        ("Modelo seleccionado", categorias.get("advertencias_modelo_seleccionado") or []),
        ("Horizonte solicitado", categorias.get("advertencias_horizonte") or []),
        ("Intervalo", categorias.get("advertencias_intervalo") or []),
        ("Factibilidad global", categorias.get("advertencias_factibilidad_global") or factibilidad.get("advertencias") or []),
    ]
    contenido = []
    for titulo, items in grupos:
        limpios = [_resumir(item, 220) for item in items if valor_o_no_disponible(item) != NO_DISPONIBLE]
        if limpios:
            contenido.append(
                f"<div class='advertencia-grupo'><h3>{escape(titulo)}</h3>"
                + "".join(f"<p>{escape(item)}</p>" for item in limpios[:5])
                + "</div>"
            )
    if not contenido:
        return "<section class='bloque advertencias ok'><h2>Advertencias principales</h2><p>No se registran advertencias principales para el resultado mostrado.</p></section>"
    return "<section class='bloque advertencias'><h2>Advertencias principales</h2>" + "".join(contenido) + "</section>"


def _bloque_salvaguarda_benchmark(proyeccion: dict[str, Any]) -> str:
    """Informa el resultado diagnóstico de reevaluar Drift y Naive ante un horizonte no recomendable.

    H-2, 18-08-2026 (auditoria final V-CODEX-R2). El docstring y el texto de
    este bloque afirmaban una sustitucion que la funcion que los alimenta
    (`_aplicar_salvaguarda_benchmarks`) no realiza desde el CIERRE 08-08-2026:
    devuelve siempre el mismo modelo y el mismo horizonte, sin cambiarlos.
    `salvaguarda["activada"]` nunca pasa a `True` en el codigo vigente -es un
    campo heredado de la conducta retirada-, de modo que la rama que aqui
    existia para "activada=True" era inalcanzable, y la rama que SI se
    ejecutaba siempre afirmaba "los benchmarks tampoco los cumplieron" sin
    comprobar si algun benchmark si habia ampliado el alcance. Reescrito para
    describir la conducta real: diagnostico que no sustituye nada.
    """
    salvaguarda = proyeccion.get("salvaguarda_benchmark") or {}
    if not salvaguarda.get("intentada"):
        return ""
    filas = [
        ("Modelo principal (sin cambios)", salvaguarda.get("modelo_principal"), ""),
        ("Motivo del horizonte no recomendable", _resumir(salvaguarda.get("razon_fallo_principal"), 220), ""),
        ("Horizonte máximo admisible del modelo principal", salvaguarda.get("h_max_antes"), ""),
    ]
    for item in salvaguarda.get("benchmarks_evaluados") or []:
        estado = "amplía el alcance" if item.get("cumple") else "no amplía el alcance"
        filas.append(
            (
                f"Benchmark {item.get('nombre')}",
                f"{estado}; RMSE relativo ponderado {_fmt_num(item.get('rmse_ponderado'), 2)}; "
                f"horizonte admisible {item.get('h_max_admisible')}",
                "",
            )
        )
    habria_ampliado = bool(salvaguarda.get("benchmark_habria_ampliado"))
    nota = (
        "El modelo principal no fue recomendable en algún horizonte. Se reevaluaron los benchmarks "
        "Drift y Naive como referencia diagnóstica; "
        + (
            "al menos uno alcanzaría un horizonte mayor, pero esto no sustituye el modelo entregado: "
            "el modelo publicado sigue siendo el de la selección por RMSE fuera de muestra."
            if habria_ampliado
            else "ninguno alcanzaría un horizonte mayor que el modelo principal."
        )
    )
    return _tabla_clave_valor("Salvaguarda con benchmarks (diagnóstico)", filas, nota=nota)


def _bloque_ajuste_calendario(proyeccion: dict[str, Any]) -> str:
    """Muestra el patron de cambio de anio solo cuando la serie lo presenta."""
    traza = proyeccion.get("ajuste_calendario") or {}
    if not traza.get("hay_evidencia_calendario"):
        return ""
    validacion = traza.get("validacion_backtesting") or {}
    aplicado = bool(traza.get("ajuste_calendario_aplicado"))
    filas = [
        ("Estado", traza.get("estado_calendario_visible") or NO_APLICA, ""),
        ("Patrón detectado en la serie", "Si" if traza.get("patron_detectado_en_serie") else "No", ""),
        ("Efecto dentro del horizonte solicitado",
         "Si" if traza.get("efecto_en_horizonte_solicitado") else "No", ""),
        ("Ajuste aplicado a la proyección", "Si" if aplicado else "No", ""),
        ("Transiciones diciembre-enero", traza.get("transiciones_diciembre_enero"), ""),
        ("Salto mediano de cambio de anio", _fmt_pct(traza.get("salto_mediano_pct")), ""),
        ("Movimiento mensual tipico", _fmt_pct(traza.get("movimiento_mensual_tipico_pct")), ""),
        ("Razón salto / movimiento", _fmt_num(traza.get("ratio_salto_movimiento"), 2), ""),
        ("Eneros dentro del horizonte", traza.get("eneros_en_horizonte"), ""),
    ]
    if validacion.get("evaluado"):
        filas.extend(
            [
                ("Ventanas de validación", validacion.get("ventanas"), ""),
                ("Mejora en MAE", _fmt_pct(validacion.get("mejora_mae")), ""),
                ("Mejora en RMSE", _fmt_pct(validacion.get("mejora_rmse")), ""),
            ]
        )
    return _tabla_clave_valor(
        "Patron de cambio de anio",
        filas,
        nota=str(traza.get("mensaje") or ""),
        clase="calendario" if aplicado else "calendario advertencia",
    )


def _fmt_pct(valor: Any) -> str:
    """Formatea un porcentaje ya expresado en unidades de porcentaje."""
    texto = _fmt_num(valor, 2)
    return f"{texto} %" if texto not in ("", "No disponible") else texto


def _detalle_tecnico(proyeccion: dict[str, Any]) -> str:
    stats = proyeccion.get("stats") or {}
    filas = [
        ("R2", _fmt_num(stats.get("r2"), 4), ""),
        ("R2 ajustado", _fmt_num(stats.get("r2_ajustado"), 4), ""),
        ("AIC", _fmt_num(stats.get("aic"), 4), ""),
        ("AICc", _fmt_num(stats.get("aicc"), 4), ""),
        ("Durbin-Watson", _fmt_num(stats.get("durbin_watson"), 4), ""),
        ("Jarque-Bera p-value", _fmt_num(stats.get("jb_p"), 4), ""),
    ]
    # D-7: contrastes formales de media residual y heterocedasticidad.
    diagnostico = proyeccion.get("diagnostico_residuos") or {}
    filas.extend(_filas_contraste_ui(diagnostico.get("media_residual") or {}, "Media residual = 0"))
    filas.extend(_filas_contraste_ui(diagnostico.get("heterocedasticidad") or {}, "Breusch-Pagan"))
    return _tabla_clave_valor("Detalle técnico", filas, clase="detalle")


def _filas_contraste_ui(contraste: dict[str, Any], etiqueta: str) -> list[tuple[str, str, str]]:
    """Estadístico, grados de libertad y valor p; o el motivo de no calculable."""
    if not contraste:
        return []
    if not contraste.get("calculable"):
        return [(etiqueta, "No calculable", "")]
    return [
        (f"{etiqueta} estadístico", _fmt_num(contraste.get("estadistico"), 4), ""),
        (f"{etiqueta} gl", str(contraste.get("grados_libertad")), ""),
        (f"{etiqueta} valor p", _fmt_num(contraste.get("p_value"), 4), ""),
    ]


def _tabla_clave_valor(
    titulo: str,
    filas: list[tuple[str, Any, str]],
    *,
    nota: str = "",
    clase: str = "",
) -> str:
    cuerpo = "".join(
        f"<tr class='{escape(clase_fila)}'><th>{escape(etiqueta)}</th><td>{escape(valor_o_no_disponible(valor))}</td></tr>"
        for etiqueta, valor, clase_fila in filas
    )
    nota_html = f"<p class='nota'>{escape(nota)}</p>" if nota else ""
    return (
        f"<section class='bloque {escape(clase)}'>"
        f"<h2>{escape(titulo)}</h2>"
        "<table class='kv'><thead><tr><th>Campo</th><th>Valor</th></tr></thead>"
        f"<tbody>{cuerpo}</tbody></table>{nota_html}</section>"
    )


def _tabla_tres_columnas(titulo: str, filas: list[tuple[str, Any, Any]]) -> str:
    cuerpo = "".join(
        "<tr>"
        f"<th>{escape(criterio)}</th>"
        f"<td>{escape(valor_o_no_disponible(resultado))}</td>"
        f"<td>{escape(valor_o_no_disponible(interpretacion))}</td>"
        "</tr>"
        for criterio, resultado, interpretacion in filas
    )
    return (
        "<section class='bloque'>"
        f"<h2>{escape(titulo)}</h2>"
        "<table class='criterios'><thead><tr><th>Criterio</th><th>Resultado</th><th>Interpretación</th></tr></thead>"
        f"<tbody>{cuerpo}</tbody></table></section>"
    )


def _tabla_registros(
    titulo: str,
    registros: list[dict[str, Any]],
    columnas: list[tuple[str, str, str]],
    *,
    clase: str = "",
    clase_tabla: str = "",
    nota: str = "",
) -> str:
    encabezado = "".join(f"<th>{escape(titulo_col)}</th>" for _, titulo_col, _ in columnas)
    filas = []
    for item in registros:
        celdas = []
        for campo, _, formato in columnas:
            valor = _formatear_por_tipo(item.get(campo), formato)
            clase_num = " class='número'" if formato in {"decimal", "indice", "factor", "porcentaje", "ratio"} else ""
            if formato == "detalle":
                horizonte = _entero(item.get(campo))
                contenido = (
                    f"<a href='detalle-horizonte:{horizonte}'>Ver detalle</a>"
                    if horizonte is not None
                    else NO_DISPONIBLE
                )
            else:
                contenido = escape(valor)
            celdas.append(f"<td{clase_num}>{contenido}</td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    nota_html = f"<p class='nota'>{escape(nota)}</p>" if nota else ""
    return (
        f"<section class='bloque {escape(clase)}'>"
        f"<h2>{escape(titulo)}</h2>"
        "<div class='tabla-contenedor'>"
        f"<table class='{escape(clase_tabla)}'><thead><tr>{encabezado}</tr></thead><tbody>{''.join(filas)}</tbody></table>"
        f"</div>{nota_html}</section>"
    )


def _comparacion_modelo_seleccionado(proyeccion: dict[str, Any]) -> dict[str, Any]:
    stats = proyeccion.get("stats") or {}
    candidatos = stats.get("all_candidates") or []
    codigo = proyeccion.get("modelo_codigo")
    visible = proyeccion.get("model_name")
    for item in candidatos:
        if (
            item.get("nombre") == codigo
            or item.get("name") == visible
            or item.get("modelo") == visible
        ):
            return item
    return {}


def _ratios_benchmark(comparacion: dict[str, Any], benchmark: str) -> str:
    rrmse = _fmt_num(comparacion.get(f"rrmse_{benchmark}"), 4)
    rmae = _fmt_num(comparacion.get(f"rmae_{benchmark}"), 4)
    if rrmse == NO_DISPONIBLE and rmae == NO_DISPONIBLE:
        return NO_DISPONIBLE
    return f"rRMSE={rrmse}; rMAE={rmae}"


def _interpretar_benchmark(comparacion: dict[str, Any], benchmark: str) -> str:
    ratios = [
        _numero(comparacion.get(f"rrmse_{benchmark}")),
        _numero(comparacion.get(f"rmae_{benchmark}")),
    ]
    validos = [ratio for ratio in ratios if ratio is not None]
    if not validos:
        return "No disponible para este horizonte."
    if all(ratio < 1.0 for ratio in validos):
        return f"Mejora al benchmark {benchmark.capitalize()}."
    if any(ratio <= 1.05 for ratio in validos):
        return f"Desempeño comparable con {benchmark.capitalize()}."
    return f"No mejora al benchmark {benchmark.capitalize()}."


def _texto_errores_extremos(metricas: dict[str, Any]) -> str:
    """Cantidad y proporcion de errores inusuales; sin veredicto (D-8)."""
    detalle = metricas.get("errores_extremos") or {}
    if not detalle.get("calculable"):
        return NO_DISPONIBLE
    return (
        f"{_fmt_entero(detalle.get('cantidad'))} de {_fmt_entero(detalle.get('n'))} "
        f"({formatear_porcentaje(detalle.get('proporcion'))})"
    )


def _lectura_errores_extremos(metricas: dict[str, Any]) -> str:
    """Explica el criterio y su alcance, sin convertirlo en decision (D-8)."""
    detalle = metricas.get("errores_extremos") or {}
    if not detalle.get("calculable"):
        return str(detalle.get("motivo") or "Detección no calculable para esta serie.")
    return (
        f"Ventanas con puntaje z modificado |M| > {_fmt_num(detalle.get('umbral_z'), 1)} "
        "(Iglewicz y Hoaglin, 1993). Dato descriptivo: no modifica el modelo, el pronóstico, "
        "el intervalo ni el horizonte."
    )


def _interpretar_sesgo(valor: Any) -> str:
    numero = _numero(valor)
    if numero is None:
        return NO_DISPONIBLE
    if abs(numero) < 1e-9:
        return "Sin sesgo medio apreciable."
    return "Subestima en promedio." if numero > 0 else "Sobreestima en promedio."


def _interpretar_estabilidad(valor: Any) -> str:
    numero = _numero(valor)
    if numero is None:
        return NO_DISPONIBLE
    if numero <= 0.35:
        return "Errores relativamente estables."
    if numero <= 0.75:
        return "Estabilidad moderada."
    return "Errores inestables entre ventanas."


def _nombre_metodo_intervalo(valor: Any) -> str:
    texto = valor_o_no_disponible(valor)
    bajo = texto.lower()
    if "cuantil" in bajo and "student" in bajo:
        return "Cuantil empírico corregido / t de Student, errores OOS del horizonte"
    if "cuantil" in bajo:
        return "Cuantil empírico corregido sobre errores OOS del horizonte"
    if "student" in bajo:
        return "Predicción t de Student sobre errores OOS del horizonte"
    return _resumir(texto, 80)


def _fuente_errores_intervalo(valor: Any) -> str:
    texto = valor_o_no_disponible(valor).lower()
    if "horizonte" in texto and ("oos" in texto or "errores" in texto):
        return "Errores OOS de backtesting del horizonte exacto"
    if "out-of-sample" in texto or "oos" in texto or "backtesting" in texto:
        return "Errores OOS de backtesting"
    return NO_DISPONIBLE


def _ultima_fila(df: Any) -> dict[str, Any]:
    if isinstance(df, pd.DataFrame) and not df.empty:
        return dict(df.iloc[-1])
    return {}


def _numero(valor: Any) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _es_valor_nulo(valor: Any) -> bool:
    if valor is None:
        return True
    if isinstance(valor, (dict, list, tuple, set)):
        return False
    try:
        resultado = pd.isna(valor)
    except (TypeError, ValueError):
        return False
    try:
        return bool(resultado)
    except (TypeError, ValueError):
        return False


def _entero(valor: Any) -> int | None:
    numero = _numero(valor)
    return int(numero) if numero is not None else None


def _fmt_num(valor: Any, decimales: int = 4) -> str:
    numero = _numero(valor)
    return f"{numero:.{decimales}f}" if numero is not None else NO_DISPONIBLE


def _fmt_entero(valor: Any) -> str:
    numero = _entero(valor)
    return str(numero) if numero is not None else NO_DISPONIBLE


def _fmt_parametro(valor: Any) -> str:
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return _fmt_num(valor, 6)
    if isinstance(valor, (list, tuple)):
        return ", ".join(_fmt_parametro(item) for item in valor)
    return valor_o_no_disponible(valor)


def _formatear_por_tipo(valor: Any, formato: str) -> str:
    if formato == "indice":
        return formatear_indice(valor)
    if formato == "factor":
        return formatear_factor(valor)
    if formato == "porcentaje":
        return formatear_porcentaje(valor)
    if formato == "ratio":
        return formatear_porcentaje(valor, es_ratio=True)
    if formato == "decimal":
        return _fmt_num(valor, 4)
    return valor_o_no_disponible(valor)


def _horizonte_no_viable(valor: Any) -> str:
    numero = _entero(valor)
    return formatear_horizonte(numero) if numero and numero > 0 else "No identificado en los horizontes evaluados"


def _resumen_horizontes(valores: Any) -> str:
    if not isinstance(valores, (list, tuple, set)):
        return NO_DISPONIBLE
    numeros = sorted({_entero(valor) for valor in valores if _entero(valor) is not None})
    if not numeros:
        return "Ninguno"
    if numeros == list(range(numeros[0], numeros[-1] + 1)):
        return f"h={numeros[0]} a h={numeros[-1]}"
    return ", ".join(f"h={numero}" for numero in numeros)


def _resumir(valor: Any, limite: int) -> str:
    texto = valor_o_no_disponible(valor)
    if texto == NO_DISPONIBLE:
        return texto
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 3].rstrip() + "..."


def _coalesce(*valores: Any) -> Any:
    for valor in valores:
        if not _es_valor_nulo(valor):
            return valor
    return None


def _texto_oracion(valor: Any) -> str:
    texto = valor_o_no_disponible(valor)
    if texto == NO_DISPONIBLE:
        return texto
    return texto[:1].upper() + texto[1:]


def _formatear_periodo(valor: Any) -> str:
    texto = valor_o_no_disponible(valor)
    if texto == NO_DISPONIBLE:
        return texto
    partes = texto.replace("-", "_").split("_")
    if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
        return f"{int(partes[0]):04d}-{int(partes[1]):02d}"
    return texto


def _resultado_solicitado(proyeccion: dict[str, Any]) -> dict[str, Any]:
    bloque = proyeccion.get("resultado_horizonte_solicitado")
    if isinstance(bloque, dict) and bloque:
        return bloque
    info = proyeccion.get("horizonte_info") or {}
    solicitado = _entero(_coalesce(proyeccion.get("horizonte_solicitado"), info.get("horizonte_solicitado")))
    permitido = _entero(_coalesce(proyeccion.get("horizonte_permitido"), info.get("horizonte_finalmente_permitido")))
    generado = bool(proyeccion.get("proyeccion_generada", True)) and solicitado == permitido
    accion_info = str(info.get("accion") or "").lower()
    escenario = generado and "escenario" in accion_info
    estado = "escenario" if escenario else "proyeccion_tecnica" if generado else "no_admisible"
    ultima = _ultima_fila(proyeccion.get("proyecciones"))
    return {
        "horizonte_solicitado": solicitado,
        "origen_horizonte": proyeccion.get("origen_horizonte", "predeterminado"),
        "estado": estado,
        "accion": "permitir como escenario" if escenario else "permitir" if generado else "negar",
        "proyeccion_generada": generado,
        "indice_proyectado": _coalesce(ultima.get("indice_proyectado"), proyeccion.get("y_proj")) if generado else None,
        "periodo_proyectado": _coalesce(ultima.get("periodo"), proyeccion.get("periodo_proj")) if generado else None,
        "modelo_aplicado": proyeccion.get("model_name") if generado else None,
        "ic95": [
            None, None,  # P0-C RUTA C2: intervalo retirado de las salidas
        ] if generado else None,
        "nivel_confianza": (proyeccion.get("factibilidad") or {}).get("nivel_confianza_metodologica"),
        "razon_principal": proyeccion.get("explicacion") or info.get("mensaje"),
    }


def _analisis_horizontes(proyeccion: dict[str, Any]) -> dict[str, Any]:
    info = proyeccion.get("analisis_horizontes_completo") or proyeccion.get("horizonte_info") or {}
    if "tabla_horizontes" not in info:
        info = {**info, "tabla_horizontes": info.get("evaluaciones") or []}
    return info


def _estado_solicitado_visible(valor: Any) -> str:
    # H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual). Se
    # retira la entrada "escenario": `_estructurar_resultado_horizontes` solo
    # fija `estado` en "proyeccion_tecnica" o "no_admisible" desde que se
    # elimino la rama equivalente (ver su comentario H-4 residual);
    # mantenerla aqui presentaba un estado inalcanzable como si fuera una
    # salida posible.
    return {
        "proyeccion_tecnica": "Proyección técnica",
        "no_admisible": "No admisible",
    }.get(str(valor), valor_o_no_disponible(valor))


def _proyeccion_restringida(proyeccion: dict[str, Any]) -> bool:
    info = proyeccion.get("horizonte_info") or {}
    solicitado = _entero(_coalesce(proyeccion.get("horizonte_solicitado"), info.get("horizonte_solicitado")))
    permitido = _entero(_coalesce(proyeccion.get("horizonte_permitido"), info.get("horizonte_finalmente_permitido")))
    return solicitado is not None and permitido is not None and solicitado > permitido


def _accion_horizonte(proyeccion: dict[str, Any], generado: bool) -> str:
    info = proyeccion.get("horizonte_info") or {}
    solicitado = _entero(_coalesce(proyeccion.get("horizonte_solicitado"), info.get("horizonte_solicitado")))
    permitido = _entero(_coalesce(proyeccion.get("horizonte_permitido"), info.get("horizonte_finalmente_permitido")))
    if solicitado is not None and permitido is not None and solicitado > permitido:
        if permitido > 0:
            return f"Restringir a {formatear_horizonte(permitido)}; se solicitaron {formatear_horizonte(solicitado)}"
        return f"No generar la proyección solicitada de {formatear_horizonte(solicitado)}"
    accion = valor_o_no_disponible(info.get("accion"))
    if accion != NO_DISPONIBLE:
        return _texto_oracion(accion)
    if not generado:
        return "No generar la proyección"
    return NO_DISPONIBLE


def _backtesting_relevante(proyeccion: dict[str, Any]) -> dict[str, Any]:
    backtesting = proyeccion.get("backtesting")
    if isinstance(backtesting, dict) and (backtesting.get("metricas") or backtesting.get("iteraciones") is not None):
        return backtesting
    info = proyeccion.get("horizonte_info") or {}
    objetivo = _entero(
        _coalesce(
            proyeccion.get("horizonte_permitido"),
            info.get("horizonte_finalmente_permitido"),
            proyeccion.get("horizonte_solicitado"),
        )
    )
    evaluaciones = info.get("evaluaciones") or []
    for evaluacion in evaluaciones:
        if objetivo is not None and _entero(evaluacion.get("horizonte")) != objetivo:
            continue
        candidato = evaluacion.get("backtesting")
        if isinstance(candidato, dict):
            return candidato
    return {}


def _resumen_iteraciones(valor: Any) -> str:
    numero = _entero(valor)
    if numero is None:
        return NO_EVALUADO
    return f"{numero} iteración" if numero == 1 else f"{numero} iteraciones"


def _estilos_html(tema: str = "claro") -> str:
    p = paleta_tema(tema)
    fondo_estado_ok = "#203126" if tema == "oscuro" else "#e7f6ec"
    fondo_estado_cautela = "#3a301d" if tema == "oscuro" else "#fff6df"
    fondo_estado_alerta = "#3a2425" if tema == "oscuro" else "#fdecec"
    fondo_alerta = "#332c1d" if tema == "oscuro" else "#fffaf0"
    return f"""
<style>
body{{background:{p["superficie_suave"]};color:{p["texto_principal"]};}}
.resultado-icociv{{font-family:'Segoe UI',Arial,sans-serif;color:{p["texto_principal"]};background:{p["superficie_suave"]};padding:16px;line-height:1.35;}}
.encabezado{{background:{p["fondo_secundario"]};border:1px solid {p["bordes"]};border-left:5px solid {p["acento"]};padding:16px;margin-bottom:14px;}}
.encabezado h1{{font-size:21px;margin:3px 0 7px;color:{p["texto_principal"]};}}
.encabezado p{{margin:0;color:{p["texto_secundario"]};}}
.eyebrow{{font-size:11px;font-weight:700;text-transform:uppercase;color:{p["acento"]};}}
.estado-linea{{margin-top:12px;padding-top:8px;border-top:1px solid {p["bordes"]};}}
.chip{{white-space:nowrap;padding:5px 8px;font-weight:700;font-size:11px;border:1px solid {p["bordes"]};}}
.confianza{{margin-left:12px;color:{p["texto_secundario"]};font-weight:600;}}
.estado-texto{{font-weight:700;color:{p["texto_secundario"]};}}
.estado-ok{{background:{fondo_estado_ok};color:{p["exito"]};border-color:{p["exito"]};}}
.estado-cautela{{background:{fondo_estado_cautela};color:{p["advertencia"]};border-color:{p["advertencia"]};}}
.estado-alerta{{background:{fondo_estado_alerta};color:{p["error"]};border-color:{p["error"]};}}
.bloque{{background:{p["fondo_secundario"]};border:1px solid {p["bordes"]};padding:13px;margin:12px 0;}}
.bloque.principal{{border-top:4px solid {p["acento"]};}}
.bloque h2{{font-size:15px;margin:0 0 9px;color:{p["texto_principal"]};}}
.nota{{color:{p["texto_secundario"]};font-size:11px;margin:8px 0 0;}}
.tabla-contenedor{{width:100%;overflow-x:auto;}}
table{{width:100%;border-collapse:collapse;font-size:12px;background:{p["fondo_tabla"]};color:{p["texto_principal"]};}}
th,td{{border:1px solid {p["bordes"]};padding:7px 8px;text-align:left;vertical-align:top;white-space:normal;word-break:normal;}}
td{{background:{p["fondo_tabla"]};color:{p["texto_principal"]};}}
thead th,.kv th,.criterios th{{background:{p["encabezado_tabla"]};color:{p["texto_encabezado"]};font-weight:700;}}
.kv,.criterios{{table-layout:fixed;}}
.kv th:first-child{{width:38%;}}
.kv td{{width:62%;}}
.kv tr.destacado td{{font-size:18px;font-weight:800;color:{p["acento"]};background:{p["superficie_suave"]};}}
.kv tr.alerta th,.kv tr.alerta td{{background:{fondo_alerta};color:{p["advertencia"]};}}
.criterios th:nth-child(1){{width:25%;}}
.criterios th:nth-child(2){{width:25%;}}
.criterios th:nth-child(3){{width:50%;}}
tbody tr:nth-child(even),tbody tr:nth-child(even) td{{background:{p["superficie_suave"]};}}
td.numero{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}}
.tabla-horizontes{{min-width:1120px;table-layout:auto;}}
.tabla-horizontes th,.tabla-horizontes td{{white-space:nowrap;}}
a{{color:{p["acento"]};font-weight:700;text-decoration:none;}}
.advertencias{{border-left:5px solid {p["advertencia"]};}}
.advertencias.ok{{border-left-color:{p["exito"]};}}
.advertencia-grupo{{background:{fondo_alerta};border:1px solid {p["advertencia"]};padding:8px;margin:7px 0;}}
.advertencia-grupo h3{{font-size:12px;margin:0 0 4px;color:{p["advertencia"]};}}
.advertencia-grupo p{{margin:3px 0;color:{p["texto_secundario"]};}}
.detalle{{margin-top:16px;}}
</style>
"""
