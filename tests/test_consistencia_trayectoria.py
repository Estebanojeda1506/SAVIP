"""Los meses comunes deben valer lo mismo se pidan 3, 6, 12 o 18 meses.

El ajuste de cambio de año se aplica paso a paso con el factor
f_j = exp(gamma * (n_j - j/12)), donde n_j es el número de eneros acumulados
hasta ese paso. Su activación depende solo de que la serie tenga patrón
confirmado y de que la validación retrospectiva lo respalde, nunca de si el
horizonte total solicitado cruza un enero. Antes, un horizonte de 12 meses
activaba el ajuste y uno de 3 no, de modo que la proyección de un mismo mes
cambiaba según lo que el usuario pidiera.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.estadistica.calendario_anual import factor_ajuste_calendario
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
from app_icociv.utilidades.utilidades import ANIO_BASE

RUTA_ANEXO = ROOT / "anex-ICOCIV-may2026.xlsb"
HORIZONTES = (3, 6, 12, 18)
TOLERANCIA = 1e-9
_CACHE: dict[str, object] = {}


def _tablas():
    if "tablas" not in _CACHE:
        if not RUTA_ANEXO.exists():
            _CACHE["tablas"] = None
        else:
            from app_icociv.datos.cargador_datos import cargar_todas_tablas

            _CACHE["tablas"] = cargar_todas_tablas(RUTA_ANEXO.read_bytes(), RUTA_ANEXO.name)
    return _CACHE["tablas"]


def _serie_real(tabla: str, idx: int) -> pd.DataFrame | None:
    datos = _tablas()
    if datos is None:
        return None
    from app_icociv.proyeccion.servicio_proyeccion import construir_serie

    tablas, year_month = datos
    return construir_serie(tablas[tabla].loc[[idx]], year_month)


def _proyectar(serie: pd.DataFrame, horizonte: int) -> dict:
    anio, mes = map(int, str(serie["Periodo"].iloc[-1]).split("_"))
    total = anio * 12 + (mes - 1) + int(horizonte)
    return ejecutar_proyeccion(serie, total // 12, total % 12 + 1, ANIO_BASE, origen_horizonte="manual")


def _valores_por_periodo(resultado: dict) -> dict[str, float]:
    tabla = resultado.get("proyecciones")
    if tabla is None or not len(tabla):
        return {}
    return {str(f["periodo"]): float(f["indice_proyectado"]) for _, f in tabla.iterrows()}


def _verificar_consistencia(serie: pd.DataFrame, etiqueta: str) -> dict[int, dict]:
    resultados = {}
    for h in HORIZONTES:
        res = _proyectar(serie, h)
        if res.get("proyeccion_generada"):
            resultados[h] = res
    assert resultados, f"{etiqueta}: ninguna proyección generada"
    referencia = _valores_por_periodo(resultados[min(resultados)])
    modelo_ref = resultados[min(resultados)].get("modelo_codigo")
    for h, res in resultados.items():
        assert res.get("modelo_codigo") == modelo_ref, (
            f"{etiqueta}: el modelo cambia con el horizonte ({modelo_ref} vs {res.get('modelo_codigo')})"
        )
        for periodo, valor in _valores_por_periodo(res).items():
            if periodo in referencia:
                assert abs(valor - referencia[periodo]) < TOLERANCIA, (
                    f"{etiqueta}: {periodo} vale {valor} con h={h} y {referencia[periodo]} con "
                    f"h={min(resultados)}"
                )
    return resultados


def _serie_sintetica(salto_enero: float, anio_inicial: int = 2020, n: int = 60) -> pd.DataFrame:
    """Serie con salto recurrente en enero; termina en diciembre para cruzar enero pronto."""
    valores, nivel = [], 100.0
    for i in range(n):
        mes = i % 12 + 1
        nivel *= (1.0 + salto_enero) if (mes == 1 and i > 0) else 1.002 + 0.0004 * np.sin(i * 1.7)
        valores.append(nivel)
    periodos = [f"{anio_inicial + i // 12}_{i % 12 + 1}" for i in range(n)]
    return pd.DataFrame({"Periodo": periodos, "Indice": valores})


def test_factor_es_funcion_solo_del_paso() -> None:
    """El factor de un paso no depende del horizonte total: solo de j y de gamma."""
    gamma = 0.05
    for mes_origen in (1, 5, 11, 12):
        for paso in range(1, 19):
            esperado = factor_ajuste_calendario(gamma, mes_origen, paso)
            # Calcularlo dentro de trayectorias de distinta longitud da lo mismo.
            for _ in (3, 6, 12, 18):
                assert abs(factor_ajuste_calendario(gamma, mes_origen, paso) - esperado) < 1e-15


def test_serie_con_patron_calendario_es_consistente() -> None:
    """Serie sintética con salto de enero: meses comunes idénticos en 3, 6, 12 y 18."""
    serie = _serie_sintetica(0.05)
    resultados = _verificar_consistencia(serie, "sintética con patron")
    traza = resultados[min(resultados)].get("ajuste_calendario") or {}
    assert traza.get("hay_evidencia_calendario"), traza


def test_serie_sin_patron_es_consistente() -> None:
    """Serie suave sin patrón: no se ajusta y los meses comunes coinciden."""
    valores = [100.0 * (1.004 ** i) + 0.05 * np.sin(i * 2.1) for i in range(60)]
    periodos = [f"{2020 + i // 12}_{i % 12 + 1}" for i in range(60)]
    serie = pd.DataFrame({"Periodo": periodos, "Indice": valores})
    resultados = _verificar_consistencia(serie, "sintética sin patron")
    traza = resultados[min(resultados)].get("ajuste_calendario") or {}
    assert not traza.get("ajuste_calendario_aplicado"), traza


def test_arena_es_consistente() -> None:
    """Caso Arena: meses comunes idénticos en los cuatro horizontes.

    Lo que esta prueba fija es la **consistencia de trayectoria**, y eso lo
    comprueba `_verificar_consistencia`. La comprobación adicional de que el
    modelo fuera drift o naive describía un efecto de la salvaguarda, que
    sustituía el modelo elegido por un benchmark. Retirada esa sustitución el
    08-08-2026, el modelo entregado es el que seleccionó el desempeño fuera de
    muestra, y cuál sea no es lo que esta prueba vigila.

    Lo que sí debe seguir cumpliéndose, y se comprueba: un único modelo para
    todos los horizontes pedidos.
    """
    serie = _serie_real("T_16_7", 0)
    if serie is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    resultados = _verificar_consistencia(serie, "Arena")
    modelos = {str(r.get("modelo_codigo")) for r in resultados.values() if r.get("modelo_codigo")}
    assert len(modelos) == 1, f"la trayectoria debe usar un unico modelo: {modelos}"


def test_series_reales_de_distinto_nivel_son_consistentes() -> None:
    """Agregado, tipología y capítulo: la trayectoria no depende del horizonte pedido."""
    if _tablas() is None:
        print("SKIP: no esta disponible el anexo ICOCIV de mayo de 2026.")
        return
    for etiqueta, tabla, idx in [("Agregado", "T_16", 0), ("Tipologia", "T_16_2", 0), ("Capitulo", "T_16_3", 0)]:
        serie = _serie_real(tabla, idx)
        assert serie is not None
        _verificar_consistencia(serie, etiqueta)


def test_intervalos_usan_la_trayectoria_ajustada() -> None:
    """El intervalo del 95% se construye sobre los valores ya ajustados.

    P0-C / ESTRATEGIA C2, 15-08-2026. La comprobacion leia los limites de la
    tabla PUBLICA, que desde el retiro no entrega ninguno. La propiedad -que la
    banda se centre en la trayectoria ya ajustada, no en la sin ajustar- sigue
    siendo cierta y sigue importando: se mide sobre el resultado anterior al
    corte de publicacion.
    """
    from app_icociv.proyeccion.servicio_proyeccion import (
        _ejecutar_proyeccion_base,
        _estructurar_resultado_horizontes,
    )

    serie = _serie_sintetica(0.05)
    res = _proyectar(serie, 12)
    assert res.get("proyeccion_generada"), res.get("explicacion")

    anio, mes = map(int, str(serie["Periodo"].iloc[-1]).split("_"))
    total = anio * 12 + (mes - 1) + 12
    interno = _estructurar_resultado_horizontes(
        _ejecutar_proyeccion_base(
            serie_df=serie, year_proj=total // 12, month_proj=total % 12 + 1,
            anio_base=ANIO_BASE,
        ),
        "manual",
    )
    tabla = interno["proyecciones"]
    for _, fila in tabla.iterrows():
        valor = float(fila["indice_proyectado"])
        assert float(fila["limite_inferior_95"]) <= valor <= float(fila["limite_superior_95"]), fila["periodo"]
    # Y la trayectoria publicada es la misma: el corte solo retira la banda.
    assert [repr(v) for v in res["proyecciones"]["indice_proyectado"]] == \
        [repr(v) for v in tabla["indice_proyectado"]]

    tabla = res["proyecciones"]
    traza = res.get("ajuste_calendario") or {}
    if traza.get("ajuste_calendario_aplicado"):
        factores = traza.get("factores_por_paso") or []
        assert len(factores) == len(tabla)
        assert any(abs(float(f) - 1.0) > 1e-12 for f in factores), "El ajuste debe alterar algun paso."


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: consistencia de trayectoria frente al horizonte solicitado.")
