"""La cobertura medida se publica aunque el paso no alcance el criterio de 16.

Hasta ahora, un paso con menos de ``MIN_ERRORES_COBERTURA_EMPIRICA`` errores
publicaba ``cobertura_observada = None`` **aunque su cobertura se hubiera
evaluado de verdad**. Un h=12 con 15 errores produce 13 contrastes por origen
movil, de modo que 10/13 es una medicion real; el corte la borraba del campo.

Lo que estas pruebas fijan es la separacion de tres cosas que se venian
mezclando en un solo campo:

  * **cobertura calculada**  -> existe si hay evaluaciones y el valor es finito;
  * **cobertura publicada**  -> se publica SIEMPRE que este calculada;
  * **cobertura apta para la regla productiva** -> puede seguir exigiendo n>=16,
    porque ese criterio NO se retira en esta sesion.

El estado del horizonte, la clasificacion y el tipo de banda **no cambian**.
Los tres cortes siguen vigentes.

Ejecucion:
    python tests/test_cobertura_publicada_n_menor_16.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    COBERTURA_IC95_ACEPTABLE,
    COBERTURA_IC95_ADVERTENCIA,
    MIN_ERRORES_COBERTURA_EMPIRICA,
    TIPO_BANDA_CALCULADA,
    TIPO_RANGO_REFERENCIA,
    clasificar_intervalo_por_cobertura,
)

INFINITO = float("inf")
NO_NUMERO = float("nan")


def cobertura(aciertos: int | None, total: int, *, n_errores: int | None = None,
              h: int = 12, proporcion: float | None = None):
    """Evaluacion sintetica: `total` contrastes con `aciertos` dentro.

    `n_errores` es el numero de errores fuera de muestra del paso, distinto del
    numero de contrastes: el origen movil produce n-2 evaluaciones con n
    errores. Por omision se deriva como total+2.
    """
    if proporcion is None:
        proporcion = (aciertos / total) if (aciertos is not None and total) else None
    n_errores = (total + 2) if n_errores is None else n_errores
    filas = ([{"horizonte": h, "cobertura_95": proporcion, "n_prueba": total}]
             if total else [])
    return {
        "verificable": bool(filas),
        "verificable_paso_exacto": n_errores >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "por_horizonte": filas,
        "cobertura_95_minima": proporcion,
        "cobertura_95_paso_exacto": proporcion,
        "paso_exacto": h,
        "n_errores_paso_exacto": n_errores,
        "metodo_evaluacion": "origen_movil" if filas else "no_evaluable",
    }


# ======================================================================
# 1. La cobertura medida se publica con n < 16
# ======================================================================
def test_n15_con_cobertura_10_de_15_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(10, 15, n_errores=15))
    assert r["verificable_paso_exacto"] is False, "n=15 sigue sin ser apto"
    assert r["cobertura_observada"] is not None, (
        "la cobertura fue medida: no puede publicarse como ausente"
    )
    assert abs(float(r["cobertura_observada"]) - 10 / 15) < 1e-9
    assert r["cobertura_x_y"] == "10/15"
    assert r["aciertos"] == 10 and r["total_evaluado"] == 15


def test_n15_con_cobertura_cero_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(0, 15, n_errores=15))
    assert r["cobertura_observada"] is not None
    assert float(r["cobertura_observada"]) == 0.0
    assert r["cobertura_x_y"] == "0/15"
    assert r["diferencia_pp_frente_nominal"] == -95.0


def test_n15_con_cobertura_uno_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(15, 15, n_errores=15))
    assert float(r["cobertura_observada"]) == 1.0
    assert r["cobertura_x_y"] == "15/15"
    assert r["diferencia_pp_frente_nominal"] == 5.0


def test_n13_del_encargo_se_publica():
    """El ejemplo literal: 10 aciertos de 13 evaluaciones."""
    r = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=15))
    assert r["cobertura_x_y"] == "10/13"
    assert abs(float(r["cobertura_observada"]) - 0.769230769) < 1e-6
    assert r["diferencia_pp_frente_nominal"] == -18.1
    assert r["total_evaluado"] == 13


def test_n16_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(14, 16, n_errores=18))
    assert r["verificable_paso_exacto"] is True
    assert float(r["cobertura_observada"]) == 14 / 16
    assert r["cobertura_x_y"] == "14/16"


# ======================================================================
# 2. No se inventa cobertura donde no la hay
# ======================================================================
def test_n0_no_inventa_cobertura():
    r = clasificar_intervalo_por_cobertura(cobertura(None, 0, n_errores=0))
    assert r["cobertura_observada"] is None
    assert r["cobertura_x_y"] == ""
    assert r["aciertos"] is None and r["total_evaluado"] is None
    assert r["diferencia_pp_frente_nominal"] is None


def test_none_no_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(None, 13, proporcion=None))
    assert r["cobertura_observada"] is None
    assert r["diferencia_pp_frente_nominal"] is None


def test_nan_no_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(None, 13, proporcion=NO_NUMERO))
    assert r["cobertura_observada"] is None


def test_infinito_no_se_publica():
    r = clasificar_intervalo_por_cobertura(cobertura(None, 13, proporcion=INFINITO))
    assert r["cobertura_observada"] is None


# ======================================================================
# 3. Nada de esto cambia la decision
# ======================================================================
def test_n_menor_16_ya_no_degrada_el_estado():
    """CIERRE 08-08-2026: el corte 16 deja de decidir.

    Publicar 15/15 ya no es solo publicar: el paso conserva su estado. El
    minimo de 16 errores no tiene fuente identificada, y una muestra corta es
    una limitacion de PRECISION de la medida, no una imposibilidad de medirla.
    Lo que si sigue bloqueando es que la cobertura no sea calculable.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(15, 15, n_errores=15))
    assert r["degrada_a_escenario"] is False
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida"


def test_n_menor_16_conserva_la_banda_calculada():
    r = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=15))
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida"
    assert r["clasificacion"] == TIPO_BANDA_CALCULADA
    assert r["tipo_banda"] == TIPO_BANDA_CALCULADA


def test_con_n_menor_16_la_medida_ya_es_la_magnitud_publicada():
    """Antes `cobertura_minima` quedaba vacia porque no se usaba para decidir.

    Ahora no se decide con ella -no se decide con ninguna- y la salida publica
    el mismo numero en las dos claves: no hay una cifra oculta y otra visible.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=15))
    assert r["cobertura_observada"] is not None
    assert r["cobertura_minima"] == r["cobertura_observada"]


def test_la_aptitud_para_la_regla_se_declara_aparte():
    apto = clasificar_intervalo_por_cobertura(cobertura(14, 16, n_errores=18))
    no_apto = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=15))
    assert apto["cobertura_apta_para_regla"] is True
    assert no_apto["cobertura_apta_para_regla"] is False
    # Ambos publican su cobertura.
    assert apto["cobertura_observada"] is not None
    assert no_apto["cobertura_observada"] is not None


def test_la_limitacion_explica_el_criterio_sin_llamarlo_garantia():
    r = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=15))
    texto = str(r.get("limitacion_muestra") or "")
    assert "13" in texto, texto
    assert "criterio operativo" in texto.lower(), texto
    for prohibido in ("garant", "universal", "valida cient", "mínimo matemático",
                      "minimo matematico"):
        assert prohibido not in texto.lower(), (prohibido, texto)


def test_sin_limitacion_cuando_la_muestra_es_apta():
    r = clasificar_intervalo_por_cobertura(cobertura(14, 16, n_errores=18))
    assert not str(r.get("limitacion_muestra") or "").strip()


# ======================================================================
# 4. Los cortes siguen vigentes
# ======================================================================
def test_los_tres_cortes_siguen_activos():
    assert MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert COBERTURA_IC95_ACEPTABLE == 0.90
    assert COBERTURA_IC95_ADVERTENCIA == 0.80


def test_el_corte_sigue_gobernando_la_aptitud():
    for n, apto in ((15, False), (16, True), (17, True)):
        r = clasificar_intervalo_por_cobertura(cobertura(10, 13, n_errores=n))
        assert r["verificable_paso_exacto"] is apto, (n, r["verificable_paso_exacto"])


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
            print(f"  FALLA {prueba.__name__}: {str(exc)[:150]}")
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print(f"  ERROR {prueba.__name__}: {type(exc).__name__}: {str(exc)[:130]}")
    total = len(_principales())
    print(f"\n{total - fallos}/{total} pruebas de publicacion con n < 16")
    raise SystemExit(1 if fallos else 0)
