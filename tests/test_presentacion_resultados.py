from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import re

import pandas as pd

# Bootstrap de ruta: esta suite era la unica que no lo tenia y por eso solo
# corria bajo pytest o con PYTHONPATH definido (hallazgo H-02).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.interfaz.presentacion_resultados import (
    construir_html_detalle_horizonte,
    construir_html_explicacion_tarjeta,
    construir_html_resultados,
    formatear_factor,
    formatear_indice,
    formatear_intervalo,
    formatear_porcentaje,
    valor_o_no_disponible,
)


def test_presentacion_resultados_muestra_tarjetas_y_tablas_clave() -> None:
    resultado = {
        "proyeccion_generada": True,
        "y_proj": 145.32,
        "periodo_proj": "2026-12",
        "model_name": "Drift",
        "horizonte_solicitado": 12,
        "horizonte_permitido": 12,
        "factor_actualizacion": 1.0832,
        "variacion_acumulada": 8.32,
        "parametros_modelo": {
            "primer_valor": 100.0,
            "ultimo_valor": 134.0,
            "n": 61,
            "pendiente_mensual": 0.566666,
        },
        "backtesting": {
            "iteraciones": 14,
            "metricas": {
                "rmse": 2.1,
                "mae": 1.8,
                "mape": 1.4,
                "smape": 1.39,
                "mase": 0.91,
                "sesgo_medio": 0.12,
                "estabilidad_error": 0.22,
                "porcentaje_errores_extremos": 0.0,
            },
        },
        "factibilidad": {
            "estado": "Proyección extendida con cautela",
            "nivel_confianza_metodologica": "Media",
        },
        "horizonte_info": {
            "tipo_uso_recomendado": "Proyección extendida con cautela",
            "horizonte_maximo_recomendado": 12,
            "horizonte_maximo_permitido_como_escenario": 12,
            "primer_horizonte_no_viable": 18,
            "horizontes_evaluados": [1, 3, 6, 12, 18],
            "horizontes_no_recomendables": [18],
            "accion": "Permitir con cautela",
            "evaluaciones": [
                {
                    "horizonte": 12,
                    "estado": "Proyección extendida con cautela",
                    "decision": "Permitido",
                    "rmse": 2.1,
                    "mape": 1.4,
                    "ancho_relativo_95": 0.12,
                    "modelo_final_aplicado": "Drift",
                }
            ],
        },
        "advertencias_categorizadas": {
            "advertencias_horizonte": ["Usar como escenario técnico, no como certeza."],
        },
        "proyecciones": pd.DataFrame(
            [
                {
                    "periodo": "2026-12",
                    "indice_proyectado": 145.32,
                    "factor_actualizacion": 1.0832,
                    "variacion_acumulada_pct": 8.32,
                    "variacion_pct_ultimo_observado": 8.32,
                    "limite_inferior_80": 141.0,
                    "limite_superior_80": 149.1,
                    "limite_inferior_95": 138.2,
                    "limite_superior_95": 152.8,
                    "ancho_relativo_95": 0.10,
                    "metodo_intervalo": "empirico_centrado",
                    "ventanas_oos_horizonte": 12,
                }
            ]
        ),
        "catalogo_modelos": [
            {
                "modelo": "Drift",
                "ejecutado": True,
                "rmse": 2.1,
                "mae": 1.8,
                "mape": 1.4,
                "smape": 1.39,
                "estado": "Seleccionado",
                "razon": "Menor error fuera de muestra.",
            }
        ],
    }

    html = construir_html_resultados(resultado)

    assert "Resultado del horizonte solicitado" in html
    assert "Índice proyectado" in html
    assert "Período proyectado" in html
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 13). Retirada la seccion
    # "Incertidumbre" (solo declaraba el intervalo retirado sin ocupar
    # utilmente el espacio, item 6 del Prompt 13). En su lugar: "Error
    # histórico de referencia (±MAE)", que muestra el MAE_h del horizonte
    # solicitado como referencia descriptiva, no como intervalo de confianza.
    assert "Error histórico de referencia" in html
    assert "±MAE" in html or "no constituye un intervalo de confianza" in html
    assert "Resumen de la metodología de proyección" in html or "Resumen del análisis dinámico de horizontes" in html
    assert "Parámetros del modelo seleccionado" in html
    assert "Criterios de selección del modelo" in html
    assert "Modelo aplicado" in html
    # La banda del 80 % y la del 95 % (IC80/IC95) siguen retiradas de toda
    # salida productiva (P0-C RUTA C2). Ninguna tarjeta ni seccion principal
    # debe invitar al usuario a buscarlas (Prompt 13, item 6).
    assert "IC80" not in html, "La banda del 80 % no puede volver a la interfaz"
    assert "q80" not in html, "q80 es diagnostico interno: no se expone"
    assert "IC95" not in html, "P0-C C2: el intervalo del 95 % ya no se publica"
    assert "Intervalo de predicción" not in html, "no debe quedar una tarjeta anunciando el intervalo retirado"
    # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12/13). Retirada la
    # semantica triangular (horizonte maximo recomendado/permitido como
    # escenario/primer horizonte no viable): SAVIP tiene un alcance operativo
    # fijo de 24 meses, no una clasificacion por horizonte.
    assert "Horizonte máximo recomendado" not in html
    assert "Horizonte máximo permitido como escenario" not in html
    assert "Primer horizonte no viable" not in html
    assert "Alcance máximo de proyección" in html
    assert "Advertencias principales" in html
    assert "Tabla de proyecciones" in html
    assert "Modelos evaluados" in html
    assert "Métricas principales" not in html
    assert "title=" not in html
    assert "None" not in html
    assert "nan" not in html.lower()
    assert ">inf<" not in html.lower()
    assert ">-inf<" not in html.lower()


def test_formateadores_ui_no_exponen_valores_crudos() -> None:
    assert formatear_indice(141.11414) == "141.1141"
    assert formatear_factor(1.0832349) == "1.083235"
    assert formatear_porcentaje(8.326) == "8.33%"
    assert formatear_porcentaje(0.1286, es_ratio=True) == "12.86%"
    assert formatear_intervalo(141.11414, 149.98765) == "[141.1141, 149.9877]"
    assert valor_o_no_disponible(None) == "No disponible"
    assert valor_o_no_disponible(float("nan")) == "No disponible"
    assert valor_o_no_disponible(float("inf")) == "No disponible"
    assert valor_o_no_disponible(pd.NA) == "No disponible"
    assert valor_o_no_disponible({"rmse": 1.2}) == "No disponible"


def test_presentacion_horizonte_restringido_es_explicita_y_segura() -> None:
    resultado = {
        "proyeccion_generada": True,
        "horizonte_solicitado": 18,
        "horizonte_permitido": 12,
        "model_name": "Drift",
        "parametros_modelo": {"pendiente_mensual": 0.25, "backend": "interno"},
        "factibilidad": {
            "estado": "Proyección con cautela",
            "nivel_confianza_metodologica": "medio",
        },
        "horizonte_info": {
            "horizonte_solicitado": 18,
            "horizonte_finalmente_permitido": 12,
            "horizonte_maximo_recomendado": 12,
            "horizonte_maximo_permitido_como_escenario": 12,
            "primer_horizonte_no_viable": 13,
            "horizontes_evaluados": list(range(1, 19)),
            "horizontes_no_recomendables": list(range(13, 19)),
            "accion": "restringir",
            "tipo_uso_recomendado": "Proyección extendida con cautela",
        },
        "proyecciones": pd.DataFrame(
            [
                {
                    "periodo": "2027_1",
                    "indice_proyectado": 141.11414,
                    "factor_actualizacion": 1.0832349,
                    "variacion_acumulada_pct": 8.326,
                    "variacion_pct_ultimo_observado": 8.326,
                    "limite_inferior_80": 138.0,
                    "limite_superior_80": 144.0,
                    "limite_inferior_95": 136.0,
                    "limite_superior_95": 146.0,
                    "ancho_relativo_95": 0.071,
                    "metodo_intervalo": "errores OOS de backtesting",
                    "ventanas_oos_horizonte": 12,
                }
            ]
        ),
        "backtesting": {
            "iteraciones": 12,
            "metricas": {
                "rmse": 1.2,
                "mae": 0.9,
                "mape": float("nan"),
                "smape": float("inf"),
                "mase": None,
                "sesgo_medio": 0.1,
                "estabilidad_error": 0.2,
                "porcentaje_errores_extremos": 0.0,
            },
        },
        "diagnostico_residuos": {"alertas": []},
        "criterio_seleccion": {},
    }

    html = construir_html_resultados(resultado)

    assert "Horizonte solicitado" in html
    assert "18 meses" in html
    assert "No generado" in html
    assert "No admisible" in html
    assert "backend" not in html.lower()
    assert ">None<" not in html
    assert ">nan<" not in html.lower()
    assert ">inf<" not in html.lower()
    assert ">{}<" not in html
    assert ">[]<" not in html


def test_presentacion_no_expone_ensambles() -> None:
    """El ensamble fue retirado del alcance: la interfaz no debe mostrarlo."""
    resultado = {
        "proyeccion_generada": True,
        "model_name": "Drift",
        "horizonte_solicitado": 12,
        "horizonte_permitido": 12,
        "componentes_ensamble": [{"nombre": "drift", "peso": 0.55}],
        "parametros_modelo": {"pendiente_mensual": 0.25},
    }

    html = construir_html_resultados(resultado)

    assert "ensamble" not in html.lower()
    assert "Componentes del ensamble" not in html
    assert "Método de ponderación" not in html
    assert "Modelo aplicado" in html or "Parámetros del modelo seleccionado" in html


def test_visor_resultados_no_tiene_tooltip_y_permite_scroll_horizontal_controlado() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QTextEdit
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    ventana = VentanaPrincipal()

    assert ventana.texto_resultados.toolTip() == ""
    assert ventana.texto_resultados.viewport().toolTip() == ""
    assert ventana.texto_resultados.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
    assert (
        ventana.texto_resultados.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    assert app is not None


def test_detalle_horizonte_separa_razones_largas_de_la_tabla() -> None:
    html = construir_html_detalle_horizonte(
        {
            "horizonte": 12,
            "estado": "Proyección técnica",
            "decision": "Permitido",
            "modelo_evaluado": "Drift",
            "razon_decision": "Razón técnica completa y legible.",
            "advertencias": ["Usar junto con el IC95."],
            "clasificacion": "tecnica_cautela",
            "rmse": 1.2,
            "mae": 0.9,
            "mape": 1.1,
            "smape": 1.0,
            "mase": 0.8,
            "ancho_relativo_95": 0.12,
            "iteraciones": 9,
        }
    )
    assert "Detalle del horizonte seleccionado" in html
    assert "Razón técnica completa y legible." in html
    assert "Usar junto con el IC95." in html
    assert "9" in html


def test_seis_tarjetas_tienen_explicaciones_especificas_y_sin_valores_crudos() -> None:
    resultado = {
        "resultado_horizonte_solicitado": {
            "horizonte_solicitado": 12,
            "origen_horizonte": "manual",
            "estado": "proyeccion_tecnica",
            "accion": "permitir",
            "proyeccion_generada": True,
            "indice_proyectado": 141.1,
            "periodo_proyectado": "2027_1",
            "modelo_aplicado": "Drift",
            # P0-C RUTA C2, 14-08-2026: el intervalo se retiro de las salidas. Ninguno de
            "razon_principal": "Evidencia suficiente.",
        },
        "analisis_horizontes_completo": {
            "horizonte_solicitado_cubierto": True,
            "horizonte_maximo_recomendado": 12,
            "horizonte_maximo_evaluado": 20,
            "horizonte_maximo_permitido_como_escenario": 0,
            "horizonte_maximo_busqueda_configurado": 30,
            "primer_horizonte_no_viable": 0,
            "razon_parada": "Evaluación detenida por evidencia OOS.",
            "advertencia_metodologica_horizontes": (
                "El máximo evaluado no sustituye la clasificación técnica ni de escenario."
            ),
            "tabla_horizontes": [{"horizonte": 12, "clasificacion": "tecnica_cautela"}],
        },
        "model_name": "Drift",
        "stats": {"modelos_evaluados": ["naive", "drift"]},
        "backtesting": {"iteraciones": 8, "metricas": {"rmse": 1.2, "mae": 0.9, "mape": 1.1}},
        "proyecciones": pd.DataFrame(
            [{"metodo_intervalo": "errores OOS", "ventanas_oos_horizonte": 8, "ancho_relativo_95": 0.08}]
        ),
    }
    esperados = {
        "indice": "Explicación del índice proyectado",
        # post-r1-metodologia-12-24, 19-08-2026 (Prompt 12/13). Retirada la
        # semantica triangular ("Diferencia clave" entre solicitado/
        # recomendado/evaluado); ahora describe el alcance operativo fijo.
        "horizonte": "Alcance máximo de proyección de SAVIP",
        "modelo": "Cómo se seleccionó el modelo",
        "estado": "Interpretación",
        # C2: la tarjeta de intervalo se retiro de la interfaz; "maximo"
        # explica ahora el alcance operativo y la seleccion por RMSE OOS.
        "maximo": "RMSE OOS usado en la selección",
    }
    for clave, texto in esperados.items():
        html = construir_html_explicacion_tarjeta(clave, resultado, "oscuro")
        assert texto in html
        assert ">None<" not in html
        assert ">nan<" not in html.lower()
        assert ">{}<" not in html


def test_modo_oscuro_cambia_ui_grafica_html_y_persiste_preferencia() -> None:
    import os
    from tempfile import TemporaryDirectory

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings, Qt, QUrl
    from PySide6.QtWidgets import QApplication, QPushButton, QTextBrowser
    from app_icociv.interfaz.ventana_principal import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    ventana = VentanaPrincipal()
    with TemporaryDirectory() as carpeta:
        preferencias = QSettings(str(Path(carpeta) / "preferencias.ini"), QSettings.Format.IniFormat)
        ventana.preferencias = preferencias
        ventana._aplicar_tema("oscuro")
        assert ventana.tema_actual == "oscuro"
        assert ventana.accion_modo_oscuro.isChecked()
        assert preferencias.value("tema") == "oscuro"
        # El tema se resuelve desde app_icociv/interfaz/tema/colores.py. Se
        # comprueba contra el token, no contra un hexadecimal escrito a mano:
        # eso fue lo que dejo esta prueba obsoleta al cambiar la paleta.
        from app_icociv.interfaz.tema.colores import CLARO, OSCURO

        hoja = ventana.styleSheet()
        assert OSCURO["fondo"] in hoja, "La hoja debe usar el fondo del tema oscuro"
        assert CLARO["fondo"] not in hoja, "No debe quedar color del tema claro"
        assert OSCURO["superficie"] in construir_html_resultados({}, "oscuro")
        assert len(ventana.valores_kpi) == 6
        assert len(ventana.tarjetas_kpi) == 6
        # Se comprueba por nombre y no por cantidad: contar botones dejaba la
        # prueba obsoleta cada vez que se anadia una pantalla.
        etiquetas = [boton.text() for boton in ventana.botones_navegacion]
        assert etiquetas == ["Inicio", "Resultados", "Proyecciones ICOCIV", "Empalme ICCP-ICOCIV"], etiquetas
        # La cabecera conserva el selector unico de exportacion (DOCX/PDF/CSV).
        assert ventana.acciones_cabecera.count() == 1
        assert ventana.acciones_cabecera.itemAt(0).widget() is ventana.boton_exportar_informe
        # El boton vive en la navegacion lateral, no en la cabecera. Se
        # comprueba por ascendencia: exigir un padre directo concreto rompia
        # la prueba cada vez que se reorganizaba el arbol de widgets.
        assert ventana.navegacion.isAncestorOf(ventana.boton_guardar_sesion), (
            "Guardar sesion debe estar en la navegacion lateral"
        )
        assert not ventana.acciones_cabecera.indexOf(ventana.boton_guardar_sesion) >= 0
        assert not hasattr(ventana, "detalle_horizonte")
        capturas = []
        ventana._mostrar_explicacion_tarjeta = lambda clave: capturas.append(clave)
        for clave, tarjeta in ventana.tarjetas_kpi.items():
            assert tarjeta.cursor().shape() == Qt.CursorShape.PointingHandCursor
            assert tarjeta.focusPolicy() == Qt.FocusPolicy.StrongFocus
            tarjeta.clicked.emit()
            assert capturas[-1] == clave
        dialogo = ventana._crear_dialogo_explicacion(
            "Detalle de prueba",
            construir_html_detalle_horizonte({"horizonte": 12, "estado": "Proyección técnica"}, "oscuro"),
        )
        assert dialogo.isModal()
        assert dialogo.minimumWidth() >= 620
        assert dialogo.findChild(QTextBrowser, "visor_explicacion") is not None
        assert dialogo.findChild(QPushButton, "boton_cerrar_dialogo") is not None
        ventana.detalles_horizonte = {12: {"horizonte": 12, "estado": "Proyección técnica"}}
        modales = []
        ventana._mostrar_modal_explicacion = lambda titulo, html: modales.append((titulo, html))
        ventana._mostrar_detalle_horizonte(QUrl("detalle-horizonte:12"))
        assert modales and "h=12" in modales[-1][0]
        assert "Detalle del horizonte seleccionado" in modales[-1][1]
        ventana._aplicar_tema("claro")
        assert preferencias.value("tema") == "claro"
        assert not ventana.accion_modo_oscuro.isChecked()
    ventana.close()
    assert app is not None


def test_exportable_diferencia_recomendado_evaluado_y_limite_operativo() -> None:
    from app_icociv.reportes.generador_reportes import construir_dataframe_reproducibilidad

    salida = construir_dataframe_reproducibilidad(
        pd.DataFrame([{"Periodo": "2026_1", "Indice": 120.0}]),
        {
            "horizonte_solicitado": 45,
            "horizonte_permitido": 0,
            "proyeccion_generada": False,
            "analisis_horizontes_completo": {
                "horizonte_maximo_recomendado": 12,
                "horizonte_maximo_evaluado": 20,
                "horizonte_maximo_evaluable_por_datos": 20,
                "horizonte_maximo_busqueda_configurado": 30,
                "razon_parada": "Evaluación detenida por falta de evidencia OOS suficiente.",
                "trazabilidad": {"firma_serie_sha256": "abc", "version_criterios": "v2"},
            },
        },
    )
    fila = salida.iloc[0]
    assert fila["horizonte_maximo_recomendado"] == 12
    assert fila["horizonte_maximo_evaluado"] == 20
    assert fila["limite_operativo_auditoria"] == 30
    assert fila["razon_parada_horizontes"].startswith("Evaluación detenida")


def _evaluacion_horizonte_ui(
    horizonte: int,
    *,
    tecnico: bool = True,
    escenario: bool = True,
    no_recomendable: bool = False,
) -> dict:
    permitido = tecnico or escenario
    return {
        "horizonte": horizonte,
        "permitido": permitido,
        "permitido_para_proyeccion_tecnica": tecnico,
        "permitido_como_escenario": escenario,
        "no_recomendable": no_recomendable,
        "estado": (
            "No recomendable"
            if no_recomendable
            else "Escenario de alta incertidumbre"
            if escenario and not tecnico
            else "Proyección extendida con cautela"
        ),
        "decision": "No recomendable" if no_recomendable else "Permitido",
        "clasificacion": (
            "no_viable"
            if no_recomendable
            else "escenario_alta_incertidumbre"
            if escenario and not tecnico
            else "extendida_cautela"
        ),
        "tipo_uso": "Escenario estadístico extendido" if horizonte >= 13 else "Proyección extendida con cautela",
        "modelo": {"nombre": "drift", "nombre_visible": "Drift"},
        "backtesting": {
            "iteraciones": 8,
            "metricas": {
                "rmse": 1.0 + horizonte / 10,
                "mae": 0.8 + horizonte / 12,
                "mape": 1.2,
                "smape": 1.1,
                "mase": 0.9,
            },
        },
        "evaluacion_intervalos": {
            "ancho_relativo_95_maximo": 0.12 if horizonte <= 12 else 0.32,
        },
        "mensaje_horizonte": "Evidencia evaluada para este horizonte.",
    }


def test_horizonte_dinamico_diferencia_tecnico_cautela_y_no_evaluado() -> None:
    """H-4 residual, 18-08-2026 (reauditoria dirigida V-CODEX-R2 residual).
    Renombrada y reescrita: el nombre y la ultima asercion original
    describian una tercera salida "permitir como escenario" que el
    evaluador real nunca produce (`permitido_como_escenario ==
    permitido_para_proyeccion_tecnica` siempre) y que se retiro tambien de
    `determinar_horizonte_maximo_estadistico`. Con datos sinteticos que
    fuerzan `permitido_como_escenario=True, permitido_para_proyeccion_
    tecnica=False` -combinacion que ya no ocurre con datos reales, pero que
    esta funcion sigue aceptando como entrada-, la accion resultante es
    ahora "permitir con cautela": una etiqueta generica y honesta, no la
    etiqueta de estado retirada."""
    from app_icociv.proyeccion.servicio_proyeccion import determinar_horizonte_maximo_estadistico

    evaluaciones = [
        _evaluacion_horizonte_ui(h)
        if h <= 12
        else _evaluacion_horizonte_ui(h, tecnico=False, escenario=True)
        for h in range(1, 19)
    ]
    info = determinar_horizonte_maximo_estadistico(
        None, None, None, evaluaciones, None, horizonte_solicitado=18
    )

    assert info["horizonte_maximo_recomendado"] == 12
    assert info["horizonte_maximo_permitido_como_escenario"] == 18
    assert info["horizonte_finalmente_permitido"] == 18
    assert info["accion"] == "permitir con cautela"
    assert info["primer_horizonte_no_viable"] == 0

    sin_h18 = determinar_horizonte_maximo_estadistico(
        None, None, None, evaluaciones[:12], None, horizonte_solicitado=18
    )
    assert sin_h18["horizonte_maximo_recomendado"] == 12
    assert sin_h18["horizonte_maximo_permitido_como_escenario"] == 0
    assert sin_h18["horizonte_maximo_admisible"] == 12
    assert 18 in sin_h18["horizontes_no_evaluados"]
    assert sin_h18["accion"] == "restringir"
    assert sin_h18["horizonte_finalmente_permitido"] == 12


def test_horizonte_no_salta_un_corte_no_viable() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import determinar_horizonte_maximo_estadistico

    evaluaciones = [
        _evaluacion_horizonte_ui(1),
        _evaluacion_horizonte_ui(2, tecnico=False, escenario=False, no_recomendable=True),
        _evaluacion_horizonte_ui(3),
        _evaluacion_horizonte_ui(4),
    ]
    info = determinar_horizonte_maximo_estadistico(
        None, None, None, evaluaciones, None, horizonte_solicitado=12
    )

    # P0-H, 16-08-2026 (V-CODEX-3). Antes se exigia que un corte no viable en
    # h=2 restringiera todo a h=1: el prefijo consecutivo. La auditoria
    # independiente lo marco como regla decisoria CRITICA sin fuente. Ninguna
    # referencia exige que los horizontes validos formen un prefijo continuo:
    # FPP3 5.10 publica UNA TABLA POR HORIZONTE y cada h tiene su propia muestra
    # de errores, de modo que el desempeno en h=2 no es evidencia sobre h=3.
    #
    # El contrato nuevo: cada horizonte se juzga con su evidencia propia. Lo que
    # NO cambia es que el hueco se siga informando -`primer_horizonte_no_viable`
    # lo localiza- ni que h=2 siga marcado como no permitido.
    assert info["horizonte_maximo_recomendado"] == 4
    assert info["horizonte_maximo_admisible"] == 4
    assert info["primer_horizonte_no_viable"] == 2, "el hueco debe seguir informandose"
    assert info["horizonte_finalmente_permitido"] == 4
    assert info["accion"] != "bloquear"
    # Y el horizonte no viable no se convierte en permitido por el cambio.
    estados = {int(e["horizonte"]): e for e in evaluaciones}
    assert estados[2].get("permitido_para_proyeccion_tecnica") is False
    assert estados[2].get("permitido_como_escenario") is False


def test_iteraciones_insuficientes_limitan_el_intervalo_no_el_horizonte() -> None:
    """P0-G REABIERTO, 14-08-2026. Antes exigia que una sola ventana NO RECOMENDARA.

    Es la misma regla sin fuente que la revision independiente marco como critica
    (R02): el punto se calcula del ajuste del modelo y no depende del numero de
    ventanas. Las ventanas hacen falta para construir y evaluar el INTERVALO, y
    ahi el piso sigue vigente. Lo que se comprueba ahora es que el horizonte no se
    cancele y que la carencia se comunique.
    """
    from app_icociv.proyeccion.servicio_proyeccion import _clasificar_evidencia_horizonte

    evidencia = _clasificar_evidencia_horizonte(
        horizonte=12,
        modelo={
            "nombre": "drift",
            "nombre_visible": "Drift",
            "es_benchmark": True,
            "comparacion_benchmarks": {},
        },
        backtesting={
            "iteraciones": 1,
            "metricas": {
                "mae": 1.0,
                "rmse": 1.2,
                "mape": 1.0,
                "smape": 1.0,
                "mase": 0.9,
                "porcentaje_errores_extremos": 0.0,
            },
        },
        factibilidad={
            "factible": True,
            "estado": "Proyectable",
            "razones_tecnicas": [],
            "advertencias": [],
        },
        evaluacion_intervalos={
            "ancho_relativo_95_maximo": 0.15,
        },
    )

    assert evidencia["permitido"] is True, evidencia
    assert evidencia["no_recomendable"] is False, evidencia
    assert evidencia["clasificacion"] != "no_viable", evidencia
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 2). Se exigia la frase
    # «ventanas de validacion», que llegaba dentro de un texto que citaba el
    # minimo del INTERVALO -«por debajo de 3 no es posible construir ni evaluar el
    # intervalo de prediccion. El pronostico puntual se entrega; su intervalo
    # no»-. Con el intervalo retirado esa frase informa sobre un objeto que no se
    # entrega. Se exige lo sustantivo: que el numero de errores fuera de muestra
    # se declare y se califique de muy limitado.
    texto = " ".join(str(a) for a in (evidencia.get("advertencias") or [])).lower()
    assert "n=1" in texto, texto
    assert "muy limitada" in texto, texto
    assert "fuera de muestra" in texto, texto


def test_docx_final_no_tiene_tablas_deformadas() -> None:
    """Genera el DOCX en un temporal en lugar de leer uno residual.

    Antes buscaba reportes_generados/prueba_final_ui_word_referencias.docx
    y, si no existia, no comprobaba nada: la prueba pasaba sin ejercitar
    el codigo. Ahora produce el documento y siempre lo verifica.
    """
    import tempfile

    import pandas as pd

    from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
    from app_icociv.reportes.generador_reportes import generar_reporte_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme

    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(60)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": [100.0 + 0.7 * i for i in range(60)]})
    resultado = ejecutar_proyeccion(serie, 2026, 6, 2021)

    with tempfile.TemporaryDirectory(prefix="savip_docx_") as tmp:
        ruta = Path(tmp) / "informe.docx"
        generar_reporte_proyeccion(
            ruta, "Prueba", "anexo.xlsb", {}, {}, None, "T_16",
            serie.head(1), serie, resultado, periodos,
            configuracion=ConfiguracionInforme.desde_tipo("tecnico"),
        )
        _verificar_tablas_docx(ruta)


def _verificar_tablas_docx(ruta: Path) -> None:

    from docx import Document

    doc = Document(str(ruta))
    patron_etiqueta_pegada = re.compile(
        r"\b(Periodo|Modelo|Estado|Confianza|Metodo|Errores OOS|Tabla ICOCIV|Variación acumulada)(?!\s*:)(?=[A-Z0-9_])"
    )
    for tabla in doc.tables:
        assert max((len(fila.cells) for fila in tabla.rows), default=0) <= 6
        for fila in tabla.rows:
            for celda in fila.cells:
                texto = " ".join(celda.text.split())
                assert len(texto) <= 180
                assert not patron_etiqueta_pegada.search(texto)

    with ZipFile(ruta) as zf:
        xml = zf.read("word/document.xml")
    root_xml = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for tabla in root_xml.findall(".//w:tbl", ns):
        for columna in tabla.findall(".//w:tblGrid/w:gridCol", ns):
            ancho = int(columna.attrib.get("{%s}w" % ns["w"], "0") or 0)
            assert not ancho or ancho >= 1100


def _ejecutar() -> int:
    """Ejecutor propio (hallazgo H-02).

    Esta suite no tenia bloque __main__: ejecutada con `python archivo.py` se
    importaba, no llamaba a ninguna funcion y terminaba con codigo 0. Cualquier
    ejecutor guiado por el codigo de salida la contaba como aprobada sin haber
    comprobado nada.
    """
    fallos = total = 0
    for nombre, funcion in sorted(globals().items()):
        if not nombre.startswith("test_") or not callable(funcion):
            continue
        total += 1
        try:
            funcion()
            print(f"  OK    {nombre}")
        except AssertionError as error:
            fallos += 1
            print(f"  FALLA {nombre}: {error}")
        except Exception as error:  # pragma: no cover
            fallos += 1
            print(f"  ERROR {nombre}: {type(error).__name__}: {error}")
    print(f"\n{total - fallos}/{total} pruebas aprobadas.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
