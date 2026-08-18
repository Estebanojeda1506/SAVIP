# Mapa de reorganización de módulos ICOCIV

Este documento registra la reorganización de código fuente de la app ICOCIV hacia una carpeta principal única: `app_icociv/`.

No se movieron datos brutos, documentos externos, reportes generados, sesiones ni material académico ajeno al código fuente. La carpeta `pruebas app/` se mantiene como legado histórico y no forma parte de la app PySide6 activa.

| Archivo original | Nueva ubicación | Motivo del cambio | Imports actualizados |
|---|---|---|---|
| `aplicacion.py` | `aplicacion.py` | Se conserva como punto de entrada liviano. | Sí |
| `interfaz/ventana_principal.py` | `app_icociv/interfaz/ventana_principal.py` | Agrupar la interfaz PySide6 dentro del paquete principal. | Sí |
| `interfaz/controladores/controlador_principal.py` | `app_icociv/interfaz/controladores/controlador_principal.py` | Mantener controladores separados de widgets y backend. | Sí |
| `interfaz/controladores/trabajadores.py` | `app_icociv/interfaz/controladores/trabajadores.py` | Mantener hilos/trabajadores Qt dentro de la capa visual. | Sí |
| `interfaz/widgets/modelo_tabla.py` | `app_icociv/interfaz/widgets/modelo_tabla.py` | Agrupar widgets auxiliares de Qt. | Sí |
| `interfaz/estilos/constantes_visuales.py` | `app_icociv/interfaz/estilos/constantes_visuales.py` | Centralizar constantes visuales de la UI. | Sí |
| `interfaz/estilos/estilo.qss` | `app_icociv/interfaz/estilos/estilo.qss` | Mantener QSS junto a la interfaz. | No aplica |
| `migracion/funciones/cargador_datos.py` | `app_icociv/datos/cargador_datos.py` | Separar carga y lectura de anexos ICOCIV. | Sí |
| `migracion/funciones/regresion.py` | `app_icociv/modelos/regresion.py` | Ubicar regresiones e IC bootstrap dentro de modelos. | Sí |
| `migracion/funciones/servicio_proyeccion.py` | `app_icociv/proyeccion/servicio_proyeccion.py` | Agrupar construcción de series, factibilidad, horizontes y proyección. | Sí |
| `migracion/estadistica/analisis_series.py` | `app_icociv/estadistica/analisis_series.py` | Mantener validación descriptiva y variables derivadas en estadística. | Sí |
| `migracion/estadistica/criterios.py` | `app_icociv/estadistica/criterios.py` | Centralizar criterios estadísticos y auditoría metodológica. | Sí |
| `migracion/estadistica/diagnostico_residuos.py` | `app_icociv/estadistica/diagnostico_residuos.py` | Mantener diagnóstico residual separado de proyección e interfaz. | Sí |
| `migracion/estadistica/metricas.py` | `app_icociv/estadistica/metricas.py` | Mantener MAE, RMSE, MAPE, sMAPE, MASE y criterios auxiliares. | Sí |
| `migracion/estadistica/modelos_interpretables.py` | `app_icociv/estadistica/modelos_interpretables.py` | Conservar catálogo de modelos interpretables usados por el análisis. | Sí |
| `migracion/estadistica/validacion_series.py` | `app_icociv/estadistica/validacion_series.py` | Separar validación temporal exploratoria de validación predictiva. | Sí |
| `migracion/estadistica/backtesting.py` | `app_icociv/validacion/backtesting.py` | Separar walk-forward y comparación predictiva en la capa de validación. | Sí |
| `migracion/reportes/generador_reportes.py` | `app_icociv/reportes/generador_reportes.py` | Agrupar generación PDF, DOCX, HTML, gráficos y tablas de informe. | Sí |
| `migracion/persistencia/gestor_sesiones.py` | `app_icociv/persistencia/gestor_sesiones.py` | Separar persistencia JSON local. | Sí |
| `migracion/utilidades/utilidades.py` | `app_icociv/utilidades/utilidades.py` | Centralizar funciones comunes de periodos, filtros y estadística auxiliar. | Sí |
| `migracion/utilidades/nomenclatura_icociv.py` | `app_icociv/utilidades/nomenclatura_icociv.py` | Mantener nomenclatura técnica ICOCIV reutilizable. | Sí |
| Nuevo | `app_icociv/config/rutas.py` | Centralizar raíz del proyecto, sesiones y reportes. | Sí |
| Nuevo | `app_icociv/config/settings.py` | Registrar nombre y versión de la app. | No aplica |
| Nuevo | `app_icociv/config/constantes.py` | Registrar constantes generales de extensiones y horizontes UI. | No aplica |
| Nuevo | `app_icociv/servicios/orquestador.py` | Coordinar flujo general sin duplicar lógica interna. | No aplica |
| Nuevo | `app_icociv/exportables/csv_reproducible.py` | Dar ubicación funcional a exportaciones CSV reproducibles. | No aplica |
| Nuevo | `tests/test_imports_modulos.py` | Verificar importación de módulos principales bajo la nueva arquitectura. | No aplica |

## Imports corregidos

Se reemplazaron imports antiguos como:

```python
from migracion.funciones.servicio_proyeccion import ejecutar_proyeccion
from interfaz.ventana_principal import ejecutar_aplicacion
```

por imports bajo el paquete principal:

```python
from app_icociv.proyeccion.servicio_proyeccion import ejecutar_proyeccion
from app_icociv.interfaz.ventana_principal import ejecutar_aplicacion
```

También se ajustaron rutas especiales:

| Import antiguo | Import nuevo |
|---|---|
| `migracion.funciones.cargador_datos` | `app_icociv.datos.cargador_datos` |
| `migracion.funciones.regresion` | `app_icociv.modelos.regresion` |
| `migracion.funciones.servicio_proyeccion` | `app_icociv.proyeccion.servicio_proyeccion` |
| `migracion.estadistica.backtesting` | `app_icociv.validacion.backtesting` |
| `migracion.reportes.generador_reportes` | `app_icociv.reportes.generador_reportes` |
| `migracion.persistencia.gestor_sesiones` | `app_icociv.persistencia.gestor_sesiones` |
| `interfaz.*` | `app_icociv.interfaz.*` |

## Rutas revisadas

La interfaz ahora obtiene las carpetas de sesiones y reportes desde:

```python
from app_icociv.config.rutas import CARPETA_REPORTES, CARPETA_SESIONES, RAIZ_PROYECTO
```

Esto evita que `ventana_principal.py` dependa de la profundidad física de su archivo dentro del paquete.
