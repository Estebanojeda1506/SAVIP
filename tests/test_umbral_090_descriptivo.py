"""El corte 0,90 es descriptivo: no decide nada (conversion del 07-08-2026).

Hasta esta fecha `COBERTURA_IC95_ACEPTABLE` encabezaba la escalera de
clasificacion. Su efecto decisorio aislado, medido con la variante
E-090-AISLADO sobre los cincuenta escenarios, era **cero**: las dos ramas que
separaba comparten `degrada_a_escenario=False`, comparten `tipo_banda` y
comparten etiqueta visible.

Pero esa inocuidad era un accidente del orden de los `if`. Estas pruebas fijan
que ahora es **estructural**: la degradacion se decide fuera de la escalera y
solo con el corte de advertencia, de modo que mover 0,90 a cualquier valor no
puede cambiar ni un estado ni un tipo de banda.

La prueba fuerte es `test_mover_el_corte_no_mueve_ninguna_decision`: recorre el
corte por todo el rango util y comprueba que la decision no se inmuta. Si
alguien devolviera 0,90 a la escalera, esa prueba se pone roja.

0,90 **no se sustituye por 0,95** ni por ningun otro corte: conserva su valor y
pierde su funcion.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app_icociv.estadistica.criterios import (  # noqa: E402
    COBERTURA_IC95_ACEPTABLE,
    COBERTURA_IC95_ADVERTENCIA,
    MIN_ERRORES_COBERTURA_EMPIRICA,
)
from app_icociv.proyeccion import servicio_proyeccion as sp  # noqa: E402
from app_icociv.proyeccion.servicio_proyeccion import (  # noqa: E402
    clasificar_intervalo_por_cobertura,
)

#: Frases que ninguna salida puede contener como regla.
PROHIBIDAS = (
    "cobertura garantizada", "cobertura asegurada",
    "cumple el 90", "no cumple el 90", "cumple el 95", "no cumple el 95",
    "validado por cobertura", "aprobado por cobertura", "cobertura validada",
)


def cobertura(valor: float | None, n_paso: int = 24, paso: int = 6,
              n_prueba: int = 22) -> dict:
    return {
        "verificable": True,
        "verificable_paso_exacto": n_paso >= MIN_ERRORES_COBERTURA_EMPIRICA,
        "paso_exacto": paso,
        "n_errores_paso_exacto": n_paso,
        "cobertura_95_paso_exacto": valor,
        "cobertura_95_minima": valor,
        "metodo_evaluacion": "origen_movil",
        "por_horizonte": [
            {"horizonte": paso, "cobertura_95": valor, "n_prueba": n_prueba}
        ],
    }


# ==============================================================
# 1. 0,90 no gobierna ninguna consecuencia
# ==============================================================
#: Claves que 0,90 no puede mover. `consecuencia_operativa` queda fuera a
#: proposito: las dos ramas difieren en la clausula «; se advierte», que es
#: justo la redaccion que 0,90 conserva. Que ambas digan «no se degrada» se
#: comprueba aparte, por su contenido y no por igualdad de cadena.
DECISORIAS = (
    "degrada_a_escenario", "tipo_banda", "clasificacion", "etiqueta_visible",
)


def test_las_dos_ramas_de_090_comparten_toda_consecuencia():
    """Encima y debajo de 0,90 el resultado operativo es identico."""
    encima = clasificar_intervalo_por_cobertura(cobertura(0.95))
    debajo = clasificar_intervalo_por_cobertura(cobertura(0.85))
    for clave in DECISORIAS:
        assert encima[clave] == debajo[clave], (clave, encima[clave], debajo[clave])
    # La consecuencia se redacta distinto, pero declara lo mismo.
    for r in (encima, debajo):
        assert "no se degrada" in r["consecuencia_operativa"], r


def test_mover_el_corte_no_mueve_ninguna_decision():
    """El blindaje: recorrer 0,90 por todo el rango no cambia nada decisorio.

    Si 0,90 volviera a la escalera de decision, alguno de estos barridos
    produciria un `degrada_a_escenario` distinto y la prueba fallaria.
    """
    original = sp.COBERTURA_IC95_ACEPTABLE
    muestras = (0.80, 0.83, 0.90, 0.95, 0.99, 1.0)
    try:
        referencia = {
            v: clasificar_intervalo_por_cobertura(cobertura(v))
            for v in muestras
        }
        for corte in (0.0, 0.5, 0.80, 0.85, 0.90, 0.95, 1.0):
            sp.COBERTURA_IC95_ACEPTABLE = corte
            for v in muestras:
                r = clasificar_intervalo_por_cobertura(cobertura(v))
                base = referencia[v]
                for clave in DECISORIAS + (
                    "cobertura_observada", "cobertura_minima",
                    "aciertos", "total_evaluado", "diferencia_pp_frente_nominal",
                ):
                    assert r[clave] == base[clave], (corte, v, clave)
    finally:
        sp.COBERTURA_IC95_ACEPTABLE = original
    assert sp.COBERTURA_IC95_ACEPTABLE == 0.90, "el valor productivo sigue siendo 0,90"


def test_ningun_corte_de_cobertura_degrada_ya():
    """CIERRE 08-08-2026: 0,80 tampoco decide. Ahora solo elige la advertencia.

    Hasta esta fecha era el ultimo corte de proporcion con efecto. No tiene
    fuente: ninguna referencia fija una cobertura observada minima por debajo
    de la cual un intervalo deje de poder comunicarse. Lo que si es informacion
    -el valor, el recuento x/y y la distancia al nominal- se publica siempre.
    """
    for valor in (COBERTURA_IC95_ADVERTENCIA, COBERTURA_IC95_ADVERTENCIA - 1e-9,
                  0.5, 0.0):
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert r["degrada_a_escenario"] is False, (valor, r["clasificacion_interna"])
        assert r["cobertura_observada"] == valor


def test_por_debajo_de_080_se_advierte_con_el_valor():
    """Retirar el veto no puede retirar la informacion."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.44))
    assert r["clasificacion_interna"] == "cobertura_por_debajo_del_nominal", r
    assert "44%" in r["advertencia"]
    assert r["cobertura_x_y"]
    assert r["diferencia_pp_frente_nominal"] is not None


# ==============================================================
# 2. 0,90 conserva su papel de redaccion, y lo declara
# ==============================================================
def test_090_sigue_eligiendo_la_redaccion():
    """Lo unico que conserva: si se emite o no la nota de distancia."""
    assert clasificar_intervalo_por_cobertura(cobertura(0.95))["advertencia"] == ""
    assert clasificar_intervalo_por_cobertura(cobertura(0.85))["advertencia"].strip()


def test_el_umbral_de_aceptacion_sigue_siendo_inclusivo():
    justo = clasificar_intervalo_por_cobertura(cobertura(COBERTURA_IC95_ACEPTABLE))
    assert justo["clasificacion_interna"] == "nominal", justo
    debajo = clasificar_intervalo_por_cobertura(
        cobertura(COBERTURA_IC95_ACEPTABLE - 1e-9))
    assert debajo["clasificacion_interna"] == "admisible_con_advertencia", debajo


def test_el_papel_descriptivo_viaja_en_el_resultado():
    """Quien audite la salida no deberia tener que abrir el codigo."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.923))
    assert r["umbral_aceptacion_descriptivo"] == COBERTURA_IC95_ACEPTABLE
    papel = r["papel_umbral_aceptacion"].lower()
    assert "descriptivo" in papel
    assert "no decide" in papel


def test_el_criterio_publicado_nombra_la_regla_real():
    """`umbral_aplicado` debe nombrar 0,80, no presentar 0,90 como aprobacion."""
    r = clasificar_intervalo_por_cobertura(cobertura(0.95))
    texto = r["umbral_aplicado"]
    assert f"{COBERTURA_IC95_ADVERTENCIA:.2f}" in texto, texto
    assert "no interviene" in texto, texto


# ==============================================================
# 3. La lectura descriptiva sustituye a la categoria
# ==============================================================
def test_la_lectura_reune_las_seis_magnitudes():
    r = clasificar_intervalo_por_cobertura(cobertura(0.909091, n_paso=24, n_prueba=22))
    lectura = r["lectura_descriptiva"]
    assert "20/22" in lectura, lectura                    # recuento x/y
    assert "0.909" in lectura, lectura                    # proporcion
    assert "95%" in lectura, lectura                      # nivel nominal
    assert "pp" in lectura, lectura                       # diferencia
    assert "n = 24" in lectura, lectura                   # n del paso
    assert "origen movil" in lectura, lectura             # metodo


def test_la_lectura_cabe_en_una_celda_de_tabla():
    """Viaja al DOCX: por encima de 180 caracteres deforma la composicion."""
    for valor in (0.0, 0.727, 0.85, 0.923, 1.0):
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        assert len(r["lectura_descriptiva"]) <= 180, (valor, r["lectura_descriptiva"])
    assert len(sp.PAPEL_UMBRAL_ACEPTACION) <= 180


def test_sin_medicion_no_se_inventa_lectura():
    r = clasificar_intervalo_por_cobertura(cobertura(None, n_paso=9))
    assert r["lectura_descriptiva"] == ""


def test_ninguna_salida_convierte_090_en_una_regla():
    for valor in (None, 0.0, 0.727, 0.85, 0.923, 1.0):
        r = clasificar_intervalo_por_cobertura(cobertura(valor))
        texto = " ".join(str(r.get(c, "")) for c in (
            "advertencia", "umbral_aplicado", "lectura_descriptiva",
            "papel_umbral_aceptacion", "etiqueta_visible", "consecuencia_operativa",
        )).lower()
        for prohibida in PROHIBIDAS:
            assert prohibida not in texto, (valor, prohibida, texto)


# ==============================================================
# 4. Lo que esta conversion NO toca
# ==============================================================
def test_los_otros_dos_criterios_siguen_intactos():
    assert MIN_ERRORES_COBERTURA_EMPIRICA == 16
    assert COBERTURA_IC95_ADVERTENCIA == 0.80
    assert COBERTURA_IC95_ACEPTABLE == 0.90, "0,90 conserva su valor; pierde su funcion"


def test_el_minimo_de_contrastes_ya_no_degrada_pero_se_declara():
    """CIERRE 08-08-2026: 16 deja de decidir; el tamano de muestra se publica.

    Un paso con 15 errores tiene la cobertura MEDIDA. Que la muestra sea corta
    es una limitacion de precision, no una imposibilidad, y el corte 16 no
    tiene fuente. La medicion, `n` y la limitacion viajan en la salida.
    """
    r = clasificar_intervalo_por_cobertura(cobertura(1.0, n_paso=15))
    assert r["clasificacion_interna"] == "medida_con_muestra_reducida", r
    assert r["degrada_a_escenario"] is False
    assert r["cobertura_observada"] == 1.0
    assert r["n_errores_paso_exacto"] == 15
    assert "muestra reducida" in r["advertencia"]


def test_g2_no_se_ve_afectada():
    """La advertencia de consistencia sigue disparandose con 0,90."""
    entrada = cobertura(1.0, paso=6)
    entrada["por_horizonte"] = [
        {"horizonte": 4, "cobertura_95": 0.762, "n_prueba": 21},
        {"horizonte": 6, "cobertura_95": 1.0, "n_prueba": 19},
    ]
    entrada["cobertura_95_minima"] = 0.762
    r = clasificar_intervalo_por_cobertura(entrada)
    assert r["consistencia_entre_horizontes"]["aplica"] is True, r
    assert r["degrada_a_escenario"] is False, "G-2: la advertencia no degrada"


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
