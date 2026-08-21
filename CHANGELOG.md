# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionamiento semántico: `MAJOR.MINOR.PATCH`.

La versión vigente se define en el archivo [`VERSION`](VERSION), que es la única
fuente de verdad: la aplicación, el ejecutable y los scripts de compilación la
leen de allí.

---

## [1.0.0] — 20 de agosto de 2026

Primera versión estable de SAVIP. Incluye el módulo de Proyecciones ICOCIV
(catálogo de 21 candidatos, N0=12, H=24, backtesting rectangular, un modelo
seleccionado por serie, horizonte operativo de 1 a 24 meses), el módulo de
Empalme ICCP–ICOCIV (con proyección de fecha futura acotada al mismo
horizonte de 24 meses), generación de reportes DOCX/PDF/CSV, y la
optimización de tiempos de cálculo del motor de proyecciones.

## [0.3.0-rc3] — 30 de julio de 2026

Versión candidata que atiende los hallazgos confirmados por la reauditoría
independiente de `0.3.0-rc2`. No es versión final y no está etiquetada. El
ejecutable que se genera en esta fase sigue marcado `NO_DISTRIBUIR`.

### Cambiado — 17 de agosto de 2026

Remediación de los cinco residuales del veredicto `V-CODEX-R3`. **Ninguno era
estadístico**: los tres primeros eran de publicación y comunicación, los dos
últimos documentales. No se reabrieron P0-B, P0-G ni P0-D, y no se cerró P0-E.

- **P0-C — el intervalo retirado ya no es reconstruible.** Vaciar los límites no
  lo había retirado: la tabla de ventanas de backtesting seguía publicando el
  **vector completo de errores fuera de muestra**, y con el pronóstico puntual
  —que es público y debe serlo— `σ̂ = √(media(e²))` devuelve los límites exactos.
  Se retiran de la publicación las siete columnas que lo reconstruyen —incluidas
  `Observado`/`Predicho`, cuya diferencia *es* el error, y `Error_abs`, porque σ̂
  no depende del signo— de `backtesting` y de las 420 entradas de
  `backtesting_comparativo`. Se conserva el **diseño** de la validación (origen,
  periodo objetivo, paso, modelo del corte, tamaño del entrenamiento) y **todos
  los agregados**: RMSE, MAE, MASE, MAPE/sMAPE, sesgo y número de ventanas.
  Se retiraron además doce familias de texto que publicaban σ̂, el nivel nominal,
  la cobertura efectiva y el **ancho relativo con su valor**, que multiplicado por
  el punto devuelve el semiancho de la banda. El CSV pierde siete columnas del
  intervalo que llevaban vacías y cuyo nombre seguía anunciándolo.
- **HGRID — la rejilla deja de anunciar evidencia inexistente.** `_maximo_con`
  forzaba `max(1, …)`: con `N₀ = 6` y `n = 2..6` la cota da cero ventanas y el
  backtesting devuelve cero, pero se publicaba `h = 1` como evaluable. La cuenta
  se unifica en `ventanas_oos_disponibles`, que replica las guardas del bucle;
  verificado contra el backtesting real en 48 combinaciones sin desajustes. Se
  añade el vocabulario de tres tramos y se renombra
  `horizonte_maximo_validado_por_datos`: una ventana no es un horizonte validado.
- **P0-H — la razón pública deja de negar la entrega.** Faltaba la rama que
  redacta el motivo cuando el horizonte **sí** se entrega, de modo que con h1
  permitido, h2 no viable y h3 permitido la salida decía «la evidencia se corta en
  h=2… no puede sostenerse un horizonte de 3 meses» mientras entregaba h=3. Ahora
  el hueco se nombra como hueco, se declara que no se interpola y se explica que
  cada horizonte se evalúa con su propia muestra. Se corrigieron tres textos que
  describían la continuidad ya retirada, se retiró el tercer recorrido por
  prefijo, y las dos gráficas —informe e interfaz— cortan la línea en el hueco
  leyendo una única columna `horizonte_disponible`.
- **P0-E — retirados los overclaims, sin tocar el estado.** Siete archivos activos
  afirmaban un cierre inexistente. `N₀ = 6` sigue **provisional**,
  `C-WF-002 = pendiente_de_decision` y `evidencia_oos_provisional = True`.
- **P0-F — coherencia documental.** No se tocó una línea de la lógica productiva
  del calendario: `aplicado = False` sigue siendo incondicional. Se corrigieron el
  encabezado del módulo, la ficha C-CAL-002 con sus tres artefactos generados,
  cinco bloques de la tesis y la sección completa del anexo.

Regresión detectada por las propias pruebas y corregida: al retirar el piso, la
rejilla podía quedar vacía con `n ≤ N₀` y `_modelos_para_analisis` la indexaba con
`[-1]`, de modo que una serie de dos observaciones levantaba `IndexError` en vez de
bloquear con su razón.

### Cambiado — 16 de agosto de 2026

Remediación de las cuatro regresiones productivas que la auditoría independiente
`V-CODEX-3` confirmó end-to-end, bajo un principio explícito: **SAVIP no persigue
el modelo estadístico perfecto**, persigue que cada regla que afecte el resultado
tenga respaldo. Un bloqueo con sustento es legítimo y se conserva; solo se retira
lo que no encaja en una de las cuatro causas válidas —imposibilidad matemática,
inexistencia del dato, error crítico de entrada, o limitación de alcance declarada.

- **P0-B — el mínimo de 8 observaciones deja de negar la proyección.**
  `construir_serie` cancelaba con `len(serie) < 8` y la compuerta de
  `_ejecutar_proyeccion_base` repetía la comprobación. Era un literal sin fuente
  que cancelaba un pronóstico calculable. Hoy solo impiden modelar un error
  crítico de los datos o una serie sin valores numéricos. Las cifras de 18 y 24
  se conservan como referencias operativas que se comunican y no deciden.

- **P0-C — el intervalo de predicción sale por completo del objeto público.**
  Se había conservado dentro del resultado bajo una clave llamada
  `diagnostico_cobertura_no_publicado`. La objeción de la auditoría es correcta:
  **todo lo que devuelve `ejecutar_proyeccion` es salida pública**, y el nombre de
  una clave no la vuelve privada. El corte de publicación retira ahora también los
  componentes que permitirían reconstruir la banda —`sigma_h`, cuantiles, anchos
  relativos, método— y la cobertura empírica con su clasificación. El cálculo
  permanece dentro de `_ejecutar_proyeccion_base` como diagnóstico que no decide.

- **P0-G — la rejilla de horizontes se acota por existencia, no por la banda.**
  El techo se fijaba con `MIN_ITERACIONES_WF_ESCENARIO = 3`, un mínimo cuya propia
  ficha declara que procede de estimar la dispersión y verificar la cobertura del
  **intervalo**: un requisito de la banda recortaba los horizontes en que se
  entrega el **punto**. El límite pasa a ser la cota aritmética `h ≤ n − N₀`,
  derivada de exigir al menos una ventana. No es un umbral elegido: por debajo no
  existe ningún error fuera de muestra. La constante sobrevive como corte
  descriptivo. En la misma línea, la criticidad de la banda y el ancho relativo
  dejan de entrar en `bloqueos_proyeccion`.

- **P0-H — los horizontes válidos dejan de tener que formar un prefijo.**
  `_ultimo_horizonte_admisible_consecutivo` recorría desde `h=1` y paraba en la
  primera falla, de modo que un fallo temprano cancelaba toda la trayectoria
  posterior. Ninguna fuente exige contigüidad. Se publica ahora el mayor horizonte
  con evidencia suficiente, y el hueco se informa en `primer_horizonte_no_viable`
  sin que el horizonte fallido deje de estar marcado como no permitido.

**Medición.** Sobre diez escenarios de contraste, nueve quedan idénticos byte a
byte —modelo, punto, horizonte, ranking, número de pares y métricas—. El único que
cambia es la serie de siete observaciones, que pasa de `No seleccionado / h=0` a
`Lineal (OLS) / 110,5000 / h=1`: es exactamente la remediación de P0-B. Ninguna
cifra se movió por efecto de las otras tres.

Se sincronizaron además la tesis, `docs/documentacion_tecnica/04_STATISTICAL_METHODS.md`,
`CLAUDE.md` y el inventario de criterios, que describían como vigentes mecanismos
retirados. El documento compila en 154 páginas sin errores ni referencias
indefinidas.

### Cambiado — 7 de agosto de 2026

- **El corte 0,90 de cobertura pasa a ser comunicación descriptiva.**
  `COBERTURA_IC95_ACEPTABLE` encabezaba la escalera de clasificación del
  intervalo, y su texto (`cobertura >= 0,90`) se leía como una regla de
  aprobación. Medido de forma aislada sobre los cincuenta escenarios —separado
  del corte de 0,80, con el que se confundía por el orden de las
  comparaciones—, su efecto propio era **cero**: 0 cambios de estado, 0 de tipo
  de banda y 0 numéricos. La causa está en la propia regla: las dos categorías
  que separaba comparten `degrada_a_escenario=False`, comparten
  `tipo_banda = banda_calculada` y comparten etiqueta visible, de modo que lo
  único que elegía era la redacción.

  La degradación se decide ahora **una sola vez y fuera de la escalera**, con
  el corte de advertencia como único criterio de proporción con efecto. 0,90
  **conserva su valor** —no se sustituye por 0,95 ni por ningún otro corte— y
  queda restringido a elegir si se emite la nota de distancia al nominal.

  Se publica en su lugar una **lectura descriptiva** con las seis magnitudes
  que sostienen la cifra: recuento `x/y`, proporción, nivel nominal declarado,
  distancia en puntos porcentuales, número de errores fuera de muestra del paso
  y método de evaluación. El papel del corte viaja declarado en
  `papel_umbral_aceptacion`, de modo que la salida se puede auditar sin abrir
  el código. Ambos campos llegan a interfaz, CSV, DOCX y PDF.

  **Sin efecto sobre el producto**: 0 estados, 0 tipos de banda, 0 intervalos,
  0 pronósticos, 0 modelos, 0 métricas, 0 cambios de horizonte máximo y 0 de
  calendario sobre los cincuenta escenarios. Los criterios de 16 y 0,80 quedan
  intactos. Blindado en `tests/test_umbral_090_descriptivo.py`.

### Cambiado — 6 de agosto de 2026

- **V-C · Vocabulario neutral del tipo de banda.** El identificador que viajaba
  al CSV, a la interfaz y a los informes usaba `nominal`,
  `admisible_con_advertencia`, `cobertura_insuficiente` y `no_verificable`: tres
  emiten un juicio sobre la cobertura observada y el primero se lee como
  cobertura confirmada del 95 %. Se sustituyen por **`banda_calculada`**,
  **`rango_de_referencia`** y **`banda_no_calculable`**, que describen qué es la
  banda entregada sin afirmar cobertura. La clave con la que se decide sobrevive
  en `clasificacion_interna`, de modo que el criterio aplicado sigue siendo
  auditable. `nominal_95` desaparece como valor de `tipo_banda`. La expresión
  «nivel nominal del 95 %» se conserva calificando el nivel de construcción,
  nunca el resultado. **No cambia ningún estado ni ninguna cifra**: sobre 50
  escenarios, 0 estados y 0 columnas del producto modificadas.
- **G-2 · El estado del horizonte solicitado lo decide su propia evidencia.**
  La magnitud comparada contra los umbrales era el mínimo sobre todos los pasos
  `1..h`, de modo que un paso intermedio con peor cobertura degradaba el
  horizonte pedido; la cobertura del paso entregado se calculaba, se publicaba y
  no intervenía en su propio estado. Ahora deciden `cobertura_h`, `n_h` y la
  validez de la banda de `h`. La cobertura mínima de la trayectoria **se
  conserva, se publica y se localiza** —horizonte y número de contrastes— y
  genera una **advertencia de consistencia entre horizontes** que declara
  expresamente que no invalida el horizonte solicitado. Sobre 50 escenarios
  cambian **3** estados (C-03-h6, C-05-h6 y C-11-h6) y **0** columnas del
  producto. El caso ilustrativo es C-11-h6: cobertura observada 1,000 sobre 21
  contrastes, degradado hasta ahora porque `h=4` cubría 0,762.
  Respaldo: Christoffersen (1998); Diebold y Mariano (1995); Clark y McCracken
  (2013).
- Los tres criterios operativos internos **siguen vigentes y siguen decidiendo**
  (`MIN_ERRORES_COBERTURA_EMPIRICA = 16`, `COBERTURA_IC95_ACEPTABLE = 0,90`,
  `COBERTURA_IC95_ADVERTENCIA = 0,80`), ahora aplicados sobre la cobertura del
  paso solicitado. Retirarlos sin sustituirlos se evaluó y **se descartó**:
  habría promovido 18 horizontes adicionales, seis con cobertura bajo 0,80, y
  habría dado la misma señal a una banda que cubre 0,727 y a otra que cubre
  1,000.
- El CSV reproducible añade `horizonte_minimo_global`,
  `n_errores_horizonte_minimo_global`, `advertencia_consistencia_horizontes` y
  `consecuencia_advertencia_consistencia`.

### Cambiado — 6 de agosto de 2026 (publicación de cobertura con muestra corta)

- **La cobertura observada se publica siempre que se haya medido.** Hasta ahora,
  un paso que no alcanzaba `MIN_ERRORES_COBERTURA_EMPIRICA` publicaba
  `cobertura_observada = None` **aunque su cobertura se hubiera evaluado**: un
  h=12 con 15 errores produce 13 contrastes por origen móvil, de modo que 10/13
  es una medición real. El criterio operativo no sólo gobernaba la decisión,
  además borraba el dato. Sobre los 50 escenarios eran **20 coberturas
  ocultas** —los diez h=12 y los diez h=18—, ahora todas visibles.
- **Medir, publicar y decidir se separan en tres campos.**
  `cobertura_observada` es lo que se midió y se publica siempre;
  `cobertura_apta_para_regla` declara si esa medición puede usarse en la regla
  vigente; `cobertura_minima` sigue siendo la magnitud con la que se decidió y
  queda vacía cuando no se usó ninguna.
- **`limitacion_muestra`**: cuando hay cobertura medida que el criterio no
  admite, se explica con su número de evaluaciones y se nombra el mínimo como
  **criterio operativo vigente**, nunca como requisito estadístico universal,
  garantía, validación científica ni mínimo matemático.
- Excepción deliberada heredada de V-C: con `banda_no_calculable` la cobertura
  **sigue sin publicarse**, porque describiría el procedimiento y no la banda
  entregada, que no existe.
- **0 cambios de estado, de clasificación, de tipo de banda y de las 16 columnas
  del producto** sobre los 50 escenarios. Los tres cortes siguen vigentes y
  **D-1b reformulada sigue sin integrar**.

### Corregido — 6 de agosto de 2026

- **D-Z1 · Una cobertura de 0,000 se informaba como no verificable.**
  `_numero_finito_o_none` devuelve el número, de modo que
  `not _numero_finito_o_none(0.0)` era `True` igual que para `None` o `NaN`:
  Python trata `0.0` como falsy y el código confundía «la banda no cubrió
  ninguna observación» con «no se pudo medir». Un paso con 0 aciertos sobre 24
  contrastes se clasificaba `no_verificable`, publicaba el motivo «n < 16
  errores en el paso exacto solicitado» —falso, con 24 errores— y dejaba
  `cobertura_observada` vacía. Ahora la comprobación es explícita contra `None`
  y una cobertura de 0,000 se clasifica por su valor. Tres puntos corregidos:
  la guarda del clasificador, la normalización previa de la cobertura del paso
  y la publicación de la cobertura mínima global.
- **D-Z2 · El mínimo entre horizontes excluía la cobertura 0,000.**
  `_minimo_entre_horizontes` filtraba las filas por su verdad, de modo que el
  horizonte que no cubría ninguna observación quedaba fuera del cálculo: el
  peor paso desaparecía justo del indicador creado para señalarlo. Ahora se
  incluye 0,000 y se excluye sólo `None`, `NaN` e infinito, conservando el
  horizonte y el número de contrastes del mínimo. La advertencia de
  consistencia de G-2 se emite con normalidad y sigue sin degradar el paso
  solicitado.
- Ambos eran **defectos latentes**: ningún escenario del anexo alcanza
  cobertura 0,000 —la mínima observada es 0,727—, de modo que no corrompían
  ningún resultado publicado. Sobre los 50 escenarios la corrección produce
  **0 cambios** en estados, clasificaciones, etiquetas, advertencias y en las
  16 columnas del producto.

### Añadido — 6 de agosto de 2026

- **Cobertura descriptiva.** La clasificación publica ahora `aciertos`,
  `total_evaluado`, `cobertura_x_y` y `diferencia_pp_frente_nominal`, calculada
  como `100 × (p − 0,95)`. El recuento acompaña siempre a la proporción, porque
  1,000 sobre siete contrastes y 1,000 sobre veintiuno se leen igual sin él. La
  diferencia es **estrictamente descriptiva**: no aprueba, no degrada, no
  bloquea, no clasifica calidad y no sustituye a 0,80 ni a 0,90. Aparece en la
  interfaz, en el CSV reproducible, en el DOCX y en el PDF.
- Los tres criterios operativos internos siguen vigentes y sin modificación
  (16 / 0,90 / 0,80). **D-1b reformulada sigue sin integrar.**

### Corregido

- **RA-01 · Verificabilidad del horizonte exacto.** La clasificación del
  intervalo exigía 16 errores fuera de muestra en *algún* horizonte, no en el
  paso solicitado, de modo que un `h=12` con 15 errores heredaba la
  verificabilidad de `h=1`. Ahora la condición `n >= 16` se evalúa sobre el paso
  exacto que se entrega. El objeto de resultado expone `verificabilidad_paso_exacto`
  con el número de errores del paso, su cobertura cuando es calculable, el estado
  de verificabilidad y la cobertura mínima global como dato separado. No cambian
  la fórmula del intervalo, los pronósticos puntuales ni el modelo seleccionado.
- **RA-03 · Exportación de series bloqueadas.** `grafica_residuos` restaba el
  histórico con un vector de ajuste vacío y rompía DOCX y PDF de toda serie
  bloqueada (`ValueError` de broadcasting). La gráfica se omite de forma
  controlada ante longitudes incompatibles y el informe bloqueado declara
  explícitamente el estado, el motivo, la ausencia de trayectoria futura y la
  ausencia de intervalo, sin inventar valores.
- **RA-02 · Construcción reproducible del ejecutable.** `scripts/build_exe.ps1`
  instalaba `requirements.txt`. Ahora recrea `.venv-build` desde cero, instala
  exclusivamente `requirements-lock.txt` con `--no-deps`, verifica las 32
  versiones con `scripts/verificar_lock.py` y aborta antes de PyInstaller ante
  cualquier diferencia, ausencia o paquete adicional.
- **RA-04 · Mensajes de Ljung–Box.** Los informes atribuían a la distribución la
  ausencia del valor p cuando el diagnóstico no era calculable por muestra corta
  o residuos constantes. Se distingue dependencia disponible, diagnóstico no
  calculable y motivo específico. El cálculo validado no cambia.
- **RA-05 · Coherencia de métricas.** La tabla de modelos evaluados leía claves
  inexistentes (`mae_backtesting`, `rmse_backtesting`, …) y declaraba «no
  disponible» lo que el texto contiguo publicaba. Tabla, texto, CSV, DOCX y PDF
  usan ahora la misma fuente: las métricas del backtesting del modelo.
- **RA-06 · Material de pruebas de terceros.** `packaging/SAVIP.spec` excluye el
  árbol `sklearn/datasets/tests/`, ajeno al código que la aplicación importa.
- **RA-08 · Metadatos del ejecutable.** `README_EJECUTABLE.txt` declaraba
  `0.1.0-beta`; `VERSION.txt` exponía el hostname de compilación. Ambos
  corregidos.
- **H-03 · Coherencia documental.** Se retiró IC80 como salida del producto en
  tesis, guía académica, criterios estadísticos, documentación de módulos,
  evidencia metodológica, ejemplo numérico y salida HTML. ETS deja de figurar
  como modelo implementado. `statsmodels` se describe como dependencia
  obligatoria en versión exacta `0.14.6`, nunca condicional.
- **H-08 · Estimador Huber.** Se documenta la implementación efectiva,
  `sklearn.linear_model.HuberRegressor` con `epsilon=1.35`, `alpha=0.0001` y
  `max_iter=2000`, y se sustituye la referencia a `statsmodels.RLM` por Huber
  (1964) y la documentación de scikit-learn.
- **H-09 · Caso acero.** Se declara la limitación: reproducibilidad matemática
  completa, trazabilidad institucional de los índices y trazabilidad contractual
  pendiente para `P0`, `Ix` y `q`.

### Cambiado

- **Marco teórico.** Las secciones 2.8, 2.9.7 y 2.9.8 se reescribieron como
  contenido estrictamente teórico. «Suavizamiento exponencial ETS y razón de su
  exclusión» pasa a «Suavizamiento exponencial ETS» y «Combinación de pronósticos
  y razón de su exclusión» a «Combinación de pronósticos». Las decisiones de
  alcance se trasladaron al capítulo de pruebas, en la nueva subsección
  «Evaluación de modelos y justificación de exclusiones».
- Versión alineada a `0.3.0-rc3` en `VERSION`, `packaging/version_info.txt`,
  `README_EJECUTABLE.txt` y el nombre de la carpeta del ejecutable temporal.

### Añadido

- `tests/test_verificabilidad_paso_exacto.py`: 13 pruebas de la regla del paso
  exacto, incluidos los cuatro casos señalados por la reauditoría.
- `tests/test_informes_serie_bloqueada.py`: 11 pruebas de exportación de series
  bloqueadas y de coherencia de métricas entre secciones.
- `tests/test_mensajes_ljung_box.py`: 8 pruebas de los mensajes causales del
  diagnóstico.
- `scripts/verificar_lock.py`: verificación del entorno contra el lock.

---

## [0.3.0-rc2] — 29 de julio de 2026

Versión candidata para reauditoría. Aplica las correcciones derivadas de la
auditoría estadística, técnica y documental independiente, que emitió un
veredicto de **no aprobado** con 15 hallazgos.

**No cambia ningún pronóstico ni ningún límite de intervalo.** Sobre los 50
escenarios de la línea base (20 series reales, horizontes de 1, 3, 6, 12 y 18
meses): 0 cambios en modelo seleccionado, pronóstico puntual, límites del
intervalo del 95 %, horizonte recomendado, horizonte admisible y patrón
calendario. Los 9 cambios de estado del horizonte están justificados uno por uno
en `docs/remediacion_auditoria/COMPARACION_ANTES_DESPUES.csv`.

### Corregido

- **`statsmodels` pasa a dependencia obligatoria**, fijada a `0.14.6`. Antes su
  presencia opcional cambiaba el modelo y la cifra sin avisar: el mismo dato daba
  resultados distintos según el entorno. Holt conserva sus coeficientes fijos
  (α=0,65; β=0,20; φ=0,88) y ya no consulta la biblioteca. Ljung–Box se calcula
  siempre, con rezagos y grados de libertad declarados.
- **Jarque–Bera** normalizaba con `std(ddof=1)` en lugar de momentos centrales de
  divisor n. El estadístico corregido coincide con `scipy.stats.jarque_bera`
  dentro de 2,4·10⁻¹⁶. En un caso documentado con n=26 la decisión al 5 % se
  invierte respecto de la implementación anterior.
- **El CSV reproducible exponía `q80`** pese al retiro declarado de la banda del
  80 %. Ninguna columna del CSV menciona ya el 80 %.
- **Metadatos del ejecutable de Windows** (`packaging/version_info.txt`) seguían
  en `0.1.0-beta`, dos versiones por detrás de `VERSION`, pese a que el propio
  archivo exige mantenerlos sincronizados.
- **Una prueba cambiaba de resultado** según existiera un CSV residual en disco.
  Ahora usa dos fixtures versionados y hay una comprobación de hermeticidad.
- **Finales de línea**: `.gitattributes` cubre ahora todos los tipos de texto del
  repositorio. `git diff --check` termina sin hallazgos.

### Añadido

- **Clasificación del intervalo del 95 % según su cobertura empírica medida**
  (decisión autorizada, hallazgo H-05). El cálculo numérico no cambia: cambia lo
  que el sistema afirma sobre la banda y hasta dónde permite usarla. Cuatro
  estados: cobertura no verificable, nominal, admisible con advertencia y
  cobertura insuficiente. Los umbrales (0,90 y 0,80) se declaran como criterios
  operativos internos, no como reglas estadísticas universales, y su sensibilidad
  está medida en `docs/remediacion_auditoria/SENSIBILIDAD_UMBRALES_COBERTURA.md`.
- **Separación entre patrón calendario detectado en la serie y efecto dentro del
  horizonte solicitado** (decisión autorizada, hallazgo H-10). El patrón es una
  propiedad de la serie; el efecto existe solo si algún paso cae en enero. Se
  comunican por separado en interfaz, informes y CSV.
- **Matriz de referencias y manifiesto de fuentes externas**
  (`docs/referencias/`), con DOI o URL, ubicación consultada, estado de acceso y
  SHA-256 del artefacto revisado. El manifiesto registra el hash, no el
  artefacto: la biblioteca de terceros no se versiona.
- Verificación de dependencias obligatorias antes de cualquier cálculo
  (`app_icociv/config/dependencias.py`); la aplicación falla con mensaje
  explícito en lugar de degradarse en silencio.
- Suite nueva `tests/test_calendario_y_clasificacion_intervalo.py` (14
  comprobaciones). El total pasa a 28 suites, aprobadas en dos ejecuciones
  consecutivas.

### Declarado como limitación

- La cobertura del intervalo es **nominal, no garantizada**. La medida varía
  entre series: de 0,375 a 1,000 en la muestra de referencia.
- Cuando se aplica el ajuste de cambio de año, **la incertidumbre de gamma no
  está incorporada al intervalo**, que mide el error del modelo base.
- Las series que no reúnen 16 errores fuera de muestra conservan la clasificación
  de escenario: se entrega el pronóstico puntual, pero la cobertura de la banda
  no es verificable. No hay excepción para series cortas.
- El sistema **no se declara aprobado**. Esta versión se entrega para
  reauditoría.

---

## [0.2.0-beta] — 26 de julio de 2026

Correcciones estadísticas derivadas de la auditoría independiente y de la
validación previa al empaquetado. Cambian resultados numéricos respecto de
`0.1.0-beta`: los intervalos son más amplios, algunas series antes bloqueadas ahora
proyectan y las proyecciones de series con patrón de cambio de año se ajustan en
todos los horizontes.

### Corregido

- **Jarque–Bera**: el valor-p se evaluaba contra una chi-cuadrado con cuatro grados
  de libertad, `exp(-JB/2)·(1+JB/2)`, lo que sobreestimaba el resultado entre dos y
  once veces. Ahora usa la cola exacta de chi-cuadrado con dos grados de libertad,
  `exp(-JB/2)`. Con menos de ocho residuos, o dispersión nula, se reporta como no
  calculable en lugar de devolver `p=1`.
- **Bloqueo en cascada**: el fallo del modelo principal en `h=1` anulaba toda la
  serie. Se añadió una salvaguarda conservadora que reevalúa Drift y Naive con los
  mismos umbrales antes de bloquear, y adopta el benchmark para toda la trayectoria
  si amplía el horizonte admisible. La serie del insumo Arena pasó de horizonte
  máximo 0 a 24 meses admisibles.
- **Intervalos de predicción**: se reconstruyeron con los errores fuera de muestra
  del horizonte exacto de cada paso, sin reescalar errores de otro horizonte. Se
  eliminó la banda fabricada de escala mínima (±2,77 %) que se emitía sin respaldo.
  La cobertura empírica se verifica por partición temporal y se reporta; antes se
  declaraba un 95 % nominal cuya cobertura real era del 73 % al 92 %.
- **Ajuste de cambio de año**: se aplicaba o no según si el horizonte *total*
  cruzaba un enero, de modo que la proyección de un mismo mes cambiaba al pedir 3 o
  12 meses. Ahora el factor se evalúa por paso y la decisión de aplicarlo depende
  solo de la serie y del modelo. Los meses comunes coinciden exactamente en
  solicitudes de 3, 6, 12 y 18 meses.
- **Explicación de la selección de modelos**: atribuía la decisión a AICc, R²
  ajustado y Durbin–Watson, que no intervienen. El texto describe ahora el criterio
  real: RMSE de validación temporal relativo al mejor modelo de cada horizonte,
  ponderado por 1/h.

### Cambiado

- **ETS retirado del catálogo.** Sin `statsmodels` reproducía exactamente la
  trayectoria de Holt amortiguado, de modo que no aportaba una alternativa
  independiente. El catálogo pasó de 13 a 12 modelos. Queda como trabajo futuro.
- **Banda del 80 % retirada de todas las salidas al usuario.** Su cobertura medida
  fue de 0,77 de media y 0,55 en el peor caso. La aplicación muestra únicamente el
  intervalo de predicción del 95 %; el cálculo del 80 % permanece como diagnóstico
  interno.
- **Terminología**: «intervalo de confianza» pasó a «intervalo de predicción» en
  interfaz, gráficas e informes, por tratarse de la cobertura de una observación
  futura y no de un parámetro.
- **Valores atípicos**: las detecciones de las tres escalas se consolidan en una
  alerta por periodo y se clasifican como patrón calendario, posible error de datos,
  posible cambio de nivel o atípico aislado. Los eneros del patrón confirmado dejan
  de contarse como anomalías. Ningún valor se elimina, interpola ni suaviza.
- **Coeficientes de Holt** declarados como parámetros internos fijos (criterio
  auditable `C-MOD-002`), con su análisis de sensibilidad documentado.

### Agregado

- Reporte de cobertura empírica del intervalo por horizonte, con advertencia
  automática cuando la cobertura observada cae por debajo del 90 %.
- Trazabilidad de la salvaguarda con benchmarks en interfaz e informes.
- `scipy` como dependencia declarada, para los cuantiles t de los intervalos.
- Pruebas nuevas: `test_jarque_bera.py`, `test_intervalos_prediccion.py`,
  `test_salvaguarda_benchmarks.py`, `test_atipicos_calendario.py` y
  `test_consistencia_trayectoria.py`.

### Nota metodológica

El procedimiento de intervalos toma el máximo entre un cuantil empírico con
corrección de muestra finita y la predicción t de Student. **No se reclama la
garantía de cobertura de la predicción conformal**: esa garantía exige
intercambiabilidad de los errores, supuesto que la validación temporal no cumple. El
método se sostiene en la verificación empírica de cobertura, que la aplicación mide y
reporta por serie y horizonte.

---

## [0.1.0-beta] — 23 de julio de 2026

Primera distribución ejecutable para Windows, destinada a validación interna.

### Agregado

- Empaquetado con PyInstaller en modalidad `onedir`, con especificación
  versionada en `packaging/SAVIP.spec` y metadatos de Windows en
  `packaging/version_info.txt`.
- Scripts de compilación reproducible: `scripts/build_exe.ps1`,
  `scripts/build_exe.bat`, `scripts/clean_build.ps1` y
  `scripts/package_release.ps1`.
- Entorno virtual dedicado de compilación (`.venv-build`) creado por el script,
  de modo que el ejecutable solo incluya las dependencias declaradas.
- Módulo centralizado de rutas (`app_icociv/config/rutas.py`) que distingue
  recursos internos de solo lectura, datos del usuario y registros.
- Registro de ejecución en archivo con captura de excepciones no controladas
  (`app_icociv/config/registro.py`), en `%LOCALAPPDATA%\SAVIP\logs`.
- Modo de autocomprobación sin interfaz (`SAVIP.exe --autocomprobacion`) que
  ejercita recursos, datos ICCP, empalme, proyección, exportables y escritura
  externa; lo usa el script de compilación como verificación posterior.
- Menú **Ayuda** con «Acerca de SAVIP» (versión y ubicaciones de trabajo) y
  «Abrir carpeta de registros».
- Archivo `VERSION` como fuente única de versión, mostrada en la barra de
  título y en el diálogo «Acerca de».
- `requirements-build.txt` con las dependencias exclusivas de compilación.
- `README_EJECUTABLE.txt` para el usuario final de la distribución.
- Guía de compilación en `docs/documentacion_tecnica/EXE_BUILD_GUIDE.md`.

### Cambiado

- Los reportes, exportables y sesiones ya no se sugieren dentro del directorio
  del programa. Cuando la aplicación corre empaquetada usan
  `Documentos\SAVIP`, que es escribible y sobrevive a una reinstalación.
- Los recursos internos (`iccp_historico.json`, `estilo.qss`) se resuelven con
  `ruta_recurso()` en lugar de `__file__`, para que funcionen empaquetados.

### Conocido

- La distribución ocupa unos 284 MB por las dependencias de PySide6, pandas,
  matplotlib, scikit-learn y scipy. Es el tamaño esperado para una aplicación
  científica de escritorio con Qt.
- El ejecutable no está firmado digitalmente: Windows SmartScreen y algunos
  antivirus pueden advertir sobre él en el primer arranque.
- La distribución no incluye ningún icono propio; se usa el icono por defecto
  de PyInstaller. Falta definir un icono institucional autorizado.
- La prueba en un equipo Windows completamente limpio (sin Python ni entorno de
  desarrollo) está pendiente de ejecución por parte del responsable; la lista de
  comprobación está en `docs/documentacion_tecnica/EXE_BUILD_GUIDE.md`.

### Pendiente

- Icono `.ico` institucional autorizado.
- Firma digital de código e instalador firmado.
- Instalador con Inno Setup o NSIS, una vez validada la distribución en carpeta.
- Flujo opcional de compilación en GitHub Actions (`workflow_dispatch`).

---

## Cómo publicar una nueva versión

1. Modificar el código fuente.
2. Ejecutar las pruebas (`tests/` y `pruebas/`).
3. Actualizar el archivo `VERSION`.
4. Actualizar los números de `packaging/version_info.txt`.
5. Añadir la entrada correspondiente en este archivo.
6. Ejecutar `.\scripts\build_exe.ps1`.
7. Probar la distribución generada.
8. Ejecutar `.\scripts\package_release.ps1` para el ZIP y su checksum.

El procedimiento completo está en `docs/documentacion_tecnica/EXE_BUILD_GUIDE.md`.
