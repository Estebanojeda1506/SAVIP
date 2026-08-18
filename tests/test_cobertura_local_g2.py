"""G-2: el estado del horizonte solicitado lo decide su propia evidencia.

Integrada el 06-08-2026. Antes, la magnitud comparada contra los cortes era el
**minimo sobre todos los pasos 1..h**, de modo que un paso intermedio con
cobertura peor degradaba el horizonte que el usuario habia pedido. La cobertura
del paso entregado se calculaba, se publicaba y no intervenia en su propio
estado.

Respaldo: Christoffersen (1998) sostiene evaluar cada horizonte por separado;
Diebold y Mariano (1995) y Clark y McCracken (2013) muestran que los errores de
horizontes distintos estan correlacionados, de modo que el minimo entre ellos no
es un estadistico con distribucion conocida.

G-2 **no retira ningun corte**: cambia sobre que magnitud se aplican.

Ejecucion:
    python tests/test_cobertura_local_g2.py
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


def cobertura(
    minima: float | None,
    paso: float | None,
    *,
    n_paso: int = 21,
    h: int = 6,
    horizonte_minimo: int = 4,
    n_minimo: int = 21,
    verificable: bool = True,
) -> dict:
    """Cobertura sintetica con el minimo en un horizonte distinto del pedido."""
    filas = []
    if minima is not None:
        filas.append({"horizonte": horizonte_minimo, "cobertura_95": minima,
                      "n_prueba": n_minimo})
    if horizonte_minimo != h and paso is not None:
        filas.append({"horizonte": h, "cobertura_95": paso, "n_prueba": n_paso})
    return {
        "verificable": True,
        "verificable_paso_exacto": verificable and n_paso >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "por_horizonte": filas,
        "cobertura_95_minima": minima,
        "cobertura_95_paso_exacto": paso,
        "paso_exacto": h,
        "n_errores_paso_exacto": n_paso,
        "metodo_evaluacion": "origen_movil",
    }


# ======================================================================
# 1. La cobertura local gobierna
# ======================================================================
def test_la_cobertura_del_paso_solicitado_decide_el_estado():
    r = clasificar_intervalo_por_cobertura(cobertura(0.762, 0.842))
    assert r["clasificacion_interna"] == "admisible_con_advertencia", r
    assert r["degrada_a_escenario"] is False
    assert abs(float(r["cobertura_observada"]) - 0.842) < 1e-9, (
        "la cifra publicada debe ser la del paso, no la del minimo"
    )


def test_otro_paso_con_cobertura_baja_no_degrada_el_solicitado():
    """Un h=4 en 0,50 no puede tumbar un h=6 que cubre 0,95."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.50, 0.95))
    assert r["degrada_a_escenario"] is False, r
    assert r["clasificacion"] == TIPO_BANDA_CALCULADA


def test_la_cobertura_local_baja_se_advierte_con_su_valor():
    """G-2 sigue mirando el paso solicitado; lo que cambia es la consecuencia.

    CIERRE 08-08-2026: la cobertura ya no degrada. Lo que G-2 gano -que el
    horizonte se juzgue por SU propia evidencia y no por el minimo de la
    trayectoria- sigue en pie: la advertencia habla del paso solicitado.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(0.99, 0.60))
    assert r["degrada_a_escenario"] is False, r
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal"
    assert r["clasificacion"] == TIPO_RANGO_REFERENCIA
    assert r["cobertura_observada"] == 0.60


def test_el_criterio_declara_que_magnitud_uso():
    r = clasificar_intervalo_por_cobertura(cobertura(0.70, 0.95))
    assert "paso solicitado" in r["umbral_aplicado"], r["umbral_aplicado"]
    assert "h=6" in r["umbral_aplicado"], r["umbral_aplicado"]


# ======================================================================
# 2. La advertencia global
# ======================================================================
def test_la_advertencia_global_se_publica_con_horizonte_y_conteo():
    r = clasificar_intervalo_por_cobertura(cobertura(0.762, 0.842, n_minimo=21))
    aviso = r["consistencia_entre_horizontes"]
    assert aviso["aplica"] is True, aviso
    assert aviso["horizonte_minimo_global"] == 4
    assert aviso["n_errores_del_horizonte_minimo"] == 21
    assert abs(float(aviso["cobertura_minima_global"]) - 0.762) < 1e-9
    assert str(aviso["mensaje_descriptivo"]).strip()
    assert str(aviso["consecuencia_operativa"]).strip()


def test_la_advertencia_dice_que_no_invalida_el_horizonte_solicitado():
    aviso = clasificar_intervalo_por_cobertura(
        cobertura(0.762, 0.842)
    )["consistencia_entre_horizontes"]
    mensaje = str(aviso["mensaje_descriptivo"]).lower()
    assert "no invalida" in mensaje, mensaje
    assert "cautela" in mensaje, mensaje
    assert "h=4" in mensaje and "h=6" in mensaje, mensaje


def test_no_se_advierte_cuando_el_minimo_cae_en_el_paso_solicitado():
    """C-18-h3: el minimo ES su propio paso. No hay inconsistencia que avisar."""
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.727, 0.727, n_paso=24, h=3, horizonte_minimo=3)
    )
    assert r["consistencia_entre_horizontes"]["aplica"] is False, r
    assert r["degrada_a_escenario"] is False, "ningun corte de cobertura degrada ya"
    assert r["cobertura_observada"] == 0.727, "pero la medicion se publica"


def test_no_se_advierte_cuando_todos_los_horizontes_cubren_bien():
    r = clasificar_intervalo_por_cobertura(cobertura(0.94, 0.96))
    assert r["consistencia_entre_horizontes"]["aplica"] is False, r


def test_todos_los_horizontes_iguales_no_producen_advertencia():
    r = clasificar_intervalo_por_cobertura(cobertura(0.85, 0.85, horizonte_minimo=6))
    assert r["consistencia_entre_horizontes"]["aplica"] is False, r


def test_cobertura_global_no_calculable_no_rompe_ni_advierte():
    r = clasificar_intervalo_por_cobertura(
        {
            "verificable": True, "verificable_paso_exacto": True, "por_horizonte": [],
            "cobertura_95_minima": float("nan"), "cobertura_95_paso_exacto": 0.95,
            "paso_exacto": 6, "n_errores_paso_exacto": 20,
        }
    )
    assert r["cobertura_minima_global"] is None
    assert r["consistencia_entre_horizontes"]["aplica"] is False
    assert r["clasificacion_interna"] == "nominal"


def test_el_minimo_global_se_publica_siempre_aunque_no_advierta():
    r = clasificar_intervalo_por_cobertura(cobertura(0.94, 0.96))
    assert abs(float(r["cobertura_minima_global"]) - 0.94) < 1e-9
    assert r["horizonte_de_cobertura_minima"] == 4


# ======================================================================
# 3. Los tres casos exactos
# ======================================================================
CASOS = {
    # caso: (minimo global, h del minimo, cobertura del paso, n, clave esperada)
    "C-03-h6": (0.762, 4, 0.842, 21, "admisible_con_advertencia"),
    "C-05-h6": (0.773, 3, 0.842, 21, "admisible_con_advertencia"),
    "C-11-h6": (0.762, 4, 1.000, 21, "nominal"),
}


def test_los_tres_casos_dejan_de_degradarse():
    for caso, (minimo, h_min, paso, n, clave) in CASOS.items():
        r = clasificar_intervalo_por_cobertura(
            cobertura(minimo, paso, n_paso=n, h=6, horizonte_minimo=h_min)
        )
        assert r["clasificacion_interna"] == clave, (caso, r)
        assert r["degrada_a_escenario"] is False, (caso, r)
        assert r["clasificacion"] == TIPO_BANDA_CALCULADA, (caso, r)
        assert r["consistencia_entre_horizontes"]["aplica"] is True, (caso, r)


def test_c11_h6_conserva_su_cobertura_de_1000_sin_degradarse():
    """El caso que obliga a decidir: una banda que no fallo nunca."""
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.762, 1.000, n_paso=21, h=6, horizonte_minimo=4)
    )
    assert abs(float(r["cobertura_observada"]) - 1.0) < 1e-9
    assert r["degrada_a_escenario"] is False
    assert r["clasificacion_interna"] == "nominal"
    aviso = r["consistencia_entre_horizontes"]
    assert aviso["aplica"] is True, "la cobertura menor de h=4 debe seguir visible"
    assert aviso["horizonte_minimo_global"] == 4


# ======================================================================
# 4. Lo que G-2 no toca
# ======================================================================
def test_los_tres_cortes_siguen_activos():
    """D-1b-B sigue fuera."""
    assert MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert COBERTURA_IC95_ACEPTABLE == 0.90
    assert COBERTURA_IC95_ADVERTENCIA == 0.80


def test_el_corte_de_16_ya_no_degrada_con_cobertura_local_perfecta():
    """C-11-h12: cobertura 1,000 con 15 contrastes. Se mide y se publica.

    CIERRE 08-08-2026: el minimo de 16 errores pasa a ser una referencia
    descriptiva de tamano de muestra.
    """
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.762, 1.000, n_paso=15, h=12, horizonte_minimo=4)
    )
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida", r
    assert r["degrada_a_escenario"] is False
    assert r["clasificacion"] == TIPO_BANDA_CALCULADA
    assert r["cobertura_observada"] == 1.000


def test_los_cortes_siguen_siendo_inclusivos_sobre_la_cobertura_local():
    justo = clasificar_intervalo_por_cobertura(cobertura(0.50, COBERTURA_IC95_ACEPTABLE))
    assert justo["clasificacion_interna"] == "nominal", justo
    debajo = clasificar_intervalo_por_cobertura(
        cobertura(0.50, COBERTURA_IC95_ACEPTABLE - 1e-9)
    )
    assert debajo["clasificacion_interna"] == "admisible_con_advertencia", debajo
    limite = clasificar_intervalo_por_cobertura(cobertura(0.50, COBERTURA_IC95_ADVERTENCIA))
    assert limite["clasificacion_interna"] == "admisible_con_advertencia", limite
    bajo = clasificar_intervalo_por_cobertura(
        cobertura(0.50, COBERTURA_IC95_ADVERTENCIA - 1e-9)
    )
    assert bajo["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", bajo
    assert bajo["degrada_a_escenario"] is False, "ningun corte degrada ya"


def test_no_hay_regla_basada_en_n_mayor_o_igual_a_19():
    """D-1b-B introduciria una distincion por conteo. No debe existir."""
    a = clasificar_intervalo_por_cobertura(cobertura(0.50, 0.85, n_paso=18))
    b = clasificar_intervalo_por_cobertura(cobertura(0.50, 0.85, n_paso=19))
    assert a["clasificacion_interna"] == b["clasificacion_interna"], (a, b)
    assert a["clasificacion"] == b["clasificacion"]


def test_vc_permanece_estable_bajo_g2():
    """El vocabulario no cambia por la regla de decision."""
    for minimo, paso, esperado in (
        (0.762, 1.000, TIPO_BANDA_CALCULADA),
        (0.762, 0.842, TIPO_BANDA_CALCULADA),
        (0.99, 0.60, TIPO_RANGO_REFERENCIA),
    ):
        r = clasificar_intervalo_por_cobertura(cobertura(minimo, paso))
        assert r["clasificacion"] == esperado, (minimo, paso, r)
        assert r["tipo_banda"] == r["clasificacion"]
        assert r["clasificacion"] != r["clasificacion_interna"]


def test_el_llamador_sin_paso_exacto_conserva_la_regla_anterior():
    """Usos sinteticos e historicos: sin paso informado manda el global."""
    r = clasificar_intervalo_por_cobertura(
        {"verificable": True, "por_horizonte": [{"horizonte": 1, "cobertura_95": 0.70,
                                                 "n_prueba": 20}],
         "cobertura_95_minima": 0.70},
        errores_por_horizonte={1: [0.0] * 20},
    )
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", r


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
            print(f"  FALLA {prueba.__name__}: {str(exc)[:200]}")
    print(f"\n{len(_principales()) - fallos}/{len(_principales())} pruebas de cobertura local G-2")
    raise SystemExit(1 if fallos else 0)
