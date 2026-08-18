"""Separa EVIDENCIA INTERNA de PUBLICACION en los horizontes (control 18/64/60).

El cierre F/H/G dejo un caso que exigia verificacion antes de cerrar P0-H: una
serie donde el usuario pide 18 meses, la rejilla evalua hasta h=64 y varios campos
de `horizonte_info` valen 64, mientras el limite operativo de entrada es 60.

La pregunta que esta prueba responde es cual de las dos cosas ocurre:

* que la evidencia se mida hasta donde la aritmetica de ventanas permite, y se
  publique **solo** lo solicitado -correcto, y necesario: REQ 18 exige evidencia
  del horizonte publicado, no de menos-;
* o que el producto entregue una trayectoria mas larga que la pedida o que el
  limite operativo -eso si seria un defecto-.

Medido: se entregan exactamente 18 filas. La evidencia interna llega a 64 y esta
correctamente separada.

No introduce ningun tope nuevo: los limites que comprueba son el horizonte que el
usuario pidio y el limite de entrada que ya existia.

Ejecucion directa, sin pytest:

    python tests/test_publicacion_horizonte.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    HORIZONTE_MAXIMO_OPERATIVO,
    _limites_auditoria_horizontes,
    ejecutar_proyeccion,
)


def _serie(n: int = 72) -> pd.DataFrame:
    generador = np.random.default_rng(31)
    valores = [100.0 + 0.35 * i + float(generador.normal(0, 0.4)) for i in range(n)]
    return pd.DataFrame(
        {"Periodo": [f"{2019 + i // 12}_{i % 12 + 1}" for i in range(n)], "Indice": valores}
    )


def _objetivo(serie: pd.DataFrame, horizonte: int) -> tuple[int, int]:
    anio, mes = (int(x) for x in str(serie["Periodo"].iloc[-1]).split("_")[:2])
    total = anio * 12 + (mes - 1) + horizonte
    return total // 12, total % 12 + 1


def test_lo_publicado_no_excede_lo_solicitado() -> None:
    """La trayectoria entregada tiene exactamente los pasos pedidos, ni uno mas."""
    serie = _serie()
    solicitado = 18
    resultado = ejecutar_proyeccion(serie, *_objetivo(serie, solicitado), 2021)
    assert resultado["proyeccion_generada"] is True, resultado.get("explicacion")

    proyecciones = resultado["proyecciones"]
    assert len(proyecciones) == solicitado, (len(proyecciones), solicitado)
    assert int(resultado["horizonte_solicitado"]) == solicitado
    assert int(resultado["horizonte_permitido"]) <= solicitado
    info = resultado["horizonte_info"]
    assert int(info["horizonte_finalmente_permitido"]) <= solicitado


def test_lo_publicado_no_excede_el_limite_operativo() -> None:
    """Ninguna salida entregada supera el limite de entrada del producto."""
    serie = _serie()
    solicitado = 18
    resultado = ejecutar_proyeccion(serie, *_objetivo(serie, solicitado), 2021)
    tope = min(solicitado, HORIZONTE_MAXIMO_OPERATIVO)
    assert len(resultado["proyecciones"]) <= tope
    assert int(resultado["horizonte_permitido"]) <= tope
    assert int(resultado["horizonte_info"]["horizonte_finalmente_permitido"]) <= tope


def test_la_evidencia_interna_si_puede_superar_lo_solicitado() -> None:
    """Y debe poder: medir mas horizontes de los pedidos no es publicarlos.

    REQ 18 exige evidencia **del horizonte publicado**. Recortar la medicion al
    horizonte solicitado no ahorraria nada y ocultaria el comportamiento del
    modelo mas alla; lo que no puede ocurrir es confundir esa medicion con una
    entrega.
    """
    serie = _serie()
    solicitado = 18
    resultado = ejecutar_proyeccion(serie, *_objetivo(serie, solicitado), 2021)
    info = resultado["horizonte_info"]

    _, maximo_por_datos, _, _ = _limites_auditoria_horizontes(len(serie))
    evaluados = [int(e["horizonte"]) for e in (info.get("evaluaciones") or [])]
    assert max(evaluados) == maximo_por_datos, (max(evaluados), maximo_por_datos)
    assert max(evaluados) > solicitado, "La evidencia interna debe poder ir mas alla de lo pedido."
    # Y esa evidencia no se convierte en trayectoria entregada.
    assert len(resultado["proyecciones"]) == solicitado


def test_la_razon_de_parada_no_atribuye_a_un_limite_que_no_actuo() -> None:
    """Control 18/64/60: el mensaje debe nombrar la causa real de la parada.

    Con el cap 30 retirado, `horizonte_maximo_busqueda_configurado` y
    `horizonte_maximo_evaluable_por_datos` coinciden siempre, de modo que la
    aplicacion caia en la rama de «limite operativo configurado» y afirmaba
    haberse detenido por un limite de 60 al llegar a h=64. Falso: se detuvo al
    agotar las ventanas de validacion de la serie.
    """
    serie = _serie()
    resultado = ejecutar_proyeccion(serie, *_objetivo(serie, 18), 2021)
    info = resultado["horizonte_info"]

    _, maximo_por_datos, _, _ = _limites_auditoria_horizontes(len(serie))
    max_evaluado = int(info["horizonte_maximo_evaluado"])
    if max_evaluado >= maximo_por_datos and not int(info.get("primer_horizonte_no_viable") or 0):
        assert info["tipo_parada"] == "evidencia_oos_insuficiente", info["tipo_parada"]
        razon = str(info["razon_parada"]).lower()
        assert "operativo" not in razon, razon
        # Y el limite operativo real no puede aparecer como causa cuando la
        # rejilla lo supero.
        if max_evaluado > HORIZONTE_MAXIMO_OPERATIVO:
            assert "limite operativo" not in razon and "límite operativo" not in razon, razon


def test_los_cinco_horizontes_se_publican_por_separado() -> None:
    """Solicitado, evaluado, admisible, publicable continuo y operativo son distintos.

    Confundirlos es lo que el control 18/64/60 vigila. Se comprueba que los cinco
    existan como campos separados y que el entregado sea el solicitado.
    """
    serie = _serie()
    resultado = ejecutar_proyeccion(serie, *_objetivo(serie, 18), 2021)
    info = resultado["horizonte_info"]
    for clave in (
        "horizonte_solicitado",
        "horizonte_maximo_evaluado",
        "horizonte_maximo_admisible",
        "horizonte_maximo_publicable_continuo",
        "horizonte_finalmente_permitido",
    ):
        assert clave in info, clave
    assert HORIZONTE_MAXIMO_OPERATIVO == 60
    # El unico que gobierna la entrega es el finalmente permitido.
    assert len(resultado["proyecciones"]) == int(info["horizonte_finalmente_permitido"])


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
