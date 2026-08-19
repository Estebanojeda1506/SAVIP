# SAVIP — Sistema de Análisis de Variaciones de Precios

Aplicación de escritorio en Python y PySide6 para analizar las series del **Índice
de Costos de la Construcción de Obras Civiles (ICOCIV)** del DANE, validar su
calidad temporal, comparar modelos de pronóstico mediante *backtesting*
walk-forward, determinar hasta qué horizonte existe evidencia fuera de muestra,
proyectar índices y generar informes técnicos en PDF, DOCX, HTML y CSV.

Incluye un módulo de actualización de precios que empalma el **ICCP** histórico
con el **ICOCIV**, contempla el caso especial del acero y exporta la trazabilidad
completa del cálculo a Excel.

> **ICOCIV** e **ICCP** son índices oficiales del DANE, no nombres de esta
> aplicación. El paquete Python interno conserva el nombre técnico `app_icociv`.

## Alcance y limitaciones

SAVIP **no** reemplaza la producción estadística oficial del DANE ni el criterio
profesional del ingeniero responsable. Las proyecciones que genera son
estimaciones propias del software y se distinguen explícitamente del dato
histórico oficial en toda salida.

Las equivalencias ICCP–ICOCIV son selecciones técnicas que **requieren
validación profesional**. La fecha base aplicable depende de las condiciones del
contrato específico: la aplicación no la determina automáticamente.

Limitaciones metodológicas declaradas en la versión final:

- El primer origen del *backtesting* (`N₀ = 6`) es una **configuración
  provisional**, derivada del modelo más exigente del catálogo. No es un valor
  óptimo ni universal, y la selección del modelo ganador es sensible a él en
  parte de las series.
- Los **intervalos de predicción** se estudiaron y se **retiraron** de las
  salidas: la construcción completa no alcanzó el sustento exigido. El cálculo
  permanece solo como diagnóstico interno y no decide nada.
- El patrón de variación concentrada en la transición diciembre–enero se
  **identifica de forma descriptiva** pero **no se traslada al pronóstico**.
  Queda documentado como trabajo futuro.

## Requisitos e instalación

Python 3.12 o superior.

```bash
python -m venv .venv
```

```bash
python -m pip install -r requirements.txt
```

En PowerShell el entorno se activa con `.\.venv\Scripts\Activate.ps1`; en Linux o
macOS con `source .venv/bin/activate`.

## Ejecutar la aplicación

```bash
python aplicacion.py
```

El archivo Excel o XLSB del anexo se elige desde un diálogo; no se escriben rutas
en el código. Los anexos oficiales del DANE **no se distribuyen con este
repositorio**: se descargan de la publicación oficial.

Para validar una instalación o una distribución empaquetada sin abrir la
interfaz:

```bash
python aplicacion.py --autocomprobacion
```

## Ejecutar pruebas

```bash
python tests/test_imports_modulos.py
```

```bash
python tests/test_cierre_metodologico.py
```

Las pruebas que necesitan el anexo oficial se **omiten solas** cuando el archivo
no está presente, de modo que la suite corre en una copia limpia del
repositorio. Si se instala `pytest` —no es una dependencia declarada— puede
usarse `pytest tests pruebas`.

## Estructura

```text
app_icociv/
├── config/        # rutas, autocomprobación y configuración
├── datos/         # carga de Excel/XLSB y lectura de anexos
├── estadistica/   # descriptivos, métricas, diagnósticos, criterios y modelos
├── validacion/    # backtesting walk-forward
├── proyeccion/    # factibilidad, horizontes y proyección
├── reportes/      # PDF, DOCX, HTML, gráficas y tablas
├── exportables/   # CSV reproducible
├── persistencia/  # sesiones JSON
├── servicios/     # empalme ICCP-ICOCIV y actualización de valores
├── interfaz/      # PySide6, controladores, widgets, tema y QSS
└── utilidades/    # periodos, nomenclatura y funciones auxiliares
```

Puntos de entrada relevantes:

| Archivo | Qué hace |
|---|---|
| `aplicacion.py` | Punto de entrada; admite `--autocomprobacion` |
| `VERSION` | Fuente única de la versión |
| `app_icociv/proyeccion/servicio_proyeccion.py` | Flujo estadístico y proyección |
| `app_icociv/validacion/backtesting.py` | Evaluación walk-forward |
| `app_icociv/estadistica/criterios.py` | Matriz auditable de criterios |
| `app_icociv/servicios/empalme_iccp_icociv.py` | Fórmulas del empalme |
| `packaging/SAVIP.spec` | Empaquetado con PyInstaller |

## Metodología

El modelo entregado se elige por **RMSE fuera de muestra sobre la muestra
común** entre diez candidatos interpretables (Naive, Drift, lineal,
logarítmico, exponencial log-lineal, Huber, Holt lineal, Holt amortiguado,
variación mensual y log-variación). Se entrega **un solo modelo por serie**,
para que los meses comunes no cambien según el horizonte solicitado.

Cada horizonte se evalúa con su **propia** evidencia fuera de muestra. Un
horizonte se niega solo por imposibilidad: que el pronóstico no sea finito, o
que no exista el dato con el que evaluarlo. Ninguna magnitud de error, amplitud
o recuento intermedio de ventanas veta un horizonte; todas se publican con su
valor.

Cada criterio que afecta un resultado está registrado con su tipo, su valor y su
fuente en `app_icociv/estadistica/criterios.py`, del que se generan
automáticamente la matriz publicada en el documento y
`docs/auditoria_criterios_estadisticos.md`.

## Documentación

| Ruta | Contenido |
|---|---|
| `documentacion_latex/documento_tecnico_icociv_iccp/` | **Documento final del trabajo de grado** |
| `documentacion_latex/criterios_estadisticos_aplicacion/` | Anexo de criterios con fórmula, fuente y prueba |
| `documentacion_latex/guia_academica_estadistica/` | Guía académica del análisis estadístico |
| `documentacion_latex/ejemplo_numerico_vias_urbanas/` | Ejemplo numérico reproducible |
| `documentacion_latex/documentacion_tecnica_modulos/` | Documentación técnica de módulos |
| `documentacion_latex/LEEME.md` | Índice y estado de cada documento |
| `docs/referencias/` | Matriz de referencias y manifiesto de fuentes externas |
| `docs/mapa_reorganizacion_modulos.md` | Mapa técnico de módulos |
| `docs/claude/` | Documentación técnica: arquitectura, mapa de módulos, métodos estadísticos, empalme, pruebas, empaquetado y sistema visual |
| `MANIFIESTO_REPOSITORIO.md` | Qué contiene este repositorio y qué se dejó fuera |

El documento final se compila desde su carpeta con `latexmk`, que decide por sí
mismo cuántas pasadas hacen falta y evita dejar un *rerun* pendiente:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Si `latexmk` no está disponible, la secuencia manual equivalente —verificada
para que converja sin *rerun* pendiente— es:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex && bibtex main && pdflatex -interaction=nonstopmode -halt-on-error main.tex && pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Los PDF compilados **no se versionan**: se reconstruyen desde las fuentes para
que el binario y el texto no puedan divergir sin que se note.

## Fuentes y atribución

Los datos de índices provienen de los anexos oficiales del **DANE** y no se
redistribuyen aquí. La bibliografía metodológica se cita en el punto de uso y se
lista en `referencias.bib` de cada documento; su trazabilidad está en
`docs/referencias/MATRIZ_REFERENCIAS.csv` y
`docs/referencias/MANIFIESTO_FUENTES_EXTERNAS.md`.

Las bibliotecas de terceros empleadas conservan sus propias licencias y se
declaran en `requirements.txt`.

## Contexto

Trabajo de grado, modalidad investigación, desarrollado para apoyar el análisis
de variaciones de precios en contratos de obra civil de la Secretaría de
Infraestructura de la Gobernación del Cauca.

- **Autor:** Carlos Esteban Ojeda Calvache
- **Director:** PhD. Lucio Gerardo Cruz Velasco
- Programa de Ingeniería Civil, Facultad de Ingeniería Civil, Universidad del
  Cauca. Popayán, Colombia, 2026.

## Notas de mantenimiento

- Mantener separadas la lógica estadística, la presentación en PySide6 y la
  generación de informes.
- Ningún color ni medida literal fuera de `app_icociv/interfaz/tema/`.
- No comunicar un estado solo con color: acompañar con símbolo o texto.
- Conservar la trazabilidad de `I`, `I0`, `R1`, `R2`, `R`, valor actualizado y,
  para acero, `Z`.
- Mantener la coherencia entre la aplicación, el Excel exportable, los informes
  y el documento LaTeX.
- Docstrings y comentarios nuevos en español.
