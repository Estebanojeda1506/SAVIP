"""Pruebas de las dos decisiones autorizadas el 29 de julio de 2026.

1. **Calendario (alternativa A).** El patron de cambio de anio es una propiedad
   de la serie y se detecta con independencia del horizonte; lo que si depende
   del horizonte es que haya o no un enero dentro de el. Ambas cosas se
   informan por separado y no vuelve la condicion ``cruza_enero``.

2. **Intervalo del 95 % (alternativas A + C).** El calculo numerico no cambia:
   cambia lo que el sistema afirma sobre la banda y hasta donde permite usarla,
   segun la cobertura empirica medida.

Ejecucion directa, sin pytest:

    python tests/test_calendario_y_clasificacion_intervalo.py
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

from app_icociv.estadistica.calendario_anual import (  # noqa: E402
    perfil_salto_anual,
    resumen_trazabilidad,
)
from app_icociv.estadistica.criterios import (  # noqa: E402
    COBERTURA_IC95_ACEPTABLE,
    COBERTURA_IC95_ADVERTENCIA,
    MIN_ERRORES_COBERTURA_EMPIRICA,
)
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    clasificar_intervalo_por_cobertura,
    ejecutar_proyeccion,
)
from app_icociv.reportes.generador_reportes import (  # noqa: E402
    construir_dataframe_reproducibilidad,
)


# ==============================
# APOYOS
# ==============================


def serie_con_salto_de_enero(anios: int = 6) -> pd.DataFrame:
    """Serie mensual con tendencia suave y un escalon reproducible cada enero."""
    periodos, indices = [], []
    valor = 100.0
    for anio in range(2019, 2019 + anios):
        for mes in range(1, 13):
            valor *= 1.055 if mes == 1 else 1.004
            periodos.append(f"{anio}-{mes:02d}")
            indices.append(round(valor, 4))
    return pd.DataFrame({"Periodo": periodos, "Indice": indices})


def trazabilidad(serie: pd.DataFrame, horizonte: int) -> dict:
    """Trazabilidad del calendario tal como la arma el servicio de proyeccion.

    P0-F, 08-08-2026: el ayudante ya no fuerza ``aplicado=True``. El factor de
    reconcentracion diciembre->enero se retiro por carecer de sustento, asi que
    ``_ajustar_salto_anual`` devuelve siempre ``aplicado=False``. Un ayudante que
    siguiera pasando ``True`` estaria protegiendo un valor que produccion ya no
    produce, y por tanto no protegeria nada.
    """
    perfil = perfil_salto_anual(serie)
    mes_origen = int(str(serie["Periodo"].iloc[-1]).replace("-", "_").split("_")[1])
    return resumen_trazabilidad(
        perfil,
        {"evaluado": False},
        aplicado=False,
        horizonte=horizonte,
        mes_origen=mes_origen,
    )


# Frases que el estado visible NO puede contener mientras el tratamiento este
# retirado: afirmarian que se corrigio el pronostico.
PROHIBIDO_AFIRMAR_TRATAMIENTO = ("se aplica", "reconcentra", "ajustado por calendario")


def _no_afirma_tratamiento(texto: str) -> None:
    bajo = str(texto).lower()
    for frase in PROHIBIDO_AFIRMAR_TRATAMIENTO:
        assert frase not in bajo, (frase, texto)


def cobertura(minima: float | None, verificable: bool = True) -> dict:
    return {"verificable": verificable, "cobertura_95_minima": minima}


# ==============================
# 1. CALENDARIO
# ==============================


def test_patron_se_detecta_y_se_declara_sin_tratamiento():
    """El patron sigue siendo una propiedad de la serie; lo que se retiro es la correccion.

    Antes esta prueba fijaba la frase «sin efecto en el horizonte». Esa redaccion
    describia el estado del TRATAMIENTO segun alcanzara o no un enero. Retirado el
    tratamiento en P0-F, el estado ya no depende del horizonte y la frase carece de
    objeto. Lo que se protege ahora es lo sustantivo: el fenomeno se sigue midiendo
    y se declara, y el sistema no afirma haber corregido nada.
    """
    serie = serie_con_salto_de_enero()
    # Ultimo periodo es diciembre; se corta en mayo para que h=6 no llegue a enero.
    serie = serie.iloc[:-7]
    assert serie["Periodo"].iloc[-1].endswith("-05")

    corto = trazabilidad(serie, horizonte=6)
    assert corto["patron_detectado_en_serie"] is True, corto
    assert corto["eneros_en_horizonte"] == 0, corto
    assert corto["horizonte_cruza_cambio_anio"] is False, corto
    # El tratamiento no se aplica, luego no hay efecto que declarar en el horizonte.
    assert corto["ajuste_calendario_aplicado"] is False, corto
    assert corto["efecto_en_horizonte_solicitado"] is False, corto
    # El texto nombra el patron detectado y declara que no se le aplica correccion,
    # sin negar el fenomeno y sin afirmar un tratamiento.
    estado = corto["estado_calendario_visible"].lower()
    assert "patr" in estado, estado
    assert "no aplicado" in estado or "sin sustento" in estado, estado
    _no_afirma_tratamiento(estado)


def test_horizonte_que_alcanza_enero_lo_cuenta_pero_no_produce_efecto():
    """El enero dentro del horizonte se sigue contando; ya no dispara ningun ajuste.

    Antes se exigia ``efecto_en_horizonte_solicitado is True`` cuando el horizonte
    cruzaba un enero. Ese campo declara el efecto del TRATAMIENTO, y sin
    tratamiento no puede haber efecto: hoy es False. La distincion de CLAUDE.md
    entre «patron detectado en la serie» y «horizonte que alcanza enero» no se
    pierde, la sostienen ``horizonte_cruza_cambio_anio`` y ``eneros_en_horizonte``,
    que se siguen publicando.
    """
    serie = serie_con_salto_de_enero().iloc[:-7]
    corto = trazabilidad(serie, horizonte=6)
    largo = trazabilidad(serie, horizonte=18)
    assert largo["patron_detectado_en_serie"] is True
    # El fenomeno se cuenta y se localiza: el horizonte largo si alcanza un enero.
    assert largo["eneros_en_horizonte"] >= 1, largo
    assert largo["horizonte_cruza_cambio_anio"] is True, largo
    # Y aun asi no se corrige nada ni se afirma efecto alguno.
    assert largo["ajuste_calendario_aplicado"] is False, largo
    assert largo["efecto_en_horizonte_solicitado"] is False, largo
    _no_afirma_tratamiento(largo["estado_calendario_visible"])
    # Las compuertas de calendario no redactan: alcanzar o no un enero no cambia
    # el estado publicado, porque el estado describe el metodo, no el horizonte.
    assert largo["estado_calendario_visible"] == corto["estado_calendario_visible"], (
        corto["estado_calendario_visible"], largo["estado_calendario_visible"]
    )


def test_los_meses_comunes_no_cambian_al_ampliar_el_horizonte():
    """Blindaje de la regla: el ajuste es por paso, no por horizonte total."""
    serie = serie_con_salto_de_enero().iloc[:-7]
    corto = trazabilidad(serie, horizonte=6)
    largo = trazabilidad(serie, horizonte=18)
    for clave in ("salto_mediano_pct", "movimiento_mensual_tipico_pct",
                  "ratio_salto_movimiento", "transiciones_diciembre_enero",
                  "patron_detectado_en_serie", "hay_evidencia_calendario"):
        assert corto[clave] == largo[clave], (clave, corto[clave], largo[clave])


def test_serie_sin_patron_lo_declara_como_no_detectado():
    periodos = [f"{2019 + i // 12}-{i % 12 + 1:02d}" for i in range(60)]
    plana = pd.DataFrame({
        "Periodo": periodos,
        "Indice": [round(100 * 1.004 ** i, 4) for i in range(60)],
    })
    traza = trazabilidad(plana, horizonte=12)
    assert traza["patron_detectado_en_serie"] is False
    assert traza["efecto_en_horizonte_solicitado"] is False
    assert traza["ajuste_calendario_aplicado"] is False
    _no_afirma_tratamiento(traza["estado_calendario_visible"])
    # El estado de «sin patron» debe ser distinguible del de «patron detectado»:
    # se comprueba la distincion, no una frase concreta, que la redaccion puede cambiar.
    con_patron = trazabilidad(serie_con_salto_de_enero().iloc[:-7], horizonte=12)
    assert con_patron["patron_detectado_en_serie"] is True
    assert traza["estado_calendario_visible"] != con_patron["estado_calendario_visible"], traza


def test_el_estado_visible_llega_al_csv_reproducible():
    serie = serie_con_salto_de_enero().iloc[:-7]
    traza = trazabilidad(serie, horizonte=6)
    resultado = {
        "ajuste_calendario": traza,
        "clasificacion_intervalo": clasificar_intervalo_por_cobertura(cobertura(0.95)),
    }
    tabla = construir_dataframe_reproducibilidad(serie, resultado)
    assert not tabla.empty
    fila = tabla.iloc[0]
    assert bool(fila["patron_cambio_anio_detectado_en_serie"]) is True
    assert bool(fila["efecto_cambio_anio_en_horizonte_solicitado"]) is False
    assert bool(fila["ajuste_cambio_anio_aplicado"]) is False
    # Lo que se exige es CONSISTENCIA entre artefactos, no una frase literal: el CSV
    # debe transportar exactamente el estado que publica la trazabilidad. Asi el
    # test no se rompe al reescribir el mensaje, pero si al desincronizarlos.
    assert str(fila["estado_cambio_anio"]) == str(traza["estado_calendario_visible"])
    _no_afirma_tratamiento(str(fila["estado_cambio_anio"]))
    # P0-C / ESTRATEGIA C2, 15-08-2026. Aqui se comprobaba que el CSV exportara
    # el identificador neutro de la banda -`clasificacion_intervalo_95`, su
    # etiqueta y si degradaba a escenario- para vigilar el vocabulario V-C. Esas
    # tres columnas se retiraron: tipifican una banda que esta version ya no
    # entrega, y un identificador neutro sigue siendo una afirmacion sobre un
    # intervalo ausente.
    #
    # La vigilancia NO se pierde, cambia de objeto: lo que el CSV debe declarar
    # ahora es que no publica intervalo, y lo que no debe hacer es reintroducirlo
    # por ninguna columna -ni la banda del 95 %, ni la del 80 %, ni la cobertura
    # con que se tipificaba-. V-C se sigue comprobando donde vive, sobre el
    # diccionario interno, en `tests/test_vocabulario_vc.py`.
    assert str(fila["intervalo_publicado"]) == "No", fila["intervalo_publicado"]
    assert "clasificacion_intervalo_95" not in tabla.columns, list(tabla.columns)
    assert not [c for c in tabla.columns if "80" in c], list(tabla.columns)
    # `limite_operativo_auditoria` acota el HORIZONTE, no el intervalo: no entra.
    #
    # ENDURECIDO 17-08-2026 (V-CODEX-R3, residual 1). Antes se toleraban
    # `ic95_inferior` e `ic95_superior` siempre que llegaran vacias. Se RETIRARON
    # del CSV: una columna permanentemente vacia cuyo nombre anuncia el intervalo
    # del 95 % en la cabecera es una afirmacion sobre un objeto que no se entrega,
    # y ningun consumidor dependia de ellas. Con ellas se fueron `metodo_intervalo`,
    # `sigma_h_intervalo`, `q95_intervalo` y los dos percentiles.
    prohibidas = [
        c for c in tabla.columns
        if any(m in str(c).lower() for m in
               ("cobertura", "nominal", "limite_inferior", "limite_superior", "ic95",
                "sigma_h", "q95_intervalo", "percentil_95", "metodo_intervalo"))
    ]
    assert not prohibidas, prohibidas


def test_en_produccion_el_calendario_no_toca_el_pronostico_puntual():
    """P0-F: el blindaje real. Se lee el resultado de produccion, no un ayudante.

    Las pruebas anteriores construyen la trazabilidad con
    ``resumen_trazabilidad``. Esta ejecuta el flujo completo para que el test no
    pueda volver a divergir de lo que la aplicacion produce: el factor de cada
    paso debe ser exactamente 1, es decir, el calendario no altera ningun numero
    del pronostico puntual.
    """
    serie = serie_con_salto_de_enero().iloc[:-7].copy()
    serie["Periodo"] = serie["Periodo"].str.replace("-", "_", regex=False)
    resultado = ejecutar_proyeccion(serie, 2024, 11, 2021, origen_horizonte="manual")

    ajuste = resultado.get("ajuste_calendario") or {}
    assert ajuste["patron_detectado_en_serie"] is True, ajuste
    assert ajuste["ajuste_calendario_aplicado"] is False, ajuste
    factores = [float(f) for f in (ajuste.get("factores_por_paso") or [])]
    assert factores, ajuste
    assert all(f == 1.0 for f in factores), factores
    _no_afirma_tratamiento(ajuste["estado_calendario_visible"])
    # El calendario tampoco sustenta el intervalo por ninguna via.
    assert resultado.get("intervalo_sustentado") is False, resultado.get("intervalo_sustentado")


# ==============================
# 2. CLASIFICACION DEL INTERVALO
# ==============================


def test_cobertura_alta_es_intervalo_nominal_sin_degradacion():
    r = clasificar_intervalo_por_cobertura(cobertura(0.95))
    assert r["clasificacion_interna"] == "nominal"
    assert r["degrada_a_escenario"] is False
    assert r["advertencia"] == ""
    assert "95" in r["etiqueta"]


def test_el_umbral_de_aceptacion_es_inclusivo():
    justo = clasificar_intervalo_por_cobertura(cobertura(COBERTURA_IC95_ACEPTABLE))
    assert justo["clasificacion_interna"] == "nominal", justo
    debajo = clasificar_intervalo_por_cobertura(cobertura(COBERTURA_IC95_ACEPTABLE - 1e-9))
    assert debajo["clasificacion_interna"] == "admisible_con_advertencia", debajo


def test_cobertura_intermedia_es_admisible_con_advertencia_y_no_degrada():
    r = clasificar_intervalo_por_cobertura(cobertura(0.85))
    assert r["clasificacion_interna"] == "admisible_con_advertencia"
    assert r["degrada_a_escenario"] is False, "una advertencia no debe bloquear el horizonte"
    assert r["advertencia"].strip()
    assert "85" in r["advertencia"]


def test_el_umbral_de_advertencia_es_inclusivo():
    justo = clasificar_intervalo_por_cobertura(cobertura(COBERTURA_IC95_ADVERTENCIA))
    assert justo["clasificacion_interna"] == "admisible_con_advertencia", justo
    debajo = clasificar_intervalo_por_cobertura(cobertura(COBERTURA_IC95_ADVERTENCIA - 1e-9))
    assert debajo["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", debajo


def test_cobertura_baja_se_advierte_con_su_valor():
    """CIERRE 08-08-2026: 0,80 deja de degradar y pasa a elegir la advertencia."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.44))
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal"
    assert r["degrada_a_escenario"] is False
    assert "rango de referencia" in r["etiqueta"].lower()
    assert "44%" in r["advertencia"]
    assert r["cobertura_observada"] == 0.44


def test_cobertura_no_calculable_no_afirma_ninguna_cobertura():
    """No se afirma lo que no se midio. P0-G REABIERTO: y tampoco se degrada.

    El docstring anterior decia «lo unico que sigue degradando». Con P0-C abierto,
    que la cobertura no sea calculable es la situacion NORMAL del intervalo, no una
    excepcion: degradar por ella convertia el bloqueo metodologico en un veto del
    punto. Lo sustantivo -no afirmar una cobertura que no existe- se conserva.
    """
    r = clasificar_intervalo_por_cobertura(
        cobertura(None, verificable=False),
        errores_por_horizonte={1: np.arange(9, dtype=float)},
    )
    assert r["clasificacion_interna"] == "no_calculable"
    assert r["cobertura_minima"] is None
    assert r["degrada_a_escenario"] is False, r
    assert "no es calculable" in r["advertencia"]
    texto = f"{r['etiqueta']} {r['advertencia']}".lower()
    for prohibida in ("garantiza", "validad", "asegurad"):
        assert prohibida not in texto, (prohibida, texto)


def test_ninguna_clasificacion_promete_garantia_exacta():
    prohibidas = ("garantiza", "garantía", "garantia", "exactamente el 95", "conformal")
    for minima in (None, 0.44, 0.85, 0.99):
        r = clasificar_intervalo_por_cobertura(
            cobertura(minima, verificable=minima is not None)
        )
        texto = f"{r['etiqueta']} {r['advertencia']}".lower()
        for palabra in prohibidas:
            assert palabra not in texto, (minima, palabra, texto)


def test_la_clasificacion_no_toca_ningun_numero_del_intervalo():
    """Blindaje del limite autorizado: clasificar no altera limites ni pronosticos."""
    entrada = cobertura(0.44)
    copia = dict(entrada)
    r = clasificar_intervalo_por_cobertura(entrada)
    assert entrada == copia, "la clasificacion no debe mutar la cobertura recibida"
    # Claves que la clasificacion debe seguir entregando siempre.
    assert {"clasificacion", "etiqueta", "cobertura_minima",
            "degrada_a_escenario", "umbral_aplicado", "advertencia"} <= set(r)
    # RA-01 anadio el detalle del paso exacto. Lo que se blinda aqui es que la
    # clasificacion no produzca ni toque ningun numero del intervalo ni del
    # pronostico: eso sigue siendo territorio exclusivo del calculo.
    # La remediacion del 04-08-2026 anadio campos DESCRIPTIVOS separados
    # (nivel nominal, cobertura observada, tipo de banda, etiqueta visible,
    # limitacion y consecuencia). Ninguno es un numero del intervalo: la
    # prohibicion de mas abajo sigue siendo el blindaje real.
    assert set(r) <= {
        "clasificacion", "clasificacion_interna", "etiqueta", "cobertura_minima",
        "degrada_a_escenario",
        "umbral_aplicado", "advertencia", "paso_exacto", "n_errores_paso_exacto",
        "verificable_paso_exacto", "cobertura_paso_exacto",
        "etiqueta_visible", "tipo_banda", "nivel_nominal", "cobertura_observada",
        "limitacion", "consecuencia_operativa",
        # G-2: el minimo entre horizontes se publica localizado y con su
        # conteo. Ninguno de los cinco es un numero del intervalo entregado.
        "cobertura_minima_global", "horizonte_de_cobertura_minima",
        "n_errores_del_horizonte_minimo", "advertencia_consistencia",
        "consistencia_entre_horizontes",
        # Cobertura descriptiva: recuento del paso y distancia al nivel
        # nominal. Son cifras de la EVALUACION, no del intervalo entregado.
        "aciertos", "total_evaluado", "cobertura_x_y",
        "diferencia_pp_frente_nominal",
        # Publicacion con n < 16: la medicion se publica siempre y la aptitud
        # para la regla se declara aparte, con su nota de muestra.
        "cobertura_apta_para_regla", "limitacion_muestra",
        # Conversion de 0,90 en descriptivo (07-08-2026): la lectura con las
        # seis magnitudes que sostienen la cifra, el valor del corte y la
        # declaracion de que no decide. Ninguno es un numero del intervalo.
        "lectura_descriptiva", "umbral_aceptacion_descriptivo",
        "papel_umbral_aceptacion",
    }, set(r)
    prohibidas = {
        "limite_inferior", "limite_superior", "limite_inferior_95", "limite_superior_95",
        "y_proj", "indice_proyectado", "q95", "sigma_h", "offsets", "semiancho",
    }
    assert not prohibidas & set(r), set(r)


def test_los_umbrales_estan_declarados_como_criterios_operativos():
    from app_icociv.estadistica import criterios
    fuente = Path(criterios.__file__).read_text(encoding="utf-8-sig").lower()
    assert "criterios operativos internos" in fuente
    assert "no reglas estadisticas universales" in fuente or \
           "no son reglas estadisticas universales" in fuente


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
