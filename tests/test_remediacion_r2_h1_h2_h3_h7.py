"""Guardas dirigidas para H-1, H-2, H-3 y H-7 de la auditoria final V-CODEX-R2.

Fijan CONDUCTA (mensajes publicos y clasificacion resultante), no texto de
codigo fuente, salvo donde se comprueba directamente la ausencia de una rama
muerta.

H-1  ningun mensaje publico presenta el intervalo retirado como fundamento.
H-2  la salvaguarda nunca sustituye el modelo, y sus mensajes no afirman una
     sustitucion ni un fallo de benchmark que no se comprobo.
H-3  la escalera de horizonte por longitud, la autocorrelacion y la
     continuidad ya no recortan el horizonte publicado ni generan la
     advertencia "rango estadisticamente defendible".
H-7  el criterio de seleccion publicado es RMSE OOS global; no queda
     ponderacion 1/h en ningun fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from app_icociv.estadistica.analisis_series import (
    evaluar_factibilidad_proyeccion,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.proyeccion.servicio_proyeccion import (
    _aplicar_salvaguarda_benchmarks,
    _clasificar_evidencia_horizonte,
    seleccionar_modelo_por_rmse_oos_global,
)

RUTA_ANEXO = ROOT / "anex-ICOCIV-ene2026.xlsb"
_CACHE: dict[str, object] = {}


def _serie(tabla: str, idx: int):
    clave = f"{tabla}:{idx}"
    if clave in _CACHE:
        return _CACHE[clave]
    if not RUTA_ANEXO.exists():
        _CACHE[clave] = None
        return None
    from app_icociv.datos.cargador_datos import cargar_todas_tablas
    from app_icociv.proyeccion.servicio_proyeccion import construir_serie

    tablas, year_month = cargar_todas_tablas(RUTA_ANEXO.read_bytes(), RUTA_ANEXO.name)
    _CACHE[clave] = construir_serie(tablas[tabla].loc[[idx]], year_month)
    return _CACHE[clave]


def _proyectar(serie, horizonte: int = 1):
    from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
    from app_icociv.utilidades.utilidades import ANIO_BASE

    ultimo = str(serie["Periodo"].iloc[-1])
    anio, mes = map(int, ultimo.split("_"))
    total = anio * 12 + (mes - 1) + int(horizonte)
    return ejecutar_proyeccion(
        serie, total // 12, total % 12 + 1, ANIO_BASE, origen_horizonte="manual"
    )


def _todos_los_mensajes_publicos(resultado: dict) -> list[str]:
    """Reune todo texto publico alcanzable en un resultado real."""
    textos: list[str] = []
    rhs = resultado.get("resultado_horizonte_solicitado") or {}
    for clave in ("nivel_confianza", "explicacion", "mensaje"):
        v = rhs.get(clave)
        if isinstance(v, str):
            textos.append(v)
    ahc = resultado.get("analisis_horizontes_completo") or {}
    for item in ahc.get("estado_por_horizonte") or []:
        for clave in ("mensaje", "decision", "estado", "recomendacion"):
            v = item.get(clave)
            if isinstance(v, str):
                textos.append(v)
        for adv in item.get("advertencias") or []:
            if isinstance(adv, str):
                textos.append(adv)
    for clave in ("explicacion", "justificacion_modelo"):
        v = resultado.get(clave)
        if isinstance(v, str):
            textos.append(v)
    proy = resultado.get("proyecciones")
    if proy is not None and hasattr(proy, "get"):
        for col in ("advertencias",):
            if col in getattr(proy, "columns", []):
                for celda in proy[col]:
                    if isinstance(celda, str):
                        textos.append(celda)
                    elif isinstance(celda, list):
                        textos.extend(x for x in celda if isinstance(x, str))
    return textos


# ----------------------------------------------------------------- H-1 -----
def test_h1_ningun_mensaje_publico_cita_intervalos_como_fundamento():
    """H-1A: 'segun backtesting e intervalos' no debe aparecer en salida publica."""
    for tabla, idx in (("T_16_2", 6), ("T_16_7", 0)):
        serie = _serie(tabla, idx)
        if serie is None:
            print(f"  OMITIDA test_h1 ({tabla}:{idx}, falta el anexo)")
            continue
        for h in (1, 6, 18):
            res = _proyectar(serie, h)
            for texto in _todos_los_mensajes_publicos(res):
                baja = texto.lower()
                assert "e intervalos" not in baja, (
                    f"h={h}: mensaje publico cita intervalos como fundamento: {texto!r}"
                )
                assert "intervalos son razonables" not in baja, (
                    f"h={h}: mensaje publico cita intervalos como fundamento: {texto!r}"
                )


def test_h1_la_defensa_de_un_horizonte_sin_cautelas_no_menciona_intervalos():
    """El mensaje reachable en el branch 'tecnica_alta' ya no cita 'e intervalos'."""
    evidencia = _clasificar_evidencia_horizonte(
        horizonte=1,
        modelo={"nombre_visible": "Drift", "es_benchmark": False},
        backtesting={"metricas": {"rmse": 1.0, "mae": 1.0, "mape": 1.0, "smape": 1.0,
                                   "mase": 0.5, "sesgo_medio": 0.0, "estabilidad_error": 0.1,
                                   "iteraciones": 10},
                     "iteraciones": 10},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": "banda_calculada"},
    )
    assert evidencia["clasificacion"] == "tecnica_alta"
    assert "e intervalos" not in evidencia["mensaje"].lower()
    assert "backtesting" in evidencia["mensaje"].lower()


# ----------------------------------------------------------------- H-2 -----
def test_h2_la_salvaguarda_nunca_cambia_el_modelo_final():
    """Sea cual sea el resultado de los benchmarks, modelo_final == modelo_principal."""
    for tabla, idx in (("T_16_7", 0), ("T_16_2", 6)):
        serie = _serie(tabla, idx)
        if serie is None:
            print(f"  OMITIDA test_h2_modelo_final ({tabla}:{idx}, falta el anexo)")
            continue
        res = _proyectar(serie, 1)
        salv = res.get("salvaguarda_benchmark") or {}
        assert salv.get("modelo_final") == salv.get("modelo_principal"), (
            f"la salvaguarda cambio el modelo: {salv}"
        )
        assert salv.get("activada") is False, "activada dejo de ser siempre False"


def test_h2_benchmark_habria_ampliado_no_implica_sustitucion():
    """benchmark_habria_ampliado=True puede coexistir con modelo principal intacto."""
    evaluaciones = [
        {"horizonte": 1, "no_recomendable": False, "bloqueo_por_datos": False},
    ]
    _, modelo_final, salvaguarda = _aplicar_salvaguarda_benchmarks(
        evaluaciones=evaluaciones,
        modelo_consistente="holt_amortiguado",
        candidatos=[{"nombre": "holt_amortiguado", "predict": lambda t: t},
                    {"nombre": "drift", "predict": lambda t: t},
                    {"nombre": "naive", "predict": lambda t: t}],
        backtesting_comparativo={},
        horizontes=(1,),
        serie_trabajo=None,
        validacion_serie={},
        outliers=[],
        t_ultimo=10,
        y_obs=np.array([1.0, 2.0, 3.0]),
        anio_base=2020,
        horizonte_solicitado=1,
    )
    # Sin fallo (no_recomendable=False en todas), la salvaguarda ni se intenta.
    assert salvaguarda["intentada"] is False
    assert modelo_final == "holt_amortiguado"


def test_h2_ningun_texto_publico_afirma_sustitucion_o_fallo_no_evaluado():
    """Ningun texto alcanzable dice 'se aplico X a toda la trayectoria' por la salvaguarda."""
    from app_icociv.interfaz.presentacion_resultados import _bloque_salvaguarda_benchmark
    from app_icociv.reportes.contenido import _seccion_seleccion_modelo, DatosProyeccion

    salvaguarda_intentada = {
        "intentada": True,
        "activada": False,
        "modelo_principal": "holt_amortiguado",
        "razon_fallo_principal": "h=18: evidencia insuficiente",
        "modelo_final": "holt_amortiguado",
        "h_max_antes": 12,
        "h_max_despues": 12,
        "benchmark_habria_ampliado": True,
        "benchmarks_evaluados": [
            {"nombre": "drift", "cumple": True, "rmse_ponderado": 0.9, "h_max_admisible": 18},
        ],
    }
    html = _bloque_salvaguarda_benchmark({"salvaguarda_benchmark": salvaguarda_intentada})
    baja = html.lower()
    assert "tampoco" not in baja, f"el bloque HTML afirma que los benchmarks tampoco cumplieron: {html!r}"
    assert "modelo finalmente aplicado" not in baja, "el rotulo de sustitucion inexistente sigue presente"
    assert "no sustituye" in baja or "sin cambios" in baja, "el bloque no aclara que no hay sustitucion"


# ----------------------------------------------------------------- H-3 -----
def test_h3_ljung_box_no_reduce_el_horizonte_maximo_publicado():
    """Una advertencia de autocorrelacion no debe generar el recorte retirado."""
    serie = normalizar_serie_mensual(pd_serie_lineal(n=40))
    validacion = validar_serie_mensual(serie)
    resultado = evaluar_factibilidad_proyeccion(
        serie=serie,
        validacion=validacion,
        outliers=[],
        horizonte_solicitado=24,
        diagnostico={"ljung_box": {"p_value": 0.0001}},
    )
    for adv in resultado.get("advertencias", []):
        assert "rango estad" not in adv.lower(), (
            f"la advertencia retirada reaparecio: {adv!r}"
        )


def test_h3_longitud_18_24_36_60_84_no_crea_cap_ad_hoc():
    """Ninguna longitud de serie por si sola debe producir la advertencia retirada."""
    for n in (18, 24, 36, 60, 84, 90):
        serie = normalizar_serie_mensual(pd_serie_lineal(n=n))
        validacion = validar_serie_mensual(serie)
        resultado = evaluar_factibilidad_proyeccion(
            serie=serie, validacion=validacion, outliers=[], horizonte_solicitado=n + 5,
        )
        for adv in resultado.get("advertencias", []):
            assert "rango estad" not in adv.lower(), (
                f"n={n}: la advertencia retirada reaparecio: {adv!r}"
            )


def test_h3_seleccion_y_punto_no_cambian_para_un_caso_representativo():
    """H-3 solo debe afectar clasificacion/mensaje, nunca el modelo ni el punto."""
    serie = _serie("T_16_2", 6)
    if serie is None:
        print("  OMITIDA test_h3_seleccion_y_punto (falta el anexo)")
        return
    res = _proyectar(serie, 1)
    assert res.get("model_name") == "Drift", f"el modelo gandor cambio: {res.get('model_name')}"
    proy = res.get("proyecciones")
    assert proy is not None and len(proy) > 0
    assert abs(float(proy["indice_proyectado"].iloc[0]) - 140.8567) < 1e-3, (
        "el punto proyectado cambio con la remediacion H-3"
    )


# ----------------------------------------------------------------- H-7 -----
def test_h7_el_fallback_de_justificacion_describe_rmse_oos_global():
    from app_icociv.reportes.contenido import _seccion_seleccion_modelo

    class Falso:
        resultado = {"salvaguarda_benchmark": {}}

    seccion = _seccion_seleccion_modelo(Falso())
    texto = " ".join(
        b.texto if hasattr(b, "texto") else str(b)
        for b in seccion.bloques
    ).lower()
    assert "rmse" in texto
    assert "ponderado por horizonte" not in texto


def pd_serie_lineal(n: int):
    import pandas as pd

    periodos = [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(n)]
    valores = [100.0 + 0.5 * i for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


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
