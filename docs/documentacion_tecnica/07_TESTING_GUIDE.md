# Guía de pruebas

## Ejecución automática disponible

Los archivos de prueba con bloque `__main__` pueden ejecutarse sin `pytest`:

```bash
python tests/test_imports_modulos.py
python tests/test_empalme_iccp_icociv.py
python tests/test_resultado_horizonte_solicitado.py
python pruebas/prueba_analisis_integral.py
python pruebas/prueba_bloqueo_estadistico.py
python pruebas/prueba_auditoria_estadistica_app_docs.py
```

En un entorno sin pantalla, definir antes `QT_QPA_PLATFORM=offscreen`. `pytest` no está instalado ni declarado en el estado auditado; por eso la colección completa queda pendiente.

Desde el 28 de julio de 2026 **todas** las suites de `tests/` y `pruebas/` traen
bloque `__main__` y bootstrap de `sys.path`, y hay un ejecutor único que las corre
todas y devuelve código distinto de cero si alguna falla:

```bash
python docs/remediacion_auditoria/ejecutar_suites.py
```

Son 28 suites y tardan unos 14 minutos. Las tres más lentas son
`test_consistencia_trayectoria.py` (≈198 s),
`prueba_horizonte_dinamico_ui_reportes.py` (≈225 s) y
`test_informes_rediseno.py` (≈56 s).

## Registro de verificaciones del 19 de julio de 2026

| ID | Módulo | Objetivo | Insumos | Procedimiento | Criterio de aceptación | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|---|---|---|---|
| T-IMP-01 | Arquitectura | Importar módulos principales | Código actual | `python tests/test_imports_modulos.py` | Sin excepciones | Mensaje OK | `OK: módulos principales importados correctamente` | Aprobada |
| T-EMP-01 | Empalme general | Verificar R1, R2, R y casos temporales | Series sintéticas del archivo de prueba | `python tests/test_empalme_iccp_icociv.py` | Aserciones completas | R=R1+R2 y valores esperados | Mensaje `OK`; todas las aserciones pasaron | Aprobada |
| T-EMP-02 | Selector ICCP | Separar total, canasta y grupo; rechazar mezcla | Diccionario ICCP sintético | Incluida en T-EMP-01 | Listas separadas y errores explícitos | Sin mezcla | Aserciones pasaron | Aprobada |
| T-ACR-01 | Acero | Calcular R y Z; dejar Z pendiente sin Ix/q | Series y P0 sintéticos | Incluida en T-EMP-01 | Fórmulas y estado opcional correctos | Valores esperados | Aserciones pasaron | Aprobada |
| T-XLS-01 | Excel empalme | Verificar libro, dos cálculos y fórmulas | Dos cálculos sintéticos | Incluida en T-EMP-01 | Cinco hojas y fórmulas por ambas filas | Libro consistente | Aserciones pasaron | Aprobada |
| T-HOR-01 | Horizonte | Evitar usar 20 como constante y respetar evidencia | Evaluaciones sintéticas | `python tests/test_resultado_horizonte_solicitado.py` | Todos los escenarios pasan | Mensaje OK | `Pruebas de resultado del horizonte solicitado OK` | Aprobada |
| T-INT-01 | Flujo ICOCIV | Ejecutar análisis integral y generar reportes | Serie de prueba incluida | `python pruebas/prueba_analisis_integral.py` | Proyección y archivos sin excepción | Resumen final | Modelo sobre variación mensual; h solicitado/permitido 12; PDF/DOCX generados | Aprobada |
| T-BLO-01 | Factibilidad | Verificar bloqueo gradual | Casos del script | `python pruebas/prueba_bloqueo_estadistico.py` | Aserciones completas | Mensaje de finalización | `Pruebas de factibilidad gradual completadas` | Aprobada |
| T-AUD-01 | App/LaTeX/bibliografía | Auditar trazabilidad metodológica | Código y bibliografía final | `python pruebas/prueba_auditoria_estadistica_app_docs.py` | Todas las claves esperadas existen | Sin aserciones | Falló: no se satisfacen simultáneamente `duan1983`, `iglewicz_hoaglin1993`, `granger_newbold1974` | Fallida |
| T-PRE-01 | Presentación/referencias | Ejecutar colección de presentación | Código y fuentes | Ejecución directa intentada | Importación y aserciones | Sin errores | El lanzador directo no añadió la raíz y produjo `ModuleNotFoundError`; requiere pytest/PYTHONPATH y colección real | Pendiente |
| T-LTX-01 | LaTeX | Compilar documento final | `main.tex`, `.bib`, figuras | `pdflatex -interaction=nonstopmode -halt-on-error main.tex` | Exit 0 y PDF | PDF actualizado | Exit 0; 112 páginas, 945149 bytes; avisos no fatales | Aprobada |

## Pruebas manuales recomendadas

### Carga y selector ICOCIV

- **ID:** M-SEL-01.
- **Objetivo:** comprobar cascada jerárquica y fila fuente con un anexo oficial.
- **Insumo:** `anex-ICOCIV-ene2026.xlsb`.
- **Procedimiento:** cargar, recorrer al menos dos rutas de tablas distintas y abrir serie/fila fuente.
- **Aceptación:** cada cambio limpia niveles dependientes, la ruta visible coincide y no hay error de consola.
- **Resultado obtenido:** no ejecutado durante la migración.
- **Estado:** pendiente.

### Proyección, métricas y backtesting

- **ID:** M-EST-01.
- **Objetivo:** revisar una serie real y un horizonte dentro/fuera del máximo recomendado.
- **Procedimiento:** analizar una ruta larga, revisar modelos, MAE/RMSE/MAPE/sMAPE/MASE, IC95, diagnóstico y tabla de horizontes; repetir con horizonte no viable.
- **Aceptación:** el modelo y razones coinciden entre panel, explicación, gráfica y reporte; el caso no viable no inventa índice.
- **Resultado obtenido:** no ejecutado en UI durante la migración; el flujo integral sintético sí pasó.
- **Estado:** pendiente manual.

### Empalme y proyección integrada

- **ID:** M-EMP-01.
- **Objetivo:** validar acumulación y reutilización de la proyección.
- **Procedimiento:** calcular una fecha final con dato real y otra posterior al último ICOCIV; verificar dos filas en ambas tablas, marca proyectada y pestañas de proyección.
- **Aceptación:** índices correctos, R=R1+R2, sin cálculo si el horizonte es no viable.
- **Resultado obtenido:** no ejecutado manualmente en UI.
- **Estado:** pendiente manual.

### Reportes e interfaz

- **ID:** M-REP-01.
- **Objetivo:** generar DOCX, PDF y CSV desde una sesión real.
- **Procedimiento:** ejecutar análisis, exportar formatos, abrir archivos y comparar ruta, periodo, modelo e intervalos.
- **Aceptación:** archivos legibles y consistentes, sin tablas deformadas.
- **Resultado obtenido:** T-INT-01 generó PDF/DOCX; revisión visual y CSV quedan pendientes.
- **Estado:** parcial.

## Regla para futuras pruebas

Registrar siempre comando, fecha, insumo real/sintético, salida obtenida y estado. Una prueba omitida o bloqueada no debe marcarse como aprobada.
