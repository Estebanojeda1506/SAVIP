# Guia academica de modelado estadistico ICOCIV

Este directorio contiene un proyecto LaTeX academico para explicar el analisis estadistico y predictivo usado por la aplicacion ICOCIV.

## Archivos

- `main.tex`: documento principal.
- `referencias.bib`: bibliografia en formato BibTeX.
- `figuras/`: carpeta reservada para figuras futuras.
- `tablas/`: carpeta reservada para tablas auxiliares futuras.

## Compilacion recomendada en Overleaf

1. Crear un proyecto nuevo en Overleaf.
2. Subir `main.tex` y `referencias.bib`.
3. Mantener `pdflatex` como compilador.
4. Compilar con la secuencia estandar:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Overleaf ejecuta esta secuencia automaticamente cuando detecta BibTeX.

## Compilacion local

Si el equipo tiene TeX Live, MiKTeX o una distribucion equivalente:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Notas metodologicas

El documento no recalcula la metodologia oficial del DANE. Explica como la aplicacion usa series oficiales del ICOCIV para analisis descriptivo, validacion temporal, seleccion de modelos, intervalos de prediccion y determinacion dinamica del horizonte maximo.

La version actual usa un diagrama TikZ liviano dentro de `pdflscape` y `adjustbox`. No usa bucles, imagenes externas ni bibliografia pesada, por lo que debe ser compatible con Overleaf gratuito.
