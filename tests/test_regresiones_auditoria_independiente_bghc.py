"""Regresiones productivas halladas por la auditoria independiente (V-CODEX-3).

Cuatro bloques quedaron en FAIL con casos reproducibles. Estas pruebas los fijan
como CONTRATO, no como instantanea: cada una invoca la ruta productiva real y
comprueba QUE DECIDE, no como se llama ninguna variable.

    B  `n < 8` es un veto GLOBAL que bloquea antes de consultar la estimabilidad
       propia de cada candidato. El propio criterio se tipa
       `operativo_interno_sin_sustento`.

    G  `MIN_ITERACIONES_WF_ESCENARIO = 3` -derivado de poder construir y
       verificar la BANDA- recorta la rejilla, y la reconciliacion convierte esa
       poda en `proyeccion_generada=False` para un punto finito.

    H  El prefijo consecutivo desde h=1 corta en el primer hueco: h1 PASS,
       h2 FAIL, h3 PASS deja h3 vetado pese a tener evidencia propia.

    C  El retiro del intervalo es nominal: los extremos quedan `None` pero el
       objeto publico y el CSV conservan `width95`, `sigma_h`, `q95`, los
       offsets percentiles y el metodo, con los que la formula productiva
       reconstruye los limites exactos.

Referencias: `06_REMEDIACIONES/CODEX_FINAL/04_P0C_RETIRO.md`,
`05_P0G_DESACOPLE.md`, `11_REGLAS_DECISORIAS.md`, `13_VEREDICTO_FINAL.md`.

Ejecucion directa, sin pytest:

    python tests/test_regresiones_auditoria_independiente_bghc.py
"""
from __future__ import annotations

import math
import re
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    PUNTO_NO_FINITO,
    _clasificar_evidencia_horizonte,
    ejecutar_proyeccion,
    estado_banda,
)

ANIO_BASE = 2021


# ==============================
# APOYO
# ==============================


def _serie(n: int, pendiente: float = 1.5, ruido: float = 0.0, semilla: int = 5) -> pd.DataFrame:
    generador = np.random.default_rng(semilla)
    valores = [
        100.0 + pendiente * i + (float(generador.normal(0, ruido)) if ruido else 0.0)
        for i in range(n)
    ]
    return pd.DataFrame(
        {"Periodo": [f"{ANIO_BASE + i // 12}_{i % 12 + 1}" for i in range(n)], "Indice": valores}
    )


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _proyectar(serie: pd.DataFrame, horizonte: int) -> dict:
    return ejecutar_proyeccion(serie, *_objetivo(serie, horizonte), ANIO_BASE)


def _finito(valor) -> bool:
    if isinstance(valor, bool) or valor is None:
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


def _punto_directo(serie: pd.DataFrame, horizonte: int) -> float | None:
    """Punto que el catalogo puede producir, al margen de la reja de horizontes.

    Ajusta cada modelo elegible sobre la serie completa y devuelve el primer
    pronostico finito para ese horizonte. Sirve para demostrar que el punto
    EXISTE cuando la ruta productiva dice que no se genera.
    """
    from app_icociv.estadistica.modelos_interpretables import (
        MODELOS_INTERPRETABLES,
        ajustar_modelo_interpretable,
    )
    t = np.arange(1.0, len(serie) + 1.0)
    y = serie["Indice"].to_numpy(dtype=float)
    for nombre in MODELOS_INTERPRETABLES:
        try:
            ajuste = ajustar_modelo_interpretable(nombre, t, y)
            valor = float(ajuste["predict"](np.array([len(serie) + horizonte], dtype=float))[0])
        except Exception:  # noqa: BLE001 - un candidato que no ajusta no aporta
            continue
        if math.isfinite(valor):
            return valor
    return None


#: Claves y columnas cuyo valor permite RECONSTRUIR el intervalo retirado.
#: La formula productiva es
#:     base = punto / factor ; limite = (base + offset) * factor
#: de modo que basta el par de offsets, o `sigma_h` con su cuantil, o el ancho.
CLAVES_RECONSTRUCTIVAS = (
    "width95", "width80",
    "ancho_relativo_intervalo_max",
    "sigma_h_intervalo", "sigma_h",
    "q80_intervalo", "q95_intervalo", "q80", "q95",
    "percentil_80_inf_intervalo", "percentil_80_sup_intervalo",
    "percentil_95_inf_intervalo", "percentil_95_sup_intervalo",
    "percentil_80_inf", "percentil_80_sup",
    "percentil_95_inf", "percentil_95_sup",
    "ancho_relativo_80", "ancho_relativo_95", "ancho_relativo_intervalo",
    "ancho_relativo", "ancho_relativo_maximo",
    "ancho_relativo_80_maximo", "ancho_relativo_95_maximo",
    "limite_inferior", "limite_superior",
    "limite_inferior_80", "limite_superior_80",
    "limite_inferior_95", "limite_superior_95",
    "ic95_inferior", "ic95_superior", "ic80_inferior", "ic80_superior",
    "ci_lo", "ci_hi", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi",
)

#: Claves de texto que describen el metodo del intervalo retirado.
CLAVES_METODO_INTERVALO = (
    "metodo_intervalo", "metodo_intervalo_codigo",
    "clasificacion_intervalo", "tipo_banda",
    "cobertura_empirica", "cobertura_observada",
)


def _fugas_reconstructivas(objeto, ruta: str = "") -> list[tuple[str, float]]:
    """Todo numero finito publicado bajo una clave reconstructiva."""
    hallados: list[tuple[str, float]] = []
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            sub = f"{ruta}.{clave}" if ruta else str(clave)
            if str(clave) in CLAVES_RECONSTRUCTIVAS and _finito(valor):
                hallados.append((sub, float(valor)))
            elif str(clave) in CLAVES_RECONSTRUCTIVAS and isinstance(valor, (list, tuple)):
                hallados.extend(
                    (f"{sub}[{i}]", float(v)) for i, v in enumerate(valor) if _finito(v))
            else:
                hallados.extend(_fugas_reconstructivas(valor, sub))
    elif isinstance(objeto, pd.DataFrame):
        for columna in objeto.columns:
            if str(columna) in CLAVES_RECONSTRUCTIVAS:
                for i, valor in enumerate(objeto[columna].tolist()):
                    if _finito(valor):
                        hallados.append((f"{ruta}[{i}].{columna}", float(valor)))
    elif isinstance(objeto, (list, tuple)):
        for i, item in enumerate(objeto):
            hallados.extend(_fugas_reconstructivas(item, f"{ruta}[{i}]"))
    return hallados


_CACHE: dict[str, dict] = {}


def _ordinario() -> dict:
    if "ordinario" not in _CACHE:
        _CACHE["ordinario"] = _proyectar(_serie(48, ruido=0.4), 6)
    return _CACHE["ordinario"]


# ==============================
# BLOQUE B — veto global n < 8
# ==============================


def b1_n7_con_candidato_finito_no_se_bloquea() -> None:
    """B-RED-1 de Codex: n=7 con punto finito no puede negarse solo por n<8."""
    serie = _serie(7)
    punto_posible = _punto_directo(serie, 1)
    assert punto_posible is not None and math.isfinite(punto_posible), (
        "el fixture no ejerce el criterio: ningun candidato produce punto finito"
    )
    resultado = _proyectar(serie, 1)
    explicacion = str(resultado.get("explicacion") or "")
    assert resultado.get("proyeccion_generada") is True, (
        f"P0-B: serie de 7 observaciones con punto finito {punto_posible!r} negada. "
        f"Motivo publicado: {explicacion[:160]}"
    )
    assert _finito(resultado.get("y_proj")), resultado.get("y_proj")


def b2_sin_candidato_ajustable_bloquea_por_candidato() -> None:
    """Si NINGUN candidato puede ajustarse, el bloqueo debe ser por candidato."""
    serie = pd.DataFrame({"Periodo": ["2021_1", "2021_2"], "Indice": [100.0, 101.0]})
    resultado = _proyectar(serie, 1)
    assert resultado.get("proyeccion_generada") is False, "dos observaciones no sostienen nada"
    motivo = " ".join([
        str(resultado.get("explicacion") or ""),
        " ".join(str(r) for r in (resultado.get("factibilidad") or {}).get("razones_tecnicas", [])),
    ]).lower()
    assert "8" not in motivo or "candidat" in motivo or "model" in motivo, (
        f"el bloqueo se sigue justificando por el minimo global: {motivo[:200]}"
    )


# ==============================
# BLOQUE G — ventanas y banda
# ==============================


def g1_n8_h2_entrega_el_punto() -> None:
    """G-RED-1 de Codex: n=8, h=2, punto finito debe entregarse."""
    serie = _serie(8)
    punto_posible = _punto_directo(serie, 2)
    assert punto_posible is not None, "el fixture no produce punto para h=2"
    resultado = _proyectar(serie, 2)
    assert resultado.get("proyeccion_generada") is True, (
        f"P0-G: h=2 negado con n=8 pese a existir punto finito {punto_posible!r}. "
        f"Motivo: {str(resultado.get('explicacion'))[:160]}"
    )
    assert int(resultado.get("horizonte_permitido") or 0) == 2
    assert _finito(resultado.get("y_proj"))


def g2_menos_de_tres_ventanas_no_veta_el_punto() -> None:
    """El recuento de ventanas es diagnostico, no requisito de publicacion."""
    for n, h in ((8, 2), (9, 3), (10, 4)):
        serie = _serie(n)
        if _punto_directo(serie, h) is None:
            continue
        resultado = _proyectar(serie, h)
        assert resultado.get("proyeccion_generada") is True, (
            f"P0-G: n={n}, h={h} negado por falta de ventanas. "
            f"Motivo: {str(resultado.get('explicacion'))[:140]}"
        )


def _clasificar(estado: str, **extra) -> dict:
    base = dict(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
    )
    evaluacion = {"estado_banda": estado, "ancho_relativo_95_maximo": 0.1}
    evaluacion.update(extra)
    return _clasificar_evidencia_horizonte(evaluacion_intervalos=evaluacion, **base)


def g3_banda_ancha_no_veta_el_punto() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import BANDA_VALIDA
    c = _clasificar(BANDA_VALIDA, ancho_relativo_95_maximo=5.0, critico=True)
    assert c.get("permitido_para_proyeccion_tecnica") or c.get("permitido_como_escenario"), (
        "P0-G: una banda muy ancha veta el punto"
    )


def g4_cobertura_pobre_no_veta_el_punto() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import (
        BANDA_VALIDA,
        clasificar_intervalo_por_cobertura,
    )
    cobertura = {
        "verificable": True, "verificable_paso_exacto": True,
        "cobertura_95_paso_exacto": 0.0, "n_errores_paso_exacto": 20,
        "cobertura_95_minima": 0.0, "metodo_evaluacion": "origen_movil",
        "por_horizonte": [{"horizonte": 1, "cobertura_95": 0.0, "n_prueba": 20,
                           "n_calibracion": 20}],
    }
    r = clasificar_intervalo_por_cobertura(cobertura, {1: np.zeros(20)},
                                           estado_banda_paso=BANDA_VALIDA)
    assert r.get("degrada_a_escenario") is False, "P0-G: la cobertura degrada el punto"


def g5_limites_no_finitos_o_invertidos_no_vetan() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import (
        BANDA_LIMITES_INVERTIDOS,
        BANDA_LIMITES_NO_FINITOS,
        BANDA_NO_CALCULABLE,
        BANDA_SEMIANCHO_CERO,
    )
    for estado in (BANDA_LIMITES_NO_FINITOS, BANDA_LIMITES_INVERTIDOS,
                   BANDA_NO_CALCULABLE, BANDA_SEMIANCHO_CERO):
        c = _clasificar(estado, critico=True)
        assert c.get("permitido_para_proyeccion_tecnica") or c.get("permitido_como_escenario"), (
            f"P0-G: '{estado}' veta un punto finito"
        )


def g6_punto_no_finito_sigue_bloqueando() -> None:
    for punto in (float("nan"), float("inf"), float("-inf")):
        assert estado_banda(90.0, 110.0, punto) == PUNTO_NO_FINITO
    c = _clasificar(PUNTO_NO_FINITO)
    assert not c.get("permitido_para_proyeccion_tecnica")
    assert not c.get("permitido_como_escenario")


# ==============================
# BLOQUE H — prefijo consecutivo
# ==============================


def _estados(*permitidos: bool) -> list[dict]:
    return [
        {"horizonte": i, "permitido_para_proyeccion_tecnica": p,
         "permitido_como_escenario": p, "clasificacion": "tecnica" if p else "no_viable",
         "no_recomendable": not p}
        for i, p in enumerate(permitidos, start=1)
    ]


def h1_hueco_en_h2_no_veta_h3() -> None:
    """H-RED-1: h1 PASS, h2 FAIL, h3 PASS. h3 conserva su evidencia propia."""
    from app_icociv.proyeccion.servicio_proyeccion import (
        _mayor_horizonte_permitido,
    )
    estados = _estados(True, False, True)
    admisible = _mayor_horizonte_permitido(estados)
    assert admisible >= 3, (
        f"P0-H: el prefijo corta en el hueco de h=2 y deja el maximo en {admisible}; "
        "h=3 tiene evidencia propia y no puede quedar vetado por h=2"
    )


def h2_un_fallo_real_no_se_inventa() -> None:
    """Retirar el prefijo no puede convertir un h fallido en admisible."""
    from app_icociv.proyeccion.servicio_proyeccion import (
        _mayor_horizonte_permitido,
    )
    estados = _estados(True, False, True)
    assert estados[1]["permitido_para_proyeccion_tecnica"] is False
    assert estados[1]["permitido_como_escenario"] is False
    # El maximo no puede saltar a un horizonte que nadie evaluo.
    assert _mayor_horizonte_permitido(estados) <= 3


def h3_la_evidencia_de_cada_horizonte_se_conserva() -> None:
    from app_icociv.proyeccion.servicio_proyeccion import (
        _mayor_horizonte_permitido,
    )
    assert _mayor_horizonte_permitido(_estados(False, False, False)) == 0
    assert _mayor_horizonte_permitido(_estados(True, True, True)) == 3
    assert _mayor_horizonte_permitido(_estados(False, True, False)) == 2


# ==============================
# BLOQUE C — retiro REAL del intervalo
# ==============================


def c1_objeto_publico_sin_componentes_reconstructivos() -> None:
    fugas = _fugas_reconstructivas(_ordinario(), "resultado")
    assert not fugas, (
        f"P0-C: el objeto publico conserva {len(fugas)} componentes del intervalo. "
        f"Ejemplos: {fugas[:8]}"
    )


def c2_sin_width95_en_stats() -> None:
    stats = _ordinario().get("stats") or {}
    for clave in ("width95", "width80", "ancho_relativo_intervalo_max"):
        assert not _finito(stats.get(clave)), f"P0-C: stats.{clave} = {stats.get(clave)!r}"


def c3_sin_cuantiles_ni_offsets() -> None:
    proy = _ordinario().get("proyecciones")
    assert isinstance(proy, pd.DataFrame)
    for columna in ("q80_intervalo", "q95_intervalo",
                    "percentil_80_inf_intervalo", "percentil_80_sup_intervalo",
                    "percentil_95_inf_intervalo", "percentil_95_sup_intervalo"):
        if columna not in proy.columns:
            continue
        valores = [v for v in proy[columna].tolist() if _finito(v)]
        assert not valores, f"P0-C: columna {columna} publica {valores[:3]}"


def c4_sin_sigma_h_como_parametro_del_intervalo() -> None:
    proy = _ordinario().get("proyecciones")
    if isinstance(proy, pd.DataFrame) and "sigma_h_intervalo" in proy.columns:
        valores = [v for v in proy["sigma_h_intervalo"].tolist() if _finito(v)]
        assert not valores, f"P0-C: sigma_h_intervalo publica {valores[:3]}"


def c5_csv_no_permite_reconstruir_el_intervalo() -> None:
    from app_icociv.reportes.generador_reportes import construir_dataframe_reproducibilidad
    publico = _ordinario()
    df = construir_dataframe_reproducibilidad(_serie(48, ruido=0.4), publico, None)
    fugas = _fugas_reconstructivas(df, "csv")
    assert not fugas, f"P0-C: el CSV publica componentes reconstructivos: {fugas[:8]}"


def c6_ui_no_muestra_ancho_ni_metodo_del_intervalo() -> None:
    from app_icociv.interfaz.presentacion_resultados import construir_html_resultados
    html = re.sub(r"<[^>]+>", " ", construir_html_resultados(_ordinario())).lower()
    for marca in ("ancho relativo", "sigma", "cuantil", "q95",
                  "método de intervalo", "metodo de intervalo"):
        assert marca not in html, f"P0-C: la UI publica '{marca}'"
    assert not re.search(r"ic\s*95\s*[:=]?\s*-?\d", html), "P0-C: la UI publica un IC95 numerico"


def _texto_informe(tipo: str = "tecnico") -> str:
    from app_icociv.reportes.contenido import DatosProyeccion, construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme
    from dataclasses import fields, is_dataclass

    datos = DatosProyeccion(
        resultado=_ordinario(), serie_df=_serie(48, ruido=0.4), fuente_label="T_16",
        archivo_excel="anexo.xlsx", ruta_jerarquica=[{"nivel": "Grupo", "valor": "X"}],
        fila=pd.DataFrame([{"Grupos_Obra": "X"}]),
        year_month=[], usuario="Auditoria",
    )
    informe = construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo(tipo))

    def textos(objeto, vistos=None):
        vistos = vistos if vistos is not None else set()
        if isinstance(objeto, str):
            return [objeto]
        if id(objeto) in vistos:
            return []
        vistos.add(id(objeto))
        salida = []
        if is_dataclass(objeto):
            for campo in fields(objeto):
                salida += textos(getattr(objeto, campo.name), vistos)
        elif isinstance(objeto, dict):
            for k, v in objeto.items():
                salida += textos(k, vistos) + textos(v, vistos)
        elif isinstance(objeto, (list, tuple, set)):
            for item in objeto:
                salida += textos(item, vistos)
        return salida

    return " ".join(textos(informe)).lower()


def c7_docx_no_publica_el_metodo_del_intervalo() -> None:
    texto = _texto_informe("tecnico")
    for marca in ("método calculado internamente", "metodo calculado internamente",
                  "trazabilidad del método retirado", "trazabilidad del metodo retirado",
                  "horizonte de los errores usados"):
        assert marca not in texto, f"P0-C: el informe publica '{marca}'"


def c8_pdf_no_publica_el_metodo_del_intervalo() -> None:
    # DOCX y PDF dibujan el MISMO objeto de contenido; comprobarlo alli los cubre.
    c7_docx_no_publica_el_metodo_del_intervalo()
    texto = _texto_informe("completo")
    assert "errores fuera de muestra disponibles" not in texto, (
        "P0-C: el informe publica el recuento de errores como trazabilidad del intervalo"
    )


def c9_las_metricas_oos_generales_permanecen() -> None:
    publico = _ordinario()
    metricas = (publico.get("backtesting") or {}).get("metricas") or {}
    for clave in ("rmse", "mae", "mase"):
        assert _finito(metricas.get(clave)), f"se perdio la metrica OOS {clave}"


def c10_intervalo_sustentado_sigue_declarado_false() -> None:
    publico = _ordinario()
    assert publico.get("intervalo_sustentado") is False
    assert str(publico.get("motivo_intervalo_no_sustentado") or "").strip()


def c11_ninguna_banda_decide() -> None:
    """El estado de banda no puede alterar el horizonte permitido."""
    from app_icociv.proyeccion.servicio_proyeccion import (
        BANDA_LIMITES_NO_FINITOS,
        BANDA_VALIDA,
    )
    con_banda = _clasificar(BANDA_VALIDA)
    sin_banda = _clasificar(BANDA_LIMITES_NO_FINITOS)
    assert con_banda.get("permitido_para_proyeccion_tecnica") == \
        sin_banda.get("permitido_para_proyeccion_tecnica"), (
        "P0-C/G: el estado de la banda cambia el permiso del horizonte"
    )


def c12_casos_ordinarios_conservan_modelo_punto_y_horizonte() -> None:
    publico = _ordinario()
    assert publico.get("proyeccion_generada") is True
    assert str(publico.get("model_name") or "").strip()
    assert _finito(publico.get("y_proj"))
    assert int(publico.get("horizonte_permitido") or 0) == 6


PRUEBAS = [
    ("B1", "n=7 con candidato finito no se bloquea", b1_n7_con_candidato_finito_no_se_bloquea),
    ("B2", "sin candidato ajustable bloquea por candidato", b2_sin_candidato_ajustable_bloquea_por_candidato),
    ("G1", "n=8 h=2 entrega el punto", g1_n8_h2_entrega_el_punto),
    ("G2", "menos de tres ventanas no veta el punto", g2_menos_de_tres_ventanas_no_veta_el_punto),
    ("G3", "banda ancha no veta el punto", g3_banda_ancha_no_veta_el_punto),
    ("G4", "cobertura pobre no veta el punto", g4_cobertura_pobre_no_veta_el_punto),
    ("G5", "limites no finitos o invertidos no vetan", g5_limites_no_finitos_o_invertidos_no_vetan),
    ("G6", "punto no finito sigue bloqueando", g6_punto_no_finito_sigue_bloqueando),
    ("H1", "hueco en h2 no veta h3", h1_hueco_en_h2_no_veta_h3),
    ("H2", "un fallo real no se inventa", h2_un_fallo_real_no_se_inventa),
    ("H3", "la evidencia de cada horizonte se conserva", h3_la_evidencia_de_cada_horizonte_se_conserva),
    ("C1", "objeto publico sin componentes reconstructivos", c1_objeto_publico_sin_componentes_reconstructivos),
    ("C2", "sin width95 en stats", c2_sin_width95_en_stats),
    ("C3", "sin cuantiles ni offsets", c3_sin_cuantiles_ni_offsets),
    ("C4", "sin sigma_h como parametro del intervalo", c4_sin_sigma_h_como_parametro_del_intervalo),
    ("C5", "el CSV no permite reconstruir el intervalo", c5_csv_no_permite_reconstruir_el_intervalo),
    ("C6", "la UI no muestra ancho ni metodo", c6_ui_no_muestra_ancho_ni_metodo_del_intervalo),
    ("C7", "el DOCX no publica el metodo", c7_docx_no_publica_el_metodo_del_intervalo),
    ("C8", "el PDF no publica el metodo", c8_pdf_no_publica_el_metodo_del_intervalo),
    ("C9", "las metricas OOS generales permanecen", c9_las_metricas_oos_generales_permanecen),
    ("C10", "intervalo_sustentado sigue False", c10_intervalo_sustentado_sigue_declarado_false),
    ("C11", "ninguna banda decide", c11_ninguna_banda_decide),
    ("C12", "casos ordinarios conservan modelo, punto y horizonte", c12_casos_ordinarios_conservan_modelo_punto_y_horizonte),
]


def main() -> int:
    fallos = 0
    for identificador, literal, prueba in PRUEBAS:
        try:
            prueba()
        except Exception:  # noqa: BLE001 - se reporta integro
            fallos += 1
            print(f"FAIL {identificador}  {literal}")
            traceback.print_exc()
        else:
            print(f"OK   {identificador}  {literal}")
    print(f"\n{len(PRUEBAS) - fallos}/{len(PRUEBAS)} verdes, {fallos} fallo(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
