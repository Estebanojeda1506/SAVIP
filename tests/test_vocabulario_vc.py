"""V-C: el identificador de la banda no afirma cobertura.

Integrado el 06-08-2026. El vocabulario anterior -`nominal`,
`admisible_con_advertencia`, `cobertura_insuficiente`, `no_verificable`-
viajaba al CSV y a las tablas como identificador visible, y tres de los cuatro
se leen como un juicio sobre la cobertura observada. V-C los sustituye por tres
identificadores que describen QUE ES la banda entregada.

Lo que estas pruebas fijan:

  * las tres etiquetas existen y son las unicas publicadas;
  * ningun termino prohibido llega al identificador visible;
  * el nivel nominal se sigue publicando aparte, en su propio campo;
  * la clave de decision sobrevive en `clasificacion_interna`;
  * V-C **no** mueve ningun estado ni ninguna cifra.

Ejecucion:
    python tests/test_vocabulario_vc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    BANDA_LIMITES_INVERTIDOS,
    BANDA_LIMITES_NO_FINITOS,
    BANDA_NO_CALCULABLE,
    BANDA_SEMIANCHO_CERO,
    BANDA_VALIDA,
    CLASIFICACION_VC,
    COBERTURA_IC95_ACEPTABLE,
    COBERTURA_IC95_ADVERTENCIA,
    ETIQUETA_VISIBLE_VC,
    MIN_ERRORES_COBERTURA_EMPIRICA,
    TIPO_BANDA_CALCULADA,
    TIPO_BANDA_NO_CALCULABLE,
    TIPO_RANGO_REFERENCIA,
    clasificar_intervalo_por_cobertura,
)

#: Identificadores que no deben aparecer NUNCA como valor publicado. Se
#: comprueban sobre el identificador y el tipo de banda, no sobre la prosa: una
#: frase como «no como cobertura asegurada» es un uso correcto, y marcarla
#: seria el falso positivo que ya se corrigio el 05-08.
PROHIBIDOS = {
    "nominal",
    "cobertura_insuficiente",
    "admisible_con_advertencia",
    "no_verificable",
    "cobertura_por_debajo_del_nominal",
    "medida_con_muestra_reducida",
    "intervalo_validado",
    "cobertura_garantizada",
    "cobertura_asegurada",
    "cobertura_suficiente",
}


def cobertura(
    minima: float | None,
    *,
    paso: float | None = None,
    n_paso: int = 21,
    h: int = 6,
    verificable: bool = True,
    horizonte_minimo: int = 4,
) -> dict:
    """Cobertura sintetica con paso solicitado y minimo global separados."""
    paso = minima if paso is None else paso
    filas = [{"horizonte": horizonte_minimo, "cobertura_95": minima, "n_prueba": 21}]
    if horizonte_minimo != h:
        filas.append({"horizonte": h, "cobertura_95": paso, "n_prueba": n_paso})
    return {
        "verificable": verificable,
        "verificable_paso_exacto": verificable and n_paso >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "por_horizonte": filas,
        "cobertura_95_minima": minima,
        "cobertura_95_paso_exacto": paso,
        "paso_exacto": h,
        "n_errores_paso_exacto": n_paso,
        "metodo_evaluacion": "origen_movil",
    }


# ======================================================================
# 1. Las tres etiquetas
# ======================================================================
def test_existen_exactamente_las_tres_etiquetas():
    assert set(ETIQUETA_VISIBLE_VC) == {
        TIPO_BANDA_CALCULADA,
        TIPO_RANGO_REFERENCIA,
        TIPO_BANDA_NO_CALCULABLE,
    }
    assert TIPO_BANDA_CALCULADA == "banda_calculada"
    assert TIPO_RANGO_REFERENCIA == "rango_de_referencia"
    assert TIPO_BANDA_NO_CALCULABLE == "banda_no_calculable"


def test_todo_identificador_publicado_pertenece_al_vocabulario():
    assert set(CLASIFICACION_VC.values()) <= set(ETIQUETA_VISIBLE_VC)


def test_ningun_identificador_publicado_es_un_termino_prohibido():
    for identificador in set(CLASIFICACION_VC.values()):
        assert identificador not in PROHIBIDOS, identificador


def test_ninguna_etiqueta_afirma_cobertura():
    """«nivel nominal del 95 %» es admisible; «cobertura garantizada» no."""
    for etiqueta in ETIQUETA_VISIBLE_VC.values():
        plano = etiqueta.lower()
        for palabra in ("garantiz", "asegurad", "suficiente", "validad", "verificad"):
            assert palabra not in plano, (etiqueta, palabra)
        # "nominal" solo se admite calificando el NIVEL, nunca el resultado.
        for coincidencia in re.finditer(r"nominal", plano):
            contexto = plano[max(0, coincidencia.start() - 12): coincidencia.end() + 4]
            assert "nivel nominal" in contexto, etiqueta


# ======================================================================
# 2. De que depende cada etiqueta
# ======================================================================
def test_banda_calculada_cuando_la_banda_existe_y_se_evaluo():
    for valor in (0.95, COBERTURA_IC95_ACEPTABLE, 0.85, COBERTURA_IC95_ADVERTENCIA):
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert r["clasificacion"] == TIPO_BANDA_CALCULADA, (valor, r)
        assert r["tipo_banda"] == TIPO_BANDA_CALCULADA
        assert r["etiqueta_visible"] == ETIQUETA_VISIBLE_VC[TIPO_BANDA_CALCULADA]


def test_rango_de_referencia_con_evidencia_limitada_o_respaldo_no_confirmado():
    limitada = clasificar_intervalo_por_cobertura(
        cobertura(None, n_paso=9, verificable=False),
        errores_por_horizonte={1: np.arange(9, dtype=float)},
    )
    assert limitada["clasificacion"] == TIPO_RANGO_REFERENCIA, limitada
    baja = clasificar_intervalo_por_cobertura(cobertura(0.44))
    assert baja["clasificacion"] == TIPO_RANGO_REFERENCIA, baja
    for r in (limitada, baja):
        assert r["etiqueta_visible"] == ETIQUETA_VISIBLE_VC[TIPO_RANGO_REFERENCIA]


def test_banda_no_calculable_solo_por_imposibilidad_matematica():
    """Sin errores, limites invertidos o no finitos: no hay banda que tipificar.

    P0-C / C2, 15-08-2026. La linea `assert r["degrada_a_escenario"] is True`
    contradecia la decision P0-G del 14-08-2026, que la fijo en `False`:
    degradar a escenario es una decision sobre el PUNTO, y la ausencia de banda
    pertenece al eje INTERVALO (REQ 14). La reapertura de P0-G ya reescribio dos
    tests hermanos con este mismo assert -`test_la_cobertura_no_calculable_
    sigue_degradando` y `test_cobertura_no_calculable_no_afirma_ninguna_
    cobertura`, ambos hoy verdes en `test_calendario_y_clasificacion_intervalo`
    con `is False`- y este quedo fuera. Trazado en
    `P0G_REAPERTURA_DECISION_FINAL.md`, tabla «Los siete tests reescritos».

    El contrato nuevo no se limita a invertir el booleano: comprueba las DOS
    direcciones de la separacion, que es lo que P0-G fijo y lo que el assert
    antiguo no miraba.
    """
    for estado in (BANDA_NO_CALCULABLE, BANDA_LIMITES_INVERTIDOS, BANDA_LIMITES_NO_FINITOS):
        r = clasificar_intervalo_por_cobertura(cobertura(0.99), estado_banda_paso=estado)
        assert r["clasificacion"] == TIPO_BANDA_NO_CALCULABLE, (estado, r)
        # 1. La ausencia de banda NO degrada el punto.
        assert r["degrada_a_escenario"] is False, (
            f"P0-G reabierto: '{estado}' vuelve a degradar el punto por una "
            f"deficiencia del intervalo (REQ 14)"
        )
        # 2. Y no se afirma ninguna cobertura que no se pudo medir.
        assert r["cobertura_observada"] is None, "sin banda no se publica cobertura"
        # 3. La ausencia se DECLARA: no se degrada, pero tampoco se silencia.
        assert str(r.get("umbral_aplicado") or "").strip(), (estado, r)
        # 4. Ninguna etiqueta afirma cobertura sobre una banda inexistente.
        for clave in ("etiqueta", "etiqueta_visible", "clasificacion", "tipo_banda"):
            texto = str(r.get(clave) or "").lower()
            assert "cobertura" not in texto or "no" in texto, (clave, r.get(clave))


def test_la_banda_ausente_no_bloquea_el_punto_pero_el_punto_no_finito_si():
    """Las dos direcciones de la separacion P0-G, sobre la decision real.

    Complementa al test anterior. Aquel comprueba la CLASIFICACION del intervalo;
    este comprueba la CONSECUENCIA sobre el horizonte, que es donde P0-G fijo la
    regla: un punto finito con banda inexistente sigue siendo publicable, y un
    punto no finito sigue bloqueando.
    """
    from app_icociv.proyeccion.servicio_proyeccion import (
        PUNTO_NO_FINITO,
        _clasificar_evidencia_horizonte,
    )

    base = dict(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
    )

    # Direccion 1: la banda que no existe no cancela un punto finito.
    for estado in (BANDA_NO_CALCULABLE, BANDA_LIMITES_INVERTIDOS,
                   BANDA_LIMITES_NO_FINITOS, BANDA_SEMIANCHO_CERO, BANDA_VALIDA):
        c = _clasificar_evidencia_horizonte(
            evaluacion_intervalos={"estado_banda": estado, "ancho_relativo_95_maximo": 0.1},
            **base,
        )
        assert c.get("permitido_para_proyeccion_tecnica") or c.get("permitido_como_escenario"), (
            f"P0-G reabierto: '{estado}' bloquea un punto finito (REQ 14)"
        )

    # Direccion 2: la imposibilidad aritmetica real sigue bloqueando.
    c = _clasificar_evidencia_horizonte(
        evaluacion_intervalos={"estado_banda": PUNTO_NO_FINITO, "ancho_relativo_95_maximo": 0.1},
        **base,
    )
    assert not c.get("permitido_para_proyeccion_tecnica")
    assert not c.get("permitido_como_escenario"), (
        "un punto no finito no es un escenario: no hay numero que ofrecer"
    )


def test_una_banda_valida_nunca_es_no_calculable():
    for estado in (BANDA_VALIDA, BANDA_SEMIANCHO_CERO):
        r = clasificar_intervalo_por_cobertura(cobertura(0.99), estado_banda_paso=estado)
        assert r["clasificacion"] != TIPO_BANDA_NO_CALCULABLE, (estado, r)


def test_la_imposibilidad_matematica_manda_sobre_cualquier_umbral():
    """Se comprueba ANTES que la cobertura: una banda inexistente no se puntua."""
    alta = clasificar_intervalo_por_cobertura(
        cobertura(1.0), estado_banda_paso=BANDA_LIMITES_INVERTIDOS
    )
    assert alta["clasificacion"] == TIPO_BANDA_NO_CALCULABLE
    assert "umbral" in alta["umbral_aplicado"].lower()


# ======================================================================
# 3. Campos separados (apartado 7.3)
# ======================================================================
def test_los_campos_viajan_separados():
    r = clasificar_intervalo_por_cobertura(cobertura(0.85))
    for campo in (
        "nivel_nominal", "cobertura_observada", "n_errores_paso_exacto",
        "clasificacion", "clasificacion_interna", "tipo_banda", "etiqueta_visible",
        "limitacion", "consecuencia_operativa", "umbral_aplicado",
    ):
        assert campo in r, campo
    assert r["nivel_nominal"] == 0.95
    assert r["clasificacion"] != r["clasificacion_interna"], (
        "el identificador publicado no puede ser la clave de decision"
    )


def test_el_nivel_nominal_no_es_la_cobertura_observada():
    r = clasificar_intervalo_por_cobertura(cobertura(0.727))
    assert r["nivel_nominal"] == 0.95
    assert abs(float(r["cobertura_observada"]) - 0.727) < 1e-9


def test_la_clave_de_decision_sigue_siendo_auditable():
    esperado = {
        0.95: "nominal",
        0.85: "admisible_con_advertencia",
        0.44: "cobertura_por_debajo_del_nominal",
    }
    for valor, clave in esperado.items():
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert r["clasificacion_interna"] == clave, (valor, r)
        assert str(r["umbral_aplicado"]).strip(), "el criterio aplicado debe declararse"


# ======================================================================
# 4. V-C no mueve nada
# ======================================================================
def test_vc_no_cambia_la_degradacion():
    """CIERRE 08-08-2026: ninguna cobertura medida degrada ya el horizonte.

    V-C separo el nombre de la banda de la afirmacion de cobertura; el cierre
    metodologico separa ademas la MEDICION de la DECISION. La banda de 0,44
    sigue llamandose rango de referencia -eso describe la banda- pero el
    horizonte ya no se degrada por su valor.
    """
    esperado = {0.95: False, 0.85: False, 0.44: False}
    for valor, degrada in esperado.items():
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert r["degrada_a_escenario"] is degrada, (valor, r)


def test_vc_no_cambia_los_cortes():
    """D-1b-B sigue fuera: los tres cortes conservan su valor."""
    assert MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert COBERTURA_IC95_ACEPTABLE == 0.90
    assert COBERTURA_IC95_ADVERTENCIA == 0.80


def test_vc_no_publica_ninguna_cifra_del_intervalo():
    r = clasificar_intervalo_por_cobertura(cobertura(0.85))
    prohibidas = {
        "limite_inferior", "limite_superior", "limite_inferior_95", "limite_superior_95",
        "y_proj", "indice_proyectado", "q95", "sigma_h", "offsets", "semiancho",
    }
    assert not prohibidas & set(r), set(r) & prohibidas


# ======================================================================
# 5. Casos nombrados en el encargo
# ======================================================================
def test_c18_h3_con_cobertura_0727_es_rango_de_referencia():
    """0,727 con 24 contrastes: la banda existe, pero no se presenta como confirmada."""
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.727, n_paso=24, h=3, horizonte_minimo=3)
    )
    assert r["clasificacion"] == TIPO_RANGO_REFERENCIA, r
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal"


def test_c11_h12_con_cobertura_1000_y_15_errores_es_banda_calculada():
    """Cobertura 1,000 con 15 contrastes: se mide, se publica y NO degrada.

    CIERRE 08-08-2026: el corte de 16 deja de gobernar. La banda se llama
    calculada porque lo esta, y la muestra reducida viaja en la advertencia.
    """
    r = clasificar_intervalo_por_cobertura(
        cobertura(0.762, paso=1.0, n_paso=15, h=12, horizonte_minimo=4)
    )
    assert r["clasificacion"] == TIPO_BANDA_CALCULADA, r
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida"
    assert r["degrada_a_escenario"] is False
    assert "muestra reducida" in r["advertencia"]


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
            print(f"  FALLA {prueba.__name__}: {exc}")
    print(f"\n{len(_principales()) - fallos}/{len(_principales())} pruebas de vocabulario V-C")
    raise SystemExit(1 if fallos else 0)
