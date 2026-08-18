"""Pruebas de la salvaguarda conservadora con benchmarks (decisión D-3).

Un único modelo principal por serie. Si ese modelo falla en algún horizonte
por causas atribuibles al modelo (no a falta de datos), se evalúan Drift y
Naive en el orden que el backtesting demuestre más conservador; si un
benchmark cumple los mismos criterios, sustituye al principal para TODA la
trayectoria. Solo se bloquea cuando ningún modelo razonable resulta admisible.
Caso de referencia: la serie de insumo «Arena» quedaba bloqueada en cascada
(h_max=0) aunque los benchmarks eran admisibles en horizontes cortos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.proyeccion.servicio_proyeccion import (
    _limites_auditoria_horizontes,
    ejecutar_proyeccion,
)
from app_icociv.utilidades.utilidades import ANIO_BASE

RUTA_ANEXO = ROOT / "anex-ICOCIV-may2026.xlsb"
_CACHE: dict[str, object] = {}


def _serie_arena() -> pd.DataFrame | None:
    if "arena" in _CACHE:
        return _CACHE["arena"]  # type: ignore[return-value]
    if not RUTA_ANEXO.exists():
        _CACHE["arena"] = None
        return None
    from app_icociv.datos.cargador_datos import cargar_todas_tablas
    from app_icociv.proyeccion.servicio_proyeccion import construir_serie

    tables, year_month = cargar_todas_tablas(RUTA_ANEXO.read_bytes(), RUTA_ANEXO.name)
    fila = tables["T_16_7"].loc[[0]]
    assert str(fila["Insumos"].iloc[0]).strip().lower().startswith("arena")
    serie = construir_serie(fila, year_month)
    _CACHE["arena"] = serie
    return serie


def _proyectar(serie: pd.DataFrame, horizonte: int) -> dict:
    ultimo = str(serie["Periodo"].iloc[-1])
    anio, mes = map(int, ultimo.split("_"))
    total = anio * 12 + (mes - 1) + int(horizonte)
    return ejecutar_proyeccion(serie, total // 12, total % 12 + 1, ANIO_BASE, origen_horizonte="manual")


def _serie_suave(n: int = 48) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    valores, nivel = [], 100.0
    for _ in range(n):
        nivel *= 1.004 + float(rng.normal(0.0, 0.0015))
        valores.append(nivel)
    periodos = [f"{2022 + i // 12}_{i % 12 + 1}" for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def _serie_erratica(n: int = 30) -> pd.DataFrame:
    valores = [100.0 * (1.45 if i % 2 == 0 else 0.55) for i in range(n)]
    periodos = [f"{2023 + i // 12}_{i % 12 + 1}" for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def test_arena_ya_no_necesita_ser_rescatada_por_un_benchmark() -> None:
    """SG-1, reformulada por el cierre metodológico del 08-08-2026.

    La salvaguarda existía para rescatar series que un veto sin fuente había
    bloqueado: el corte rRMSE > 1,25 declaraba no viable el modelo elegido y un
    benchmark asumía TODA la trayectoria, aunque su error fuera peor en los
    demás horizontes.

    Retirado el veto, no hay nada que rescatar. La serie se entrega con el
    modelo que el desempeño fuera de muestra seleccionó, y la salvaguarda ni
    siquiera se intenta. Lo que la prueba fija ahora es lo que importa: que la
    serie **se entrega**, que su horizonte es admisible y que la salvaguarda no
    sustituye el modelo.
    """
    serie = _serie_arena()
    if serie is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    resultado = _proyectar(serie, 1)
    salvaguarda = resultado.get("salvaguarda_benchmark")
    assert isinstance(salvaguarda, dict), "El resultado debe exponer salvaguarda_benchmark."
    assert salvaguarda.get("activada") is False, salvaguarda
    assert salvaguarda.get("modelo_final") == salvaguarda.get("modelo_principal"), salvaguarda
    info = resultado.get("horizonte_info") or {}
    assert int(info.get("horizonte_maximo_admisible") or 0) >= 1, info.get("horizonte_maximo_admisible")
    assert resultado.get("proyeccion_generada") is True, resultado.get("explicacion")
    assert resultado.get("modelo_codigo") == salvaguarda.get("modelo_principal")


def test_un_solo_modelo_en_toda_la_trayectoria() -> None:
    """SG-2: con salvaguarda activada, todos los horizontes usan el mismo modelo."""
    serie = _serie_arena()
    if serie is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    resultado = _proyectar(serie, 3)
    info = resultado.get("horizonte_info") or {}
    codigos = {
        str(ev.get("modelo_final_codigo"))
        for ev in info.get("evaluaciones") or []
        if ev.get("modelo_final_codigo")
    }
    assert len(codigos) == 1, f"La trayectoria debe usar un único modelo: {codigos}"


def test_modelo_estable_frente_al_horizonte_solicitado() -> None:
    """SG-3: pedir 1 o 3 meses no cambia el modelo ni el primer valor proyectado."""
    serie = _serie_arena()
    if serie is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    res_1 = _proyectar(serie, 1)
    res_3 = _proyectar(serie, 3)
    info_1 = res_1.get("horizonte_info") or {}
    info_3 = res_3.get("horizonte_info") or {}
    ev1 = {int(e["horizonte"]): e for e in info_1.get("evaluaciones") or [] if e.get("modelo_final_codigo")}
    ev3 = {int(e["horizonte"]): e for e in info_3.get("evaluaciones") or [] if e.get("modelo_final_codigo")}
    assert ev1 and ev3
    assert ev1[1]["modelo_final_codigo"] == ev3[1]["modelo_final_codigo"]
    if res_1.get("proyeccion_generada") and res_3.get("proyeccion_generada"):
        primero_1 = float(res_1["proyecciones"]["indice_proyectado"].iloc[0])
        primero_3 = float(res_3["proyecciones"]["indice_proyectado"].iloc[0])
        assert abs(primero_1 - primero_3) < 1e-9, (primero_1, primero_3)


def test_sin_fallo_no_se_activa_salvaguarda() -> None:
    """SG-4: si el modelo principal es admisible, no se sustituye."""
    resultado = _proyectar(_serie_suave(), 3)
    salvaguarda = resultado.get("salvaguarda_benchmark")
    assert isinstance(salvaguarda, dict), "salvaguarda_benchmark debe existir siempre."
    assert salvaguarda.get("activada") is False, salvaguarda
    assert resultado.get("proyeccion_generada") is True, resultado.get("explicacion")


def test_una_serie_erratica_se_entrega_con_su_incertidumbre() -> None:
    """SG-5, reformulada por el cierre metodológico del 08-08-2026.

    La serie alterna entre 145 y 55 cada mes. Antes quedaba bloqueada, y la
    prueba lo llamaba «bloqueo legítimo». No lo era: la bloqueaban los cortes de
    amplitud del IC95, nueve literales internos sin fuente.

    El pronóstico es calculable y la incertidumbre es enorme. Lo correcto es
    entregarlo diciendo cuánta: el ancho relativo del intervalo se publica con
    su valor. Bloquear era decidir por el usuario con un umbral inventado.
    """
    resultado = _proyectar(_serie_erratica(), 3)
    salvaguarda = resultado.get("salvaguarda_benchmark")
    assert isinstance(salvaguarda, dict)
    assert salvaguarda.get("activada") is False, salvaguarda
    if not resultado.get("proyeccion_generada"):
        # Si algo la bloquea, debe ser una imposibilidad de cálculo, no un umbral.
        razones = " ".join(str(r) for r in (resultado.get("factibilidad") or {}).get("razones_tecnicas", []))
        assert ("no valida" in razones.lower() or "ventanas" in razones.lower()
                or "no finitas" in razones.lower()), razones
        return
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). Se exigia «Intervalos
    # amplios (IC95 X%)» o «La incertidumbre del intervalo 95% es excesiva (ancho
    # relativo maximo X%)». Ambos son RECONSTRUCTIVOS: el ancho relativo por el
    # pronostico -que es publico y debe serlo- devuelve el semiancho de la banda
    # que P0-C retiro.
    #
    # El contrato de fondo -que la serie erratica se entrega CON su incertidumbre
    # a la vista, no en silencio- se conserva con las senales publicables.
    advertencias = " | ".join(
        str(a) for a in (resultado.get("factibilidad") or {}).get("advertencias", [])
    )
    assert advertencias.strip(), "la serie erratica se entrego sin ninguna advertencia"
    for reconstructivo in ("ancho relativo", "IC95", "IP95"):
        assert reconstructivo not in advertencias, (
            f"volvio a publicarse el ancho de la banda retirada: {advertencias}"
        )


def test_serie_corta_evalua_todo_lo_medible_y_no_intenta_rescate() -> None:
    """SG-6, reformulada por el cierre metodológico del 08-08-2026.

    Antes esta prueba exigía que una serie corta dejara horizontes
    ``horizontes_no_evaluados``. Esa lista era la huella del ``break`` del
    barrido: al primer horizonte no recomendable se dejaba de medir el resto.
    Retirado el ``break`` en P0-H, la huella desaparece —y con ella el assert—,
    porque un juicio de desempeño sobre *h* no puede negar la MEDICIÓN de los
    horizontes posteriores.

    Lo que se fija ahora separa EVALUADO de PUBLICADO y es más exigente que el
    contrato anterior: se mide exactamente el rango que la aritmética de
    ventanas permite, nadie se queda fuera por una parada anticipada, y la
    salvaguarda no se intenta porque no hay nada no calculable que rescatar.
    Si el ``break`` se reintrodujera, este test falla.
    """
    serie = _serie_suave(26)
    resultado = _proyectar(serie, 3)
    salvaguarda = resultado.get("salvaguarda_benchmark")
    assert isinstance(salvaguarda, dict)
    assert salvaguarda.get("intentada") is False, salvaguarda
    assert salvaguarda.get("activada") is False, salvaguarda
    assert salvaguarda.get("modelo_final") == salvaguarda.get("modelo_principal"), salvaguarda

    info = resultado.get("horizonte_info") or {}
    # El barrido no se detiene: no hay horizontes sin evaluar ni horizonte de corte.
    assert info.get("horizontes_no_evaluados") == [], info.get("horizontes_no_evaluados")
    assert int(info.get("primer_horizonte_no_viable") or 0) == 0, info.get("primer_horizonte_no_viable")
    # El rango medido es el que la aritmética de ventanas permite, derivado, no un tope literal.
    _, maximo_por_datos, _, _ = _limites_auditoria_horizontes(len(serie))
    evaluados = [int(h) for h in (info.get("horizontes_evaluados") or [])]
    assert evaluados == list(range(1, maximo_por_datos + 1)), (evaluados, maximo_por_datos)


def test_orden_de_benchmarks_es_conservador_y_trazable() -> None:
    """SG-7: cuando se evalúan, van de menor a mayor RMSE relativo ponderado.

    Tras el cierre del 08-08-2026 la salvaguarda solo se intenta si algún
    horizonte resulta no calculable, y en el anexo de mayo eso ya no ocurre.
    La prueba comprueba el orden **cuando hay evaluación**, y que en su
    ausencia el diagnóstico sea coherente: nada intentado, nada sustituido.
    """
    serie = _serie_arena()
    if serie is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    resultado = _proyectar(serie, 1)
    salvaguarda = resultado.get("salvaguarda_benchmark") or {}
    evaluados = salvaguarda.get("benchmarks_evaluados") or []
    if not evaluados:
        assert salvaguarda.get("intentada") is False, salvaguarda
        assert salvaguarda.get("activada") is False, salvaguarda
        assert salvaguarda.get("modelo_final") == salvaguarda.get("modelo_principal")
        return
    puntajes = [float(item.get("rmse_ponderado", float("inf"))) for item in evaluados]
    assert puntajes == sorted(puntajes), evaluados
    for item in evaluados:
        assert item.get("nombre") in {"drift", "naive"}


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: salvaguarda conservadora con benchmarks antes del bloqueo.")
