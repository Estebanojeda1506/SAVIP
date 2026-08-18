"""Modelo de documento común a los informes DOCX y PDF de SAVIP.

Los dos renderizadores (``docx_render`` y ``pdf_render``) reciben exactamente el
mismo :class:`Informe`: una lista de secciones formadas por bloques tipados. Así
el contenido se decide una sola vez, en ``contenido.py``, y cada formato decide
únicamente *cómo* se dibuja, nunca *qué* se dice. Sin esta separación las dos
salidas vuelven a divergir, que es justo lo que ocurría con el generador
anterior.

Este módulo no lee ni interpreta resultados estadísticos: solo describe forma,
color y formato numérico.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Literal

from app_icociv.interfaz.tema.colores import CLARO


# ==============================
# PALETA DOCUMENTAL
# ==============================
# Los colores se toman del sistema visual de la aplicación; aquí no se inventa
# ninguno. Solo se seleccionan los que tienen sentido sobre papel blanco, que es
# siempre el soporte de un informe (el tema oscuro no se traslada al documento).

PALETA = {
    "marca": CLARO["principal"],
    "marca_intensa": CLARO["principal_intenso"],
    "marca_suave": CLARO["principal_suave"],
    "acento": CLARO["secundario"],
    "texto": CLARO["texto"],
    "texto_secundario": CLARO["texto_secundario"],
    "borde": CLARO["borde"],
    "borde_fuerte": CLARO["borde_fuerte"],
    "superficie": CLARO["superficie"],
    "superficie_alterna": CLARO["superficie_2"],
    "aviso": CLARO["advertencia"],
    "aviso_fondo": CLARO["advertencia_suave"],
    "error": CLARO["error"],
    "error_fondo": CLARO["error_suave"],
    "exito": CLARO["exito"],
    "exito_fondo": CLARO["exito_suave"],
    "informacion": CLARO["informacion"],
    "informacion_fondo": CLARO["informacion_suave"],
}

# Dos tipografías, como pide el diseño: uno con serifas para el cuerpo no aporta
# nada en pantalla, así que se usa una sans para todo y una monoespaciada solo
# para fórmulas y sustituciones numéricas, donde la alineación importa.
FUENTE_TEXTO = "Calibri"
FUENTE_TEXTO_PDF = "Helvetica"
FUENTE_MONO = "Consolas"
FUENTE_MONO_PDF = "Courier"

NOMBRE_APLICACION = "SAVIP"
NOMBRE_COMPLETO = "SAVIP — Sistema de Análisis de Variaciones de Precios"


# ==============================
# FORMATEADORES
# ==============================

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Separador de miles: espacio duro. Evita que un número se parta al final de
# una línea y existe en cualquier fuente, a diferencia del espacio fino.
ESPACIO_MILES = " "

MONEDAS = {
    "COP": ("$", ".", ","),
    "USD": ("US$", ",", "."),
    "EUR": ("€", ".", ","),
}


def es_numero(valor: Any) -> bool:
    """True solo si el valor es un número real finito."""
    if isinstance(valor, bool):
        return False
    try:
        return math.isfinite(float(valor))
    except (TypeError, ValueError):
        return False


def formato_indice(valor: Any, decimales: int = 4) -> str:
    """Índices con cuatro decimales y coma decimal (convención §10.1)."""
    if not es_numero(valor):
        return "No disponible" if valor in (None, "") else str(valor)
    return f"{float(valor):,.{decimales}f}".replace(",", ESPACIO_MILES).replace(".", ",")


def formato_porcentaje(valor: Any, decimales: int = 1) -> str:
    """Porcentajes con uno o dos decimales y espacio antes del signo (§10.2)."""
    if not es_numero(valor):
        return "No disponible"
    return f"{float(valor):.{decimales}f}".replace(".", ",") + " %"


def formato_moneda(valor: Any, codigo: str = "COP", decimales: int = 2) -> str:
    """Moneda con separadores según la configuración regional elegida (§10.3)."""
    if not es_numero(valor):
        return "No disponible"
    simbolo, miles, decimal = MONEDAS.get(codigo, MONEDAS["COP"])
    entero = f"{float(valor):,.{decimales}f}"
    entero = entero.replace(",", "\x00").replace(".", decimal).replace("\x00", miles)
    return f"{simbolo} {entero}"


def formato_entero(valor: Any) -> str:
    if not es_numero(valor):
        return "No disponible"
    return f"{int(round(float(valor))):,}".replace(",", ".")


def periodo_largo(periodo: Any) -> str:
    """``2026_5`` / ``2026-05`` -> ``mayo de 2026`` (§10.4)."""
    anio, mes = _partes_periodo(periodo)
    if anio is None or mes is None:
        return str(periodo or "No disponible")
    return f"{MESES_ES[mes - 1]} de {anio}"


def periodo_corto(periodo: Any) -> str:
    """Forma compacta ``AAAA-MM`` para tablas y ejes."""
    anio, mes = _partes_periodo(periodo)
    if anio is None or mes is None:
        return str(periodo or "")
    return f"{anio:04d}-{mes:02d}"


def fecha_larga(momento: datetime | None = None) -> str:
    momento = momento or datetime.now()
    return f"{momento.day} de {MESES_ES[momento.month - 1]} de {momento.year}"


def fecha_hora_larga(momento: datetime | None = None) -> str:
    momento = momento or datetime.now()
    return f"{fecha_larga(momento)}, {momento:%H:%M}"


def _partes_periodo(periodo: Any) -> tuple[int | None, int | None]:
    if hasattr(periodo, "year") and hasattr(periodo, "month"):
        return int(periodo.year), int(periodo.month)
    texto = str(periodo or "").strip().replace("/", "_").replace("-", "_")
    partes = [p for p in texto.split("_") if p]
    if len(partes) >= 2 and partes[0].isdigit() and partes[1].isdigit():
        mes = int(partes[1])
        if 1 <= mes <= 12:
            return int(partes[0]), mes
    return None, None


def identificador_informe(momento: datetime | None = None) -> str:
    """Identificador único y reproducible del informe (§13)."""
    momento = momento or datetime.now()
    return f"{NOMBRE_APLICACION}-INF-{momento:%Y%m%d-%H%M%S}"


def nombre_archivo_informe(tipo: str, referencia: str, extension: str, momento: datetime | None = None) -> str:
    """Nombre de archivo claro y sin caracteres inválidos (§12)."""
    momento = momento or datetime.now()
    etiquetas = {
        "ejecutivo": "Informe_Ejecutivo",
        "tecnico": "Informe_Tecnico",
        "empalme": "Ajuste_ICCP_ICOCIV",
        "personalizado": "Informe_Personalizado",
    }
    partes = [NOMBRE_APLICACION, etiquetas.get(tipo, "Informe"), _limpiar_nombre(referencia), f"{momento:%Y%m%d}"]
    return "_".join(p for p in partes if p) + "." + extension.lstrip(".")


def _limpiar_nombre(texto: str, maximo: int = 40) -> str:
    """Quita acentos y caracteres inválidos en nombres de archivo de Windows."""
    plano = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    plano = re.sub(r"[^A-Za-z0-9]+", "_", plano).strip("_")
    return plano[:maximo].strip("_")


# ==============================
# BLOQUES DE CONTENIDO
# ==============================


@dataclass(frozen=True)
class Parrafo:
    texto: str
    enfasis: bool = False


@dataclass(frozen=True)
class Vinetas:
    items: list[str]


@dataclass(frozen=True)
class Ficha:
    """Bloque de cifras principales: pares campo/valor en formato tarjeta."""

    filas: list[tuple[str, str]]
    destacados: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Tabla:
    encabezados: list[str]
    filas: list[list[str]]
    titulo: str = ""
    nota: str = ""
    fuente: str = ""
    # Índice de las columnas cuyas cifras se alinean a la derecha (§10.5).
    columnas_numericas: tuple[int, ...] = ()
    anchos: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Imagen:
    datos: bytes
    pie: str = ""
    ancho_cm: float = 16.0


@dataclass(frozen=True)
class Aviso:
    """Recuadro visible de advertencias y limitaciones."""

    titulo: str
    items: list[str]
    nivel: Literal["advertencia", "informacion", "error"] = "advertencia"


@dataclass(frozen=True)
class Formula:
    """Fórmula general seguida de su sustitución numérica y resultado."""

    etiqueta: str
    general: str
    sustitucion: list[str]
    resultado: str


@dataclass(frozen=True)
class Firmas:
    roles: list[str]


Bloque = Parrafo | Vinetas | Ficha | Tabla | Imagen | Aviso | Formula | Firmas


@dataclass
class Seccion:
    clave: str
    titulo: str
    bloques: list[Bloque] = field(default_factory=list)
    nivel: int = 1
    # Las subsecciones se aplanan al renderizar; el nivel controla la jerarquía.

    def vacia(self) -> bool:
        return not self.bloques


@dataclass
class Portada:
    titulo: str
    subtitulo: str
    filas: list[tuple[str, str]]
    observaciones: str = ""
    logo: bytes | None = None


@dataclass
class Informe:
    """Documento completo, ya resuelto, listo para renderizar."""

    portada: Portada | None
    secciones: list[Seccion]
    identificador: str
    tipo: str
    generado: datetime
    pie: str = ""

    def secciones_visibles(self) -> list[Seccion]:
        """Descarta secciones sin bloques: nunca se emite un título vacío (§14.3)."""
        return [s for s in self.secciones if not s.vacia()]

    def indice(self) -> list[tuple[int, str]]:
        return [(s.nivel, s.titulo) for s in self.secciones_visibles()]


# ==============================
# CONFIGURACIÓN DEL INFORME
# ==============================

SECCIONES_DISPONIBLES: tuple[tuple[str, str], ...] = (
    ("portada", "Portada"),
    ("resumen", "Resumen ejecutivo"),
    ("identificacion", "Identificación de la serie"),
    ("ficha", "Ficha de resultados"),
    ("grafica_principal", "Gráfica principal"),
    ("tabla_proyeccion", "Tabla de proyección"),
    ("interpretacion", "Interpretación"),
    ("advertencias", "Advertencias y limitaciones"),
    ("preparacion", "Preparación de datos"),
    ("fundamento", "Fundamento estadístico"),
    ("modelos", "Modelos comparados"),
    ("seleccion_modelo", "Criterio de selección de modelo"),
    ("metricas", "Métricas"),
    ("backtesting", "Backtesting"),
    # P0-C / C2: las dos secciones existen, pero ya no entregan banda ni
    # cobertura. Se renombran para que el selector no ofrezca al usuario un
    # contenido que el informe no va a contener.
    ("intervalos", "Incertidumbre del pronóstico"),
    ("cobertura", "Evidencia fuera de muestra del horizonte"),
    ("residuos", "Diagnóstico de residuos"),
    ("atipicos", "Valores atípicos"),
    ("calendario", "Patrón calendario"),
    ("horizonte", "Horizonte estadístico"),
    ("formulas", "Fórmulas"),
    ("reproducibilidad", "Reproducibilidad"),
    ("anexos", "Anexos"),
)

GRAFICAS_DISPONIBLES: tuple[tuple[str, str], ...] = (
    ("historico_proyeccion", "Histórico y proyección"),
    # P0-C / C2: retirada la opcion de grafica del intervalo. La banda no se
    # dibuja, de modo que ofrecerla dejaba una casilla que no producia nada.
    ("comparacion_modelos", "Comparación de modelos"),
    ("errores_horizonte", "Errores por horizonte"),
    ("residuos", "Residuos"),
    ("atipicos", "Valores atípicos"),
    ("calendario", "Patrón calendario"),
)

PRESET_EJECUTIVO: frozenset[str] = frozenset({
    "portada", "resumen", "identificacion", "ficha", "grafica_principal",
    "interpretacion", "advertencias", "tabla_proyeccion", "reproducibilidad",
})

# Los anexos son opcionales por diseño: la serie completa y las ventanas de
# backtesting ya viajan en el CSV reproducible, y repetirlas añade dos páginas
# de tablas que casi nadie lee. Siguen disponibles en el selector.
PRESET_TECNICO: frozenset[str] = frozenset(
    clave for clave, _ in SECCIONES_DISPONIBLES if clave != "anexos"
)

PRESET_EMPALME: frozenset[str] = frozenset({
    "portada", "resumen", "identificacion", "ficha", "formulas",
    "advertencias", "reproducibilidad",
})

GRAFICAS_EJECUTIVO: frozenset[str] = frozenset({"historico_proyeccion"})
GRAFICAS_TECNICO: frozenset[str] = frozenset(clave for clave, _ in GRAFICAS_DISPONIBLES)


@dataclass
class CamposInstitucionales:
    """Datos opcionales del §11. Ninguno es obligatorio."""

    entidad: str = ""
    dependencia: str = ""
    proyecto: str = ""
    contrato: str = ""
    objeto: str = ""
    contratista: str = ""
    supervisor: str = ""
    interventor: str = ""
    responsable: str = ""
    observaciones: str = ""
    logo: bytes | None = None
    incluir_firmas: bool = False

    def pares(self) -> list[tuple[str, str]]:
        etiquetas = (
            ("entidad", "Entidad"),
            ("dependencia", "Dependencia"),
            ("proyecto", "Proyecto"),
            ("contrato", "Contrato"),
            ("objeto", "Objeto"),
            ("contratista", "Contratista"),
            ("supervisor", "Supervisor"),
            ("interventor", "Interventor"),
            ("responsable", "Responsable del informe"),
        )
        return [(titulo, str(getattr(self, campo)).strip()) for campo, titulo in etiquetas if str(getattr(self, campo)).strip()]


@dataclass
class ConfiguracionInforme:
    """Qué contenido incluye el informe y con qué datos institucionales (§4)."""

    tipo: Literal["ejecutivo", "tecnico", "empalme", "personalizado"] = "ejecutivo"
    secciones: frozenset[str] = PRESET_EJECUTIVO
    graficas: frozenset[str] = GRAFICAS_EJECUTIVO
    institucional: CamposInstitucionales = field(default_factory=CamposInstitucionales)
    moneda: str = "COP"
    incluir_anexo_backtesting: bool = False
    csv_solicitado: bool = False

    @classmethod
    def desde_tipo(cls, tipo: str, **extra: Any) -> "ConfiguracionInforme":
        presets = {
            "ejecutivo": (PRESET_EJECUTIVO, GRAFICAS_EJECUTIVO),
            "tecnico": (PRESET_TECNICO, GRAFICAS_TECNICO),
            "empalme": (PRESET_EMPALME, frozenset()),
        }
        secciones, graficas = presets.get(tipo, (PRESET_EJECUTIVO, GRAFICAS_EJECUTIVO))
        return cls(tipo=tipo, secciones=secciones, graficas=graficas, **extra)

    def incluye(self, clave: str) -> bool:
        return clave in self.secciones

    def incluye_grafica(self, clave: str) -> bool:
        return clave in self.graficas

    def titulo_documento(self) -> str:
        return {
            "ejecutivo": "Informe ejecutivo de proyección de índices",
            "tecnico": "Informe técnico de proyección de índices",
            "empalme": "Informe de actualización de precios ICCP–ICOCIV",
        }.get(self.tipo, "Informe de análisis de variaciones de precios")


def texto_o(valor: Any, alternativa: str = "No registrado") -> str:
    texto = str(valor).strip() if valor is not None else ""
    return texto or alternativa


def unir(items: Iterable[str], separador: str = "; ") -> str:
    limpios = [str(i).strip() for i in items if str(i).strip()]
    return separador.join(limpios)
