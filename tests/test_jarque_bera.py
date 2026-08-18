"""Contraste de Jarque-Bera: estadístico, cola chi²(2) y decisión al 5 %.

Reescrito tras el hallazgo H-04 de la auditoría independiente. La versión
anterior de esta suite replicaba el mismo `ddof=1` que el código productivo
(`_jb_estadistico`), de modo que no podía detectar el defecto: prueba e
implementación compartían el error. Se conservan las comprobaciones de la cola
chi²(2) y de la política de muestra insuficiente, que sí eran correctas.

Ahora el oráculo es externo (`scipy.stats.jarque_bera`) y se incluye un caso
documentado donde la corrección **cambia la decisión** al 5 %.

Ejecutar con:  python tests/test_jarque_bera.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.criterios import (  # noqa: E402
    ALPHA_PRUEBAS_RESIDUALES,
    MIN_OBS_JARQUE_BERA,
)
from app_icociv.estadistica.diagnostico_residuos import evaluar_residuos  # noqa: E402
from app_icociv.utilidades.utilidades import (  # noqa: E402
    estadistico_jarque_bera,
    valor_p_jarque_bera,
)

TOLERANCIA = 1e-9

# Caso n=26 en el que la implementación anterior (normalizando con ddof=1) no
# rechazaba la normalidad y la estándar sí. Es la evidencia concreta de que el
# defecto tenía consecuencias, no solo diferencias en decimales.
CASO_CRUCE_ALPHA_5 = np.array([
    -1.330203, -0.240946, -0.820502, -0.502563, -0.184435, 0.256895,
    -2.530462, 0.328062, 1.069455, 0.196452, 2.188442, 4.944500,
    0.521170, -0.200130, 1.795651, 1.267923, -0.203868, -0.488245,
    -3.014393, 0.200766, 1.562604, 0.100649, 1.085795, 0.815302,
    -0.968204, -0.575519,
])


def _jb_implementacion_anterior(r: np.ndarray) -> tuple[float, float]:
    """Reproduce el cálculo previo a la corrección, solo para contrastarlo."""
    n = len(r)
    z = (r - r.mean()) / r.std(ddof=1)
    asimetria = float(np.mean(z ** 3))
    curtosis = float(np.mean(z ** 4))
    jb = (n / 6.0) * (asimetria ** 2 + ((curtosis - 3.0) ** 2) / 4.0)
    return jb, math.exp(-jb / 2.0)


# ==============================
# Contraste contra oráculo externo
# ==============================


def test_estadistico_coincide_con_scipy_en_casos_variados() -> None:
    rng = np.random.default_rng(7)
    casos = {
        "normal n=60": rng.normal(0.0, 1.0, 60),
        "normal n=26": rng.normal(0.0, 1.0, 26),
        "asimetrica n=40": rng.exponential(1.0, 40),
        "colas pesadas n=50": rng.standard_t(3, 50),
        "uniforme n=100": rng.uniform(-1.0, 1.0, 100),
        "muestra minima": np.array([-2.0, -1.0, -0.5, 0.0, 0.2, 0.5, 1.0, 3.0]),
    }
    for nombre, x in casos.items():
        jb, _, _ = estadistico_jarque_bera(x)
        referencia = stats.jarque_bera(x)
        assert abs(jb - referencia.statistic) < TOLERANCIA, (
            f"{nombre}: JB propio={jb} vs scipy={referencia.statistic}"
        )


def test_valor_p_coincide_con_scipy() -> None:
    rng = np.random.default_rng(21)
    for _ in range(30):
        x = rng.standard_t(5, 45)
        assert abs(valor_p_jarque_bera(x) - float(stats.jarque_bera(x).pvalue)) < TOLERANCIA


def test_asimetria_y_curtosis_usan_momentos_centrales_de_divisor_n() -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(0.0, 3.0, 70)
    _, asimetria, curtosis = estadistico_jarque_bera(x)

    d = x - x.mean()
    m2 = float(np.mean(d ** 2))
    assert abs(asimetria - float(np.mean(d ** 3)) / m2 ** 1.5) < TOLERANCIA
    assert abs(curtosis - float(np.mean(d ** 4)) / m2 ** 2) < TOLERANCIA
    # Y coinciden con scipy, que usa la misma convención.
    assert abs(asimetria - float(stats.skew(x))) < TOLERANCIA
    assert abs(curtosis - 3.0 - float(stats.kurtosis(x))) < TOLERANCIA


def test_p_es_cola_chi2_dos_gl() -> None:
    """p debe ser exp(-JB/2), la supervivencia exacta de chi²(2)."""
    for jb in (0.5, 2.0, 5.99, 9.21, 15.0):
        assert abs(math.exp(-jb / 2.0) - float(stats.chi2.sf(jb, 2))) < TOLERANCIA


def test_la_cola_no_es_la_de_cuatro_grados_de_libertad() -> None:
    """Regresión de una corrección anterior: chi²(4) sobreestimaba el valor p."""
    rng = np.random.default_rng(2)
    x = rng.standard_t(4, 50)
    jb, _, _ = estadistico_jarque_bera(x)
    p = valor_p_jarque_bera(x)
    assert abs(p - float(stats.chi2.sf(jb, 2))) < TOLERANCIA
    assert abs(p - math.exp(-jb / 2.0) * (1.0 + jb / 2.0)) > TOLERANCIA


# ==============================
# Casos exigidos por la remediación
# ==============================


def test_caso_normal_no_rechaza() -> None:
    rng = np.random.default_rng(1234)
    x = rng.normal(0.0, 1.0, 200)
    p = valor_p_jarque_bera(x)
    assert p > ALPHA_PRUEBAS_RESIDUALES
    assert abs(p - float(stats.jarque_bera(x).pvalue)) < TOLERANCIA


def test_caso_no_normal_rechaza() -> None:
    rng = np.random.default_rng(99)
    x = rng.exponential(1.0, 120)
    p = valor_p_jarque_bera(x)
    assert p < ALPHA_PRUEBAS_RESIDUALES
    assert abs(p - float(stats.jarque_bera(x).pvalue)) < TOLERANCIA


def test_caso_cercano_a_alpha_cambia_la_decision_tras_la_correccion() -> None:
    """H-04: el caso documentado donde la corrección invierte la conclusión."""
    x = CASO_CRUCE_ALPHA_5
    assert len(x) == 26

    jb_viejo, p_viejo = _jb_implementacion_anterior(x)
    jb_nuevo, _, _ = estadistico_jarque_bera(x)
    p_nuevo = valor_p_jarque_bera(x)

    # La implementación anterior NO rechazaba; la corregida SÍ rechaza.
    assert p_viejo > ALPHA_PRUEBAS_RESIDUALES, f"p anterior={p_viejo}"
    assert p_nuevo <= ALPHA_PRUEBAS_RESIDUALES, f"p corregido={p_nuevo}"
    assert jb_nuevo > jb_viejo, "ddof=1 encogía el estadístico"

    referencia = stats.jarque_bera(x)
    assert abs(jb_nuevo - referencia.statistic) < TOLERANCIA
    assert abs(p_nuevo - float(referencia.pvalue)) < TOLERANCIA


def test_serie_constante_no_es_calculable() -> None:
    """Residuos idénticos: JB indefinido; debe reportarse NaN."""
    constante = np.full(20, 3.14)
    jb, asimetria, curtosis = estadistico_jarque_bera(constante)
    assert math.isnan(jb) and math.isnan(asimetria) and math.isnan(curtosis)
    assert math.isnan(valor_p_jarque_bera(constante))


def test_muestra_minima_y_por_debajo_del_minimo() -> None:
    rng = np.random.default_rng(3)
    justo = rng.normal(0.0, 1.0, MIN_OBS_JARQUE_BERA)
    assert math.isfinite(estadistico_jarque_bera(justo)[0])

    corta = rng.normal(0.0, 1.0, MIN_OBS_JARQUE_BERA - 1)
    assert math.isnan(estadistico_jarque_bera(corta)[0])
    assert math.isnan(valor_p_jarque_bera(corta))
    assert math.isnan(valor_p_jarque_bera(np.array([1.0, 2.0, 3.0, 4.0, 5.0])))
    assert math.isnan(valor_p_jarque_bera(np.array([np.nan] * 10 + [1.0, 2.0])))


def test_valores_no_finitos_se_descartan() -> None:
    rng = np.random.default_rng(8)
    x = rng.normal(0.0, 1.0, 50)
    con_huecos = np.concatenate([x, [np.nan, np.inf, -np.inf]])
    assert abs(estadistico_jarque_bera(x)[0] - estadistico_jarque_bera(con_huecos)[0]) < TOLERANCIA


def test_residuos_normales_no_alertan() -> None:
    rng = np.random.default_rng(12345)
    assert valor_p_jarque_bera(rng.standard_normal(200)) > ALPHA_PRUEBAS_RESIDUALES


# ==============================
# Integración con el diagnóstico
# ==============================


def test_el_diagnostico_expone_estadistico_asimetria_y_curtosis() -> None:
    rng = np.random.default_rng(17)
    x = rng.normal(0.0, 1.0, 60)
    diagnostico = evaluar_residuos(x)
    for clave in ("jb", "jb_p", "jb_asimetria", "jb_curtosis"):
        assert clave in diagnostico, f"falta {clave} en el diagnostico"
    assert abs(diagnostico["jb"] - float(stats.jarque_bera(x).statistic)) < TOLERANCIA
    assert abs(diagnostico["jb_p"] - float(stats.jarque_bera(x).pvalue)) < TOLERANCIA


def test_la_alerta_de_normalidad_sigue_el_valor_p_corregido() -> None:
    diagnostico = evaluar_residuos(CASO_CRUCE_ALPHA_5)
    assert diagnostico["jb_p"] <= ALPHA_PRUEBAS_RESIDUALES
    assert "normalidad" in " ".join(diagnostico["alertas"]), (
        "Con el estadistico corregido la alerta de no normalidad debe emitirse"
    )


def test_evaluar_residuos_con_muestra_corta_no_falla() -> None:
    """Con n<8 el diagnóstico no lanza excepción ni alerta normalidad espuria."""
    diagnostico = evaluar_residuos(np.array([0.5, -0.2, 0.1, -0.4, 0.3]))
    jb_p = diagnostico.get("jb_p")
    assert jb_p is None or not math.isfinite(float(jb_p))
    assert not any("normalidad" in str(a).lower() for a in diagnostico.get("alertas", []))


def _ejecutar() -> int:
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
