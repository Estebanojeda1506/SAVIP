"""Pruebas del nivel de evidencia reducida para horizontes cortos.

Cubren el caso detectado el 19 de julio de 2026: series cortas (n=24) negaban
un horizonte de 3 meses porque no alcanzaban las ventanas walk-forward mínimas,
aunque el desempeño medido era bueno. La corrección distingue entre
"no se pudo medir" (escenario con advertencia) y "se midió y salió mal"
(bloqueo), sin relajar los umbrales de error.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.criterios import (  # noqa: E402
    MIN_ITERACIONES_WF,
    MIN_ITERACIONES_WF_ESCENARIO,
)
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    _evaluar_intervalos_prediccion,
    _ejecutar_proyeccion_base,
    _estructurar_resultado_horizontes,
    _limites_auditoria_horizontes,
    _umbrales_incertidumbre,
    ejecutar_proyeccion,
)


def _periodos(n: int, anio_inicial: int = 2024) -> list[str]:
    return [f"{anio_inicial + i // 12}_{i % 12 + 1}" for i in range(n)]


def _serie(valores) -> pd.DataFrame:
    valores = list(valores)
    return pd.DataFrame({"Periodo": _periodos(len(valores)), "Indice": valores})


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _pares_disponibles(n: int, entrenamiento: int, horizonte: int) -> int:
    """Origenes walk-forward que admite el horizonte h: ``n - N0 - h + 1``.

    Identidad aritmetica del esquema de origen movil con ventana expansiva: el
    primer origen usa N0 observaciones y el ultimo par (t, t+h) exige que t+h
    caiga dentro de la muestra. Se calcula aqui para que las pruebas deriven el
    numero de pares en vez de fijarlo, y para que ningun tope historico -30, 57
    ni ningun otro- pueda colarse como contrato.
    """
    return n - entrenamiento - horizonte + 1


def _horizontes_con_pares(n: int) -> list[int]:
    """Horizontes que la aritmetica de ventanas permite medir en una serie de n."""
    entrenamiento = _limites_auditoria_horizontes(n)[0]
    return [
        h for h in range(1, n)
        if _pares_disponibles(n, entrenamiento, h) >= 1
    ]


def test_limites_distinguen_validado_y_escenario() -> None:
    """El techo de escenario debe ser mayor o igual que el validado."""
    assert MIN_ITERACIONES_WF_ESCENARIO < MIN_ITERACIONES_WF
    for n in (24, 26, 30, 61):
        entrenamiento, maximo_datos, limite, maximo_validado = _limites_auditoria_horizontes(n)
        assert maximo_datos >= maximo_validado
        assert limite <= maximo_datos
        # Coherencia con el conteo real de ventanas: origenes = n - entrenamiento - h + 1
        assert n - entrenamiento - maximo_validado + 1 >= MIN_ITERACIONES_WF
        # P0-G, 16-08-2026 (V-CODEX-3). Antes se exigia que el techo de la rejilla
        # dejara MIN_ITERACIONES_WF_ESCENARIO = 3 ventanas. Ese tres procede, por
        # declaracion de su propia ficha, de estimar la dispersion y verificar la
        # cobertura del INTERVALO, eje que P0-C retiro; usarlo para recortar los
        # horizontes del PUNTO era el acoplamiento que Codex marco como critico.
        #
        # El techo pasa a ser la cota de EXISTENCIA: al menos una ventana. No es
        # otro umbral elegido, es la frontera aritmetica -con cero ventanas no
        # hay ningun error fuera de muestra y el RMSE no esta definido-.
        assert n - entrenamiento - maximo_datos + 1 >= 1
        # Y `MIN_ITERACIONES_WF_ESCENARIO` sigue existiendo como corte
        # DESCRIPTIVO: no ha desaparecido, ha dejado de recortar.
        assert MIN_ITERACIONES_WF_ESCENARIO >= 1


def test_serie_corta_publica_su_cobertura_y_niega_solo_por_ventanas() -> None:
    """Serie corta: h=1 y h=3 se entregan; h=5 se niega por falta de ventanas.

    P0-E, 12-08-2026 — POR QUE LA SERIE PASA DE 24 A 12 OBSERVACIONES. Las tres
    situaciones que esta prueba fija son las mismas; lo que cambia es el tamano
    de serie que las produce, porque el primer origen dejo de ser
    `max(18, 0,60 n) = 18` -dos literales sin fuente- y pasa a derivarse de la
    estimabilidad de los candidatos, con valor 6.

        situacion            condicion            con N0=18   con N0=6
        h=1 muestra reducida n - N0 < 16 errores  n < 34      n < 22
        h=5 sin ventanas     n - N0 - 5 + 1 < 3   n < 25      n < 13

    Con 24 observaciones ambas se cumplian a la vez; con el criterio vigente ya
    no, y hace falta una serie de 12. **No es un fixture retocado para que la
    prueba pase**: es la misma prueba sobre el tamano que hoy reproduce las tres
    situaciones, y el cambio se declara aqui.

    Historia de este caso, porque resume el cierre metodológico:

    * hasta el 29-07-2026 h=1 era ``proyeccion_tecnica``;
    * ese día pasó a ``escenario`` porque con 24 observaciones ningún horizonte
      reúne los 16 errores fuera de muestra que exigía la verificación;
    * el **08-08-2026** se retira ese corte: 16 no tiene fuente identificada, y
      una muestra corta limita la PRECISIÓN de la cobertura medida, no la
      posibilidad de medirla ni la de proyectar.

    Vuelve a ser ``proyeccion_tecnica``, ahora con la cobertura publicada y su
    tamaño de muestra declarado. Lo que sigue negando h=5 es lo único que de
    verdad impide calcular: no hay ventanas de validación suficientes.
    """
    serie = _serie(np.linspace(100, 112, 12) + np.random.default_rng(3).normal(0, 0.25, 12))

    res1 = ejecutar_proyeccion(serie, *_objetivo(serie, 1), 2021)
    sol1 = res1["resultado_horizonte_solicitado"]
    assert sol1["estado"] == "proyeccion_tecnica", sol1["estado"]
    assert sol1["proyeccion_generada"] is True
    assert sol1["indice_proyectado"] is not None
    # P0-C, 16-08-2026 (V-CODEX-3). La cobertura y su clasificacion dejaron de
    # viajar en el objeto publico: todo lo que devuelve `ejecutar_proyeccion` ES
    # la salida publica, y describen una banda que no se entrega. La propiedad
    # que esta prueba fija -que una muestra corta limita la PRECISION de la
    # cobertura, no la posibilidad de proyectar- sigue siendo cierta y se mide
    # donde vive, en el resultado anterior al corte de publicacion.
    assert res1["clasificacion_intervalo"] is None
    assert res1["degradacion_por_cobertura"] is None
    interno1 = _estructurar_resultado_horizontes(
        _ejecutar_proyeccion_base(
            serie_df=serie, year_proj=_objetivo(serie, 1)[0],
            month_proj=_objetivo(serie, 1)[1], anio_base=2021),
        "predeterminado",
    )
    clasificacion = interno1["clasificacion_intervalo"]
    assert clasificacion["clasificacion_interna"] == "medida_con_muestra_reducida", clasificacion
    assert clasificacion["degrada_a_escenario"] is False
    assert clasificacion["cobertura_observada"] is not None
    assert clasificacion["cobertura_x_y"]
    assert interno1["degradacion_por_cobertura"]["aplicada"] is False

    res3 = ejecutar_proyeccion(serie, *_objetivo(serie, 3), 2021)
    sol3 = res3["resultado_horizonte_solicitado"]
    info3 = res3["analisis_horizontes_completo"]
    # Antes: no_admisible; luego escenario; ahora se entrega con advertencias.
    assert sol3["estado"] == "proyeccion_tecnica", sol3["estado"]
    assert sol3["proyeccion_generada"] is True
    assert sol3["indice_proyectado"] is not None
    # Los dos maximos se siguen publicando y son coherentes entre si.
    assert int(info3["horizonte_maximo_recomendado"]) <= int(info3["horizonte_maximo_admisible"])

    # P0-G, 16-08-2026 (V-CODEX-3). Antes se negaba h=5 y se comprobaba que ese
    # horizonte quedara por debajo de las TRES ventanas. Ese tres procede del eje
    # intervalo, retirado por P0-C; con n=12 y N0=6 el horizonte 5 reune DOS
    # ventanas y hoy es evaluable, de modo que negarlo carecia de sustento.
    #
    # La frontera autentica es la de EXISTENCIA. Se comprueba en h=7, que reune
    # CERO ventanas: ahi no hay ningun error fuera de muestra y el RMSE no esta
    # definido. No es escasez, es inexistencia del dato.
    n = len(serie)
    entrenamiento = _limites_auditoria_horizontes(n)[0]
    assert _pares_disponibles(n, entrenamiento, 5) >= 1, "h=5 deberia ser medible"

    res7 = ejecutar_proyeccion(serie, *_objetivo(serie, 7), 2021)
    sol7 = res7["resultado_horizonte_solicitado"]
    info7 = res7["analisis_horizontes_completo"]
    assert sol7["estado"] == "no_admisible"
    assert sol7["proyeccion_generada"] is False
    assert _pares_disponibles(n, entrenamiento, 7) < 1, (
        n, entrenamiento, _pares_disponibles(n, entrenamiento, 7)
    )
    # h=7 no se midio, luego no pudo ser reprobado: no aparece entre los evaluados.
    evaluados7 = [int(e["horizonte"]) for e in (info7.get("evaluaciones") or [])]
    assert 7 not in evaluados7, evaluados7
    # El maximo admisible publicado es EXACTAMENTE el mayor h medible: frontera
    # comprobada por ambos lados, sin literal alguno.
    maximo = int(info7["horizonte_maximo_admisible"])
    assert _pares_disponibles(n, entrenamiento, maximo) >= 1
    assert _pares_disponibles(n, entrenamiento, maximo + 1) < 1
    assert maximo == max(_horizontes_con_pares(n)), (maximo, _horizontes_con_pares(n))
    # Comprobacion negativa: la razon no atribuye la negacion al desempeno.
    razon = str(sol7["razon_principal"]).lower()
    for palabra in ("rmse", "mape", "mase", "desempe", "error del modelo"):
        assert palabra not in razon, (palabra, razon)


def test_la_rejilla_de_horizontes_no_tiene_tope_historico_ni_cascada() -> None:
    """P0-H: se mide todo lo que la aritmetica permite; ningun tope fijo sobrevive.

    Tres propiedades que el cierre F/H/G dejo acopladas y conviene separar:

    * **evaluado != publicable**. La rejilla evaluada la fija la aritmetica de
      ventanas. La continuidad del producto -``horizonte_maximo_publicable_continuo``-
      es una regla de presentacion, y el propio campo lo declara.
    * **sin cascada**. Un horizonte con evidencia pobre no borra la evidencia de
      los posteriores: ninguno queda sin evaluar.
    * **sin tope historico**. Con n=61 la rejilla llega a 53, muy por encima del
      cap 30 retirado. El numero no se fija aqui: se deriva.
    """
    serie = _serie(np.linspace(100, 150, 61) + np.random.default_rng(7).normal(0, 0.4, 61))
    n = len(serie)
    res = ejecutar_proyeccion(serie, *_objetivo(serie, 3), 2021)
    info = res["analisis_horizontes_completo"]

    esperados = _horizontes_con_pares(n)
    evaluados = [int(e["horizonte"]) for e in (info.get("evaluaciones") or [])]
    # 1. La rejilla medida es exactamente la que admite el numero de pares.
    assert evaluados == esperados, (evaluados[:5], evaluados[-5:], esperados[-5:])
    # 2. Nadie se queda sin medir por lo que ocurriera en un horizonte anterior.
    assert info.get("horizontes_no_evaluados") == [], info.get("horizontes_no_evaluados")
    # 3. El techo derivado supera con holgura el cap 30 retirado; se comprueba la
    #    ausencia del tope, no un valor nuevo.
    assert max(evaluados) > 30, max(evaluados)
    assert max(evaluados) == _limites_auditoria_horizontes(n)[1]

    # 4. ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 3). Antes se exigia que la
    #    base declarara la continuidad como «requisito de producto». Esa regla se
    #    retiro del calculo el 16-08-2026 -el maximo es `max(validos)`, no la
    #    racha desde h=1-, pero el texto la seguia publicando. Ahora se exige que
    #    declare lo que el codigo hace: que admite huecos y que no los interpola.
    base_continuo = str(info.get("base_horizonte_maximo_publicable_continuo") or "").lower()
    assert "no se interpola" in base_continuo, base_continuo
    assert "sin huecos" not in base_continuo, base_continuo
    # Y se publica en un campo distinto del techo estadistico, para que no pueda
    # presentarse una regla de presentacion como criterio de validacion.
    assert "horizonte_maximo_publicable_continuo" in info
    assert "horizonte_maximo_admisible" in info

    # 5. P0-E sigue sin cerrar: la evidencia OOS se publica como provisional y el
    #    bloqueo metodologico se declara junto al resultado.
    assert res.get("evidencia_oos_provisional") is True, res.get("evidencia_oos_provisional")
    assert "P0-E" in (res.get("bloqueos_metodologicos") or {}), res.get("bloqueos_metodologicos")


def test_serie_larga_conserva_proyeccion_tecnica() -> None:
    """Series con evidencia completa no cambian de clasificación."""
    serie = _serie(np.linspace(100, 150, 61) + np.random.default_rng(7).normal(0, 0.4, 61))
    res = ejecutar_proyeccion(serie, *_objetivo(serie, 3), 2021)
    sol = res["resultado_horizonte_solicitado"]
    assert sol["estado"] == "proyeccion_tecnica", sol["estado"]
    assert sol["proyeccion_generada"] is True


def test_serie_erratica_se_entrega_con_su_incertidumbre_a_la_vista() -> None:
    """Una serie errática ya no se bloquea: se entrega diciendo lo que es.

    CIERRE 08-08-2026. Lo que antes la bloqueaba eran los nueve cortes de
    amplitud del IC95, literales internos sin fuente. El propio proyecto ya
    había escrito que la anchura del intervalo es «consecuencia de la
    incertidumbre estimada, no un defecto sancionable» (FPP3 §5.5).

    Bloquear una proyección calculable equivale a decidir por el usuario. La
    alternativa auditable es entregarla con la incertidumbre medida delante:
    aquí, un IC95 desbordado y el diagnóstico residual completo. Ninguna de esas
    cifras se pierde; lo que desaparece es el veto sin fuente.

    P0-E, 12-08-2026. Se retira la comprobación de la advertencia por «ventanas
    de validación» reducidas. **No es una relajación de la prueba**: esa
    advertencia se emitía porque el primer origen era 18 y esta serie de 24
    observaciones dejaba solo cuatro ventanas en h=3. Derivado el primer origen
    de la estimabilidad (6), la misma serie reúne dieciséis, de modo que la
    advertencia **no corresponde** y exigirla comprobaría un artefacto del
    literal retirado. La negación por falta de ventanas sigue verificada en
    `test_serie_corta_publica_su_cobertura_y_niega_solo_por_ventanas`.
    """
    generador = np.random.default_rng(11)
    valores = 100 * np.exp(np.cumsum(generador.normal(0, 0.35, 24)))
    res = ejecutar_proyeccion(_serie(valores), *_objetivo(_serie(valores), 3), 2021)
    sol = res["resultado_horizonte_solicitado"]
    assert sol["proyeccion_generada"] is True
    texto = " | ".join(str(a) for a in (res["factibilidad"].get("advertencias") or []))
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Se exigia «Intervalos de
    # prediccion muy amplios para este horizonte (IC95 50.8%)» o «La incertidumbre
    # del intervalo 95% es excesiva (ancho relativo maximo 50.8%)».
    #
    # NO es una relajacion: esos dos textos son RECONSTRUCTIVOS. El ancho relativo
    # multiplicado por el pronostico -que es publico y debe serlo- devuelve el
    # semiancho de la banda que P0-C retiro, es decir una representacion
    # equivalente del intervalo. Exigirlos obligaria a publicar el intervalo por
    # una via textual. Se calculan y siguen viajando como diagnostico interno.
    #
    # Lo que la prueba comprueba sigue siendo lo mismo de fondo -que una serie
    # erratica se entrega CON su incertidumbre a la vista-, pero con las señales
    # que si son publicables: los diagnosticos residuales y MASE.
    assert "Breusch-Pagan" in texto or "Ljung" in texto or "Jarque" in texto, texto
    assert "MASE" in texto, texto
    for reconstructivo in ("ancho relativo", "IC95", "IP95"):
        assert reconstructivo not in texto, (
            f"volvio a publicarse el ancho de la banda retirada: {texto}"
        )


def test_banda_de_cautela_existe_en_todo_horizonte() -> None:
    """'cautela' debe ser estrictamente menor que el bloqueo en cada tramo.

    Si coinciden desaparece el estado intermedio y superar el umbral salta
    directo al bloqueo duro, que por cascada anula los horizontes siguientes.
    """
    for h in (1, 2, 3, 4, 6, 9, 12, 15, 18, 24):
        u = _umbrales_incertidumbre(h)
        assert u["aceptable"] <= u["cautela"] < u["no_recomendado"], (h, u)


def test_intervalo_amplio_en_horizonte_corto_no_bloquea_pero_degrada() -> None:
    """h=2 con IC95 relativo 22,8% (caso real) debe ser escenario, no bloqueo."""
    def _tabla(ancho: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "indice_proyectado": [100.0],
                "ancho_relativo_95": [ancho],
                "ancho_relativo_80": [ancho * 0.6],
            }
        )

    # Caso reportado: 22,8% en h=2 dejaba fuera todos los horizontes.
    evaluacion = _evaluar_intervalos_prediccion(_tabla(0.228), horizonte=2)
    assert evaluacion["critico"] is False, evaluacion
    # Un intervalo realmente desproporcionado en horizonte corto sigue bloqueado.
    assert _evaluar_intervalos_prediccion(_tabla(0.45), horizonte=2)["critico"] is True


def test_trayectoria_no_depende_del_horizonte_solicitado() -> None:
    """Los primeros valores proyectados deben ser iguales pidas 1, 3 o 18 meses."""
    serie = _serie(np.linspace(100, 150, 61) + np.random.default_rng(9).normal(0, 0.5, 61))
    referencia_modelo: str | None = None
    referencia_valores: list[float] = []
    for horizonte in (1, 2, 3, 6, 12, 18):
        res = ejecutar_proyeccion(serie, *_objetivo(serie, horizonte), 2021)
        proyecciones = res.get("proyecciones")
        if not isinstance(proyecciones, pd.DataFrame) or proyecciones.empty:
            continue
        modelo = str(res["resultado_horizonte_solicitado"].get("modelo_aplicado") or "")
        valores = [float(v) for v in proyecciones["indice_proyectado"].head(1)]
        if referencia_modelo is None:
            referencia_modelo, referencia_valores = modelo, valores
            continue
        assert modelo == referencia_modelo, (horizonte, modelo, referencia_modelo)
        assert np.allclose(valores, referencia_valores), (horizonte, valores, referencia_valores)


def test_modelo_agregado_minimiza_el_error_oos_global() -> None:
    """Una serie con tendencia lineal clara se resuelve con un modelo de tendencia.

    CIERRE H-9, 08-08-2026. Esta prueba exigía antes `drift` por su nombre, y lo
    exigía porque la regla de selección ponderaba los horizontes por `1/h` y
    drift domina el corto plazo. Retirada esa ponderación ---no tenía fuente---,
    la selección minimiza el error cuadrático medio fuera de muestra global, y
    sobre esta serie sintética gana `exponencial_log_lineal`: RMSE global 1,44
    frente a 1,95 de drift.

    El intercambio es real y conviene tenerlo escrito: **drift sigue siendo tres
    veces mejor en h=1** (0,449 frente a 1,329). La regla vigente no optimiza
    h=1; optimiza la pérdida cuadrática total observada, que es su definición.

    Lo que la prueba fija ahora es la propiedad de la regla, no la identidad del
    ganador: el modelo entregado es el de mínimo RMSE global sobre la muestra
    común. Si alguien reintroduce un peso por horizonte, esta prueba lo detecta.
    """
    from app_icociv.proyeccion.servicio_proyeccion import (
        _errores_oos_por_par,
        seleccionar_modelo_por_rmse_oos_global,
    )
    from app_icociv.validacion.backtesting import ejecutar_backtesting_comparativo

    valores = [100.0 + 0.45 * i + 1.8 * np.sin(i / 3.0) for i in range(61)]
    serie = _serie(valores)
    res = ejecutar_proyeccion(serie, *_objetivo(serie, 3), 2021)
    entregado = str(res["resultado_horizonte_solicitado"].get("modelo_aplicado") or "")
    assert entregado, res["resultado_horizonte_solicitado"]

    horizontes = tuple(range(1, 25))
    banco = ejecutar_backtesting_comparativo(
        serie[["Periodo", "Indice"]], horizontes=horizontes, anio_base=2021)
    esperado = seleccionar_modelo_por_rmse_oos_global(banco, horizontes)
    assert esperado is not None

    # El modelo entregado es el de mínimo RMSE global, recalculado aquí.
    pares = _errores_oos_por_par(banco, horizontes)
    comunes = set.intersection(*(set(d) for d in pares.values()))
    globales = {
        m: float(np.sqrt(sum(d[p] ** 2 for p in comunes) / len(comunes)))
        for m, d in pares.items()
    }
    assert esperado == min(globales, key=globales.get), globales


if __name__ == "__main__":
    test_trayectoria_no_depende_del_horizonte_solicitado()
    test_modelo_agregado_minimiza_el_error_oos_global()
    test_banda_de_cautela_existe_en_todo_horizonte()
    test_intervalo_amplio_en_horizonte_corto_no_bloquea_pero_degrada()
    test_limites_distinguen_validado_y_escenario()
    test_serie_corta_publica_su_cobertura_y_niega_solo_por_ventanas()
    test_serie_larga_conserva_proyeccion_tecnica()
    test_serie_erratica_se_entrega_con_su_incertidumbre_a_la_vista()
    test_la_rejilla_de_horizontes_no_tiene_tope_historico_ni_cascada()
    print("Pruebas de evidencia reducida por horizonte OK")
