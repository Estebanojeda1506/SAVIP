"""Registro de ejecución de la aplicación SAVIP.

Cuando la aplicación corre empaquetada no hay consola donde ver un error, de
modo que un fallo silencioso resulta indepurable. Este módulo escribe un
archivo de registro rotado por fecha y captura las excepciones no controladas.

No se registran datos sensibles: solo versión, entorno, etapa, tipo de error y
traza técnica. Las rutas de archivos que el usuario carga se registran por su
nombre, no por su contenido.
"""

from __future__ import annotations

import logging
import platform
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app_icociv.config.rutas import (
    VERSION,
    asegurar_carpeta,
    carpeta_logs,
    es_ejecutable_congelado,
)

_NOMBRE_LOGGER = "savip"
_configurado = False


def ruta_archivo_log() -> Path:
    """Ruta del archivo de registro vigente."""
    return carpeta_logs() / f"savip_{datetime.now():%Y%m%d}.log"


def configurar_registro(nivel: int = logging.INFO) -> logging.Logger:
    """Configura el registro en archivo y captura excepciones no controladas.

    Es idempotente: llamarla varias veces no duplica manejadores.
    """
    global _configurado
    logger = logging.getLogger(_NOMBRE_LOGGER)
    if _configurado:
        return logger

    logger.setLevel(nivel)
    logger.propagate = False

    asegurar_carpeta(carpeta_logs())
    try:
        manejador: logging.Handler = RotatingFileHandler(
            ruta_archivo_log(), maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
    except OSError:
        # Si la carpeta de logs no es escribible, la aplicación debe seguir
        # funcionando; se degrada a la salida estándar.
        manejador = logging.StreamHandler(sys.stderr)

    manejador.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    logger.addHandler(manejador)

    if not es_ejecutable_congelado():
        logger.addHandler(logging.StreamHandler(sys.stderr))

    _configurado = True
    _registrar_contexto(logger)
    _instalar_captura_excepciones(logger)
    return logger


def obtener_logger(nombre: str | None = None) -> logging.Logger:
    """Devuelve el logger de la aplicación, configurándolo si hace falta."""
    if not _configurado:
        configurar_registro()
    return logging.getLogger(_NOMBRE_LOGGER if nombre is None else f"{_NOMBRE_LOGGER}.{nombre}")


def _registrar_contexto(logger: logging.Logger) -> None:
    """Deja constancia del entorno al inicio de cada ejecución."""
    logger.info("=" * 60)
    logger.info("Inicio de SAVIP versión %s", VERSION)
    logger.info("Empaquetado: %s", "si" if es_ejecutable_congelado() else "no (código fuente)")
    logger.info("Sistema: %s %s", platform.system(), platform.release())
    logger.info("Python: %s", platform.python_version())
    logger.info("Registro en: %s", ruta_archivo_log())


def _instalar_captura_excepciones(logger: logging.Logger) -> None:
    """Registra cualquier excepción no controlada antes de que cierre la aplicación."""
    anterior = sys.excepthook

    def _manejar(tipo: type[BaseException], valor: BaseException, traza: Any) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            anterior(tipo, valor, traza)
            return
        logger.critical("Excepcion no controlada", exc_info=(tipo, valor, traza))
        anterior(tipo, valor, traza)

    sys.excepthook = _manejar
