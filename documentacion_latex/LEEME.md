# Documentos LaTeX del proyecto

Todos los documentos LaTeX del proyecto viven aquí. Fuera de esta carpeta no
debe quedar ningún `.tex` propio: si aparece uno, es una copia que hay que
mover o descartar.

Última consolidación: 22 de julio de 2026.

---

## Documentos vigentes

| Carpeta | Qué es | Estado | Páginas |
|---|---|---|---|
| `documento_tecnico_icociv_iccp/` | **Documento final del trabajo de grado.** Único entregable académico. | Vigente | 119 |
| `guia_academica_estadistica/` | Guía académica del análisis estadístico y predictivo. Apoyo metodológico, no entregable. | Vigente | — |
| `ejemplo_numerico_vias_urbanas/` | Ejemplo numérico reproducible completo (Vías urbanas, h=18) con datos reales. | Vigente | 12 |
| `documentacion_tecnica_modulos/` | Documentación técnica de los módulos de la aplicación. | Vigente | — |
| `criterios_estadisticos_aplicacion/` | Documento de estudio independiente: todos los criterios estadísticos con fórmula, fuente, implementación y prueba. Su contenido está **integrado en el cuerpo de la tesis** (marco teórico y metodología, Sección "Catálogo auditable de criterios"); este documento se conserva para estudiarlo por separado. Tabla generada desde el módulo interno de criterios. | Vigente | 17 |
| `evidencia_metodologica_cumplimiento/` | Documento de respaldo con la matriz de trazabilidad metodológica (antiguo apartado 3.14 de la tesis, extraído para no recargar el cuerpo). | Vigente | 3 |

El anexo `documento_tecnico_icociv_iccp/anexos/flujo_estadistico_aplicacion.tex`
(6 páginas) explica el flujo estadístico y se compila por separado.

## Cómo saber cuál es la última versión

Cada documento vigente tiene **una sola** carpeta en el primer nivel de
`documentacion_latex/`. Todo lo que esté bajo `historico/` es una versión
anterior y no debe editarse ni citarse.

## Compilación

Desde la carpeta del documento, con `latexmk` (decide por sí mismo cuántas
pasadas hacen falta, incluida la bibliografía, y evita dejar un *rerun*
pendiente):

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Documentos sin bibliografía propia pueden compilarse con una sola pasada de
`pdflatex`. Si `latexmk` no está disponible, la secuencia manual equivalente
para el documento final —verificada para que converja sin *rerun*
pendiente— es:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex && bibtex main && pdflatex -interaction=nonstopmode -halt-on-error main.tex && pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Versiones históricas

En `historico/`, conservadas solo como respaldo:

| Carpeta | Origen anterior | Por qué no es la vigente |
|---|---|---|
| `guia_academica_2026-06-21_identica_a_vigente/` | `Documento latex 21-06-2026/` | Byte a byte idéntica a la vigente; duplicado exacto. |
| `guia_academica_con_correcciones/` | `documentacion/metodologia icociv overleaf con correcciones/` | Versión más corta y anterior de la guía. |
| `guia_academica_avances_estadistico/` | `documentos avances estadistico/guia_academica_modelado_estadistico_icociv/` | Idéntica a la anterior; duplicado exacto. |
| `guia_academica_variante_tikz/` | `docs/guia_academica_modelado_estadistico_icociv/` | Variante con diagramas TikZ en línea; describe un «nivel 3» que fue eliminado del proyecto. |

Las cuatro son versiones de la **misma** guía académica. La vigente es
`guia_academica_estadistica/`, confirmada como proyecto canónico en
`informe_actualizacion_documento_metodologico.md`.

## Reglas

- No editar nada dentro de `historico/`.
- No crear copias de un documento vigente en otra carpeta; versionar por Git.
- No mover `documento_tecnico_icociv_iccp/`: su ruta está fijada en `CLAUDE.md`
  y en `docs/claude/`.
