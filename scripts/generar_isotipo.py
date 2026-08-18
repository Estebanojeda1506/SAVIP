"""Genera el isotipo de SAVIP a partir de la paleta del sistema visual.

El isotipo es una curva de índice ascendente con un nodo de dato en su extremo y
la banda de intervalo bajo el trazo: los tres elementos con los que la propia
aplicación representa una proyección. Se dibuja por código para que herede
siempre los colores de la paleta y para poder regenerarlo en cualquier tamaño
sin pérdida.

Uso:
    python scripts/generar_isotipo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from app_icociv.interfaz.tema.colores import RAMPA

DESTINO = RAIZ / "app_icociv" / "interfaz" / "recursos"

# Curva del índice en coordenadas normalizadas (0..1), con el origen arriba a la
# izquierda. Sube con una inflexión, como una serie real, no como una diagonal.
CURVA = [
    (0.17, 0.74),
    (0.31, 0.63),
    (0.43, 0.68),
    (0.57, 0.49),
    (0.68, 0.54),
    (0.79, 0.34),
]


def _dibujar(lado: int, con_fondo: bool = True) -> QPixmap:
    pixmap = QPixmap(lado, lado)
    pixmap.fill(Qt.GlobalColor.transparent)

    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if con_fondo:
        # Cuadrado redondeado con el degradado profundo de la rampa.
        fondo = QLinearGradient(0, 0, lado, lado)
        fondo.setColorAt(0.0, QColor(RAMPA["t20"]))
        fondo.setColorAt(1.0, QColor(RAMPA["t05"]))
        radio = lado * 0.235
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(fondo))
        pintor.drawRoundedRect(QRectF(0, 0, lado, lado), radio, radio)

    puntos = [QPointF(x * lado, y * lado) for x, y in CURVA]

    # Banda de intervalo: se abre hacia el futuro, como la incertidumbre real.
    banda = QPainterPath()
    apertura = lado * 0.075
    banda.moveTo(puntos[0].x(), puntos[0].y() - apertura * 0.25)
    for indice, punto in enumerate(puntos[1:], start=1):
        factor = indice / (len(puntos) - 1)
        banda.lineTo(punto.x(), punto.y() - apertura * (0.25 + factor))
    for indice in range(len(puntos) - 1, -1, -1):
        factor = indice / (len(puntos) - 1)
        punto = puntos[indice]
        banda.lineTo(punto.x(), punto.y() + apertura * (0.25 + factor))
    banda.closeSubpath()
    color_banda = QColor(RAMPA["t70"])
    color_banda.setAlpha(95)
    pintor.setBrush(QBrush(color_banda))
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.drawPath(banda)

    # Trazo del índice.
    trazo = QPainterPath()
    trazo.moveTo(puntos[0])
    for punto in puntos[1:]:
        trazo.lineTo(punto)
    lapiz = QPen(QColor(RAMPA["t85"]), lado * 0.075)
    lapiz.setCapStyle(Qt.PenCapStyle.RoundCap)
    lapiz.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(lapiz)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(trazo)

    # Nodo de dato en el extremo: el punto proyectado.
    nodo = puntos[-1]
    radio_nodo = lado * 0.092
    halo = QColor(RAMPA["t95"])
    halo.setAlpha(60)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QBrush(halo))
    pintor.drawEllipse(nodo, radio_nodo * 1.55, radio_nodo * 1.55)
    pintor.setBrush(QBrush(QColor(RAMPA["t95"])))
    pintor.drawEllipse(nodo, radio_nodo, radio_nodo)

    pintor.end()
    return pixmap


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app
    DESTINO.mkdir(parents=True, exist_ok=True)
    generados = []
    for nombre, lado, fondo in (
        ("savip_logo.png", 512, True),
        ("savip_icono.png", 256, True),
        ("savip_isotipo_plano.png", 512, False),
    ):
        ruta = DESTINO / nombre
        _dibujar(lado, con_fondo=fondo).save(str(ruta))
        generados.append((nombre, lado, ruta.stat().st_size))
    for nombre, lado, tamano in generados:
        print(f"{nombre}: {lado}x{lado}, {tamano} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
