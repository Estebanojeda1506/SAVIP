"""Renderizado de un :class:`Informe` a PDF de consulta y archivo.

El PDF no es una conversión del DOCX: se compone aparte, con control explícito
de márgenes, saltos, repetición de encabezados de tabla, índice navegable,
marcadores y numeración «Página X de Y».

Se usa ReportLab porque el requisito incluye marcadores, índice con enlaces
internos y fuentes incrustadas, que un PDF dibujado con matplotlib no puede
ofrecer. Si la biblioteca no está instalada, la función de guardado lanza un
error explícito en lugar de degradar el documento en silencio.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app_icociv.reportes.modelo import (
    Aviso,
    Ficha,
    Firmas,
    Formula,
    FUENTE_MONO_PDF,
    Imagen,
    Informe,
    NOMBRE_COMPLETO,
    PALETA,
    Parrafo,
    Portada,
    Seccion,
    Tabla,
    Vinetas,
    fecha_larga,
)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image as ImagenPlatypus,
        KeepTogether,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table as TablaPlatypus,
        TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    PDF_DISPONIBLE = True
except ImportError:  # pragma: no cover - depende del entorno
    PDF_DISPONIBLE = False


# TANDA 3, 14-08-2026: margen de 2,2 a 2,0 cm. Sigue siendo un margen amplio para
# A4 -no es un margen extremo- y devuelve 0,4 cm de ancho y de alto por pagina.
MARGEN = 2.0
# Umbral de secciones a partir del cual el documento supera las ocho páginas y
# merece índice. El informe ejecutivo queda por debajo a propósito: un índice en
# un documento de cinco páginas roba una página y no ayuda a nadie.
SECCIONES_PARA_INDICE = 10

_FUENTES_REGISTRADAS = False


def esta_disponible() -> bool:
    return PDF_DISPONIBLE


def _registrar_fuentes() -> tuple[str, str, str]:
    """Incrusta Bitstream Vera, que viaja con ReportLab y cubre el español.

    Se incrusta a propósito: una fuente base del visor no queda dentro del
    archivo y el documento se ve distinto según dónde se abra.
    """
    global _FUENTES_REGISTRADAS
    normal, negrita, cursiva = "SAVIP-Sans", "SAVIP-Sans-Bold", "SAVIP-Sans-Italic"
    if _FUENTES_REGISTRADAS:
        return normal, negrita, cursiva
    import reportlab

    carpeta = Path(reportlab.__file__).parent / "fonts"
    archivos = {normal: "Vera.ttf", negrita: "VeraBd.ttf", cursiva: "VeraIt.ttf"}
    try:
        for nombre, archivo in archivos.items():
            pdfmetrics.registerFont(TTFont(nombre, str(carpeta / archivo)))
        pdfmetrics.registerFontFamily(normal, normal=normal, bold=negrita, italic=cursiva, boldItalic=negrita)
        _FUENTES_REGISTRADAS = True
        return normal, negrita, cursiva
    except Exception:  # pragma: no cover - instalación sin las fuentes empaquetadas
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _c(hex_color: str) -> Any:
    return colors.HexColor(hex_color)


def _estilos() -> dict[str, Any]:
    normal, negrita, cursiva = _registrar_fuentes()
    base = getSampleStyleSheet()
    return {
        "normal": ParagraphStyle(
            "SavipNormal", parent=base["Normal"], fontName=normal, fontSize=9.5, leading=12.6,
            textColor=_c(PALETA["texto"]), spaceAfter=4, alignment=TA_LEFT,
        ),
        "titulo_portada": ParagraphStyle(
            "SavipTituloPortada", fontName=negrita, fontSize=23, leading=27,
            textColor=_c(PALETA["marca"]), spaceAfter=8,
        ),
        "subtitulo_portada": ParagraphStyle(
            "SavipSubtituloPortada", fontName=normal, fontSize=11.5, leading=15,
            textColor=_c(PALETA["texto_secundario"]), spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "SavipH1", fontName=negrita, fontSize=14, leading=17,
            textColor=_c(PALETA["marca_intensa"]), spaceBefore=8, spaceAfter=4,
        ),
        "titulo_tabla": ParagraphStyle(
            "SavipTituloTabla", fontName=negrita, fontSize=9.5, leading=12,
            textColor=_c(PALETA["marca_intensa"]), spaceBefore=6, spaceAfter=3,
        ),
        "celda": ParagraphStyle(
            "SavipCelda", fontName=normal, fontSize=8.2, leading=9.9, textColor=_c(PALETA["texto"]),
        ),
        "celda_derecha": ParagraphStyle(
            "SavipCeldaDerecha", fontName=normal, fontSize=8.2, leading=9.9,
            textColor=_c(PALETA["texto"]), alignment=TA_RIGHT,
        ),
        "celda_encabezado": ParagraphStyle(
            "SavipCeldaEncabezado", fontName=negrita, fontSize=8.2, leading=10.4, textColor=colors.white,
        ),
        "celda_encabezado_derecha": ParagraphStyle(
            "SavipCeldaEncabezadoDerecha", fontName=negrita, fontSize=8.2, leading=10.4,
            textColor=colors.white, alignment=TA_RIGHT,
        ),
        "clave": ParagraphStyle(
            "SavipClave", fontName=negrita, fontSize=8.6, leading=11, textColor=_c(PALETA["texto"]),
        ),
        "destacado_etiqueta": ParagraphStyle(
            "SavipDestacadoEtiqueta", fontName=normal, fontSize=7, leading=9,
            textColor=_c(PALETA["texto_secundario"]), alignment=TA_CENTER,
        ),
        "destacado_valor": ParagraphStyle(
            "SavipDestacadoValor", fontName=negrita, fontSize=12.5, leading=15,
            textColor=_c(PALETA["marca_intensa"]), alignment=TA_CENTER,
        ),
        "nota": ParagraphStyle(
            "SavipNota", fontName=normal, fontSize=7.8, leading=10,
            textColor=_c(PALETA["texto_secundario"]), spaceAfter=6,
        ),
        "pie_figura": ParagraphStyle(
            "SavipPieFigura", fontName=cursiva, fontSize=8, leading=10.5,
            textColor=_c(PALETA["texto_secundario"]), spaceBefore=3, spaceAfter=8,
        ),
        "formula": ParagraphStyle(
            "SavipFormula", fontName=FUENTE_MONO_PDF, fontSize=9, leading=12.5,
            textColor=_c(PALETA["texto"]), leftIndent=0.7 * cm, spaceAfter=1,
        ),
        "formula_resultado": ParagraphStyle(
            "SavipFormulaResultado", fontName=FUENTE_MONO_PDF, fontSize=9, leading=12.5,
            textColor=_c(PALETA["marca_intensa"]), leftIndent=0.7 * cm, spaceAfter=8,
        ),
        "aviso_titulo": ParagraphStyle(
            "SavipAvisoTitulo", fontName=negrita, fontSize=9.2, leading=12, spaceAfter=3,
        ),
        "aviso_item": ParagraphStyle(
            "SavipAvisoItem", fontName=normal, fontSize=8.8, leading=11.5, leftIndent=0.3 * cm, spaceAfter=2,
        ),
        "vineta": ParagraphStyle(
            "SavipVineta", fontName=normal, fontSize=9.2, leading=12.5,
            leftIndent=0.5 * cm, bulletIndent=0.15 * cm, spaceAfter=3, textColor=_c(PALETA["texto"]),
        ),
        "toc1": ParagraphStyle(
            "SavipTOC1", fontName=normal, fontSize=10, leading=17, textColor=_c(PALETA["texto"]),
        ),
        "_fuentes": (normal, negrita, cursiva),
    }


def _escapar(texto: Any) -> str:
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class _DocumentoInforme(BaseDocTemplate):
    """Plantilla con portada sin adornos, cuerpo con encabezado, pie y marcadores."""

    def __init__(self, destino: Any, informe: Informe, estilos: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(destino, pagesize=A4, **kwargs)
        self.informe = informe
        self.estilos = estilos
        self.total_paginas = 0
        self._titulos_vistos = 0
        ancho, alto = A4
        marco = Frame(
            MARGEN * cm, (MARGEN - 0.4) * cm,
            ancho - 2 * MARGEN * cm, alto - (2 * MARGEN - 0.2) * cm,
            id="cuerpo", showBoundary=0,
        )
        self.addPageTemplates([
            PageTemplate(id="portada", frames=[marco], onPage=self._pintar_portada),
            PageTemplate(id="cuerpo", frames=[marco], onPage=self._pintar_cuerpo),
        ])

    def _pintar_portada(self, lienzo: Any, documento: Any) -> None:
        ancho, alto = A4
        lienzo.saveState()
        lienzo.setFillColor(_c(PALETA["marca"]))
        lienzo.rect(0, alto - 1.0 * cm, ancho, 1.0 * cm, stroke=0, fill=1)
        lienzo.setFillColor(_c(PALETA["texto_secundario"]))
        lienzo.setFont(self.estilos["_fuentes"][0], 7.5)
        lienzo.drawString(MARGEN * cm, 1.2 * cm, self.informe.pie)
        lienzo.restoreState()

    def _pintar_cuerpo(self, lienzo: Any, documento: Any) -> None:
        ancho, alto = A4
        normal, negrita, _ = self.estilos["_fuentes"]
        lienzo.saveState()
        lienzo.setFont(normal, 7.5)
        lienzo.setFillColor(_c(PALETA["texto_secundario"]))
        lienzo.drawRightString(ancho - MARGEN * cm, alto - 1.35 * cm, f"{NOMBRE_COMPLETO}  ·  {self.informe.identificador}")
        lienzo.setStrokeColor(_c(PALETA["borde"]))
        lienzo.setLineWidth(0.5)
        lienzo.line(MARGEN * cm, alto - 1.55 * cm, ancho - MARGEN * cm, alto - 1.55 * cm)

        lienzo.line(MARGEN * cm, 1.55 * cm, ancho - MARGEN * cm, 1.55 * cm)
        lienzo.drawString(MARGEN * cm, 1.15 * cm, fecha_larga(self.informe.generado))
        total = f" de {self.total_paginas}" if self.total_paginas else ""
        lienzo.setFont(negrita, 7.5)
        lienzo.drawRightString(ancho - MARGEN * cm, 1.15 * cm, f"Página {documento.page}{total}")
        lienzo.restoreState()

    def afterFlowable(self, flowable: Any) -> None:
        """Registra cada título como entrada de índice y marcador navegable."""
        if not isinstance(flowable, Paragraph) or flowable.style.name != "SavipH1":
            return
        texto = flowable.getPlainText()
        # La clave se numera por orden de aparición, no por página: en la segunda
        # pasada el índice desplaza las páginas y una clave basada en la página
        # dejaría los enlaces apuntando a destinos que ya no existen.
        self._titulos_vistos += 1
        clave = f"savip-seccion-{self._titulos_vistos}"
        self.canv.bookmarkPage(clave)
        self.canv.addOutlineEntry(texto, clave, level=0, closed=False)
        self.notify("TOCEntry", (0, texto, self.page, clave))

    def afterPage(self) -> None:
        self.total_paginas = max(self.total_paginas, self.page)

    def _startBuild(self, *args: Any, **kwargs: Any) -> Any:
        # multiBuild reutiliza la plantilla entre pasadas; el contador debe
        # reiniciarse o la segunda pasada generaría claves distintas.
        self._titulos_vistos = 0
        return super()._startBuild(*args, **kwargs)


# ==============================
# BLOQUES
# ==============================


def _ancho_disponible() -> float:
    return A4[0] - 2 * MARGEN * cm


def _tabla_clave_valor(filas: list[tuple[str, str]], estilos: dict[str, Any], ancho_clave: float = 5.4) -> Any:
    disponible = _ancho_disponible()
    anchos = [ancho_clave * cm, disponible - ancho_clave * cm]
    datos = [
        [Paragraph(_escapar(campo), estilos["clave"]), Paragraph(_escapar(valor), estilos["celda"])]
        for campo, valor in filas
    ]
    tabla = TablaPlatypus(datos, colWidths=anchos, repeatRows=0, splitByRow=1)
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, _c(PALETA["borde"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
    ]
    for indice in range(0, len(datos), 2):
        estilo.append(("BACKGROUND", (0, indice), (-1, indice), _c(PALETA["superficie_alterna"])))
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _tabla(bloque: Tabla, estilos: dict[str, Any]) -> list[Any]:
    columnas = len(bloque.encabezados)
    disponible = _ancho_disponible()
    proporciones = bloque.anchos or tuple([1.0] * columnas)
    total = sum(proporciones) or 1.0
    anchos = [disponible * (p / total) for p in proporciones]

    encabezado = [
        Paragraph(
            _escapar(titulo),
            estilos["celda_encabezado_derecha"] if indice in bloque.columnas_numericas else estilos["celda_encabezado"],
        )
        for indice, titulo in enumerate(bloque.encabezados)
    ]
    datos = [encabezado]
    for valores in bloque.filas:
        fila = []
        for indice in range(columnas):
            texto = _escapar(valores[indice]) if indice < len(valores) else ""
            estilo = estilos["celda_derecha"] if indice in bloque.columnas_numericas else estilos["celda"]
            fila.append(Paragraph(texto, estilo))
        datos.append(fila)

    # repeatRows repite el encabezado en cada página; splitByRow impide que una
    # fila quede partida entre dos páginas.
    tabla = TablaPlatypus(datos, colWidths=anchos, repeatRows=1, splitByRow=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), _c(PALETA["marca"])),
        ("GRID", (0, 0), (-1, -1), 0.4, _c(PALETA["borde"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        # TANDA 3, 14-08-2026: relleno vertical de 2,2 a 1,5 pt. La tabla de
        # evaluacion por horizonte crecio a 68 filas al derivarse la rejilla de la
        # aritmetica de ventanas, y cada punto de relleno se multiplica por fila.
        # Es compactacion de MAQUETACION: no se retira ninguna fila.
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]
    for indice in range(2, len(datos), 2):
        estilo.append(("BACKGROUND", (0, indice), (-1, indice), _c(PALETA["superficie_alterna"])))
    tabla.setStyle(TableStyle(estilo))

    salida: list[Any] = []
    if bloque.titulo:
        salida.append(Paragraph(_escapar(bloque.titulo), estilos["titulo_tabla"]))
    salida.append(tabla)
    for texto, etiqueta in ((bloque.nota, "Nota"), (bloque.fuente, "Fuente")):
        if texto:
            salida.append(Paragraph(f"{etiqueta}: {_escapar(texto)}", estilos["nota"]))
    salida.append(Spacer(1, 6))
    # Un título de tabla nunca debe quedar solo al final de una página.
    return [KeepTogether(salida[:2])] + salida[2:] if len(salida) > 2 else salida


def _ficha(bloque: Ficha, estilos: dict[str, Any]) -> list[Any]:
    salida: list[Any] = []
    if bloque.destacados:
        disponible = _ancho_disponible()
        ancho = disponible / len(bloque.destacados)
        datos = [
            [Paragraph(_escapar(e.upper()), estilos["destacado_etiqueta"]) for e, _ in bloque.destacados],
            [Paragraph(_escapar(v), estilos["destacado_valor"]) for _, v in bloque.destacados],
        ]
        tarjetas = TablaPlatypus(datos, colWidths=[ancho] * len(bloque.destacados))
        tarjetas.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _c(PALETA["marca_suave"])),
            ("LINEBELOW", (0, 1), (-1, 1), 1.6, _c(PALETA["marca"])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        salida.append(KeepTogether([tarjetas, Spacer(1, 8)]))
    if bloque.filas:
        salida.append(_tabla_clave_valor(bloque.filas, estilos, ancho_clave=6.0))
        salida.append(Spacer(1, 6))
    return salida


def _aviso(bloque: Aviso, estilos: dict[str, Any]) -> list[Any]:
    paletas = {
        "advertencia": (PALETA["aviso"], PALETA["aviso_fondo"], "!"),
        "error": (PALETA["error"], PALETA["error_fondo"], "×"),
        "informacion": (PALETA["informacion"], PALETA["informacion_fondo"], "i"),
    }
    borde, fondo, simbolo = paletas.get(bloque.nivel, paletas["advertencia"])
    titulo = ParagraphStyle("AvisoTitulo", parent=estilos["aviso_titulo"], textColor=_c(borde))
    contenido: list[Any] = [Paragraph(f"{simbolo}&nbsp;&nbsp;{_escapar(bloque.titulo)}", titulo)]
    contenido += [Paragraph(f"—&nbsp;{_escapar(item)}", estilos["aviso_item"]) for item in bloque.items]

    caja = TablaPlatypus([[contenido]], colWidths=[_ancho_disponible()])
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _c(fondo)),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, _c(borde)),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [KeepTogether([caja, Spacer(1, 8)])]


def _formula(bloque: Formula, estilos: dict[str, Any]) -> list[Any]:
    piezas: list[Any] = [
        Paragraph(_escapar(bloque.etiqueta), estilos["titulo_tabla"]),
        Paragraph(_escapar(bloque.general), estilos["formula"]),
    ]
    piezas += [Paragraph(_escapar(linea), estilos["formula"]) for linea in bloque.sustitucion]
    piezas.append(Paragraph(_escapar(bloque.resultado), estilos["formula_resultado"]))
    return [KeepTogether(piezas)]


def _firmas(bloque: Firmas, estilos: dict[str, Any]) -> list[Any]:
    ancho = _ancho_disponible() / len(bloque.roles)
    datos = [
        [Paragraph("&nbsp;", estilos["celda"]) for _ in bloque.roles],
        [Paragraph(f"<b>{_escapar(rol)}</b><br/>Nombre, cargo y fecha", estilos["celda"]) for rol in bloque.roles],
    ]
    tabla = TablaPlatypus(datos, colWidths=[ancho] * len(bloque.roles), rowHeights=[1.6 * cm, None])
    tabla.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (-1, 1), 0.8, _c(PALETA["borde_fuerte"])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    return [Spacer(1, 14), KeepTogether([tabla])]


def _imagen(bloque: Imagen, estilos: dict[str, Any]) -> list[Any]:
    lector = ImageReader(io.BytesIO(bloque.datos))
    ancho_px, alto_px = lector.getSize()
    ancho = min(bloque.ancho_cm * cm, _ancho_disponible())
    alto = ancho * alto_px / ancho_px
    # Ninguna figura debe empujar el resto de la página fuera del marco.
    maximo = 10.2 * cm
    if alto > maximo:
        ancho *= maximo / alto
        alto = maximo
    figura = ImagenPlatypus(io.BytesIO(bloque.datos), width=ancho, height=alto)
    figura.hAlign = "CENTER"
    piezas: list[Any] = [figura]
    if bloque.pie:
        piezas.append(Paragraph(_escapar(bloque.pie), estilos["pie_figura"]))
    return [KeepTogether(piezas)]


def _bloque(bloque: Any, estilos: dict[str, Any]) -> list[Any]:
    if isinstance(bloque, Parrafo):
        texto = _escapar(bloque.texto)
        return [Paragraph(f"<b>{texto}</b>" if bloque.enfasis else texto, estilos["normal"])]
    if isinstance(bloque, Vinetas):
        return [Paragraph(_escapar(i), estilos["vineta"], bulletText="•") for i in bloque.items]
    if isinstance(bloque, Ficha):
        return _ficha(bloque, estilos)
    if isinstance(bloque, Tabla):
        return _tabla(bloque, estilos)
    if isinstance(bloque, Imagen):
        return _imagen(bloque, estilos)
    if isinstance(bloque, Aviso):
        return _aviso(bloque, estilos)
    if isinstance(bloque, Formula):
        return _formula(bloque, estilos)
    if isinstance(bloque, Firmas):
        return _firmas(bloque, estilos)
    return []


def _portada(portada: Portada, estilos: dict[str, Any]) -> list[Any]:
    piezas: list[Any] = [Spacer(1, 1.4 * cm)]
    if portada.logo:
        try:
            lector = ImageReader(io.BytesIO(portada.logo))
            ancho_px, alto_px = lector.getSize()
            ancho = 4.5 * cm
            logo = ImagenPlatypus(io.BytesIO(portada.logo), width=ancho, height=ancho * alto_px / ancho_px)
            logo.hAlign = "LEFT"
            piezas += [logo, Spacer(1, 0.8 * cm)]
        except Exception:  # pragma: no cover - logo inválido no debe romper el informe
            pass
    piezas.append(Paragraph(_escapar(portada.titulo), estilos["titulo_portada"]))
    piezas.append(Paragraph(_escapar(portada.subtitulo), estilos["subtitulo_portada"]))
    piezas.append(_tabla_clave_valor(portada.filas, estilos, ancho_clave=6.0))
    if portada.observaciones:
        piezas.append(Spacer(1, 0.5 * cm))
        piezas.append(Paragraph("Observaciones generales", estilos["titulo_tabla"]))
        piezas.append(Paragraph(_escapar(portada.observaciones), estilos["normal"]))
    return piezas


def _indice(estilos: dict[str, Any]) -> list[Any]:
    tabla = TableOfContents()
    tabla.levelStyles = [estilos["toc1"]]
    tabla.dotsMinLevel = 0
    return [Paragraph("Contenido", estilos["h1"]), tabla, PageBreak()]


def construir_historia(informe: Informe, estilos: dict[str, Any]) -> list[Any]:
    historia: list[Any] = []
    secciones: list[Seccion] = informe.secciones_visibles()

    if informe.portada is not None:
        historia += _portada(informe.portada, estilos)
        historia.append(NextPageTemplate("cuerpo"))
        historia.append(PageBreak())
    else:
        historia.append(NextPageTemplate("cuerpo"))

    if len(secciones) >= SECCIONES_PARA_INDICE:
        historia += _indice(estilos)

    for numero, seccion in enumerate(secciones, start=1):
        historia.append(Paragraph(f"{numero}. {_escapar(seccion.titulo)}", estilos["h1"]))
        for bloque in seccion.bloques:
            historia += _bloque(bloque, estilos)
    return historia


def guardar(informe: Informe, ruta: Any) -> Path:
    """Compone el PDF en dos pasadas para resolver el índice y el total de páginas."""
    if not PDF_DISPONIBLE:
        raise RuntimeError(
            "reportlab no está instalado y es necesario para el informe PDF. "
            "Ejecute: pip install reportlab"
        )
    destino = Path(ruta)
    if destino.suffix.lower() != ".pdf":
        destino = destino.with_suffix(".pdf")
    destino.parent.mkdir(parents=True, exist_ok=True)

    estilos = _estilos()
    documento = _DocumentoInforme(
        str(destino), informe, estilos,
        title=informe.identificador,
        author=NOMBRE_COMPLETO,
        subject=informe.pie,
        creator=NOMBRE_COMPLETO,
    )
    documento.multiBuild(construir_historia(informe, estilos))
    return destino


def a_bytes(informe: Informe) -> bytes:
    if not PDF_DISPONIBLE:
        raise RuntimeError("reportlab no está instalado. Ejecute: pip install reportlab")
    estilos = _estilos()
    memoria = io.BytesIO()
    documento = _DocumentoInforme(memoria, informe, estilos, title=informe.identificador, author=NOMBRE_COMPLETO)
    documento.multiBuild(construir_historia(informe, estilos))
    return memoria.getvalue()
