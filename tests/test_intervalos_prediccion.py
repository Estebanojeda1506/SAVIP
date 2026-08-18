"""Pruebas del intervalo de predicción del 95% recalibrado (decisión D-2).

Diseño aprobado: cada paso p de la trayectoria usa los errores fuera de
muestra del backtesting a horizonte exactamente p; con 10+ errores se usan
percentiles empíricos centrados, con 3–9 un intervalo t de Student
(más ancho, conservador), y con menos de 3 el paso no es calculable
(se elimina la banda fabricada de «escala mínima» de ±2.77%). La amplitud
es no decreciente con el paso y la cobertura empírica se comprueba y reporta.
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
    _cobertura_empirica_intervalos,
    _intervalos_prediccion,
)


def _errores_lineales(amplitud: float, n: int) -> np.ndarray:
    return np.linspace(-amplitud, amplitud, n)


def test_contencion_y_limites_validos() -> None:
    """IP-1: lo95 <= lo80 <= pred <= hi80 <= hi95 y límite inferior >= 0."""
    y = np.array([100.0, 101.0, 102.0])
    errores = {1: _errores_lineales(2.0, 20), 2: _errores_lineales(3.0, 20), 3: _errores_lineales(4.0, 15)}
    intervalos = _intervalos_prediccion(y, errores)
    assert len(intervalos) == 3
    for paso, (pred, item) in enumerate(zip(y, intervalos), start=1):
        lo95, hi95 = float(item["limite_inferior_95"]), float(item["limite_superior_95"])
        lo80, hi80 = float(item["limite_inferior_80"]), float(item["limite_superior_80"])
        assert lo95 <= lo80 <= pred <= hi80 <= hi95, (paso, item)
        assert lo95 >= 0.0


def test_errores_separados_por_horizonte() -> None:
    """IP-2: el paso p usa la distribución de errores del horizonte p."""
    y = np.array([100.0, 100.0])
    errores = {1: _errores_lineales(1.0, 21), 2: _errores_lineales(5.0, 21)}
    intervalos = _intervalos_prediccion(y, errores)
    ancho1 = float(intervalos[0]["limite_superior_95"]) - float(intervalos[0]["limite_inferior_95"])
    ancho2 = float(intervalos[1]["limite_superior_95"]) - float(intervalos[1]["limite_inferior_95"])
    # p2.5/p97.5 de +-5 con 21 puntos: semiancho 4.75; de +-1: 0.95.
    assert ancho2 > ancho1 * 3.0, (ancho1, ancho2)
    assert int(intervalos[0]["errores_oos_disponibles"]) == 21


def test_muestra_pequena_ensancha_por_sigma_estimada() -> None:
    """IP-3. AUDITORIA 09-08-2026 (P0-C). Antes fijaba el max(cuantil, t).

    La construccion vigente es la de FPP3 5.5: yhat +- c*sigma_h, con sigma_h la
    raiz del error cuadratico medio de los errores del paso. Como sigma_h se
    ESTIMA, el multiplicador exacto bajo el supuesto de normalidad de la fuente
    es el cuantil de una t con n grados de libertad, no el de la normal.

    Se conserva lo que la prueba verificaba de fondo -que con muestra pequena la
    banda es estrictamente mas ancha que la normal y se advierte- y se sustituye
    la formula esperada.
    """
    try:
        from scipy.stats import t as t_dist
    except Exception:
        print("SKIP: scipy no disponible.")
        return
    y = np.array([100.0])
    e = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    item = _intervalos_prediccion(y, {1: e})[0]
    sigma = float(np.sqrt(np.mean(e ** 2)))
    semiancho = float(item["limite_superior_95"]) - 100.0
    esperado = float(t_dist.ppf(0.975, len(e))) * sigma
    assert abs(semiancho - esperado) < 1e-9, (semiancho, esperado)
    assert semiancho > 1.96 * sigma, "con sigma estimada la banda supera al multiplicador normal"
    # ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 1). La advertencia decia
    # «Muestra de errores reducida (n=5): sigma se estima con pocos errores y el
    # nivel nominal supone ademas una distribucion aproximadamente normal. La
    # cobertura efectiva puede diferir...». Publicaba sigma_h, el nivel nominal y
    # la cobertura del intervalo retirado en cinco superficies publicas.
    #
    # El HECHO que informaba -cuantos errores fuera de muestra reune el paso- si
    # es del usuario y se conserva, con el numero. Lo que cambia es el
    # vocabulario. La prueba sigue exigiendo que la advertencia EXISTA y que
    # declare el tamano de la muestra; ya no exige la palabra retirada.
    advertencia = str(item["advertencia_evidencia_oos"]).lower()
    assert "limitada" in advertencia, item["advertencia_evidencia_oos"]
    assert f"n={len(e)}" in advertencia, item["advertencia_evidencia_oos"]
    for retirado in ("σ", "nivel nominal", "cobertura"):
        assert retirado not in advertencia, (
            f"la advertencia volvio a publicar «{retirado}»: {item['advertencia_evidencia_oos']}"
        )


def test_las_colas_pesadas_ensanchan_la_banda() -> None:
    """AUDITORIA 09-08-2026 (P0-C). Antes fijaba que el cuantil ganara el max().

    Retirada la combinacion, lo que se conserva es la propiedad de fondo: unos
    pocos errores muy grandes deben ensanchar la banda. Con sigma_h = RMS eso
    ocurre por construccion, porque el RMS pondera los errores al cuadrado.
    """
    y = np.array([100.0])
    e = np.concatenate([np.zeros(25), np.array([12.0, -12.0])])
    item = _intervalos_prediccion(y, {1: e})[0]
    sigma = float(np.sqrt(np.mean(e ** 2)))
    semiancho = float(item["limite_superior_95"]) - 100.0
    assert semiancho >= 1.96 * sigma, (semiancho, sigma)
    assert "5.5" in str(item["metodo"]) or "sigma" in str(item["metodo"]).lower()

    # Sin las dos colas la banda es estrictamente mas estrecha.
    sin_colas = _intervalos_prediccion(y, {1: np.concatenate([np.zeros(25), np.array([0.4, -0.4])])})[0]
    assert (float(sin_colas["limite_superior_95"]) - 100.0) < semiancho


def test_el_sesgo_ensancha_la_banda_pero_no_la_desplaza() -> None:
    """AUDITORIA 09-08-2026 (P0-C). Antes exigia que la banda se DESPLAZARA.

    FPP3 5.4 es taxativo: «If the residuals have mean m, then simply add m to
    all forecasts and the bias problem is solved». El remedio del sesgo
    corresponde al PRONOSTICO, no al intervalo. Desplazar la banda por la media
    del error disimulaba el sesgo dentro del intervalo y obligaba ademas a una
    correccion posterior para que el pronostico publicado no quedara fuera de su
    propia banda.

    Lo que se conserva: el pronostico queda dentro de la banda -ahora por
    construccion, al centrarse en el- y el sesgo no pasa inadvertido, porque
    sigma_h usa SUM e^2 y por tanto lo absorbe ENSANCHANDO.
    """
    y = np.array([100.0])
    e = np.full(25, 3.0) + np.linspace(-0.5, 0.5, 25)  # el modelo subestima siempre
    item = _intervalos_prediccion(y, {1: e})[0]
    lo95, hi95 = float(item["limite_inferior_95"]), float(item["limite_superior_95"])

    assert lo95 <= 100.0 <= hi95, item
    # Simetrica alrededor del pronostico: el sesgo NO desplaza la banda.
    assert abs((hi95 - 100.0) - (100.0 - lo95)) < 1e-9, (lo95, hi95)
    # Pero si la ensancha: el RMS supera a la desviacion tipica centrada.
    assert float(np.sqrt(np.mean(e ** 2))) > float(np.std(e, ddof=1))


def test_paso_sin_errores_no_fabrica_banda() -> None:
    """IP-4: sin errores OOS para un paso no se inventa una banda fija."""
    y = np.array([100.0, 101.0])
    try:
        _intervalos_prediccion(y, {1: _errores_lineales(1.0, 12)})
    except ValueError as exc:
        assert "paso" in str(exc).lower() or "errores" in str(exc).lower()
        return
    raise AssertionError("Debe rechazarse un paso sin errores OOS suficientes (min 3).")


def test_la_amplitud_de_cada_paso_refleja_su_propia_evidencia() -> None:
    """IP-5. AUDITORIA 09-08-2026 (P0-C). Antes fijaba una ENVOLVENTE MONOTONA.

    La version anterior exigia que la amplitud no decreciera con el paso, y la
    envolvente lo garantizaba copiando la anchura del paso anterior cuando el
    siguiente resultaba mas estrecho. Esa envolvente **no tenia fuente**: FPP3
    5.5 observa que sigma_h SUELE crecer con el horizonte, lo cual es una
    constatacion empirica y no una restriccion que deba imponerse. Al imponerla,
    la anchura declarada en un paso dejaba de depender de la evidencia de ese
    paso. Su fallo demostro que la envolvente si alteraba el resultado.

    Se conserva lo que la prueba verificaba de fondo -que la amplitud sale de
    los errores del paso exacto y no de una regla externa- y se sustituye la
    expectativa: cada paso declara la incertidumbre que SU muestra sostiene.
    """
    y = np.array([100.0, 100.0, 100.0])
    # h2 deliberadamente mas homogeneo que h1: la banda de h2 DEBE ser mas
    # estrecha, porque su evidencia lo es. No se hereda la anchura de h1.
    errores = {1: _errores_lineales(4.0, 20), 2: _errores_lineales(0.5, 20), 3: _errores_lineales(0.6, 20)}
    intervalos = _intervalos_prediccion(y, errores)
    anchos95 = [float(i["limite_superior_95"]) - float(i["limite_inferior_95"]) for i in intervalos]
    anchos80 = [float(i["limite_superior_80"]) - float(i["limite_inferior_80"]) for i in intervalos]

    assert anchos95[1] < anchos95[0], anchos95
    assert anchos95[2] > anchos95[1], anchos95
    # El intervalo del 80 % queda contenido en el del 95 % en cada paso, por
    # construccion: misma sigma_h y c80 < c95.
    for a80, a95 in zip(anchos80, anchos95):
        assert a80 < a95, (a80, a95)


def test_factor_calendario_escala_los_limites() -> None:
    """IP-8: los límites llevan el mismo factor multiplicativo que la trayectoria."""
    y_base = np.array([100.0, 101.0])
    errores = {1: _errores_lineales(2.0, 20), 2: _errores_lineales(2.5, 20)}
    factores = np.array([1.10, 1.10])
    sin_factor = _intervalos_prediccion(y_base, errores)
    con_factor = _intervalos_prediccion(y_base * factores, errores, factores_calendario=factores)
    for base, ajustado in zip(sin_factor, con_factor):
        for clave in ("limite_inferior_80", "limite_superior_80", "limite_inferior_95", "limite_superior_95"):
            assert abs(float(ajustado[clave]) - float(base[clave]) * 1.10) < 1e-9, clave


def test_cobertura_empirica_estructura_y_valores() -> None:
    """IP-6: la cobertura se evalua por origen movil y queda cerca del nominal.

    Actualizada el 04-08-2026 al integrar D-12b-C. La particion fija producia
    `n_calibracion` + `n_prueba` = n; el origen movil no parte la muestra: de n
    errores obtiene n-2 contrastes, porque el rango que evalua a cada error se
    construye con los anteriores y necesita dos para existir.
    """
    rng = np.random.default_rng(2026)
    errores = {h: rng.normal(0.0, 1.0 + 0.3 * h, 200) for h in (1, 2, 3)}
    cobertura = _cobertura_empirica_intervalos(errores)
    filas = cobertura.get("por_horizonte") or []
    assert len(filas) == 3, cobertura
    for fila in filas:
        assert "n_calibracion" not in fila, "el origen movil no calibra una mitad"
        assert int(fila["n_errores"]) == 200
        assert int(fila["n_prueba"]) == 198, fila
        assert fila["metodo"] == "origen_movil"
        assert 0.88 <= float(fila["cobertura_95"]) <= 1.0, fila
        assert 0.65 <= float(fila["cobertura_80"]) <= 0.95, fila
    assert cobertura.get("verificable") is True
    assert cobertura.get("metodo_evaluacion") == "origen_movil"


def test_cobertura_sin_muestra_es_honesta() -> None:
    """Sin muestra para evaluar no se afirma ninguna cobertura.

    Actualizada el 04-08-2026 al integrar D-12b-C. Con la particion fija hacian
    falta 16 errores para medir algo; el origen movil mide desde tres, de modo
    que la frontera de lo evaluable bajo. Lo que NO cambia es la honestidad:
    por debajo de la condicion de existencia no se afirma cobertura alguna, y
    una muestra pequena no vuelve verificable el paso solicitado.
    """
    # Dos errores: el rango no existe y no se evalua nada.
    sin_muestra = _cobertura_empirica_intervalos({1: _errores_lineales(1.0, 2)})
    assert sin_muestra.get("verificable") is False
    assert "no verificable" in str(sin_muestra.get("mensaje", "")).lower()
    assert not sin_muestra.get("por_horizonte")

    # Ocho errores: ya hay cobertura evaluada, pero el paso solicitado sigue sin
    # ser verificable, porque el minimo de 16 continua vigente (D-1b-B fuera).
    pocos = _cobertura_empirica_intervalos({1: _errores_lineales(1.0, 8)}, paso_exacto=1)
    assert pocos["por_horizonte"], "el origen movil si puede evaluar ocho errores"
    assert pocos["por_horizonte"][0]["n_prueba"] == 6
    assert pocos["verificable_paso_exacto"] is False
    assert pocos["n_errores_paso_exacto"] == 8


def test_proyeccion_reporta_cobertura_y_sin_banda_minima() -> None:
    """IP-7: el resultado expone la cobertura empírica y no usa la banda de escala mínima."""
    from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
    from app_icociv.utilidades.utilidades import ANIO_BASE

    valores, nivel = [], 100.0
    rng = np.random.default_rng(99)
    for i in range(48):
        nivel *= 1.004 + float(rng.normal(0.0, 0.0015))
        valores.append(nivel)
    periodos = [f"{2022 + i // 12}_{i % 12 + 1}" for i in range(48)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": valores})
    resultado = ejecutar_proyeccion(serie, 2026, 3, ANIO_BASE, origen_horizonte="manual")
    assert resultado.get("proyeccion_generada"), resultado.get("explicacion")
    assert "cobertura_empirica" in resultado, "El resultado debe reportar cobertura empírica."
    proyecciones = resultado["proyecciones"]
    metodos = " ".join(proyecciones["metodo_intervalo"].astype(str).unique())
    assert "escala mínima" not in metodos.lower(), metodos


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: intervalo de predicción del 95% por horizonte con cobertura verificada.")
