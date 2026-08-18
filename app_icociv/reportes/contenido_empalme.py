"""Contenido del informe de actualización de precios ICCP–ICOCIV.

Cada cálculo del módulo de empalme se documenta con la fórmula general, la
sustitución numérica y el resultado, para que un tercero pueda rehacer la
cuenta a mano. Mostrar solo la ecuación abstracta no sirve para revisar un
ajuste contractual.

Este módulo no recalcula nada: los valores vienen resueltos por
``app_icociv.servicios.empalme_iccp_icociv``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app_icociv.config.rutas import VERSION
from app_icociv.reportes.modelo import (
    Aviso,
    ConfiguracionInforme,
    Ficha,
    Firmas,
    Formula,
    Informe,
    NOMBRE_COMPLETO,
    Parrafo,
    Portada,
    Seccion,
    Tabla,
    es_numero,
    fecha_hora_larga,
    formato_indice,
    formato_moneda,
    formato_porcentaje,
    identificador_informe,
    periodo_largo,
    texto_o,
)


PERIODO_TRANSICION_VISIBLE = "diciembre de 2021"

ADVERTENCIAS_CONTRACTUALES = (
    "Los índices ICOCIV proyectados por SAVIP son informativos y no sustituyen el índice oficial del DANE.",
    "El ajuste definitivo debe calcularse con los índices oficiales efectivamente publicados.",
    "El índice base I0 debe corresponder al contrato o al acuerdo entre las partes.",
    "La equivalencia ICCP–ICOCIV es una selección técnica manual y requiere criterio del profesional responsable.",
    "SAVIP no reemplaza la validación jurídica, contractual ni financiera del ajuste.",
)

CASOS_VISIBLES = {
    "solo_iccp": f"Solo ICCP (ambas fechas hasta {PERIODO_TRANSICION_VISIBLE})",
    "solo_icociv": f"Solo ICOCIV (ambas fechas posteriores a {PERIODO_TRANSICION_VISIBLE})",
    "empalme_completo": f"Empalme completo (el periodo cruza {PERIODO_TRANSICION_VISIBLE})",
}


def _insumo(calculo: dict[str, Any]) -> str:
    return texto_o(calculo.get("item") or calculo.get("insumo") or calculo.get("codigo_item"), "Sin insumo")


def _tipo_dato_icociv(calculo: dict[str, Any]) -> str:
    """Diferencia índice oficial observado de índice proyectado por SAVIP (§7.2)."""
    return "Índice proyectado por SAVIP" if calculo.get("icociv_final_es_proyectado") else "Índice oficial observado"


def _seccion_datos_generales(generales: dict[str, str], config: ConfiguracionInforme, calculos: list[dict[str, Any]]) -> Seccion:
    institucional = dict(config.institucional.pares())
    filas: list[tuple[str, str]] = []
    for etiqueta, clave in (
        ("Entidad", "entidad"), ("Dependencia", "dependencia"), ("Proyecto", "proyecto"),
        ("Contrato", "contrato"), ("Objeto", "objeto"), ("Contratista", "contratista"),
        ("Supervisor", "supervisor"), ("Interventor", "interventor"), ("Responsable del informe", "responsable"),
    ):
        valor = institucional.get(etiqueta) or generales.get(clave) or ""
        if valor:
            filas.append((etiqueta, valor))
    if not filas and generales.get("contrato"):
        filas.append(("Contrato", generales["contrato"]))
    if generales.get("objeto_contrato") and not any(e == "Objeto" for e, _ in filas):
        filas.append(("Objeto", generales["objeto_contrato"]))
    if generales.get("responsable_tecnico") and not any(e == "Responsable del informe" for e, _ in filas):
        filas.append(("Responsable técnico", generales["responsable_tecnico"]))

    if calculos:
        filas.append(("Periodo del ajuste", f"{periodo_largo(calculos[0].get('fecha_inicial'))} a {periodo_largo(calculos[-1].get('fecha_final'))}"))
        filas.append(("Ítems analizados", str(len(calculos))))
    total = sum(float(c["r_total"]) for c in calculos if es_numero(c.get("r_total")))
    base = sum(float(c["base_ajustable"]) for c in calculos if es_numero(c.get("base_ajustable")))
    actualizado = sum(float(c["valor_actualizado"]) for c in calculos if es_numero(c.get("valor_actualizado")))

    destacados = [
        ("Base ajustable total", formato_moneda(base, config.moneda)),
        ("Ajuste total (R)", formato_moneda(total, config.moneda)),
        ("Valor actualizado total", formato_moneda(actualizado, config.moneda)),
    ]
    bloques: list[Any] = [Ficha(filas, destacados=destacados)]
    observacion = generales.get("observacion_general") or config.institucional.observaciones
    if observacion:
        bloques.append(Parrafo(f"Observación general: {observacion}"))
    return Seccion("datos_generales", "Datos generales del ajuste", bloques)


def _seccion_indices(calculos: list[dict[str, Any]]) -> Seccion:
    filas: list[list[str]] = []
    for calculo in calculos:
        insumo = _insumo(calculo)
        candidatos = (
            ("I0 ICCP", "Índice ICCP del periodo base", calculo.get("i0_iccp"), calculo.get("fecha_inicial"),
             texto_o(calculo.get("ruta_iccp"), "ICCP histórico"), "Índice oficial observado"),
            ("I ICCP", "Índice ICCP del cierre del tramo ICCP", calculo.get("i_iccp"),
             calculo.get("fecha_final") if calculo.get("caso") == "solo_iccp" else "2021_12",
             texto_o(calculo.get("ruta_iccp"), "ICCP histórico"), "Índice oficial observado"),
            ("I0 ICOCIV", "Índice ICOCIV del periodo base del tramo ICOCIV", calculo.get("i0_icociv"),
             calculo.get("fecha_inicial") if calculo.get("caso") == "solo_icociv" else "2021_12",
             texto_o(calculo.get("ruta_icociv"), "ICOCIV"), "Índice oficial observado"),
            ("I ICOCIV", "Índice ICOCIV del periodo final", calculo.get("i_icociv"), calculo.get("fecha_final"),
             texto_o(calculo.get("ruta_icociv"), "ICOCIV"), _tipo_dato_icociv(calculo)),
        )
        for variable, descripcion, valor, periodo, fuente, tipo in candidatos:
            if not es_numero(valor):
                continue
            filas.append([
                f"{variable} · {insumo}" if len(calculos) > 1 else variable,
                descripcion, formato_indice(valor), periodo_largo(periodo), fuente, tipo,
            ])
    if not filas:
        return Seccion("indices", "Índices utilizados", [])
    return Seccion("indices", "Índices utilizados", [Tabla(
        encabezados=["Variable", "Descripción", "Valor", "Periodo", "Fuente", "Tipo de dato"],
        filas=filas,
        titulo="Índices que intervienen en el cálculo",
        nota="Los índices proyectados por SAVIP se identifican de forma explícita y no son publicación oficial.",
        fuente="ICCP histórico y anexos ICOCIV del DANE.",
        columnas_numericas=(2,),
        anchos=(2.6, 4.4, 2.0, 2.6, 3.4, 3.0),
    )])


def _seccion_seleccion_i0(calculos: list[dict[str, Any]]) -> Seccion:
    bloques: list[Any] = [Parrafo(
        "El índice base I0 fija el punto de partida del ajuste. Las fuentes metodológicas sugieren fechas "
        "determinadas —cierre de la licitación, acta de inicio o presentación de la oferta—, pero la fecha "
        "que se aplica puede depender de lo pactado en el contrato o del mutuo acuerdo entre la entidad y "
        "el contratista. La fecha registrada abajo es la que el usuario seleccionó en la aplicación."
    )]
    filas = [[
        _insumo(calculo),
        periodo_largo(calculo.get("fecha_inicial")),
        periodo_largo(calculo.get("fecha_final")),
        CASOS_VISIBLES.get(str(calculo.get("caso")), texto_o(calculo.get("caso"), "No determinado")),
        texto_o(calculo.get("observacion_tecnica"), "Sin observación registrada"),
    ] for calculo in calculos]
    if filas:
        bloques.append(Tabla(
            encabezados=["Ítem", "Fecha base (I0)", "Fecha final (I)", "Caso aplicado", "Criterio u observación"],
            filas=filas,
            titulo="Fechas seleccionadas y criterio registrado",
            anchos=(3.4, 2.8, 2.8, 4.0, 5.0),
        ))
    bloques.append(Aviso(
        "Sobre la elección de I0",
        [
            "La fecha base debe corresponder a la establecida en el contrato o al acuerdo entre las partes.",
            "Si el contrato no la fija, el acuerdo debe quedar documentado antes de aplicar el ajuste.",
        ],
        nivel="informacion",
    ))
    return Seccion("seleccion_i0", "Selección del índice base I0", bloques)


def _formulas_calculo(calculo: dict[str, Any], moneda: str) -> list[Any]:
    """Fórmula general, sustitución numérica y resultado de cada componente."""
    acero = calculo.get("tipo_calculo") == "Cálculo especial acero"
    base = calculo.get("base_ajustable")
    bloques: list[Any] = []

    if acero:
        bloques.append(Formula(
            etiqueta="Base del cálculo (acero)",
            general="Base = P0",
            sustitucion=[f"Base = {formato_moneda(calculo.get('p0'), moneda)}"],
            resultado=f"Base = {formato_moneda(base, moneda)}",
        ))
    else:
        bloques.append(Formula(
            etiqueta="Base ajustable",
            general="Base = P - A",
            sustitucion=[
                f"Base = {formato_moneda(calculo.get('precio_base'), moneda)}"
                f" - {formato_moneda(calculo.get('anticipo_amortizado'), moneda)}"
            ],
            resultado=f"Base = {formato_moneda(base, moneda)}",
        ))

    if es_numero(calculo.get("factor_iccp")):
        bloques.append(Formula(
            etiqueta="Ajuste del tramo ICCP (R1)",
            general="R1 = Base x [(I_ICCP / I0_ICCP) - 1]",
            sustitucion=[
                f"R1 = {formato_moneda(base, moneda)}",
                f"     x [({formato_indice(calculo.get('i_iccp'))} / {formato_indice(calculo.get('i0_iccp'))}) - 1]",
                f"     = {formato_moneda(base, moneda)} x {formato_indice(float(calculo['factor_iccp']) - 1.0, 6)}",
            ],
            resultado=f"R1 = {formato_moneda(calculo.get('r1'), moneda)}",
        ))
    else:
        bloques.append(Parrafo("No se aplica R1: el periodo analizado no incluye tramo ICCP."))

    if es_numero(calculo.get("factor_icociv")):
        bloques.append(Formula(
            etiqueta="Ajuste del tramo ICOCIV (R2)",
            general="R2 = (Base + R1) x [(I_ICOCIV / I0_ICOCIV) - 1]",
            sustitucion=[
                f"R2 = ({formato_moneda(base, moneda)} + {formato_moneda(calculo.get('r1'), moneda)})",
                f"     x [({formato_indice(calculo.get('i_icociv'))} / {formato_indice(calculo.get('i0_icociv'))}) - 1]",
                f"     = {formato_moneda(float(base or 0) + float(calculo.get('r1') or 0), moneda)}"
                f" x {formato_indice(float(calculo['factor_icociv']) - 1.0, 6)}",
            ],
            resultado=f"R2 = {formato_moneda(calculo.get('r2'), moneda)}",
        ))
    else:
        bloques.append(Parrafo("No se aplica R2: el periodo analizado no incluye tramo ICOCIV."))

    bloques.append(Formula(
        etiqueta="Ajuste total (R)",
        general="R = R1 + R2",
        sustitucion=[f"R = {formato_moneda(calculo.get('r1'), moneda)} + {formato_moneda(calculo.get('r2'), moneda)}"],
        resultado=f"R = {formato_moneda(calculo.get('r_total'), moneda)}",
    ))
    bloques.append(Formula(
        etiqueta="Valor actualizado",
        general="Valor actualizado = Base + R",
        sustitucion=[f"Valor actualizado = {formato_moneda(base, moneda)} + {formato_moneda(calculo.get('r_total'), moneda)}"],
        resultado=f"Valor actualizado = {formato_moneda(calculo.get('valor_actualizado'), moneda)}",
    ))

    if acero:
        if es_numero(calculo.get("z")):
            bloques.append(Formula(
                etiqueta="Valor adicional por fluctuación del acero (Z)",
                general="Z = (Ix x q) - (R + P0)",
                sustitucion=[
                    f"Z = ({formato_moneda(calculo.get('ix'), moneda)} x {formato_indice(calculo.get('q'))})",
                    f"    - ({formato_moneda(calculo.get('r_total'), moneda)} + {formato_moneda(calculo.get('p0'), moneda)})",
                ],
                resultado=f"Z = {formato_moneda(calculo.get('z'), moneda)}",
            ))
        else:
            bloques.append(Parrafo(texto_o(calculo.get("z_observacion"), "Para calcular Z deben registrarse Ix y q.")))
    return bloques


def _seccion_formulas(calculos: list[dict[str, Any]], moneda: str) -> Seccion:
    bloques: list[Any] = [Parrafo(
        "Cada componente se presenta con la fórmula general, la sustitución con los valores del caso y el "
        "resultado, de modo que el cálculo pueda verificarse sin la aplicación."
    )]
    for numero, calculo in enumerate(calculos, start=1):
        etiqueta = f"Ítem {numero}: {_insumo(calculo)}"
        detalle = (
            f"Unidad {texto_o(calculo.get('unidad'), 'no registrada')} · "
            f"{CASOS_VISIBLES.get(str(calculo.get('caso')), 'caso no determinado')} · "
            f"{periodo_largo(calculo.get('fecha_inicial'))} a {periodo_largo(calculo.get('fecha_final'))}"
        )
        bloques.append(Parrafo(etiqueta, enfasis=True))
        bloques.append(Parrafo(detalle))
        bloques.extend(_formulas_calculo(calculo, moneda))
    return Seccion("formulas", "Fórmulas y sustitución numérica", bloques)


def _seccion_resultados(calculos: list[dict[str, Any]], moneda: str) -> Seccion:
    filas = [[
        _insumo(calculo),
        texto_o(calculo.get("unidad"), ""),
        formato_moneda(calculo.get("base_ajustable"), moneda),
        formato_moneda(calculo.get("r1"), moneda),
        formato_moneda(calculo.get("r2"), moneda),
        formato_moneda(calculo.get("r_total"), moneda),
        formato_moneda(calculo.get("valor_actualizado"), moneda),
        formato_porcentaje(calculo.get("diferencia_porcentual")),
    ] for calculo in calculos]
    if not filas:
        return Seccion("resultados", "Resultados del ajuste", [])
    return Seccion("resultados", "Resultados del ajuste", [Tabla(
        encabezados=["Ítem", "Unidad", "Base ajustable", "R1", "R2", "Ajuste R", "Valor actualizado", "Variación"],
        filas=filas,
        titulo="Resultados parciales y valor actualizado por ítem",
        fuente="Cálculo de SAVIP con índices ICCP históricos e índices ICOCIV del DANE.",
        columnas_numericas=(2, 3, 4, 5, 6, 7),
        anchos=(3.2, 1.4, 2.6, 2.2, 2.2, 2.4, 2.8, 1.6),
    )])


def _seccion_advertencias(calculos: list[dict[str, Any]]) -> Seccion:
    propias: list[str] = []
    if any(c.get("icociv_final_es_proyectado") for c in calculos):
        propias.append(
            "Al menos un ítem usa un índice ICOCIV proyectado por SAVIP; ese resultado es informativo "
            "y debe recalcularse cuando el DANE publique el índice del periodo."
        )
    for calculo in calculos:
        if str(calculo.get("ruta_icociv") or "").count(" > ") < 2 and calculo.get("ruta_icociv"):
            propias.append(f"La ruta ICOCIV de «{_insumo(calculo)}» parece general; revise si el nivel es suficiente.")
            break
    for calculo in calculos:
        if calculo.get("tipo_calculo") == "Cálculo especial acero" and not es_numero(calculo.get("z")):
            propias.append(texto_o(calculo.get("z_observacion"), "El valor Z del acero no pudo calcularse."))
            break

    bloques: list[Any] = []
    if propias:
        bloques.append(Aviso("Advertencias de este cálculo", propias, nivel="advertencia"))
    bloques.append(Aviso("Advertencias contractuales", list(ADVERTENCIAS_CONTRACTUALES), nivel="informacion"))
    return Seccion("advertencias", "Advertencias contractuales", bloques)


def _seccion_trazabilidad(
    calculos: list[dict[str, Any]],
    identificador: str,
    config: ConfiguracionInforme,
    momento: datetime,
) -> Seccion:
    filas = [[
        texto_o(calculo.get("calculo_id") or calculo.get("numero_calculo") or numero, str(numero)),
        _insumo(calculo),
        texto_o(calculo.get("tipo_serie_iccp_visible"), "No aplica"),
        texto_o(calculo.get("serie_iccp"), "No aplica"),
        texto_o(calculo.get("ruta_icociv"), "No aplica"),
        _tipo_dato_icociv(calculo),
        texto_o(calculo.get("modelo_proyeccion"), "No aplica") if calculo.get("icociv_final_es_proyectado") else "No aplica",
    ] for numero, calculo in enumerate(calculos, start=1)]

    bloques: list[Any] = [Tabla(
        encabezados=["ID", "Ítem", "Tipo de serie ICCP", "Serie ICCP", "Ruta ICOCIV", "Origen de I ICOCIV", "Modelo"],
        filas=filas,
        titulo="Trazabilidad por ítem",
        columnas_numericas=(),
        anchos=(1.0, 2.8, 2.4, 2.6, 3.6, 2.6, 2.0),
    )]
    bloques.append(Tabla(
        encabezados=["Elemento", "Valor"],
        filas=[
            ["Identificador del informe", identificador],
            ["Versión de SAVIP", VERSION],
            ["Fecha de generación", fecha_hora_larga(momento)],
            ["Fuente ICCP", "Anexo histórico ICCP incorporado en la aplicación"],
            ["Periodo de transición ICCP a ICOCIV", PERIODO_TRANSICION_VISIBLE],
            ["Moneda", config.moneda],
        ],
        titulo="Trazabilidad del informe",
        anchos=(5.0, 10.4),
    ))
    if config.institucional.incluir_firmas:
        bloques.append(Firmas(["Elaboró", "Revisó", "Aprobó"]))
    return Seccion("trazabilidad", "Trazabilidad", bloques)


def _seccion_resumen(calculos: list[dict[str, Any]], generales: dict[str, str], moneda: str) -> Seccion:
    if not calculos:
        return Seccion("resumen", "Resumen ejecutivo", [])
    base = sum(float(c["base_ajustable"]) for c in calculos if es_numero(c.get("base_ajustable")))
    total = sum(float(c["r_total"]) for c in calculos if es_numero(c.get("r_total")))
    actualizado = base + total
    variacion = (total / base * 100.0) if base else float("nan")
    casos = {CASOS_VISIBLES.get(str(c.get("caso")), "caso no determinado") for c in calculos}
    proyectados = sum(1 for c in calculos if c.get("icociv_final_es_proyectado"))

    parrafos = [
        f"Se calculó la actualización de precios de {len(calculos)} ítem(s) del contrato "
        f"{texto_o(generales.get('contrato'), 'sin identificar')}, entre "
        f"{periodo_largo(calculos[0].get('fecha_inicial'))} y {periodo_largo(calculos[-1].get('fecha_final'))}.",
        f"Sobre una base ajustable de {formato_moneda(base, moneda)}, el ajuste total asciende a "
        f"{formato_moneda(total, moneda)}, lo que lleva el valor actualizado a "
        f"{formato_moneda(actualizado, moneda)}"
        + (f" y representa una variación de {formato_porcentaje(variacion)}." if es_numero(variacion) else "."),
        "Metodología aplicada: " + ", ".join(sorted(casos)) + ".",
    ]
    if proyectados:
        parrafos.append(
            f"{proyectados} de los {len(calculos)} ítems emplean un índice ICOCIV proyectado por SAVIP. "
            "Ese componente del ajuste es informativo y debe recalcularse con el índice oficial publicado."
        )
    else:
        parrafos.append("Todos los índices utilizados corresponden a publicaciones oficiales observadas.")
    return Seccion("resumen", "Resumen ejecutivo", [Parrafo(p) for p in parrafos])


def _portada(
    generales: dict[str, str],
    calculos: list[dict[str, Any]],
    config: ConfiguracionInforme,
    identificador: str,
    momento: datetime,
) -> Portada:
    filas: list[tuple[str, str]] = [
        ("Tipo de análisis", "Actualización de precios con empalme ICCP–ICOCIV"),
        ("Ítems analizados", str(len(calculos))),
    ]
    if calculos:
        filas.append(("Periodo del ajuste", f"{periodo_largo(calculos[0].get('fecha_inicial'))} a {periodo_largo(calculos[-1].get('fecha_final'))}"))
    filas += [
        ("Fecha y hora de generación", fecha_hora_larga(momento)),
        ("Versión de SAVIP", VERSION),
        ("Identificador del informe", identificador),
    ]
    institucional = config.institucional.pares()
    filas.extend(institucional)
    if not any(e == "Contrato" for e, _ in institucional) and generales.get("contrato"):
        filas.append(("Contrato", generales["contrato"]))
    if not any(e == "Objeto" for e, _ in institucional) and generales.get("objeto_contrato"):
        filas.append(("Objeto", generales["objeto_contrato"]))
    return Portada(
        titulo=config.titulo_documento(),
        subtitulo=NOMBRE_COMPLETO,
        filas=filas,
        observaciones=(config.institucional.observaciones or generales.get("observacion_general") or "").strip(),
        logo=config.institucional.logo,
    )


def construir_informe_empalme(
    calculos: list[dict[str, Any]],
    generales: dict[str, str] | None = None,
    config: ConfiguracionInforme | None = None,
    momento: datetime | None = None,
) -> Informe:
    """Arma el informe de ajuste ICCP–ICOCIV a partir de los cálculos del módulo."""
    config = config or ConfiguracionInforme.desde_tipo("empalme")
    generales = generales or {}
    momento = momento or datetime.now()
    identificador = identificador_informe(momento)
    calculos = [c for c in calculos if isinstance(c, dict)]

    candidatas: list[Seccion] = [
        _seccion_resumen(calculos, generales, config.moneda),
        _seccion_datos_generales(generales, config, calculos),
        _seccion_indices(calculos),
        _seccion_seleccion_i0(calculos),
        _seccion_formulas(calculos, config.moneda),
        _seccion_resultados(calculos, config.moneda),
        _seccion_advertencias(calculos),
        _seccion_trazabilidad(calculos, identificador, config, momento),
    ]
    return Informe(
        portada=_portada(generales, calculos, config, identificador, momento) if config.incluye("portada") else None,
        secciones=[s for s in candidatas if not s.vacia()],
        identificador=identificador,
        tipo="empalme",
        generado=momento,
        pie=f"{NOMBRE_COMPLETO} · versión {VERSION} · {identificador}",
    )
