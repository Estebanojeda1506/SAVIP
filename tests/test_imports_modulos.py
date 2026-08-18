"""Pruebas mínimas de importación de la arquitectura app_icociv."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MODULOS_PRINCIPALES = [
    "app_icociv.config.rutas",
    "app_icociv.datos.cargador_datos",
    "app_icociv.estadistica.analisis_series",
    "app_icociv.estadistica.metricas",
    "app_icociv.estadistica.diagnostico_residuos",
    "app_icociv.estadistica.criterios",
    "app_icociv.validacion.backtesting",
    "app_icociv.proyeccion.servicio_proyeccion",
    "app_icociv.reportes.generador_reportes",
    "app_icociv.persistencia.gestor_sesiones",
    "app_icociv.exportables.csv_reproducible",
    "app_icociv.servicios.empalme_iccp_icociv",
    "app_icociv.servicios.actualizacion_icociv",
    "app_icociv.interfaz.widgets.proyecciones_icociv",
    "app_icociv.interfaz.widgets.visor_grafica",
    "app_icociv.interfaz.ventana_principal",
    "app_icociv.interfaz.controladores.controlador_principal",
    "app_icociv.interfaz.widgets.empalme_iccp_icociv",
]


def test_importar_modulos_principales() -> None:
    """Verifica que los módulos principales importen sin rutas antiguas rotas."""
    for nombre_modulo in MODULOS_PRINCIPALES:
        importlib.import_module(nombre_modulo)


if __name__ == "__main__":
    test_importar_modulos_principales()
    print("OK: módulos principales importados correctamente.")
