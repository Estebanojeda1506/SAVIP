"""P0-C / ESTRATEGIA C2 — retiro de publicacion del intervalo no sustentado.

Estas pruebas NO comprueban «lo que hoy hace el codigo». Comprueban los
DIECIOCHO CRITERIOS C1-C18 congelados en

    06_REMEDIACIONES/P0C_C2_C1_C18_NORMA_CONGELADA.md
    (SHA-256 f5355e867f2930e61d213fc32ad8f1819f88f778601b82fc658cd7223fb23641)

cuya procedencia -el prompt normativo anterior a la sesion, NO el estado del
codigo- consta en `P0C_C2_C1_C18_PROVENIENCIA.md`. La lista se congelo y se le
calculo el hash ANTES de escribir este archivo y ANTES de tocar produccion.

C2 significa RETIRAR DE PUBLICACION un intervalo no sustentado. No significa
validarlo, sustituirlo por otra banda, renombrarlo, negar la incertidumbre ni
cambiar el calculo puntual. El calculo interno se conserva: es diagnostico.

TRAZABILIDAD CRITERIO -> PRUEBA
-------------------------------
C1  Ningun IC95 numerico en UI ................. criterio_c1_ui_sin_ic95_numerico
C2  Ninguna banda 95% en grafica publica ....... criterio_c2_grafica_sin_banda
C3  Ningun IC95 numerico en CSV/HTML publico ... criterio_c3_csv_html_sin_ic95
C4  Ningun IC95 numerico en DOCX/PDF ........... criterio_c4_docx_pdf_sin_ic95
C5  `graficas.py` no publica banda ............. criterio_c5_graficas_no_publica_banda
C6  Objeto publico sin limites numericos ....... criterio_c6_objeto_publico_sin_limites
C7  Cobertura residual no se publica ........... criterio_c7_cobertura_residual_no_publicada
C8  No existe banda sustituta .................. criterio_c8_sin_banda_sustituta
C9  Punto finito permanece publicable .......... criterio_c9_punto_finito_publicable
C10 Falta de sustento no bloquea el punto ...... criterio_c10_falta_de_sustento_no_bloquea
C11 Punto no finito sigue bloqueando ........... criterio_c11_punto_no_finito_bloquea
C12 Modelo intacto ............................. criterio_c12_modelo_intacto
C13 Horizonte intacto .......................... criterio_c13_horizonte_intacto
C14 Metricas/muestra intactas .................. criterio_c14_metricas_muestra_intactas
C15 P0-D no reabierto .......................... criterio_c15_p0d_no_reabierto
C16 P0-E sigue bloqueado/E3 .................... criterio_c16_p0e_sigue_bloqueado
C17 P0-F/G/H no regresan ....................... criterio_c17_p0fgh_no_regresan
C18 Codigo/UI/CSV/DOCX/PDF/tesis coherentes .... criterio_c18a_artefactos_productivos
                                                 criterio_c18b_tesis (PENDIENTE_TESIS)

C18 exige coherencia que incluye la TESIS. Su mitad documental no puede
verificarse antes de la fase de tesis y se declara `PENDIENTE_TESIS`: ni PASS
anticipado ni FAIL artificial. El cierre total de C1-C18 solo ocurre despues de
esa fase. El texto del criterio NO se altera para evitarlo.

Ejecucion directa, sin pytest:

    python tests/test_p0c_retiro_intervalos_no_sustentados.py
"""
from __future__ import annotations

import ast
import inspect
import math
import re
import sys
import traceback
import zipfile
from dataclasses import fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.interfaz import presentacion_resultados  # noqa: E402
from app_icociv.interfaz.presentacion_resultados import (  # noqa: E402
    construir_html_resultados,
    formatear_indice,
)
from app_icociv.proyeccion import servicio_proyeccion  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    BANDA_LIMITES_INVERTIDOS,
    BANDA_LIMITES_NO_FINITOS,
    BANDA_NO_CALCULABLE,
    BANDA_SEMIANCHO_CERO,
    BANDA_VALIDA,
    BLOQUEOS_METODOLOGICOS_VIGENTES,
    PUNTO_NO_FINITO,
    _clasificar_evidencia_horizonte,
    _ejecutar_proyeccion_base,
    _estructurar_resultado_horizontes,
    _sse_exacto,
    ejecutar_proyeccion,
    estado_banda,
    seleccionar_modelo_por_rmse_oos_global,
)
from app_icociv.reportes import contenido as mod_contenido  # noqa: E402
from app_icociv.reportes import generador_reportes, graficas  # noqa: E402
from app_icociv.reportes.contenido import (  # noqa: E402
    DatosProyeccion,
    construir_informe_proyeccion,
)
from app_icociv.reportes.modelo import ConfiguracionInforme, formato_indice  # noqa: E402


ANIO_BASE = 2019
RUTA_JERARQUICA = [
    {"nivel": "Grupo de obra", "valor": "Carreteras"},
    {"nivel": "Insumo", "valor": "Herramienta menor"},
]

#: Claves y columnas cuyo contenido es un LIMITE del intervalo. Es la superficie
#: que C1/C3/C4/C6 prohiben publicar con numeros. No incluye `sigma_h`, `q95` ni
#: los anchos relativos: esos son diagnostico del metodo, no limites entregados.
CLAVES_LIMITE = (
    "limite_inferior", "limite_superior",
    "limite_inferior_80", "limite_superior_80",
    "limite_inferior_95", "limite_superior_95",
    "ic95_inferior", "ic95_superior",
    "ic80_inferior", "ic80_superior",
    "ci_lo", "ci_hi", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi",
)

#: Claves cuyo VALOR es la pareja de limites, no un limite suelto. El bloque del
#: horizonte solicitado y los dos constructores de informes publican asi la
#: banda: `"ic95": [inferior, superior]`. Sin esta lista el recorrido entraria
#: en la secuencia, encontraria dos flotantes sin nombre de limite y los daria
#: por buenos.
CLAVES_LIMITE_SECUENCIA = ("ic95", "ic80", "ic_95", "ic_80", "intervalo_95", "intervalo_80")

#: Marcas de cobertura EMPIRICA de la banda retirada. C7 prohibe publicarlas.
#: `nominal declarado` es la frase exacta senalada como bloqueo B2.
MARCAS_COBERTURA_PUBLICA = (
    "nominal declarado",
    "cobertura observada",
    "cobertura mínima global",
    "cobertura minima global",
    "diferencia frente al nivel nominal",
    "lectura descriptiva de la cobertura",
    "evaluaciones dentro de la banda",
    "puntos porcentuales",
)


# ==============================
# APOYO
# ==============================


def _serie(n: int = 72, semilla: int | None = None) -> pd.DataFrame:
    """Serie mensual reproducible con tendencia y escalon de enero."""
    if semilla is None:
        valores = [100.0 + 0.8 * i + (3.5 if i and i % 12 == 0 else 0.0) for i in range(n)]
    else:
        g = np.random.default_rng(semilla)
        valores = [
            100.0 + 0.8 * i + (3.5 if i and i % 12 == 0 else 0.0) + float(g.normal(0, 0.4))
            for i in range(n)
        ]
    return pd.DataFrame(
        {"Periodo": [f"{ANIO_BASE + i // 12}_{i % 12 + 1}" for i in range(n)], "Indice": valores}
    )


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _proyectar(serie: pd.DataFrame, horizonte: int) -> dict:
    """Resultado PUBLICO: exactamente lo que recibe cualquier consumidor."""
    anio, mes = _objetivo(serie, horizonte)
    return ejecutar_proyeccion(serie, anio, mes, ANIO_BASE)


def _proyectar_interno(serie: pd.DataFrame, horizonte: int) -> dict:
    """Resultado ANTERIOR al corte de publicacion, con los numeros internos.

    Reproduce la composicion de `ejecutar_proyeccion` sin su ultimo paso. Es la
    referencia contra la que se mide que el corte C2 toca SOLO el intervalo:
    misma entrada, misma version, misma metodologia -> por REQ 24 todo lo demas
    debe coincidir campo a campo.
    """
    anio, mes = _objetivo(serie, horizonte)
    base = _ejecutar_proyeccion_base(
        serie_df=serie, year_proj=anio, month_proj=mes, anio_base=ANIO_BASE
    )
    return _estructurar_resultado_horizontes(base, "predeterminado")


def _finito(valor) -> bool:
    if isinstance(valor, bool) or valor is None:
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


def _numeros_publicados_de_limite(objeto, ruta: str = "") -> list[tuple[str, float]]:
    """Recorre el objeto publico y recoge todo numero finito bajo clave de limite.

    Propiedad, no instantanea: no fija la lista de claves de hoy, recorre lo que
    haya y decide por el NOMBRE de la clave. Si manana apareciera una clave de
    limite nueva con numero, esta funcion la encontraria igual.
    """
    hallados: list[tuple[str, float]] = []
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            sub = f"{ruta}.{clave}" if ruta else str(clave)
            if str(clave) in CLAVES_LIMITE and _finito(valor):
                hallados.append((sub, float(valor)))
            elif str(clave) in CLAVES_LIMITE_SECUENCIA and isinstance(valor, (list, tuple)):
                hallados.extend(
                    (f"{sub}[{i}]", float(v)) for i, v in enumerate(valor) if _finito(v)
                )
            else:
                hallados.extend(_numeros_publicados_de_limite(valor, sub))
    elif isinstance(objeto, pd.DataFrame):
        for columna in objeto.columns:
            if str(columna) in CLAVES_LIMITE:
                for i, valor in enumerate(objeto[columna].tolist()):
                    if _finito(valor):
                        hallados.append((f"{ruta}[{i}].{columna}", float(valor)))
    elif isinstance(objeto, (list, tuple)):
        for i, item in enumerate(objeto):
            hallados.extend(_numeros_publicados_de_limite(item, f"{ruta}[{i}]"))
    return hallados


def _limites_internos(serie: pd.DataFrame, horizonte: int) -> list[float]:
    """Los numeros de la banda tal como los calcula el motor, antes del corte."""
    interno = _proyectar_interno(serie, horizonte)
    return [valor for _, valor in _numeros_publicados_de_limite(interno)]


def _representaciones(valor: float) -> set[str]:
    """Como se veria ese numero si alguien lo publicara, con los formateadores reales."""
    formas = {formatear_indice(valor), formato_indice(valor)}
    for decimales in (1, 2, 3, 4, 6):
        formas.add(f"{valor:.{decimales}f}")
        formas.add(f"{valor:,.{decimales}f}")
        formas.add(f"{valor:.{decimales}f}".replace(".", ","))
    return {f for f in formas if f and any(c.isdigit() for c in f)}


def _fugas_numericas(texto: str, limites: list[float]) -> list[str]:
    """Que numero de banda aparece en un texto publicado, y con que formato."""
    plano = re.sub(r"<[^>]+>", " ", texto)
    fugas = []
    for valor in limites:
        for forma in _representaciones(valor):
            if forma in plano:
                fugas.append(f"{valor!r} publicado como {forma!r}")
                break
    return fugas


def _textos_de(objeto, vistos: set[int] | None = None) -> list[str]:
    """Todas las cadenas de un arbol de dataclasses/listas/dicts (bloques de informe)."""
    vistos = vistos if vistos is not None else set()
    if id(objeto) in vistos:
        return []
    if isinstance(objeto, str):
        return [objeto]
    vistos.add(id(objeto))
    salida: list[str] = []
    if is_dataclass(objeto):
        for campo in fields(objeto):
            salida.extend(_textos_de(getattr(objeto, campo.name), vistos))
    elif isinstance(objeto, dict):
        for clave, valor in objeto.items():
            salida.extend(_textos_de(clave, vistos))
            salida.extend(_textos_de(valor, vistos))
    elif isinstance(objeto, (list, tuple, set)):
        for item in objeto:
            salida.extend(_textos_de(item, vistos))
    elif isinstance(objeto, (int, float)) and not isinstance(objeto, bool):
        salida.append(repr(objeto))
    return salida


def _informe(serie: pd.DataFrame, resultado: dict, tipo: str = "tecnico"):
    datos = DatosProyeccion(
        resultado=resultado,
        serie_df=serie,
        fuente_label="T_16",
        archivo_excel="anexo.xlsx",
        ruta_jerarquica=RUTA_JERARQUICA,
        fila=pd.DataFrame([{"Grupos_Obra": "Carreteras"}]),
        year_month=[str(p) for p in serie["Periodo"]],
        usuario="Auditoria",
    )
    return construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo(tipo))


def _texto_docx(bytes_docx: bytes) -> str:
    with zipfile.ZipFile(__import__("io").BytesIO(bytes_docx)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    return re.sub(r"<[^>]+>", " ", xml)


def _arbol_alcanzable(ruta: Path) -> ast.Module:
    """AST del modulo con las ramas estaticamente falsas podadas.

    `if False and ...:` es codigo muerto: no publica nada. Podarlo permite
    preguntar por lo ALCANZABLE en vez de por la presencia del literal, que es
    lo que el criterio quiere decir con «no publica».
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))

    def falso(test: ast.expr) -> bool:
        if isinstance(test, ast.Constant) and test.value is False:
            return True
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            return any(falso(v) for v in test.values)
        return False

    class Podador(ast.NodeTransformer):
        def visit_If(self, nodo: ast.If):
            self.generic_visit(nodo)
            if falso(nodo.test):
                return nodo.orelse or None
            return nodo

    return ast.fix_missing_locations(Podador().visit(arbol))


def _llamadas_alcanzables(ruta: Path, nombre: str) -> list[int]:
    return [
        nodo.lineno
        for nodo in ast.walk(_arbol_alcanzable(ruta))
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == nombre
    ]


def _lineas_ejecutables(ruta: Path) -> list[tuple[int, str]]:
    """Lineas de codigo sin comentarios ni docstrings.

    Sin esto, buscar una cadena en el fuente da falsos positivos: los
    comentarios de esta remediacion NOMBRAN precisamente lo que se retiro.
    """
    # `utf-8-sig` retira el BOM: algunos modulos del proyecto lo llevan y
    # `ast.parse` lo rechaza como caracter no imprimible.
    fuente = ruta.read_text(encoding="utf-8-sig")
    arbol = ast.parse(fuente)
    docstrings: set[int] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            cuerpo = getattr(nodo, "body", None)
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant) \
                    and isinstance(cuerpo[0].value.value, str):
                docstrings.update(range(cuerpo[0].lineno, (cuerpo[0].end_lineno or cuerpo[0].lineno) + 1))
    salida = []
    for numero, linea in enumerate(fuente.splitlines(), start=1):
        if numero in docstrings:
            continue
        limpia = re.sub(r"#.*$", "", linea).strip()
        if limpia:
            salida.append((numero, limpia))
    return salida


# ==============================
# CASO CANONICO (una sola ejecucion, reutilizada)
# ==============================

# Caso mas pequeno que ejerce los dieciocho criterios: proyecta, produce banda
# interna y recorre todas las salidas. El caso canonico h=18 sobre el anexo real
# se mide en el BASE/POST de la remediacion, no aqui: esta prueba es una guarda
# que debe poder ejecutarse a menudo.
_SERIE = _serie(48)
_HORIZONTE = 6
_CACHE: dict[str, object] = {}


def _caso() -> tuple[dict, dict, list[float]]:
    if "publico" not in _CACHE:
        _CACHE["publico"] = _proyectar(_SERIE, _HORIZONTE)
        _CACHE["interno"] = _proyectar_interno(_SERIE, _HORIZONTE)
        _CACHE["limites"] = [v for _, v in _numeros_publicados_de_limite(_CACHE["interno"])]
    return _CACHE["publico"], _CACHE["interno"], _CACHE["limites"]  # type: ignore[return-value]


# ==============================
# C1 — Ningun IC95 numerico en UI
# ==============================


def criterio_c1_ui_sin_ic95_numerico() -> None:
    publico, _, limites = _caso()
    assert limites, "El motor no produjo banda interna: el caso no ejerce el criterio."
    html = construir_html_resultados(publico)
    fugas = _fugas_numericas(html, limites)
    assert not fugas, f"La UI publica limites del intervalo: {fugas[:6]}"
    plano = re.sub(r"<[^>]+>", " ", html).lower()
    assert not re.search(r"\[\s*-?\d[\d.,]*\s*,\s*-?\d[\d.,]*\s*\]", plano), \
        "La UI publica un par [inferior, superior]."


# ==============================
# C2 — Ninguna banda 95% en grafica publica
# ==============================


def criterio_c2_grafica_sin_banda() -> None:
    publico, _, _ = _caso()
    for ruta in (RAIZ / "app_icociv" / "reportes" / "graficas.py",
                 RAIZ / "app_icociv" / "interfaz" / "ventana_principal.py"):
        lineas = _llamadas_alcanzables(ruta, "fill_between")
        assert not lineas, f"{ruta.name} dibuja la banda en linea(s) {lineas}."
    # La grafica debe seguir generandose: retirar la banda no retira la grafica.
    imagen = graficas.grafica_principal(_SERIE, publico, con_intervalo=True)
    assert imagen and len(imagen) > 1000, "La grafica principal dejo de generarse."


# ==============================
# C3 — Ningun IC95 numerico en CSV/HTML publico
# ==============================


def criterio_c3_csv_html_sin_ic95() -> None:
    publico, _, limites = _caso()
    df = generador_reportes.construir_dataframe_reproducibilidad(_SERIE, publico, RUTA_JERARQUICA)
    fugas_df = _numeros_publicados_de_limite(df, "csv")
    assert not fugas_df, f"El CSV reproducible publica limites: {fugas_df[:6]}"
    fugas_texto = _fugas_numericas(df.to_csv(index=False), limites)
    assert not fugas_texto, f"El CSV publica limites en otra columna: {fugas_texto[:6]}"

    with TemporaryDirectory() as tmp:
        ruta = generador_reportes.generar_reporte_html(
            Path(tmp) / "informe.html", "Auditoria", "anexo.xlsx", {}, {},
            RUTA_JERARQUICA, "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]),
            _SERIE, publico, [str(p) for p in _SERIE["Periodo"]],
        )
        html = Path(ruta).read_text(encoding="utf-8")
    fugas_html = _fugas_numericas(html, limites)
    assert not fugas_html, f"El informe HTML publica limites: {fugas_html[:6]}"


# ==============================
# C4 — Ningun IC95 numerico en DOCX/PDF
# ==============================


def criterio_c4_docx_pdf_sin_ic95() -> None:
    publico, _, limites = _caso()
    # El contenido se decide UNA vez y lo dibujan DOCX y PDF: comprobarlo sobre
    # el objeto de contenido cubre ambos formatos en su origen comun.
    for tipo in ("tecnico", "ejecutivo", "completo"):
        texto = " ".join(_textos_de(_informe(_SERIE, publico, tipo)))
        fugas = _fugas_numericas(texto, limites)
        assert not fugas, f"El informe '{tipo}' publica limites: {fugas[:6]}"

    bytes_docx = generador_reportes.construir_bytes_reporte_docx(
        "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]), _SERIE, publico,
        [str(p) for p in _SERIE["Periodo"]],
    )
    fugas_docx = _fugas_numericas(_texto_docx(bytes_docx), limites)
    assert not fugas_docx, f"El DOCX renderizado publica limites: {fugas_docx[:6]}"


# ==============================
# C5 — `graficas.py` no publica banda
# ==============================


def criterio_c5_graficas_no_publica_banda() -> None:
    ruta = RAIZ / "app_icociv" / "reportes" / "graficas.py"
    assert not _llamadas_alcanzables(ruta, "fill_between"), "graficas.py aun dibuja la banda."
    ejecutables = " ".join(t for _, t in _lineas_ejecutables(ruta)).lower()
    for marca in ("fill_betweenx", "axhspan", "errorbar"):
        assert marca not in ejecutables, f"graficas.py introduce '{marca}' como banda."


# ==============================
# C6 — Objeto publico no expone limites numericos
# ==============================


def criterio_c6_objeto_publico_sin_limites() -> None:
    publico, _, _ = _caso()
    fugas = _numeros_publicados_de_limite(publico, "resultado")
    assert not fugas, f"El objeto publico expone {len(fugas)} limite(s) numerico(s): {fugas[:8]}"
    # Y no solo en el caso feliz: tambien en una serie corta y en un horizonte 1.
    for serie, horizonte in ((_serie(30), 3), (_serie(48), 1)):
        otras = _numeros_publicados_de_limite(_proyectar(serie, horizonte), "resultado")
        assert not otras, f"Otra ruta publica expone limites: {otras[:6]}"


# ==============================
# C7 — La cobertura residual no se publica
# ==============================


def criterio_c7_cobertura_residual_no_publicada() -> None:
    publico, _, _ = _caso()
    superficies = {
        "UI": construir_html_resultados(publico),
        "CSV": generador_reportes.construir_dataframe_reproducibilidad(
            _SERIE, publico, RUTA_JERARQUICA).to_csv(index=False),
        "informe": " ".join(_textos_de(_informe(_SERIE, publico, "completo"))),
    }
    with TemporaryDirectory() as tmp:
        ruta = generador_reportes.generar_reporte_html(
            Path(tmp) / "i.html", "Auditoria", "anexo.xlsx", {}, {}, RUTA_JERARQUICA,
            "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]), _SERIE, publico,
            [str(p) for p in _SERIE["Periodo"]],
        )
        superficies["HTML"] = Path(ruta).read_text(encoding="utf-8")

    for nombre, texto in superficies.items():
        plano = re.sub(r"<[^>]+>", " ", texto).lower()
        presentes = [m for m in MARCAS_COBERTURA_PUBLICA if m in plano]
        assert not presentes, f"{nombre} publica la cobertura de la banda retirada: {presentes}"

    # P0-C, 16-08-2026 (V-CODEX-3). Aqui se exigia que el diagnostico de
    # cobertura SIGUIERA en el objeto publico, con el argumento de que
    # "retirar no es borrar". La auditoria independiente refuto esa lectura:
    # todo lo que devuelve `ejecutar_proyeccion` ES la salida publica, y que
    # una clave se llame `diagnostico_cobertura_no_publicado` no la vuelve
    # privada. El calculo permanece dentro de `_ejecutar_proyeccion_base`,
    # donde es diagnostico y no decide; lo que ya no viaja es la salida.
    assert publico.get("cobertura_empirica") is None, publico.get("cobertura_empirica")
    assert publico.get("clasificacion_intervalo") is None, publico.get("clasificacion_intervalo")


# ==============================
# C8 — No existe banda sustituta
# ==============================


def criterio_c8_sin_banda_sustituta() -> None:
    publico, interno, _ = _caso()
    # Nada nuevo aparece en el objeto publico: el corte solo QUITA.
    nuevas = set(publico) - set(interno)
    assert not nuevas, f"El corte introdujo claves nuevas en el objeto publico: {sorted(nuevas)}"
    proy_pub = publico.get("proyecciones")
    proy_int = interno.get("proyecciones")
    if isinstance(proy_pub, pd.DataFrame) and isinstance(proy_int, pd.DataFrame):
        columnas_nuevas = set(proy_pub.columns) - set(proy_int.columns)
        assert not columnas_nuevas, f"Columnas nuevas en la tabla publica: {sorted(columnas_nuevas)}"

    # Ninguna superficie ofrece un rango numerico con otro nombre.
    html = re.sub(r"<[^>]+>", " ", construir_html_resultados(publico)).lower()
    for sustituto in ("rango de referencia", "banda alternativa", "margen de error",
                      "intervalo aproximado", "banda indicativa", "rango estimado"):
        assert sustituto not in html, f"Aparecio una banda sustituta: '{sustituto}'."


# ==============================
# C9 — El punto finito/calculable permanece publicable
# ==============================


def criterio_c9_punto_finito_publicable() -> None:
    publico, interno, _ = _caso()
    assert publico.get("proyeccion_generada") is True, "Se dejo de proyectar un punto calculable."
    punto = publico.get("y_proj")
    assert _finito(punto), f"El punto publicado no es finito: {punto!r}"
    assert float(punto) == float(interno["y_proj"]), "El corte C2 movio el pronostico puntual."
    proy = publico.get("proyecciones")
    assert isinstance(proy, pd.DataFrame) and not proy.empty, "La tabla de proyeccion desaparecio."
    assert all(_finito(v) for v in proy["indice_proyectado"]), "Hay pasos sin punto finito."
    # Y llega a las salidas: no basta con calcularlo.
    assert formatear_indice(punto) in re.sub(r"<[^>]+>", " ", construir_html_resultados(publico)), \
        "El punto no aparece en la UI."


# ==============================
# C10 — La falta de sustento del intervalo no bloquea por si sola el punto
# ==============================


def criterio_c10_falta_de_sustento_no_bloquea() -> None:
    base = dict(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
    )
    for estado in (BANDA_NO_CALCULABLE, BANDA_LIMITES_NO_FINITOS,
                   BANDA_LIMITES_INVERTIDOS, BANDA_SEMIANCHO_CERO, BANDA_VALIDA):
        clasificacion = _clasificar_evidencia_horizonte(
            evaluacion_intervalos={"estado_banda": estado, "ancho_relativo_95_maximo": 0.1},
            **base,
        )
        assert clasificacion.get("permitido_para_proyeccion_tecnica") or \
            clasificacion.get("permitido_como_escenario"), \
            f"El estado de banda '{estado}' bloquea un punto finito (REQ 14)."
    # Y el propio resultado publico lo declara sin sustento sin dejar de proyectar.
    publico, _, _ = _caso()
    assert publico.get("intervalo_sustentado") is False, "P0-C sigue abierto: no puede declararse sustentado."
    assert publico.get("proyeccion_generada") is True


# ==============================
# C11 — Un punto no finito sigue bloqueando
# ==============================


def criterio_c11_punto_no_finito_bloquea() -> None:
    for punto in (float("nan"), float("inf"), float("-inf")):
        assert estado_banda(90.0, 110.0, punto) == PUNTO_NO_FINITO, \
            f"Un pronostico {punto!r} debe declararse PUNTO_NO_FINITO."
    clasificacion = _clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": PUNTO_NO_FINITO, "ancho_relativo_95_maximo": 0.1},
    )
    assert not clasificacion.get("permitido_para_proyeccion_tecnica"), \
        "Un punto no finito no puede publicarse como proyeccion tecnica."
    assert not clasificacion.get("permitido_como_escenario"), \
        "Un punto no finito tampoco es un escenario: no hay numero que ofrecer."


# ==============================
# C12/C13/C14 — Modelo, horizonte, metricas y muestra intactos
# ==============================

#: Campos del objeto publico cuya diferencia frente al interno esta AUTORIZADA
#: por C2: son limites, o texto que los nombraba.
#: P0-C, 16-08-2026 (V-CODEX-3). El corte C2 se amplio: ademas de los limites
#: retira los COMPONENTES RECONSTRUCTIVOS -sigma_h, cuantiles, offsets y anchos-
#: y los DIAGNOSTICOS de la banda -cobertura, clasificacion, degradacion-, que
#: viajaban en el dict devuelto por la funcion publica. Los bloques que los
#: contienen cambian por tanto de forma AUTORIZADA.
CAMPOS_AUTORIZADOS_A_CAMBIAR = set(CLAVES_LIMITE) | {
    "cobertura_empirica",
    "clasificacion_intervalo",
    "diagnostico_cobertura_no_publicado",
    "degradacion_por_cobertura",
    "verificabilidad_paso_exacto",
    "stats",
    "horizonte_info",
    "analisis_horizontes_completo",
    "proyecciones",
    # AMPLIADO 17-08-2026 (V-CODEX-R3, residual 1). El corte retira ahora las
    # columnas de error de la tabla de ventanas, porque el vector completo
    # reconstruye `sigma_h` y con el punto -publico- los limites EXACTOS del
    # intervalo retirado. Codex lo verifico con n=48, h=6.
    #
    # Autorizar el bloque NO afloja la prueba: `t_obj_8` y `criterio_c14`
    # comparan aparte, y de forma explicita, `backtesting["metricas"]` y
    # `backtesting["iteraciones"]`, que son justamente lo que debe permanecer
    # identico. Lo que se autoriza a cambiar es el detalle por ventana.
    "backtesting",
    "backtesting_comparativo",
}


#: Unicos campos de reloj de pared del resultado. Dos ejecuciones de la misma
#: entrada difieren en ellos por definicion y REQ 24 no los incluye: exige mismo
#: modelo, parametros, horizonte, pronostico, intervalos, metricas, estado y
#: artefactos, no el instante en que se corrio. Se normalizan -no se excluye el
#: bloque que los contiene, que si debe compararse entero-.
CAMPOS_RELOJ = ("timestamp_ejecucion_utc", "fecha_analisis", "fecha_generacion")


def _normalizar(objeto):
    """Neutraliza el reloj y los limites, en cualquier nivel del arbol.

    Los limites se neutralizan porque C2 AUTORIZA su cambio: son lo unico que
    el corte puede tocar. Sin esto la comparacion seria insatisfacible por
    construccion. Todo lo demas -incluido el bloque que los contiene- se sigue
    comparando entero, que es lo que hace fuerte a la prueba: cualquier campo
    que no sea un limite y difiera, aparece.
    """
    if isinstance(objeto, dict):
        salida = {}
        for clave, valor in objeto.items():
            if clave in CAMPOS_RELOJ:
                salida[clave] = "<reloj>"
            elif (clave in CLAVES_LIMITE or clave in CLAVES_LIMITE_SECUENCIA
                  or clave in CAMPOS_AUTORIZADOS_A_CAMBIAR):
                salida[clave] = "<limite retirado por C2>"
            else:
                salida[clave] = _normalizar(valor)
        return salida
    if isinstance(objeto, list):
        return [_normalizar(v) for v in objeto]
    if isinstance(objeto, tuple):
        return tuple(_normalizar(v) for v in objeto)
    return objeto


def _diferencias(publico: dict, interno: dict) -> list[str]:
    """Campos de primer nivel que difieren, excluyendo los autorizados por C2."""
    diferencias = []
    for clave in sorted(set(publico) | set(interno)):
        if clave in CAMPOS_AUTORIZADOS_A_CAMBIAR:
            continue
        a, b = publico.get(clave), interno.get(clave)
        if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
            continue  # la tabla se compara aparte, columna a columna
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            if not np.array_equal(np.asarray(a, dtype=object), np.asarray(b, dtype=object)):
                diferencias.append(clave)
            continue
        if callable(a) or callable(b):
            continue
        try:
            if repr(_normalizar(a)) != repr(_normalizar(b)):
                diferencias.append(clave)
        except Exception:  # noqa: BLE001 - comparacion defensiva
            diferencias.append(clave)
    return diferencias


def criterio_c12_modelo_intacto() -> None:
    publico, interno, _ = _caso()
    assert publico.get("model_name") == interno.get("model_name"), "Cambio el modelo publicado."
    assert publico.get("modelo_codigo") == interno.get("modelo_codigo"), "Cambio el codigo de modelo."
    assert str(publico.get("model_name") or "").strip(), "El modelo dejo de publicarse."
    proy = publico.get("proyecciones")
    assert set(proy["modelo"].unique()) == set(interno["proyecciones"]["modelo"].unique()), \
        "La tabla publica cambio de modelo."


def criterio_c13_horizonte_intacto() -> None:
    publico, interno, _ = _caso()
    for clave in ("horizonte_solicitado", "horizonte_permitido", "periodo_proj", "t_proj"):
        assert publico.get(clave) == interno.get(clave), f"Cambio '{clave}'."
    assert int(publico["horizonte_solicitado"]) == _HORIZONTE
    assert len(publico["proyecciones"]) == len(interno["proyecciones"]), \
        "Cambio el numero de pasos publicados."


def criterio_c14_metricas_muestra_intactas() -> None:
    publico, interno, _ = _caso()
    diferencias = _diferencias(publico, interno)
    assert not diferencias, \
        f"El corte C2 cambio campos que no son limites del intervalo: {diferencias}"
    # La tabla publica: identica columna a columna salvo los limites.
    pub, int_ = publico["proyecciones"], interno["proyecciones"]
    # P0-C, 16-08-2026: ademas de los limites, el corte retira de la tabla los
    # componentes con que se reconstruian -sigma_h, cuantiles, offsets, anchos-
    # y el metodo de construccion. Todos son cambios AUTORIZADOS.
    from app_icociv.proyeccion.servicio_proyeccion import COLUMNAS_RECONSTRUCTIVAS
    autorizadas = set(CLAVES_LIMITE) | set(COLUMNAS_RECONSTRUCTIVAS)
    for columna in int_.columns:
        if str(columna) in autorizadas:
            continue
        assert columna in pub.columns, f"Desaparecio la columna '{columna}'."
        a = pub[columna].astype(object).tolist()
        b = int_[columna].astype(object).tolist()
        assert [repr(x) for x in a] == [repr(x) for x in b], f"Cambio la columna '{columna}'."


# ==============================
# C15 — P0-D no reabierto
# ==============================


def criterio_c15_p0d_no_reabierto() -> None:
    from fractions import Fraction
    assert isinstance(_sse_exacto([1.0, 2.0, 3.0]), Fraction), \
        "La suma de cuadrados dejo de ser exacta: P0-D reabierto."
    # Dos candidatos separados por 1 ULP deben seguir siendo distinguibles.
    a = 1.0
    b = math.nextafter(1.0, 2.0)
    assert _sse_exacto([a]) != _sse_exacto([b]), "El selector volvio a empatar por redondeo."
    fuente = " ".join(t for _, t in _lineas_ejecutables(
        RAIZ / "app_icociv" / "proyeccion" / "servicio_proyeccion.py"))
    assert "_sse_exacto" in inspect.getsource(seleccionar_modelo_por_rmse_oos_global), \
        "El selector dejo de decidir sobre la suma exacta."
    assert "hypot" not in inspect.getsource(seleccionar_modelo_por_rmse_oos_global), \
        "El selector volvio a decidir sobre un flotante redondeado."
    assert fuente, "No se pudo leer el fuente del servicio."


# ==============================
# C16 — P0-E sigue bloqueado / E3
# ==============================


def criterio_c16_p0e_sigue_bloqueado() -> None:
    assert "P0-E" in BLOQUEOS_METODOLOGICOS_VIGENTES, "P0-E desaparecio de los bloqueos vigentes."
    publico, _, _ = _caso()
    assert publico.get("evidencia_oos_provisional") is True, \
        "La evidencia OOS dejo de declararse provisional."
    assert "P0-E" in (publico.get("bloqueos_metodologicos") or {}), \
        "El resultado publico no transporta el bloqueo P0-E."
    assert str(publico.get("motivo_evidencia_provisional") or "").strip(), \
        "El motivo del bloqueo P0-E quedo vacio."


# ==============================
# C17 — P0-F / P0-G / P0-H no regresan
# ==============================


def criterio_c17_p0fgh_no_regresan() -> None:
    publico, _, _ = _caso()

    # P0-F: los tres hechos del calendario siguen separados.
    calendario = publico.get("ajuste_calendario") or {}
    for campo in ("patron_detectado_en_serie", "eneros_en_horizonte",
                  "horizonte_cruza_cambio_anio", "efecto_en_horizonte_solicitado"):
        assert campo in calendario, f"P0-F regreso: falta '{campo}' en la trazabilidad calendario."
    efecto = bool(calendario["efecto_en_horizonte_solicitado"])
    if efecto:
        assert int(calendario["eneros_en_horizonte"]) > 0, \
            "El efecto se declara sin eneros en el horizonte."

    # P0-G: el estado metodologico viaja con el resultado y separa punto de intervalo.
    assert str(publico.get("estado_metodologico") or "").strip(), "P0-G regreso: sin estado metodologico."
    assert publico.get("bloqueos_metodologicos"), "P0-G regreso: sin bloqueos en el resultado."
    assert publico.get("intervalo_sustentado") is False

    # P0-H: el horizonte publicado se decide con la evidencia de ese horizonte.
    solicitado = publico.get("resultado_horizonte_solicitado") or {}
    assert solicitado, "P0-H regreso: no hay bloque del horizonte solicitado."
    assert int(solicitado.get("horizonte") or publico["horizonte_solicitado"]) == _HORIZONTE


# ==============================
# C18 — Coherencia entre artefactos
# ==============================


def criterio_c18a_artefactos_productivos() -> None:
    """Mitad verificable de C18: codigo, UI, CSV, DOCX y PDF dicen lo mismo."""
    publico, _, limites = _caso()
    superficies = {
        "UI": construir_html_resultados(publico),
        "CSV": generador_reportes.construir_dataframe_reproducibilidad(
            _SERIE, publico, RUTA_JERARQUICA).to_csv(index=False),
        "informe": " ".join(_textos_de(_informe(_SERIE, publico, "completo"))),
        "DOCX": _texto_docx(generador_reportes.construir_bytes_reporte_docx(
            "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]), _SERIE, publico,
            [str(p) for p in _SERIE["Periodo"]])),
    }
    for nombre, texto in superficies.items():
        assert not _fugas_numericas(texto, limites), f"{nombre} incoherente con C2: publica limites."
    # Ninguna superficie promete al lector un intervalo que ya no existe.
    for nombre, texto in superficies.items():
        plano = re.sub(r"<[^>]+>", " ", texto).lower()
        for promesa in ("junto con el intervalo de predicción del 95",
                        "interpretarse junto con el intervalo",
                        "intervalo de predicción 95%=["):
            assert promesa not in plano, f"{nombre} remite a un intervalo retirado: '{promesa}'."
    # Y todas siguen diciendo lo mismo del punto y del modelo.
    modelo = str(publico.get("model_name") or "")
    for nombre, texto in superficies.items():
        plano = re.sub(r"<[^>]+>", " ", texto)
        assert modelo.split(" (")[0] in plano, f"{nombre} no declara el modelo '{modelo}'."


def criterio_c18b_tesis() -> None:
    """Mitad documental de C18: la tesis es coherente con el retiro C2.

    Verificable desde el 15-08-2026, tras la fase de tesis. Antes de ella este
    criterio se declaraba `PENDIENTE_TESIS`: ni PASS anticipado ni FAIL
    artificial.

    Se comprueba sobre el fuente LaTeX, no sobre el PDF: es donde vive la
    afirmacion y es lo que un auditor puede leer. La compilacion -150 paginas,
    0 errores, 0 referencias sin resolver- se registra en el artefacto de la
    sesion; aqui se vigila el CONTENIDO.
    """
    tex = RAIZ / "documentacion_latex" / "documento_tecnico_icociv_iccp"
    fuentes = {
        p.name: p.read_text(encoding="utf-8", errors="replace")
        for p in [tex / "main.tex", tex / "tabla_criterios_auditable.tex",
                  *(tex / "anexos").glob("*.tex")]
        if p.exists()
    }
    assert fuentes, "no se encontro el documento final"
    principal = fuentes["main.tex"]

    # 1. Declara el retiro, en presente y sin ambiguedad.
    assert "no publica intervalos de prediccion" in principal.replace("ó", "o") or \
        "no publica intervalo de prediccion" in principal.replace("ó", "o"), \
        "la tesis no declara que esta version no publique intervalo"

    # 2. Ninguna tabla entrega limites ni ancho de la banda como resultado.
    for nombre, texto in fuentes.items():
        for prohibido in ("IC95 inf", "IC95 sup", "IC95 rel."):
            assert prohibido not in texto, f"{nombre} publica '{prohibido}'"

    # 3. No presenta C2 como validacion del IC95.
    for nombre, texto in fuentes.items():
        plano = texto.lower()
        for falso in ("ic95 validad", "intervalo validad", "cobertura validad",
                      "se valido el intervalo", "intervalo de prediccion validado"):
            assert falso not in plano.replace("ó", "o"), f"{nombre}: '{falso}'"

    # 4. P0-E NO se presenta como resuelto.
    assert "primer origen" in principal, "la tesis dejo de mencionar el primer origen"
    assert "sigue abierta" in principal or "no est" in principal, \
        "la tesis debe seguir declarando abierto el primer origen (P0-E)"

    # 5. No contradice P0-D: no afirma que hypot devuelva el mismo valor.
    assert "devuelve el mismo valor sin materializar" not in principal, \
        "la tesis vuelve a afirmar lo que P0-D midio como falso"


# ==============================
# EJECUCION
# ==============================


class Pendiente(Exception):
    """Criterio que aun no puede verificarse en esta fase (no es un fallo)."""


CRITERIOS = [
    ("C1", "Ningún IC95 numérico en UI.", criterio_c1_ui_sin_ic95_numerico),
    ("C2", "Ninguna banda 95% en gráfica pública.", criterio_c2_grafica_sin_banda),
    ("C3", "Ningún IC95 numérico en CSV/HTML público.", criterio_c3_csv_html_sin_ic95),
    ("C4", "Ningún IC95 numérico en DOCX/PDF.", criterio_c4_docx_pdf_sin_ic95),
    ("C5", "`graficas.py` no publica banda.", criterio_c5_graficas_no_publica_banda),
    ("C6", "Objeto público no expone límites numéricos.", criterio_c6_objeto_publico_sin_limites),
    ("C7", "Cobertura residual no se publica.", criterio_c7_cobertura_residual_no_publicada),
    ("C8", "No existe banda sustituta.", criterio_c8_sin_banda_sustituta),
    ("C9", "Punto finito/calculable permanece publicable.", criterio_c9_punto_finito_publicable),
    ("C10", "Falta de sustento del intervalo no bloquea por sí sola el punto.",
     criterio_c10_falta_de_sustento_no_bloquea),
    ("C11", "Punto no finito sigue bloqueando.", criterio_c11_punto_no_finito_bloquea),
    ("C12", "Modelo intacto.", criterio_c12_modelo_intacto),
    ("C13", "Horizonte intacto.", criterio_c13_horizonte_intacto),
    ("C14", "Métricas/muestra intactas.", criterio_c14_metricas_muestra_intactas),
    ("C15", "P0-D no reabierto.", criterio_c15_p0d_no_reabierto),
    ("C16", "P0-E sigue bloqueado/E3.", criterio_c16_p0e_sigue_bloqueado),
    ("C17", "P0-F/G/H no regresan.", criterio_c17_p0fgh_no_regresan),
    ("C18", "Código/UI/CSV/DOCX/PDF/tesis son coherentes con C2. [productivos]",
     criterio_c18a_artefactos_productivos),
    ("C18", "Código/UI/CSV/DOCX/PDF/tesis son coherentes con C2. [tesis]",
     criterio_c18b_tesis),
]


def main() -> int:
    fallos = 0
    pendientes = 0
    for identificador, literal, prueba in CRITERIOS:
        try:
            prueba()
        except Pendiente as pendiente:
            pendientes += 1
            print(f"PENDIENTE_TESIS {identificador}  {literal}")
            print(f"                {pendiente}")
        except Exception:  # noqa: BLE001 - se reporta integro
            fallos += 1
            print(f"FAIL {identificador}  {literal}")
            traceback.print_exc()
        else:
            print(f"OK   {identificador}  {literal}")
    total = len(CRITERIOS)
    print(f"\n{total - fallos - pendientes}/{total} criterios verdes, "
          f"{pendientes} pendiente(s) de tesis, {fallos} fallo(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
