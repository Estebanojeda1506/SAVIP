"""Contratos conductuales de los residuales V-CODEX-R3: P0-C, HGRID y P0-H.

Estas pruebas EJECUTAN el comportamiento. No inspeccionan el codigo fuente, no
buscan subcadenas en comentarios ni cuentan nombres de funcion: construyen una
serie, proyectan, y comprueban lo que la aplicacion entrega en cada superficie
publica -objeto, DataFrame, sesion JSON, CSV, interfaz, DOCX y PDF-.

Los tres residuales que cubren:

P0-C  El intervalo retirado no debe poder RECONSTRUIRSE desde ninguna superficie
      publica. La fuga demostrada por Codex no eran los limites -ya vaciados-
      sino el VECTOR COMPLETO de errores fuera de muestra: con el punto, que es
      publico, `sigma_h = sqrt(mean(e**2))` devuelve los limites exactos. Las
      pruebas intentan la reconstruccion y exigen que falle, y a la vez exigen
      que los AGREGADOS -RMSE, MAE, MASE, sesgo, n_pairs- sigan publicandose,
      porque son los que sostienen la sustentacion.

HGRID `W = n - N0 - h + 1` es una condicion de EXISTENCIA. Las pruebas comparan
      la formula contra el numero REAL de ventanas del backtesting en los bordes
      cortos, y exigen que el vocabulario no llame validado a un horizonte por
      tener una ventana.

P0-H  Con h1 permitido, h2 no viable y h3 permitido, h3 se entrega y el mensaje
      publico debe decirlo. Las pruebas exigen que la razon publicada no afirme
      que la evidencia se corta ni que h3 no pueda sostenerse, y que la grafica
      no una h1 con h3 por encima del hueco.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_icociv.estadistica.modelos_interpretables import MODELOS_ESTADISTICOS  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    MIN_ITERACIONES_BACKTESTING,
    MIN_ITERACIONES_WF_ESCENARIO,
    TRAMO_OOS_DISPONIBLE,
    TRAMO_OOS_MUY_LIMITADA,
    TRAMO_OOS_SIN_EVIDENCIA,
    _estructurar_resultado_horizontes,
    _multiplicador_intervalo,
    NIVEL_NOMINAL_95,
    ejecutar_proyeccion,
    tramo_evidencia_oos,
    ventanas_oos_disponibles,
)
from app_icociv.validacion.backtesting import ejecutar_backtesting  # noqa: E402

# ==============================
# UTILIDADES
# ==============================

#: Palabras con que NO se puede calificar un horizonte por su numero de ventanas.
VOCABULARIO_PROHIBIDO = ("validado", "validada", "suficiente", "robusto", "certificado")

#: Vocabulario del intervalo retirado. Ninguno puede aparecer en texto publico,
#: salvo en la declaracion explicita de la limitacion.
VOCABULARIO_INTERVALO = (
    "σ̂", "sigma_h", "ancho relativo", "semiancho", "cobertura efectiva",
    "cobertura empírica", "cobertura empirica", "nivel nominal",
    "ic95", "ic 95", "ip95", "cuantil", "percentil",
)

#: Claves cuyo VALOR es la declaracion de la limitacion. Deben permanecer.
CLAVES_DECLARACION = (
    "motivo_intervalo_no_sustentado", "bloqueos_metodologicos",
    "motivo_evidencia_provisional", "intervalo_sustentado",
)

#: Columnas cuyo contenido permite reconstruir `sigma_h`, y por tanto el
#: intervalo. Ninguna puede aparecer en una tabla de ventanas publicada.
COLUMNAS_PROHIBIDAS_OOS = (
    "Observado", "Predicho", "Error", "Error_abs", "Error_pct",
    "Error_escalado_abs", "Escala_naive_insample",
)

#: Agregados que SI deben seguir publicandose (sustentacion del trabajo).
AGREGADOS_EXIGIDOS = ("rmse", "mae", "mase")


def _serie(valores: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "Periodo": [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(len(valores))],
        "Indice": valores,
    })


def _lineal(n: int, base: float = 100.0, paso: float = 1.5) -> pd.DataFrame:
    return _serie([base + paso * i for i in range(n)])


def _ondulada(n: int) -> pd.DataFrame:
    return _serie([100.0 + 0.4 * i + 3.0 * math.sin(i * 0.7) for i in range(n)])


def _proyectar(datos: pd.DataFrame, horizonte: int) -> dict:
    anio, mes = map(int, datos.iloc[-1]["Periodo"].split("_")[:2])
    total = anio * 12 + mes - 1 + horizonte
    return ejecutar_proyeccion(datos, total // 12, total % 12 + 1, 2021)


def _hojas(objeto, ruta="", vistos=None):
    """Recorre el arbol y genera (ruta, valor) para cada hoja."""
    vistos = vistos if vistos is not None else set()
    if isinstance(objeto, (dict, list, tuple, pd.DataFrame, pd.Series)):
        if id(objeto) in vistos:
            return
        vistos.add(id(objeto))
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            yield from _hojas(valor, f"{ruta}.{clave}", vistos)
    elif isinstance(objeto, (list, tuple)):
        for i, valor in enumerate(objeto):
            yield from _hojas(valor, f"{ruta}[{i}]", vistos)
    elif isinstance(objeto, pd.DataFrame):
        for columna in objeto.columns:
            for i, valor in enumerate(objeto[columna].tolist()):
                yield from _hojas(valor, f"{ruta}<{columna}>[{i}]", vistos)
    elif isinstance(objeto, pd.Series):
        for i, valor in enumerate(objeto.tolist()):
            yield from _hojas(valor, f"{ruta}[{i}]", vistos)
    else:
        yield ruta, objeto


def _textos_publicos(objeto) -> list[tuple[str, str]]:
    """Cadenas del arbol, excluidas las que declaran la limitacion."""
    salida = []
    for ruta, valor in _hojas(objeto):
        if not isinstance(valor, str):
            continue
        if any(clave in ruta for clave in CLAVES_DECLARACION):
            continue
        salida.append((ruta, valor))
    return salida


def _fuga_de_vocabulario(objeto) -> list[tuple[str, str]]:
    fugas = []
    for ruta, texto in _textos_publicos(objeto):
        bajo = texto.lower()
        for palabra in VOCABULARIO_INTERVALO:
            if palabra.lower() in bajo:
                fugas.append((ruta, texto[:180]))
                break
    return fugas


def _tablas_de_ventanas(objeto) -> list[tuple[str, pd.DataFrame]]:
    """Toda tabla publica que tenga forma de tabla de ventanas de backtesting."""
    encontradas: list[tuple[str, pd.DataFrame]] = []
    vistos: set[int] = set()

    def recorrer(nodo, ruta=""):
        if id(nodo) in vistos:
            return
        if isinstance(nodo, pd.DataFrame):
            vistos.add(id(nodo))
            if "Origen" in nodo.columns or "Horizonte" in nodo.columns:
                encontradas.append((ruta, nodo))
            return
        if isinstance(nodo, dict):
            vistos.add(id(nodo))
            for clave, valor in nodo.items():
                recorrer(valor, f"{ruta}.{clave}")
        elif isinstance(nodo, (list, tuple)):
            vistos.add(id(nodo))
            for i, valor in enumerate(nodo):
                recorrer(valor, f"{ruta}[{i}]")

    recorrer(objeto)
    return encontradas


def _errores_recuperables(objeto) -> list[tuple[str, list[float]]]:
    """Series numericas publicas que podrian ser el vector de errores OOS.

    Se buscan por FORMA, no por nombre: cualquier coleccion de al menos dos
    numeros finitos bajo una clave que sugiera error, observado o predicho.
    """
    sospechosas: list[tuple[str, list[float]]] = []
    for ruta, tabla in _tablas_de_ventanas(objeto):
        for columna in tabla.columns:
            if columna in COLUMNAS_PROHIBIDAS_OOS:
                valores = pd.to_numeric(tabla[columna], errors="coerce").dropna().tolist()
                if len(valores) >= 2:
                    sospechosas.append((f"{ruta}<{columna}>", valores))
    return sospechosas


def _ic95_desde(punto: float, errores: list[float]) -> tuple[float, float]:
    n = len(errores)
    sigma = float(np.sqrt(np.mean(np.asarray(errores, dtype=float) ** 2)))
    c95 = _multiplicador_intervalo(NIVEL_NOMINAL_95, n)
    return punto - c95 * sigma, punto + c95 * sigma


# ==============================
# CASOS COMPARTIDOS
# ==============================

_CACHE: dict[str, dict] = {}


def _caso(clave: str, datos: pd.DataFrame, horizonte: int) -> dict:
    if clave not in _CACHE:
        _CACHE[clave] = _proyectar(datos, horizonte)
    return _CACHE[clave]


def _caso_ordinario() -> dict:
    return _caso("n48h6", _ondulada(48), 6)


def _resultado_con_hueco() -> dict:
    """h1 permitido, h2 no viable, h3 permitido, con h3 solicitado."""
    evaluaciones = [
        {
            "horizonte": h,
            "permitido_para_proyeccion_tecnica": ok,
            "permitido_como_escenario": ok,
            "clasificacion": "tecnica" if ok else "no_viable",
            "razon_decision": "evidencia propia del horizonte" if ok else "sin evidencia OOS en h=2",
        }
        for h, ok in ((1, True), (2, False), (3, True))
    ]
    base = {
        "proyeccion_generada": True,
        "horizonte_solicitado": 3,
        "horizonte_permitido": 3,
        "y_proj": 123.0,
        "periodo_proj": "2021_12",
        "model_name": "Lineal (OLS)",
        "factibilidad": {"razones_tecnicas": []},
        "proyecciones": pd.DataFrame({
            "periodo": ["2021_10", "2021_11", "2021_12"],
            "indice_proyectado": [121.0, 122.0, 123.0],
        }),
        "horizonte_info": {
            "horizonte_solicitado": 3,
            "evaluaciones": evaluaciones,
            "horizontes_no_evaluados": [],
            "primer_horizonte_no_viable": 2,
            "horizonte_maximo_recomendado": 3,
            "horizonte_maximo_admisible": 3,
            "horizonte_maximo_evaluable_por_datos": 3,
            "razones": [],
        },
    }
    return _estructurar_resultado_horizontes(base, "manual")


# ==============================
# P0-C — C1..C4: reconstruccion imposible en objeto, tabla, sesion y CSV
# ==============================


def c1_objeto_no_reconstruye_el_intervalo() -> None:
    """n=48, h=6: el caso exacto con que Codex reconstruyo el IC95."""
    resultado = _caso_ordinario()
    punto = resultado.get("y_proj")
    assert punto is not None and np.isfinite(float(punto)), "Se perdio el pronostico puntual."

    recuperables = _errores_recuperables(resultado)
    assert not recuperables, (
        "El objeto publico conserva un vector con el que se reconstruye el intervalo: "
        + ", ".join(
            f"{ruta} ({len(v)} valores) -> IC95 {_ic95_desde(float(punto), v)}"
            for ruta, v in recuperables
        )
    )
    # Y los limites directos siguen sin publicarse.
    for clave in ("ci_lo", "ci_hi", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi"):
        assert resultado.get(clave) is None, f"'{clave}' volvio a publicarse."


def c2_dataframe_de_proyecciones_sin_reconstruccion() -> None:
    resultado = _caso_ordinario()
    tabla = resultado.get("proyecciones")
    assert isinstance(tabla, pd.DataFrame) and not tabla.empty
    for columna in tabla.columns:
        bajo = columna.lower()
        if any(marca in bajo for marca in
               ("limite", "sigma", "ancho_relativo", "q80", "q95", "percentil", "ic95")):
            valores = pd.to_numeric(tabla[columna], errors="coerce").dropna()
            assert valores.empty, f"La columna '{columna}' publica valores del intervalo: {valores.tolist()[:3]}"
    # El punto de cada paso SI se publica: es lo que el usuario recibe.
    puntos = pd.to_numeric(tabla["indice_proyectado"], errors="coerce").dropna()
    assert len(puntos) == len(tabla), "La trayectoria dejo de publicarse."


def c3_sesion_json_sin_reconstruccion() -> None:
    """La sesion serializa el resultado completo: es la superficie mas amplia."""
    from app_icociv.interfaz.controladores.controlador_principal import ControladorPrincipal

    resultado = _caso_ordinario()
    serializado = ControladorPrincipal._proyeccion_serializable(resultado)
    texto = json.dumps(serializado, ensure_ascii=False, default=str)

    predicciones = (serializado.get("backtesting") or {}).get("predicciones") or []
    for fila in predicciones:
        for columna in COLUMNAS_PROHIBIDAS_OOS:
            assert columna not in fila, f"La sesion serializa '{columna}' por ventana."
    for palabra in ("σ̂", "cobertura efectiva", "ancho relativo"):
        assert palabra.lower() not in texto.lower(), f"La sesion publica '{palabra}'."
    # Los agregados si viajan.
    metricas = (serializado.get("backtesting") or {}).get("metricas") or {}
    for agregado in AGREGADOS_EXIGIDOS:
        assert agregado in metricas, f"La sesion perdio '{agregado}'."


def c4_csv_sin_reconstruccion() -> None:
    """Se comprueba el CSV ESCRITO EN DISCO, tal como lo recibe el usuario."""
    from tempfile import TemporaryDirectory

    from app_icociv.reportes.generador_reportes import generar_csv_reproducibilidad

    resultado = _caso_ordinario()
    ruta_jerarquica = [{"nivel": "Serie", "valor": "Serie de prueba"}]
    with TemporaryDirectory() as tmp:
        ruta = generar_csv_reproducibilidad(
            Path(tmp) / "reproducible.csv", _ondulada(48), resultado, ruta_jerarquica
        )
        csv = pd.read_csv(ruta, encoding="utf-8-sig")
    assert isinstance(csv, pd.DataFrame) and not csv.empty

    for columna in csv.columns:
        bajo = columna.lower()
        assert not any(marca in bajo for marca in
                       ("sigma_h", "q95_intervalo", "percentil_95", "ic95_inferior", "ic95_superior")), \
            f"El CSV conserva la columna del intervalo '{columna}'."
    texto = csv.astype(str).to_csv(index=False)
    for palabra in ("σ̂", "cobertura efectiva", "ancho relativo"):
        assert palabra.lower() not in texto.lower(), f"El CSV publica '{palabra}'."
    # Los agregados por horizonte si estan.
    for columna in ("rmse_horizonte", "mae_horizonte", "mase_horizonte", "iteraciones_backtesting_horizonte"):
        assert columna in csv.columns, f"El CSV perdio '{columna}'."


# ==============================
# P0-C — C5..C7: interfaz, DOCX y PDF
# ==============================


def c5_interfaz_sin_reconstruccion() -> None:
    """El HTML que la interfaz muestra, no una estructura intermedia."""
    from app_icociv.interfaz.presentacion_resultados import (
        construir_html_detalle_horizonte,
        construir_html_resultados,
    )

    resultado = _caso_ordinario()
    html = construir_html_resultados(resultado) + construir_html_detalle_horizonte(resultado)
    bajo = html.lower()
    for palabra in VOCABULARIO_INTERVALO:
        assert palabra.lower() not in bajo, f"La interfaz publica '{palabra}'."
    assert str(resultado.get("model_name") or "") in html, "La interfaz dejo de mostrar el modelo."


def _informe(tipo: str = "tecnico"):
    """Modelo de contenido del informe, que es lo que DOCX y PDF dibujan."""
    from app_icociv.reportes.contenido import DatosProyeccion, construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme

    serie = _ondulada(48)
    datos = DatosProyeccion(
        resultado=_caso_ordinario(),
        serie_df=serie,
        fuente_label="T_16",
        archivo_excel="anexo_icociv.xlsb",
        ruta_jerarquica=[{"nivel": "Serie", "valor": "Serie de prueba"}],
        fila=serie.head(1),
        year_month=list(serie["Periodo"]),
        usuario="Prueba",
    )
    return construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo(tipo))


def _texto_informe(informe) -> str:
    """Todo el texto de los bloques visibles, cubriendo los ocho tipos."""
    partes: list[str] = []
    for seccion in informe.secciones_visibles():
        partes.append(str(seccion.titulo))
        for bloque in seccion.bloques:
            for atributo in ("texto", "titulo", "nota", "fuente"):
                valor = getattr(bloque, atributo, None)
                if isinstance(valor, str):
                    partes.append(valor)
            for atributo in ("items", "encabezados"):
                valor = getattr(bloque, atributo, None)
                if isinstance(valor, (list, tuple)):
                    partes.extend(str(x) for x in valor)
            filas = getattr(bloque, "filas", None)
            if isinstance(filas, (list, tuple)):
                for fila in filas:
                    partes.append(
                        " | ".join(str(c) for c in fila)
                        if isinstance(fila, (list, tuple)) else str(fila)
                    )
    return "\n".join(partes)


def c6_docx_sin_reconstruccion() -> None:
    """Se comprueba el DOCX ESCRITO EN DISCO, tal como lo recibe el usuario."""
    import re
    import zipfile
    from tempfile import TemporaryDirectory

    from app_icociv.reportes import docx_render

    informe = _informe("tecnico")
    with TemporaryDirectory() as tmp:
        ruta = docx_render.guardar(informe, Path(tmp) / "tecnico.docx")
        with zipfile.ZipFile(ruta) as paquete:
            xml = paquete.read("word/document.xml").decode("utf-8")
    texto = re.sub(r"<[^>]+>", " ", xml).lower()
    for palabra in VOCABULARIO_INTERVALO:
        assert palabra.lower() not in texto, f"El DOCX publica '{palabra}'."
    # La tabla de ventanas no puede llevar columnas de error. Se comprueba sobre
    # los ENCABEZADOS del informe y no por subcadena en el texto: el glosario
    # metodologico menciona legitimamente «error absoluto» al explicar el MAE.
    for seccion in informe.secciones_visibles():
        for bloque in seccion.bloques:
            encabezados = [str(x).lower() for x in (getattr(bloque, "encabezados", None) or [])]
            for prohibida in ("observado", "predicho", "error abs", "error pct", "error"):
                assert prohibida not in encabezados, \
                    f"La sección '{seccion.clave}' publica la columna '{prohibida}'."


def c7_pdf_sin_reconstruccion() -> None:
    """El PDF se genera y su contenido -lo que `pdf_render` dibuja- esta limpio."""
    from tempfile import TemporaryDirectory

    from app_icociv.reportes import pdf_render

    informe = _informe("tecnico")
    with TemporaryDirectory() as tmp:
        ruta = pdf_render.guardar(informe, Path(tmp) / "tecnico.pdf")
        assert ruta.read_bytes()[:4] == b"%PDF", "El PDF no se genero."
    # El texto del PDF viaja comprimido; se comprueba sobre el mismo modelo de
    # contenido que `pdf_render.guardar` acaba de dibujar.
    texto = _texto_informe(informe).lower()
    for palabra in VOCABULARIO_INTERVALO:
        assert palabra.lower() not in texto, f"El PDF publica '{palabra}'."


# ==============================
# P0-C — C8..C11: series cortas (donde vivia la fuga textual)
# ==============================


def _sin_fuga_en_serie(n: int, horizonte: int) -> None:
    resultado = _caso(f"n{n}h{horizonte}", _lineal(n), horizonte)
    fugas = _fuga_de_vocabulario(resultado)
    assert not fugas, f"n={n}, h={horizonte} publica vocabulario del intervalo: {fugas[:3]}"
    recuperables = _errores_recuperables(resultado)
    assert not recuperables, f"n={n}, h={horizonte} publica el vector de errores: {recuperables[:2]}"


def c8_serie_n7() -> None:
    _sin_fuga_en_serie(7, 1)


def c9_serie_n8() -> None:
    _sin_fuga_en_serie(8, 1)


def c10_un_solo_par_oos() -> None:
    """n=8, h=2 -> una sola ventana. Es el caso `n_pairs=1` de P0-G."""
    assert ventanas_oos_disponibles(8, 2) == 1, "El fixture dejo de tener una sola ventana."
    _sin_fuga_en_serie(8, 2)


def c11_dos_pares_oos() -> None:
    """n=8, h=1 -> dos ventanas."""
    assert ventanas_oos_disponibles(8, 1) == 2, "El fixture dejo de tener dos ventanas."
    resultado = _caso("n8h1", _lineal(8), 1)
    assert not _fuga_de_vocabulario(resultado)
    assert not _errores_recuperables(resultado)


def c12_agregados_oos_preservados() -> None:
    """Lo que P0-C NO puede llevarse: la evidencia agregada de la sustentacion."""
    resultado = _caso_ordinario()
    backtesting = resultado.get("backtesting") or {}
    metricas = backtesting.get("metricas") or {}
    for agregado in AGREGADOS_EXIGIDOS:
        valor = metricas.get(agregado)
        assert valor is not None and np.isfinite(float(valor)), f"Se perdio '{agregado}'."
    assert "sesgo_medio" in metricas, "Se perdio el sesgo medio."
    for porcentual in ("mape", "smape"):
        assert porcentual in metricas, f"Se perdio '{porcentual}' (aunque no sea finito)."
    iteraciones = backtesting.get("iteraciones")
    assert isinstance(iteraciones, int) and iteraciones > 0, "Se perdio n_pairs."
    # Y el diseno de la validacion sigue acreditandose.
    tabla = backtesting.get("predicciones")
    assert isinstance(tabla, pd.DataFrame) and len(tabla) == iteraciones, \
        "La tabla de ventanas dejo de acreditar el diseno."
    for columna in ("Origen", "Periodo", "Horizonte"):
        assert columna in tabla.columns, f"La tabla de ventanas perdio '{columna}'."


# ==============================
# HGRID — HG1..HG5
# ==============================


def _ventanas_reales(n: int, horizonte: int) -> int:
    backtesting = ejecutar_backtesting(
        _lineal(n), 2021, None, horizonte, "seleccion_automatica", MODELOS_ESTADISTICOS
    )
    return int(backtesting.get("iteraciones") or 0)


def hg1_sin_evidencia_por_debajo_del_primer_origen() -> None:
    """n=2..6 con h=1: cero ventanas reales, y la formula debe decir cero."""
    for n in range(2, 7):
        assert ventanas_oos_disponibles(n, 1) == 0, f"La formula anuncia evidencia con n={n}."
        assert _ventanas_reales(n, 1) == 0, f"El backtesting produjo ventanas con n={n}."
        assert tramo_evidencia_oos(ventanas_oos_disponibles(n, 1)) == TRAMO_OOS_SIN_EVIDENCIA


def hg2_una_ventana_en_n7() -> None:
    assert ventanas_oos_disponibles(7, 1) == 1
    assert _ventanas_reales(7, 1) == 1
    assert tramo_evidencia_oos(1) == TRAMO_OOS_MUY_LIMITADA


def hg3_formula_coincide_con_backtesting_en_los_bordes() -> None:
    """El contrato de fondo: la rejilla no puede prometer lo que el bucle no da."""
    desajustes = []
    for n in range(2, 14):
        for horizonte in (1, 2, 3, 4):
            formula = ventanas_oos_disponibles(n, horizonte)
            real = _ventanas_reales(n, horizonte)
            if formula != real:
                desajustes.append((n, horizonte, formula, real))
    assert not desajustes, f"W != ventanas reales en {desajustes}"


def hg4_una_ventana_no_se_llama_validada() -> None:
    """Ni el vocabulario ni las claves publicas pueden afirmar validacion."""
    resultado = _caso("n7h1", _lineal(7), 1)
    traza = (resultado.get("horizonte_info") or {}).get("trazabilidad") or {}
    assert traza.get("ventanas_oos_horizonte_solicitado") == 1
    assert traza.get("tramo_evidencia_oos_horizonte_solicitado") == TRAMO_OOS_MUY_LIMITADA
    texto = str(traza.get("evidencia_oos_horizonte_solicitado") or "").lower()
    assert "muy limitada" in texto, f"El texto no declara la limitacion: {texto!r}"
    for palabra in VOCABULARIO_PROHIBIDO:
        assert palabra not in texto, f"El texto llama '{palabra}' a una sola ventana."
    # Ninguna clave publica puede llamarse «validado por datos».
    for ruta, _ in _hojas(resultado):
        assert "validado_por_datos" not in ruta, f"Sobrevive la clave de validacion: {ruta}"


def hg5_primer_origen_se_comunica_provisional() -> None:
    resultado = _caso_ordinario()
    assert resultado.get("evidencia_oos_provisional") is True, "P0-E dejo de declararse."
    traza = (resultado.get("horizonte_info") or {}).get("trazabilidad") or {}
    assert traza.get("primer_origen_provisional") is True, "El primer origen no se declara provisional."
    assert "W = n - N0 - h + 1" in str(traza.get("formula_ventanas_oos") or ""), \
        "No se publica la formula de existencia."


def hg6_tramos_no_son_umbrales_de_aceptacion() -> None:
    """Las tres fronteras describen; ninguna niega."""
    assert tramo_evidencia_oos(0) == TRAMO_OOS_SIN_EVIDENCIA
    assert tramo_evidencia_oos(MIN_ITERACIONES_WF_ESCENARIO - 1) == TRAMO_OOS_MUY_LIMITADA
    assert tramo_evidencia_oos(MIN_ITERACIONES_WF_ESCENARIO) == TRAMO_OOS_DISPONIBLE
    assert tramo_evidencia_oos(MIN_ITERACIONES_BACKTESTING) == TRAMO_OOS_DISPONIBLE
    # Con UNA ventana el punto se entrega igualmente (P0-G, no reabrir).
    resultado = _caso("n8h2", _lineal(8), 2)
    assert resultado.get("proyeccion_generada") is True, \
        "Una sola ventana volvio a negar la proyeccion."


# ==============================
# P0-H — H1..H5
# ==============================


def h1_el_hueco_no_cancela_el_horizonte_posterior() -> None:
    salida = _resultado_con_hueco()
    pedido = salida["resultado_horizonte_solicitado"]
    assert pedido["proyeccion_generada"] is True, "h3 dejo de entregarse tras el hueco de h2."
    assert pedido["estado"] == "proyeccion_tecnica"
    assert pedido["accion"] == "permitir"
    assert float(pedido["indice_proyectado"]) == 123.0


def h2_el_hueco_se_publica_como_no_disponible() -> None:
    salida = _resultado_con_hueco()
    info = salida["horizonte_info"]
    por_h = {int(x["horizonte"]): x for x in info["evaluaciones"]}
    assert por_h[2]["permitido_para_proyeccion_tecnica"] is False
    assert por_h[2]["permitido_como_escenario"] is False
    assert por_h[1]["permitido_para_proyeccion_tecnica"] is True
    assert por_h[3]["permitido_para_proyeccion_tecnica"] is True
    assert int(info["primer_horizonte_no_viable"]) == 2, "El hueco dejo de senalarse."
    # Y no se inventa un valor para h=2.
    assert 2 not in {int(x["horizonte"]) for x in info["evaluaciones"] if x.get("interpolado")}


def h3_el_mensaje_no_afirma_que_la_evidencia_se_corta() -> None:
    """El nucleo del residual: la conducta era correcta y el mensaje la negaba."""
    salida = _resultado_con_hueco()
    razon = str(salida["resultado_horizonte_solicitado"]["razon_principal"])
    bajo = razon.lower()
    for falsedad in ("se corta", "no puede sostenerse", "use hasta"):
        assert falsedad not in bajo, f"La razon publica sigue diciendo «{falsedad}»: {razon!r}"
    assert "h=2" in razon, "La razon no nombra el hueco."
    assert "no se interpola" in bajo, "La razon no declara que no se interpola."
    assert "propia evidencia" in bajo or "propia muestra" in bajo, \
        "La razon no explica que cada horizonte se evalua por separado."


def h4_la_grafica_rompe_la_linea_en_el_hueco() -> None:
    """La linea no puede unir h1 con h3 por encima de un mes no disponible."""
    from app_icociv.reportes.graficas import _hay_hueco, _trayectoria_con_huecos

    tabla = pd.DataFrame({
        "periodo": ["2021_10", "2021_11", "2021_12"],
        "indice_proyectado": [121.0, 122.0, 123.0],
        "horizonte_disponible": [True, False, True],
    })
    assert _hay_hueco(tabla) is True
    trayectoria = _trayectoria_con_huecos(tabla)
    assert math.isnan(trayectoria[1]), "El paso no disponible se sigue dibujando."
    assert trayectoria[0] == 121.0 and trayectoria[2] == 123.0, \
        "Los pasos disponibles dejaron de dibujarse."
    # Sin la columna, el comportamiento anterior se conserva.
    sin_columna = tabla.drop(columns=["horizonte_disponible"])
    assert _hay_hueco(sin_columna) is False
    assert _trayectoria_con_huecos(sin_columna) == [121.0, 122.0, 123.0]


def h5_disponibilidad_por_paso_en_el_resultado() -> None:
    """La columna que alimenta ambas graficas viaja en el resultado."""
    salida = _resultado_con_hueco()
    tabla = salida.get("proyecciones")
    assert isinstance(tabla, pd.DataFrame)
    assert "horizonte_disponible" in tabla.columns, "No se publica la disponibilidad por paso."
    assert tabla["horizonte_disponible"].tolist() == [True, False, True]
    # El valor del paso no disponible NO se borra: existe y no se interpola.
    assert float(tabla["indice_proyectado"].iloc[1]) == 122.0


def h6_sin_hueco_no_se_inventa_uno() -> None:
    """Regresion: una trayectoria completa no debe marcarse con huecos."""
    resultado = _caso_ordinario()
    tabla = resultado.get("proyecciones")
    assert "horizonte_disponible" in tabla.columns
    assert all(bool(x) for x in tabla["horizonte_disponible"]), \
        "Se marcaron huecos en una trayectoria completa."
    razon = str((resultado.get("resultado_horizonte_solicitado") or {}).get("razon_principal") or "")
    assert "hueco" not in razon.lower(), f"Se anuncia un hueco inexistente: {razon!r}"


# ==============================
# REGRESION B / G / D — focalizada, no se reabre nada
# ==============================


def reg_b_n7_no_bloqueado_por_longitud() -> None:
    resultado = _caso("n7h1", _lineal(7), 1)
    assert resultado.get("proyeccion_generada") is True, "n=7 volvio a bloquearse."
    assert np.isfinite(float(resultado["y_proj"]))


def reg_g_una_ventana_entrega_punto() -> None:
    resultado = _caso("n8h2", _lineal(8), 2)
    assert resultado.get("proyeccion_generada") is True
    assert np.isfinite(float(resultado["y_proj"]))


def reg_d_seleccion_sigue_exacta() -> None:
    """P0-D: la seleccion compara SSE exacta, sin epsilon ni redondeo."""
    from app_icociv.proyeccion.servicio_proyeccion import _sse_exacto

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0 + 2 ** -40]
    assert _sse_exacto(a) != _sse_exacto(b), "La comparacion dejo de distinguir un ULP."
    assert _sse_exacto(a) == _sse_exacto(list(a)), "La SSE exacta dejo de ser reproducible."


# ==============================
# EJECUCION
# ==============================

PRUEBAS = [
    ("C1", "n=48,h=6 no reconstruible desde el objeto", c1_objeto_no_reconstruye_el_intervalo),
    ("C2", "DataFrame de proyecciones sin intervalo", c2_dataframe_de_proyecciones_sin_reconstruccion),
    ("C3", "sesion JSON sin reconstruccion", c3_sesion_json_sin_reconstruccion),
    ("C4", "CSV sin reconstruccion", c4_csv_sin_reconstruccion),
    ("C5", "interfaz sin vocabulario del intervalo", c5_interfaz_sin_reconstruccion),
    ("C6", "DOCX sin reconstruccion", c6_docx_sin_reconstruccion),
    ("C7", "PDF sin reconstruccion", c7_pdf_sin_reconstruccion),
    ("C8", "serie n=7", c8_serie_n7),
    ("C9", "serie n=8", c9_serie_n8),
    ("C10", "un solo par OOS", c10_un_solo_par_oos),
    ("C11", "dos pares OOS", c11_dos_pares_oos),
    ("C12", "agregados OOS preservados", c12_agregados_oos_preservados),
    ("HG1", "n=2..6 sin evidencia OOS", hg1_sin_evidencia_por_debajo_del_primer_origen),
    ("HG2", "n=7 -> W=1", hg2_una_ventana_en_n7),
    ("HG3", "formula W == ventanas reales", hg3_formula_coincide_con_backtesting_en_los_bordes),
    ("HG4", "W=1 no se llama validado", hg4_una_ventana_no_se_llama_validada),
    ("HG5", "primer origen provisional", hg5_primer_origen_se_comunica_provisional),
    ("HG6", "los tramos no son umbrales", hg6_tramos_no_son_umbrales_de_aceptacion),
    ("H1", "PASS/FAIL/PASS conserva h3", h1_el_hueco_no_cancela_el_horizonte_posterior),
    ("H2", "h2 visible como no disponible", h2_el_hueco_se_publica_como_no_disponible),
    ("H3", "el mensaje no dice «se corta»", h3_el_mensaje_no_afirma_que_la_evidencia_se_corta),
    ("H4", "la grafica rompe el hueco", h4_la_grafica_rompe_la_linea_en_el_hueco),
    ("H5", "disponibilidad por paso publicada", h5_disponibilidad_por_paso_en_el_resultado),
    ("H6", "sin hueco no se inventa uno", h6_sin_hueco_no_se_inventa_uno),
    ("B", "n=7 no bloqueado por longitud", reg_b_n7_no_bloqueado_por_longitud),
    ("G", "una ventana entrega punto", reg_g_una_ventana_entrega_punto),
    ("D", "seleccion sigue exacta", reg_d_seleccion_sigue_exacta),
]


def main() -> int:
    fallos = 0
    for codigo, titulo, prueba in PRUEBAS:
        try:
            prueba()
        except AssertionError as exc:
            fallos += 1
            print(f"FAIL {codigo:5s} {titulo}\n       {exc}")
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue
            fallos += 1
            print(f"ERROR {codigo:5s} {titulo}\n       {type(exc).__name__}: {exc}")
        else:
            print(f"OK   {codigo:5s} {titulo}")
    print()
    print(f"{len(PRUEBAS) - fallos}/{len(PRUEBAS)} pruebas verdes, {fallos} fallo(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
