"""Integracion coordinada P0-F + P0-H + P0-G (12-08-2026).

QUE INTEGRA. Las tres remediaciones ya auditadas, y SOLO ellas:

* **P0-F** — el tratamiento de calendario diciembre-enero deja de modificar el
  pronostico. Su metodo completo no esta sustentado: ni `gamma` como estimador
  del efecto futuro, ni la forma `exp(gamma(n_j - j/12))` -cuyo termino `-j/12`
  supone que el modelo base repartio gamma uniformemente, hipotesis falsa para
  `naive`-, ni las puertas `>=2`, `>1,5`, `>=0,6`, calibradas segun el propio
  codigo «sobre el anexo ICOCIV», es decir sobre el anexo de aplicacion. El
  perfil se sigue MIDIENDO y publicando como diagnostico descriptivo.

* **P0-H** — el bucle de evaluacion deja de detenerse en el primer horizonte no
  recomendable, y el tope `HORIZONTE_MAXIMO_AUDITORIA = 30` deja de recortar la
  evidencia. Ninguna fuente exige que los horizontes validos formen un prefijo:
  FPP3 5.10 publica UNA TABLA por horizonte. La continuidad mensual se conserva
  como REGLA DE PUBLICACION, con ese nombre.

* **P0-G** — `MIN_ITERACIONES_WF = 6` y `ADVERTENCIA_MIN_OBS = 18` dejan de
  vetar; la escalera de confianza sin fuente se retira; una banda invalida deja
  de cancelar el pronostico puntual (REQ 14).

QUE NO INTEGRA, Y HAY QUE DECIRLO. **P0-C y P0-E siguen abiertos.** No se
construye ningun intervalo, no se cambia `N0` y no se declara ninguna serie
admisible. El estado metodologico que esta integracion introduce sirve
justamente para DECIRLO.

Ejecucion:
    python tests/test_integracion_fhg.py
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import numpy as np
import pandas as pd

from app_icociv.estadistica import analisis_series as AS
from app_icociv.estadistica import calendario_anual as CAL
from app_icociv.estadistica import criterios as CR
from app_icociv.proyeccion import servicio_proyeccion as SP


def _serie(n: int, semilla: int = 0) -> pd.DataFrame:
    g = np.random.default_rng(semilla)
    periodos, anio, mes = [], 2021, 1
    for _ in range(n):
        periodos.append(f"{anio}_{mes:02d}")
        mes += 1
        if mes == 13:
            anio, mes = anio + 1, 1
    t = np.arange(n, dtype=float)
    valores = 100.0 + 0.8 * t + 1.5 * np.sin(t / 6.0)
    # salto de cambio de anio, para que el perfil de calendario SI se detecte
    for i, p in enumerate(periodos):
        if p.endswith("_01") and i > 0:
            valores[i:] *= 1.03
    return pd.DataFrame({"Periodo": periodos, "Indice": valores + g.normal(0, 0.2, n)})


# --- P0-F ------------------------------------------------------------------

def test_f1_el_calendario_no_modifica_el_pronostico() -> None:
    serie = _serie(65)
    y = np.array([100.0, 101.0, 102.0, 103.0], dtype=float)
    salida = SP._ajustar_salto_anual(serie, y, {}, "drift", 4)
    assert np.allclose(np.asarray(salida["y_futuro"], dtype=float), y), (
        "el ajuste de calendario sigue desplazando el pronostico"
    )
    assert all(abs(float(f) - 1.0) < 1e-12 for f in salida["factores"]), salida["factores"]


def test_f2_el_perfil_se_sigue_midiendo_como_diagnostico() -> None:
    """Retirar el TRATAMIENTO no es negar el FENOMENO."""
    perfil = CAL.perfil_salto_anual(_serie(65))
    assert perfil["evaluable"] is True
    assert perfil["transiciones"] >= 2
    assert np.isfinite(perfil["gamma"])


def test_f3_las_puertas_no_deciden_ninguna_salida() -> None:
    serie = _serie(65)
    traz = SP._ajustar_salto_anual(serie, np.array([100.0, 101.0]), {}, "drift", 2)["trazabilidad"]
    assert traz["ajuste_calendario_aplicado"] is False
    assert traz["efecto_en_horizonte_solicitado"] is False


def test_f4_el_texto_no_afirma_que_el_fenomeno_no_exista() -> None:
    serie = _serie(65)
    traz = SP._ajustar_salto_anual(serie, np.array([100.0, 101.0]), {}, "drift", 2)["trazabilidad"]
    texto = f"{traz['estado_calendario_visible']} {traz['mensaje']}".lower()
    assert "sin sustento" in texto or "no aplicado" in texto, texto
    assert "no se detect" not in texto, "afirma ausencia del fenomeno cuando lo que se retiro fue el metodo"


def test_f5_no_se_anadio_ningun_modelo_calendario() -> None:
    from app_icociv.estadistica.modelos_interpretables import MODELOS_INTERPRETABLES
    assert not any("calend" in m or "estacional" in m or "season" in m for m in MODELOS_INTERPRETABLES)


# --- P0-H ------------------------------------------------------------------

def test_h1_el_bucle_no_se_detiene_en_el_primer_horizonte_no_recomendable() -> None:
    """Propiedad, no texto: ninguna linea EJECUTABLE hace break por no_recomendable."""
    cuerpo = inspect.getsource(SP._evaluar_horizontes_proyeccion).split('"""')[-1]
    ejecutables = [l for l in cuerpo.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert not any(l.strip() == "break" for l in ejecutables), (
        "sigue existiendo una parada temprana en el bucle de horizontes"
    )


def test_h2_el_tope_30_ya_no_recorta_la_evidencia() -> None:
    _, maximo_datos, limite, _ = SP._limites_auditoria_horizontes(65)
    assert limite == maximo_datos, (
        f"la rejilla sigue acotada por un tope ({limite}) por debajo de lo que el dato permite ({maximo_datos})"
    )


def test_h3_el_tope_60_solo_restringe_la_entrada() -> None:
    assert SP.validar_horizonte_solicitado(60) == 60
    try:
        SP.validar_horizonte_solicitado(61)
        raise AssertionError("61 deberia rechazarse en la entrada")
    except ValueError:
        pass
    fuente = inspect.getsource(SP)
    usos = [l for l in fuente.splitlines() if "HORIZONTE_MAXIMO_OPERATIVO" in l]
    assert len(usos) <= 3, f"el tope operativo se usa fuera de la validacion de entrada: {usos}"


def test_h4_el_maximo_publicado_declara_que_admite_huecos() -> None:
    """ACTUALIZADO 17-08-2026 (V-CODEX-R3, residual 3).

    Esta prueba exigia que la base publicada dijera «continuidad» y «producto»,
    es decir que declarara una REGLA DE CONTINUIDAD como fundamento del maximo.
    Esa regla se retiro del CALCULO el 16-08-2026 -ambos maximos pasaron a ser
    `max(validos)`-, pero los textos siguieron describiendola, y esta prueba los
    protegia: exigia que el producto declarara una regla que ya no aplica.

    NO es una relajacion. El campo explicito se sigue exigiendo, y ahora se exige
    ademas que su base diga la verdad: que el maximo NO obliga a que los
    horizontes anteriores esten permitidos y que los huecos se declaran.
    """
    serie = _serie(40)
    r = SP.ejecutar_proyeccion(serie, 2024, 6, 2021)
    info = r["analisis_horizontes_completo"]
    assert "horizonte_maximo_publicable_continuo" in info, "falta el campo explicito de publicacion"
    base = str(info.get("base_horizonte_maximo_recomendado", "")).lower()
    assert "propia evidencia" in base, base
    assert "hueco" in base, base
    assert "racha continua" not in base, f"reaparecio el prefijo en la base publicada: {base}"
    base_continuo = str(info.get("base_horizonte_maximo_publicable_continuo", "")).lower()
    assert "sin huecos" not in base_continuo, base_continuo
    assert "no se interpola" in base_continuo, base_continuo


# --- P0-G ------------------------------------------------------------------

def test_g1_cinco_ventanas_no_vetan() -> None:
    fuente = inspect.getsource(AS.evaluar_factibilidad_proyeccion)
    cuerpo = fuente.split('"""')[-1]
    assert "bloqueos_proyeccion.append" not in cuerpo.split("MIN_ITERACIONES_BACKTESTING")[-1][:400], (
        "MIN_ITERACIONES_BACKTESTING sigue produciendo un bloqueo"
    )


def test_g2_la_longitud_no_veta_la_proyeccion() -> None:
    cuerpo = inspect.getsource(AS.evaluar_factibilidad_proyeccion).split('"""')[-1]
    linea = next((l for l in cuerpo.splitlines() if "proyectable =" in l), "")
    assert "ADVERTENCIA_MIN_OBS" not in linea, f"la longitud sigue vetando: {linea.strip()}"


def test_g3_no_hay_escalera_de_confianza_sin_fuente() -> None:
    cuerpo = inspect.getsource(AS.evaluar_factibilidad_proyeccion).split('"""')[-1]
    for etiqueta in ('"alto"', '"medio"', '"bajo"'):
        assert etiqueta not in cuerpo, f"sigue viva la escalera de confianza: {etiqueta}"


def test_g4_el_intervalo_no_sustentado_no_cancela_el_punto() -> None:
    """CORREGIDO el 13-08-2026 tras auditar las nueve fallas.

    La version anterior de esta prueba exigia que una banda con limites no
    finitos o invertidos dejara de bloquear el horizonte, invocando REQ 14.
    **Esa lectura era incorrecta y se retira**: `estado_banda` incluye el propio
    pronostico en la comprobacion de finitud, y unos limites invertidos exigen
    un semiancho negativo, es decir un calculo roto. REQ 14 habla de una
    DEFICIENCIA del intervalo, no de una IMPOSIBILIDAD DE CALCULO.

    Lo que P0-G si identifico con razon, y es lo que aqui se comprueba, es que
    el intervalo cuyo METODO no esta sustentado (P0-C) no debe bloquear ni
    condicionar el punto: se publica el punto y se declara que la banda no esta
    sustentada.
    """
    serie = _serie(40)
    r = SP.ejecutar_proyeccion(serie, 2024, 6, 2021)
    assert r.get("proyeccion_generada") is True
    assert r.get("y_proj") is not None
    assert r.get("intervalo_sustentado") is False
    assert "P0-C" in (r.get("bloqueos_metodologicos") or {})


def test_g5_existe_estado_metodologico_explicito() -> None:
    serie = _serie(40)
    r = SP.ejecutar_proyeccion(serie, 2024, 6, 2021)
    estado = r.get("estado_metodologico") or (r.get("factibilidad") or {}).get("estado_metodologico")
    assert estado, "no existe estado_metodologico"
    assert estado in SP.ESTADOS_METODOLOGICOS, estado


def test_g6_p0e_bloqueado_impide_declarar_resultado_sustentado() -> None:
    serie = _serie(40)
    r = SP.ejecutar_proyeccion(serie, 2024, 6, 2021)
    estado = r.get("estado_metodologico") or (r.get("factibilidad") or {}).get("estado_metodologico")
    assert estado != "resultado_metodologicamente_sustentado", (
        "se declara sustentado con P0-C y P0-E abiertos"
    )


def test_g7_el_intervalo_no_se_publica_como_sustentado() -> None:
    serie = _serie(40)
    r = SP.ejecutar_proyeccion(serie, 2024, 6, 2021)
    assert r.get("intervalo_sustentado") is False, "la banda se sigue presentando como sustentada"


def test_g8_c_wf_002_no_se_publica_como_derivacion() -> None:
    criterio = next(c for c in CR.CRITERIOS_ESTADISTICOS if c.id == "C-WF-002")
    assert criterio.tipo != CR.TIPO_DERIVACION, "P0-E esta bloqueado y el criterio se publica como derivacion"


def test_g9_los_diagnosticos_siguen_sin_vetar() -> None:
    """Propiedad que NO debe cambiar: cumplen REQ 7 y asi deben seguir."""
    cuerpo = inspect.getsource(AS.evaluar_factibilidad_proyeccion).split('"""')[-1]
    tramo = cuerpo.split("bloqueos_proyeccion")[0]
    for termino in ("ljung", "jarque", "breusch"):
        assert termino not in tramo.lower()


# --- P0-A / P0-B / P0-D intactos -------------------------------------------

def test_p0abd_intactos() -> None:
    """P0-A, P0-B y P0-D siguen cerrados. P0-D, por comportamiento.

    P0-C / C2, 15-08-2026. La ultima linea era
    `assert "comunes" in fuente and "rmse_global" in fuente`. `rmse_global` era
    el nombre de una VARIABLE LOCAL del selector, y lo retiro la propia
    remediacion P0-D del 14-08-2026 al pasar a comparar la suma exacta de
    cuadrados. Comprobado en `P0C_C2_MICROAUDITORIA_4_TESTS_PREEXISTENTES.md`:
    ese assert PASA con la aritmetica defectuosa restaurada -es una cadena, no
    una propiedad-, de modo que no protegia nada.

    Se sustituye por el contrato: muestra comun, orden correcto con SSE apenas
    distinto, independencia del orden de insercion y desempate historico. La
    definicion canonica vive en `test_origen_inicial_backtesting`, que es la
    suite de P0-D; aqui se invoca para no duplicarla ni dejar que las dos
    versiones diverjan.
    """
    assert "seleccionar_modelo_por_evidencia(" not in inspect.getsource(SP)
    assert SP.MODELOS_PARAMETRO_SIN_SUSTENTO == {"promedio_movil", "variacion_reciente"}
    from tests.test_origen_inicial_backtesting import test_p0d_la_regla_de_seleccion_no_cambia
    test_p0d_la_regla_de_seleccion_no_cambia()


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
            except Exception as exc:  # noqa: BLE001
                fallos += 1
                print(f"  ERROR {nombre}: {type(exc).__name__}: {exc}")
    print(f"\n{'todas las pruebas pasan' if not fallos else f'{fallos} fallidas'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_ejecutar())
