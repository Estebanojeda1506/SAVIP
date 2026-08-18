"""P0-C / C2 — bloqueo B1: el objeto publico no entrega la banda no sustentada.

Diez comprobaciones (T-OBJ-1..10) sobre `ejecutar_proyeccion`, la frontera
publica. Se escriben ANTES del cambio productivo y deben estar en rojo sobre el
estado actual en T-OBJ-1, T-OBJ-2 y T-OBJ-3.

Las siete restantes son la mitad que importa igual: comprueban que el corte
QUITA la banda y NO toca nada mas -punto, modelo, horizonte, metricas, muestra-,
y que las dos reglas de bloqueo siguen intactas en sus dos direcciones.

Criterio de la norma congelada al que responden:
    C6  Objeto publico no expone limites numericos.
    C9  Punto finito/calculable permanece publicable.
    C10 Falta de sustento del intervalo no bloquea por si sola el punto.
    C11 Punto no finito sigue bloqueando.
    C12/C13/C14 Modelo, horizonte, metricas y muestra intactos.

Ejecucion directa, sin pytest:

    python tests/test_p0c_objeto_publico_sin_intervalo.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.interfaz.controladores.controlador_principal import (  # noqa: E402
    ControladorPrincipal,
)
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    PUNTO_NO_FINITO,
    _clasificar_evidencia_horizonte,
    estado_banda,
)
from app_icociv.reportes import generador_reportes  # noqa: E402
from tests.test_p0c_retiro_intervalos_no_sustentados import (  # noqa: E402
    RUTA_JERARQUICA,
    _diferencias,
    _finito,
    _numeros_publicados_de_limite,
    _proyectar,
    _proyectar_interno,
    _serie,
)


_SERIE = _serie(48)
_HORIZONTE = 6
_CACHE: dict[str, dict] = {}


def _caso() -> tuple[dict, dict]:
    if not _CACHE:
        _CACHE["publico"] = _proyectar(_SERIE, _HORIZONTE)
        _CACHE["interno"] = _proyectar_interno(_SERIE, _HORIZONTE)
    return _CACHE["publico"], _CACHE["interno"]


def _limites_publicados(objeto, prefijo: str = "") -> list[tuple[str, float]]:
    return _numeros_publicados_de_limite(objeto, prefijo)


# ==============================
# T-OBJ-1 / T-OBJ-2 — ningun limite numerico publicado
# ==============================


def t_obj_1_sin_limite_inferior_numerico() -> None:
    publico, _ = _caso()
    inferiores = [
        (ruta, valor) for ruta, valor in _limites_publicados(publico, "resultado")
        if "inferior" in ruta or ruta.endswith("_lo") or ruta.endswith("[0]")
    ]
    assert not inferiores, f"El objeto publico entrega limite inferior: {inferiores[:6]}"


def t_obj_2_sin_limite_superior_numerico() -> None:
    publico, _ = _caso()
    superiores = [
        (ruta, valor) for ruta, valor in _limites_publicados(publico, "resultado")
        if "superior" in ruta or ruta.endswith("_hi") or ruta.endswith("[1]")
    ]
    assert not superiores, f"El objeto publico entrega limite superior: {superiores[:6]}"


# ==============================
# T-OBJ-3 — ninguna ruta publica alternativa los serializa
# ==============================


def t_obj_3_ninguna_ruta_alternativa_serializa_limites() -> None:
    publico, _ = _caso()

    # Ruta 1: el payload real que el controlador entrega a la interfaz.
    serializado = ControladorPrincipal._proyeccion_serializable(publico)
    fugas = _limites_publicados(serializado, "payload")
    assert not fugas, f"El payload de la interfaz serializa limites: {fugas[:6]}"

    # Ruta 2: el CSV reproducible.
    df = generador_reportes.construir_dataframe_reproducibilidad(_SERIE, publico, RUTA_JERARQUICA)
    fugas_csv = _limites_publicados(df, "csv")
    assert not fugas_csv, f"El CSV serializa limites: {fugas_csv[:6]}"

    # Ruta 3: la tabla publica convertida a registros, que es como viaja a la UI.
    registros = publico["proyecciones"].to_dict(orient="records")
    fugas_reg = _limites_publicados(registros, "registros")
    assert not fugas_reg, f"La tabla serializada entrega limites: {fugas_reg[:6]}"


# ==============================
# T-OBJ-4 — la declaracion de no sustento sigue siendo coherente
# ==============================


def t_obj_4_intervalo_sustentado_falso_y_coherente() -> None:
    publico, _ = _caso()
    assert publico.get("intervalo_sustentado") is False, \
        "P0-C sigue abierto: el intervalo no puede declararse sustentado."
    assert str(publico.get("motivo_intervalo_no_sustentado") or "").strip(), \
        "Se retira la banda sin decir por que."
    assert "P0-C" in (publico.get("bloqueos_metodologicos") or {}), \
        "El bloqueo P0-C dejo de viajar con el resultado."
    # Coherencia: no se declara sin sustento y se entrega el numero a la vez.
    assert not _limites_publicados(publico, "resultado"), \
        "Se declara el intervalo no sustentado y aun asi se entregan sus limites."


# ==============================
# T-OBJ-5..8 — el corte no mueve punto, modelo, horizonte ni metricas
# ==============================


def t_obj_5_punto_identico() -> None:
    publico, interno = _caso()
    assert _finito(publico.get("y_proj")), "El punto publicado dejo de ser finito."
    assert float(publico["y_proj"]) == float(interno["y_proj"]), \
        f"El punto cambio: {publico['y_proj']!r} vs {interno['y_proj']!r}"
    a = publico["proyecciones"]["indice_proyectado"].tolist()
    b = interno["proyecciones"]["indice_proyectado"].tolist()
    assert [repr(x) for x in a] == [repr(x) for x in b], "Cambio algun paso de la trayectoria."


def t_obj_6_modelo_identico() -> None:
    publico, interno = _caso()
    assert publico.get("model_name") == interno.get("model_name")
    assert publico.get("modelo_codigo") == interno.get("modelo_codigo")
    assert str(publico.get("model_name") or "").strip(), "El modelo dejo de publicarse."


def t_obj_7_horizonte_identico() -> None:
    publico, interno = _caso()
    for clave in ("horizonte_solicitado", "horizonte_permitido", "periodo_proj", "t_proj"):
        assert publico.get(clave) == interno.get(clave), f"Cambio '{clave}'."
    assert len(publico["proyecciones"]) == len(interno["proyecciones"])


def t_obj_8_metricas_oos_identicas() -> None:
    publico, interno = _caso()
    diferencias = _diferencias(publico, interno)
    assert not diferencias, f"El corte cambio campos que no son limites: {diferencias}"
    # Y explicitamente las metricas y el tamano de muestra del backtesting.
    mp = (publico.get("backtesting") or {}).get("metricas") or {}
    mi = (interno.get("backtesting") or {}).get("metricas") or {}
    assert repr(mp) == repr(mi), "Cambiaron las metricas OOS."
    assert (publico.get("backtesting") or {}).get("iteraciones") == \
        (interno.get("backtesting") or {}).get("iteraciones"), "Cambio el numero de ventanas."


# ==============================
# T-OBJ-9 / T-OBJ-10 — las dos direcciones del bloqueo
# ==============================


def t_obj_9_punto_no_finito_sigue_bloqueando() -> None:
    for punto in (float("nan"), float("inf"), float("-inf")):
        assert estado_banda(90.0, 110.0, punto) == PUNTO_NO_FINITO
    clasificacion = _clasificar_evidencia_horizonte(
        horizonte=6,
        modelo={"nombre": "drift", "nombre_visible": "Drift", "comparacion_benchmarks": {}},
        backtesting={"iteraciones": 24, "metricas": {
            "mape": 1.0, "smape": 1.0, "mase": 0.5, "mae": 1.0, "rmse": 1.2,
            "sesgo_medio": 0.0, "estabilidad_error": 0.3, "iteraciones": 24}},
        factibilidad={"factible": True, "razones_tecnicas": [], "advertencias": []},
        evaluacion_intervalos={"estado_banda": PUNTO_NO_FINITO, "ancho_relativo_95_maximo": 0.1},
    )
    assert not clasificacion.get("permitido_para_proyeccion_tecnica")
    assert not clasificacion.get("permitido_como_escenario")


def t_obj_10_banda_no_sustentada_no_bloquea_punto_finito() -> None:
    publico, _ = _caso()
    assert publico.get("proyeccion_generada") is True, \
        "Un punto finito dejo de publicarse por una banda sin sustento (REQ 14)."
    assert _finito(publico.get("y_proj"))
    solicitado = publico.get("resultado_horizonte_solicitado") or {}
    assert solicitado.get("proyeccion_generada") is True, \
        "La ficha del horizonte solicitado niega un punto calculable."
    assert _finito(solicitado.get("indice_proyectado")), \
        "La ficha no entrega el punto que si es publicable."


PRUEBAS = [
    ("T-OBJ-1", "No hay limite inferior numerico publico.", t_obj_1_sin_limite_inferior_numerico),
    ("T-OBJ-2", "No hay limite superior numerico publico.", t_obj_2_sin_limite_superior_numerico),
    ("T-OBJ-3", "Ninguna ruta publica alternativa serializa limites.",
     t_obj_3_ninguna_ruta_alternativa_serializa_limites),
    ("T-OBJ-4", "`intervalo_sustentado=False` permanece coherente.",
     t_obj_4_intervalo_sustentado_falso_y_coherente),
    ("T-OBJ-5", "Punto identico.", t_obj_5_punto_identico),
    ("T-OBJ-6", "Modelo identico.", t_obj_6_modelo_identico),
    ("T-OBJ-7", "Horizonte identico.", t_obj_7_horizonte_identico),
    ("T-OBJ-8", "Metricas OOS identicas.", t_obj_8_metricas_oos_identicas),
    ("T-OBJ-9", "Punto NaN/inf sigue bloqueando.", t_obj_9_punto_no_finito_sigue_bloqueando),
    ("T-OBJ-10", "Banda no sustentada no bloquea un punto finito.",
     t_obj_10_banda_no_sustentada_no_bloquea_punto_finito),
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
    print(f"\n{len(PRUEBAS) - fallos}/{len(PRUEBAS)} pruebas verdes, {fallos} fallo(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
