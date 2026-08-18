"""Punto de entrada de la aplicacion de escritorio SAVIP.

Modos de uso:

    aplicacion.py                    abre la interfaz grafica
    aplicacion.py --autocomprobacion ejecuta comprobaciones sin interfaz y
                                     devuelve 0 si todas pasan

El modo de autocomprobacion permite validar una distribucion empaquetada sin
abrir ventanas; lo usa el script de compilacion como verificacion posterior.
"""

import sys

from app_icociv.config.registro import configurar_registro, obtener_logger


def main(argumentos: list[str] | None = None) -> int:
    """Configura el registro y arranca el modo solicitado.

    El registro se activa antes de importar la interfaz para que cualquier
    fallo de arranque (por ejemplo, un recurso ausente en una distribucion
    empaquetada) quede escrito en el archivo de log.
    """
    argv = sys.argv[1:] if argumentos is None else argumentos
    configurar_registro()
    logger = obtener_logger("arranque")

    # Las dependencias se verifican antes de cualquier calculo. Una biblioteca
    # ausente no debe llevar a una ruta alternativa que cambie resultados en
    # silencio: eso fue el hallazgo H-01 de la auditoria independiente.
    from app_icociv.config.dependencias import (
        DependenciaFaltante,
        verificar_dependencias_obligatorias,
    )

    try:
        verificadas = verificar_dependencias_obligatorias()
        logger.info("Dependencias obligatorias verificadas: %s", ", ".join(verificadas))
    except DependenciaFaltante as error:
        logger.error("Dependencias obligatorias incompletas: %s", error)
        print(str(error), file=sys.stderr)
        return 3

    if "--autocomprobacion" in argv:
        from app_icociv.config.autocomprobacion import ejecutar_autocomprobacion

        logger.info("Ejecutando autocomprobacion")
        codigo = ejecutar_autocomprobacion()
        logger.info("Autocomprobacion finalizada con codigo %s", codigo)
        return codigo

    try:
        from app_icociv.interfaz.ventana_principal import ejecutar_aplicacion

        return ejecutar_aplicacion()
    except Exception:
        logger.exception("Fallo al iniciar la aplicacion")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
