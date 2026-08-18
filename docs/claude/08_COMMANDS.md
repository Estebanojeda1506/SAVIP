# Comandos del proyecto

Ejecutar desde la raíz, salvo que se indique otra carpeta.

## Crear y activar entorno

```bash
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

La creación de un entorno nuevo no se ejecutó durante la migración para no alterar el entorno de trabajo.

## Instalar dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

El archivo declara pandas, NumPy, scikit-learn, pyxlsb, openpyxl, python-docx, matplotlib y PySide6. Sus importaciones se verificaron en el entorno existente. `statsmodels` y `pytest` no están declarados.

## Ejecutar la aplicación

```bash
python aplicacion.py
```

El punto de entrada y sus importaciones se verificaron; no se abrió una sesión interactiva completa durante la migración.

## Ejecutar pruebas sin pytest

```bash
python tests/test_imports_modulos.py
python tests/test_empalme_iccp_icociv.py
python tests/test_resultado_horizonte_solicitado.py
python pruebas/prueba_analisis_integral.py
python pruebas/prueba_bloqueo_estadistico.py
```

Para Qt sin pantalla:

PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python tests/test_empalme_iccp_icociv.py
```

Linux/macOS:

```bash
QT_QPA_PLATFORM=offscreen python tests/test_empalme_iccp_icociv.py
```

Si se incorpora `pytest` como dependencia de desarrollo:

```bash
python -m pytest tests pruebas
```

Este último comando está pendiente de verificar; `pytest` no estaba instalado.

## Compilar LaTeX

```bash
cd documentacion_latex/documento_tecnico_icociv_iccp
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

`pdflatex` se verificó con MiKTeX. La secuencia completa con BibTeX es la requerida para actualizar citas y referencias; en esta migración se verificó una pasada de pdfLaTeX sobre auxiliares existentes.

## Limpiar temporales LaTeX

No usar `git clean -fdX`: el `.gitignore` también cubre formatos de datos y documentos que pueden ser fuentes. Desde la carpeta del documento final, la limpieza explícita es:

PowerShell:

```powershell
Remove-Item -LiteralPath main.aux,main.bbl,main.blg,main.lof,main.log,main.lot,main.out,main.toc -ErrorAction SilentlyContinue
```

Linux/macOS:

```bash
rm -f main.aux main.bbl main.blg main.lof main.log main.lot main.out main.toc
```

Estos comandos eliminan auxiliares concretos, no `main.tex`, `referencias.bib` ni figuras. No fueron ejecutados durante la migración.

## Reportes y sesiones

La generación normal de PDF, DOCX y CSV se inicia desde los botones de la interfaz; no existe un CLI estable dedicado. `python pruebas/prueba_analisis_integral.py` genera reportes de verificación en `reportes_generados/`. Las sesiones se administran desde la aplicación y se guardan en `sesiones/`.

## Empaquetado como ejecutable de Windows

```powershell
.\scripts\build_exe.ps1                 # compila (crea .venv-build, prueba y autocomprueba)
.\scripts\build_exe.ps1 -Diagnostico    # variante con consola visible
.\scripts\package_release.ps1           # ZIP + SHA-256
.\scripts\clean_build.ps1               # limpia build/ y dist/
```

Salida: `release/ICOCIV-<VERSION>-windows/ICOCIV.exe`.
Autocomprobacion sin interfaz: `ICOCIV.exe --autocomprobacion`.
Procedimiento completo: `EXE_BUILD_GUIDE.md`.
