"""Contratos fijados por la auditoria de fundamentacion metodologica (09-08-2026).

Cada prueba corresponde a un hallazgo con prueba roja documentada en
``AUDITORIA_FUNDAMENTACION_METODOLOGICA_INSTITUCIONAL_SAVIP_2026-08-09``.
Lo que fijan no es un resultado numerico sino una PROPIEDAD: que el producto no
publique una descripcion falsa de sus propias reglas y que ningun veto quede sin
fuente.
"""
from __future__ import annotations

from app_icociv.estadistica import criterios as C
from app_icociv.proyeccion import servicio_proyeccion as sp
from app_icociv.validacion.backtesting import seleccionar_mejor_modelo


def _fila(cid: str) -> C.CriterioEstadistico:
    return next(c for c in C.matriz_criterios() if c.id == cid)


# --------------------------------------------------------------------- F-05
# El texto de `justificacion_modelo` viaja a la interfaz, al DOCX y al PDF.
# Hasta el 09-08-2026 describia la ponderacion 1/h y la salvaguarda sustitutiva,
# retiradas ambas el 08-08-2026.

def _justificacion() -> str:
    return seleccionar_mejor_modelo("Drift", {}, {"metricas": {"rmse": 1.0, "mape": 1.0}})


def test_la_justificacion_publicada_no_menciona_la_ponderacion_retirada():
    texto = _justificacion().lower()
    assert "1/h" not in texto
    assert "ponderaci" not in texto


def test_la_justificacion_publicada_no_promete_salvaguarda_sustitutiva():
    assert "salvaguarda conservadora" not in _justificacion().lower()


def test_la_justificacion_publicada_describe_la_regla_vigente():
    texto = _justificacion().lower()
    assert "global" in texto
    assert "muestra com" in texto


# --------------------------------------------------------------------- E-03
# Una razon porcentual indefinida limita la METRICA, no el pronostico.

def _evidencia(mape: float, smape: float, rmse: float = 1.2, mae: float = 1.0) -> dict:
    return sp._clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={
            "iteraciones": 12,
            "metricas": {
                "mape": mape, "smape": smape, "mase": 0.5, "mae": mae, "rmse": rmse,
                "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 12,
            },
        },
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={
            "estado_banda": sp.BANDA_VALIDA, "ancho_relativo_95_maximo": 0.1,
        },
    )


def test_mape_no_finito_no_bloquea_el_horizonte():
    ev = _evidencia(float("nan"), float("nan"))
    assert ev["permitido"] is True
    assert not any("porcentuales no finitas" in str(r) for r in ev["razones"])


def test_mape_no_calculable_se_publica_como_advertencia():
    ev = _evidencia(float("nan"), float("nan"))
    texto = " ".join(str(a) for a in ev["advertencias"]).lower()
    assert "mape no calculable" in texto
    assert "smape no calculable" in texto


def test_sin_ventanas_suficientes_el_punto_sigue_pero_el_intervalo_no():
    """P0-G REABIERTO, 14-08-2026 (regla R02 de la revision independiente).

    Esta prueba llamaba «imposibilidad» a tener menos de tres ventanas. No lo es:
    el punto se calcula del AJUSTE del modelo y existe con dos ventanas, como
    demostro el caso n=8 -punto 112,0 y RMSE/MAE finitos-. Las ventanas hacen
    falta para construir y evaluar el INTERVALO, y ahi el piso sigue vigente:
    `_intervalos_prediccion` se niega a fabricar una banda sin respaldo.

    Lo que se fija ahora es que el horizonte no se cancele y que la carencia se
    comunique.
    """
    ev = sp._clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 2, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 2}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": sp.BANDA_VALIDA, "ancho_relativo_95_maximo": 0.1},
    )
    assert ev["permitido"] is True, ev
    assert ev["no_recomendable"] is False, ev
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 2). Antes bastaba la palabra
    # «ventanas», que llegaba dentro de una frase que citaba el minimo del
    # INTERVALO. Se exige lo sustantivo: que el numero de errores fuera de muestra
    # se declare y se califique de muy limitado, sin nombrar un intervalo que no
    # se entrega.
    texto = " ".join(str(a) for a in (ev.get("advertencias") or [])).lower()
    assert "n=2" in texto, texto
    assert "muy limitada" in texto, texto
    assert "intervalo" not in texto, f"la carencia se explica por el intervalo: {texto}"


def test_banda_no_valida_se_declara_sin_bloquear_el_punto():
    """Reescrito por P0-C ruta C2.

    P0-C RUTA C2, 14-08-2026. El contrato anterior —una banda invalida BLOQUEA—
    era correcto mientras el intervalo formaba parte del producto: sin banda no
    habia resultado completo que entregar. Retirado el intervalo (C2), un fallo
    aritmetico de un objeto que **ya no se publica** no puede cancelar un
    pronostico finito. Lo que sigue bloqueando es `PUNTO_NO_FINITO`, la
    imposibilidad del valor que SI se publica.
    """
    ev = sp._clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 12, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 12}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": sp.BANDA_LIMITES_INVERTIDOS,
                               "ancho_relativo_95_maximo": 0.1},
    )
    assert ev["permitido"] is True, ev
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Antes se exigia que el
    # estado de la banda apareciera en las advertencias PUBLICAS. El estado se
    # sigue registrando en `evaluacion_intervalos` -diagnostico interno-, pero
    # anunciar que «la banda no existe» informa sobre el defecto de un objeto que
    # no se entrega en ningun caso. El contrato de fondo -que NO bloquea- se
    # conserva, y se anade la direccion contraria.
    publicas = " ".join(str(a) for a in ev["advertencias"]).lower()
    for retirado in ("la banda no existe", "limite del intervalo", "construir la banda"):
        assert retirado not in publicas, f"vocabulario de la banda en publico: {ev['advertencias']}"


def test_lo_que_bloquea_son_imposibilidades_del_resultado_no_carencias_de_evidencia():
    """P0-G REABIERTO: se retira el recuento de `bloqueo_duro = True`.

    Contar ocurrencias protegia una cardinalidad accidental -cambia con cualquier
    refactor- y no decia QUE bloquea. Ademas una de las dos contadas era la regla
    sin fuente que la revision independiente marco como critica.

    Se prueban las dos familias semanticas que deben seguir bloqueando, y las dos
    carencias de evidencia que ya no pueden hacerlo.
    """
    def _clasificar(estado_banda, iteraciones=24):
        return sp._clasificar_evidencia_horizonte(
            horizonte=6,
            modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
            backtesting={"iteraciones": iteraciones, "metricas": {
                "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
                "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": iteraciones}},
            factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
            evaluacion_intervalos={"estado_banda": estado_banda, "ancho_relativo_95_maximo": 0.1},
        )

    # Lo unico que bloquea tras C2: la no finitud del PUNTO publicado.
    assert _clasificar(sp.PUNTO_NO_FINITO)["permitido"] is False
    # Los estados de la BANDA retirada se clasifican y NO bloquean.
    for estado in (sp.BANDA_LIMITES_NO_FINITOS, sp.BANDA_LIMITES_INVERTIDOS,
                   sp.BANDA_NO_CALCULABLE):
        assert _clasificar(estado)["permitido"] is True, estado
    assert _clasificar(sp.BANDA_VALIDA, iteraciones=2)["permitido"] is True


# --------------------------------------------------------------------- K-03
def test_la_construccion_del_intervalo_tiene_fuente_completa():
    """AUDITORIA 09-08-2026 (P0-C). Antes fijaba que C-INT-001 NO fuera bibliografica.

    Y era correcto entonces: la construccion combinaba dos metodos por max() sin
    fuente para la combinacion. Al adoptarse la construccion COMPLETA de FPP3
    5.5, la fila vuelve a ser bibliografica con pleno derecho. Lo que esta
    prueba fija ahora es que la fila declare el metodo y su fuente, y que NO
    reaparezca ninguna combinacion ad hoc.
    """
    fila = _fila("C-INT-001")
    assert fila.tipo == C.TIPO_BIBLIOGRAFICO
    texto = (fila.valor + " " + fila.fuente).lower()
    assert "sigma_h" in texto and "5.5" in texto
    assert "max(" not in texto


# --------------------------------------------------------------------- K-04
def test_la_muestra_de_evaluacion_de_la_seleccion_esta_fundamentada():
    """P0-D. RMSE_global es el RMSE sobre una MUESTRA DE EVALUACION.

    Lo que debe estar fundamentado no es «agregar» sino CUAL es esa muestra, y
    se deduce del contrato: un modelo por serie que debe servir todos los meses
    entregables. La fila no puede afirmar que la agregacion no sea una eleccion,
    ni atribuir a la rejilla un alcance mayor que el del producto.
    """
    fila = _fila("C-SEL-001")
    texto = (fila.fuente + " " + fila.justificacion).lower()
    assert "no una convencion elegida" not in texto
    assert "que el producto no entrega" not in texto
    assert "entregable" in texto, "no consta la justificacion del conjunto de evaluacion"


def test_la_seleccion_no_escala_los_errores_y_declara_por_que():
    """El escalado resuelve la comparacion ENTRE series, no dentro de una."""
    texto = (_fila("C-SEL-001").fuente + " " + _fila("C-SEL-001").justificacion).lower()
    assert "5.8" in texto or "escalad" in texto


# --------------------------------------------------------------------- K-01
def test_los_cortes_de_amplitud_no_se_publican_como_bloqueo():
    justificacion = _fila("C-INT-003").justificacion.lower()
    assert "bloquear el horizonte" not in justificacion
    assert justificacion.startswith("descriptivo")


# --------------------------------------------------------------------- K-02
def test_los_cortes_de_benchmark_retirados_no_se_publican_como_vigentes():
    fila = _fila("C-BEN-001")
    assert fila.tipo == C.TIPO_MUERTO
    assert "1.25" not in fila.valor


# --------------------------------------------------------------------- I-01
def test_la_evaluacion_de_cobertura_cita_su_fuente():
    assert "christoffersen" in _fila("C-INT-004").fuente.lower()


# --------------------------------------------------------------------- J-01
def test_el_minimo_de_ventanas_se_deriva_del_intervalo_y_no_de_la_metrica():
    justificacion = _fila("C-HOR-003").justificacion.lower()
    assert "minimo para que exista una medicion" not in justificacion
    assert "cobertura" in justificacion


# --------------------------------------------------------------------- P0-A
# El selector de respaldo combinaba once coeficientes sin fuente e incluia
# penalizaciones por identidad del modelo. Se retiro el 09-08-2026.

def test_la_ruta_productiva_no_invoca_el_selector_de_respaldo():
    import inspect
    fuente = inspect.getsource(sp._evaluar_horizontes_proyeccion)
    assert "seleccionar_modelo_por_evidencia(" not in fuente


def test_el_selector_de_respaldo_no_se_importa_en_la_ruta_productiva():
    import inspect
    assert "seleccionar_modelo_por_evidencia" not in "".join(
        inspect.getsource(sp).splitlines(keepends=True)[:120]
    )


def test_sin_evidencia_comparable_el_horizonte_no_se_entrega():
    """C-SEL-001 sin decision => no se fabrica un modelo con un puntaje propio."""
    import inspect
    fuente = inspect.getsource(sp._evaluar_horizontes_proyeccion)
    assert "modelo_no_seleccionable" in fuente


def test_el_selector_retirado_conserva_su_definicion_para_auditoria():
    """Se conserva sin llamadas, como se hizo con la regla 1/h."""
    from app_icociv.estadistica import modelos_interpretables as mi
    assert callable(mi.seleccionar_modelo_por_evidencia)
    assert "RETIRADA COMO SELECTOR" in (mi.seleccionar_modelo_por_evidencia.__doc__ or "")


# --------------------------------------------------------------------- P0-B
# El catalogo lo gobernaban siete literales sin fuente. Se sustituyen por
# estimabilidad matematica y sustento de los parametros propios.

def _codigo_ejecutable(fn) -> str:
    """Fuente de una funcion sin su docstring, para no emparejar la memoria."""
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(fn).lstrip())
    cuerpo = arbol.body[0].body
    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)):
        cuerpo = cuerpo[1:]
    return "\n".join(ast.unparse(n) for n in cuerpo)


def test_ningun_literal_sin_fuente_gobierna_el_catalogo():
    codigo = _codigo_ejecutable(sp._modelos_para_analisis)
    for literal in ("0.035", "0.05", "48", "horizonte >= 7", "horizonte <= 6",
                    "MIN_OBS_NIVEL_2"):
        assert literal not in codigo, literal


def test_el_catalogo_excluye_solo_por_parametro_sin_sustento():
    assert sorted(sp.MODELOS_PARAMETRO_SIN_SUSTENTO) == [
        "promedio_movil", "variacion_reciente"
    ]
    codigo = _codigo_ejecutable(sp._modelos_para_analisis)
    assert "MODELOS_PARAMETRO_SIN_SUSTENTO" in codigo


def test_huber_no_se_excluye_por_un_minimo_sin_fuente():
    from app_icociv.estadistica import modelos_interpretables as mi
    assert "MIN_OBS_HUBER" not in _codigo_ejecutable(mi.ajustar_modelos_candidatos)


def test_la_elegibilidad_la_resuelve_cada_modelo():
    """Un modelo no estimable se excluye por su propia excepcion, no por filtro."""
    from app_icociv.estadistica import modelos_interpretables as mi
    import numpy as np
    t = np.arange(3, dtype=float)
    y = np.array([100.0, -5.0, 102.0])          # y<=0 rompe las transformaciones log
    cands = {c["nombre"]: c for c in mi.ajustar_modelos_candidatos(t, y)}
    assert "error" in cands["exponencial_log_lineal"], "deberia excluirse por dominio"
    assert "predict" in cands["naive"], "naive es estimable y debe competir"
    assert "predict" in cands["drift"], "drift es estimable y debe competir"


# --------------------------------------------------------------------- matriz
def test_la_matriz_conserva_tipos_admitidos():
    C.validar_tipos_criterios()


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
