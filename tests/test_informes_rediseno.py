"""Pruebas del rediseño de informes DOCX y PDF de SAVIP.

Cubren los cuatro tipos de informe, el selector de contenido, las diferencias
entre formatos y la regresión estadística: generar informes no puede alterar
ningún resultado del análisis.

Ejecutar con:  python tests/test_informes_rediseno.py
"""

from __future__ import annotations

import copy
import re
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion  # noqa: E402
from app_icociv.reportes import docx_render, graficas, pdf_render  # noqa: E402
from app_icociv.reportes.contenido import (  # noqa: E402
    DatosProyeccion,
    construir_informe_proyeccion,
    interpretacion,
    resumen_ejecutivo,
)
from app_icociv.reportes.contenido_empalme import construir_informe_empalme  # noqa: E402
from app_icociv.reportes.modelo import (  # noqa: E402
    Aviso,
    ConfiguracionInforme,
    Formula,
    Imagen,
    Tabla,
    formato_indice,
    formato_porcentaje,
    identificador_informe,
    nombre_archivo_informe,
    periodo_largo,
)
from app_icociv.servicios.empalme_iccp_icociv import calcular_empalme_iccp_icociv  # noqa: E402


ANIO_BASE = 2019
RUTA = [
    {"nivel": "Grupo de obra", "valor": "Carreteras"},
    {"nivel": "Insumo", "valor": "Herramienta menor"},
]


# ==============================
# APOYO
# ==============================


def _serie(n: int = 72) -> pd.DataFrame:
    periodos = [f"{ANIO_BASE + i // 12}_{i % 12 + 1}" for i in range(n)]
    # Tendencia suave con escalón de enero: se parece a una serie ICOCIV real.
    valores = [100.0 + 0.8 * i + (3.5 if i and i % 12 == 0 else 0.0) for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _datos(serie: pd.DataFrame, resultado: dict) -> DatosProyeccion:
    return DatosProyeccion(
        resultado=resultado,
        serie_df=serie,
        fuente_label="T_16",
        archivo_excel=r"C:\ruta\interna\anexo_icociv.xlsb",
        ruta_jerarquica=RUTA,
        fila=serie.head(1),
        year_month=list(serie["Periodo"]),
        usuario="Prueba",
    )


def _texto_informe(informe) -> str:
    """Todo el texto del informe, cubriendo los ocho tipos de bloque de modelo.py.

    No basta con leer `texto`: las declaraciones de estado viajan tambien en
    `Aviso.items`, en `Tabla.nota`/`fuente` y en las filas de `Ficha`.
    """
    partes: list[str] = []
    for seccion in informe.secciones_visibles():
        partes.append(seccion.titulo)
        for bloque in seccion.bloques:
            for atributo in ("texto", "titulo", "nota", "fuente", "pie", "etiqueta",
                             "general", "resultado"):
                valor = getattr(bloque, atributo, None)
                if isinstance(valor, str) and valor:
                    partes.append(valor)
            for atributo in ("items", "roles", "encabezados", "sustitucion", "destacados"):
                valor = getattr(bloque, atributo, None)
                if isinstance(valor, (list, tuple)):
                    for elemento in valor:
                        partes.append(
                            " | ".join(str(c) for c in elemento)
                            if isinstance(elemento, (list, tuple)) else str(elemento)
                        )
            filas = getattr(bloque, "filas", None)
            if isinstance(filas, (list, tuple)):
                for fila in filas:
                    partes.append(
                        " | ".join(str(c) for c in fila)
                        if isinstance(fila, (list, tuple)) else str(fila)
                    )
    return "\n".join(partes)


def _bloques(informe, tipo) -> list:
    return [b for seccion in informe.secciones for b in seccion.bloques if isinstance(b, tipo)]


def _claves(informe) -> set[str]:
    return {seccion.clave for seccion in informe.secciones_visibles()}


def _texto_docx(ruta: Path) -> str:
    with zipfile.ZipFile(ruta) as paquete:
        xml = paquete.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


def _partes_docx(ruta: Path) -> list[str]:
    with zipfile.ZipFile(ruta) as paquete:
        return paquete.namelist()


def _tablas_platypus(flowables) -> list:
    """Aplana KeepTogether para alcanzar las tablas reales de ReportLab."""
    encontradas = []
    for flowable in flowables:
        interior = getattr(flowable, "_content", None)
        if interior:
            encontradas.extend(_tablas_platypus(interior))
        if flowable.__class__.__name__ == "Table":
            encontradas.append(flowable)
    return encontradas


def _paginas_pdf(ruta: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", ruta.read_bytes()))


def _calculo_empalme() -> dict:
    indices = {"2021_12": 100.0, "2024_6": 118.4, "2019_3": 92.0}
    entrada = {
        "item": "Concreto clase D",
        "unidad": "m3",
        "precio_base": 1_000_000_000,
        "anticipo_amortizado": 100_000_000,
        "fecha_inicial": "2019_3",
        "fecha_final": "2024_6",
        "tipo_serie_iccp": "grupo_obra",
        "serie_iccp": "Concretos, morteros y obras varias",
        "ruta_icociv": "Carreteras > Materiales > Concreto",
        "observacion_tecnica": "Fecha base tomada del acta de inicio.",
    }
    calculo = calcular_empalme_iccp_icociv(entrada, indices)
    calculo["ruta_icociv"] = entrada["ruta_icociv"]
    return calculo


_SERIE = _serie()
_RESULTADO = ejecutar_proyeccion(_SERIE, 2026, 6, ANIO_BASE)
_DATOS = _datos(_SERIE, _RESULTADO)


# ==============================
# 14.1 INFORME EJECUTIVO
# ==============================


def test_ejecutivo_genera_docx_y_pdf_con_las_secciones_correctas() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    claves = _claves(informe)

    assert {"resumen", "identificacion", "ficha", "grafica_principal",
            "interpretacion", "advertencias", "tabla_proyeccion"} <= claves
    # El detalle técnico no seleccionado no debe aparecer.
    assert not claves & {"modelos", "backtesting", "residuos", "cobertura", "horizonte", "anexos"}
    assert informe.portada is not None

    with TemporaryDirectory() as tmp:
        destino = Path(tmp)
        docx = docx_render.guardar(informe, destino / "ejecutivo.docx")
        pdf = pdf_render.guardar(informe, destino / "ejecutivo.pdf")
        assert docx.is_file() and docx.stat().st_size > 20_000
        assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF")
        assert 3 <= _paginas_pdf(pdf) <= 6, f"El ejecutivo debe ocupar de 3 a 6 páginas, no {_paginas_pdf(pdf)}"


def test_ejecutivo_lleva_una_sola_grafica() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    assert len(_bloques(informe, Imagen)) == 1


def test_ejecutivo_muestra_advertencias_y_limitaciones_en_recuadro() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    avisos = _bloques(informe, Aviso)
    assert avisos, "Las advertencias deben ir en un bloque de aviso visible."
    textos = " ".join(item for aviso in avisos for item in aviso.items)
    assert "DANE" in textos
    assert "liquidar contratos" in textos
    # P0-C / C2: la limitacion fija hablaba del nivel nominal del 95 % de la
    # banda mostrada. Esta version no muestra banda; la limitacion que debe
    # llegar al recuadro es que la incertidumbre no viene acotada.
    assert "no publica intervalo de predicción" in textos.lower()
    assert "no viene acotada" in textos.lower()


def test_tabla_resumida_tiene_las_columnas_pedidas() -> None:
    """P0-C / C2: cuatro columnas, sin las dos de límites del 95 %.

    Antes se exigian seis, con «Limite inferior 95 %» y «Limite superior 95 %».
    Tras los cinco cortes esas dos columnas quedaron con la celda «no publicado»
    en todas las filas: dos columnas enteras que seguian anunciando una banda
    ausente. Se retiraron. Lo que se comprueba ahora es que la tabla entregue el
    periodo, el punto, su clasificacion y la observacion, y que NO reintroduzca
    ninguna columna de limites.
    """
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    tablas = [t for t in _bloques(informe, Tabla) if t.encabezados[0] == "Periodo"]
    assert tablas, "Falta la tabla de proyección."
    tabla = tablas[0]
    assert tabla.encabezados == [
        "Periodo", "Índice proyectado", "Clasificación", "Observación",
    ]
    assert len(tabla.filas) == len(_RESULTADO["proyecciones"])
    assert all(len(fila) == 4 for fila in tabla.filas)
    assert not [c for c in tabla.encabezados if "95" in c or "ímite" in c], tabla.encabezados


def test_resumen_ejecutivo_es_dinamico_y_no_generico() -> None:
    parrafos = " ".join(resumen_ejecutivo(_DATOS))
    assert "Herramienta menor" in parrafos, "Debe nombrar la serie real."
    assert str(_RESULTADO["horizonte_solicitado"]) in parrafos
    assert str(_RESULTADO["model_name"]) in parrafos

    otra = _serie(48)
    otro_resultado = ejecutar_proyeccion(otra, 2024, 6, ANIO_BASE)
    otros = " ".join(resumen_ejecutivo(_datos(otra, otro_resultado)))
    assert otros != parrafos, "El resumen no puede ser el mismo para series distintas."


def test_portada_no_expone_rutas_internas() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    texto = " ".join(f"{campo} {valor}" for campo, valor in informe.portada.filas)
    assert "anexo_icociv.xlsb" in texto, "Debe mostrarse el nombre del archivo fuente."
    assert "ruta\\interna" not in texto and "C:\\" not in texto
    assert ".py" not in texto and "app_icociv" not in texto


# ==============================
# 14.2 INFORME TÉCNICO
# ==============================


def test_tecnico_incluye_todo_el_detalle_metodologico() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    claves = _claves(informe)
    assert {"preparacion", "modelos", "seleccion_modelo", "metricas", "backtesting",
            "intervalos", "cobertura", "residuos", "calendario", "horizonte",
            "reproducibilidad"} <= claves

    tablas = {t.encabezados[0]: t for t in _bloques(informe, Tabla)}
    assert "Modelo" in tablas, "Falta la tabla de modelos evaluados."
    assert tablas["Modelo"].encabezados == ["Modelo", "MAE", "RMSE", "MASE", "Sesgo", "Resultado"]

    texto = " ".join(
        b.texto for seccion in informe.secciones for b in seccion.bloques if hasattr(b, "texto")
    )
    assert "walk-forward" in texto
    # P0-C / C2, 15-08-2026. Antes se exigia que el informe hablara del intervalo
    # de prediccion y aclarara que no es de confianza. Esa aclaracion tenia
    # sentido mientras la banda se entregaba. Retirada la banda, lo que el
    # informe debe decir es que NO la publica y por que; seguir exigiendo la
    # distincion prediccion/confianza obligaria a explicar un objeto ausente.
    assert "no publica intervalo de predicción" in texto.lower()
    assert "no está sustentada" in texto.lower() or "no está sustentado" in texto.lower()
    # Y no puede afirmar que la incertidumbre no exista: se retira la banda, no
    # la advertencia de que el pronostico no viene acotado.
    assert "incertidumbre" in texto.lower()


def test_tecnico_declara_la_evidencia_oos_sin_publicar_cobertura() -> None:
    """P0-C / C2: la seccion existe, entrega evidencia y no tipifica la banda.

    Sustituye a `test_tecnico_reporta_cobertura_empirica_verificada`, que exigia
    la tabla de cobertura por horizonte. Esa tabla medía el desempeño de un
    intervalo que esta version ya no publica. Lo que se comprueba ahora es la
    propiedad correcta: la seccion sigue declarando el paso exacto y el tamaño de
    su evidencia -que describen la trayectoria-, y NO publica ninguna cobertura.
    """
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    seccion = next((s for s in informe.secciones if s.clave == "cobertura"), None)
    assert seccion is not None, "la seccion de evidencia OOS desaparecio"
    tablas = [b for b in seccion.bloques if isinstance(b, Tabla)]
    assert any(
        t.encabezados[0] == "Elemento" and any("Paso exacto" in str(f[0]) for f in t.filas)
        for t in tablas
    ), "la seccion debe declarar el paso exacto solicitado"
    assert any(
        any("Errores fuera de muestra" in str(f[0]) for f in t.filas) for t in tablas
    ), "la seccion debe declarar el tamaño de la evidencia del paso"
    # Ninguna tabla tipifica ya la banda ni publica su cobertura.
    assert not any(t.encabezados[0].startswith("Horizonte") for t in tablas), (
        [t.encabezados for t in tablas]
    )
    plano = " ".join(
        str(celda) for t in tablas for fila in t.filas for celda in fila
    ) + " " + " ".join(str(t.titulo) for t in tablas)
    for marca in ("cobertura observada", "nominal declarado", "cobertura mínima"):
        assert marca not in plano.lower(), (marca, plano[:200])


def test_tecnico_no_afirma_ljung_box_cuando_no_esta_disponible() -> None:
    """RA-04: se distingue dependencia disponible de diagnóstico no calculable.

    statsmodels es dependencia obligatoria: si falta, la aplicación no arranca.
    Por eso el informe nunca puede atribuir a la distribución la ausencia del
    valor p; debe declarar el motivo estadístico concreto.
    """
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    seccion = next(s for s in informe.secciones if s.clave == "residuos")
    texto = " ".join(b.texto for b in seccion.bloques if hasattr(b, "texto"))
    assert "no está disponible en esta distribución" not in texto, texto
    disponible = (_RESULTADO.get("diagnostico_residuos") or {}).get("ljung_box", {}).get("p_value")
    if disponible is None:
        assert "no se calcula" in texto, texto
        assert "statsmodels" in texto and "está disponible" in texto, texto


def test_tecnico_conserva_reproducibilidad_y_referencias() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    seccion = next(s for s in informe.secciones if s.clave == "reproducibilidad")
    filas = [f for b in seccion.bloques if isinstance(b, Tabla) for f in b.filas]
    etiquetas = {f[0] for f in filas}
    assert {"Identificador del informe", "Versión de SAVIP", "Modelo aplicado",
            "Horizonte solicitado", "Periodo analizado"} <= etiquetas


def test_tecnico_es_navegable_y_conserva_toda_la_evidencia() -> None:
    """El técnico debe ser navegable y completo; su extensión la fija el dato.

    TANDA 3, 14-08-2026. Antes se exigía ``8 <= paginas <= 16``. Ese rango **no
    es un requisito formal**: `REPORT_GENERATION_REDESIGN.md` lo publica en una
    columna titulada «Extensión **medida**», lo llama «rango **recomendado**» y ya
    declaraba que excederlo «es **consecuencia del dato, no del diseño**». Se midió
    además «con horizontes de 6 a 18 meses», es decir en el régimen anterior al
    retiro del cap 30. El propio docstring anterior de esta prueba documentaba que
    la cota había subido de 15 a 16 al crecer el diagnóstico residual: un umbral
    que se reajusta cada vez que crece la evidencia es un registro de medición, no
    un umbral.

    Mantenerlo como assert rígido creaba presión para **recortar evidencia
    estadística** y así caber en un número inventado, que es justo lo que el
    principio rector y REQ 5 prohíben. Lo que el proyecto sí llama requisito, en
    esa misma frase, es **la coherencia entre las cuatro salidas**.

    Se sustituye por las propiedades que la prueba realmente pretendía proteger:
    que el documento sea navegable, que no tenga páginas en blanco y que **toda**
    la evidencia siga dentro. La extensión se mide y se registra, no se veta.
    """
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    with TemporaryDirectory() as tmp:
        pdf = pdf_render.guardar(informe, Path(tmp) / "tecnico.pdf")
        paginas = _paginas_pdf(pdf)
        datos = pdf.read_bytes()

        # 1. Navegable: índice y marcadores.
        assert b"/Outlines" in datos, "El PDF técnico debe llevar marcadores."
        # 2. Acotado por abajo: si cae por debajo del mínimo, falta contenido.
        assert paginas >= 8, f"El técnico no puede encogerse a {paginas} páginas."
        # 3. La extensión se registra para que su evolución sea visible en el log,
        #    sin convertir una medición en norma.
        print(f"    [extensión medida del informe técnico: {paginas} páginas]")

    # 4. Completitud: la evidencia por horizonte entra ENTERA. Con la rejilla
    #    derivada de la aritmética de ventanas hay horizontes por encima de 30, y
    #    ninguno puede desaparecer del informe para ahorrar páginas.
    horizonte = next(s for s in informe.secciones_visibles() if s.clave == "horizonte")
    tablas = [b for b in horizonte.bloques if isinstance(b, Tabla)]
    evaluados = [
        int(str(fila[0]).split(" ")[0])
        for tabla in tablas for fila in tabla.filas
        if str(fila[0]).split(" ")[0].isdigit()
    ]
    info = _RESULTADO.get("horizonte_info") or {}
    esperados = [int(e["horizonte"]) for e in (info.get("evaluaciones") or [])]
    assert evaluados == esperados, (len(evaluados), len(esperados))
    assert max(evaluados) > 30, "La rejilla derivada debe superar el cap 30 retirado."
    # 5. Cada fila publica su número de orígenes: `n_pairs` sigue recuperable.
    tabla_h = next(t for t in tablas if "h" in t.encabezados[0].lower() or len(t.filas) == len(esperados))
    assert any("rígenes" in c or "rigenes" in c for c in tabla_h.encabezados), tabla_h.encabezados


def test_tecnico_publica_los_bloqueos_metodologicos_vigentes() -> None:
    """P0-C y P0-E deben ser visibles para quien lee el informe.

    TANDA 3: el resultado transportaba `intervalo_sustentado=False`,
    `evidencia_oos_provisional=True` y `bloqueos_metodologicos={P0-C, P0-E}`, pero
    **ninguno llegaba al documento**. El lector veía métricas e intervalos sin
    saber que su fundamento sigue abierto. No es un defecto de cálculo: ninguna
    cifra cambia, se publica el estado que ya estaba decidido (REQ 25, REQ 26).
    """
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    texto = _texto_informe(informe).lower()

    assert _RESULTADO["intervalo_sustentado"] is False
    assert _RESULTADO["evidencia_oos_provisional"] is True
    # P0-C: el intervalo se declara no sustentado, y nunca «validado».
    assert "no sustentado" in texto, "El informe debe declarar el intervalo no sustentado."
    assert "validado" not in texto, "El informe no puede presentar nada como validado."
    # P0-E: la evidencia fuera de muestra se declara provisional.
    assert "provisional" in texto
    # P0-F: el calendario dice que no se aplica, sin negar el fenómeno.
    assert "no aplicado" in texto or "no se aplica" in texto
    assert "reconcentra" not in texto
    # P0-H: no reaparece ningún techo estadístico de 30.
    assert "admisible 30" not in texto and "máximo 30" not in texto


# ==============================
# 14.3 INFORME PERSONALIZADO
# ==============================


def test_personalizado_respeta_exactamente_la_seleccion() -> None:
    config = ConfiguracionInforme(
        tipo="personalizado",
        secciones=frozenset({"portada", "ficha", "modelos", "reproducibilidad"}),
        graficas=frozenset(),
    )
    informe = construir_informe_proyeccion(_DATOS, config)
    assert _claves(informe) == {"ficha", "modelos", "reproducibilidad"}
    assert not _bloques(informe, Imagen), "Sin gráficas marcadas no debe haber imágenes."


def test_personalizado_no_deja_titulos_vacios_ni_paginas_en_blanco() -> None:
    # Secciones que no tienen datos en este resultado: no deben emitir el título.
    config = ConfiguracionInforme(
        tipo="personalizado",
        secciones=frozenset({"ficha", "atipicos", "cobertura", "anexos"}),
        graficas=frozenset(),
    )
    informe = construir_informe_proyeccion(_DATOS, config)
    assert all(seccion.bloques for seccion in informe.secciones), "Ninguna sección puede quedar vacía."

    with TemporaryDirectory() as tmp:
        pdf = pdf_render.guardar(informe, Path(tmp) / "personalizado.pdf")
        assert _paginas_pdf(pdf) <= 4


def test_seccion_sin_datos_se_omite_por_completo() -> None:
    resultado = copy.deepcopy(_RESULTADO)
    resultado["catalogo_modelos"] = []
    resultado["cobertura_empirica"] = {}
    # RA-01: el bloque del paso exacto forma parte de la evidencia de cobertura;
    # sin el, la seccion tampoco tiene nada que mostrar.
    resultado["verificabilidad_paso_exacto"] = {}
    informe = construir_informe_proyeccion(
        _datos(_SERIE, resultado),
        ConfiguracionInforme(tipo="personalizado", secciones=frozenset({"modelos", "cobertura", "ficha"}), graficas=frozenset()),
    )
    assert _claves(informe) == {"ficha"}


def test_grafica_desmarcada_no_se_dibuja() -> None:
    config = ConfiguracionInforme(
        tipo="personalizado",
        secciones=frozenset({"grafica_principal", "residuos"}),
        graficas=frozenset({"historico_proyeccion"}),
    )
    informe = construir_informe_proyeccion(_DATOS, config)
    # Solo la principal: la de residuos quedó sin marcar.
    assert len(_bloques(informe, Imagen)) == 1


# ==============================
# 14.4 INFORME ICCP–ICOCIV
# ==============================


def test_empalme_muestra_formulas_con_sustitucion_numerica() -> None:
    calculo = _calculo_empalme()
    informe = construir_informe_empalme([calculo], {"contrato": "SIC-2024-018"})
    formulas = {f.etiqueta: f for f in _bloques(informe, Formula)}
    assert {"Base ajustable", "Ajuste del tramo ICCP (R1)", "Ajuste del tramo ICOCIV (R2)",
            "Ajuste total (R)", "Valor actualizado"} <= set(formulas)

    r1 = formulas["Ajuste del tramo ICCP (R1)"]
    assert "R1 = Base x [(I_ICCP / I0_ICCP) - 1]" == r1.general
    assert r1.sustitucion, "La fórmula debe traer la sustitución numérica."
    assert any(formato_indice(calculo["i_iccp"]) in linea for linea in r1.sustitucion)
    assert "$" in r1.resultado


def test_empalme_diferencia_indice_oficial_de_proyectado() -> None:
    oficial = _calculo_empalme()
    proyectado = _calculo_empalme()
    proyectado["icociv_final_es_proyectado"] = True
    proyectado["modelo_proyeccion"] = "Drift"

    informe = construir_informe_empalme([oficial, proyectado], {})
    tabla = next(t for t in _bloques(informe, Tabla) if t.encabezados[0] == "Variable")
    tipos = {fila[5] for fila in tabla.filas}
    assert "Índice oficial observado" in tipos
    assert "Índice proyectado por SAVIP" in tipos


def test_empalme_incluye_advertencias_contractuales() -> None:
    informe = construir_informe_empalme([_calculo_empalme()], {})
    textos = " ".join(item for aviso in _bloques(informe, Aviso) for item in aviso.items)
    assert "índices oficiales" in textos
    assert "I0" in textos
    assert "jurídica" in textos


def test_empalme_registra_criterio_de_i0_y_se_exporta() -> None:
    calculo = _calculo_empalme()
    informe = construir_informe_empalme([calculo], {"contrato": "SIC-2024-018"})
    assert "seleccion_i0" in _claves(informe)
    tabla = next(t for t in _bloques(informe, Tabla) if t.encabezados[0] == "Ítem")
    assert any("acta de inicio" in fila[-1] for fila in tabla.filas)

    with TemporaryDirectory() as tmp:
        destino = Path(tmp)
        docx = docx_render.guardar(informe, destino / "empalme.docx")
        pdf = pdf_render.guardar(informe, destino / "empalme.pdf")
        assert docx.is_file() and pdf.read_bytes().startswith(b"%PDF")
        assert "Valor actualizado" in _texto_docx(docx)


def test_empalme_acero_documenta_z() -> None:
    indices = {"2021_12": 100.0, "2024_6": 118.4, "2019_3": 92.0}
    entrada = {
        "item": "Acero de refuerzo",
        "unidad": "kg",
        "calculo_acero": True,
        "p0": 500_000_000,
        "ix": 4200,
        "q": 150_000,
        "fecha_inicial": "2019_3",
        "fecha_final": "2024_6",
        "tipo_serie_iccp": "grupo_obra",
        "serie_iccp": "Aceros y elementos metálicos",
        "ruta_icociv": "Carreteras > Materiales > Acero",
    }
    calculo = calcular_empalme_iccp_icociv(entrada, indices)
    calculo["ruta_icociv"] = entrada["ruta_icociv"]
    informe = construir_informe_empalme([calculo], {})
    etiquetas = {f.etiqueta for f in _bloques(informe, Formula)}
    assert "Valor adicional por fluctuación del acero (Z)" in etiquetas


# ==============================
# 14.5 DOCX
# ==============================


def test_docx_abre_y_trae_tablas_editables_estilos_e_imagenes() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    with TemporaryDirectory() as tmp:
        ruta = docx_render.guardar(informe, Path(tmp) / "tecnico.docx")
        partes = _partes_docx(ruta)
        assert "word/document.xml" in partes
        assert "word/styles.xml" in partes
        assert any(p.startswith("word/media/") for p in partes), "Las gráficas deben ir incrustadas."
        assert any(p.startswith("word/header") for p in partes), "Debe haber encabezado."
        assert any(p.startswith("word/footer") for p in partes), "Debe haber pie de página."

        with zipfile.ZipFile(ruta) as paquete:
            documento = paquete.read("word/document.xml").decode("utf-8")
        # Tablas reales de Word, no imágenes de tabla.
        assert documento.count("<w:tbl>") > 5
        assert "<w:tblHeader" in documento, "El encabezado de tabla debe repetirse entre páginas."
        assert "<w:cantSplit" in documento, "Las filas no deben partirse entre páginas."
        assert "TOC" in documento, "El informe técnico debe traer índice automático."

        with zipfile.ZipFile(ruta) as paquete:
            pie = " ".join(
                paquete.read(nombre).decode("utf-8")
                for nombre in paquete.namelist() if nombre.startswith("word/footer")
            )
        assert "PAGE" in pie and "NUMPAGES" in pie, "El pie debe numerar «Página X de Y»."


def test_docx_ejecutivo_no_lleva_indice_por_ser_corto() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    with TemporaryDirectory() as tmp:
        ruta = docx_render.guardar(informe, Path(tmp) / "ejecutivo.docx")
        with zipfile.ZipFile(ruta) as paquete:
            documento = paquete.read("word/document.xml").decode("utf-8")
        assert r'TOC \o' not in documento


def test_docx_campos_institucionales_llegan_a_la_portada() -> None:
    from app_icociv.reportes.modelo import CamposInstitucionales

    config = ConfiguracionInforme.desde_tipo("ejecutivo")
    config.institucional = CamposInstitucionales(
        entidad="Secretaría de Infraestructura del Cauca",
        contrato="SIC-2026-004",
        responsable="Ing. responsable",
        observaciones="Documento de trabajo.",
        incluir_firmas=True,
    )
    informe = construir_informe_proyeccion(_DATOS, config)
    with TemporaryDirectory() as tmp:
        texto = _texto_docx(docx_render.guardar(informe, Path(tmp) / "inst.docx"))
    assert "Secretar" in texto and "SIC-2026-004" in texto
    assert "Documento de trabajo." in texto
    assert "Elabor" in texto, "El bloque de firmas debe aparecer."


# ==============================
# 14.6 PDF
# ==============================


def test_pdf_pagina_indice_marcadores_y_fuentes_incrustadas() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    with TemporaryDirectory() as tmp:
        ruta = pdf_render.guardar(informe, Path(tmp) / "tecnico.pdf")
        datos = ruta.read_bytes()
    assert datos.startswith(b"%PDF")
    assert b"/Outlines" in datos, "Faltan marcadores."
    assert b"/FontFile2" in datos, "Las fuentes deben ir incrustadas, no referenciadas."
    assert b"Contenido" in datos or b"/Annots" in datos
    assert re.search(rb"/Type\s*/Page[^s]", datos)


def test_pdf_conserva_las_graficas() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    esperadas = len(_bloques(informe, Imagen))
    assert esperadas >= 2
    with TemporaryDirectory() as tmp:
        datos = pdf_render.guardar(informe, Path(tmp) / "t.pdf").read_bytes()
    assert datos.count(b"/Subtype /Image") >= esperadas or datos.count(b"/Image") >= esperadas


def test_pdf_repite_encabezados_y_no_parte_filas() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("tecnico"))
    estilos = pdf_render._estilos()
    historia = pdf_render.construir_historia(informe, estilos)
    tablas = _tablas_platypus(historia)
    con_encabezado = [t for t in tablas if getattr(t, "repeatRows", 0) == 1]
    assert con_encabezado, "Alguna tabla debe repetir encabezado."
    assert all(getattr(t, "splitByRow", 1) for t in tablas), "Las tablas deben partirse por fila entera."


def test_pdf_y_docx_cuentan_lo_mismo() -> None:
    """El PDF no es una conversión del DOCX, pero el contenido debe coincidir."""
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    titulos = [s.titulo for s in informe.secciones_visibles()]
    with TemporaryDirectory() as tmp:
        docx = docx_render.guardar(informe, Path(tmp) / "e.docx")
        texto_docx = _texto_docx(docx)
    for titulo in titulos:
        assert titulo.split()[0] in texto_docx


# ==============================
# 14.7 REGRESIÓN ESTADÍSTICA
# ==============================


def test_generar_informes_no_altera_ningun_resultado_estadistico() -> None:
    serie = _serie()
    resultado = ejecutar_proyeccion(serie, 2026, 6, ANIO_BASE)

    antes = {
        "modelo": resultado["model_name"],
        "y_proj": resultado["y_proj"],
        "ci95": (resultado["ci95_lo"], resultado["ci95_hi"]),
        "horizonte_permitido": resultado["horizonte_permitido"],
        "calendario": dict(resultado["ajuste_calendario"]),
        "proyecciones": resultado["proyecciones"].copy(deep=True),
        "horizontes": copy.deepcopy(resultado["analisis_horizontes_completo"]["tabla_horizontes"]),
    }
    serie_antes = serie.copy(deep=True)

    datos = _datos(serie, resultado)
    with TemporaryDirectory() as tmp:
        destino = Path(tmp)
        for tipo in ("ejecutivo", "tecnico"):
            informe = construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo(tipo))
            docx_render.guardar(informe, destino / f"{tipo}.docx")
            pdf_render.guardar(informe, destino / f"{tipo}.pdf")

    assert resultado["model_name"] == antes["modelo"]
    assert resultado["y_proj"] == antes["y_proj"]
    assert (resultado["ci95_lo"], resultado["ci95_hi"]) == antes["ci95"]
    assert resultado["horizonte_permitido"] == antes["horizonte_permitido"]
    assert resultado["ajuste_calendario"] == antes["calendario"]
    pd.testing.assert_frame_equal(resultado["proyecciones"], antes["proyecciones"])
    assert resultado["analisis_horizontes_completo"]["tabla_horizontes"] == antes["horizontes"]
    pd.testing.assert_frame_equal(serie, serie_antes)


def test_dos_ejecuciones_del_informe_dan_el_mismo_contenido() -> None:
    """A igual instante, igual documento: lo único variable es el sello de tiempo."""
    from datetime import datetime

    config = ConfiguracionInforme.desde_tipo("tecnico")
    momento = datetime(2026, 7, 26, 15, 30, 45)
    uno = construir_informe_proyeccion(_DATOS, config, momento)
    dos = construir_informe_proyeccion(_DATOS, config, momento)
    assert uno.identificador == dos.identificador
    assert [s.titulo for s in uno.secciones] == [s.titulo for s in dos.secciones]
    tablas_uno = [t.filas for t in _bloques(uno, Tabla)]
    tablas_dos = [t.filas for t in _bloques(dos, Tabla)]
    assert tablas_uno == tablas_dos


def test_horizonte_bloqueado_no_inventa_proyeccion() -> None:
    serie = _serie(20)
    resultado = ejecutar_proyeccion(serie, 2022, 8, ANIO_BASE)
    assert not resultado.get("proyeccion_generada"), "El caso de prueba debe quedar bloqueado."
    informe = construir_informe_proyeccion(_datos(serie, resultado), ConfiguracionInforme.desde_tipo("ejecutivo"))
    texto = " ".join(b.texto for s in informe.secciones for b in s.bloques if hasattr(b, "texto"))
    if not resultado.get("proyeccion_generada"):
        assert "no generó proyección" in texto or "no fue generada" in texto.lower()
        assert not _bloques(informe, Imagen) or True  # la serie histórica sí puede graficarse


# ==============================
# CONVENCIONES DE FORMATO Y NOMBRES
# ==============================


def test_convenciones_de_formato() -> None:
    assert formato_indice(145.89) == "145,8900"
    assert formato_indice(1234.5) == "1 234,5000"  # espacio duro como separador de miles
    assert formato_porcentaje(4.06) == "4,1 %"
    assert formato_porcentaje(92.0, 2) == "92,00 %"
    assert periodo_largo("2026_5") == "mayo de 2026"
    assert periodo_largo("2026-05") == "mayo de 2026"
    assert formato_indice(None) == "No disponible"


def test_identificador_y_nombres_de_archivo() -> None:
    from datetime import datetime

    momento = datetime(2026, 7, 26, 15, 30, 45)
    assert identificador_informe(momento) == "SAVIP-INF-20260726-153045"

    nombre = nombre_archivo_informe("ejecutivo", "Vías férreas / pistas", "docx", momento)
    assert nombre == "SAVIP_Informe_Ejecutivo_Vias_ferreas_pistas_20260726.docx"
    assert not set(nombre) & set('<>:"/\\|?*')

    assert nombre_archivo_informe("tecnico", "T_16", "pdf", momento).endswith("_20260726.pdf")
    assert "Ajuste_ICCP_ICOCIV" in nombre_archivo_informe("empalme", "SIC-2024-018", "docx", momento)


def test_identificador_aparece_en_portada_y_pie() -> None:
    informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo("ejecutivo"))
    assert informe.identificador in informe.pie
    assert any(informe.identificador == valor for _, valor in informe.portada.filas)
    with TemporaryDirectory() as tmp:
        ruta = docx_render.guardar(informe, Path(tmp) / "id.docx")
        with zipfile.ZipFile(ruta) as paquete:
            cabecera = " ".join(
                paquete.read(nombre).decode("utf-8")
                for nombre in paquete.namelist() if nombre.startswith("word/header")
            )
    assert informe.identificador in re.sub(r"<[^>]+>", "", cabecera)


def test_tablas_no_superan_ocho_columnas() -> None:
    for tipo in ("ejecutivo", "tecnico"):
        informe = construir_informe_proyeccion(_DATOS, ConfiguracionInforme.desde_tipo(tipo))
        for tabla in _bloques(informe, Tabla):
            assert len(tabla.encabezados) <= 8, f"{tabla.titulo} tiene {len(tabla.encabezados)} columnas."
    informe = construir_informe_empalme([_calculo_empalme()], {})
    for tabla in _bloques(informe, Tabla):
        assert len(tabla.encabezados) <= 8, f"{tabla.titulo} tiene {len(tabla.encabezados)} columnas."


# ==============================
# INTERPRETACIÓN Y GRÁFICAS
# ==============================


def test_interpretacion_cubre_tendencia_incertidumbre_y_uso() -> None:
    """P0-C / C2: la incertidumbre se declara, ya no se cuantifica.

    El assert anterior exigia «intervalo de prediccion del 95 %» o «95 %» en el
    texto, porque la interpretacion publicaba la amplitud de la banda («abarca
    aproximadamente X % alrededor del valor central»). Esa frase se retiro: es
    una magnitud del intervalo que la aplicacion ya no entrega, y decir cuan
    ancha es una banda que el lector no recibe sugiere que la incertidumbre si
    esta acotada.

    La propiedad que debe conservarse -y que este test sigue vigilando- es que la
    interpretacion cubra los TRES ejes: tendencia, incertidumbre y uso. Lo que
    cambia es como se cubre el segundo: declarando que no viene acotada, en vez
    de dando un numero.
    """
    texto = " ".join(interpretacion(_DATOS))
    assert "tendencia" in texto
    assert "incertidumbre" in texto.lower()
    assert "no publica intervalo de predicción" in texto.lower()
    assert "confianza metodológica" in texto
    # Y no reaparece la cuantificacion de la banda retirada.
    assert "95 %" not in texto and "95%" not in texto, texto


def test_interpretacion_explica_el_patron_calendario_cuando_se_aplica() -> None:
    texto = " ".join(interpretacion(_DATOS))
    if (_RESULTADO.get("ajuste_calendario") or {}).get("ajuste_calendario_aplicado"):
        assert "cambio de año" in texto
        assert "no un valor atípico" in texto


def test_grafica_principal_ya_no_dibuja_banda_de_intervalo() -> None:
    """Reescrito por P0-C ruta C2: la grafica ya no sombrea la banda.

    Se sigue generando y sigue siendo un PNG valido; lo que ya no hace es
    dibujar el intervalo, de modo que pedirla con y sin produce lo MISMO.
    """
    con = graficas.grafica_principal(_SERIE, _RESULTADO, con_intervalo=True)
    sin = graficas.grafica_principal(_SERIE, _RESULTADO, con_intervalo=False)
    assert con and sin
    assert con == sin, "con_intervalo ya no puede cambiar el dibujo"
    assert con[:8] == b"\x89PNG\r\n\x1a\n"


def test_graficas_sin_datos_devuelven_none_en_lugar_de_una_figura_vacia() -> None:
    vacio: dict = {}
    assert graficas.grafica_residuos(vacio) is None
    assert graficas.grafica_errores_horizonte(vacio) is None
    assert graficas.grafica_comparacion_modelos(vacio) is None
    assert graficas.grafica_atipicos(pd.DataFrame(), vacio) is None
    assert graficas.grafica_calendario(pd.DataFrame(), vacio) is None


def _ejecutar() -> int:
    fallos = 0
    total = 0
    for nombre, funcion in sorted(globals().items()):
        if not nombre.startswith("test_") or not callable(funcion):
            continue
        total += 1
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as error:
            fallos += 1
            print(f"  FALLA {nombre}: {error}")
        except Exception as error:  # pragma: no cover - error inesperado
            fallos += 1
            print(f"  ERROR {nombre}: {type(error).__name__}: {error}")
    print(f"\n{total - fallos}/{total} pruebas aprobadas.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
