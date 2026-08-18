"""Dependencias obligatorias de SAVIP y su verificación en el arranque.

Este módulo existe por un hallazgo concreto de la auditoría independiente de
julio de 2026 (H-01): `statsmodels` se importaba dentro de un `try/except` y su
presencia o ausencia cambiaba el modelo seleccionado y la cifra proyectada sin
que nada lo advirtiera. El mismo dato producía resultados distintos según lo que
hubiera instalado en la máquina.

La regla ahora es única: **no hay dependencias que alteren resultados de forma
opcional**. Si falta una, la aplicación se detiene con un mensaje explícito en
lugar de tomar otro camino en silencio.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Versión exacta de statsmodels con la que se validó esta distribución.
#: No es un rango: el resultado de un diagnóstico no debe depender de qué
#: versión resolvió el instalador.
VERSION_STATSMODELS_REQUERIDA = "0.14.6"


@dataclass(frozen=True)
class DependenciaObligatoria:
    modulo: str
    proposito: str
    version_requerida: str | None = None


DEPENDENCIAS_OBLIGATORIAS: tuple[DependenciaObligatoria, ...] = (
    DependenciaObligatoria("pandas", "Series y tablas del anexo"),
    DependenciaObligatoria("numpy", "Álgebra de los modelos"),
    DependenciaObligatoria("scipy", "Cuantiles t de Student del intervalo de predicción"),
    DependenciaObligatoria("sklearn", "Regresión robusta Huber"),
    DependenciaObligatoria("pyxlsb", "Lectura de anexos ICOCIV en formato XLSB"),
    DependenciaObligatoria("openpyxl", "Lectura y escritura de hojas de cálculo"),
    DependenciaObligatoria("docx", "Informe DOCX"),
    DependenciaObligatoria("reportlab", "Informe PDF paginado"),
    DependenciaObligatoria("matplotlib", "Gráficas"),
    DependenciaObligatoria(
        "statsmodels",
        "Diagnóstico Ljung-Box. No interviene en modelos, backtesting, "
        "métricas, selección, salvaguarda, intervalos ni ajuste de calendario.",
        VERSION_STATSMODELS_REQUERIDA,
    ),
)


class DependenciaFaltante(RuntimeError):
    """La distribución no reúne las condiciones para producir resultados fiables."""


def verificar_dependencias_obligatorias() -> list[str]:
    """Comprueba que todas las dependencias estén y con la versión exigida.

    Devuelve la lista de módulos verificados. Lanza :class:`DependenciaFaltante`
    con un mensaje accionable si alguna falta o no coincide en versión.
    """
    import importlib

    problemas: list[str] = []
    verificados: list[str] = []

    for dependencia in DEPENDENCIAS_OBLIGATORIAS:
        try:
            modulo = importlib.import_module(dependencia.modulo)
        except ImportError as error:
            problemas.append(
                f"  - {dependencia.modulo}: no está instalado. {dependencia.proposito}. ({error})"
            )
            continue

        instalada = str(getattr(modulo, "__version__", "")) or "desconocida"
        if dependencia.version_requerida and instalada != dependencia.version_requerida:
            problemas.append(
                f"  - {dependencia.modulo}: instalado {instalada}, se requiere "
                f"exactamente {dependencia.version_requerida}. {dependencia.proposito}."
            )
            continue
        verificados.append(f"{dependencia.modulo}=={instalada}")

    if problemas:
        raise DependenciaFaltante(
            "SAVIP no puede ejecutarse: faltan dependencias obligatorias o su "
            "versión no es la exigida.\n\n"
            + "\n".join(problemas)
            + "\n\nInstale el entorno declarado:\n"
            "  python -m pip install -r requirements-lock.txt\n\n"
            "No se continúa con una ruta alternativa: una dependencia ausente "
            "cambiaría los resultados sin dejar constancia."
        )
    return verificados
