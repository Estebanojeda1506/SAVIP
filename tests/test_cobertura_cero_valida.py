"""Una cobertura de 0,000 es un resultado, no una ausencia de resultado.

Defectos D-Z1 y D-Z2, encontrados el 06-08-2026 por el caso sintetico
``p = 0,000`` del experimento de D-1b reformulada. Ninguna de las 39 suites los
cubria porque ningun escenario real del anexo alcanza cobertura cero.

Causa comun: ``_numero_finito_o_none`` **devuelve el numero**, de modo que
``not _numero_finito_o_none(0.0)`` es ``True``, igual que para ``None`` o
``NaN``. Python trata ``0.0`` como falsy y el codigo confundia
«la banda no cubrio nada» con «no se pudo medir».

  * **D-Z1**: la clasificacion informaba `no_verificable` con el motivo
    «n < 16 errores» aunque hubiera 24, y publicaba `cobertura_observada=None`.
  * **D-Z2**: `_minimo_entre_horizontes` excluia del calculo el horizonte cuya
    cobertura fuera exactamente 0,0, de modo que el peor paso desaparecia del
    indicador creado para senalarlo.

La distincion que estas pruebas fijan:

    0,0   -> cobertura medida, valida, se publica como 0/n
    None  -> no se midio
    NaN   -> no se pudo calcular
    inf   -> no es un resultado

Ejecucion:
    python tests/test_cobertura_cero_valida.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    COBERTURA_IC95_ACEPTABLE,
    MIN_ERRORES_COBERTURA_EMPIRICA,
    NIVEL_NOMINAL_IC95,
    TIPO_RANGO_REFERENCIA,
    _minimo_entre_horizontes,
    clasificar_intervalo_por_cobertura,
)

INFINITO = float("inf")
NO_NUMERO = float("nan")


def cobertura(
    paso: float | None,
    *,
    n_paso: int = 24,
    h: int = 6,
    minima: float | None = None,
    horizonte_minimo: int = 6,
    n_minimo: int = 24,
    filas: list | None = None,
):
    """Cobertura sintetica. `minima` por omision coincide con el paso."""
    minima = paso if minima is None else minima
    if filas is None:
        filas = [{"horizonte": horizonte_minimo, "cobertura_95": minima,
                  "n_prueba": n_minimo}]
        if horizonte_minimo != h:
            filas.append({"horizonte": h, "cobertura_95": paso, "n_prueba": n_paso})
    return {
        "verificable": True,
        "verificable_paso_exacto": n_paso >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "por_horizonte": filas,
        "cobertura_95_minima": minima,
        "cobertura_95_paso_exacto": paso,
        "paso_exacto": h,
        "n_errores_paso_exacto": n_paso,
        "metodo_evaluacion": "origen_movil",
    }


# ======================================================================
# D-Z1 — cobertura 0,000 es un valor
# ======================================================================
def test_cobertura_cero_es_valida_y_no_es_no_verificable():
    """0 aciertos de 24 es una medicion, no una falta de muestra."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", r
    assert r["clasificacion_interna"] != "no_calculable", (
        "una cobertura medida de 0,000 no puede informarse como no calculable"
    )


def test_cobertura_cero_no_declara_falta_de_errores():
    """El motivo publicado no debe mentir sobre el tamano de la muestra."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    umbral = str(r["umbral_aplicado"]).lower()
    assert "n <" not in umbral, umbral
    assert "cobertura" in umbral, umbral


def test_cobertura_cero_se_publica_como_valor():
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert r["cobertura_observada"] is not None, "0,000 no puede publicarse como None"
    assert float(r["cobertura_observada"]) == 0.0
    assert float(r["cobertura_paso_exacto"]) == 0.0


def test_cobertura_cero_se_advierte_por_su_valor_y_ya_no_degrada():
    """CIERRE 08-08-2026: ningun corte de cobertura degrada el horizonte.

    Lo que D-Z1 gano sigue en pie y es lo importante: 0,000 se clasifica por su
    VALOR y no como falta de muestra. Lo que cambia es la consecuencia: se
    advierte con la cifra en vez de degradar, porque el corte 0,80 no tiene
    fuente.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert r["degrada_a_escenario"] is False
    assert r["clasificacion"] == TIPO_RANGO_REFERENCIA
    assert r["cobertura_observada"] == 0.0
    assert "0%" in r["advertencia"]


def test_none_si_es_ausencia():
    r = clasificar_intervalo_por_cobertura(cobertura(None, n_paso=24))
    assert r["clasificacion_interna"] == "no_calculable", r
    assert r["cobertura_observada"] is None


def test_nan_no_es_cobertura_valida():
    r = clasificar_intervalo_por_cobertura(cobertura(NO_NUMERO, n_paso=24))
    assert r["clasificacion_interna"] == "no_calculable", r
    assert r["cobertura_observada"] is None


def test_infinito_no_es_cobertura_valida():
    r = clasificar_intervalo_por_cobertura(cobertura(INFINITO, n_paso=24))
    assert r["clasificacion_interna"] == "no_calculable", r
    assert r["cobertura_observada"] is None


# ======================================================================
# D-Z2 — el minimo entre horizontes incluye el cero
# ======================================================================
def test_minimo_incluye_cero():
    filas = [
        {"horizonte": 1, "cobertura_95": 0.92, "n_prueba": 26},
        {"horizonte": 3, "cobertura_95": 0.00, "n_prueba": 24},
        {"horizonte": 6, "cobertura_95": 1.00, "n_prueba": 21},
    ]
    minimo, horizonte, n = _minimo_entre_horizontes(
        {"por_horizonte": filas, "cobertura_95_minima": 0.0}
    )
    assert minimo == 0.0, (minimo, horizonte, n)
    assert horizonte == 3, (minimo, horizonte, n)
    assert n == 24, (minimo, horizonte, n)


def test_minimo_respaldo_cero():
    """Sin filas, el minimo declarado de 0,0 debe conservarse."""
    minimo, horizonte, n = _minimo_entre_horizontes(
        {"por_horizonte": [], "cobertura_95_minima": 0.0}
    )
    assert minimo == 0.0, (minimo, horizonte, n)


def test_minimo_excluye_none_nan_e_infinito():
    filas = [
        {"horizonte": 1, "cobertura_95": 0.92, "n_prueba": 26},
        {"horizonte": 2, "cobertura_95": None, "n_prueba": 25},
        {"horizonte": 3, "cobertura_95": NO_NUMERO, "n_prueba": 24},
        {"horizonte": 4, "cobertura_95": INFINITO, "n_prueba": 23},
        {"horizonte": 5, "cobertura_95": 0.85, "n_prueba": 22},
    ]
    minimo, horizonte, n = _minimo_entre_horizontes(
        {"por_horizonte": filas, "cobertura_95_minima": 0.85}
    )
    assert minimo == 0.85, (minimo, horizonte, n)
    assert horizonte == 5, (minimo, horizonte, n)


def test_cero_global_genera_advertencia():
    """El peor horizonte debe aparecer en la advertencia, no desaparecer."""
    filas = [
        {"horizonte": 3, "cobertura_95": 0.00, "n_prueba": 24},
        {"horizonte": 6, "cobertura_95": 1.00, "n_prueba": 21},
    ]
    r = clasificar_intervalo_por_cobertura(
        cobertura(1.0, n_paso=21, h=6, minima=0.0, filas=filas)
    )
    aviso = r["consistencia_entre_horizontes"]
    assert aviso["aplica"] is True, aviso
    assert float(aviso["cobertura_minima_global"]) == 0.0, aviso
    assert aviso["horizonte_minimo_global"] == 3, aviso
    assert aviso["n_errores_del_horizonte_minimo"] == 24, aviso
    assert float(r["cobertura_minima_global"]) == 0.0


def test_g2_se_mantiene_con_cero_remoto():
    """Un h=3 en 0,000 no degrada el h=6 solicitado; solo advierte."""
    filas = [
        {"horizonte": 3, "cobertura_95": 0.00, "n_prueba": 24},
        {"horizonte": 6, "cobertura_95": 1.00, "n_prueba": 21},
    ]
    r = clasificar_intervalo_por_cobertura(
        cobertura(1.0, n_paso=21, h=6, minima=0.0, filas=filas)
    )
    assert r["clasificacion_interna"] == "nominal", r
    assert r["degrada_a_escenario"] is False, "G-2: decide el paso solicitado"
    assert r["consistencia_entre_horizontes"]["aplica"] is True


def test_cero_local_si_degrada_su_propio_horizonte():
    filas = [
        {"horizonte": 3, "cobertura_95": 0.00, "n_prueba": 24},
        {"horizonte": 6, "cobertura_95": 1.00, "n_prueba": 21},
    ]
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.0, n_paso=24, h=3, minima=0.0, filas=filas)
    )
    assert r["degrada_a_escenario"] is False, r
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal"
    assert r["cobertura_observada"] == 0.0


# ======================================================================
# Cobertura descriptiva
# ======================================================================
def test_diferencia_pp_de_cobertura_cero():
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert r["diferencia_pp_frente_nominal"] == -95.0, r
    assert r["aciertos"] == 0
    assert r["total_evaluado"] == 24
    assert r["cobertura_x_y"] == "0/24"


def test_diferencia_pp_valores_de_referencia():
    esperado = {0.727: -22.3, 0.95: 0.0, 1.0: 5.0}
    for proporcion, diferencia in esperado.items():
        r = clasificar_intervalo_por_cobertura(cobertura(proporcion, n_paso=22))
        assert r["diferencia_pp_frente_nominal"] == diferencia, (proporcion, r)


def test_diferencia_pp_es_descriptiva_y_no_decide():
    """Dos casos con la misma diferencia y distinto estado, y viceversa."""
    alta = clasificar_intervalo_por_cobertura(cobertura(1.0, n_paso=21))
    baja = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert alta["diferencia_pp_frente_nominal"] == 5.0
    assert baja["diferencia_pp_frente_nominal"] == -95.0
    # CIERRE 08-08-2026: ya no la decide ningun corte de cobertura, y la
    # diferencia tampoco. Las dos son descriptivas.
    assert alta["degrada_a_escenario"] is False
    assert baja["degrada_a_escenario"] is False
    # Y la diferencia no aparece en el criterio aplicado.
    for r in (alta, baja):
        assert "puntos" not in str(r["umbral_aplicado"]).lower(), r["umbral_aplicado"]
        assert "diferencia" not in str(r["umbral_aplicado"]).lower(), r["umbral_aplicado"]


def test_sin_cobertura_no_hay_diferencia():
    r = clasificar_intervalo_por_cobertura(cobertura(None, n_paso=24))
    assert r["diferencia_pp_frente_nominal"] is None
    assert r["cobertura_x_y"] == ""


def test_nivel_nominal_se_publica_aparte():
    r = clasificar_intervalo_por_cobertura(cobertura(0.0, n_paso=24))
    assert r["nivel_nominal"] == NIVEL_NOMINAL_IC95 == 0.95


# ======================================================================
# Nada de esto cambia los cortes
# ======================================================================
def test_los_cortes_siguen_vigentes():
    assert MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert COBERTURA_IC95_ACEPTABLE == 0.90


def _principales() -> list:
    return [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


if __name__ == "__main__":
    fallos = 0
    for prueba in _principales():
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except AssertionError as exc:
            fallos += 1
            print(f"  FALLA {prueba.__name__}: {str(exc)[:160]}")
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {prueba.__name__}: {type(exc).__name__}: {str(exc)[:140]}")
    total = len(_principales())
    print(f"\n{total - fallos}/{total} pruebas de cobertura cero")
    raise SystemExit(1 if fallos else 0)
