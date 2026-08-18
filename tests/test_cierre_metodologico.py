"""Cierre metodologico: ninguna heuristica sin fuente decide (08-08-2026).

Sustituye a `test_puerta_rrmse_unica.py`, que fijaba la puerta unica de RRMSE
con el corte 1,25. Esa puerta se retiro el mismo dia en que se cerro que 1,25 no
tiene fuente identificada, de modo que la prueba habria quedado defendiendo
justo lo que la revision retiro.

QUE FIJA ESTE ARCHIVO

Un horizonte deja de entregarse **solo cuando no se puede calcular**. Las
imposibilidades que quedan son tres y las tres son tecnicas:

    T-1  la banda no es un intervalo valido (limites no finitos o invertidos)
    T-2  menos de MIN_ITERACIONES_WF_ESCENARIO ventanas de validacion
    T-3  la cobertura no es calculable

La cuarta -MAPE o sMAPE no finitos- se retiro el 09-08-2026 en la auditoria de
fundamentacion (hallazgo E-03). No era una imposibilidad de calculo del
pronostico sino de una razon porcentual: MAPE no esta definido si algun valor
observado es cero, y eso no invalida un pronostico cuyo RMSE, MAE y MASE
existen. Ninguna fuente sustentaba ese veto. Medicion previa a la retirada:
**0 activaciones** sobre 10 series x 24 horizontes.

Todo lo demas se mide, se publica y **se advierte**. Las nueve heuristicas
retiradas y su sitio anterior:

    H-1  rRMSE > 1,25                      puerta de viabilidad
    H-2  salvaguarda `h_bench > h_antes`   sustitucion global por drift/naive
    H-3  V-12: benchmark en h>=13          degradaba a escenario
    H-4  n < 16 errores                    degradaba a escenario
    H-5  cobertura observada < 0,80        degradaba a escenario
    H-6  nueve cortes de amplitud del IC95 bloqueaban o degradaban
    H-7  estabilidad > 1 en h>=13          degradaba a escenario
    H-8  menos de 6 ventanas               degradaba a escenario
    H-9  ponderacion 1/h de D-5            se CONSERVA, medida y documentada

Ninguna tenia fuente identificada. Las ocho primeras se retiran como decisoras
y su informacion se conserva. La novena se conserva porque la alternativa sin
peso elige, en el unico caso donde discrepan, un modelo con peor RMSE fuera de
muestra (ver `03_REGLA_SELECCION/REGLA.md` de la carpeta de control).

Ejecucion:
    python tests/test_cierre_metodologico.py
"""
from __future__ import annotations

import ast
import inspect
import math
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica.criterios import (  # noqa: E402
    MIN_ITERACIONES_WF_ESCENARIO,
)
from app_icociv.proyeccion import servicio_proyeccion as sp  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    clasificar_intervalo_por_cobertura,
    peor_que_benchmark_naive,
)


def clasificar(rrmse_naive=0.9, rrmse_drift=0.9, es_benchmark=False, horizonte=1,
               factible=True, ancho=float("nan"), iteraciones=24,
               estabilidad=0.2, mase=0.5, mape=5.0, smape=5.0,
               estado_banda_intervalo=None):
    """Clasifica un horizonte controlando cada via por separado."""
    return sp._clasificar_evidencia_horizonte(
        horizonte=horizonte,
        modelo={
            "nombre": "drift" if es_benchmark else "exponencial_log_lineal",
            "nombre_visible": "Drift" if es_benchmark else "Exponencial/log-lineal",
            "es_benchmark": es_benchmark,
            "comparacion_benchmarks": {
                "rrmse_naive": rrmse_naive, "rrmse_drift": rrmse_drift,
                "rmae_naive": rrmse_naive, "rmae_drift": rrmse_drift,
            },
        },
        backtesting={"iteraciones": iteraciones, "metricas": {
            "mape": mape, "smape": smape, "mase": mase, "mae": 1.0, "rmse": 1.0,
            "sesgo_medio": 0.0, "estabilidad_error": estabilidad,
            "iteraciones": iteraciones,
        }},
        factibilidad={"factible": factible, "razones_tecnicas": [],
                      "advertencias": [], "estado": "Proyección técnica"},
        evaluacion_intervalos={"estado_banda": estado_banda_intervalo or sp.BANDA_VALIDA,
                               "banda_valida": estado_banda_intervalo in (None, sp.BANDA_VALIDA),
                               "advertencias": [], "razones": [],
                               "ancho_relativo_95_maximo": ancho,
                               "ancho_relativo_maximo": ancho},
    )


def cobertura(valor, n_paso=24, paso=6, n_prueba=22):
    return {
        "verificable": True,
        "verificable_paso_exacto": n_paso >= 16,
        "paso_exacto": paso, "n_errores_paso_exacto": n_paso,
        "cobertura_95_paso_exacto": valor, "cobertura_95_minima": valor,
        "metodo_evaluacion": "origen_movil",
        "por_horizonte": [{"horizonte": paso, "cobertura_95": valor,
                           "n_prueba": n_prueba}],
    }


def _texto(r) -> str:
    return " | ".join(str(x) for x in list(r["razones"]) + list(r["advertencias"]))


# ======================================================================
# H-1  El corte 1,25 no existe y rRMSE no bloquea
# ======================================================================
def test_el_corte_125_no_queda_en_ninguna_via_decisoria():
    """Si alguien reintroduce 1,25 en una rama que decide, esta prueba falla."""
    for funcion in (sp._clasificar_evidencia_horizonte,
                    sp._comparacion_desde_backtesting,
                    sp.peor_que_benchmark_naive):
        fuente = inspect.getsource(funcion)
        assert "UMBRAL_RRMSE_PEOR_BENCHMARK" not in fuente, funcion.__name__
        assert "TOLERANCIA_RRMSE_BENCHMARK" not in fuente, funcion.__name__
    assert not hasattr(sp, "puerta_rrmse_peor_que_benchmark"), (
        "la puerta se retiro; su nombre no debe reaparecer"
    )


def test_la_comparacion_con_el_benchmark_es_frente_a_uno():
    """1 es el punto de equivalencia, no un umbral elegido."""
    assert peor_que_benchmark_naive(1.0 + 1e-9, es_benchmark=False) is True
    assert peor_que_benchmark_naive(1.0, es_benchmark=False) is False
    assert peor_que_benchmark_naive(0.93, es_benchmark=False) is False
    # Comparar un benchmark consigo mismo no informa.
    assert peor_que_benchmark_naive(1.54, es_benchmark=True) is False
    # Sin ratio medible no se afirma nada.
    for valor in (None, float("nan"), float("inf"), ""):
        assert peor_que_benchmark_naive(valor, es_benchmark=False) is False


def test_un_rrmse_alto_ya_no_bloquea_pero_se_dice():
    """C-16 en h=1: rRMSE 1,5435. Antes bloqueaba; ahora se entrega y se avisa."""
    r = clasificar(rrmse_naive=1.5435, rrmse_drift=1.7703)
    assert r["no_recomendable"] is False, r["razones"]
    assert r["permitido"] is True
    assert "1.54" in _texto(r), _texto(r)
    assert "no supera al benchmark naive" in _texto(r)


def test_la_clave_de_factibilidad_es_descriptiva():
    comparacion = sp._comparacion_desde_backtesting(
        {"modelo": "exponencial_log_lineal", "metricas": {"rmse": 1.2, "mae": 1.2}},
        {"naive": {"metricas": {"rmse": 1.0, "mae": 1.0}},
         "drift": {"metricas": {"rmse": 1.0, "mae": 1.0}}},
        es_benchmark=False,
    )
    # 1,2 esta entre 1 y 1,25: antes la clave decia False y era falso.
    assert comparacion["modelo_no_supera_benchmarks"] is True
    assert comparacion["peor_que_naive_rmse"] is True


# ======================================================================
# H-3, H-6, H-7, H-8  Lo que degradaba a escenario y ahora advierte
# ======================================================================
def test_v12_ya_no_degrada_y_sigue_avisando():
    """Benchmark en h=18. La advertencia se conserva; el veto no."""
    r = clasificar(es_benchmark=True, horizonte=18)
    assert r["permitido_para_proyeccion_tecnica"] is True
    assert "benchmark/escenario simple" in _texto(r)


def test_la_amplitud_del_intervalo_ya_no_bloquea_ni_degrada():
    """IC95 del 300 %: se entrega, y el ancho NO se publica.

    ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Antes se exigia ademas que
    el texto dijera «Intervalos de prediccion muy amplios (IC95 300.0%)». Ese
    texto es RECONSTRUCTIVO: el ancho relativo multiplicado por el pronostico
    -publico- devuelve el semiancho de la banda que P0-C retiro. Exigirlo
    obligaria a publicar el intervalo por via textual.

    El contrato de fondo -que la amplitud NO bloquea ni degrada- es el que esta
    prueba protege, y se conserva intacto. Se anade la direccion contraria: que
    el ancho no reaparezca.
    """
    r = clasificar(ancho=3.0, horizonte=18)
    assert r["no_recomendable"] is False, r["razones"]
    assert r["permitido_para_proyeccion_tecnica"] is True
    texto = _texto(r).lower()
    for reconstructivo in ("ancho relativo", "ic95", "300.0%", "300,0"):
        assert reconstructivo not in texto, f"volvio a publicarse el ancho: {_texto(r)}"


def test_la_estabilidad_ya_no_degrada_y_sigue_avisando():
    r = clasificar(estabilidad=5.0, horizonte=18)
    assert r["permitido_para_proyeccion_tecnica"] is True
    assert "inestables" in _texto(r)


def test_la_evidencia_reducida_ya_no_degrada_y_sigue_avisando():
    """4 ventanas: por encima del minimo tecnico de 3, por debajo de 6."""
    r = clasificar(iteraciones=4)
    assert r["no_recomendable"] is False
    assert r["permitido_para_proyeccion_tecnica"] is True
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 2). El texto decia «Evidencia
    # fuera de muestra reducida: 4 ventanas de validacion (por debajo de 6 el
    # error fuera de muestra es poco estable)», presentando 6 como umbral de
    # estabilidad. Unificado con el vocabulario de tres tramos de HGRID, que dice
    # cuantos errores hay sin convertir 3 ni 6 en umbral de aceptacion.
    texto = _texto(r)
    assert "Evidencia fuera de muestra" in texto, texto
    assert "n=4" in texto, texto


def test_mase_sigue_siendo_descriptivo():
    r = clasificar(mase=9.3)
    assert r["permitido_para_proyeccion_tecnica"] is True
    assert "MASE" in _texto(r)


# ======================================================================
# H-4, H-5  Los dos cortes de cobertura
# ======================================================================
def test_ningun_corte_de_cobertura_degrada():
    for valor in (1.0, 0.95, 0.80, 0.79, 0.44, 0.0):
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert r["degrada_a_escenario"] is False, (valor, r["clasificacion_interna"])
        assert r["cobertura_observada"] == valor


def test_n_menor_16_se_publica_con_su_limitacion():
    r = clasificar_intervalo_por_cobertura(cobertura(1.0, n_paso=9))
    assert r["degrada_a_escenario"] is False
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida"
    assert r["cobertura_observada"] == 1.0
    assert r["n_errores_paso_exacto"] == 9
    assert r["cobertura_x_y"]
    assert r["diferencia_pp_frente_nominal"] is not None


def test_la_cobertura_se_declara_observada_y_no_garantizada():
    r = clasificar_intervalo_por_cobertura(cobertura(0.92))
    texto = " ".join(str(r.get(c, "")) for c in (
        "limitacion", "advertencia", "umbral_aplicado", "lectura_descriptiva",
        "etiqueta_visible", "consecuencia_operativa",
    )).lower()
    for prohibida in ("cobertura garantizada", "cobertura asegurada",
                      "validacion independiente", "calibracion no sesgada"):
        assert prohibida not in texto, prohibida
    assert "no es una garantia" in str(r["limitacion"]).lower()


# ======================================================================
# T-1 .. T-4  Lo que SIGUE bloqueando, y solo eso
# ======================================================================
def test_la_banda_no_valida_se_declara_sin_bloquear_el_punto():
    """Reescrito por P0-C ruta C2.

    P0-C RUTA C2, 14-08-2026. El contrato anterior —una banda invalida BLOQUEA—
    era correcto mientras el intervalo formaba parte del producto: sin banda no
    habia resultado completo que entregar. Retirado el intervalo (C2), un fallo
    aritmetico de un objeto que **ya no se publica** no puede cancelar un
    pronostico finito. Lo que sigue bloqueando es `PUNTO_NO_FINITO`, la
    imposibilidad del valor que SI se publica.
    """
    r = sp._clasificar_evidencia_horizonte(
        horizonte=1,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "es_benchmark": True,
                "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {"mape": 5.0, "smape": 5.0}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": sp.BANDA_LIMITES_INVERTIDOS,
                               "advertencias": [], "razones": [],
                               "ancho_relativo_95_maximo": float("nan")},
    )
    assert r["no_recomendable"] is False, r
    assert r["permitido"] is True, r
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Antes se exigia que el
    # estado de la banda apareciera en las advertencias PUBLICAS. El estado se
    # sigue registrando -viaja en `evaluacion_intervalos`, que es diagnostico
    # interno-, pero anunciar en la interfaz y en los informes que «la banda no
    # existe» informa sobre el defecto de un objeto que no se entrega en ningun
    # caso. Se comprueba la direccion util: que no bloquea y que no se filtra.
    publicas = " ".join(str(a) for a in r["advertencias"]).lower()
    for retirado in ("la banda no existe", "limite del intervalo", "construir la banda"):
        assert retirado not in publicas, f"vocabulario de la banda en salida publica: {r['advertencias']}"
    # Y la imposibilidad del PUNTO sigue bloqueando.
    punto = sp._clasificar_evidencia_horizonte(
        horizonte=1,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "es_benchmark": True,
                "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {"mape": 5.0, "smape": 5.0}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": sp.PUNTO_NO_FINITO,
                               "advertencias": [], "razones": [],
                               "ancho_relativo_95_maximo": float("nan")},
    )
    assert punto["no_recomendable"] is True, punto


def test_pocas_ventanas_limitan_el_intervalo_pero_no_el_punto():
    """P0-G REABIERTO, 14-08-2026. Antes se exigia que <3 ventanas BLOQUEARA.

    La revision independiente lo reprodujo: con n=8 y dos pares fuera de muestra,
    el punto y las metricas son finitos y aun asi la proyeccion se negaba. Ese
    corte no tiene fuente y, sobre todo, se aplicaba al eje equivocado: el punto
    sale del AJUSTE del modelo, no de las ventanas. Las ventanas hacen falta para
    construir y evaluar el INTERVALO, y ahi siguen operando —`_intervalos_prediccion`
    se niega a fabricar una banda sin respaldo—.

    Lo que se comprueba ahora es la separacion: pocas ventanas no cancelan el
    horizonte, y la carencia se comunica.
    """
    r = clasificar(iteraciones=MIN_ITERACIONES_WF_ESCENARIO - 1)
    assert r["no_recomendable"] is False, r
    assert r["bloqueo_por_datos"] is False, r
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 2). Antes bastaba la palabra
    # «ventanas»; el texto la traia dentro de una frase que citaba el minimo del
    # INTERVALO («por debajo de 3 no es posible construir ni evaluar el intervalo
    # de prediccion»). Ahora se exige lo sustantivo: que el NUMERO de errores
    # fuera de muestra se declare y que se califique de muy limitado.
    texto = " ".join(str(a) for a in (r.get("advertencias") or [])).lower()
    assert f"n={MIN_ITERACIONES_WF_ESCENARIO - 1}" in texto, texto
    assert "muy limitada" in texto, texto
    assert "intervalo" not in texto, f"la carencia se sigue explicando por el intervalo: {texto}"


def test_metricas_porcentuales_no_finitas_ya_no_bloquean():
    """AUDITORIA 09-08-2026 (E-03). Antes bloqueaban; era T-3.

    Esta prueba fijaba lo contrario y su fallo demostro que el criterio decidia.
    Se conserva lo que verificaba de fondo -que el caso se detecta y se
    comunica- y se sustituye la consecuencia: MAPE no esta definido si algun
    observado es cero y sMAPE si |y|+|yhat| es cero. Eso limita la METRICA, no
    el pronostico, y ninguna fuente sustenta cancelar una proyeccion por ello.
    RMSE, MAE y MASE siguen definidos y son los que sostienen la evidencia.
    """
    for evaluacion in (clasificar(mape=float("nan")), clasificar(smape=float("inf"))):
        assert evaluacion["no_recomendable"] is False
        assert not any(
            "porcentuales no finitas" in str(r) for r in evaluacion["razones"]
        )
    texto = " ".join(str(a) for a in clasificar(mape=float("nan"))["advertencias"]).lower()
    assert "mape no calculable" in texto


def test_la_cobertura_no_calculable_se_declara_y_ya_no_degrada():
    """P0-G REABIERTO, 14-08-2026 (regla R03 de la revision independiente).

    Antes la cobertura no calculable ponia `degrada_a_escenario = True` y el
    consumidor retiraba la clasificacion tecnica del horizonte. Que la cobertura
    no pueda MEDIRSE limita lo que cabe afirmar del intervalo, no la existencia
    del punto —y la propia advertencia del codigo ya lo decia: «el pronostico
    puntual se entrega igualmente»—. Mantener la degradacion contradecia ese
    texto y hacia que P0-C, abierto, siguiera decidiendo.

    Se conserva lo sustantivo: no se afirma ninguna cobertura que no se haya
    calculado.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(None, n_paso=24))
    assert r["clasificacion_interna"] == "no_calculable"
    assert r["cobertura_minima"] is None
    assert r["degrada_a_escenario"] is False, r
    assert "no es calculable" in r["advertencia"]
    texto = f"{r['etiqueta']} {r['advertencia']}".lower()
    for prohibida in ("garantiza", "validad", "asegurad"):
        assert prohibida not in texto, (prohibida, texto)


def test_lo_unico_que_bloquea_es_una_imposibilidad_del_propio_calculo():
    """P0-G REABIERTO: se retira el RECUENTO de vias y se prueba la propiedad.

    Contar `bloqueo_duro = True` protegia una cardinalidad accidental: cambiaba
    con cualquier refactor y no decia nada sobre QUE bloquea. Peor, la segunda via
    contada -menos de tres ventanas- resulto ser precisamente la regla sin fuente
    que la revision independiente marco como critica.

    Lo que importa es semantico y se comprueba sobre el comportamiento: bloquean
    las imposibilidades del propio resultado -un pronostico o unos limites que no
    son numeros, o un orden invertido- y nada mas.
    """
    # Bloquea: el PUNTO mismo es imposible. Es lo unico que queda tras C2.
    punto_imposible = clasificar(estado_banda_intervalo=sp.PUNTO_NO_FINITO)
    assert punto_imposible["no_recomendable"] is True, punto_imposible

    # No bloquean: son estados de una BANDA que C2 retiro del producto.
    for estado in (sp.BANDA_LIMITES_INVERTIDOS, sp.BANDA_LIMITES_NO_FINITOS,
                   sp.BANDA_NO_CALCULABLE, sp.BANDA_SEMIANCHO_CERO):
        assert clasificar(estado_banda_intervalo=estado)["no_recomendable"] is False, estado
    pocas = clasificar(iteraciones=MIN_ITERACIONES_WF_ESCENARIO - 1)
    assert pocas["no_recomendable"] is False, pocas

    fuente = inspect.getsource(sp._clasificar_evidencia_horizonte)
    assert "forzar_solo_escenario = True" not in fuente


# ======================================================================
# H-2  La salvaguarda no sustituye
# ======================================================================
def test_la_salvaguarda_no_sustituye_el_modelo():
    fuente = inspect.getsource(sp._aplicar_salvaguarda_benchmarks)
    assert "return mejor[1], mejor[2], salvaguarda" not in fuente, (
        "la salvaguarda no debe devolver las evaluaciones del benchmark"
    )
    assert "return evaluaciones, modelo_consistente, salvaguarda" in fuente
    assert "benchmark_habria_ampliado" in fuente, "el diagnostico debe conservarse"


# ======================================================================
# H-9  La regla de seleccion es desempeno OOS, y solo eso
# ======================================================================
def test_la_seleccion_no_consulta_ningun_umbral():
    fuente = inspect.getsource(sp.seleccionar_modelo_por_rmse_oos_global)
    for prohibido in ("UMBRAL_", "TOLERANCIA_", "es_benchmark", "MIN_ERRORES"):
        assert prohibido not in fuente, prohibido
    assert "rmse" in fuente.lower()


def test_la_ponderacion_1_h_ya_no_decide():
    """H-9 cerrada el 08-08-2026: era la ultima heuristica decisoria.

    El peso `1/h` no tenia fuente y cambiaba el modelo entregado. Lo sustituye
    el minimo RMSE fuera de muestra global sobre la muestra comun, que no tiene
    ningun parametro libre. El detalle esta en
    `tests/test_seleccion_rmse_global.py`.
    """
    fuente = inspect.getsource(sp._modelo_consistente_desde_comparativo)
    assert "1.0 / float(horizonte)" not in fuente
    assert "seleccionar_modelo_por_rmse_oos_global" in fuente


def test_la_seleccion_elige_el_de_menor_error_oos():
    import pandas as pd

    def bt(errores):
        return {"ejecutado": True,
                "metricas": {"rmse": float(sum(e ** 2 for e in errores) / len(errores)) ** 0.5},
                "predicciones": pd.DataFrame({"t": list(range(len(errores))),
                                              "Error": list(errores)})}

    banco = {"a_h1": bt([1.0, 1.0]), "b_h1": bt([2.0, 2.0]),
             "a_h2": bt([1.0, 1.0]), "b_h2": bt([2.0, 2.0])}
    assert sp.seleccionar_modelo_por_rmse_oos_global(banco, (1, 2)) == "a"


# ======================================================================
# Lo que esta sesion NO toca
# ======================================================================
def test_las_constantes_conservan_su_valor():
    """Se retira su papel decisorio, no su valor ni su publicacion."""
    assert sp.UMBRAL_RRMSE_PEOR_BENCHMARK == 1.25
    assert sp.TOLERANCIA_RRMSE_BENCHMARK == 1.10
    assert sp.MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert sp.COBERTURA_IC95_ADVERTENCIA == 0.80
    assert sp.COBERTURA_IC95_ACEPTABLE == 0.90


def test_no_queda_cascada_de_prefijo_en_ninguno_de_los_dos_maximos():
    """P0-H, 16-08-2026. Sustituye a `test_la_cascada_sigue_existiendo_para_causas_tecnicas`.

    Aquel test era incorrecto **por dos motivos independientes**.

    1. Exigia una cascada que P0-H retiro. Que los horizontes validos formen un
       prefijo desde h=1 no lo pide ninguna fuente, y hacia que una sola falla
       temprana cancelara toda la trayectoria posterior.

    2. Pasaba por una coincidencia de texto, no por una propiedad del codigo. La
       cadena `if evidencia["no_recomendable"]:` sobrevive dentro de un
       COMENTARIO que documenta el `break` retirado. `inspect.getsource` no
       distingue codigo de comentario, de modo que el assert habria seguido en
       verde tanto con el defecto restituido como con el defecto ausente. Es la
       clase de guarda que no protege nada, senalada por la revision
       independiente entre los tests incidentales.

    El nucleo nuevo es conductual: se construye un estado con un HUECO -h2 falla,
    h3 y h4 se sostienen- y se comprueba que las dos funciones que publican un
    maximo devuelven 4, no 1. La comprobacion estructural que se conserva recorre
    el ARBOL SINTACTICO en lugar del texto, de modo que ningun comentario pueda
    satisfacerla ni violarla.
    """
    estado = [
        {"horizonte": 1, "permitido_para_proyeccion_tecnica": True, "permitido_como_escenario": True},
        {"horizonte": 2, "permitido_para_proyeccion_tecnica": False, "permitido_como_escenario": False},
        {"horizonte": 3, "permitido_para_proyeccion_tecnica": True, "permitido_como_escenario": True},
        {"horizonte": 4, "permitido_para_proyeccion_tecnica": True, "permitido_como_escenario": True},
    ]
    assert sp._mayor_horizonte_con(estado, "permitido_para_proyeccion_tecnica") == 4
    assert sp._mayor_horizonte_permitido(estado) == 4

    # Retirar el prefijo NO puede convertir el horizonte fallido en permitido:
    # el hueco se informa, no se borra.
    assert estado[1]["permitido_para_proyeccion_tecnica"] is False
    assert estado[1]["permitido_como_escenario"] is False

    # Y el `break` no vuelve por via ejecutable. Se comprueba sobre el AST: un
    # `if` cuya condicion mencione `no_recomendable` no puede contener un `break`.
    arbol = ast.parse(textwrap.dedent(inspect.getsource(sp._evaluar_horizontes_proyeccion)))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.If) and "no_recomendable" in ast.unparse(nodo.test):
            assert not any(isinstance(hijo, ast.Break) for hijo in ast.walk(nodo)), (
                ast.unparse(nodo.test)
            )


def test_no_hay_modelo_por_horizonte():
    """La trayectoria se genera con UN modelo. S-HUECO no esta integrado.

    `_ejecutar_proyeccion_base` -el cuerpo real; `ejecutar_proyeccion` es un
    envoltorio de 15 lineas- toma un unico objeto `modelo` de
    `seleccion_horizonte` y proyecta con el toda la trayectoria en una sola
    llamada. Si alguien introdujera un ensamblaje por tramos, este recuento
    cambiaria.
    """
    fuente = inspect.getsource(sp._ejecutar_proyeccion_base)
    assert fuente.count("proyectar_modelo(") == 1, fuente.count("proyectar_modelo(")
    assert 'modelo = seleccion_horizonte["modelo"]' in fuente


def _ejecutar() -> int:
    fallos = 0
    for nombre, prueba in sorted(globals().items()):
        if nombre.startswith("test_") and callable(prueba):
            try:
                prueba()
                print(f"  OK   {nombre}")
            except AssertionError as exc:
                fallos += 1
                print(f"  FALLA {nombre}: {exc}")
    print(f"\n{'todas las pruebas pasan' if not fallos else f'{fallos} fallidas'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
