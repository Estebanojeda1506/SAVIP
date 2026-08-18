# Documento LaTeX

## Documento final

- Principal: `documentacion_latex/documento_tecnico_icociv_iccp/main.tex`.
- Bibliografía: `documentacion_latex/documento_tecnico_icociv_iccp/referencias.bib`.
- Figuras fuente: `documentacion_latex/documento_tecnico_icociv_iccp/figuras/`.
- Tablas y anexos: `tablas/` y `anexos/` dentro de la misma carpeta.
- Salida actual: `main.pdf`, 112 páginas en la compilación verificada del 19 de julio de 2026.

El documento está concentrado en `main.tex`; no hay capítulos separados mediante `\input`. Las figuras de flujo sí son archivos TikZ independientes.

## Compilación

Desde la carpeta del documento:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

En el entorno Windows auditado, `pdflatex` de MiKTeX compiló sin error fatal. Se observaron avisos de cajas `underfull`, sustitución de formas de fuente y actualización pendiente de MiKTeX; no impidieron generar el PDF.

## Estructura real

El outline funcional del documento es:

1. Introducción.
2. Marco teórico, contexto y antecedentes (integrado dentro de la primera sección antes de Metodología).
3. Metodología.
4. Desarrollo del software o del sistema.
5. Pruebas de software.
6. Manual de usuario.
7. Discusión y conclusiones.
8. Referencias.
9. Anexos A–G.

La sección de metodología incluye necesidades, diseño, desarrollo, análisis estadístico, integración, documentación y puesta en conocimiento. El desarrollo describe arquitectura, carga/selector, proyección, empalme y exportables. Los anexos incluyen fuentes, pruebas, capturas, fórmulas, manual ampliado, matriz de criterios e integración del documento estadístico preliminar.

## Reglas editoriales

- No alterar objetivos ni títulos institucionales fijados sin autorización.
- No mencionar innecesariamente el anteproyecto ni describir el software como local.
- No inventar resultados, referencias o pruebas.
- ARIMA fue retirado del alcance el 19 de julio de 2026, de forma coordinada en código, pruebas, reportes, bibliografía y LaTeX. No debe reaparecer en el documento.
- Conservar las citas originales y validar que toda clave citada exista en `referencias.bib`.
- Mantener consistencia de fórmulas, nombres de variables y exportables con la aplicación.
- No usar archivos de `tmp/` o PDFs generados como fuentes metodológicas.

## Documento estadístico preliminar

La fuente de apoyo está en `documentacion_latex/guia_academica_estadistica/` y existen copias históricas en otras carpetas. El documento final ya contiene un Anexo G de integración y secciones estadísticas ampliadas. Antes de trasladar más texto, comparar la implementación vigente para evitar reincorporar descripciones obsoletas.

## Pendientes documentales comprobados

- Resuelto el 19 de julio de 2026: la prueba de auditoría exigía claves (`iglewicz_hoaglin1993`, `granger_newbold1974`) que la guía académica nunca cita; se alineó la aserción con la única clave citada (`duan1983`) y la prueba pasa.
- Revisar visualmente las advertencias de composición si se modifica contenido extenso.
- Confirmar el requisito definitivo de hojas del Excel antes de futuras correcciones académicas.
