"""Movimiento y profundidad de la interfaz de SAVIP."""

from app_icociv.interfaz.animaciones.microinteracciones import (
    ElevacionHover,
    aplicar_elevacion,
    elevar_tarjetas,
    establecer_sombras,
    retirar_elevacion,
    sombras_habilitadas,
)
from app_icociv.interfaz.animaciones.transiciones import (
    animar_altura,
    animar_ancho,
    aplicar_preferencia_sistema,
    deslizar_a,
    desvanecer_entrada,
    desvanecer_salida,
    detectar_preferencia_sistema,
    detener_todas,
    entrada_escalonada,
    establecer_movimiento_reducido,
    movimiento_reducido,
    transicion_vista,
)

__all__ = [
    "ElevacionHover",
    "animar_altura",
    "animar_ancho",
    "aplicar_elevacion",
    "aplicar_preferencia_sistema",
    "deslizar_a",
    "desvanecer_entrada",
    "desvanecer_salida",
    "detener_todas",
    "elevar_tarjetas",
    "entrada_escalonada",
    "establecer_movimiento_reducido",
    "establecer_sombras",
    "movimiento_reducido",
    "retirar_elevacion",
    "sombras_habilitadas",
    "transicion_vista",
]
