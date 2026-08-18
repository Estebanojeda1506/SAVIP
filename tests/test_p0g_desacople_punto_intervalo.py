"""P0-G: el punto y el intervalo son dos ejes distintos (G1-G10).

La revision independiente reabrio P0-G con un caso reproducible: n=8, dos pares
fuera de muestra, punto y metricas finitos, y aun asi `proyeccion_generada=False`.
Una limitacion del INTERVALO -cuyo metodo sigue sin sustento, P0-C abierto- vetaba
la entrega de un PRONOSTICO PUNTUAL calculable. REQ 14 lo prohibe expresamente:
«una deficiencia del intervalo no invalida automaticamente el pronostico puntual».

Estas diez pruebas fijan la separacion en las dos direcciones: lo que ya no puede
bloquear, y lo que debe seguir bloqueando.

Ejecucion directa, sin pytest:

    python tests/test_p0g_desacople_punto_intervalo.py
"""
from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica.criterios import (  # noqa: E402
    MIN_ITERACIONES_WF_ESCENARIO,
    MIN_OBS_MODELACION,
)
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    BANDA_LIMITES_INVERTIDOS,
    BANDA_LIMITES_NO_FINITOS,
    BANDA_NO_CALCULABLE,
    BANDA_SEMIANCHO_CERO,
    BANDA_VALIDA,
    PUNTO_NO_FINITO,
    _limites_auditoria_horizontes,
    clasificar_intervalo_por_cobertura,
    ejecutar_proyeccion,
    estado_banda,
)


def _serie(n: int, pendiente: float = 1.5, ruido: float = 0.0, semilla: int = 5) -> pd.DataFrame:
    generador = np.random.default_rng(semilla)
    valores = [
        100.0 + pendiente * i + (float(generador.normal(0, ruido)) if ruido else 0.0)
        for i in range(n)
    ]
    return pd.DataFrame(
        {"Periodo": [f"{2024 + i // 12}_{i % 12 + 1}" for i in range(n)], "Indice": valores}
    )


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def _clasificar(estado_banda_valor: str) -> dict:
    """Clasifica un horizonte con el punto finito, variando solo la banda."""
    from app_icociv.proyeccion.servicio_proyeccion import _clasificar_evidencia_horizonte
    return _clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": estado_banda_valor,
                               "ancho_relativo_95_maximo": 0.1},
    )


def _pares(n: int, horizonte: int) -> int:
    return n - _limites_auditoria_horizontes(n)[0] - horizonte + 1


def _proyectar(n: int, horizonte: int = 1, **kwargs) -> dict:
    serie = _serie(n, **kwargs)
    return ejecutar_proyeccion(serie, *_objetivo(serie, horizonte), 2021)


def _proyectar_interno(n: int, horizonte: int = 1) -> dict:
    """El resultado ANTES del corte de publicacion C2, con la banda visible.

    `ejecutar_proyeccion` retira los limites del objeto publico (P0-C, C2). Las
    propiedades de P0-G que hablan de si la banda pudo construirse siguen siendo
    ciertas y siguen importando: se observan aqui, reproduciendo la composicion
    de la funcion publica sin su ultimo paso.
    """
    from app_icociv.proyeccion.servicio_proyeccion import (
        _ejecutar_proyeccion_base,
        _estructurar_resultado_horizontes,
    )
    serie = _serie(n)
    anio, mes = _objetivo(serie, horizonte)
    base = _ejecutar_proyeccion_base(
        serie_df=serie, year_proj=anio, month_proj=mes, anio_base=2021
    )
    return _estructurar_resultado_horizontes(base, "predeterminado")


# ==============================
# G1-G5: lo que YA NO puede bloquear
# ==============================


def test_g1_n8_dos_pares_entrega_el_punto_sin_banda() -> None:
    """G1. El caso exacto de la reapertura."""
    assert _pares(8, 1) == 2 < MIN_ITERACIONES_WF_ESCENARIO
    resultado = _proyectar(8)

    assert resultado["proyeccion_generada"] is True, resultado.get("explicacion")
    solicitado = resultado["resultado_horizonte_solicitado"]
    punto = solicitado["indice_proyectado"]
    assert punto is not None and math.isfinite(float(punto)), punto
    # El intervalo NO se fabrica: se declara ausente.
    assert resultado["intervalo_sustentado"] is False
    proyecciones = resultado["proyecciones"]
    assert len(proyecciones) == 1
    # P0-C / C2, 15-08-2026. Antes se comprobaba aqui que los limites PUBLICADOS
    # fueran no finitos. Desde el retiro C2 el objeto publico no entrega limites
    # en ningun caso, de modo que esa comprobacion ya no distingue este caso de
    # cualquier otro: pasaria siempre. La propiedad de G1 -con dos pares la banda
    # no puede construirse- se comprueba donde sigue siendo observable, en el
    # resultado ANTERIOR al corte de publicacion.
    for columna in ("limite_inferior_95", "limite_superior_95"):
        assert proyecciones[columna].iloc[0] is None, (columna, proyecciones[columna].iloc[0])
    interno = _proyectar_interno(8)
    for columna in ("limite_inferior_95", "limite_superior_95"):
        valor = float(interno["proyecciones"][columna].iloc[0])
        assert not math.isfinite(valor), (columna, valor)


def test_g2_dos_frente_a_tres_pares_solo_cambia_el_intervalo() -> None:
    """G2. Pasar de 2 a 3 ventanas no puede *crear* la existencia del punto."""
    assert _pares(8, 1) == 2 and _pares(9, 1) == 3
    con_dos, con_tres = _proyectar(8), _proyectar(9)

    for resultado in (con_dos, con_tres):
        assert resultado["proyeccion_generada"] is True
        assert math.isfinite(float(resultado["resultado_horizonte_solicitado"]["indice_proyectado"]))
    # Lo que si cambia es la evaluabilidad del intervalo. Se mide antes del corte
    # de publicacion C2: despues de el, ningun caso entrega limites y la
    # diferencia entre dos y tres ventanas dejaria de ser observable aqui.
    inferior_dos = float(_proyectar_interno(8)["proyecciones"]["limite_inferior_95"].iloc[0])
    inferior_tres = float(_proyectar_interno(9)["proyecciones"]["limite_inferior_95"].iloc[0])
    assert not math.isfinite(inferior_dos), inferior_dos
    assert math.isfinite(inferior_tres), inferior_tres
    # Y ninguno de los dos publica esa banda: el corte C2 no depende del caso.
    for resultado in (con_dos, con_tres):
        assert resultado["proyecciones"]["limite_inferior_95"].iloc[0] is None
    # Y en ninguno de los dos el intervalo queda sustentado: P0-C sigue abierto.
    assert con_dos["intervalo_sustentado"] is False
    assert con_tres["intervalo_sustentado"] is False


def test_g3_no_hay_salto_global_en_el_literal_ocho() -> None:
    """G3. `MIN_OBS_MODELACION = 8` deja de ser puerta global.

    Se comprueba sobre n = 8 y n = 9 -por encima y por debajo del antiguo corte-
    que el comportamiento sea continuo. n = 7 se documenta aparte: alli el limite
    lo pone la aritmetica (`_pares(7, 1) = 1`), no el literal.
    """
    assert MIN_OBS_MODELACION == 8
    for n in (8, 9, 10):
        resultado = _proyectar(n)
        assert resultado["proyeccion_generada"] is True, (n, resultado.get("explicacion"))
        punto = resultado["resultado_horizonte_solicitado"]["indice_proyectado"]
        assert math.isfinite(float(punto)), (n, punto)
    # La longitud corta se comunica como advertencia, no como razon de bloqueo.
    factibilidad = _proyectar(8)["factibilidad"]
    assert not factibilidad.get("razones_tecnicas"), factibilidad.get("razones_tecnicas")


def test_g4_un_intervalo_no_sustentado_no_reduce_el_horizonte() -> None:
    """G4. Con P0-C abierto, todos los horizontes medibles siguen disponibles."""
    resultado = _proyectar(30, horizonte=3, ruido=0.4)
    assert resultado["intervalo_sustentado"] is False
    info = resultado["horizonte_info"]
    _, maximo_por_datos, _, _ = _limites_auditoria_horizontes(30)
    evaluados = [int(e["horizonte"]) for e in (info.get("evaluaciones") or [])]
    assert max(evaluados) == maximo_por_datos, (max(evaluados), maximo_por_datos)
    assert int(resultado["horizonte_permitido"]) == 3


def test_g5_cobertura_no_evaluable_no_cancela_la_entrega() -> None:
    """G5. La cobertura que no puede medirse no vuelve la entrega imposible."""
    clasificacion = clasificar_intervalo_por_cobertura(
        {"verificable": False, "cobertura_95_minima": None},
        errores_por_horizonte={1: np.arange(2, dtype=float)},
    )
    assert clasificacion["cobertura_minima"] is None
    assert clasificacion["degrada_a_escenario"] is False, clasificacion
    # Y no se afirma ninguna cobertura que no se haya medido.
    texto = f"{clasificacion['etiqueta']} {clasificacion['advertencia']}".lower()
    for prohibida in ("garantiza", "validad", "asegurad"):
        assert prohibida not in texto, (prohibida, texto)

    resultado = _proyectar(8)
    assert resultado["proyeccion_generada"] is True


# ==============================
# G6-G7: lo que SIGUE bloqueando
# ==============================


def test_g6_los_limites_invertidos_se_clasifican_sin_bloquear_el_punto() -> None:
    """G6, reescrito por P0-C ruta C2 (14-08-2026).

    Antes exigia que unos limites invertidos BLOQUEARAN. Era correcto mientras el
    intervalo formaba parte del producto: sin banda valida no habia resultado
    completo que entregar. Retirado el intervalo (C2), un fallo aritmetico de un
    objeto que **ya no se publica** no puede cancelar un pronostico finito.

    Se conserva lo sustantivo: el estado se sigue **clasificando** y se distingue
    de un semiancho nulo, que no es imposible sino nulo. Lo que cambia es su
    consecuencia.
    """
    assert estado_banda(110.0, 90.0, pronostico=100.0, n_errores=5) == BANDA_LIMITES_INVERTIDOS
    assert estado_banda(100.0, 100.0, pronostico=100.0, n_errores=5) == BANDA_SEMIANCHO_CERO
    assert estado_banda(90.0, 110.0, pronostico=100.0, n_errores=5) == BANDA_VALIDA
    # Con el punto finito, ninguno de los estados de BANDA cancela el horizonte.
    for estado in (BANDA_LIMITES_INVERTIDOS, BANDA_LIMITES_NO_FINITOS,
                   BANDA_NO_CALCULABLE, BANDA_SEMIANCHO_CERO):
        assert _clasificar(estado)["permitido"] is True, estado


def test_g7_un_punto_no_finito_sigue_bloqueando() -> None:
    """G7, reescrito por P0-C ruta C2: la imposibilidad DEL PUNTO se nombra aparte.

    Antes, un pronostico no finito y unos limites no finitos devolvian el MISMO
    codigo, de modo que el consumidor no podia distinguir cual objeto era
    imposible. Con el intervalo retirado esa fusion pasa a ser un defecto: haria
    que un fallo de la banda cancelara el punto.

    `PUNTO_NO_FINITO` no introduce ningun umbral: es la clasificacion logica de
    `math.isfinite` sobre el valor que SI se publica.
    """
    for punto in (float("inf"), float("nan")):
        assert estado_banda(90.0, 110.0, pronostico=punto, n_errores=5) == PUNTO_NO_FINITO
    # Y sigue bloqueando, que es lo que G-A protege.
    assert _clasificar(PUNTO_NO_FINITO)["permitido"] is False

    # Los limites no finitos se clasifican aparte y NO bloquean.
    for limite in (float("inf"), float("nan")):
        assert estado_banda(limite, 110.0, pronostico=100.0, n_errores=5) == BANDA_LIMITES_NO_FINITOS
    assert _clasificar(BANDA_LIMITES_NO_FINITOS)["permitido"] is True

    # Sin errores del paso no hay banda que construir, y eso se nombra aparte.
    assert estado_banda(90.0, 110.0, pronostico=100.0, n_errores=0) == BANDA_NO_CALCULABLE


# ==============================
# G8-G10: lo que debe declararse
# ==============================


def test_g8_p0c_se_declara_y_nada_se_presenta_como_validado() -> None:
    """G8. El intervalo no sustentado se dice, y no se llama validado."""
    resultado = _proyectar(8)
    assert resultado["intervalo_sustentado"] is False
    assert str(resultado.get("motivo_intervalo_no_sustentado") or "").strip()
    assert "P0-C" in (resultado.get("bloqueos_metodologicos") or {})
    assert resultado["estado_metodologico"] != "resultado_metodologicamente_sustentado"

    texto = " ".join(str(a) for a in (resultado["factibilidad"].get("advertencias") or [])).lower()
    for prohibida in ("validado", "certificad", "garantiza"):
        assert prohibida not in texto, (prohibida, texto)


def test_g9_p0e_marca_la_evidencia_como_provisional() -> None:
    """G9. Mientras P0-E siga bloqueado, la evidencia OOS es provisional."""
    for n in (8, 9, 30):
        resultado = _proyectar(n)
        assert resultado["evidencia_oos_provisional"] is True, n
        assert "P0-E" in (resultado.get("bloqueos_metodologicos") or {}), n


def test_g10_los_diagnosticos_no_vetan() -> None:
    """G10. Un diagnostico desfavorable informa; no cancela el pronostico."""
    resultado = _proyectar(30, ruido=6.0, semilla=17)
    assert resultado["proyeccion_generada"] is True, resultado.get("explicacion")
    factibilidad = resultado["factibilidad"]
    assert factibilidad["factible"] is True
    # Los diagnosticos viajan como advertencias, no como razones de bloqueo.
    assert not factibilidad.get("razones_tecnicas"), factibilidad.get("razones_tecnicas")
    assert factibilidad.get("advertencias")


def _ejecutar() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except Exception:
            fallos += 1
            print(f"  FALLA {prueba.__name__}")
            traceback.print_exc()
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} aprobadas")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
