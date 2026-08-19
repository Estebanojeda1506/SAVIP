"""Guardas dirigidas para los residuales H-1A, H-2, H-4 y H-6 de la
reauditoria final V-CODEX-R2 (verdicto R2_CIERRE_CON_CORRECCION_DIRIGIDA).

A diferencia de `test_remediacion_r2_h1_h2_h3_h7.py` (que cubre H-1/H-2/H-3/H-7
de la fase anterior), estas pruebas invocan directamente las funciones de
`generador_reportes.py` y `contenido.py` con datos sinteticos, SIN depender
del anexo `.xlsb`, porque la reauditoria señalo que las guardas previas para
H-1 y H-2 podian pasar de forma vacia sin el anexo o no ejercitaban
`generador_reportes.py` en absoluto.

H-1A  `_lineas_determinacion_horizonte` (generador_reportes.py) no cita el
      intervalo retirado como fundamento del horizonte maximo.
H-2A  `_lineas_cobertura_empirica` (generador_reportes.py) no afirma una
      sustitucion del modelo ni un fallo de benchmark no comprobado.
H-4   Ninguna superficie (generador_reportes.py, contenido.py,
      `_estado_horizonte_visible`) presenta "escenario [de alta
      incertidumbre]" como estado alcanzable: el productor real solo fija
      "proyeccion_tecnica" o "no_admisible" desde el 08-08-2026.
H-6   El parrafo de main.tex ya no referencia `tab:matriz_conceptual` como
      fuente de la escalera de uso comunicado, y ninguna tabla del documento
      tiene un `\\toprule` pegado a su `\\caption`/`\\label` sin `\\vspace`.
N-1   Correccion unica final N-1, 18-08-2026 (reauditoria V-CODEX-R2). El
      mensaje de restriccion de horizonte en `_ejecutar_proyeccion_base`
      atribuia la causa a "el maximo permitido como escenario", un campo
      siempre 0/no identificado; el horizonte y el numero citados venian en
      realidad de `horizonte_maximo_admisible`. Se verifica con una serie
      sintetica (sin anexo DANE) que alcanza realmente la restriccion.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from app_icociv.reportes.generador_reportes import (
    _estado_horizonte_visible,
    _lineas_cobertura_empirica,
    _lineas_determinacion_horizonte,
)
from app_icociv.reportes.contenido import DatosProyeccion, resumen_ejecutivo
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion

MAIN_TEX = ROOT / "documentacion_latex" / "documento_tecnico_icociv_iccp" / "main.tex"


# ---------------------------------------------------------------- H-1A -----
def test_h1a_determinacion_horizonte_no_cita_intervalos_como_fundamento():
    """Con datos sinteticos (sin anexo), ninguna linea cita el intervalo
    retirado como fundamento del horizonte maximo, y el criterio vigente
    (backtesting + evidencia fuera de muestra) si aparece."""
    resultado = {
        "analisis_horizontes_completo": {
            "mensaje_informe": "Horizonte maximo recomendado por backtesting y evidencia fuera de muestra.",
            "horizonte_solicitado": 12,
            "horizontes_evaluados": [1, 3, 6, 12],
            "horizonte_maximo_recomendado": 12,
            "horizonte_maximo_evaluado": 12,
            "tabla_horizontes": [
                {"horizonte": 1, "no_recomendable": False},
                {"horizonte": 12, "no_recomendable": False},
            ],
        }
    }
    lineas = _lineas_determinacion_horizonte(resultado)
    texto = " ".join(lineas).lower()
    assert "e intervalos" not in texto, f"cita el intervalo retirado como fundamento: {lineas!r}"
    assert "backtesting e intervalos" not in texto
    assert "backtesting" in texto and "evidencia fuera de muestra" in texto, (
        "no aparece el criterio vigente (backtesting + evidencia fuera de muestra)"
    )


# ---------------------------------------------------------------- H-2A -----
def test_h2a_cobertura_empirica_no_afirma_sustitucion_ni_fallo_no_comprobado():
    """Con benchmark_habria_ampliado=True, generador_reportes.py debe decir
    la verdad (al menos un benchmark habria llegado mas lejos, sin sustituir
    el modelo publicado) y nunca la sustitucion falsa ni que los benchmarks
    "tampoco" cumplieron."""
    resultado = {
        "salvaguarda_benchmark": {
            "intentada": True,
            "activada": False,
            "modelo_principal": "holt_amortiguado",
            "razon_fallo_principal": "h=18: evidencia insuficiente",
            "benchmark_habria_ampliado": True,
            "benchmarks_evaluados": [
                {"nombre": "drift", "cumple": True, "rmse_ponderado": 0.9, "h_max_admisible": 18},
                {"nombre": "naive", "cumple": False, "rmse_ponderado": 1.4, "h_max_admisible": 6},
            ],
        }
    }
    lineas = _lineas_cobertura_empirica(resultado)
    texto = " ".join(lineas).lower()
    assert "tampoco" not in texto, f"afirma que los benchmarks tampoco cumplieron (falso): {lineas!r}"
    assert "se aplicó" not in texto and "toda la trayectoria proyectada" not in texto, (
        f"afirma una sustitucion de modelo que no ocurrio: {lineas!r}"
    )
    assert "no sustitución" in texto or "no sustitucion" in texto, (
        f"no aclara que la salvaguarda es diagnostica, sin sustitucion: {lineas!r}"
    )
    assert "alcanzaría un horizonte mayor" in texto or "alcanzaria un horizonte mayor" in texto, (
        f"no publica honestamente que un benchmark habria llegado mas lejos: {lineas!r}"
    )


def test_h2a_benchmark_habria_ampliado_false_tampoco_inventa_sustitucion():
    """Con benchmark_habria_ampliado=False, el texto dice que NINGUN benchmark
    habria llegado mas lejos, sin inventar una sustitucion tampoco."""
    resultado = {
        "salvaguarda_benchmark": {
            "intentada": True,
            "activada": False,
            "modelo_principal": "drift",
            "razon_fallo_principal": "h=12: evidencia insuficiente",
            "benchmark_habria_ampliado": False,
            "benchmarks_evaluados": [],
        }
    }
    lineas = _lineas_cobertura_empirica(resultado)
    texto = " ".join(lineas).lower()
    assert "ningún benchmark alcanzaría un horizonte mayor" in texto or \
        "ningun benchmark alcanzaria un horizonte mayor" in texto
    assert "se aplicó" not in texto and "modelo finalmente aplicado" not in texto


# ------------------------------------------------------------------ H-4 -----
def test_h4_determinacion_horizonte_no_presenta_escenario_como_estado():
    """Aun con un item sintetico que declare permitido_como_escenario=True y
    permitido_para_proyeccion_tecnica=False (combinacion que ya no produce el
    evaluador vigente, pero se fuerza aqui de forma adversarial), la funcion
    de generador_reportes.py no debe emitir 'escenario de alta incertidumbre'
    como si fuera un estado real: esa rama fue retirada por completo."""
    resultado = {
        "analisis_horizontes_completo": {
            "tabla_horizontes": [
                {
                    "horizonte": 18,
                    "no_recomendable": False,
                    "permitido_como_escenario": True,
                    "permitido_para_proyeccion_tecnica": False,
                },
            ],
        }
    }
    lineas = _lineas_determinacion_horizonte(resultado)
    texto = " ".join(lineas).lower()
    assert "escenario de alta incertidumbre" not in texto, (
        f"presenta un estado inalcanzable como si fuera real: {lineas!r}"
    )


def test_h4_resumen_ejecutivo_no_presenta_escenario_como_estado():
    """contenido.resumen_ejecutivo, con horizonte solicitado por encima del
    maximo recomendado, describe la cautela por evidencia sin el rotulo
    'escenario de alta incertidumbre' ni la referencia falsa a
    tab:matriz_conceptual."""
    resultado = {
        "resultado_horizonte_solicitado": {
            "horizonte_solicitado": 18,
            "proyeccion_generada": True,
            "modelo_aplicado": "Drift",
            "estado": "proyeccion_tecnica",
        },
        "analisis_horizontes_completo": {"horizonte_maximo_recomendado": 12},
        "proyecciones": pd.DataFrame(
            {
                "periodo": ["2027_06"],
                "indice_proyectado": [145.0],
                "variacion_acumulada_pct": [0.05],
            }
        ),
        "advertencias_categorizadas": {},
        "factibilidad": {"advertencias": []},
    }
    datos = DatosProyeccion(
        resultado=resultado,
        serie_df=pd.DataFrame({"Periodo": ["2026_01"], "Indice": [140.0]}),
    )
    parrafos = resumen_ejecutivo(datos)
    texto = " ".join(parrafos).lower()
    assert "escenario de alta incertidumbre" not in texto, f"rotulo retirado reaparecio: {parrafos!r}"
    assert "tab:matriz_conceptual" not in texto


def test_h4_estado_horizonte_visible_ya_no_traduce_escenario():
    """_estado_horizonte_visible ya no mapea 'escenario' a un texto de estado
    valido: al no existir mas ese estado en el productor, la clave se
    retiro. Si algun dato legado trajera 'escenario' de todos modos, la
    funcion debe devolver el valor crudo (nunca inventar una traduccion
    'Escenario de alta incertidumbre')."""
    assert _estado_horizonte_visible("proyeccion_tecnica") == "Proyección técnica"
    assert _estado_horizonte_visible("no_admisible") == "No admisible"
    assert _estado_horizonte_visible("escenario") != "Escenario de alta incertidumbre"


# ------------------------------------------------------------------ H-6 -----
def test_h6b_main_tex_no_referencia_matriz_conceptual_para_la_escalera():
    if not MAIN_TEX.exists():
        print("  OMITIDA test_h6b (main.tex no encontrado en este checkout)")
        return
    texto = MAIN_TEX.read_text(encoding="utf-8")
    inicio = texto.find("Conviene distinguir dos columnas")
    assert inicio != -1, "no se encontro el parrafo que describe la escalera de uso comunicado"
    parrafo = texto[inicio : inicio + 600]
    assert "matriz_conceptual" not in parrafo, (
        "el parrafo vuelve a referenciar tab:matriz_conceptual, que no contiene la escalera"
    )
    assert "hasta 18" in parrafo or "18," in parrafo, (
        "el parrafo ya no describe los umbrales de la escalera directamente"
    )


def test_h6a_ninguna_tabla_tiene_toprule_pegado_al_caption_sin_espaciado():
    """Guarda de regresion para H-6A: en cada bloque `\\caption{...}` con
    `\\label{tab:...}` que abra un `\\toprule` en las siguientes lineas, debe
    existir una separacion vertical explicita antes de ese `\\toprule`:
    `\\vspace` (patron usado en la mayoria de las tablas), `\\setstretch`
    (patron de `tab:matriz_conceptual`, verificado sin el defecto de forma
    visual) o `\\\\[` (fila con espaciado extra, patron del longtable
    `tab:matriz_pruebas`). Sin alguna de las tres, TeX puede colapsar el
    interlineado automatico cuando el `\\toprule` es mas alto que un
    `\\baselineskip` y la regla termina pegada a la leyenda."""
    if not MAIN_TEX.exists():
        print("  OMITIDA test_h6a (main.tex no encontrado en este checkout)")
        return
    lineas = MAIN_TEX.read_text(encoding="utf-8").split("\n")
    marcas_validas = ("\\vspace", "\\setstretch", "\\\\[")
    fallos: list[int] = []
    for i, linea in enumerate(lineas):
        if "\\caption{" not in linea:
            continue
        ventana = lineas[i : i + 8]
        conjunto = "\n".join(ventana)
        if "\\label{tab:" not in conjunto or "\\toprule" not in conjunto:
            continue
        antes_de_toprule = conjunto.split("\\toprule")[0]
        if not any(marca in antes_de_toprule for marca in marcas_validas):
            fallos.append(i + 1)
    assert not fallos, f"caption(s) sin espaciado explicito antes de \\toprule en las lineas: {fallos}"


# ------------------------------------------------------------------ N-1 -----
def test_n1_restriccion_de_horizonte_cita_el_maximo_admisible_real():
    """N-1, 18-08-2026 (correccion unica final N-1, reauditoria V-CODEX-R2).

    Serie sintetica (sin anexo DANE): tendencia lineal de 24 observaciones
    mensuales, 2020-01 a 2021-12. Con N0=6 y sin ningun horizonte no viable,
    el maximo admisible queda en h=18 (cota de existencia n-N0=18). Se
    solicita h=24, que la excede, alcanzando de verdad la rama de
    restriccion cuyo mensaje corrige N-1.
    """
    n = 24
    periodos = [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(n)]
    valores = [100.0 + 0.5 * i for i in range(n)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": valores})

    resultado = ejecutar_proyeccion(serie, 2023, 12, 2020)

    assert resultado.get("horizonte_solicitado") == 24, resultado.get("horizonte_solicitado")
    assert resultado.get("proyeccion_generada") is False
    info = resultado.get("analisis_horizontes_completo") or {}
    assert info.get("horizonte_maximo_admisible") == 18, info.get("horizonte_maximo_admisible")

    explicacion = str(resultado.get("explicacion") or "")
    assert explicacion.strip(), "la restriccion no alcanzo el mensaje de explicacion"

    baja = explicacion.lower()
    assert "máximo admisible" in baja or "maximo admisible" in baja, explicacion
    assert "h=18" in baja or "(18" in baja or "18 meses" in baja, explicacion
    assert "evidencia fuera de muestra" in baja, explicacion

    assert "permitido como escenario" not in baja, explicacion
    assert "escenario de alta incertidumbre" not in baja, explicacion
    assert "máximo como escenario" not in baja and "maximo como escenario" not in baja, explicacion
    assert "intervalo" not in baja, explicacion


def _principal() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    fallos = 0
    for nombre, funcion in pruebas:
        try:
            funcion()
            print(f"  OK   {nombre}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {nombre}: {exc}")
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {nombre}: {type(exc).__name__}: {exc}")
    print()
    print("todas las pruebas pasan" if not fallos else f"{fallos} fallo(s) de {len(pruebas)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_principal())
