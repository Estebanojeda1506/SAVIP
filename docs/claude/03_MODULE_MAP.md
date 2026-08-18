# Mapa de módulos

Este mapa complementa `docs/mapa_reorganizacion_modulos.md`. Las entradas y salidas descritas son las observadas en el código actual.

## Carga de datos ICOCIV

- **Propósito:** leer Excel/XLSB y extraer bloques A16.x con periodos normalizados.
- **Archivos:** `app_icociv/datos/cargador_datos.py`.
- **Entradas:** bytes, nombre de archivo y etiquetas de tabla.
- **Procesamiento:** detección de título, encabezados, inicio/fin, años y meses.
- **Salidas:** diccionario de `DataFrame` y lista de periodos.
- **Validaciones:** formato soportado, presencia de tabla y estructura temporal.
- **Dependencias:** pandas, pyxlsb/openpyxl; configuración de tablas.
- **Riesgo:** cambios de estructura en anexos futuros.

## Selector jerárquico ICOCIV

- **Propósito:** recorrer grupo, división, grupo CPC, clase y subclase/insumo sin perder la fila fuente.
- **Archivos:** `interfaz/controladores/controlador_principal.py`, `proyeccion/servicio_proyeccion.py`, `utilidades/nomenclatura_icociv.py`, `interfaz/ventana_principal.py`.
- **Entradas:** tablas cargadas y valores seleccionados.
- **Procesamiento:** filtrado dependiente y `resolver_fila_seleccionada`.
- **Salidas:** selección estructurada, ruta visible, fila y serie.
- **Validaciones:** habilitación progresiva y selección existente.
- **Dependencias:** cargador y utilidades de nomenclatura.
- **Riesgo:** nombres y niveles varían entre tablas A16.x.

## Serie histórica, descriptivos y validación

- **Propósito:** normalizar periodos y evaluar calidad antes de modelar.
- **Archivos:** `estadistica/analisis_series.py`, `estadistica/validacion_series.py`.
- **Entradas:** serie de periodo/índice.
- **Procesamiento:** orden temporal, numéricos, faltantes, duplicados, continuidad, positivos, descriptivos, variaciones y MAD.
- **Salidas:** serie normalizada, diagnósticos, variables derivadas y alertas.
- **Validaciones:** mínimo de 8 observaciones para modelación; advertencias antes de 18 y recomendación de 24.
- **Dependencias:** pandas y NumPy.
- **Riesgo:** no imputar ni corregir automáticamente sin decisión metodológica.

## Proyección estadística

- **Propósito:** elegir candidatos por evidencia y producir la proyección solicitada.
- **Archivos:** `proyeccion/servicio_proyeccion.py`, `estadistica/modelos_interpretables.py`.
- **Entradas:** serie, año, mes, horizonte y parámetros de bootstrap.
- **Procesamiento:** activación por nivel, ajuste, selección, intervalos y reconciliación del horizonte.
- **Salidas:** modelo, proyecciones, intervalo de predicción del 95 %, diagnóstico, advertencias y trazabilidad. La banda del 80 % se calcula como diagnóstico interno y no se publica en ninguna salida.
- **Validaciones:** horizonte entero positivo hasta el máximo operativo de 60 y evidencia suficiente.
- **Dependencias:** NumPy, pandas, scikit-learn, matplotlib; `statsmodels` solo para funciones opcionales.
- **Riesgo:** la dependencia opcional no está declarada.

## Backtesting y métricas

- **Propósito:** comparar predicciones fuera de muestra por origen y horizonte.
- **Archivos:** `validacion/backtesting.py`, `estadistica/metricas.py`, `estadistica/diagnostico_residuos.py`.
- **Entradas:** serie, candidatos, horizontes y tamaño inicial.
- **Procesamiento:** ventana expansiva, reestimación por corte, predicción y comparación con benchmarks.
- **Salidas:** MAE, RMSE, MAPE, sMAPE, MASE, sesgo, ranking y residuos.
- **Validaciones:** primer origen `N₀ = max_m N_min(m)` (hoy 6, provisional; P0-E abierto), acotado por disponibilidad a `n − 1`. La fórmula anterior `max(18; 0,60n)` fue retirada el 12 de agosto de 2026 por carecer de fuente.
- **Dependencias:** modelos interpretables y criterios.
- **Riesgo:** horizontes largos reducen los errores fuera de muestra disponibles.

## Criterios y horizonte viable

- **Propósito:** separar lo recomendable, lo admisible como escenario y lo no viable.
- **Archivos:** `estadistica/criterios.py`, `estadistica/analisis_series.py`, `proyeccion/servicio_proyeccion.py`.
- **Entradas:** calidad, métricas, intervalos, residuos y tabla de horizontes.
- **Procesamiento:** umbrales centralizados y reconciliación consecutiva.
- **Salidas:** máximo recomendado, máximo de escenario, estado y razones.
- **Validaciones:** no extrapolar más allá de la evidencia evaluable.
- **Dependencias:** backtesting y diagnóstico.
- **Riesgo:** todo cambio de umbral debe sincronizar código, reportes y LaTeX.

## Reportes PDF, DOCX, HTML y CSV

- **Propósito:** presentar y conservar resultados reproducibles.
- **Archivos:** `reportes/generador_reportes.py`, `exportables/csv_reproducible.py`.
- **Entradas:** resultado estructurado, serie, ruta y metadatos.
- **Procesamiento:** tablas, gráficas, resumen, metodología y parámetros.
- **Salidas:** bytes/archivos PDF, DOCX, HTML y CSV.
- **Validaciones:** disponibilidad de `python-docx`, límites de tablas y datos presentes.
- **Dependencias:** matplotlib, python-docx y resultados de proyección.
- **Riesgo:** evitar cálculos nuevos dentro de presentación.

## Empalme ICCP–ICOCIV

- **Propósito:** actualizar una base contractual a través de la transición de diciembre de 2021.
- **Archivos:** `servicios/empalme_iccp_icociv.py`, `datos/iccp_historico.json`, `interfaz/widgets/empalme_iccp_icociv.py`.
- **Entradas:** P, A, fechas, tipo/serie ICCP, ruta/serie ICOCIV, unidad y observación.
- **Procesamiento:** selección del caso (solo ICCP, solo ICOCIV o empalme), índices, R1, R2, R y valor actualizado.
- **Salidas:** resultado trazable y filas acumulativas.
- **Validaciones:** fechas, base positiva, serie perteneciente al tipo, unidad y ruta cuando corresponda.
- **Dependencias:** histórico ICCP y serie ICOCIV seleccionada.
- **Riesgo:** la equivalencia es manual y debe justificarse.

## Cálculo especial de acero

- **Propósito:** aplicar la base P0 y calcular Z cuando se suministran Ix y q.
- **Archivos:** `servicios/empalme_iccp_icociv.py`, widget de empalme.
- **Entradas:** P0, Ix, q y los mismos índices/fechas del empalme.
- **Procesamiento:** R1, R2, R y `Z = (Ix × q) - (R + P0)`.
- **Salidas:** resultado especial; Z queda pendiente si faltan Ix o q.
- **Validaciones:** P0 positivo; Ix y q no negativos y ambos presentes para Z.
- **Dependencias:** cálculo base compartido.
- **Riesgo:** no confundir P0 con P−A.

## Exportación Excel del empalme

- **Propósito:** exportar cálculos y fórmulas verificables.
- **Archivo:** `interfaz/widgets/empalme_iccp_icociv.py`.
- **Entradas:** lista acumulada de cálculos.
- **Procesamiento:** `openpyxl`, fórmulas por fila y formatos.
- **Salidas:** libro de una sola hoja `Empalme ICCP-ICOCIV` con secciones consecutivas (información general, trazabilidad, equivalencias, cálculo con fórmulas, metodología y detalle acero cuando aplica), conforme a RF-10 desde el 19 de julio de 2026.
- **Validaciones:** existencia de cálculos y campos requeridos; prueba de hoja única, fórmulas y referencias internas.
- **Dependencias:** openpyxl.

## Interfaz y persistencia

- **Propósito:** operar la aplicación, mostrar pestañas y guardar/restaurar sesiones.
- **Archivos:** `interfaz/ventana_principal.py`, `interfaz/presentacion_resultados.py`, `interfaz/controladores/trabajadores.py`, `persistencia/gestor_sesiones.py`, `interfaz/estilos/`.
- **Entradas:** acciones del usuario, archivo y parámetros.
- **Procesamiento:** señales Qt, trabajo asíncrono, estado compartido y serialización JSON.
- **Salidas:** panel, tablas, gráfica, mensajes y archivos de sesión.
- **Validaciones:** controles progresivos, mensajes de error y estado habilitado.
- **Dependencias:** PySide6 y todos los servicios.
- **Riesgo:** probar con `QT_QPA_PLATFORM=offscreen` en entornos sin pantalla.

## Documento LaTeX

- **Propósito:** documentar contexto, metodología, software, pruebas, manual y conclusiones del trabajo de grado.
- **Archivos:** `documentacion_latex/documento_tecnico_icociv_iccp/main.tex`, `referencias.bib`, `figuras/`, `tablas/`, `anexos/`.
- **Entradas:** código, resultados verificados y fuentes institucionales/bibliográficas.
- **Procesamiento:** pdfLaTeX, BibTeX y apacite.
- **Salidas:** `main.pdf`.
- **Validaciones:** compilación sin error fatal y coherencia con el código.
- **Dependencias:** distribución LaTeX y paquetes declarados en el preámbulo.
- **Riesgo:** duplicados históricos no deben confundirse con el documento final.
