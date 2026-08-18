"""Pruebas dirigidas de RA-03 y RA-05 (reauditoria de 0.3.0-rc2).

**RA-03.** Una serie bloqueada (`C-11`, h=3) hacia fallar la generacion DOCX y
PDF con ``ValueError: operands could not be broadcast together with shapes
(65,) (0,)``: sin ajuste no hay ``y_fit_obs``, y la grafica de residuos restaba
un vector de 65 observaciones con uno vacio. Un estado bloqueado debe poder
exportarse en CSV, DOCX y PDF sin inventar trayectorias.

**RA-05.** La tabla de modelos evaluados declaraba MAE/RMSE/MASE/Sesgo «no
disponibles» mientras el texto contiguo publicaba RMSE y MAPE del mismo
backtesting: la tabla leia claves inexistentes. Tabla, texto, CSV, DOCX y PDF
deben usar la misma fuente y el mismo criterio de disponibilidad.

Ejecucion directa, sin pytest:

    python tests/test_informes_serie_bloqueada.py
"""
from __future__ import annotations

import sys
import traceback
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.exportables.csv_reproducible import construir_csv_reproducible  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    _limites_auditoria_horizontes,
    ejecutar_proyeccion,
)
from app_icociv.reportes import graficas  # noqa: E402
from app_icociv.reportes.contenido import (  # noqa: E402
    DatosProyeccion,
    construir_informe_proyeccion,
)
from app_icociv.reportes.generador_reportes import (  # noqa: E402
    generar_reporte_pdf,
    generar_reporte_proyeccion,
)
from app_icociv.reportes.modelo import ConfiguracionInforme, Tabla  # noqa: E402

ANIO_BASE = 2019
RUTA = [{"nivel": "Capítulo detallado", "valor": "Serie bloqueada de prueba"}]


# ==============================
# APOYOS
# ==============================


#: Observaciones de la serie sintetica que no puede proyectarse.
OBSERVACIONES_SERIE_BLOQUEADA = 21


def _primer_horizonte_sin_ventanas(n: int) -> int:
    """Primer h que NO reune ninguna ventana de validacion: ``h > n - N0``.

    Se DERIVA del primer origen que usa produccion en lugar de escribirse como
    literal, para que el fixture siga al criterio vigente en vez de romperse
    contra un numero elegido. Es la misma identidad aritmetica del esquema de
    origen movil con ventana expansiva: el horizonte h admite
    ``n - N0 - h + 1`` origenes, luego con ``h > n - N0`` no queda ninguno.
    """
    entrenamiento = _limites_auditoria_horizontes(n)[0]
    return (n - entrenamiento) + 1


#: Horizonte sin ventanas de validacion para la serie de 21 observaciones.
#:
#: HISTORIA DEL FIXTURE, porque resume dos cierres y conviene no repetirla.
#:
#: P0-E, 12-08-2026. Hasta esa fecha bastaba pedir **3** meses, porque el
#: entrenamiento inicial era `max(18, 0,60 n) = 18` y con 21 observaciones solo
#: quedaba una ventana. Retirados esos dos literales -carecian de fuente-, el
#: primer origen se deriva de la estimabilidad y vale 6, de modo que la MISMA
#: serie reune 13 ventanas en h=3 y ya no se bloquea. Se recalibro a **15**,
#: que era el primer h con menos de `MIN_ITERACIONES_WF_ESCENARIO = 3` ventanas.
#:
#: P0-G, 16-08-2026 (V-CODEX-3). Ese corte de tres procede -por declaracion de
#: su propia ficha- de estimar la dispersion y verificar la cobertura del
#: INTERVALO, eje que P0-C retiro del producto: un requisito de la BANDA estaba
#: decidiendo si se entrega el PUNTO. Con dos ventanas el error fuera de muestra
#: existe y el RMSE es calculable, de modo que h=15 hoy **se entrega**, y por eso
#: esta suite quedo roja. La frontera autentica es la de EXISTENCIA, `h > n - N0`,
#: que con esta serie cae en **16**.
#:
#: **La propiedad que esta prueba verifica no ha cambiado en ninguno de los dos
#: cierres**: cuando un horizonte no reune NINGUNA ventana no hay error que
#: medir, la proyeccion no se genera y los informes deben emitirse igual,
#: declarando la ausencia sin inventar trayectoria. Lo que cambia es QUE
#: horizonte cumple esa condicion. El fixture no se retoca para que la prueba
#: pase: se deriva del criterio vigente, y ahora de forma automatica.
HORIZONTE_SIN_VENTANAS = _primer_horizonte_sin_ventanas(OBSERVACIONES_SERIE_BLOQUEADA)


def serie_bloqueada(n: int = 21) -> pd.DataFrame:
    """Serie tan corta que el horizonte pedido no tiene ventanas de validacion.

    CIERRE 08-08-2026: hasta esa fecha bastaba una serie erratica para provocar
    el bloqueo, porque lo producian los cortes de amplitud del IC95 y de
    cobertura. Retirados esos cortes -no tenian fuente-, una serie erratica ya
    no se bloquea: se entrega con su incertidumbre publicada.

    Lo que esta prueba necesita sigue existiendo, y ahora por la unica razon
    legitima: **una imposibilidad de calculo**. Con 21 observaciones y el primer
    origen derivado (6), el horizonte de `HORIZONTE_SIN_VENTANAS` meses no reune
    el minimo de ventanas fuera de muestra, de modo que no hay error que medir.
    La serie mantiene sus 21 observaciones, por encima del minimo de longitud,
    para que el bloqueo proceda de la ausencia de ventanas y no de la longitud.

    Se conserva la semilla fija para que el caso sea reproducible.
    """
    generador = np.random.default_rng(20260730)
    base = np.linspace(100.0, 140.0, n)
    valores = np.abs(base + generador.normal(0.0, 6.0, n)) + 1.0
    return pd.DataFrame({
        "Periodo": [f"{ANIO_BASE + i // 12}_{i % 12 + 1}" for i in range(n)],
        "Indice": np.round(valores, 4),
    })


def serie_normal(n: int = 72) -> pd.DataFrame:
    generador = np.random.default_rng(7)
    valores = np.linspace(100.0, 138.0, n) + generador.normal(0.0, 0.6, n)
    return pd.DataFrame({
        "Periodo": [f"{ANIO_BASE + i // 12}_{i % 12 + 1}" for i in range(n)],
        "Indice": np.round(valores, 4),
    })


def proyectar(serie: pd.DataFrame, horizonte: int) -> dict:
    anio, mes = map(int, str(serie["Periodo"].iloc[-1]).split("_"))
    total = anio * 12 + mes - 1 + horizonte
    return ejecutar_proyeccion(serie, total // 12, total % 12 + 1, ANIO_BASE)


def _datos(serie: pd.DataFrame, resultado: dict, fuente: str = "T_16_13") -> DatosProyeccion:
    return DatosProyeccion(
        resultado=resultado,
        serie_df=serie,
        fuente_label=fuente,
        archivo_excel="anexo_sintetico.xlsb",
        ruta_jerarquica=RUTA,
        fila=pd.DataFrame([{"Tip_obra_Cap_constr": "Serie bloqueada de prueba"}]),
        year_month=list(serie["Periodo"]),
        usuario="Prueba de regresión RA-03",
    )


def sin_ajuste(resultado: dict) -> dict:
    """Reproduce la forma exacta de C-11: histórico completo y ajuste vacío.

    ``_resultado_no_proyectable`` deja ``y_fit_obs`` vacío cuando el modelo se
    ajustó sobre una serie de trabajo de otra longitud. Ese es el estado que
    rompía la exportación DOCX/PDF.
    """
    copia = dict(resultado)
    copia["y_fit_obs"] = np.asarray([], dtype=float)
    copia["y_fit_full"] = np.asarray([], dtype=float)
    return copia


def bloqueado(resultado: dict) -> bool:
    proyecciones = resultado.get("proyecciones")
    return not bool(resultado.get("proyeccion_generada")) or not (
        isinstance(proyecciones, pd.DataFrame) and not proyecciones.empty
    )


def exportar_los_tres(serie: pd.DataFrame, resultado: dict, destino: Path) -> dict[str, Path]:
    comunes = (
        "Prueba de regresión RA-03", "anexo_sintetico.xlsb", {},
        {"horizonte": int(resultado.get("horizonte_solicitado") or 0)}, RUTA,
        "T_16_13", pd.DataFrame([{"Tip_obra_Cap_constr": "Serie bloqueada de prueba"}]),
        serie, resultado, list(serie["Periodo"]),
    )
    return {
        "csv": Path(construir_csv_reproducible(destino / "bloqueada.csv", serie, resultado, RUTA)),
        "docx": Path(generar_reporte_proyeccion(destino / "bloqueada.docx", *comunes)),
        "pdf": Path(generar_reporte_pdf(destino / "bloqueada.pdf", *comunes)),
    }


def texto_docx(ruta: Path) -> str:
    with zipfile.ZipFile(ruta) as paquete:
        return paquete.read("word/document.xml").decode("utf-8", "replace")


#: El informe técnico es el que incluye modelos, métricas, cobertura y residuos.
CONFIG = ConfiguracionInforme.desde_tipo("tecnico")


def texto_informe(datos: DatosProyeccion) -> str:
    informe = construir_informe_proyeccion(datos, CONFIG)
    partes: list[str] = []

    def recorrer(bloque) -> None:
        for atributo in ("titulo", "texto", "encabezado"):
            valor = getattr(bloque, atributo, None)
            if isinstance(valor, str):
                partes.append(valor)
        for atributo in ("filas", "puntos", "destacados", "encabezados"):
            valor = getattr(bloque, atributo, None)
            if isinstance(valor, (list, tuple)):
                for elemento in valor:
                    if isinstance(elemento, (list, tuple)):
                        partes.extend(str(x) for x in elemento)
                    else:
                        partes.append(str(elemento))

    for seccion in informe.secciones:
        partes.append(seccion.titulo)
        for bloque in seccion.bloques:
            recorrer(bloque)
    return "\n".join(partes)


def tablas_de(datos: DatosProyeccion) -> list[Tabla]:
    informe = construir_informe_proyeccion(datos, CONFIG)
    return [b for s in informe.secciones for b in s.bloques if isinstance(b, Tabla)]


# ===========================================================
# RA-03: la serie bloqueada exporta en los tres formatos
# ===========================================================


def test_la_serie_sintetica_queda_efectivamente_bloqueada():
    """Sin este presupuesto, las demas pruebas no probarian nada.

    P0-G, 16-08-2026: se comprueba la frontera POR AMBOS LADOS. No basta con que
    el horizonte elegido se bloquee; hay que verificar que se bloquea por la
    causa declarada -cero ventanas- y que el horizonte inmediatamente anterior,
    que si reune una, SE ENTREGA. Asi la prueba distingue una imposibilidad
    aritmetica de un veto reintroducido: si alguien devolviera un piso de
    ventanas, el horizonte anterior dejaria de entregarse y esto fallaria.
    """
    serie = serie_bloqueada()
    n = len(serie)
    entrenamiento = _limites_auditoria_horizontes(n)[0]
    ventanas = lambda h: n - entrenamiento - h + 1  # noqa: E731

    assert ventanas(HORIZONTE_SIN_VENTANAS) < 1, (n, entrenamiento, HORIZONTE_SIN_VENTANAS)
    assert ventanas(HORIZONTE_SIN_VENTANAS - 1) >= 1, "el horizonte anterior si tiene ventana"

    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    assert bloqueado(resultado), resultado.get("resultado_horizonte_solicitado")
    assert len(np.asarray(resultado.get("y_obs", []))) > 0, "el historico si existe"
    proyecciones = resultado.get("proyecciones")
    assert not isinstance(proyecciones, pd.DataFrame) or proyecciones.empty

    # El lado contrario de la frontera: con UNA sola ventana el punto se entrega.
    anterior = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS - 1)
    assert anterior["proyeccion_generada"] is True, anterior.get("explicacion")


def test_la_grafica_de_residuos_se_omite_sin_reventar():
    """El defecto exacto: restar y_obs (65) con y_fit_obs (0)."""
    serie = serie_bloqueada()
    resultado = sin_ajuste(proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS))
    assert len(np.asarray(resultado["y_obs"])) == len(serie)
    assert graficas.grafica_residuos(resultado) is None
    # Caso general de longitudes incompatibles, no solo el vector vacio.
    assert graficas.grafica_residuos({"y_obs": np.arange(65.0), "y_fit_obs": np.arange(10.0)}) is None
    assert graficas.grafica_residuos({"y_obs": np.arange(65.0), "y_fit_obs": np.array([])}) is None


def test_csv_docx_y_pdf_se_generan_con_ajuste_vacio_como_en_c11():
    """Regresión directa del ValueError (65,) vs (0,) que rompía la exportación."""
    serie = serie_bloqueada()
    resultado = sin_ajuste(proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS))
    with TemporaryDirectory() as tmp:
        archivos = exportar_los_tres(serie, resultado, Path(tmp))
        assert archivos["pdf"].read_bytes()[:5] == b"%PDF-"
        with zipfile.ZipFile(archivos["docx"]) as paquete:
            assert "word/document.xml" in paquete.namelist()
        assert archivos["csv"].stat().st_size > 0


def test_la_grafica_principal_muestra_solo_el_historico():
    serie = serie_bloqueada()
    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    imagen = graficas.grafica_principal(serie, resultado)
    assert imagen is not None, "debe dibujarse la serie histórica"
    assert imagen[:4] == b"\x89PNG"


def test_csv_docx_y_pdf_se_generan_para_una_serie_bloqueada():
    serie = serie_bloqueada()
    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    assert bloqueado(resultado)
    with TemporaryDirectory() as tmp:
        archivos = exportar_los_tres(serie, resultado, Path(tmp))
        for nombre, ruta in archivos.items():
            assert ruta.exists() and ruta.stat().st_size > 0, nombre
        assert archivos["pdf"].read_bytes()[:5] == b"%PDF-", "cabecera PDF"
        with zipfile.ZipFile(archivos["docx"]) as paquete:
            assert "word/document.xml" in paquete.namelist(), "DOCX válido"
        cabecera = archivos["csv"].read_text(encoding="utf-8-sig").splitlines()[0]
        assert "," in cabecera and cabecera.strip(), "CSV con cabecera"


def test_el_informe_bloqueado_declara_las_ausencias_y_no_inventa_trayectoria():
    serie = serie_bloqueada()
    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    datos = _datos(serie, resultado)
    texto = texto_informe(datos).lower()
    # P0-C / ESTRATEGIA C2, 15-08-2026. La fila del intervalo decia «No
    # corresponde: sin proyeccion no hay banda que acotar», y el test exigia esa
    # frase y la mencion literal «intervalo de prediccion del 95 %». Con el
    # intervalo retirado de TODA salida, esa redaccion sugeria que la banda
    # existe en el caso normal y solo falta aqui por estar bloqueada la serie.
    # La razon es otra y es la misma en los dos casos: no se publica.
    #
    # La propiedad que el test protege -que el informe bloqueado DECLARE cada
    # ausencia en vez de callarla o inventar una trayectoria- no cambia.
    for exigido in (
        "bloqueado",
        "no existe",
        "no se publica en esta versión",
        "no generado",
    ):
        assert exigido in texto, f"el informe bloqueado debe declarar «{exigido}»"
    assert "intervalo de predicción" in texto
    # Y no reaparece la banda con su nivel nominal.
    assert "intervalo de predicción del 95 %" not in texto, texto[:400]
    # No debe haber ninguna tabla de trayectoria proyectada.
    encabezados = [tuple(t.encabezados) for t in tablas_de(datos)]
    assert not [e for e in encabezados if "Índice proyectado" in e and "Periodo" in e], (
        "no debe publicarse una tabla de proyección mes a mes"
    )


def test_el_motivo_del_bloqueo_es_el_mismo_en_interfaz_y_en_reportes():
    from app_icociv.interfaz.presentacion_resultados import construir_html_resultados

    serie = serie_bloqueada()
    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    solicitado = resultado.get("resultado_horizonte_solicitado") or {}
    estado = str(solicitado.get("estado") or "")
    assert estado == "no_admisible", solicitado

    html = construir_html_resultados(resultado).lower()
    datos = _datos(serie, resultado)
    informe = texto_informe(datos).lower()
    for texto in (html, informe):
        assert "no admisible" in texto, "el estado visible debe coincidir"
        assert "no generad" in texto or "no se generó" in texto


def test_el_informe_bloqueado_conserva_diagnosticos_y_modelos_evaluados():
    serie = serie_bloqueada()
    resultado = proyectar(serie, horizonte=HORIZONTE_SIN_VENTANAS)
    datos = _datos(serie, resultado)
    texto = texto_informe(datos)
    for exigido in ("Identificación de la serie", "Modelos evaluados", "Diagnóstico de residuos"):
        assert exigido in texto, f"falta la sección «{exigido}»"
    assert "Periodo analizado" in texto or "Periodo inicial" in texto


# ===========================================================
# RA-05: una metrica no puede estar disponible y no disponible
# ===========================================================

#: Columna de la tabla de modelos -> clave de la fuente unica de metricas.
COLUMNAS_METRICAS = {"MAE": "mae", "RMSE": "rmse", "MASE": "mase", "Sesgo": "sesgo_medio"}


def test_la_tabla_de_modelos_lee_las_claves_que_el_catalogo_publica():
    resultado = proyectar(serie_normal(), horizonte=6)
    catalogo = [c for c in (resultado.get("catalogo_modelos") or []) if c.get("ejecutado") == "Si"]
    assert catalogo, "debe haber al menos un modelo ejecutado"
    for item in catalogo:
        for clave in COLUMNAS_METRICAS.values():
            assert clave in item, f"el catálogo debe publicar «{clave}»"
            assert item[clave] is not None, f"«{clave}» no debe llegar vacío para un modelo ejecutado"


def test_ninguna_metrica_aparece_disponible_en_una_seccion_y_no_disponible_en_otra():
    """Falla si tabla y texto se contradicen sobre la misma métrica."""
    serie = serie_normal()
    resultado = proyectar(serie, horizonte=6)
    datos = _datos(serie, resultado, fuente="T_16")
    metricas_backtesting = (resultado.get("backtesting") or {}).get("metricas") or {}
    tabla_modelos = next(
        (t for t in tablas_de(datos) if "MASE" in t.encabezados and "Modelo" in t.encabezados),
        None,
    )
    assert tabla_modelos is not None, "debe existir la tabla de modelos evaluados"

    seleccionado = str(resultado.get("model_name") or "")
    fila_seleccionada = next(
        (f for f in tabla_modelos.filas if str(f[-1]).strip().lower().startswith("seleccionado")),
        None,
    )
    assert fila_seleccionada is not None, f"no se halló la fila del modelo aplicado ({seleccionado})"

    for columna, clave in COLUMNAS_METRICAS.items():
        posicion = tabla_modelos.encabezados.index(columna)
        celda = str(fila_seleccionada[posicion]).strip()
        disponible_en_fuente = metricas_backtesting.get(clave) is not None and np.isfinite(
            float(metricas_backtesting[clave])
        )
        if disponible_en_fuente:
            assert celda != "No disponible", (
                f"«{columna}» está disponible en el backtesting ({metricas_backtesting[clave]}) "
                "pero la tabla del informe la declara no disponible"
            )


def test_la_tabla_y_el_texto_publican_el_mismo_rmse():
    serie = serie_normal()
    resultado = proyectar(serie, horizonte=6)
    datos = _datos(serie, resultado, fuente="T_16")
    from app_icociv.reportes.modelo import formato_indice

    rmse = (resultado.get("backtesting") or {}).get("metricas", {}).get("rmse")
    assert rmse is not None
    esperado = formato_indice(rmse)
    tabla_modelos = next(t for t in tablas_de(datos) if "MASE" in t.encabezados)
    fila = next(f for f in tabla_modelos.filas if str(f[-1]).strip().lower().startswith("seleccionado"))
    posicion = tabla_modelos.encabezados.index("RMSE")
    assert str(fila[posicion]).strip() == esperado, (fila[posicion], esperado)


# ==============================
# CORREDOR
# ==============================


def main() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except Exception:
            fallos += 1
            print(f"  FALLA {prueba.__name__}")
            traceback.print_exc()
    total = len(pruebas)
    print(f"\n{total - fallos}/{total} pruebas de informes de serie bloqueada y coherencia de métricas")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
