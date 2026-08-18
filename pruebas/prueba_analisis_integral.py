"""Pruebas de verificación del análisis estadístico integral ICOCIV."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app_icociv.estadistica.analisis_series import (  # noqa: E402
    calcular_variables_derivadas,
    detectar_valores_atipicos_mad,
    normalizar_serie_mensual,
    validar_serie_mensual,
)
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion  # noqa: E402
from app_icociv.reportes.generador_reportes import generar_reporte_pdf, generar_reporte_proyeccion  # noqa: E402


def serie_valida(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "Periodo": [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(n)],
            "Indice": [100.0 + 0.18 * i + 0.006 * (i ** 2) + float(rng.normal(0, 0.18)) for i in range(n)],
        }
    )


def serie_duplicada() -> pd.DataFrame:
    serie = serie_valida(24)
    serie.loc[5, "Periodo"] = serie.loc[4, "Periodo"]
    return serie


def serie_con_salto() -> pd.DataFrame:
    serie = serie_valida(30)
    return serie.drop(index=[10, 11]).reset_index(drop=True)


def serie_corta() -> pd.DataFrame:
    return serie_valida(8)


def serie_con_outlier() -> pd.DataFrame:
    serie = serie_valida(36)
    serie.loc[20, "Indice"] = serie.loc[20, "Indice"] * 1.25
    return serie


def serie_erratica() -> pd.DataFrame:
    valores = [100, 120, 86, 132, 91, 145, 88, 150, 93, 160, 95, 170, 96, 180, 94, 190, 92, 200]
    return pd.DataFrame({"Periodo": [f"{2024 + i // 12}_{i % 12 + 1}" for i in range(len(valores))], "Indice": valores})


def verificar_validaciones() -> None:
    normalizada = normalizar_serie_mensual(serie_valida(30), metadatos={"archivo_fuente": "sintetico.xlsx"})
    validacion = validar_serie_mensual(normalizada)
    assert validacion["continuidad_temporal"] == "OK"
    assert validacion["duplicados"] == 0

    duplicada = validar_serie_mensual(normalizar_serie_mensual(serie_duplicada()))
    assert duplicada["duplicados"] > 0
    assert duplicada["errores_criticos"]

    salto = validar_serie_mensual(normalizar_serie_mensual(serie_con_salto()))
    assert salto["continuidad_temporal"] == "REVISAR"
    assert salto["periodos_faltantes"]

    # P0-G, 16-08-2026 (V-CODEX-3). Antes se exigia `proyeccion_generada is
    # False` para una serie de ocho observaciones con h=2. La rejilla la negaba
    # por reservar tres ventanas para la BANDA, requisito del eje que P0-C
    # retiro. Con la cota de existencia `h <= n - N0` la solicitud es evaluable
    # y el punto se entrega, con la evidencia declarada como provisional.
    corta = ejecutar_proyeccion(serie_corta(), 2021, 10, 2021)
    assert corta["proyeccion_generada"] is True, corta.get("explicacion")
    assert corta["factibilidad"]["puede_generarse_informe"] is True
    assert corta["evidencia_oos_provisional"] is True

    derivadas = calcular_variables_derivadas(normalizar_serie_mensual(serie_con_outlier()))
    outliers = detectar_valores_atipicos_mad(derivadas["serie"])
    assert outliers


def verificar_proyeccion_y_horizonte() -> dict:
    resultado = ejecutar_proyeccion(serie_valida(72), 2027, 12, 2021)
    assert resultado["proyeccion_generada"] is True
    assert resultado["horizonte_permitido"] <= resultado["horizonte_solicitado"]
    assert not resultado["proyecciones"].empty
    assert "mape" in resultado["backtesting"]["metricas"]

    restringida = ejecutar_proyeccion(serie_valida(30), 2025, 12, 2021)
    assert restringida["horizonte_permitido"] <= restringida["horizonte_solicitado"]
    assert "horizonte_info" in restringida
    assert "mensaje_ui" in restringida["horizonte_info"] or not restringida["proyeccion_generada"]
    return resultado


def verificar_reportes(resultado: dict) -> None:
    # Hermeticidad: los informes de prueba van a un temporal, no al
    # repositorio. Escribir en reportes_generados dejaba residuos que
    # otras pruebas podian leer (hallazgo H-13).
    with tempfile.TemporaryDirectory(prefix="savip_prueba_") as tmp:
        _verificar_reportes_en(resultado, Path(tmp))


def _verificar_reportes_en(resultado: dict, salida: Path) -> None:
    fila = pd.DataFrame([{"Codigo": "demo", "Nombre": "Serie sintética"}])
    serie = serie_valida(72)

    pdf = generar_reporte_pdf(
        salida / "prueba_con_proyeccion.pdf",
        "prueba",
        "sintetico.xlsx",
        {},
        {"anio": 2027, "mes": 12},
        [{"nivel": "Grupo CPC", "valor": "Serie sintética"}],
        "T_16",
        fila,
        serie,
        resultado,
        [],
    )
    docx = generar_reporte_proyeccion(
        salida / "prueba_con_proyeccion.docx",
        "prueba",
        "sintetico.xlsx",
        {},
        {"anio": 2027, "mes": 12},
        [{"nivel": "Grupo CPC", "valor": "Serie sintética"}],
        "T_16",
        fila,
        serie,
        resultado,
        [],
    )
    assert pdf.exists() and pdf.stat().st_size > 20_000
    assert docx.exists() and docx.stat().st_size > 20_000

    sin_proyeccion = ejecutar_proyeccion(serie_corta(), 2021, 10, 2021)
    pdf_np = generar_reporte_pdf(
        salida / "prueba_sin_proyeccion.pdf",
        "prueba",
        "sintetico.xlsx",
        {},
        {"anio": 2021, "mes": 10},
        [{"nivel": "Grupo CPC", "valor": "Serie corta"}],
        "T_16",
        fila,
        serie_corta(),
        sin_proyeccion,
        [],
    )
    docx_np = generar_reporte_proyeccion(
        salida / "prueba_sin_proyeccion.docx",
        "prueba",
        "sintetico.xlsx",
        {},
        {"anio": 2021, "mes": 10},
        [{"nivel": "Grupo CPC", "valor": "Serie corta"}],
        "T_16",
        fila,
        serie_corta(),
        sin_proyeccion,
        [],
    )
    assert pdf_np.exists() and pdf_np.stat().st_size > 10_000
    assert docx_np.exists() and docx_np.stat().st_size > 10_000


def verificar_ejes_metodologicos(resultado: dict, erratica: dict) -> None:
    """Ocho ejes del cierre F/H/G sobre resultados ya calculados.

    CIERRE 13-08-2026. Lo que habia aqui era una sola linea:

        assert erratica["proyeccion_generada"] is False or \\
               erratica["factibilidad"]["nivel_confianza_metodologica"] in {"bajo", "no recomendable"}

    La sostenian dos reglas que P0-G retiro por no tener fuente que autorizara su
    consecuencia: el veto por ventanas y la escalera de confianza. La escalera ya
    no existe -`nivel_confianza_metodologica` es un texto descriptivo-, de modo
    que la pertenencia a un conjunto ordinal **no puede comprobarse**; y una serie
    erratica hoy se entrega, decision del 08-08-2026.

    No se sustituye por «no lanza excepcion»: se sustituye por los ocho ejes que
    el cierre dejo que comprobar, todos sobre resultados que esta prueba ya
    calcula.
    """
    # A. CALCULO. El punto se entrega cuando es tecnicamente posible; la
    #    imposibilidad aritmetica sigue bloqueando (serie de 8 observaciones,
    #    verificada en verificar_validaciones()).
    assert resultado["proyeccion_generada"] is True
    assert erratica["proyeccion_generada"] is True, erratica.get("explicacion")
    assert not resultado["proyecciones"].empty

    for nombre, res in (("valida", resultado), ("erratica", erratica)):
        # B. EVIDENCIA. Mientras P0-E este bloqueado, la evidencia OOS se publica
        #    como provisional y no puede presentarse como cerrada.
        assert res["evidencia_oos_provisional"] is True, (nombre, res.get("evidencia_oos_provisional"))
        # C. INTERVALO. Mientras P0-C este abierto, la banda no esta sustentada, y
        #    esa carencia no invalida el punto (REQ 14).
        assert res["intervalo_sustentado"] is False, (nombre, res.get("intervalo_sustentado"))
        assert str(res.get("motivo_intervalo_no_sustentado") or "").strip(), nombre
        # H. TRAZABILIDAD. Estado metodologico y bloqueos coherentes entre si.
        assert res["estado_metodologico"] != "resultado_metodologicamente_sustentado", nombre
        assert {"P0-C", "P0-E"} <= set(res["bloqueos_metodologicos"] or {}), nombre
        # F. COMPUERTAS. Sin confianza inferencial por escalera.
        confianza = str(res["factibilidad"].get("nivel_confianza_metodologica") or "").lower()
        assert confianza not in {"alto", "medio", "bajo", "no recomendable"}, (nombre, confianza)

    # D. CALENDARIO. El tratamiento no se aplica y gamma no altera el punto; el
    #    fenomeno no se niega, se publica como diagnostico.
    calendario = resultado.get("ajuste_calendario") or {}
    assert calendario["ajuste_calendario_aplicado"] is False, calendario
    factores = [float(f) for f in (calendario.get("factores_por_paso") or [])]
    assert factores and all(f == 1.0 for f in factores), factores
    assert "reconcentra" not in str(calendario.get("estado_calendario_visible") or "").lower()

    # E. HORIZONTE. La evaluacion por h no se detiene en el primer fallo, y el
    #    maximo publicado declara que admite huecos.
    #
    #    ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 3). Antes se exigia que la
    #    base dijera «producto», es decir que declarara una REGLA DE CONTINUIDAD
    #    -«trayectoria mensual sin huecos»- como fundamento del maximo. Esa regla
    #    se retiro del calculo el 16-08-2026, pero el texto la seguia publicando y
    #    esta prueba lo protegia. Ahora se exige que el texto diga la verdad.
    info = resultado.get("horizonte_info") or {}
    assert info.get("horizontes_no_evaluados") == [], info.get("horizontes_no_evaluados")
    assert "horizonte_maximo_publicable_continuo" in info
    assert "horizonte_maximo_admisible" in info
    base_continuo = str(info.get("base_horizonte_maximo_publicable_continuo") or "").lower()
    assert "no se interpola" in base_continuo, base_continuo
    assert "sin huecos" not in base_continuo, base_continuo

    # G. DIAGNOSTICOS. Siguen presentes como informacion: la serie erratica se
    #    entrega, pero no en silencio.
    assert erratica["factibilidad"].get("advertencias"), erratica["factibilidad"]


def main() -> None:
    verificar_validaciones()
    resultado = verificar_proyeccion_y_horizonte()
    verificar_reportes(resultado)
    erratica = ejecutar_proyeccion(serie_erratica(), 2025, 7, 2021)
    verificar_ejes_metodologicos(resultado, erratica)
    print("Pruebas integrales ICOCIV completadas.")
    print("Modelo:", resultado["model_name"])
    print("Horizonte solicitado:", resultado["horizonte_solicitado"])
    print("Horizonte permitido:", resultado["horizonte_permitido"])
    print("PDF/DOCX generados y verificados en carpeta temporal")


if __name__ == "__main__":
    main()
