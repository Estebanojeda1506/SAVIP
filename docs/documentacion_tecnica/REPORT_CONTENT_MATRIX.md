# Matriz de contenido de los informes

Qué sección aparece en cada tipo, de dónde salen sus datos y cuándo se omite.
Las claves son las de `SECCIONES_DISPONIBLES` en `app_icociv/reportes/modelo.py`.

`●` marcada por defecto · `○` disponible pero sin marcar · `—` no aplica

## Informe de proyección

| Clave | Título | Ejecutivo | Técnico | Origen de los datos | Se omite cuando |
|---|---|:--:|:--:|---|---|
| `portada` | Portada | ● | ● | Serie, archivo, versión, campos institucionales | Nunca (si está marcada) |
| `resumen` | Resumen ejecutivo | ● | ● | `resultado_horizonte_solicitado`, `analisis_horizontes_completo`, `proyecciones` | Nunca |
| `identificacion` | Identificación de la serie | ● | ● | `validacion_serie`, `serie_df`, ruta jerárquica | Nunca |
| `ficha` | Ficha de resultados | ● | ● | Horizonte solicitado, `ajuste_calendario`, `cobertura_empirica` | Nunca |
| `grafica_principal` | Gráfica principal | ● | ● | `serie_df` + `proyecciones` | Serie vacía o sin columna `Indice` |
| `tabla_proyeccion` | Proyección mes a mes | ● | ● | `proyecciones` + clasificación por horizonte | Nunca (si no hay proyección, explica el motivo) |
| `interpretacion` | Interpretación | ● | ● | `analisis_serie`, `proyecciones`, `ajuste_calendario`, nivel de confianza | Nunca |
| `advertencias` | Advertencias y limitaciones | ● | ● | `advertencias_categorizadas`, `factibilidad` + limitaciones fijas | Nunca |
| `preparacion` | Preparación de la serie | ○ | ● | `validacion_serie` | Nunca |
| `fundamento` | Fundamento estadístico | ○ | ● | `_lineas_fundamento_estadistico` | Sin líneas de fundamento |
| `modelos` | Modelos evaluados | ○ | ● | `catalogo_modelos` | Catálogo vacío |
| `seleccion_modelo` | Criterio de selección | ○ | ● | `justificacion_modelo`, `salvaguarda_benchmark`, `descartes_modelos` | Nunca |
| `metricas` | Métricas del modelo | ○ | ● | `backtesting.metricas` | Sin métricas finitas |
| `backtesting` | Validación temporal | ○ | ● | `backtesting`, horizontes evaluados | Nunca (explica si no se ejecutó) |
| `intervalos` | Intervalo del 95 % | ○ | ● | Primera fila de `proyecciones` | Sin tabla de proyección |
| `cobertura` | Cobertura empírica | ○ | ● | `cobertura_empirica.por_horizonte` | Sin cobertura verificable |
| `residuos` | Diagnóstico de residuos | ○ | ● | `diagnostico_residuos` | Diagnóstico vacío |
| `atipicos` | Valores atípicos | ○ | ● | `outliers` con severidad `posible_atipico` | Nunca (dice que no hay) |
| `calendario` | Patrón de cambio de año | ○ | ● | `ajuste_calendario` | Sin trazabilidad de calendario |
| `horizonte` | Horizonte admisible | ○ | ● | `analisis_horizontes_completo`, con el motivo de cada clasificación | Nunca |
| `formulas` | Fórmulas aplicadas | ○ | ● | Último índice observado y `proyecciones` | Nunca |
| `reproducibilidad` | Reproducibilidad | ● | ● | Versión, identificador, `parametros_modelo`; en el técnico añade ecuación del modelo, receta de reproducción y referencias | Nunca |
| `anexos` | Anexos | ○ | ○ | Serie histórica y, si se pidió, ventanas de backtesting | Serie vacía y anexo no solicitado |

### Gráficas

| Clave | Gráfica | Ejecutivo | Técnico | Devuelve `None` cuando |
|---|---|:--:|:--:|---|
| `historico_proyeccion` | Histórico y proyección | ● | ● | Serie vacía |
| `intervalo_95` | Banda del 95 % sobre la gráfica principal | ● | ● | (modifica la principal, no añade figura) |
| `comparacion_modelos` | RMSE por modelo | ○ | ● | Menos de dos modelos con RMSE finito |
| `errores_horizonte` | Error por horizonte | ○ | ● | Menos de dos horizontes evaluados |
| `residuos` | Residuos en el tiempo | ○ | ● | Menos de cuatro residuos finitos |
| `atipicos` | Atípicos sobre la serie | ○ | ● | Sin atípicos de severidad relevante |
| `calendario` | Variación diciembre→enero | ○ | ● | Sin evidencia de patrón calendario |

`intervalo_95` no es una figura aparte: activa la banda sombreada dentro de la
gráfica principal. Desmarcarla deja la proyección sin banda, que es lo que pide
quien quiere una lámina limpia para una presentación.

El anexo con las ventanas de backtesting es una casilla aparte
(`incluir_anexo_backtesting`), desmarcada siempre por defecto: son decenas de
filas que solo interesan a quien audita el método.

## Informe de ajuste ICCP–ICOCIV

Estructura fija; lo configurable son los campos institucionales, la moneda, el
logo y el bloque de firmas.

| Sección | Contenido | Origen |
|---|---|---|
| Resumen ejecutivo | Ítems, periodo, base, ajuste total, valor actualizado, metodología aplicada | Agregado de los cálculos |
| Datos generales del ajuste | Entidad, contrato, objeto, contratista, supervisor, interventor, responsable | Campos institucionales + formulario del módulo |
| Índices utilizados | Variable, descripción, valor, periodo, fuente y **tipo de dato** | `i0_iccp`, `i_iccp`, `i0_icociv`, `i_icociv` |
| Selección del índice base I0 | Fechas, caso aplicado y criterio registrado | `fecha_inicial`, `fecha_final`, `caso`, `observacion_tecnica` |
| Fórmulas y sustitución numérica | Base, R1, R2, R, valor actualizado y Z en el caso acero | Fórmula general + valores del cálculo |
| Resultados del ajuste | Tabla por ítem con parciales y variación | `r1`, `r2`, `r_total`, `valor_actualizado` |
| Advertencias contractuales | Cinco fijas más las propias del cálculo | Reglas del módulo de empalme |
| Trazabilidad | Serie ICCP, ruta ICOCIV, origen de I y modelo | Trazabilidad de cada cálculo |

### Tipos de dato de los índices

La columna «Tipo de dato» distingue tres orígenes, porque un ajuste contractual
no puede confundirlos:

- **Índice oficial observado** — publicado por el DANE.
- **Índice proyectado por SAVIP** — cuando `icociv_final_es_proyectado` es cierto.
  El informe lo marca, nombra el modelo y advierte que debe recalcularse con el
  índice oficial cuando se publique.
- **Valor ingresado por el usuario** — precio base, anticipo, Ix y q, que
  aparecen en las fórmulas, no en la tabla de índices.

## Lo que ningún informe muestra

Prohibido por diseño y comprobado por pruebas:

- rutas internas del sistema de archivos (solo el nombre del archivo fuente);
- nombres de módulos, funciones, archivos de código o pruebas;
- estructuras de datos crudas (`{'anio': 2026, ...}`);
- la banda del 80 %, salvo la frase que explica que se retiró;
- la expresión «intervalo de confianza» referida a observaciones futuras;
- ETS como modelo evaluado;
- Ljung–Box presentada como ejecutada cuando no está disponible;
- capturas de la aplicación.
