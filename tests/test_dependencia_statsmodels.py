"""Pruebas de la dependencia obligatoria statsmodels (hallazgo H-01).

Antes de julio de 2026 `statsmodels` era opcional: si estaba instalado, Holt
optimizaba sus coeficientes y cambiaba el modelo seleccionado y la cifra
proyectada. El mismo dato daba resultados distintos según la máquina.

Estas pruebas fijan la decisión tomada: la dependencia es obligatoria y su uso
está acotado al diagnóstico. Instalarla o desinstalarla no puede mover un
pronóstico.

Ejecutar con:  python tests/test_dependencia_statsmodels.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_icociv.config.dependencias import (  # noqa: E402
    DEPENDENCIAS_OBLIGATORIAS,
    VERSION_STATSMODELS_REQUERIDA,
    DependenciaFaltante,
    verificar_dependencias_obligatorias,
)
from app_icociv.estadistica.criterios import (  # noqa: E402
    MAX_LAG_LJUNG_BOX,
    MODEL_DF_LJUNG_BOX,
)
from app_icociv.estadistica.diagnostico_residuos import (  # noqa: E402
    calcular_ljung_box,
    evaluar_residuos,
)
from app_icociv.estadistica.modelos_interpretables import (  # noqa: E402
    HOLT_PHI_MIN,
    HOLT_PHI_MAX,
    ajustar_modelo_interpretable,
)
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion  # noqa: E402


def _serie(n: int = 60) -> pd.DataFrame:
    periodos = [f"{2021 + i // 12}_{i % 12 + 1}" for i in range(n)]
    valores = [100.0 + 0.8 * i + (2.5 if i and i % 12 == 0 else 0.0) for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


# ==============================
# 1. Version exacta instalada
# ==============================


def test_statsmodels_instalado_en_la_version_exigida() -> None:
    import statsmodels

    assert statsmodels.__version__ == VERSION_STATSMODELS_REQUERIDA, (
        f"Se requiere statsmodels {VERSION_STATSMODELS_REQUERIDA}, "
        f"hay {statsmodels.__version__}"
    )


def test_requirements_fija_version_exacta_sin_rangos() -> None:
    raiz = Path(__file__).resolve().parents[1]
    requisitos = (raiz / "requirements.txt").read_text(encoding="utf-8")
    lineas = [l.strip() for l in requisitos.splitlines() if l.strip().startswith("statsmodels")]
    assert lineas, "statsmodels debe estar declarado en requirements.txt"
    assert lineas[0] == f"statsmodels=={VERSION_STATSMODELS_REQUERIDA}", (
        f"Debe fijarse la version exacta, no un rango. Encontrado: {lineas[0]}"
    )
    for prohibido in (">=", "<=", "~=", ">", "<"):
        assert prohibido not in lineas[0], f"No se admiten rangos: {lineas[0]}"

    lock = (raiz / "requirements-lock.txt").read_text(encoding="utf-8")
    assert f"statsmodels=={VERSION_STATSMODELS_REQUERIDA}" in lock


def test_statsmodels_declarado_como_obligatorio() -> None:
    nombres = {d.modulo for d in DEPENDENCIAS_OBLIGATORIAS}
    assert "statsmodels" in nombres
    dependencia = next(d for d in DEPENDENCIAS_OBLIGATORIAS if d.modulo == "statsmodels")
    assert dependencia.version_requerida == VERSION_STATSMODELS_REQUERIDA
    # El proposito debe dejar claro que no toca la estadistica de pronostico.
    for palabra in ("Ljung-Box", "modelos", "intervalos"):
        assert palabra in dependencia.proposito


# ==============================
# 2. Importacion correcta
# ==============================


def test_importacion_directa_sin_ruta_alternativa() -> None:
    from statsmodels.stats.diagnostic import acorr_ljungbox

    assert callable(acorr_ljungbox)

    # El modulo de diagnostico debe importar statsmodels en el ambito del
    # modulo, no dentro de un try/except.
    raiz = Path(__file__).resolve().parents[1]
    fuente = (raiz / "app_icociv" / "estadistica" / "diagnostico_residuos.py").read_text(
        encoding="utf-8-sig"
    )
    assert "from statsmodels.stats.diagnostic import acorr_ljungbox" in fuente
    assert "except ImportError" not in fuente, (
        "No debe quedar ninguna ruta alternativa por ImportError"
    )


def test_ningun_modulo_productivo_hace_statsmodels_opcional() -> None:
    raiz = Path(__file__).resolve().parents[1] / "app_icociv"
    sospechosos: list[str] = []
    for archivo in raiz.rglob("*.py"):
        texto = archivo.read_text(encoding="utf-8-sig", errors="replace")
        if "statsmodels" not in texto:
            continue
        for marcador in ("STATSMODELS_DISPONIBLE", "HAS_STATSMODELS", "statsmodels no disponible"):
            if marcador in texto:
                sospechosos.append(f"{archivo.name}: {marcador}")
    assert not sospechosos, f"Rutas opcionales residuales: {sospechosos}"


def test_verificacion_de_dependencias_pasa_y_es_explicita() -> None:
    verificadas = verificar_dependencias_obligatorias()
    assert any(v.startswith("statsmodels==") for v in verificadas)
    assert DependenciaFaltante.__mro__[1] is RuntimeError


# ==============================
# 3. Ljung-Box contra caso independiente
# ==============================


def test_ljung_box_coincide_con_calculo_independiente() -> None:
    """Contraste contra la definicion, sin usar la salida de statsmodels."""
    rng = np.random.default_rng(11)
    residuos = rng.normal(0.0, 1.0, 80)

    resultado = calcular_ljung_box(residuos, max_lag=5)
    assert resultado["disponible"]
    rezagos = resultado["rezagos"]

    # Q = n(n+2) * suma_{k=1..m} rho_k^2 / (n-k), con rho de divisor n.
    x = residuos - residuos.mean()
    n = len(x)
    denominador = float(np.sum(x ** 2))
    q = 0.0
    for k in range(1, rezagos + 1):
        rho = float(np.sum(x[k:] * x[:-k]) / denominador)
        q += rho ** 2 / (n - k)
    q *= n * (n + 2)

    assert abs(q - resultado["estadistico"]) < 1e-9, (
        f"Q independiente={q} vs statsmodels={resultado['estadistico']}"
    )

    from scipy import stats

    p = float(stats.chi2.sf(q, rezagos - MODEL_DF_LJUNG_BOX))
    assert abs(p - resultado["p_value"]) < 1e-9


def test_ljung_box_declara_rezagos_y_model_df() -> None:
    resultado = calcular_ljung_box(np.sin(np.arange(60, dtype=float)))
    assert resultado["model_df"] == MODEL_DF_LJUNG_BOX
    assert 1 <= resultado["rezagos"] <= MAX_LAG_LJUNG_BOX
    assert str(MODEL_DF_LJUNG_BOX) in resultado["mensaje"]


# ==============================
# 4 y 5. Casos degenerados
# ==============================


def test_residuos_constantes_no_son_calculables() -> None:
    resultado = calcular_ljung_box(np.zeros(40))
    assert resultado["disponible"] is False
    assert resultado["p_value"] is None
    assert "constantes" in resultado["mensaje"]


def test_muestra_insuficiente_produce_no_calculable() -> None:
    """D-10: el minimo es derivado, n > rezagos, no un valor fijo.

    Con cuatro residuos, min(10, floor(4/5)) = 0 rezagos: el contraste no
    existe y debe declararse no calculable con el motivo derivado.
    """
    resultado = calcular_ljung_box(np.arange(4, dtype=float))
    assert resultado["disponible"] is False
    assert resultado["p_value"] is None
    assert "No calculable" in resultado["mensaje"]
    assert "n/5" in resultado["mensaje"], resultado["mensaje"]


def test_los_rezagos_usan_la_regla_del_tamano_muestral() -> None:
    """D-10: h = min(10, floor(n/5)), segun Hyndman y Athanasopoulos (2021) 5.4."""
    generador = np.random.default_rng(17)
    for n, esperado in ((20, 4), (35, 7), (50, 10), (65, 10), (200, 10)):
        resultado = calcular_ljung_box(generador.normal(0.0, 1.0, n))
        assert resultado["rezagos"] == esperado, (n, resultado["rezagos"], esperado)


def test_el_diagnostico_conserva_estadistico_valor_p_residuos_y_rezagos() -> None:
    """El diagnostico no pierde informacion al cambiar la regla de rezagos."""
    generador = np.random.default_rng(23)
    resultado = calcular_ljung_box(generador.normal(0.0, 1.0, 60))
    assert resultado["disponible"] is True
    for clave in ("estadistico", "p_value", "rezagos", "model_df"):
        assert resultado.get(clave) is not None, clave
    assert resultado["model_df"] == 0
    assert 0.0 <= float(resultado["p_value"]) <= 1.0
    assert float(resultado["estadistico"]) >= 0.0


def test_una_muestra_pequena_no_habilita_conclusiones_fuertes() -> None:
    """Con pocas observaciones el contraste existe pero con muy pocos rezagos.

    El diagnostico debe declarar cuantos rezagos sostienen el resultado, de modo
    que no pueda leerse como evidencia equivalente a la de una serie larga.
    """
    generador = np.random.default_rng(29)
    corta = calcular_ljung_box(generador.normal(0.0, 1.0, 12))
    larga = calcular_ljung_box(generador.normal(0.0, 1.0, 65))
    assert corta["rezagos"] == 2, corta["rezagos"]
    assert larga["rezagos"] == 10, larga["rezagos"]
    assert corta["rezagos"] < larga["rezagos"], (
        "la muestra corta debe sostenerse en menos rezagos que la larga"
    )
    assert str(corta["rezagos"]) in corta["mensaje"], corta["mensaje"]


# ==============================
# 6. El diagnostico llega a las salidas
# ==============================


def test_el_diagnostico_ljung_box_llega_al_resultado_y_al_informe() -> None:
    resultado = ejecutar_proyeccion(_serie(), 2026, 6, 2021)
    ljung = (resultado.get("diagnostico_residuos") or {}).get("ljung_box") or {}
    assert ljung.get("disponible") is True, "Ljung-Box debe calcularse siempre"
    assert isinstance(ljung.get("p_value"), float)

    from app_icociv.reportes.contenido import DatosProyeccion, construir_informe_proyeccion
    from app_icociv.reportes.modelo import ConfiguracionInforme, Tabla

    datos = DatosProyeccion(resultado=resultado, serie_df=_serie(), fuente_label="T_16")
    informe = construir_informe_proyeccion(datos, ConfiguracionInforme.desde_tipo("tecnico"))
    seccion = next(s for s in informe.secciones if s.clave == "residuos")
    texto = " ".join(
        b.texto for b in seccion.bloques if hasattr(b, "texto")
    ) + " ".join(
        f[0] for b in seccion.bloques if isinstance(b, Tabla) for f in b.filas
    )
    assert "Ljung" in texto
    assert "no está disponible" not in texto, (
        "El informe ya no puede decir que la prueba no esta disponible"
    )


# ==============================
# 7. statsmodels no cambia el pronostico
# ==============================


def test_holt_estima_sus_parametros_dentro_de_las_cotas_con_fuente() -> None:
    """AUDITORIA 09-08-2026 (C-01). Antes fijaba alpha=0,65 y beta=0,20.

    Esta prueba exigia esos valores exactos y su fallo demostro que eran una
    parametrizacion fijada sin fuente. Se conserva LO QUE VERIFICABA DE FONDO
    -que Holt no delegue en statsmodels ni dependa del entorno- y se sustituye
    la expectativa: los parametros se estiman minimizando el SSE de un paso
    (FPP3 8.1-8.2) y deben respetar las cotas de la propia fuente.
    """
    serie = _serie()
    t = np.arange(len(serie), dtype=float)
    y = serie["Indice"].to_numpy(dtype=float)

    for amortiguado, nombre in ((False, "holt_lineal"), (True, "holt_amortiguado")):
        modelo = ajustar_modelo_interpretable(nombre, t, y)
        p = modelo["parametros"]
        assert 0.0 < p["alpha"] < 1.0, p["alpha"]
        assert 0.0 < p["beta"] <= p["alpha"] + 1e-9, (p["beta"], p["alpha"])
        if amortiguado:
            assert HOLT_PHI_MIN - 1e-9 <= p["phi"] <= HOLT_PHI_MAX + 1e-9, p["phi"]
        else:
            assert p["phi"] == 1.0
        assert "nivel_inicial" in p and "tendencia_inicial" in p
        assert p["backend"] == "interno", (
            "Holt no debe delegar en statsmodels ni en ningun optimizador externo"
        )
        assert "8.1" in p["fuente_parametrizacion"] or "8.2" in p["fuente_parametrizacion"]


def test_la_estimacion_de_holt_es_determinista() -> None:
    """Reproducibilidad: la misma ventana produce siempre los mismos parametros."""
    serie = _serie()
    t = np.arange(len(serie), dtype=float)
    y = serie["Indice"].to_numpy(dtype=float)
    for nombre in ("holt_lineal", "holt_amortiguado"):
        a = ajustar_modelo_interpretable(nombre, t, y)["parametros"]
        b = ajustar_modelo_interpretable(nombre, t, y.copy())["parametros"]
        for clave in ("alpha", "beta", "phi", "nivel_inicial", "tendencia_inicial"):
            assert a[clave] == b[clave], (nombre, clave, a[clave], b[clave])


def test_la_estimacion_de_holt_solo_usa_la_ventana_recibida() -> None:
    """Ausencia de fuga: alargar la serie cambia la estimacion; truncarla la
    devuelve al valor de la ventana corta. Si la estimacion mirase mas alla de
    la ventana, el primer ajuste ya coincidiria con el de la serie larga.
    """
    serie = _serie()
    y = serie["Indice"].to_numpy(dtype=float)
    corto, largo = y[:30], y
    t_corto, t_largo = np.arange(30, dtype=float), np.arange(len(y), dtype=float)

    p_corto = ajustar_modelo_interpretable("holt_lineal", t_corto, corto)["parametros"]
    p_largo = ajustar_modelo_interpretable("holt_lineal", t_largo, largo)["parametros"]
    p_corto_2 = ajustar_modelo_interpretable("holt_lineal", t_corto, corto)["parametros"]

    assert p_corto["observaciones_estimacion"] == 30
    assert p_largo["observaciones_estimacion"] == len(y)
    assert p_corto["alpha"] == p_corto_2["alpha"], "la estimacion de la ventana corta cambio"


def test_holt_no_consulta_statsmodels_aunque_este_instalado() -> None:
    """Con statsmodels presente, el codigo de Holt no debe importarlo."""
    raiz = Path(__file__).resolve().parents[1]
    fuente = (raiz / "app_icociv" / "estadistica" / "modelos_interpretables.py").read_text(
        encoding="utf-8-sig"
    )
    assert "from statsmodels" not in fuente
    assert "import statsmodels" not in fuente


def test_la_proyeccion_es_identica_con_statsmodels_importado() -> None:
    """Importar statsmodels no debe alterar ningun numero del resultado."""
    serie = _serie()
    primero = ejecutar_proyeccion(serie, 2026, 6, 2021)

    import statsmodels.api  # noqa: F401  fuerza la carga completa del paquete

    segundo = ejecutar_proyeccion(serie, 2026, 6, 2021)

    assert primero["model_name"] == segundo["model_name"]
    assert primero["y_proj"] == segundo["y_proj"]
    assert primero["ci95_lo"] == segundo["ci95_lo"]
    assert primero["ci95_hi"] == segundo["ci95_hi"]
    assert primero["horizonte_permitido"] == segundo["horizonte_permitido"]
    info_a = primero["analisis_horizontes_completo"]
    info_b = segundo["analisis_horizontes_completo"]
    assert info_a["horizonte_maximo_recomendado"] == info_b["horizonte_maximo_recomendado"]
    assert (primero.get("salvaguarda_benchmark") or {}).get("activada") == (
        segundo.get("salvaguarda_benchmark") or {}
    ).get("activada")


# ==============================
# 8. La aplicacion no funciona sin la dependencia
# ==============================


def test_la_aplicacion_se_detiene_si_falta_una_dependencia() -> None:
    """La verificacion debe fallar de forma explicita, no seguir por otra ruta."""
    import app_icociv.config.dependencias as dep

    original = dep.DEPENDENCIAS_OBLIGATORIAS
    try:
        dep.DEPENDENCIAS_OBLIGATORIAS = original + (
            dep.DependenciaObligatoria("modulo_que_no_existe_savip", "Prueba"),
        )
        try:
            dep.verificar_dependencias_obligatorias()
        except DependenciaFaltante as error:
            mensaje = str(error)
            assert "modulo_que_no_existe_savip" in mensaje
            assert "requirements-lock.txt" in mensaje
            assert "ruta alternativa" in mensaje
        else:
            raise AssertionError("Debio lanzarse DependenciaFaltante")
    finally:
        dep.DEPENDENCIAS_OBLIGATORIAS = original


def test_version_incorrecta_tambien_detiene_la_aplicacion() -> None:
    import app_icociv.config.dependencias as dep

    original = dep.DEPENDENCIAS_OBLIGATORIAS
    try:
        dep.DEPENDENCIAS_OBLIGATORIAS = (
            dep.DependenciaObligatoria("statsmodels", "Prueba", "0.0.1-inexistente"),
        )
        try:
            dep.verificar_dependencias_obligatorias()
        except DependenciaFaltante as error:
            assert "se requiere exactamente" in str(error)
        else:
            raise AssertionError("Una version distinta debe detener la aplicacion")
    finally:
        dep.DEPENDENCIAS_OBLIGATORIAS = original


# ==============================
# 9. Empaquetado
# ==============================


def test_el_spec_declara_statsmodels_sin_condicional() -> None:
    raiz = Path(__file__).resolve().parents[1]
    spec = (raiz / "packaging" / "SAVIP.spec").read_text(encoding="utf-8-sig")
    assert "import statsmodels" in spec
    assert "statsmodels.stats.diagnostic" in spec
    assert "except ImportError:\n    pass" not in spec.split("statsmodels")[0][-200:], (
        "statsmodels ya no puede declararse dentro de un try/except opcional"
    )
    # Solo se declara el submodulo que se usa: no se inflan hiddenimports.
    assert "statsmodels.tsa.holtwinters" not in spec, (
        "Holt ya no usa statsmodels; el hiddenimport sobra"
    )


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
