"""Trabajadores Qt para ejecutar tareas pesadas fuera del hilo de UI."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class TrabajadorFuncion(QThread):
    """Ejecuta una función en segundo plano y emite resultado o error."""

    resultado = Signal(object)
    error = Signal(str)

    def __init__(self, funcion: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.funcion = funcion
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            self.resultado.emit(self.funcion(*self.args, **self.kwargs))
        except Exception as exc:
            self.error.emit(str(exc))
