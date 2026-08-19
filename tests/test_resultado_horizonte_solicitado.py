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


def test_horizonte_solo_escenario_no_se_llama_proyeccion_tecnica() -> None:
    """H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual).
    El estado intermedio "escenario" se retiro de
    `_estructurar_resultado_horizontes`: con el evaluador real,
    `permitido_como_escenario == permitido_para_proyeccion_tecnica` siempre
    (ver su comentario H-4 residual), de modo que esa rama nunca se
    ejecutaba. Este test sigue forzando con datos sinteticos la combinacion
    permitido_como_escenario=True / permitido_para_proyeccion_tecnica=False
    -que no ocurre con datos reales, pero que la funcion todavia acepta como
    entrada- para verificar la garantia que le da nombre al test: un
    horizonte que no es tecnico nunca se etiqueta como "proyeccion_tecnica".
    Hoy esa garantia se cumple devolviendo "no_admisible" en lugar del
    estado retirado."""
    for solicitado, origen in ((18, "predeterminado"), (15, "manual")):
        principal = _resultado(
            solicitado,
            tecnico_hasta=12,
            escenario_hasta=18,
            primer_no_viable=19,
            generado=True,
            origen=origen,
        )["resultado_horizonte_solicitado"]
        assert principal["estado"] != "proyeccion_tecnica"
        assert principal["estado"] == "no_admisible"
        assert principal["accion"] == "negar"
        assert "advertencia" not in principal


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
    for valor in ("", "texto", 0, -1, 1.5, None, 61):
        try:
            validar_horizonte_solicitado(valor)
        except ValueError as exc:
            assert "entero positivo" in str(exc)
        else:
            raise AssertionError(f"Se aceptó un horizonte inválido: {valor!r}")


def test_evaluacion_es_mensual_continua() -> None:
    horizontes = _horizontes_evaluacion(12, 61)
    assert horizontes[:12] == tuple(range(1, 13))


def test_misma_serie_h12_y_h45_conserva_auditoria_global() -> None:
    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(61)]
    serie = pd.DataFrame(
        {"Periodo": periodos, "Indice": [100 + 0.25 * i + 0.02 * ((i % 7) - 3) for i in range(61)]}
    )
    h12 = ejecutar_proyeccion(serie, 2027, 1, 2021, origen_horizonte="predeterminado")
    h45 = ejecutar_proyeccion(serie, 2029, 10, 2021, origen_horizonte="manual")
    a = h12["analisis_horizontes_completo"]
    b = h45["analisis_horizontes_completo"]
    for campo in (
        "horizontes_evaluados",
        "horizonte_maximo_recomendado",
        "horizonte_maximo_permitido_como_escenario",
        "primer_horizonte_no_viable",
        "horizontes_no_recomendables",
        "horizontes_no_evaluados",
        "razon_parada",
        "horizonte_maximo_evaluable_por_datos",
        "razones",
        "advertencias",
        "advertencias_por_horizonte",
        "mensaje",
        "mensaje_ui",
        "mensaje_informe",
    ):
        assert a[campo] == b[campo]
    claves = (
        "horizonte",
        "estado",
        "decision",
        "clasificacion",
        "permitido_para_proyeccion_tecnica",
        "permitido_como_escenario",
        "no_recomendable",
        "modelo_evaluado",
        "rmse",
        "mae",
        "mape",
        "smape",
        "mase",
        "ic95_relativo",
        "razon_decision",
    )
    assert [
        {clave: fila.get(clave) for clave in claves} for fila in a["tabla_horizontes"]
    ] == [
        {clave: fila.get(clave) for clave in claves} for fila in b["tabla_horizontes"]
    ]
    assert a["trazabilidad"]["firma_serie_sha256"] == b["trazabilidad"]["firma_serie_sha256"]
    assert h12["resultado_horizonte_solicitado"]["horizonte_solicitado"] == 12
    assert h45["resultado_horizonte_solicitado"]["horizonte_solicitado"] == 45


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


def test_maximo_evaluado_20_no_sustituye_recomendado_ni_escenario() -> None:
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
    resultado = {"horizonte_info": info, "analisis_horizontes_completo": info}
    html = construir_html_explicacion_tarjeta("maximo", resultado, "oscuro")
    informe = "\n".join(_lineas_determinacion_horizonte(resultado))

    assert info["horizonte_maximo_evaluado"] == 20
    assert info["horizonte_maximo_recomendado"] == 13
    assert info["horizonte_maximo_permitido_como_escenario"] == 0
    assert info["maximo_recomendado_es_limite_observado"] is False
    assert "13 meses" in html
    assert "20 meses" in html
    assert "No identificado" in html
    assert "no debe interpretarse como horizonte máximo recomendado" in informe


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
