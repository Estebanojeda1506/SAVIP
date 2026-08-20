from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app_icociv.proyeccion.servicio_proyeccion import (
    _estructurar_resultado_horizontes,
    _horizontes_evaluacion,
    determinar_horizonte_maximo_estadistico,
    ejecutar_proyeccion,
    validar_horizonte_solicitado,
)
from app_icociv.interfaz.presentacion_resultados import construir_html_explicacion_tarjeta
from app_icociv.reportes.generador_reportes import _lineas_determinacion_horizonte


def _evaluacion(h: int, estado: str) -> dict:
    tecnico = estado == "tecnico"
    escenario = estado == "escenario"
    return {
        "horizonte": h,
        "permitido": tecnico or escenario,
        "permitido_para_proyeccion_tecnica": tecnico,
        "permitido_como_escenario": tecnico or escenario,
        "no_recomendable": estado == "no_viable",
        "clasificacion": (
            "tecnica_cautela"
            if tecnico
            else "escenario_alta_incertidumbre"
            if escenario
            else "no_viable"
        ),
        "estado": "Proyección técnica" if tecnico else "Escenario de alta incertidumbre" if escenario else "No recomendable",
        "decision": "Permitido" if tecnico else "Permitido solo como escenario" if escenario else "No recomendable",
        "confianza": "medio" if tecnico else "bajo" if escenario else "no recomendable",
        "modelo_evaluado": "Drift",
        "rmse": 1.0,
        "mae": 0.8,
        "mape": 1.2,
        "smape": 1.1,
        "mase": 0.9,
        "ancho_relativo_95": 0.12,
        "errores_extremos": 0.0,
        "iteraciones": 8,
        "razon_decision": f"Decisión técnica para h={h}.",
    }


def _resultado(
    solicitado: int,
    *,
    tecnico_hasta: int,
    escenario_hasta: int,
    primer_no_viable: int,
    generado: bool,
    origen: str,
) -> dict:
    evaluaciones = [
        _evaluacion(h, "tecnico" if h <= tecnico_hasta else "escenario" if h <= escenario_hasta else "no_viable")
        for h in range(1, primer_no_viable + 1)
    ]
    no_evaluados = list(range(primer_no_viable + 1, solicitado + 1)) if solicitado > primer_no_viable else []
    base = {
        "proyeccion_generada": generado,
        "horizonte_solicitado": solicitado,
        "horizonte_permitido": solicitado if generado else 0,
        "periodo_proj": "2027_1",
        "model_name": "Drift",
        "y_proj": 141.1141,
        "ci80_lo": 137.8177,
        "ci80_hi": 143.4190,
        "ci95_lo": 136.9817,
        "ci95_hi": 143.6982,
        "factibilidad": {"nivel_confianza_metodologica": "medio", "razones_tecnicas": []},
        "horizonte_info": {
            "horizonte_solicitado": solicitado,
            "horizontes_evaluados": list(range(1, primer_no_viable + 1)),
            "horizonte_maximo_recomendado": tecnico_hasta,
            "horizonte_maximo_permitido_como_escenario": (
                escenario_hasta if escenario_hasta > tecnico_hasta else 0
            ),
            "horizonte_maximo_admisible": escenario_hasta,
            "horizonte_maximo_permitido": escenario_hasta,
            "primer_horizonte_no_viable": primer_no_viable,
            "horizontes_no_recomendables": [primer_no_viable],
            "horizontes_no_evaluados": no_evaluados,
            "evaluaciones": evaluaciones,
        },
    }
    return _estructurar_resultado_horizontes(base, origen)


def test_predeterminado_admisible_centra_h12_y_conserva_tabla_completa() -> None:
    resultado = _resultado(12, tecnico_hasta=12, escenario_hasta=18, primer_no_viable=19, generado=True, origen="predeterminado")
    principal = resultado["resultado_horizonte_solicitado"]
    assert principal["horizonte_solicitado"] == 12
    assert principal["origen_horizonte"] == "predeterminado"
    assert principal["estado"] == "proyeccion_tecnica"
    assert principal["indice_proyectado"] == 141.1141
    assert [fila["horizonte"] for fila in resultado["analisis_horizontes_completo"]["tabla_horizontes"]] == list(range(1, 20))


def test_manual_admisible_identifica_origen_y_h7() -> None:
    principal = _resultado(7, tecnico_hasta=12, escenario_hasta=18, primer_no_viable=19, generado=True, origen="manual")[
        "resultado_horizonte_solicitado"
    ]
    assert principal["horizonte_solicitado"] == 7
    assert principal["origen_horizonte"] == "manual"
    assert principal["estado"] == "proyeccion_tecnica"


def test_no_admisible_nunca_se_llama_proyeccion_tecnica() -> None:
    """post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 4
    de auditoria). Bajo la metodologia rectangular N0=12/H=24,
    `_estructurar_resultado_horizontes` ya no deriva `estado` de una
    clasificacion por horizonte ("tecnico"/"escenario"/"no_viable"): lo toma
    directamente del binario `proyeccion_generada` que entrega el motor
    (H-4 residual). La version anterior de esta prueba forzaba
    `generado=True` junto con banderas sinteticas de "solo escenario"
    esperando un tercer estado que ya no existe; con `generado=True` el
    resultado real y correcto es "proyeccion_tecnica" (no hay bug: la
    prueba asumia una rama retirada). La garantia vigente y equivalente es
    mas simple: `generado=False` nunca produce "proyeccion_tecnica"."""
    for solicitado, origen in ((18, "predeterminado"), (15, "manual")):
        principal = _resultado(
            solicitado,
            tecnico_hasta=12,
            escenario_hasta=18,
            primer_no_viable=19,
            generado=False,
            origen=origen,
        )["resultado_horizonte_solicitado"]
        assert principal["estado"] != "proyeccion_tecnica"
        assert principal["estado"] == "no_admisible"
        assert principal["accion"] == "negar"
        assert "advertencia" not in principal

    # Y el complemento: generado=True siempre produce "proyeccion_tecnica",
    # sin importar las banderas por-horizonte sinteticas (ya no gobiernan
    # nada bajo la metodologia rectangular vigente).
    for solicitado, origen in ((18, "predeterminado"), (15, "manual")):
        principal = _resultado(
            solicitado,
            tecnico_hasta=12,
            escenario_hasta=18,
            primer_no_viable=19,
            generado=True,
            origen=origen,
        )["resultado_horizonte_solicitado"]
        assert principal["estado"] == "proyeccion_tecnica"
        assert principal["accion"] == "permitir"


def test_h32_no_admisible_no_expone_proyeccion_y_marca_no_evaluados() -> None:
    resultado = _resultado(32, tecnico_hasta=10, escenario_hasta=14, primer_no_viable=15, generado=False, origen="manual")
    principal = resultado["resultado_horizonte_solicitado"]
    analisis = resultado["analisis_horizontes_completo"]
    assert principal["estado"] == "no_admisible"
    assert principal["proyeccion_generada"] is False
    assert principal["indice_proyectado"] is None
    assert principal["ic80"] is None and principal["ic95"] is None
    assert analisis["horizonte_maximo_recomendado"] == 10
    assert analisis["horizonte_maximo_permitido_como_escenario"] == 14
    assert analisis["primer_horizonte_no_viable"] == 15
    assert analisis["tabla_horizontes"][-1]["estado"] == "No evaluado"


def test_restriccion_no_hace_pasar_h12_como_resultado_de_h18() -> None:
    principal = _resultado(18, tecnico_hasta=12, escenario_hasta=12, primer_no_viable=13, generado=False, origen="predeterminado")[
        "resultado_horizonte_solicitado"
    ]
    assert principal["horizonte_solicitado"] == 18
    assert principal["proyeccion_generada"] is False
    assert principal["periodo_proyectado"] is None
    assert principal["modelo_aplicado"] is None


def test_horizonte_manual_invalido() -> None:
    # post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 4
    # de auditoria). Desde el Prompt 13, `validar_horizonte_solicitado`
    # distingue DOS causas de rechazo con mensajes distintos: "no es un
    # entero positivo" (no numerico, cero, negativo, no entero) frente a
    # "es un entero positivo pero excede el alcance 1..24" (25 en adelante).
    # Esta prueba comprobaba un unico mensaje para ambos casos; se separa
    # segun la semantica vigente.
    for valor in ("", "texto", 0, -1, 1.5, None):
        try:
            validar_horizonte_solicitado(valor)
        except ValueError as exc:
            assert "entero positivo" in str(exc)
        else:
            raise AssertionError(f"Se aceptó un horizonte inválido: {valor!r}")
    for valor in (25, 45, 61):
        try:
            validar_horizonte_solicitado(valor)
        except ValueError as exc:
            assert "1 y 24 meses" in str(exc)
            assert "entero positivo" not in str(exc)
        else:
            raise AssertionError(f"Se aceptó un horizonte fuera de alcance: {valor!r}")


def test_evaluacion_es_mensual_continua() -> None:
    horizontes = _horizontes_evaluacion(12, 61)
    assert horizontes[:12] == tuple(range(1, 13))


def test_h45_se_rechaza_explicitamente_h12_se_genera_normalmente() -> None:
    """post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 4
    de auditoria). Bajo la metodologia vigente H_OPERATIVO_MAX=24: h=45 no
    es un horizonte "generado con auditoria global comparable" (esa nocion
    triangular ya no existe), es un horizonte QUE NO SE PUEDE SOLICITAR. La
    prueba anterior llamaba `ejecutar_proyeccion` con un objetivo a 45 meses
    esperando que generara resultado; hoy eso viola 1<=h<=24 y debe
    rechazarse explicitamente antes de intentar generar nada. h=12, sobre la
    misma serie, sigue funcionando con normalidad."""
    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(61)]
    serie = pd.DataFrame(
        {"Periodo": periodos, "Indice": [100 + 0.25 * i + 0.02 * ((i % 7) - 3) for i in range(61)]}
    )
    # Ultimo periodo de la serie: 2021 + 60//12 = 2026, mes 60%12+1 = 1 -> 2026_1.
    # 2027_1 = 12 meses despues (h=12, valido). 2029_10 = 45 meses despues (h=45, invalido).
    h12 = ejecutar_proyeccion(serie, 2027, 1, 2021, origen_horizonte="predeterminado")
    assert h12["resultado_horizonte_solicitado"]["horizonte_solicitado"] == 12
    assert h12["resultado_horizonte_solicitado"]["proyeccion_generada"] is True
    assert h12["resultado_horizonte_solicitado"]["estado"] == "proyeccion_tecnica"

    try:
        ejecutar_proyeccion(serie, 2029, 10, 2021, origen_horizonte="manual")
    except ValueError as exc:
        assert "1 y 24 meses" in str(exc)
    else:
        raise AssertionError("h=45 debio rechazarse explicitamente (H_OPERATIVO_MAX=24)")


def test_maximos_se_derivan_de_clasificaciones_y_no_del_limite_de_grilla() -> None:
    evaluaciones = [
        _evaluacion(h, "tecnico" if h <= 8 else "escenario" if h <= 11 else "no_viable")
        for h in range(1, 13)
    ]
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        evaluaciones,
        None,
        horizonte_solicitado=12,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 20,
            "horizonte_maximo_evaluable_por_datos": 12,
        },
    )
    assert info["horizonte_maximo_recomendado"] == 8
    assert info["horizonte_maximo_permitido_como_escenario"] == 11
    assert info["horizonte_maximo_evaluado"] == 12
    assert info["primer_horizonte_no_viable"] == 12
    assert info["horizonte_maximo"] == 8


def test_limite_evaluable_se_informa_sin_convertirlo_en_validez_absoluta() -> None:
    evaluaciones = [_evaluacion(h, "tecnico") for h in range(1, 6)]
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        evaluaciones,
        None,
        horizonte_solicitado=12,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 10,
            "horizonte_maximo_evaluable_por_datos": 5,
        },
    )
    assert info["horizonte_maximo_recomendado"] == 5
    assert info["horizonte_maximo_evaluado"] == 5
    assert info["horizonte_maximo_busqueda_configurado"] == 10
    assert info["maximo_recomendado_es_limite_observado"] is True
    assert info["primer_horizonte_no_viable"] == 0
    assert info["tipo_parada"] == "evidencia_oos_insuficiente"
    assert info["horizontes_no_evaluados"] == [6, 7, 8, 9, 10]


def test_maximo_evaluado_20_es_descriptivo_de_la_funcion_retirada() -> None:
    """post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 4
    de auditoria). `determinar_horizonte_maximo_estadistico` sigue definida
    (funcion muerta: no la llama ningun camino productivo, ver comentarios
    en analisis_series.py y presentacion_resultados.py), y esta prueba
    conserva la comprobacion de sus propios campos, igual que sus 5
    hermanas en este archivo. Lo que se retira es la comparacion contra
    `construir_html_explicacion_tarjeta("maximo", ...)` y
    `_lineas_determinacion_horizonte(...)`: esas dos funciones de UI/reporte
    ya NO leen esta estructura triangular (leen `horizonte_info` rectangular
    real, ver test_maximo_tarjeta_usa_alcance_operativo_vigente abajo), asi
    que comparar sus textos contra vocabulario "horizonte maximo
    recomendado" prueba una integracion que ya no existe."""
    evaluaciones = [_evaluacion(h, "tecnico") for h in range(1, 14)]
    for h in range(14, 21):
        fila = _evaluacion(h, "no_viable")
        fila.update(
            {
                "permitido": False,
                "permitido_como_escenario": False,
                "no_recomendable": False,
                "clasificacion": "evidencia_insuficiente",
                "estado": "Evidencia insuficiente",
                "decision": "No determinado",
            }
        )
        evaluaciones.append(fila)
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        evaluaciones,
        None,
        horizonte_solicitado=24,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 30,
            "horizonte_maximo_evaluable_por_datos": 20,
        },
    )
    assert info["horizonte_maximo_evaluado"] == 20
    assert info["horizonte_maximo_recomendado"] == 13
    assert info["horizonte_maximo_permitido_como_escenario"] == 0
    assert info["maximo_recomendado_es_limite_observado"] is False


def test_maximo_tarjeta_usa_alcance_operativo_vigente() -> None:
    """post-r1-metodologia-12-24, 20-08-2026 (Prompt Calendario 06, hallazgo 4
    de auditoria). Reemplazo de semantica vigente para la parte de la
    prueba anterior que verificaba el contenido de la tarjeta "maximo": bajo
    N0=12/H=24 esa tarjeta muestra el alcance operativo fijo (24 meses), W*
    y el candidato/RMSE de seleccion, no un "horizonte maximo recomendado"
    triangular. Tambien confirma que los nombres de candidato llegan
    traducidos (hallazgo 1 de esta misma auditoria), no como
    "fourier_k1__...".
    """
    resultado = {
        "proyeccion": {
            "horizonte_info": {
                "alcance_maximo_proyeccion": 24,
                "w_estrella": 30,
                "modelo_seleccionado": "fourier_k1__holt_amortiguado",
                "rmse_seleccion_oos": 4.34,
                "modelo_segundo": "fourier_k1__drift",
                "diferencia_porcentual_segundo": 12.5,
            },
            "resultado_horizonte_solicitado": {"horizonte_solicitado": 12},
        }
    }
    html = construir_html_explicacion_tarjeta("maximo", resultado, "claro")
    assert "Alcance máximo de proyección de SAVIP" in html
    assert "24 meses" in html
    assert "Fourier K=1 + Holt tendencia amortiguada" in html
    assert "Fourier K=1 + Drift" in html
    assert "fourier_k1__" not in html
    for retirado in ("horizonte máximo recomendado", "máximo estadístico", "escenario"):
        assert retirado not in html.lower()


def test_20_puede_ser_maximo_recomendado_si_h20_es_tecnico() -> None:
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        [_evaluacion(h, "tecnico") for h in range(1, 21)],
        None,
        horizonte_solicitado=20,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 20,
            "horizonte_maximo_evaluable_por_datos": 20,
        },
    )
    assert info["horizonte_maximo_recomendado"] == 20
    assert info["horizonte_maximo_permitido_como_escenario"] == 0
    assert info["evidencia_horizonte_maximo_recomendado"]["horizonte"] == 20
    assert info["evidencia_horizonte_maximo_recomendado"]["clasificacion"] == "tecnica_cautela"


def test_20_puede_ser_maximo_escenario_si_h20_es_escenario_explicito() -> None:
    evaluaciones = [
        _evaluacion(h, "tecnico" if h <= 12 else "escenario")
        for h in range(1, 21)
    ]
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        evaluaciones,
        None,
        horizonte_solicitado=20,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 20,
            "horizonte_maximo_evaluable_por_datos": 20,
        },
    )
    assert info["horizonte_maximo_recomendado"] == 12
    assert info["horizonte_maximo_permitido_como_escenario"] == 20
    assert info["horizonte_maximo_admisible"] == 20
    assert info["evidencia_horizonte_maximo_escenario"]["horizonte"] == 20
    assert info["evidencia_horizonte_maximo_escenario"]["clasificacion"] == "escenario_alta_incertidumbre"


def test_parada_en_20_por_evidencia_incluye_advertencia_y_no_extrapola() -> None:
    evaluaciones = [_evaluacion(h, "tecnico") for h in range(1, 11)]
    for h in range(11, 21):
        fila = _evaluacion(h, "no_viable")
        fila.update(
            {
                "permitido": False,
                "permitido_como_escenario": False,
                "no_recomendable": False,
                "clasificacion": "evidencia_insuficiente",
            }
        )
        evaluaciones.append(fila)
    info = determinar_horizonte_maximo_estadistico(
        None,
        None,
        None,
        evaluaciones,
        None,
        horizonte_solicitado=30,
        metadatos_auditoria={
            "horizonte_maximo_busqueda_configurado": 30,
            "horizonte_maximo_evaluable_por_datos": 20,
        },
    )
    assert info["horizonte_maximo_evaluado"] == 20
    assert info["horizonte_maximo_recomendado"] == 10
    assert info["horizonte_maximo_permitido_como_escenario"] == 0
    assert info["primer_horizonte_no_viable"] == 0
    assert info["tipo_parada"] == "evidencia_oos_insuficiente"
    assert "no se puede afirmar validez para horizontes superiores" in info[
        "advertencia_metodologica_horizontes"
    ]


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
    print("Pruebas de resultado del horizonte solicitado OK")
