"""Pruebas del sistema de tema de SAVIP.

La regla que sostiene el sistema es que la plantilla QSS no puede contener
colores literales: todo se resuelve contra los tokens. El mecanismo anterior
—reemplazar cadenas hexadecimales para obtener el tema oscuro— dejaba fijados en
claro los colores que nadie hubiera registrado. Estas pruebas impiden volver a
ese estado.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_icociv.interfaz.tema import tokens
from app_icociv.interfaz.tema.colores import (
    CLARO,
    OSCURO,
    TEMAS_DISPONIBLES,
    contraste,
    hex_a_rgb,
    mezclar,
    normalizar_tema,
    paleta,
    rgba,
)
from app_icociv.interfaz.tema.estilos import (
    contexto_estilos,
    hoja_estilos,
    validar_plantilla,
)

# WCAG 2.1 AA: 4.5:1 para texto normal, 3:1 para texto grande y componentes.
CONTRASTE_TEXTO = 4.5
CONTRASTE_COMPONENTE = 3.0


def test_plantilla_sin_colores_literales() -> None:
    """Ningún color escrito a mano puede sobrevivir en la plantilla."""
    problemas = validar_plantilla()
    assert problemas == [], "Plantilla con problemas:\n  - " + "\n  - ".join(problemas)


def test_hoja_se_resuelve_por_completo_en_ambos_temas() -> None:
    """Tras componer no puede quedar ningún marcador sin sustituir."""
    for tema in TEMAS_DISPONIBLES:
        hoja = hoja_estilos(tema)
        pendientes = re.findall(r"\{[a-z0-9_]+\}", hoja)
        assert not pendientes, f"Tema {tema} deja tokens sin resolver: {pendientes[:5]}"
        assert len(hoja) > 5000, f"La hoja del tema {tema} parece truncada"


def test_los_dos_temas_producen_hojas_distintas() -> None:
    """Si ambas hojas coinciden, el tema oscuro no se está aplicando."""
    assert hoja_estilos("claro") != hoja_estilos("oscuro")


def test_ambas_paletas_tienen_las_mismas_claves() -> None:
    """Una clave presente solo en un tema rompería ese tema al usarla."""
    faltan_en_oscuro = set(CLARO) - set(OSCURO)
    faltan_en_claro = set(OSCURO) - set(CLARO)
    assert not faltan_en_oscuro, f"Ausentes en oscuro: {sorted(faltan_en_oscuro)}"
    assert not faltan_en_claro, f"Ausentes en claro: {sorted(faltan_en_claro)}"


def test_todos_los_colores_son_hexadecimales_validos() -> None:
    for tema in TEMAS_DISPONIBLES:
        for clave, valor in paleta(tema).items():
            hex_a_rgb(valor)  # lanza ValueError si el formato es inválido
            assert valor.startswith("#"), f"{tema}.{clave} no es hexadecimal: {valor}"


def test_contraste_de_texto_cumple_wcag_aa() -> None:
    """Texto principal y secundario sobre cada superficie deben ser legibles."""
    superficies = ("fondo", "superficie", "superficie_2", "superficie_3")
    for tema in TEMAS_DISPONIBLES:
        p = paleta(tema)
        for superficie in superficies:
            for texto in ("texto", "texto_secundario"):
                razon = contraste(p[texto], p[superficie])
                assert razon >= CONTRASTE_TEXTO, (
                    f"{tema}: {texto} sobre {superficie} da {razon:.2f}:1, "
                    f"por debajo de {CONTRASTE_TEXTO}:1"
                )


def test_contraste_de_acentos_y_estados() -> None:
    """Los colores de marca y estado deben distinguirse sobre su superficie."""
    for tema in TEMAS_DISPONIBLES:
        p = paleta(tema)
        for clave in ("principal", "secundario", "exito", "advertencia", "error", "acento"):
            razon = contraste(p[clave], p["superficie"])
            assert razon >= CONTRASTE_COMPONENTE, (
                f"{tema}: {clave} sobre superficie da {razon:.2f}:1"
            )


def test_texto_sobre_color_principal_es_legible() -> None:
    """El texto de los botones primarios va sobre el color de marca."""
    for tema in TEMAS_DISPONIBLES:
        p = paleta(tema)
        razon = contraste(p["texto_sobre_principal"], p["principal"])
        assert razon >= CONTRASTE_TEXTO, f"{tema}: texto sobre principal da {razon:.2f}:1"


def test_tema_oscuro_eleva_aclarando() -> None:
    """En oscuro la elevación se expresa aclarando, no con sombra."""
    p = OSCURO

    def luminancia(color: str) -> float:
        r, g, b = hex_a_rgb(color)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    assert luminancia(p["fondo"]) < luminancia(p["superficie"]) < luminancia(p["superficie_2"]) < luminancia(p["superficie_3"])


def test_tema_claro_oscurece_el_fondo_respecto_de_la_tarjeta() -> None:
    """En claro la tarjeta debe destacar sobre el fondo de la ventana."""
    p = CLARO
    assert p["fondo"] != p["superficie"]
    assert contraste(p["superficie"], p["fondo"]) > 1.0


def test_normalizar_tema_admite_entradas_invalidas() -> None:
    for entrada in (None, "", "  ", "OSCURO ", "azul", 42):
        assert normalizar_tema(entrada) in TEMAS_DISPONIBLES
    assert normalizar_tema("OSCURO ") == "oscuro"
    assert normalizar_tema("desconocido") == "claro"


def test_rgba_y_mezclar() -> None:
    assert rgba("#FFFFFF", 0.5) == "rgba(255, 255, 255, 0.500)"
    assert rgba("#000000", 5.0).endswith("1.000)"), "El alfa debe recortarse a 1"
    assert mezclar("#000000", "#FFFFFF", 0.5) == "#808080"
    assert mezclar("#123456", "#654321", 0.0) == "#123456"


def test_contexto_incluye_forma_y_tipografia() -> None:
    contexto = contexto_estilos("claro")
    for clave in ("espacio_4", "radio_grande", "altura_boton", "familia_interfaz", "peso_medio"):
        assert clave in contexto, f"Falta el token {clave} en el contexto"


def test_escala_de_espaciado_es_multiplo_de_cuatro() -> None:
    """El ritmo vertical depende de que la escala no tenga excepciones."""
    escala = [
        tokens.ESPACIO_1, tokens.ESPACIO_2, tokens.ESPACIO_3, tokens.ESPACIO_4,
        tokens.ESPACIO_5, tokens.ESPACIO_6, tokens.ESPACIO_7, tokens.ESPACIO_8,
    ]
    for valor in escala:
        assert valor % 4 == 0, f"{valor} rompe la escala de base 4"
    assert escala == sorted(escala), "La escala debe ser creciente"


def test_duraciones_de_animacion_son_breves() -> None:
    """Una animación larga estorba; el plan fijó el techo en 300 ms."""
    for duracion in (
        tokens.DURACION_RAPIDA,
        tokens.DURACION_NORMAL,
        tokens.DURACION_PAUSADA,
        tokens.DURACION_ENTRADA,
        tokens.DURACION_NOTIFICACION,
    ):
        assert 0 < duracion <= 300, f"Duración fuera del rango previsto: {duracion} ms"


def test_elevaciones_crecen_de_forma_monotona() -> None:
    niveles = [tokens.ELEVACION_0, tokens.ELEVACION_1, tokens.ELEVACION_2, tokens.ELEVACION_3]
    for anterior, siguiente in zip(niveles, niveles[1:]):
        assert siguiente.desenfoque >= anterior.desenfoque
        assert siguiente.opacidad >= anterior.opacidad


def test_las_areas_de_desplazamiento_declaran_fondo() -> None:
    """Un QScrollArea sin fondo hereda la paleta del sistema y sale negro.

    Ocurrió dos veces durante el rediseño: en el panel de navegación y en el
    módulo de Empalme, ambos con tema claro sobre un Windows en modo oscuro.
    La regla general debe existir para cubrir también los scroll sin nombre.
    """
    contenido = Path(
        ROOT / "app_icociv" / "interfaz" / "tema" / "plantilla.qss"
    ).read_text(encoding="utf-8")
    assert "QScrollArea {{" in contenido, "Falta la regla general de QScrollArea"
    indice = contenido.index("QScrollArea {{")
    bloque = contenido[indice : contenido.index("}}", indice)]
    assert "background:" in bloque, "La regla general debe fijar un fondo"


def test_los_controles_deshabilitados_no_destacan() -> None:
    """Un control apagado no puede quedar más claro que uno activo."""
    from app_icociv.interfaz.tema.colores import hex_a_rgb

    def luminancia(color: str) -> float:
        r, g, b = hex_a_rgb(color)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for tema in TEMAS_DISPONIBLES:
        p = paleta(tema)
        if tema == "oscuro":
            assert luminancia(p["deshabilitado"]) < luminancia(p["superficie"]), (
                "En oscuro el deshabilitado debe ser más apagado que la tarjeta"
            )
        else:
            assert luminancia(p["deshabilitado"]) < luminancia(p["superficie"])


def test_los_campos_se_distinguen_de_su_contenedor() -> None:
    """Con el mismo tono que la tarjeta, los formularios largos se aplanan."""
    for tema in TEMAS_DISPONIBLES:
        p = paleta(tema)
        assert p["campo"] != p["superficie_formulario"], (
            f"{tema}: el campo debe diferenciarse de su contenedor"
        )
        assert p["campo"] != p["superficie"]


def test_compatibilidad_con_constantes_visuales() -> None:
    """La API anterior sigue viva: varios módulos aún importan de ahí."""
    from app_icociv.interfaz.estilos.constantes_visuales import (
        TOOLTIPS_TECNICOS,
        aplicar_paleta_qss,
        paleta_tema,
    )

    for tema in TEMAS_DISPONIBLES:
        colores = paleta_tema(tema)
        # Claves históricas que el código existente sigue consultando.
        for clave in (
            "fondo_principal", "fondo_secundario", "texto_principal", "texto_secundario",
            "bordes", "acento", "error", "grafica", "rejilla", "borde_control",
        ):
            assert clave in colores, f"El alias {clave} desapareció del tema {tema}"
    assert aplicar_paleta_qss("", "oscuro") == hoja_estilos("oscuro")
    assert "horizonte" in TOOLTIPS_TECNICOS


if __name__ == "__main__":
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            funcion()
            print(f"OK {nombre}")
    print("OK: sistema de tema de SAVIP.")
