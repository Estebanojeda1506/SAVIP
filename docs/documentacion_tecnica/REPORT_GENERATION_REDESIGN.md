# Rediseño de la generación de informes (27 de julio de 2026)

## Por qué

Los informes eran un volcado: veinte secciones fijas, seis gráficas siempre, las
mismas tablas para cualquier lector y sin forma de elegir qué incluir. El PDF,
además, se dibujaba con `matplotlib.PdfPages`: páginas de texto plano dentro de
una figura, sin paginación, sin índice, sin marcadores y sin tablas reales. El
DOCX y el PDF habían divergido hasta traer secciones distintas y numeraciones
distintas del mismo análisis.

El objetivo del rediseño es que el informe sirva para decidir: primero el
resultado, después la explicación y solo al final la metodología, con el usuario
eligiendo el nivel de detalle.

**El rediseño no toca la estadística.** Modelos, fórmulas, métricas, intervalos,
criterios, clasificaciones, ajuste calendario y selección de modelo quedan
exactamente igual. La capa de contenido solo lee el diccionario que devuelve
`ejecutar_proyeccion`.

## Arquitectura

Un modelo de documento en el centro y dos renderizadores que lo dibujan. El
contenido se decide una sola vez; el formato decide *cómo* se ve, nunca *qué*
se dice.

```
ejecutar_proyeccion()  ──►  contenido.py          ──┐
calcular_empalme()     ──►  contenido_empalme.py ──┤──►  Informe  ──┬──► docx_render.py  ──► .docx
                                                    │  (modelo.py)  └──► pdf_render.py   ──► .pdf
                            graficas.py  ───────────┘
```

### Archivos

| Archivo | Responsabilidad |
|---|---|
| `app_icociv/reportes/modelo.py` | Bloques tipados (`Parrafo`, `Tabla`, `Ficha`, `Aviso`, `Formula`, `Imagen`, `Vinetas`, `Firmas`), `Seccion`, `Portada`, `Informe`, `ConfiguracionInforme`, `CamposInstitucionales`, paleta documental y formateadores. |
| `app_icociv/reportes/contenido.py` | Construye el informe de proyección e interpreta los resultados en lenguaje comprensible. |
| `app_icociv/reportes/contenido_empalme.py` | Construye el informe de ajuste ICCP–ICOCIV con fórmulas y sustitución numérica. |
| `app_icociv/reportes/graficas.py` | Gráficas con la identidad SAVIP. Devuelven `None` si no hay datos. |
| `app_icociv/reportes/docx_render.py` | Word editable: estilos nombrados, portada, índice de campo, encabezado y pie, tablas reales. |
| `app_icociv/reportes/pdf_render.py` | PDF paginado con ReportLab: índice navegable, marcadores, «Página X de Y», fuentes incrustadas. |
| `app_icociv/interfaz/widgets/dialogo_informe.py` | Selector de contenido previo a exportar. |
| `app_icociv/reportes/generador_reportes.py` | Capa de datos: CSV reproducible, informe HTML, fragmentos `_lineas_*` y las entradas públicas que delegan en el nuevo pipeline. |

El generador antiguo perdió 1 400 líneas: el compositor DOCX, las tablas de Word
hechas a mano y las gráficas del PDF de matplotlib desaparecieron al quedar sin
uso. Las firmas públicas se conservan, con un parámetro opcional
`configuracion` al final.

### Regla de oro del modelo

`Informe.secciones_visibles()` descarta toda sección sin bloques. Por eso las
funciones de `graficas.py` devuelven `None` cuando faltan datos y las secciones
devuelven una `Seccion` vacía: nunca queda un título con un hueco debajo ni una
página en blanco.

## Tipos de informe

| Tipo | Extensión medida | Contenido |
|---|---|---|
| Ejecutivo | 4–6 páginas | Portada, resumen, identificación, ficha, una gráfica, interpretación, advertencias, tabla de proyección, trazabilidad. |
| Técnico | 13–15 páginas | Todo lo anterior más preparación, fundamento estadístico, modelos, criterio de selección, métricas, backtesting, intervalo del 95 %, cobertura, residuos, atípicos, calendario, horizonte, fórmulas y reproducibilidad. Los anexos quedan disponibles pero sin marcar. |
| Ajuste ICCP–ICOCIV | 3–5 páginas | Datos generales, índices tipificados, criterio de I0, fórmulas con sustitución numérica, resultados, advertencias contractuales y trazabilidad. |
| Personalizado | Variable | Selección libre de secciones y gráficas. |

Las extensiones son las medidas con horizontes de 6 a 18 meses. Un horizonte más
largo alarga la tabla de proyección y la de evaluación por horizonte: con
h = 24 el técnico llega a 16 páginas, una por encima del rango recomendado. Es
consecuencia del dato, no del diseño.

Los anexos —serie histórica completa y ventanas de backtesting— quedan fuera del
preajuste técnico: esa información ya viaja en el CSV reproducible y repetirla
añadía dos páginas de tablas. Siguen disponibles marcándolos en el selector.

## Selector de contenido

`pedir_configuracion(padre, tipo_inicial, formato)` abre el diálogo modal y
devuelve una `ConfiguracionInforme` o `None` si el usuario cancela.

- Elegir un tipo aplica su plantilla de casillas.
- Tocar cualquier casilla pasa el tipo a «Personalizado»: a partir de ahí la
  selección ya no coincide con ninguna plantilla.
- Los campos institucionales son todos opcionales y viven en una pestaña aparte.
- El logo se limita a 4 MB y se incrusta en la portada de ambos formatos.

## Diferencias entre DOCX y PDF

No son el mismo archivo convertido: cada uno se compone por separado a partir
del mismo `Informe`.

**DOCX (formato de trabajo).** Estilos nombrados de Word (`Normal`, `Title`,
`Heading 1-3`, `SAVIP Pie de figura`, `SAVIP Nota`, `SAVIP Formula`,
`SAVIP Aviso`) para que un cambio se propague a todo el documento. Portada
editable, campo `TOC` que Word recalcula con F9, encabezado con el identificador,
pie con `PAGE` de `NUMPAGES`, tablas reales con `w:tblHeader` (encabezado
repetido) y `w:cantSplit` (filas que no se parten), y bloque de firmas opcional.

**PDF (formato final).** `BaseDocTemplate` con dos plantillas de página: portada
sin encabezado y cuerpo con encabezado y pie. Índice con enlaces internos
(`TableOfContents` + `notify("TOCEntry", ...)`), marcadores de navegación
(`bookmarkPage` + `addOutlineEntry`), tablas con `repeatRows=1` y `splitByRow=1`,
figuras y avisos envueltos en `KeepTogether`, y fuentes Bitstream Vera
incrustadas. Se compone en dos pasadas (`multiBuild`) para resolver el índice.

El índice solo aparece a partir de diez secciones: en un documento de cinco
páginas robaría una página sin ayudar a nadie.

## Dependencia nueva: ReportLab

Los requisitos del PDF —índice navegable, marcadores, tablas que no se cortan y
fuentes incrustadas— no se pueden cumplir dibujando con matplotlib. `reportlab`
queda declarado en `requirements.txt`, en `hiddenimports` de
`packaging/SAVIP.spec` y sus fuentes Vera en `datas`, porque se abren por ruta en
tiempo de ejecución.

Si falta, `pdf_render.guardar()` lanza un error explícito con la instrucción de
instalación, igual que hace `python-docx`. No se degrada el documento en
silencio.

```bash
python -m pip install reportlab
```

## Decisiones de contenido que corrigen el informe anterior

- **La portada ya no expone rutas internas.** Solo el nombre del archivo fuente.
  El antiguo «Ruta del archivo» y «Selección registrada: {dict}» desaparecieron.
- **Ljung–Box no se presenta como ejecutada.** Sin `statsmodels` la prueba no se
  calcula, y el informe lo dice con esas palabras en vez de imprimir un campo
  vacío.
- **La banda del 80 % no aparece.** El mensaje de cobertura que produce la capa
  estadística la menciona; el informe reconstruye ese resumen con el 95 % en
  lugar de copiarlo. La única mención al 80 % es la frase que explica por qué se
  retiró.
- **Los intervalos se llaman de predicción**, nunca de confianza, y el informe
  explica la diferencia.
- **El patrón calendario se distingue del valor atípico.** La gráfica de atípicos
  excluye los eneros clasificados como patrón calendario.
- **La cobertura empírica se reporta con su mínimo**, no solo con la media, y con
  la advertencia de que no se reclama la garantía del método conformal.

### Trazabilidad conservada del informe anterior

El rediseño reordenó el contenido, no lo recortó. Siguen presentes en el informe
técnico, reutilizando los generadores de texto de `generador_reportes.py`:

- el fundamento estadístico del método (sección propia `fundamento`);
- los parámetros y la ecuación del modelo aplicado;
- la receta paso a paso para reproducir la proyección a mano;
- las referencias metodológicas y estadísticas;
- el motivo por el que cada horizonte quedó en su clasificación, como viñeta por
  clasificación más la del horizonte solicitado.

## Convenciones de formato

| Dato | Formato | Ejemplo |
|---|---|---|
| Índices | 4 decimales, coma decimal, espacio duro de miles | `1 234,5000` |
| Porcentajes | 1 o 2 decimales, espacio antes del signo | `4,1 %` |
| Moneda | Separadores según el código elegido (COP, USD, EUR) | `$ 1.000.000.000,00` |
| Fechas de periodo | Mes en letras | `mayo de 2026` |
| Fecha de generación | Día, mes en letras y año | `26 de julio de 2026, 15:30` |
| Identificador | `SAVIP-INF-AAAAMMDD-HHMMSS` | `SAVIP-INF-20260726-153045` |
| Nombre de archivo | Sin acentos ni caracteres inválidos de Windows | `SAVIP_Informe_Ejecutivo_Vias_ferreas_20260726.docx` |

Ninguna tabla supera ocho columnas; hay una prueba que lo comprueba.

## Qué hacer para añadir una sección

1. Registrar la clave y su etiqueta en `SECCIONES_DISPONIBLES` (`modelo.py`).
2. Escribir `_seccion_<clave>(datos, ...) -> Seccion` en `contenido.py`,
   devolviendo una sección sin bloques cuando no haya datos.
3. Añadirla a `construir_informe_proyeccion` en el orden que le corresponda.
4. Incluir la clave en el preajuste que la necesite.

No hace falta tocar los renderizadores: entienden los bloques, no las secciones.

## Ver también

- `docs/documentacion_tecnica/REPORT_CONTENT_MATRIX.md` — qué sección aparece en cada tipo.
- `docs/documentacion_tecnica/REPORT_TEST_PLAN.md` — qué comprueba cada prueba y qué no.
