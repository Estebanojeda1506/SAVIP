"""Compatibilidad con la API visual anterior, delegando en `interfaz.tema`.

El sistema de tema vive ahora en `app_icociv/interfaz/tema/`. Este módulo se
conserva porque varios widgets y la ventana principal importan de aquí; expone
las mismas funciones y constantes, resueltas contra los tokens nuevos.

`paleta_tema` devuelve la paleta nueva más los alias de los nombres antiguos, de
modo que el código existente (`colores["fondo_secundario"]`, `colores["bordes"]`)
sigue funcionando mientras el código nuevo usa los nombres del sistema de tema.
"""

from __future__ import annotations

from app_icociv.interfaz.tema import estilos as _estilos
from app_icociv.interfaz.tema.colores import TEMAS_DISPONIBLES, normalizar_tema
from app_icociv.interfaz.tema.colores import paleta as _paleta_base
from app_icociv.interfaz.tema.tokens import (
    ALTURA_CONTROL,
    ANCHO_BOTON_INCREMENTO,
    ESPACIO_3 as ESPACIADO_PANEL,
    ESPACIO_4 as MARGEN_PANEL,
    ESPACIO_4 as ESPACIADO_GRUPOS,
    ALTURA_CONTROL_COMPACTO as ALTURA_CHECKBOX,
    GRAFICA_MIN_HEIGHT,
    GRAFICA_MIN_WIDTH,
    PANEL_MAX_WIDTH,
    PANEL_MIN_WIDTH,
    PANEL_SCROLL_MAX_WIDTH,
    PANEL_SCROLL_MIN_WIDTH,
    VENTANA_MIN_HEIGHT,
    VENTANA_MIN_WIDTH,
)

__all__ = [
    "ALTURA_CHECKBOX",
    "ALTURA_CONTROL",
    "ANCHO_BOTON_INCREMENTO",
    "ESPACIADO_GRUPOS",
    "ESPACIADO_PANEL",
    "GRAFICA_MIN_HEIGHT",
    "GRAFICA_MIN_WIDTH",
    "MARGEN_PANEL",
    "PANEL_MAX_WIDTH",
    "PANEL_MIN_WIDTH",
    "PANEL_SCROLL_MAX_WIDTH",
    "PANEL_SCROLL_MIN_WIDTH",
    "TEMAS",
    "TEMAS_DISPONIBLES",
    "TOOLTIPS_TECNICOS",
    "VENTANA_MIN_HEIGHT",
    "VENTANA_MIN_WIDTH",
    "aplicar_paleta_qss",
    "hoja_estilos",
    "normalizar_tema",
    "paleta_tema",
]

# Nombre antiguo -> nombre en el sistema de tema.
_ALIAS_HISTORICOS = {
    "fondo_principal": "fondo",
    "fondo_secundario": "superficie",
    "fondo_tabla": "superficie",
    "encabezado_tabla": "superficie_3",
    "texto_principal": "texto",
    "bordes": "borde",
    "acento": "principal",
    "acento_oscuro": "principal_intenso",
    "superficie_suave": "superficie_2",
    "texto_encabezado": "texto",
    "grafica": "grafica_fondo",
    "rejilla": "grafica_rejilla",
}


def paleta_tema(tema: str | None) -> dict[str, str]:
    """Paleta del tema con los nombres nuevos y los alias históricos."""
    colores = _paleta_base(tema)
    for antiguo, nuevo in _ALIAS_HISTORICOS.items():
        colores.setdefault(antiguo, colores[nuevo])
    return colores


def hoja_estilos(tema: str | None = "claro") -> str:
    """Hoja QSS completa del tema indicado."""
    return _estilos.hoja_estilos(tema)


def aplicar_paleta_qss(qss: str, tema: str | None) -> str:
    """Compatibilidad: antes reemplazaba hex; ahora compone desde la plantilla.

    Se ignora `qss` a propósito. La sustitución de cadenas hexadecimales era el
    origen de los colores que no seguían al tema oscuro, y por eso desapareció.
    """
    _ = qss
    return hoja_estilos(tema)


TEMAS = {nombre: paleta_tema(nombre) for nombre in TEMAS_DISPONIBLES}


TOOLTIPS_TECNICOS = {
    "archivo": "Selecciona un archivo Excel del DANE en formato .xlsx o .xlsb. No se usan rutas fijas.",
    "grupo_obra": "Primer nivel de agregación de la tabla ICOCIV seleccionada.",
    "tabla_activa": "Tabla técnica ICOCIV que alimenta la serie histórica y la proyección actual.",
    "costos_globales": "Permite navegar desde el grupo de obra hacia grupos de costos e insumos asociados.",
    "costos_subclase": "Permite analizar grupos de costos e insumos asociados a la subclase CPC seleccionada.",
    "costos_tipologia": "Permite analizar grupos de costos e insumos asociados a la tipologia de obra seleccionada.",
    "costos_capitulo": "Permite analizar grupos de costos e insumos asociados al capítulo constructivo seleccionado.",
    "anio": "Año calendario del periodo que se desea proyectar.",
    "mes": "Mes calendario del periodo que se desea proyectar.",
    "horizonte": (
        "Horizonte solicitado en meses. La aplicación valida por backtesting e intervalos "
        "si el horizonte es recomendable, debe restringirse o se permite como escenario."
    ),
    "ejecutar": "Ejecuta la selección de tabla, construye la serie histórica y calcula la proyección.",
    "sesion": "Guarda o recupera una sesión JSON con selección, parámetros, serie y resultados.",
    "reporte": "Genera un informe técnico DOCX con trazabilidad, métricas, backtesting y gráficas.",
    "serie": "Serie histórica exacta usada por el modelo de regresion.",
    "fila": "Registro fuente de la tabla ICOCIV que origina la serie histórica.",
    # P0-C / C2: la gráfica ya no dibuja banda, de modo que anunciarla aquí
    # describiría algo que el usuario no va a encontrar.
    "grafica": "Visualización del ajuste histórico y de la proyección.",
    "tema": "Alterna entre tema claro y oscuro. La preferencia se conserva en la sesión.",
    "navegacion": "Contrae o expande el panel de navegacion lateral.",
    # P0-C / C2: la cobertura describe una banda que esta versión no publica.
    # Sigue calculándose como diagnóstico interno y no aparece en las salidas.
    "cobertura": (
        "Esta versión no publica intervalo de predicción: su método no está sustentado, de modo "
        "que ni sus límites ni su cobertura forman parte de la salida."
    ),
}
