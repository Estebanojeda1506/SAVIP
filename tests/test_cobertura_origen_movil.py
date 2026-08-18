"""D-12b-C: evaluacion de cobertura por origen movil (integrada 04-08-2026).

Fija las propiedades que hacen valida la evaluacion —orden temporal, ausencia de
fuga, horizonte exacto— y las que garantizan que la integracion NO tocó el
producto: intervalos, modelos y pronosticos siguen igual, y D-1b-B sigue fuera.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica import criterios  # noqa: E402
from app_icociv.proyeccion import servicio_proyeccion as sp  # noqa: E402


def observaciones(errores, paso=1, desde=1):
    """Observaciones sinteticas ordenadas por origen creciente."""
    return [
        {
            "origen": f"2021_{desde + i:02d}",
            "fecha_origen": f"2021_{desde + i:02d}",
            "paso": paso,
            "fecha_objetivo": f"2022_{desde + i:02d}",
            "modelo": "drift",
            "pronostico": 100.0,
            "real": 100.0 + float(e),
            "error": float(e),
            "error_absoluto": abs(float(e)),
        }
        for i, e in enumerate(errores)
    ]


# ------------------------------------------------------- 1-3. fuga y orden
def test_no_hay_fuga_el_error_no_entra_en_su_propio_rango():
    """Un error enorme al final no puede ensanchar el rango que lo evalua."""
    normales = [0.1, -0.1, 0.12, -0.08, 0.09, -0.11]
    con_atipico = normales + [50.0]
    r = sp.evaluacion_cobertura_origen_movil({1: observaciones(con_atipico)}, paso_exacto=1)
    ultimo = [t for t in r["trazabilidad"] if t["incluido_evaluacion"]][-1]
    assert ultimo["error"] == 50.0
    assert ultimo["dentro_del_rango"] is False, (
        "si el error entrara en su propio rango, se cubriria a si mismo"
    )


def test_los_errores_futuros_no_se_consultan():
    """Anadir observaciones al final no cambia las evaluaciones anteriores."""
    base = [0.1, -0.2, 0.15, -0.05, 0.3]
    corta = sp.evaluacion_cobertura_origen_movil({1: observaciones(base)}, paso_exacto=1)
    larga = sp.evaluacion_cobertura_origen_movil(
        {1: observaciones(base + [9.0, -9.0])}, paso_exacto=1
    )
    previos_corta = [t for t in corta["trazabilidad"] if t.get("dentro_del_rango") is not None]
    previos_larga = [t for t in larga["trazabilidad"] if t.get("dentro_del_rango") is not None]
    for a, b in zip(previos_corta, previos_larga):
        assert a["dentro_del_rango"] == b["dentro_del_rango"]
        assert math.isclose(a["limite_superior_evaluacion"], b["limite_superior_evaluacion"])


def test_el_orden_temporal_se_respeta():
    r = sp.evaluacion_cobertura_origen_movil(
        {1: observaciones([0.1, -0.2, 0.15, -0.05, 0.3])}, paso_exacto=1
    )
    previos = [t["n_errores_previos"] for t in r["trazabilidad"]]
    assert previos == sorted(previos), "el numero de errores previos debe crecer"
    assert previos[0] == 0


# --------------------------------------------------- 4-5. horizonte exacto
def test_cada_horizonte_usa_solo_sus_errores():
    datos = {
        1: observaciones([0.1] * 8, paso=1),
        12: observaciones([5.0] * 8, paso=12),
    }
    r = sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=12)
    for fila in r["filas"]:
        assert fila["n_errores"] == 8
    for registro in r["trazabilidad"]:
        if registro["paso"] == 1:
            assert abs(registro["error"] - 0.1) < 1e-9
        else:
            assert abs(registro["error"] - 5.0) < 1e-9


def test_no_se_mezclan_pasos_en_el_rango():
    """h=12 con errores grandes no debe verse cubierto por el rango de h=1."""
    datos = {
        1: observaciones([0.01] * 10, paso=1),
        12: observaciones([0.01, 0.01, 8.0], paso=12),
    }
    r = sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=12)
    fila12 = [f for f in r["filas"] if f["horizonte"] == 12][0]
    assert fila12["cobertura_95"] == 0.0, "el 8.0 debe quedar fuera del rango de su propio paso"


# ------------------------------------------------ 6-8. casos no calculables
def test_ningun_error_no_es_calculable():
    r = sp.evaluacion_cobertura_origen_movil({1: []}, paso_exacto=1)
    assert r["filas"] == []
    assert r["cobertura_paso"] is None


def test_un_solo_error_no_es_calculable():
    r = sp.evaluacion_cobertura_origen_movil({1: observaciones([0.5])}, paso_exacto=1)
    assert r["filas"] == []
    registro = r["trazabilidad"][0]
    assert registro["estado_evaluacion"] == sp.EVAL_IMPOSIBLE
    assert registro["incluido_evaluacion"] is False
    assert "sin errores previos" in registro["motivo_exclusion"]


def test_dos_errores_dejan_el_segundo_sin_evaluar():
    r = sp.evaluacion_cobertura_origen_movil({1: observaciones([0.5, 0.6])}, paso_exacto=1)
    assert r["filas"] == []
    assert r["trazabilidad"][1]["motivo_exclusion"] == sp.MOTIVO_UN_PREVIO


def test_valores_no_finitos_se_declaran():
    """Error no finito con observacion real presente: el motivo es el error."""
    obs = observaciones([0.1, -0.1, 0.2, 0.0])
    obs[-1]["error"] = float("nan")  # `real` sigue siendo finito
    r = sp.evaluacion_cobertura_origen_movil({1: obs}, paso_exacto=1)
    ultimo = r["trazabilidad"][-1]
    assert ultimo["estado_evaluacion"] == sp.EVAL_IMPOSIBLE
    assert ultimo["motivo_exclusion"] == sp.MOTIVO_NO_FINITO


def test_observacion_sin_real_se_declara_aparte():
    """Si falta el valor real, el motivo es ese y no el del error."""
    obs = observaciones([0.1, -0.1, 0.2, 0.3])
    obs[-1]["real"] = float("nan")
    r = sp.evaluacion_cobertura_origen_movil({1: obs}, paso_exacto=1)
    assert r["trazabilidad"][-1]["motivo_exclusion"] == sp.MOTIVO_SIN_REAL


def test_observacion_sin_fecha_objetivo_se_excluye():
    obs = observaciones([0.1, -0.1, 0.2])
    obs[-1]["fecha_objetivo"] = ""
    r = sp.evaluacion_cobertura_origen_movil({1: obs}, paso_exacto=1)
    assert r["trazabilidad"][-1]["motivo_exclusion"] == sp.MOTIVO_SIN_FECHA


# ------------------------------------------------------ 9-11. comportamiento
def test_cambio_estructural_se_amortigua_y_se_puede_observar():
    """Limitacion declarada: el rango absorbe el cambio a medida que ocurre."""
    errores = [0.05] * 12 + [3.0] * 6
    r = sp.evaluacion_cobertura_origen_movil({1: observaciones(errores)}, paso_exacto=1)
    cobertura = r["filas"][0]["cobertura_95"]
    assert 0.0 < cobertura < 1.0


def test_cobertura_perfecta_con_errores_homogeneos():
    r = sp.evaluacion_cobertura_origen_movil(
        {1: observaciones(list(np.random.default_rng(4).normal(0.0, 0.05, 30)))}, paso_exacto=1
    )
    assert r["filas"][0]["cobertura_95"] >= 0.9


def test_cobertura_deficiente_con_dispersion_creciente():
    errores = [1e-3 * (60.0 ** i) for i in range(8)]
    r = sp.evaluacion_cobertura_origen_movil({1: observaciones(errores)}, paso_exacto=1)
    assert r["filas"][0]["cobertura_95"] == 0.0


# --------------------------------------------------------- 12-17. horizontes
def test_todos_los_horizontes_operativos_se_evaluan():
    rng = np.random.default_rng(21)
    # Tamanos reales del anexo: 26, 24, 21, 15 y 9 errores.
    datos = {
        h: observaciones(list(rng.normal(0.0, 0.3, n)), paso=h)
        for h, n in ((1, 26), (3, 24), (6, 21), (12, 15), (18, 9))
    }
    r = sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=18)
    evaluados = {f["horizonte"]: f["n_prueba"] for f in r["filas"]}
    assert set(evaluados) == {1, 3, 6, 12, 18}, (
        "h=12 y h=18 quedaban sin medir con la particion fija"
    )
    assert evaluados[18] == 7, "con 9 errores se obtienen 7 evaluaciones"
    assert evaluados[12] == 13


def test_faltantes_al_final_no_rompen_la_evaluacion():
    obs = observaciones([0.1, -0.1, 0.2, 0.15, float("nan"), float("nan")])
    r = sp.evaluacion_cobertura_origen_movil({1: obs}, paso_exacto=1)
    assert r["filas"], "los faltantes finales no deben anular la evaluacion previa"


def test_reproducibilidad():
    datos = {1: observaciones(list(np.random.default_rng(5).normal(0.0, 0.2, 20)))}
    a = sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=1)
    b = sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=1)
    assert a["filas"] == b["filas"]


# ------------------------------------------------ 19-21. metodo y D-1b-B
def test_el_metodo_visible_es_origen_movil():
    c = sp._cobertura_empirica_intervalos(
        {1: np.random.default_rng(6).normal(0.0, 0.3, 26)}, paso_exacto=1
    )
    assert c["metodo_evaluacion"] == "origen_movil"
    assert all(f["metodo"] == "origen_movil" for f in c["por_horizonte"])


def test_los_cortes_productivos_siguen_activos():
    """D-1b-B no se integra: 16, 0,90 y 0,80 siguen decidiendo."""
    assert criterios.MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert criterios.COBERTURA_IC95_ACEPTABLE == 0.90
    assert criterios.COBERTURA_IC95_ADVERTENCIA == 0.80
    assert sp.min_errores_cobertura_vigente() == 16


def test_el_minimo_de_16_sigue_gobernando_la_verificabilidad():
    quince = sp._cobertura_empirica_intervalos(
        {12: np.random.default_rng(7).normal(0.0, 0.3, 15)}, paso_exacto=12
    )
    assert quince["verificable_paso_exacto"] is False, "con 15 errores el paso no se verifica"
    assert quince["por_horizonte"], "pero su cobertura SI se evalua ahora"

    dieciseis = sp._cobertura_empirica_intervalos(
        {12: np.random.default_rng(7).normal(0.0, 0.3, 16)}, paso_exacto=12
    )
    assert dieciseis["verificable_paso_exacto"] is True


def test_las_etiquetas_de_cobertura_no_cambiaron():
    """No se introduce la distincion por n>=19 de D-1b-B.

    V-C anadio `banda_no_calculable`, que no es un corte de cobertura sino la
    ausencia de banda. El CIERRE del 08-08-2026 renombro las dos claves que
    dejaron de degradar -`cobertura_insuficiente` y `no_verificable`- por
    nombres que describen lo que son, mediciones y no veredictos, y separo de
    `no_verificable` el unico caso que sigue degradando: que la cobertura no sea
    calculable. Siguen siendo cinco claves y ninguna nueva por tamano de muestra.
    """
    esperadas = {
        "nominal", "admisible_con_advertencia", "cobertura_por_debajo_del_nominal",
        "medida_con_muestra_reducida", "no_calculable", "banda_no_calculable",
    }
    assert set(sp.ETIQUETA_VISIBLE_POR_CLASIFICACION) == esperadas
    for etiqueta in sp.ETIQUETA_VISIBLE_POR_CLASIFICACION.values():
        assert "cuantil" not in etiqueta.lower()


# ------------------------------------------- 22-24. el producto no cambia
def test_el_intervalo_entregado_no_depende_de_la_evaluacion():
    """La banda se construye con TODOS los errores del paso, no por origen movil."""
    errores = np.random.default_rng(8).normal(0.0, 0.4, 20)
    offsets_a, _, _, _ = sp._cuantiles_intervalo(errores)
    sp.evaluacion_cobertura_origen_movil({1: observaciones(list(errores))}, paso_exacto=1)
    offsets_b, _, _, _ = sp._cuantiles_intervalo(errores)
    assert offsets_a == offsets_b


def test_la_evaluacion_no_escribe_en_los_errores_recibidos():
    datos = {1: observaciones([0.1, -0.2, 0.3, -0.15])}
    copia = [dict(o) for o in datos[1]]
    sp.evaluacion_cobertura_origen_movil(datos, paso_exacto=1)
    for original, ahora in zip(copia, datos[1]):
        assert original == ahora, "la evaluacion no debe mutar sus insumos"


def test_la_trazabilidad_conserva_origen_y_fecha_objetivo():
    r = sp.evaluacion_cobertura_origen_movil(
        {6: observaciones([0.1, -0.1, 0.2, 0.05], paso=6)}, paso_exacto=6
    )
    for registro in r["trazabilidad"]:
        for campo in ("origen", "fecha_origen", "paso", "fecha_objetivo", "modelo",
                      "pronostico", "real", "error", "error_absoluto",
                      "n_errores_previos", "incluido_evaluacion", "motivo_exclusion"):
            assert campo in registro, campo
        assert registro["paso"] == 6


def _ejecutar() -> int:
    fallos = 0
    for nombre, prueba in sorted(globals().items()):
        if nombre.startswith("test_") and callable(prueba):
            try:
                prueba()
                print(f"  OK   {nombre}")
            except AssertionError as exc:
                fallos += 1
                print(f"  FALLA {nombre}: {exc}")
    print(f"\n{'todas las pruebas pasan' if not fallos else f'{fallos} fallidas'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
