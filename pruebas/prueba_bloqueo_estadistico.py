"""Pruebas de factibilidad gradual y proyección cautelosa ICOCIV."""

from __future__ import annotations

import math

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.estadistica.criterios import MIN_ITERACIONES_WF, MIN_ITERACIONES_WF_ESCENARIO  # noqa: E402
from app_icociv.validacion.backtesting import ejecutar_backtesting  # noqa: E402
from app_icociv.estadistica.analisis_series import evaluar_factibilidad_proyeccion  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    ESTADO_CALCULABLE_PENDIENTE,
    _limites_auditoria_horizontes,
    ejecutar_proyeccion,
)
from app_icociv.reportes.generador_reportes import generar_reporte_pdf, generar_reporte_proyeccion  # noqa: E402

#: Etiquetas ordinales de la escalera de confianza metodologica retirada en P0-G.
#: Ninguna puede volver a publicarse: sostenian una consecuencia -degradar o
#: bloquear- con literales internos sin fuente (REQ 5, REQ 7). Se comprueban por
#: ausencia, no por pertenencia: fijar el conjunto NUEVO reconstruiria la escalera
#: dentro de la propia prueba.
ESCALERA_RETIRADA = {
    "alto", "medio", "bajo", "no recomendable",
    "alta confiabilidad relativa", "proyeccion con cautela", "proyección con cautela",
    "proyectable con cautela", "solo proyeccion de corto plazo",
    "solo proyección de corto plazo",
}


def _sin_escalera_de_confianza(factibilidad: dict) -> None:
    """La confianza publicada debe ser descriptiva, nunca un grado ordinal."""
    confianza = str(factibilidad.get("nivel_confianza_metodologica") or "").strip().lower()
    assert confianza not in ESCALERA_RETIRADA, confianza


def _pares_disponibles(n: int, horizonte: int) -> int:
    """Origenes walk-forward que admite h: ``n - N0 - h + 1``, con N0 de produccion."""
    return n - _limites_auditoria_horizontes(n)[0] - horizonte + 1


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _periodos(n: int) -> list[str]:
    return [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(n)]


def serie_drift_superior(n: int = 61) -> pd.DataFrame:
    valores = [100.0 + 0.5 * i + 2.0 * np.sin(i / 3.0) for i in range(n)]
    return pd.DataFrame({"Periodo": _periodos(n), "Indice": valores})


def serie_suave_con_ruido(n: int = 72) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    valores = [100.0 + 0.20 * i + 0.004 * (i ** 2) + float(rng.normal(0, 0.16)) for i in range(n)]
    return pd.DataFrame({"Periodo": _periodos(n), "Indice": valores})


def serie_erratica(n: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(99)
    valores = [
        max(1.0, 100.0 + (50.0 if i % 2 == 0 else -50.0) + float(rng.normal(0, 25.0)))
        for i in range(n)
    ]
    return pd.DataFrame({"Periodo": _periodos(n), "Indice": valores})


def serie_pocos_datos() -> pd.DataFrame:
    return pd.DataFrame({"Periodo": _periodos(10), "Indice": [100 + i for i in range(10)]})


def test_drift_superior_permite_proyeccion_corta() -> None:
    serie = serie_drift_superior()
    bt_lineal = ejecutar_backtesting(serie, horizonte=1, modelo="lineal")
    bt_drift = ejecutar_backtesting(serie, horizonte=1, modelo="drift")
    assert bt_drift["metricas"]["rmse"] < bt_lineal["metricas"]["rmse"]

    resultado = ejecutar_proyeccion(serie, 2026, 4, 2021)
    assert resultado["proyeccion_generada"] is True
    assert resultado["horizonte_permitido"] <= resultado["horizonte_solicitado"]

    # P0-G, 13-08-2026. Antes se exigia que el estado perteneciera al conjunto
    # {"Proyeccion con cautela", "Alta confiabilidad relativa"}: los peldanos de
    # la escalera de confianza. La escalera se retiro porque sus literales no
    # tenian fuente que autorizara la consecuencia aplicada, y `estado` es hoy un
    # texto descriptivo. Fijar el conjunto NUEVO seria reconstruir la escalera
    # dentro de la prueba; lo que se comprueba es que no vuelva, y que el estado
    # metodologico distinga calculo de sustentacion.
    factibilidad = resultado["factibilidad"]
    assert factibilidad["factible"] is True, factibilidad
    assert str(factibilidad.get("estado") or "").strip(), factibilidad
    _sin_escalera_de_confianza(factibilidad)
    assert resultado["estado_metodologico"] == ESTADO_CALCULABLE_PENDIENTE, resultado["estado_metodologico"]
    # REQ 14: el intervalo no sustentado convive con un punto calculable.
    assert resultado["intervalo_sustentado"] is False
    assert {"P0-C", "P0-E"} <= set(resultado["bloqueos_metodologicos"] or {})


def test_dw_bajo_no_bloquea_globalmente_si_hay_backtesting_aceptable() -> None:
    resultado = evaluar_factibilidad_proyeccion(
        serie_drift_superior(),
        {"observaciones": 61, "errores_criticos": [], "continuidad_temporal": "OK"},
        diagnostico={"durbin_watson": 0.25, "acf": [{"lag": 1, "valor": 0.7}]},
        backtesting={
            "ejecutado": True,
            "iteraciones": 12,
            "metricas": {
                "mae": 0.6,
                "rmse": 0.8,
                "mape": 0.7,
                "smape": 0.7,
                "mase": 1.2,
                "sesgo_medio": 0.1,
                "estabilidad_error": 0.5,
                "porcentaje_errores_extremos": 0.0,
            },
        },
        comparacion_benchmarks={"rrmse_naive": 0.8, "rrmse_drift": 1.0},
        horizonte_solicitado=1,
    )
    # D-2: Durbin-Watson queda como estadistico descriptivo. Un valor bajo no
    # bloquea la proyeccion ni genera una advertencia categorica basada en
    # cortes internos sin fuente. La intencion original de la prueba se
    # conserva y se refuerza: con backtesting aceptable, un DW de 0,25 no
    # impide proyectar.
    assert resultado["factible"] is True
    # P0-G: se retira la pertenencia al conjunto de peldanos de la escalera. Lo
    # que la prueba fija es lo que su nombre dice: un DW de 0,25 no bloquea ni
    # degrada por si solo, y el diagnostico sigue siendo informativo.
    _sin_escalera_de_confianza(resultado)
    assert not any(
        "autocorrelación residual severa" in a.lower() or "limitar horizonte" in a.lower()
        for a in resultado["advertencias"]
    ), "Durbin-Watson no debe emitir advertencia categorica por cortes internos"


def test_fechas_criticas_bloquean() -> None:
    serie = serie_suave_con_ruido(30)
    serie.loc[5, "Periodo"] = "2021_13"
    resultado = ejecutar_proyeccion(serie, 2023, 8, 2021)
    assert resultado["proyeccion_generada"] is False
    assert resultado["factibilidad"]["estado"] == "No proyectable por errores criticos de datos"


def test_pocos_datos_entrega_el_punto_con_evidencia_limitada() -> None:
    """P0-G, 16-08-2026 (V-CODEX-3). Antes se exigia el bloqueo por serie corta.

    Con diez observaciones y N0=6 la rejilla anterior llegaba a h=2 -porque
    reservaba tres ventanas para poder construir y verificar la BANDA- y una
    solicitud de h=3 se negaba. Ese tres procede del eje intervalo, que P0-C
    retiro, y no tiene fuente que autorice negar un PUNTO.

    Hoy la rejilla se acota por la cota de existencia `h <= n - N0`: con diez
    observaciones llega a h=4. Lo que se comprueba es que el punto se entrega
    Y que la escasez de evidencia se comunica, no que se oculte.
    """
    resultado = ejecutar_proyeccion(serie_pocos_datos(), 2022, 1, 2021)
    assert resultado["proyeccion_generada"] is True, resultado.get("explicacion")
    assert math.isfinite(float(resultado["y_proj"]))
    assert resultado["factibilidad"]["puede_generarse_informe"] is True
    # La evidencia sigue siendo provisional y el recuento de ventanas viaja.
    assert resultado["evidencia_oos_provisional"] is True
    paso = resultado.get("verificabilidad_paso_exacto") or {}
    assert int(paso.get("n_errores_oos") or 0) >= 1, paso
    # Y el motivo del bloqueo, cuando lo haya, nunca puede ser el minimo global.
    motivo = str(resultado.get("explicacion") or "").lower()
    assert "mínimo 8" not in motivo and "minimo 8" not in motivo


def test_intervalos_amplios_no_bloquean_ni_degradan_por_si_solos() -> None:
    resultado = evaluar_factibilidad_proyeccion(
        serie_suave_con_ruido(),
        {"observaciones": 72, "errores_criticos": [], "continuidad_temporal": "OK"},
        diagnostico={"durbin_watson": 2.0, "acf": []},
        backtesting={
            "ejecutado": True,
            "iteraciones": 10,
            "metricas": {
                "mae": 0.4,
                "rmse": 0.6,
                "mape": 0.5,
                "smape": 0.5,
                "mase": 0.7,
                "sesgo_medio": 0.0,
                "estabilidad_error": 0.4,
                "porcentaje_errores_extremos": 0.0,
            },
        },
        evaluacion_intervalos={
            "critico": True,
            "ancho_relativo_maximo": 0.45,
            "razones": ["La incertidumbre del intervalo de predicción es excesiva."],
        },
        horizonte_solicitado=6,
    )
    # CIERRE 08-08-2026: los nueve cortes de amplitud del IC95 eran literales sin
    # fuente. Un intervalo ancho es la incertidumbre estimada, no un defecto
    # sancionable (FPP3 5.5): se publica su valor y no restringe el horizonte.
    # Antes esta prueba exigia el peldano «Solo proyeccion de corto plazo».
    assert resultado["factible"] is True
    _sin_escalera_de_confianza(resultado)
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Antes se exigia que el
    # ancho medido viajara «como informacion» en las advertencias publicas. Es
    # RECONSTRUCTIVO: el ancho relativo por el pronostico -que es publico-
    # devuelve el semiancho de la banda que P0-C retiro, es decir una
    # representacion equivalente del intervalo. El calculo se conserva como
    # diagnostico interno; lo que se retira es su publicacion.
    #
    # El contrato de fondo -que un intervalo ancho NO bloquea ni degrada- es el
    # que esta prueba protege, y se comprueba igual. Se anade la direccion
    # contraria: que el ancho no reaparezca en la salida publica.
    _publicas = " ".join(str(a) for a in (resultado.get("advertencias") or [])).lower()
    for _reconstructivo in ("ancho relativo", "ic95", "incertidumbre del intervalo"):
        assert _reconstructivo not in _publicas, (
            f"volvio a publicarse el ancho de la banda retirada: {resultado['advertencias']}"
        )
    assert resultado["horizonte_maximo_sugerido"] >= 6, resultado


def test_serie_erratica_se_entrega_con_su_incertidumbre() -> None:
    """CIERRE 08-08-2026: una serie erratica ya no se bloquea; se advierte.

    La bloqueaban los cortes de amplitud del IC95, nueve literales internos sin
    fuente. Un pronostico calculable con incertidumbre enorme se entrega
    diciendo cuanta: el ancho relativo viaja con su valor. Si algo la bloquea,
    debe ser una imposibilidad de calculo, y eso tambien se comprueba.
    """
    resultado = ejecutar_proyeccion(serie_erratica(), 2023, 9, 2021)
    if not resultado["proyeccion_generada"]:
        razones = " ".join(str(r) for r in resultado["factibilidad"].get("razones_tecnicas", []))
        assert ("ventanas" in razones.lower() or "no finitas" in razones.lower()
                or "no valida" in razones.lower()), razones
        return
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Se exigia «Intervalos
    # amplios (IC95 X%)» o «La incertidumbre del intervalo 95% es excesiva (ancho
    # relativo maximo X%)». Ambos son RECONSTRUCTIVOS: el ancho relativo por el
    # pronostico -publico- devuelve el semiancho de la banda retirada.
    #
    # El contrato de fondo -que la serie erratica SE ENTREGA y no en silencio- se
    # conserva, con las senales que si son publicables: los diagnosticos
    # residuales y los atipicos detectados.
    advertencias = " | ".join(str(a) for a in resultado["factibilidad"].get("advertencias", []))
    assert advertencias.strip(), "la serie erratica se entrego sin ninguna advertencia"
    for _reconstructivo in ("ancho relativo", "IC95", "IP95"):
        assert _reconstructivo not in advertencias, (
            f"volvio a publicarse el ancho de la banda retirada: {advertencias}"
        )


def test_los_vetos_retirados_no_vuelven_a_bloquear() -> None:
    """Regresion negativa de P0-G: los cuatro cortes retirados, uno por uno.

    Cada escenario se construye con la ARITMETICA de ventanas, no con tamanos
    elegidos a mano: `n - N0 - h + 1`, con N0 tomado de produccion. Si N0 cambia,
    la prueba sigue el cambio en vez de romperse contra un literal.
    """
    # 1. ADVERTENCIA_MIN_OBS = 18 no veta. Serie de 14 observaciones, calculable.
    corta = serie_suave_con_ruido(14)
    assert len(corta) < 18
    assert _pares_disponibles(len(corta), 1) >= MIN_ITERACIONES_WF_ESCENARIO
    res_corta = ejecutar_proyeccion(corta, *_objetivo(corta, 1), 2021)
    assert res_corta["proyeccion_generada"] is True, res_corta.get("explicacion")
    _sin_escalera_de_confianza(res_corta["factibilidad"])

    # 2. MIN_ITERACIONES_WF = 6 no veta: con pares entre el minimo de escenario y
    #    6 la serie se entrega, porque medir con pocas ventanas limita la
    #    PRECISION de la evidencia, no la posibilidad de calcularla.
    pocas = serie_suave_con_ruido(12)
    pares = _pares_disponibles(len(pocas), 3)
    assert MIN_ITERACIONES_WF_ESCENARIO <= pares < MIN_ITERACIONES_WF, (pares,)
    res_pocas = ejecutar_proyeccion(pocas, *_objetivo(pocas, 3), 2021)
    assert res_pocas["proyeccion_generada"] is True, res_pocas.get("explicacion")

    # 3. Una banda no sustentada NO bloquea un punto finito y coherente (REQ 14).
    assert res_pocas["intervalo_sustentado"] is False
    assert res_pocas["resultado_horizonte_solicitado"]["indice_proyectado"] is not None

    # 4. Lo que si sigue bloqueando: la INEXISTENCIA del dato, comprobada por
    #    ambos lados de la frontera.
    #
    #    P0-G, 16-08-2026 (V-CODEX-3). Este bloque exigia antes que una serie de
    #    diez observaciones negara h=3 por reunir menos de
    #    MIN_ITERACIONES_WF_ESCENARIO ventanas. Ese corte de tres procede -por
    #    declaracion de su propia ficha- de estimar la dispersion y verificar la
    #    cobertura del INTERVALO, eje que P0-C retiro; con dos ventanas el error
    #    fuera de muestra EXISTE y el RMSE es calculable, de modo que negar el
    #    punto carecia de sustento.
    #
    #    La frontera autentica es `h <= n - N0`, es decir al menos una ventana.
    #    No es un umbral elegido: por encima no hay ningun error fuera de muestra
    #    que medir. Se comprueba el ultimo horizonte medible y el primero que no
    #    lo es, ambos derivados de la aritmetica y no fijados a mano.
    minima = serie_pocos_datos()
    n = len(minima)
    ultimo_medible = max(h for h in range(1, n) if _pares_disponibles(n, h) >= 1)
    assert _pares_disponibles(n, ultimo_medible) >= 1
    assert _pares_disponibles(n, ultimo_medible + 1) < 1

    # Con evidencia minima -pero existente- el punto se entrega.
    res_borde = ejecutar_proyeccion(minima, *_objetivo(minima, ultimo_medible), 2021)
    assert res_borde["proyeccion_generada"] is True, res_borde.get("explicacion")
    assert res_borde["resultado_horizonte_solicitado"]["indice_proyectado"] is not None

    # Un paso mas alla no hay dato, y ahi si se niega.
    res_minima = ejecutar_proyeccion(minima, *_objetivo(minima, ultimo_medible + 1), 2021)
    assert res_minima["proyeccion_generada"] is False
    # Y la negacion no se atribuye al desempeno: no se midio, luego no se reprobo.
    motivo = " ".join(
        str(x) for x in (
            res_minima["resultado_horizonte_solicitado"].get("razon_principal"),
            res_minima.get("explicacion"),
        )
    ).lower()
    for palabra in ("rmse", "mape", "mase", "desempe"):
        assert palabra not in motivo, (palabra, motivo)


def test_reportes_con_y_sin_proyeccion() -> None:
    # Hermeticidad: salida en temporal, no en el repositorio.
    with tempfile.TemporaryDirectory(prefix="savip_prueba_") as tmp:
        _reportes_con_y_sin_proyeccion_en(Path(tmp))


def _reportes_con_y_sin_proyeccion_en(salida: Path) -> None:
    fila = pd.DataFrame([{"Codigo": "demo", "Nombre": "Serie sintética"}])

    con_proyeccion = ejecutar_proyeccion(serie_suave_con_ruido(), 2027, 12, 2021)
    assert con_proyeccion["proyeccion_generada"] is True
    # CIERRE 08-08-2026: el caso «sin proyeccion» ya no lo produce una serie
    # erratica -eso ahora se entrega con su incertidumbre-, sino una serie
    # demasiado corta, que es una imposibilidad real de calculo.
    #
    # P0-G, 16-08-2026: el objetivo se DERIVA de la cota de existencia en vez de
    # fijarse a mano. Antes se pedia 2022-01 sobre una serie de diez
    # observaciones -h=3-, que se negaba por reunir menos de tres ventanas; ese
    # corte se retiro y h=3 hoy se entrega. El primer horizonte sin dato es el
    # que deja CERO ventanas, y es el que este informe debe retratar.
    corta = serie_pocos_datos()
    sin_dato = min(h for h in range(1, len(corta)) if _pares_disponibles(len(corta), h) < 1)
    sin_proyeccion = ejecutar_proyeccion(corta, *_objetivo(corta, sin_dato), 2021)
    assert sin_proyeccion["proyeccion_generada"] is False, sin_proyeccion.get("explicacion")

    for nombre, resultado, serie in (
        ("con_proyeccion", con_proyeccion, serie_suave_con_ruido()),
        ("sin_proyeccion", sin_proyeccion, serie_pocos_datos()),
    ):
        pdf = generar_reporte_pdf(
            salida / f"prueba_gradual_{nombre}.pdf",
            "prueba",
            "sintetico.xlsx",
            {},
            {"anio": 2027, "mes": 12},
            [{"nivel": "Grupo CPC", "valor": nombre}],
            "T_16",
            fila,
            serie,
            resultado,
            [],
        )
        docx = generar_reporte_proyeccion(
            salida / f"prueba_gradual_{nombre}.docx",
            "prueba",
            "sintetico.xlsx",
            {},
            {"anio": 2027, "mes": 12},
            [{"nivel": "Grupo CPC", "valor": nombre}],
            "T_16",
            fila,
            serie,
            resultado,
            [],
        )
        assert pdf.exists() and pdf.stat().st_size > 10_000
        assert docx.exists() and docx.stat().st_size > 10_000


def main() -> None:
    test_drift_superior_permite_proyeccion_corta()
    test_dw_bajo_no_bloquea_globalmente_si_hay_backtesting_aceptable()
    test_fechas_criticas_bloquean()
    test_pocos_datos_entrega_el_punto_con_evidencia_limitada()
    test_intervalos_amplios_no_bloquean_ni_degradan_por_si_solos()
    test_serie_erratica_se_entrega_con_su_incertidumbre()
    test_los_vetos_retirados_no_vuelven_a_bloquear()
    test_reportes_con_y_sin_proyeccion()
    print("Pruebas de factibilidad gradual completadas.")


if __name__ == "__main__":
    main()
