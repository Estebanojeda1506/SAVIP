"""Controles Qt compartidos que evitan cambios accidentales con la rueda del mouse."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class ComboBoxSinRueda(QComboBox):
    """QComboBox que evita cambios accidentales de selección con la rueda del mouse."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - firma Qt
        event.ignore()


class SpinSinRueda(QDoubleSpinBox):
    """Evita cambios accidentales en campos numéricos con la rueda."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - firma Qt
        event.ignore()


class SpinEnteroSinRueda(QSpinBox):
    """Evita cambios accidentales en campos enteros con la rueda."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - firma Qt
        event.ignore()
