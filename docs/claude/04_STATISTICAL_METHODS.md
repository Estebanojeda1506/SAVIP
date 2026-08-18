# Métodos estadísticos implementados

Anexo de referencia: `documentacion_latex/criterios_estadisticos_aplicacion/` documenta cada criterio con fórmula numerada, fuente verificable, implementacion y prueba; su tabla se genera desde `criterios.py` (regenerar con genera_tabla_criterios.py de esa carpeta si cambia la matriz). Las fórmulas estan protegidas por `tests/test_auditoria_formulas_estadisticas.py` (valores calculados a mano y comprobación de que no hay fuga).

Fuente principal: `app_icociv/estadistica/`, `app_icociv/validacion/backtesting.py` y `app_icociv/proyeccion/servicio_proyeccion.py`. Los umbrales están centralizados en `criterios.py`; allí se distingue entre criterio bibliográfico, estándar, computacional y operativo interno.

## 1. Preparación y validación

`normalizar_serie_mensual` y las funciones de validación convierten periodos a una secuencia mensual ordenada y revisan:

- periodos no reconocibles y discontinuidad temporal;
- duplicados;
- valores faltantes o no numéricos;
- índices no positivos;
- longitud de la serie.

**Actualizado el 16 de agosto de 2026 (P0-B).** El corte de 8 observaciones dejó de negar la proyección: era un literal sin fuente que vetaba el punto, no una imposibilidad de cálculo. Hoy solo un error crítico de los datos —o una serie vacía— impide modelar. Por debajo de 18 observaciones se advierte y se recomiendan al menos 24, pero ambas cifras son **orientativas y se comunican**, no deciden. Las advertencias permanecen en la trazabilidad.

## 2. Descriptivos y variables derivadas

`calcular_variables_derivadas` produce estadísticos de nivel y cambios mensuales/acumulados. La detección robusta de atípicos usa mediana y MAD con z modificado, cuyo umbral central es 3,5. Los atípicos se informan; no se sustituyen automáticamente.

## 3. Modelos y benchmarks reales

`MODELOS_INTERPRETABLES` registra:

- regresión lineal;
- regresión logarítmica temporal y exponencial/log-lineal;
- regresión robusta Huber;
- Holt lineal y Holt amortiguado;
- modelos sobre variación mensual y log-variación;
- naive, drift, promedio móvil y variación reciente.

Los cuatro últimos funcionan como benchmarks, aunque el promedio móvil también se presenta como contraste descriptivo. `servicio_proyeccion.py` activa candidatos progresivamente:

- nivel 1: naive, drift, Holt lineal y Holt amortiguado;
- nivel 2: logarítmico, exponencial/log-lineal, variación, log-variación y Huber;
El esquema progresivo tiene dos niveles; el nivel 3 fue eliminado el 19 de julio de 2026 junto con el modelo polinómico de grado 2 (era inalcanzable por guards contradictorios).

La activación depende de longitud, horizonte y diagnóstico; no todos los candidatos se ajustan en toda serie. Los errores de ajuste quedan como razones de descarte.

### Estado de ARIMA

ARIMA fue retirado del alcance del proyecto el 19 de julio de 2026: se eliminó de `modelos_interpretables.py`, `criterios.py`, `servicio_proyeccion.py`, reportes, interfaz, pruebas, del documento LaTeX final y de todas las carpetas históricas de documentación. No debe reintroducirse como candidato. `statsmodels` es dependencia obligatoria desde el 28 de julio de 2026, fijada a la versión 0.14.6, y se usa **solo** para el diagnóstico Ljung–Box. Holt no la consulta: sus coeficientes son fijos y declarados.

### Combinación de pronósticos: retirada (23 de julio de 2026)

El ensamble ponderado por RMSE fue eliminado del código, los reportes, la interfaz, el documento LaTeX y `criterios.py` (criterio `C-ENS-001` y constantes `UMBRAL_*_ENSAMBLE`, `PENALIZACION_ENSAMBLE_*`). La decisión se tomó con evidencia: sobre 40 series y 720 comparaciones, midiendo sin fuga (pesos calibrados en la primera mitad de los orígenes walk-forward, evaluación en la segunda), la variante de pesos fijos por serie —única compatible con la trayectoria consistente— ganó en 312 de 720 casos y empeoró el RMSE un 9,1 % en promedio. La mejora aparente del 13,4 % que mostraba la medición ingenua provenía de calibrar los pesos sobre los mismos errores con que luego se evaluaban. No reintroducir sin una medición equivalente.

### Ajuste de cambio de año

`app_icociv/estadistica/calendario_anual.py` detecta el salto recurrente de diciembre a enero con estadística robusta y **publica su perfil** (`gamma`, ratio, consistencia de signo y número de transiciones). **Desde el 12 de agosto de 2026 (P0-F) el tratamiento NO se aplica al pronóstico**: `_ajustar_salto_anual` fija `aplicado = False` de forma incondicional. Ningún componente del método tenía sustento completo —`gamma` como estimador del salto futuro, la forma `f_j = exp(gamma·(n_j − j/12))` cuyo término `−j/12` es falso para `naive`, y las puertas `≥2`, `>1,5` y `≥0,6`, calibradas sobre el propio anexo de aplicación, lo que la constitución del proyecto prohíbe—. El fenómeno está medido y es contundente; lo que falta es un método publicado para tratarlo, y **no se introdujo reemplazo**. Detalle completo en [`ANNUAL_JUMP_ADJUSTMENT.md`](ANNUAL_JUMP_ADJUSTMENT.md).

## 4. Backtesting walk-forward

`ejecutar_backtesting` usa ventana expansiva. Para cada origen:

1. toma solo la historia disponible hasta el corte;
2. reestima el modelo;
3. pronostica el horizonte objetivo;
4. compara con la observación real correspondiente.

**P0-E, 12 de agosto de 2026; estado E3, limitación abierta.** El primer origen vigente es `N₀ = max_m N_min(m)` sobre los candidatos que compiten, con el mínimo de cada modelo derivado de su formulación (`OBSERVACIONES_MINIMAS_MODELO`). Con el catálogo actual el binding es Holt amortiguado —cinco parámetros, luego seis observaciones para **estimarlos**—, de modo que **N₀ = 6 es el valor provisional actualmente implementado**. No es un valor cerrado, derivado ni identificado: lo que se deriva son las dos **cotas** —`N₀ ≥ max_m N_min(m)` por comparabilidad y `N₀ ≤ n − 1` por disponibilidad—, y entre ellas las fuentes no eligen. **La elección del primer origen permanece como limitación metodológica declarada**, porque el valor decide el modelo entregado: 6 de 10 series cambian de ganador según `N₀`, y 11 de 59 combinaciones `N₀`-serie. Esa sensibilidad se publica y **no** se usa para escoger `N₀`. `C-WF-002` sigue en `pendiente_de_decision` y el resultado viaja con `evidencia_oos_provisional = True`. `ejecutar_backtesting_comparativo` lo calcula **una sola vez** y lo pasa explícito a cada ejecución: no hay origen por modelo.

Sustituye a `max(18, 0,60 × n)`, dos literales sin fuente que la tabla de criterios atribuía además a Hyndman y Athanasopoulos. Verificado contra el original: FPP3 §5.10 —el procedimiento aplicado— **no da ninguna proporción**, y la única del libro (§5.8, «about 20 %» de conjunto de **prueba** para una partición única, es decir 80 % de entrenamiento) pertenece a otro procedimiento y no es 60 %.

Con las series de 65 observaciones del anexo quedan `n_h = 60 − h` ventanas: 59 en h=1, 54 en h=6, 48 en h=12, 42 en h=18 y 36 en h=24. **Limitación declarada:** FPP3 §5.10 excluye las primeras observaciones «since it is not possible to obtain a reliable forecast based on a small training set», pero no operacionaliza «pequeño» y esta derivación tampoco; los primeros orígenes pronostican desde ventanas cortas y sus errores, ahora, se miden en vez de quedar fuera.

### Niveles de evidencia por horizonte (19 de julio de 2026)

El número de orígenes disponibles para un horizonte `h` es `n − entrenamiento_inicial − h + 1`. Se distinguen cuatro tramos, porque *no poder medir* no equivale a *haber medido mal*; solo el último niega, y niega por aritmética:

- **≥ 6 ventanas**: la evidencia se considera estable. Es una lectura **descriptiva**; ya no certifica ni promueve.
- **3 a 5 ventanas**: evidencia reducida. Se informa el recuento; el horizonte **no** se degrada por ello.
- **1 o 2 ventanas**: evidencia mínima. Se advierte que el intervalo no es construible ni evaluable, y **el pronóstico puntual se entrega igualmente**.
- **0 ventanas** (`h > n − N₀`): el horizonte no se evalúa, porque no existe ningún error fuera de muestra. Es la **cota de existencia** del dato, no un umbral elegido.

**Actualizado el 16 de agosto de 2026 (P0-G).** Los tres niveles anteriores (`≥6` certificaba, `3–5` degradaba a escenario, `<3` negaba) **dejaron de decidir**: ninguna fuente autoriza que un recuento de ventanas cancele un pronóstico puntual, y el corte de 3 procedía de un requisito de la **banda** —poder estimar su dispersión— que recortaba los horizontes en que se entrega el **punto**. Los umbrales de error (MAPE 25 %, sMAPE 30 %, errores extremos 50 %, rRMSE 1,25) también se retiraron como vetos y se publican con su valor. Lo único que sigue negando un horizonte es que el punto no sea finito o que `h > n − N₀`. Cubierto por `tests/test_horizonte_evidencia_reducida.py` y `tests/test_post_codex_bghc.py`.

## 5. Métricas y selección

Las métricas disponibles son MAE, RMSE, MAPE, sMAPE, MASE, sesgo medio, R², R² ajustado, AIC y AICc. MASE usa una escala naive dentro de cada origen cuando corresponde. La selección combina error fuera de muestra, comparación con benchmarks, parsimonia, estabilidad, sesgo y diagnóstico residual; no se basa solo en el ajuste dentro de muestra.

## 6. Diagnóstico residual

Se calculan Durbin–Watson, ACF, PACF, media residual y un contraste básico de heterocedasticidad. Ljung–Box se calcula siempre, con `statsmodels` 0.14.6, un rezago igual a `min(10, n/4, n-2)` y `model_df=0`. Con menos de 12 residuos o con residuos constantes se declara «no calculable». Es diagnóstico: no bloquea por sí solo una proyección ni cambia el modelo, el pronóstico o el intervalo. Los diagnósticos alimentan advertencias y penalizaciones, no una corrección silenciosa de datos.

## 7. Intervalo de predicción del 95 % — **retirado de las salidas (P0-C)**

**Desde agosto de 2026 el intervalo no se publica.** No aparece en la interfaz, el CSV, el DOCX, el PDF, el HTML ni la tesis, y el objeto que devuelve `ejecutar_proyeccion` no lo contiene: ni los límites, ni los componentes que permitirían reconstruirlos (`sigma_h`, cuantiles, anchos relativos, método), ni la cobertura empírica. El motivo es que la **construcción completa** carece de sustento verificable: el centrado por la media de la propia calibración, la imposición de amplitud no decreciente y el recorte en cero no tienen fuente que los respalde en conjunto, aunque cada pieza por separado sea reconocible.

Lo que se conserva como **diagnóstico interno**, sin llegar a ninguna salida: para cada paso se toman los errores fuera de muestra del **horizonte exactamente igual a ese paso**, sin reescalar errores de otro horizonte, y se centran por su media; el semiancho es el **máximo** entre un cuantil de orden empírico con corrección de muestra finita y la predicción t de Student.

La banda del 80 % ya se había retirado el 26 de julio de 2026 por cobertura medida de 0,77 media y 0,55 mínima. Con P0-C, **ninguna de las dos bandas se publica**.

**El ancho relativo ya no participa en la clasificación de horizonte** (P0-G): sus nueve cortes eran literales internos sin fuente y con cero activaciones sobre el anexo de referencia. Se calcula y se advierte cuando es alto; no veta ni degrada.

**Cobertura.** Se sigue midiendo internamente por partición temporal, pero **no se publica** y **no decide nada**. La cobertura medida varía entre series: en la muestra de referencia va de 0,375 a 1,000, heterogeneidad que —unida a la ausencia de una construcción completa sustentada— motivó retirar la banda en lugar de acompañarla de advertencias. Nunca se reclamó la garantía del método conformal: exige intercambiabilidad, que los errores walk-forward no cumplen. Ver `docs/remediacion_auditoria/DECISION_INTERVALO_95.md`.

El módulo `modelos/regresion.py` y los parámetros bootstrap vestigiales fueron eliminados el 19 de julio de 2026 por no participar del flujo activo.

## 8. Horizonte viable y bloqueos

La interfaz ofrece 1, 3, 6, 12, 18 o un valor personalizado hasta 60 meses. El valor 18 no es un límite estadístico fijo. El servicio evalúa cada horizonte **por su propia evidencia** y devuelve:

- máximo recomendado;
- máximo permitido como escenario;
- máximo admisible/evaluado;
- primer horizonte no viable y tipo de parada;
- estado, razones y advertencias para el horizonte solicitado.

**Actualizado el 16 de agosto de 2026 (P0-H).** Los horizontes válidos **ya no tienen que formar un prefijo consecutivo**: si `h=2` falla y `h=3` y `h=4` se sostienen, se publican `h=3` y `h=4`, y el hueco se informa (`primer_horizonte_no_viable`) sin que `h=2` deje de estar marcado como no permitido. Ninguna fuente exige la contigüidad. Lo que no ocurre en ningún caso es fabricar un valor: si el punto no es finito o `h > n − N₀`, no se genera proyección.

## 9. Exportación y relación documental

El resultado estructurado alimenta el panel, la serie, gráfica, fila fuente, explicaciones y los exportables PDF/DOCX/HTML/CSV. `reportes/generador_reportes.py` presenta la información; la lógica estadística permanece en los servicios.

El documento final `documentacion_latex/documento_tecnico_icociv_iccp/main.tex` describe estos métodos. El soporte preliminar está en `documentacion_latex/guia_academica_estadistica/`. Cualquier cambio metodológico debe contrastarse con ambos y con la matriz `docs/auditoria_criterios_estadisticos.md`.


### Estado de ETS: retirado (26 de julio de 2026)

ETS fue retirado del catálogo tras verificar que `_ajustar_ets`
devolvía exactamente la trayectoria de Holt amortiguado: no era un modelo
independiente sino un duplicado que inflaba el número de candidatos comparados. Se
eliminó de `MODELOS_INTERPRETABLES`, `MODELOS_SERIE_TEMPORAL`, el despachador,
`MODELOS_NIVEL_2`, `CATALOGO_MODELOS_CANDIDATOS`, los textos de reportes y el
documento LaTeX. El catálogo pasó de 13 a 12 modelos. No reintroducir sin una
implementación con estimación real de los parámetros de espacio de estados y
evidencia de que mejora a Holt amortiguado fuera de muestra.

### Intervalos de predicción recalibrados (26 de julio de 2026)

`_intervalos_prediccion` recibe ahora `errores_por_horizonte`: cada paso `p` usa los
errores walk-forward del horizonte exactamente `p`, sin reescalar con `sqrt(p/h)`. El
semiancho es el **máximo entre un cuantil de orden con corrección de muestra finita**
(índice `k = ceil((n+1)(1-alpha))`, el mismo que usa el conformal split) **y la
predicción t de Student** `t * s * sqrt(1+1/n)`, ambos centrados en la media del error
para que un sesgo sistemático desplace la banda. **No se reclama la garantía conformal**:
exige intercambiabilidad, que los errores walk-forward no cumplen (orígenes con historia
compartida, modelo reestimado, varianza cambiante) y además el centrado usa la media de
la propia calibración. Es un criterio conservador validado empíricamente. Con `n < 19`
ningún dato alcanza la cola del 95 % y domina el respaldo t, con advertencia explícita. La amplitud se fuerza no decreciente con el
paso y el límite inferior se recorta en 0. Se eliminó la banda fabricada de «escala
mínima» (±2,77 %): un paso sin al menos 3 errores del horizonte no produce intervalo.

`_cobertura_empirica_intervalos` verifica la cobertura por partición temporal
(calibración/prueba 50/50, mínimo 16 errores) y el resultado se reporta en interfaz y
reportes. El método anterior alcanzaba 73–92 % de cobertura frente al 95 % nominal;
el actual alcanza 92–100 % en la serie agregada. Los umbrales **no** se calibran
contra la muestra de prueba: hacerlo invalidaría la verificación.

### Salvaguarda conservadora con benchmarks (26 de julio de 2026)

`_aplicar_salvaguarda_benchmarks` corrige el bloqueo en cascada. Si el modelo único de
la serie produce un horizonte no viable por causas del modelo (no por falta de
ventanas: `bloqueo_por_datos` lo distingue), se reevalúan Drift y Naive con los mismos
umbrales, ordenados por su RMSE relativo ponderado 1/h. El primero que amplíe el
horizonte admisible sustituye al principal en **toda** la trayectoria. El bloqueo solo
persiste si ninguna alternativa cumple. La trazabilidad va en
`resultado["salvaguarda_benchmark"]`.

### Clasificación de atípicos y patrón calendario (26 de julio de 2026)

`detectar_valores_atipicos_mad` consolida las detecciones de las tres escalas en una
alerta por periodo (`escalas_detectadas` conserva cuáles la señalaron) y clasifica en
`patron_calendario`, `posible_error_datos`, `posible_cambio_nivel` o
`posible_atipico_aislado`. Los eneros del patrón confirmado no cuentan como atípicos
en `evaluar_calidad_datos` ni en la factibilidad. Ningún valor se elimina, interpola
ni suaviza. Los umbrales del módulo de salto anual no cambiaron. Criterio auditable
nuevo: `C-ATI-003`.

### Retiro del intervalo del 80 % (26 de julio de 2026)

La verificación de cobertura sobre 8 series y 24 combinaciones midió para la banda
nominal del 80 % una cobertura media de 0,77 con mínimo de 0,55. Por el mismo criterio
que motivó la recalibración del 95 %, se retiró de interfaz, gráficas, informes,
exportaciones (CSV reproducible) y tesis. `_cuantiles_intervalo` y
`_intervalos_prediccion` siguen calculando `lo80`/`hi80` como **diagnóstico interno**
—los usa `_cobertura_empirica_intervalos`— pero ninguna salida al usuario los expone.
El intervalo de predicción del 95 % pasó entonces a ser la única banda visible. **Superado el 16 de agosto de 2026 (P0-C): tampoco el 95 % se publica.** Ver la sección 7.

### Ajuste calendario independiente del horizonte solicitado (26 de julio de 2026)

La validación previa al empaquetado detectó que la proyección de un mismo mes cambiaba
según el horizonte pedido: `_ajustar_salto_anual` condicionaba la activación a que el
horizonte **total** cruzara un enero (`cruza_enero`), pero al activarse aplicaba el
factor a **todos** los pasos. Con último dato en mayo de 2026, pedir 6 meses daba
148,6051 para junio y pedir 12 daba 148,4663.

Corrección aplicada entonces: se eliminó esa condición. **Superado el 12 de agosto de 2026 (P0-F): el ajuste ya no se aplica en absoluto**, de modo que la independencia respecto del horizonte solicitado es hoy trivialmente cierta. Se conserva el registro porque explica por qué el perfil se sigue midiendo por paso. El factor
`f_j = exp(gamma * (n_j - j/12))` se evalúa por paso con su propio `n_j`, y la decisión
de aplicar depende solo de que el patrón esté confirmado y de que la validación
retrospectiva lo respalde. Esa validación se agrega ahora sobre
`HORIZONTES_VALIDACION_CALENDARIO = (1, 3, 6)`, fijos, para que la decisión sea
propiedad de la serie y del modelo y no del horizonte solicitado. La firma pasó a
`_ajustar_salto_anual(serie, y_futuro, backtesting_comparativo, modelo_codigo, horizonte)`.

Los umbrales del módulo de salto anual (`MIN_TRANSICIONES_SALTO_ANUAL`,
`RATIO_SALTO_ANUAL`, `CONSISTENCIA_SIGNO_SALTO_ANUAL`,
`TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO`) **no cambiaron**. Verificación en
`tests/test_consistencia_trayectoria.py`: los meses comunes coinciden dentro de 1e-9 al
pedir 3, 6, 12 y 18 meses, en series sintéticas con y sin patrón y en series reales de
cuatro niveles de agregación.

### Alcance académico realista: qué puede y qué no puede decidir la aplicación (16 de agosto de 2026)

La revisión independiente de agosto de 2026 cerró con una regla de la que se derivan
todos los cambios anteriores de esta lista:

> Cada decisión, criterio, umbral, bloqueo, reducción de horizonte, selección,
> tratamiento, transformación o regla **que afecte el resultado** debe estar
> respaldada por literatura verificable, por una estimación sustentada o por una
> derivación matemática válida.

Esto **no** significa que la aplicación deba proyectar siempre. Un bloqueo sustentado
es legítimo y debe conservarse. Las categorías de bloqueo válidas son cuatro:

1. **Imposibilidad matemática** — el pronóstico puntual no es un número finito.
2. **Inexistencia del dato** — `h > n − N₀`: no hay ninguna ventana de validación, luego
   no hay error fuera de muestra que medir.
3. **Error crítico de los datos de entrada** — periodos irreconocibles, serie vacía,
   índices no positivos.
4. **Limitación de alcance declarada** — el proyecto no implementa el método; se declara
   y no se sustituye por una heurística inventada.

Todo corte que no encaje en una de las cuatro se retiró y su magnitud se **publica**
en lugar de decidir. La consecuencia práctica, medida sobre los escenarios de
verificación, es que la aplicación entrega resultados en más casos y que en cada caso
declara con qué evidencia cuenta. Ninguna cifra cambió por esta retirada: los puntos y
las métricas de los horizontes promovidos son exactamente los que ya se calculaban.

Lo que queda **declarado como limitación**, no resuelto:

- el intervalo de predicción, cuya construcción completa no tiene sustento verificable;
- el tratamiento del salto de cambio de año, medido pero sin método publicado que aplicar;
- el primer origen de la validación temporal, que FPP3 §5.10 deja sin una regla cerrada.
