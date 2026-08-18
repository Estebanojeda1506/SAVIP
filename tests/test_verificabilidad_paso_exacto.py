"""Pruebas dirigidas de la correccion RA-01 (reauditoria de 0.3.0-rc2).

La reauditoria independiente comprobo que el sistema podia declarar verificable
el conjunto porque *algun* horizonte reunia 16 errores fuera de muestra, aunque
el paso exacto solicitado tuviera menos. Cuatro salidas congeladas
(``C-01-h12``, ``C-03-h12``, ``C-04-h12``, ``C-09-h12``) quedaron como
proyeccion tecnica con solo 15 errores en h=12.

Regla que se blinda aqui: la clasificacion del horizonte solicitado se evalua
con ``n_errores_oos_del_paso_exacto_solicitado >= 16``. Que otro paso llegue a
16 no verifica este paso. La cobertura minima global se conserva como dato
complementario y sigue siendo la magnitud comparada contra 0,90 y 0,80: es la
lectura conservadora de la banda, que cubre toda la trayectoria.

Ejecucion directa, sin pytest:

    python tests/test_verificabilidad_paso_exacto.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica.criterios import (  # noqa: E402
    MIN_ERRORES_COBERTURA_EMPIRICA,
)
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    _cobertura_empirica_intervalos,
    clasificar_intervalo_por_cobertura,
)


# ==============================
# APOYOS
# ==============================


def errores(n: int, semilla: int, escala: float = 1.0) -> np.ndarray:
    """Errores walk-forward reproducibles, sin dependencia del reloj ni de disco."""
    generador = np.random.default_rng(semilla)
    return generador.normal(0.0, escala, size=int(n))


def clasificar(errores_por_horizonte: dict[int, np.ndarray], paso: int) -> dict:
    """Cadena completa de produccion: cobertura -> clasificacion."""
    cobertura = _cobertura_empirica_intervalos(errores_por_horizonte, paso_exacto=paso)
    return clasificar_intervalo_por_cobertura(cobertura, errores_por_horizonte)


def cobertura_forzada(minima: float | None, n_paso: int, paso: int = 12) -> dict:
    """Objeto de cobertura con la cobertura global fijada y el paso exacto dado.

    Permite ejercer los tres tramos de umbral sin depender de que una muestra
    aleatoria caiga exactamente en 0,92 / 0,85 / 0,75.
    """
    return {
        "verificable": minima is not None,
        "cobertura_95_minima": minima,
        "por_horizonte": [],
        "paso_exacto": int(paso),
        "n_errores_paso_exacto": int(n_paso),
        "min_errores_exigidos": int(MIN_ERRORES_COBERTURA_EMPIRICA),
        "verificable_paso_exacto": int(n_paso) >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "cobertura_95_paso_exacto": minima,
    }


# =========================================================
# 1. h=1 con 20 errores y h=2 con 15: h=2 no es verificable
# =========================================================


def test_h2_con_15_errores_no_hereda_la_verificabilidad_de_h1():
    """El caso refutatorio exacto de la reauditoria."""
    mapa = {1: errores(20, semilla=101), 2: errores(15, semilla=102)}

    en_h1 = clasificar(mapa, paso=1)
    assert en_h1["verificable_paso_exacto"] is True, en_h1
    assert en_h1["clasificacion_interna"] != "no_verificable", en_h1
    assert en_h1["n_errores_paso_exacto"] == 20, en_h1

    en_h2 = clasificar(mapa, paso=2)
    # CIERRE 08-08-2026: la muestra reducida se declara y no degrada. Lo que la
    # prueba sigue fijando -y es lo suyo- es que el paso solicitado se evalua
    # con SU propia muestra, no con la de otro horizonte.
    assert en_h2["clasificacion_interna"] == "medida_con_muestra_reducida", en_h2
    assert en_h2["verificable_paso_exacto"] is False, en_h2
    assert en_h2["n_errores_paso_exacto"] == 15, en_h2
    assert en_h2["degrada_a_escenario"] is False, en_h2
    assert en_h2["cobertura_observada"] is not None, en_h2


def test_el_mensaje_de_h2_nombra_el_paso_y_no_culpa_al_conjunto():
    mapa = {1: errores(20, semilla=101), 2: errores(15, semilla=102)}
    resultado = clasificar(mapa, paso=2)
    texto = resultado["advertencia"].lower()
    assert "h=2" in texto, texto
    assert "15" in texto, texto
    assert str(MIN_ERRORES_COBERTURA_EMPIRICA) in texto, texto
    # CIERRE 08-08-2026: el mensaje ya no explica por que el paso NO se verifica
    # -porque ya no se degrada por eso-, sino con que tamano de muestra se midio.
    assert "muestra reducida" in texto, texto


def test_la_cobertura_expone_el_detalle_del_paso_exacto():
    mapa = {1: errores(20, semilla=101), 2: errores(15, semilla=102)}
    cobertura = _cobertura_empirica_intervalos(mapa, paso_exacto=2)
    assert cobertura["paso_exacto"] == 2
    assert cobertura["n_errores_paso_exacto"] == 15
    assert cobertura["verificable_paso_exacto"] is False
    assert cobertura["min_errores_exigidos"] == MIN_ERRORES_COBERTURA_EMPIRICA
    # La cobertura global sigue existiendo como dato complementario.
    assert cobertura["verificable"] is True, "h=1 si es medible y su cobertura se conserva"
    assert cobertura["cobertura_95_minima"] is not None


# ==================================================
# 2. h=12 con 15 errores: escenario, no proyeccion
# ==================================================


def test_h12_con_15_errores_se_mide_y_se_publica_con_su_muestra():
    """CIERRE 08-08-2026: 15 errores miden la cobertura; no la invalidan."""
    mapa = {h: errores(30 - h, semilla=200 + h) for h in range(1, 13)}
    assert len(mapa[12]) == 18
    mapa[12] = errores(15, semilla=999)

    resultado = clasificar(mapa, paso=12)
    assert resultado["clasificacion_interna"] == "medida_con_muestra_reducida", resultado
    assert resultado["degrada_a_escenario"] is False, resultado
    assert resultado["n_errores_paso_exacto"] == 15, resultado
    assert resultado["cobertura_observada"] is not None, resultado


# =========================================================
# 3-5. h=12 con 16 errores: los tres tramos de cobertura
# =========================================================


def test_h12_con_16_errores_y_cobertura_092_es_nominal():
    resultado = clasificar_intervalo_por_cobertura(cobertura_forzada(0.92, n_paso=16))
    assert resultado["clasificacion_interna"] == "nominal", resultado
    assert resultado["degrada_a_escenario"] is False, resultado
    assert resultado["advertencia"] == "", resultado
    assert resultado["verificable_paso_exacto"] is True


def test_h12_con_16_errores_y_cobertura_085_es_admisible_con_advertencia():
    resultado = clasificar_intervalo_por_cobertura(cobertura_forzada(0.85, n_paso=16))
    assert resultado["clasificacion_interna"] == "admisible_con_advertencia", resultado
    assert resultado["degrada_a_escenario"] is False, resultado
    assert resultado["advertencia"].strip(), resultado


def test_h12_con_16_errores_y_cobertura_075_se_advierte_y_no_degrada():
    """CIERRE 08-08-2026: el tercer tramo pasa de degradar a advertir."""
    resultado = clasificar_intervalo_por_cobertura(cobertura_forzada(0.75, n_paso=16))
    assert resultado["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", resultado
    assert resultado["degrada_a_escenario"] is False, resultado
    assert "75%" in resultado["advertencia"], resultado
    assert resultado["cobertura_observada"] == 0.75


def test_el_minimo_de_16_sigue_siendo_inclusivo_como_referencia():
    """CIERRE 08-08-2026: 16 sigue separando dos redacciones; ya no dos estados.

    El corte conserva su valor y su inclusividad -16 basta, 15 no-, pero lo que
    cambia entre las dos ramas es la advertencia, no la decision: ninguna de las
    dos degrada el horizonte.
    """
    justo = clasificar_intervalo_por_cobertura(cobertura_forzada(0.92, n_paso=16))
    assert justo["clasificacion_interna"] == "nominal", justo
    debajo = clasificar_intervalo_por_cobertura(cobertura_forzada(0.92, n_paso=15))
    assert debajo["clasificacion_interna"] == "medida_con_muestra_reducida", debajo
    assert justo["degrada_a_escenario"] is False
    assert debajo["degrada_a_escenario"] is False
    assert debajo["cobertura_observada"] == 0.92


# =========================================================
# 6. Los cuatro casos senalados por la reauditoria
# =========================================================

# Errores fuera de muestra del paso exacto y cobertura minima global tal como
# los midio la reauditoria independiente en RESULTADOS_COBERTURA.csv. Los cuatro
# quedaban como proyeccion tecnica en rc2 pese a tener 15 errores en h=12.
CASOS_REAUDITORIA = {
    "C-01-h12": {"n": 15, "cobertura_global": 0.916667, "rc2": "nominal"},
    "C-03-h12": {"n": 15, "cobertura_global": 0.875000, "rc2": "admisible_con_advertencia"},
    "C-04-h12": {"n": 15, "cobertura_global": 1.000000, "rc2": "nominal"},
    "C-09-h12": {"n": 15, "cobertura_global": 1.000000, "rc2": "nominal"},
}


def test_los_cuatro_casos_de_la_reauditoria_publican_su_muestra():
    """Los cuatro casos de h=12 con 15 errores, en su tercera version.

    * En rc2 se clasificaban por su cobertura global -1,000 o 0,875- y salian
      como `nominal` o `admisible_con_advertencia`: se les atribuia una
      verificacion que su paso no tenia.
    * La remediacion del 29-07-2026 los paso a `no_verificable` y los degrado a
      escenario, con el corte de 16 errores.
    * El CIERRE del 08-08-2026 retira ese corte, que no tiene fuente. Los cuatro
      vuelven a entregarse, pero **ya no se les atribuye nada**: se publica la
      cobertura de SU paso, con SU tamano de muestra declarado.

    Lo que la reauditoria pedia -que no se afirmara una verificacion inexistente-
    se cumple mejor asi: antes se ocultaba el dato; ahora se publica con su
    limitacion.
    """
    for caso, datos in CASOS_REAUDITORIA.items():
        resultado = clasificar_intervalo_por_cobertura(
            cobertura_forzada(datos["cobertura_global"], n_paso=datos["n"], paso=12)
        )
        assert resultado["clasificacion_interna"] == "medida_con_muestra_reducida", (caso, resultado)
        assert resultado["degrada_a_escenario"] is False, (caso, resultado)
        assert resultado["clasificacion_interna"] != datos["rc2"], (
            f"{caso} conserva la clasificacion defectuosa de rc2"
        )
        assert resultado["verificable_paso_exacto"] is False, (caso, resultado)
        assert resultado["n_errores_paso_exacto"] == datos["n"], (caso, resultado)
        assert resultado["cobertura_observada"] is not None, (
            f"{caso} no debe publicar una cobertura como verificada"
        )


def test_el_paso_se_evalua_con_su_propia_muestra():
    """La cobertura global no sustituye a la del paso: cada paso lleva la suya.

    CIERRE 08-08-2026: con 15 errores el paso ya no se degrada, pero sigue
    declarando su propio tamano de muestra y su propia medicion. Lo que la
    prueba vigila -que no se importe la evidencia de otro horizonte- se
    mantiene.
    """
    resultado = clasificar_intervalo_por_cobertura(
        cobertura_forzada(1.0, n_paso=15, paso=12)
    )
    assert resultado["clasificacion_interna"] == "medida_con_muestra_reducida", resultado
    assert resultado["degrada_a_escenario"] is False, resultado
    assert resultado["n_errores_paso_exacto"] == 15, resultado


# =========================================================
# Blindajes de alcance: la correccion no toca nada mas
# =========================================================


def test_la_correccion_no_altera_pronosticos_ni_limites():
    """Clasificar no escribe en la entrada ni produce numeros de intervalo."""
    entrada = cobertura_forzada(0.92, n_paso=15)
    copia = dict(entrada)
    resultado = clasificar_intervalo_por_cobertura(entrada)
    assert entrada == copia, "la clasificacion no debe mutar la cobertura recibida"
    prohibidas = {"limite_inferior", "limite_superior", "y_proj", "q95", "sigma_h"}
    assert not prohibidas & set(resultado), resultado


def test_sin_paso_exacto_se_conserva_el_comportamiento_anterior():
    """Compatibilidad: los usos que no informan el paso siguen usando el global."""
    resultado = clasificar_intervalo_por_cobertura(
        {"verificable": True, "cobertura_95_minima": 0.92}
    )
    assert resultado["clasificacion_interna"] == "nominal", resultado
    assert resultado["paso_exacto"] is None, resultado


def test_ninguna_clasificacion_promete_garantia():
    prohibidas = ("garantiza", "garantía", "garantia", "exactamente el 95", "conformal")
    for minima, n in ((None, 15), (0.75, 16), (0.85, 16), (0.92, 16), (1.0, 15)):
        resultado = clasificar_intervalo_por_cobertura(cobertura_forzada(minima, n_paso=n))
        texto = f"{resultado['etiqueta']} {resultado['advertencia']}".lower()
        for palabra in prohibidas:
            assert palabra not in texto, (minima, n, palabra, texto)


# ==============================
# CORREDOR
# ==============================


def main() -> int:
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for prueba in pruebas:
        try:
            prueba()
            print(f"  OK    {prueba.__name__}")
        except Exception:
            fallos += 1
            print(f"  FALLA {prueba.__name__}")
            traceback.print_exc()
    total = len(pruebas)
    print(f"\n{total - fallos}/{total} pruebas de verificabilidad del paso exacto")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
