"""P0-C / C2 — guardas de regresion negativa (R1-R10).

Diez propiedades que deben seguir siendo ciertas manana. No comprueban que el
retiro se hizo -eso lo hace `test_p0c_retiro_intervalos_no_sustentados.py`-,
sino que NO puede deshacerse por descuido: que ningun formato vuelva a entregar
la banda, que no aparezca una sustituta, y que las dos direcciones del bloqueo
del punto sigan como estan.

Son PROPIEDADES, no instantaneas de texto: se comprueba que ningun numero de la
banda -calculada en vivo, no fijada aqui- aparezca en las salidas, y que ninguna
llamada de dibujo de banda sea alcanzable. Asi la guarda no se rompe al
reescribir una frase, pero si al reintroducir el dato.

    R1  No vuelvan numeros IC95 en UI.
    R2  No vuelva `fill_between` de la banda retirada.
    R3  No vuelvan numeros IC95 en CSV/HTML.
    R4  No vuelvan numeros IC95 en DOCX/PDF.
    R5  No vuelva `graficas.py` a publicar banda.
    R6  No vuelva el objeto publico a exponer limites numericos.
    R7  No vuelva la cobertura publica del intervalo retirado.
    R8  No aparezca banda sustituta.
    R9  La falta de intervalo no bloquee un punto finito.
    R10 Un punto no finito siga bloqueando.

Ejecucion directa, sin pytest:

    python tests/test_p0c_regresion_negativa_c2.py
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.interfaz.presentacion_resultados import construir_html_resultados  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    PUNTO_NO_FINITO,
    _clasificar_evidencia_horizonte,
    estado_banda,
)
from app_icociv.reportes import generador_reportes  # noqa: E402
from tests.test_p0c_retiro_intervalos_no_sustentados import (  # noqa: E402
    MARCAS_COBERTURA_PUBLICA,
    RUTA_JERARQUICA,
    _finito,
    _fugas_numericas,
    _informe,
    _llamadas_alcanzables,
    _numeros_publicados_de_limite,
    _proyectar,
    _proyectar_interno,
    _serie,
    _textos_de,
    _texto_docx,
)


_SERIE = _serie(48)
_HORIZONTE = 6
_CACHE: dict[str, object] = {}


def _caso() -> tuple[dict, list[float]]:
    """Resultado publico y los numeros que la banda TIENE internamente.

    Los limites se calculan en vivo desde el resultado anterior al corte: no se
    fijan en el archivo, de modo que la guarda sigue siendo valida si cambian
    los datos, el modelo o el horizonte.
    """
    if "publico" not in _CACHE:
        _CACHE["publico"] = _proyectar(_SERIE, _HORIZONTE)
        interno = _proyectar_interno(_SERIE, _HORIZONTE)
        _CACHE["limites"] = [v for _, v in _numeros_publicados_de_limite(interno)]
    return _CACHE["publico"], _CACHE["limites"]  # type: ignore[return-value]


def _superficies(publico: dict) -> dict[str, str]:
    with TemporaryDirectory() as tmp:
        ruta = generador_reportes.generar_reporte_html(
            Path(tmp) / "informe.html", "Auditoria", "anexo.xlsx", {}, {}, RUTA_JERARQUICA,
            "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]), _SERIE, publico,
            [str(p) for p in _SERIE["Periodo"]],
        )
        html_informe = Path(ruta).read_text(encoding="utf-8")
    return {
        "UI": construir_html_resultados(publico),
        "CSV": generador_reportes.construir_dataframe_reproducibilidad(
            _SERIE, publico, RUTA_JERARQUICA).to_csv(index=False),
        "HTML": html_informe,
        "informe": " ".join(_textos_de(_informe(_SERIE, publico, "completo"))),
        "DOCX": _texto_docx(generador_reportes.construir_bytes_reporte_docx(
            "T_16", pd.DataFrame([{"Grupos_Obra": "Carreteras"}]), _SERIE, publico,
            [str(p) for p in _SERIE["Periodo"]])),
    }


def r1_ui_sin_numeros_ic95() -> None:
    publico, limites = _caso()
    assert limites, "El motor no produjo banda interna: la guarda no ejerce nada."
    fugas = _fugas_numericas(construir_html_resultados(publico), limites)
    assert not fugas, f"Volvieron numeros del intervalo a la UI: {fugas[:6]}"


def r2_sin_fill_between_de_la_banda() -> None:
    for ruta in (RAIZ / "app_icociv" / "reportes" / "graficas.py",
                 RAIZ / "app_icociv" / "interfaz" / "ventana_principal.py"):
        lineas = _llamadas_alcanzables(ruta, "fill_between")
        assert not lineas, f"{ruta.name} volvio a dibujar la banda en {lineas}."


def r3_csv_y_html_sin_numeros_ic95() -> None:
    publico, limites = _caso()
    superficies = _superficies(publico)
    for nombre in ("CSV", "HTML"):
        fugas = _fugas_numericas(superficies[nombre], limites)
        assert not fugas, f"Volvieron numeros del intervalo a {nombre}: {fugas[:6]}"


def r4_docx_y_pdf_sin_numeros_ic95() -> None:
    publico, limites = _caso()
    superficies = _superficies(publico)
    for nombre in ("informe", "DOCX"):
        fugas = _fugas_numericas(superficies[nombre], limites)
        assert not fugas, f"Volvieron numeros del intervalo a {nombre}: {fugas[:6]}"


def r5_graficas_no_publica_banda() -> None:
    ruta = RAIZ / "app_icociv" / "reportes" / "graficas.py"
    assert not _llamadas_alcanzables(ruta, "fill_between")
    assert not _llamadas_alcanzables(ruta, "fill_betweenx")
    assert not _llamadas_alcanzables(ruta, "axhspan")
    assert not _llamadas_alcanzables(ruta, "errorbar")


def r6_objeto_publico_sin_limites_numericos() -> None:
    publico, _ = _caso()
    fugas = _numeros_publicados_de_limite(publico, "resultado")
    assert not fugas, f"El objeto publico volvio a exponer limites: {fugas[:8]}"
    # Y tambien en el payload que el controlador entrega a la interfaz.
    from app_icociv.interfaz.controladores.controlador_principal import ControladorPrincipal
    payload = ControladorPrincipal._proyeccion_serializable(publico)
    assert not _numeros_publicados_de_limite(payload, "payload")


def r7_sin_cobertura_publica_del_intervalo_retirado() -> None:
    publico, _ = _caso()
    for nombre, texto in _superficies(publico).items():
        plano = re.sub(r"<[^>]+>", " ", texto).lower()
        presentes = [m for m in MARCAS_COBERTURA_PUBLICA if m in plano]
        assert not presentes, f"{nombre} volvio a publicar la cobertura: {presentes}"
    # P0-C, 16-08-2026 (V-CODEX-3). Aqui se exigia que el diagnostico de
    # cobertura SIGUIERA en el objeto publico, con el argumento de que
    # "retirar no es borrar". La auditoria independiente refuto esa lectura:
    # todo lo que devuelve `ejecutar_proyeccion` ES la salida publica, y que
    # una clave se llame `diagnostico_cobertura_no_publicado` no la vuelve
    # privada. El calculo permanece dentro de `_ejecutar_proyeccion_base`,
    # donde es diagnostico y no decide; lo que ya no viaja es la salida.
    assert publico.get("cobertura_empirica") is None
    assert publico.get("clasificacion_intervalo") is None
    assert publico.get("diagnostico_cobertura_no_publicado") is None


def r8_sin_banda_sustituta() -> None:
    publico, _ = _caso()
    interno = _proyectar_interno(_SERIE, _HORIZONTE)
    assert not (set(publico) - set(interno)), "Aparecieron claves nuevas en el objeto publico."
    for nombre, texto in _superficies(publico).items():
        plano = re.sub(r"<[^>]+>", " ", texto).lower()
        for sustituto in ("rango de referencia", "banda alternativa", "margen de error",
                          "intervalo aproximado", "banda indicativa", "rango estimado",
                          "banda orientativa"):
            assert sustituto not in plano, f"{nombre} ofrece una banda sustituta: '{sustituto}'."


def r9_falta_de_intervalo_no_bloquea_punto_finito() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import (
        BANDA_LIMITES_INVERTIDOS, BANDA_LIMITES_NO_FINITOS, BANDA_NO_CALCULABLE,
        BANDA_SEMIANCHO_CERO, BANDA_VALIDA,
    )
    base = dict(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
    )
    for estado in (BANDA_NO_CALCULABLE, BANDA_LIMITES_NO_FINITOS, BANDA_LIMITES_INVERTIDOS,
                   BANDA_SEMIANCHO_CERO, BANDA_VALIDA):
        c = _clasificar_evidencia_horizonte(
            evaluacion_intervalos={"estado_banda": estado, "ancho_relativo_95_maximo": 0.1},
            **base,
        )
        assert c.get("permitido_para_proyeccion_tecnica") or c.get("permitido_como_escenario"), \
            f"'{estado}' volvio a bloquear un punto finito (REQ 14)."
    publico, _ = _caso()
    assert publico.get("proyeccion_generada") is True
    assert _finito(publico.get("y_proj"))


def r10_punto_no_finito_sigue_bloqueando() -> None:
    for punto in (float("nan"), float("inf"), float("-inf")):
        assert estado_banda(90.0, 110.0, punto) == PUNTO_NO_FINITO
    c = _clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": PUNTO_NO_FINITO, "ancho_relativo_95_maximo": 0.1},
    )
    assert not c.get("permitido_para_proyeccion_tecnica")
    assert not c.get("permitido_como_escenario")


GUARDAS = [
    ("R1", "No vuelven números IC95 en UI.", r1_ui_sin_numeros_ic95),
    ("R2", "No vuelve `fill_between` de la banda retirada.", r2_sin_fill_between_de_la_banda),
    ("R3", "No vuelven números IC95 en CSV/HTML.", r3_csv_y_html_sin_numeros_ic95),
    ("R4", "No vuelven números IC95 en DOCX/PDF.", r4_docx_y_pdf_sin_numeros_ic95),
    ("R5", "`graficas.py` no vuelve a publicar banda.", r5_graficas_no_publica_banda),
    ("R6", "El objeto público no vuelve a exponer límites numéricos.",
     r6_objeto_publico_sin_limites_numericos),
    ("R7", "No vuelve la cobertura pública del intervalo retirado.",
     r7_sin_cobertura_publica_del_intervalo_retirado),
    ("R8", "No aparece banda sustituta.", r8_sin_banda_sustituta),
    ("R9", "La falta de intervalo no bloquea un punto finito.",
     r9_falta_de_intervalo_no_bloquea_punto_finito),
    ("R10", "Un punto no finito sigue bloqueando.", r10_punto_no_finito_sigue_bloqueando),
]


def main() -> int:
    fallos = 0
    for identificador, literal, guarda in GUARDAS:
        try:
            guarda()
        except Exception:  # noqa: BLE001 - se reporta integro
            fallos += 1
            print(f"FAIL {identificador}  {literal}")
            traceback.print_exc()
        else:
            print(f"OK   {identificador}  {literal}")
    print(f"\n{len(GUARDAS) - fallos}/{len(GUARDAS)} guardas verdes, {fallos} fallo(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
