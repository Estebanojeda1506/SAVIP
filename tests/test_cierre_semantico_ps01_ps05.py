"""Cierre semantico PS-01..PS-05 (18-08-2026).

Fija CONDUCTA, no texto de codigo fuente. Cada prueba corresponde a un hallazgo
resuelto en el cierre semantico y falla si la conducta se revierte.

PS-01  la salvaguarda por benchmark es diagnostica: no sustituye el modelo.
PS-02  las metricas por horizonte de la ruta de referencia son reproducibles.
PS-03  la negacion de un horizonte tiene exactamente dos causas, ambas
       imposibilidades: punto no finito, o W = 0 (inexistencia del dato).
PS-04  los hiperparametros de Huber no gobiernan el resultado.
PS-05  N_min se deriva por familia y no por una regla unica k+1.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import HuberRegressor

from app_icociv.estadistica.modelos_interpretables import (
    MODELOS_INTERPRETABLES,
    OBSERVACIONES_MINIMAS_MODELO,
    ajustar_modelo_interpretable,
    observaciones_minimas_catalogo,
)
from app_icociv.proyeccion.servicio_proyeccion import (
    _catalogo_activo,
    ventanas_oos_disponibles,
)

RUTA_ANEXO = ROOT / "anex-ICOCIV-ene2026.xlsb"
_CACHE: dict[str, object] = {}


def _serie(tabla: str, idx: int):
    """Carga una serie real del anexo con corte enero 2026; None si no esta."""
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


# ----------------------------------------------------------------- PS-01 -----
def test_ps01_la_salvaguarda_no_sustituye_el_modelo_entregado():
    """El modelo entregado es el que gano por RMSE OOS, nunca uno impuesto."""
    serie = _serie("T_16_7", 0)  # Arena
    if serie is None:
        print("  OMITIDA test_ps01_...sustituye (falta el anexo)")
        return
    res = _proyectar(serie)
    salv = res.get("salvaguarda_benchmark") or {}
    # La politica publicada es explicita.
    assert "no sustituye" in str(salv.get("politica", "")).lower() or not salv.get("activada"), (
        f"la salvaguarda se declara sustitutiva: {salv.get('politica')!r}"
    )
    # Y en ningun caso el alcance cambia por haberla consultado.
    assert int(salv["h_max_antes"]) == int(salv["h_max_despues"]), (
        "consultar la salvaguarda cambio el horizonte maximo: volvio a sustituir"
    )
    # El modelo final es el principal.
    assert salv.get("modelo_final") == salv.get("modelo_principal"), (
        "el modelo final difiere del principal: la salvaguarda sustituyo"
    )


def test_ps01_arena_entrega_drift_por_merito_y_sin_intentar_salvaguarda():
    """En Arena no hay fallo de horizonte, luego la salvaguarda ni se intenta."""
    serie = _serie("T_16_7", 0)
    if serie is None:
        print("  OMITIDA test_ps01_arena (falta el anexo)")
        return
    res = _proyectar(serie)
    salv = res.get("salvaguarda_benchmark") or {}
    assert salv.get("intentada") is False, (
        "la salvaguarda se intento: el caso Arena dejo de ilustrar lo que la tesis afirma"
    )
    ganador = str(res.get("modelo_codigo") or "").lower()
    assert ganador == "drift", f"el ganador de Arena dejo de ser Drift: {ganador!r}"
    # Y lo es por menor RMSE OOS en h=1, no por sustitucion.
    bt = res.get("backtesting_comparativo") or {}
    pares = [
        (nombre, (datos.get("metricas") or {}).get("rmse"))
        for nombre, datos in bt.items()
        if isinstance(datos, dict) and nombre.endswith("_h1")
    ]
    pares = [(n, r) for n, r in pares if isinstance(r, (int, float))]
    assert pares, "no se pudo leer el ranking de RMSE en h=1"
    mejor = min(pares, key=lambda x: x[1])[0]
    assert mejor.startswith("drift"), f"Drift ya no minimiza el RMSE en h=1: gano {mejor!r}"


# ----------------------------------------------------------------- PS-02 -----
def test_ps02_las_metricas_por_horizonte_de_la_tabla_son_reproducibles():
    """Los valores publicados en la tabla de la tesis se reproducen."""
    serie = _serie("T_16_2", 6)  # Vias urbanas
    if serie is None:
        print("  OMITIDA test_ps02_metricas (falta el anexo)")
        return
    res = _proyectar(serie)
    ahc = res.get("analisis_horizontes_completo") or {}
    estados = {int(e["horizonte"]): e for e in (ahc.get("estado_por_horizonte") or [])}
    # (h, W, MAPE, MASE) tal como se publican en la tesis.
    esperado = {
        1: (55, 0.5855, 1.2089),
        3: (53, 1.3208, 2.8210),
        6: (50, 2.0381, 4.4983),
        12: (44, 3.0530, 7.2643),
        18: (38, 5.2541, 13.9040),
    }
    n = len(serie)
    for h, (w, mape, mase) in esperado.items():
        assert ventanas_oos_disponibles(n, h) == w, (
            f"h={h}: W cambio de {w} a {ventanas_oos_disponibles(n, h)}"
        )
        e = estados.get(h) or {}
        assert int(e.get("iteraciones") or -1) == w, (
            f"h={h}: la formula dice W={w} pero el backtesting hizo {e.get('iteraciones')}"
        )
        assert abs(float(e["mape"]) - mape) < 5e-4, f"h={h}: MAPE {e['mape']} != {mape}"
        assert abs(float(e["mase"]) - mase) < 5e-4, f"h={h}: MASE {e['mase']} != {mase}"


def test_ps02_ninguna_metrica_niega_un_horizonte_con_evidencia():
    """MASE de 13,9 en h=18 advierte, no bloquea."""
    serie = _serie("T_16_2", 6)
    if serie is None:
        print("  OMITIDA test_ps02_ninguna_metrica (falta el anexo)")
        return
    res = _proyectar(serie)
    ahc = res.get("analisis_horizontes_completo") or {}
    estados = {int(e["horizonte"]): e for e in (ahc.get("estado_por_horizonte") or [])}
    e18 = estados.get(18) or {}
    assert float(e18.get("mase") or 0) > 1.0, "el caso perdio su interes: MASE ya no supera 1"
    assert e18.get("permitido") is True, "un MASE alto volvio a negar el horizonte"
    assert e18.get("no_recomendable") is False, "un MASE alto volvio a degradar el horizonte"


# ----------------------------------------------------------------- PS-03 -----
def test_ps03_w_es_cero_exactamente_cuando_el_dato_no_existe():
    """W = 0 <=> h > n - N0. No es un umbral: es la inexistencia del dato."""
    n0 = observaciones_minimas_catalogo(_catalogo_activo())
    for n in (20, 40, 61, 65):
        cota = n - n0
        assert ventanas_oos_disponibles(n, cota) >= 1, (
            f"n={n}: h={cota} deberia tener al menos una ventana"
        )
        assert ventanas_oos_disponibles(n, cota + 1) == 0, (
            f"n={n}: h={cota + 1} deberia no tener ninguna ventana"
        )


def test_ps03_la_escasez_de_evidencia_no_equivale_a_su_inexistencia():
    """W en {1,2} entrega con advertencia; W = 0 no es evaluable."""
    from app_icociv.proyeccion.servicio_proyeccion import (
        TRAMO_OOS_DISPONIBLE,
        TRAMO_OOS_MUY_LIMITADA,
        TRAMO_OOS_SIN_EVIDENCIA,
        tramo_evidencia_oos,
    )

    assert tramo_evidencia_oos(0) == TRAMO_OOS_SIN_EVIDENCIA
    assert tramo_evidencia_oos(1) == TRAMO_OOS_MUY_LIMITADA
    assert tramo_evidencia_oos(2) == TRAMO_OOS_MUY_LIMITADA
    assert tramo_evidencia_oos(3) == TRAMO_OOS_DISPONIBLE
    assert tramo_evidencia_oos(50) == TRAMO_OOS_DISPONIBLE
    # Y el tramo "disponible" no se llama "validado" en ninguna variante.
    for w in (3, 10, 50):
        texto = tramo_evidencia_oos(w).lower()
        assert "valid" not in texto and "certific" not in texto, (
            f"W={w} se publica como validado/certificado: {texto!r}"
        )


# ----------------------------------------------------------------- PS-04 -----
def test_ps04_la_cota_de_iteraciones_no_es_la_restriccion_activa():
    """En la ruta real Huber converge holgadamente y la cota no mueve el ajuste.

    La cota adoptada (2000) es un margen: lo que se fija aqui es que sobre la
    serie de referencia el optimizador converge muy por debajo de ella y que el
    coeficiente no depende de la cota. NO se fija un numero de iteraciones
    valido para cualquier serie: una serie sintetica de 40 puntos puede exigir
    entre 70 y 85, y por eso el margen existe.
    """
    serie = _serie("T_16_2", 6)
    if serie is None:
        print("  OMITIDA test_ps04_la_cota (falta el anexo)")
        return
    y = np.asarray(serie["Indice"], dtype=float)
    t = np.arange(1.0, len(y) + 1.0)
    coeficientes = []
    for cota in (100, 500, 2000, 5000):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            m = HuberRegressor(epsilon=1.35, alpha=0.0001, max_iter=cota)
            m.fit(t.reshape(-1, 1), y)  # una ConvergenceWarning fallaria aqui
        coeficientes.append(float(m.coef_[0]))
        assert int(m.n_iter_) < 100, (
            f"cota={cota}: Huber dejo de converger holgadamente ({m.n_iter_} iteraciones)"
        )
    assert max(coeficientes) - min(coeficientes) < 1e-9, (
        f"la cota de iteraciones cambio el ajuste: {coeficientes}"
    )


def test_ps04_alpha_no_gobierna_el_ajuste_de_huber():
    """La regularizacion adoptada no decide la pendiente en esta escala."""
    y = np.array([100.0 + 0.7 * i for i in range(40)])
    t = np.arange(1.0, len(y) + 1.0)
    base = None
    for a in (0.0, 1e-5, 1e-4, 1e-3):
        m = HuberRegressor(epsilon=1.35, alpha=a, max_iter=2000).fit(t.reshape(-1, 1), y)
        if base is None:
            base = float(m.coef_[0])
        rel = abs(float(m.coef_[0]) - base) / abs(base)
        assert rel < 1e-3, f"alpha={a} movio la pendiente un {rel:.2e} relativo"


def test_ps04_huber_estima_la_escala_lo_que_sustenta_su_nmin():
    """El Nmin de Huber cuenta 3 parametros porque la escala tambien se ajusta."""
    y = np.array([100.0 + 0.7 * i for i in range(20)])
    t = np.arange(1.0, len(y) + 1.0)
    m = HuberRegressor(epsilon=1.35, alpha=0.0001, max_iter=2000).fit(t.reshape(-1, 1), y)
    assert hasattr(m, "scale_"), "el estimador dejo de exponer la escala ajustada"
    assert OBSERVACIONES_MINIMAS_MODELO["huber"] == 4, (
        "el Nmin de Huber cambio sin rehacer su derivacion (beta0, beta1, sigma -> n >= 4)"
    )


# ----------------------------------------------------------------- PS-05 -----
def test_ps05_nmin_no_sigue_una_regla_unica_para_todas_las_familias():
    """Las formas cerradas NO obedecen n >= k+1; contarlas asi seria falso."""
    # naive no estima nada: su minimo es 1, no 2.
    assert OBSERVACIONES_MINIMAS_MODELO["naive"] == 1
    # drift es forma cerrada sobre dos puntos: 2, no 3.
    assert OBSERVACIONES_MINIMAS_MODELO["drift"] == 2
    # los modelos sobre variaciones exigen variaciones finitas, no k+1.
    assert OBSERVACIONES_MINIMAS_MODELO["variacion_lineal"] == 4
    assert OBSERVACIONES_MINIMAS_MODELO["log_variacion"] == 4
    # y los ajustados por minimizacion si cuentan todo parametro estimado.
    assert OBSERVACIONES_MINIMAS_MODELO["lineal"] == 3          # k=2
    assert OBSERVACIONES_MINIMAS_MODELO["huber"] == 4           # k=3 con la escala
    assert OBSERVACIONES_MINIMAS_MODELO["holt_lineal"] == 5     # k=4
    assert OBSERVACIONES_MINIMAS_MODELO["holt_amortiguado"] == 6  # k=5


def test_ps05_holt_estima_sus_parametros_y_no_los_lleva_fijos():
    """Si Holt volviera a coeficientes fijos, su k y su Nmin dejarian de valer."""
    rng = np.random.default_rng(11)
    for escala in (0.5, 3.0):
        y = np.array([100.0 + 0.8 * i + float(rng.normal(0, escala)) for i in range(30)])
        t = np.arange(1.0, len(y) + 1.0)
        m = ajustar_modelo_interpretable("holt_amortiguado", t, y)
        p = m["parametros"]
        assert m["k"] == 5, f"k de Holt amortiguado cambio a {m['k']}"
        for nombre in ("alpha", "beta", "phi"):
            assert nombre in p, f"Holt dejo de publicar {nombre}"
        # Los tres valores retirados el 09-08-2026 no deben reaparecer juntos.
        fijos_retirados = (
            abs(p["alpha"] - 0.65) < 1e-9
            and abs(p["beta"] - 0.20) < 1e-9
            and abs(p["phi"] - 0.88) < 1e-9
        )
        assert not fijos_retirados, "reaparecieron los coeficientes fijos sin fuente"
        # El criterio publicado debe seguir declarando que los parametros se
        # ESTIMAN de los datos, y citar la fuente de las cotas.
        criterio = str(p.get("criterio_estimacion", "")).lower()
        assert "estima" in criterio, "Holt dejo de declarar que estima sus parametros"
        assert "sse" in criterio, "Holt dejo de declarar el criterio de estimacion (SSE)"
        # Y phi debe quedar dentro de las cotas de FPP3, no en un valor fijo.
        assert 0.80 - 1e-9 <= p["phi"] <= 0.98 + 1e-9, f"phi fuera de las cotas: {p['phi']}"


def test_ps05_el_primer_origen_es_el_maximo_de_los_minimos():
    """N0 sale del modelo mas exigente del catalogo activo (hoy Holt amortiguado)."""
    catalogo = _catalogo_activo()
    n0 = observaciones_minimas_catalogo(catalogo)
    minimos = [OBSERVACIONES_MINIMAS_MODELO[m] for m in catalogo if m in OBSERVACIONES_MINIMAS_MODELO]
    assert n0 == max(minimos), f"N0={n0} dejo de ser el maximo de los minimos {sorted(minimos)}"
    assert n0 == 6, f"N0 cambio a {n0}: es provisional, pero su cambio debe ser deliberado"


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
