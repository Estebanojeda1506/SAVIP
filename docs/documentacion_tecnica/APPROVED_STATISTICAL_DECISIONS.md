# Decisiones estadísticas aprobadas por el usuario — 25 de julio de 2026

Estas decisiones son **instrucciones obligatorias** para la fase de implementación.
Responden a las seis preguntas de `AUDITORIA_ESTADISTICA_INTEGRAL_OPUS5.md` §14 y
**reemplazan cualquier duda pendiente de la auditoría**. No reinterpretar.

---

## D-1. Retiro de ETS

Retirar ETS del catálogo de modelos implementados. Sin `statsmodels`, ETS genera
exactamente la misma trayectoria que Holt amortiguado (diferencia verificada: 0.0).

- Eliminar ETS de la comparación de modelos.
- Eliminarlo de tablas, reportes, interfaz y resultados.
- Corregir la tesis para que no se presente como modelo evaluado.
- Conservarlo únicamente como posible trabajo futuro, si resulta pertinente.
- **No instalar `statsmodels` en esta fase** solo para conservar ETS.
- Revisar por separado la justificación de los parámetros fijos de Holt amortiguado.

## D-2. Intervalo de predicción obligatorio del 95 %

El intervalo de predicción nominal del 95 % es obligatorio. No conservar bandas que
se llamen «95 %» si su cobertura empírica está claramente por debajo.

- Recalcular los intervalos usando errores fuera de muestra **correspondientes a cada
  horizonte**.
- Calibrar el procedimiento para aproximar la cobertura empírica al 95 % nominal.
- Aceptar que los intervalos se ensanchen cuando sea necesario.
- Permitir que horizontes cambien de categoría si aumenta la incertidumbre.
- **Informar la cobertura empírica observada.**
- Usar la expresión «intervalo de predicción del 95 %»; eliminar «intervalo de
  confianza» cuando se refiera a observaciones futuras.
- Eliminar o corregir bandas fijas sin respaldo estadístico (incluida la banda
  mínima fabricada de ±2,77 %).
- Revisar que la amplitud tenga comportamiento coherente con el horizonte.
- Mantener el 95 % como intervalo principal de la aplicación y los reportes.
- **No está aprobado** conservar bandas estrechas cambiándoles solo el nombre.

## D-3. Criterio conservador de modelo y bloqueo

Mantener **un único modelo principal por serie** (estabilidad de la trayectoria).
**No** implementar selección libre de un modelo distinto por horizonte.

Salvaguarda conservadora antes de bloquear:

1. Evaluar el modelo principal seleccionado para la serie.
2. Si falla en un horizonte, evaluar benchmarks válidos.
3. Considerar Drift y Naive, en el orden que el backtesting demuestre más conservador.
4. Usar como respaldo el benchmark que cumpla los criterios mínimos.
5. Bloquear únicamente cuando ningún modelo razonable resulte admisible.

**No permitir** que el fallo del modelo principal en h=1 bloquee automáticamente toda
la serie si existe un benchmark aceptable.

## D-4. Tratamiento de los meses de enero

Los eneros que cumplan los criterios confirmados del módulo de cambio de año se
clasifican como **«Patrón calendario de cambio de año»** y **no** deben aparecer
simultáneamente como valores atípicos.

- Mantener esos valores en la serie; no eliminarlos, interpolarlos ni suavizarlos.
- Excluirlos del recuento general de anomalías cuando el patrón esté confirmado.
- Mostrarlos como comportamiento recurrente de cambio de año.
- **Deduplicar alertas por periodo** (un periodo no aparece varias veces por
  distintos detectores/escalas).
- Diferenciar: patrón calendario / atípico aislado / cambio de nivel / posible error
  de datos.
- **Conservar sin cambios los umbrales del módulo de salto anual** (la auditoría los
  encontró bien calibrados).

## D-5. Contradicciones tesis–aplicación

Las contradicciones **estadísticas** se corrigen en la misma iteración que el código.
Como mínimo: explicación real de selección de modelos; retiro de ETS; fórmula y
valor-p de Jarque–Bera; salvaguarda con benchmarks; clasificación de enero;
construcción e interpretación del intervalo de predicción del 95 %; cobertura
empírica; diferencia confianza/predicción; límites de uso de SAVIP; aclaración de que
SAVIP no sustituye el índice oficial; afirmaciones sobre AICc, R² ajustado,
Durbin–Watson o Ljung–Box que no coincidan con la ruta real del código.

Las correcciones puramente editoriales pueden quedar para una revisión posterior.
**No debe quedar contradicción entre código, tesis, interfaz, reportes y pruebas.**

## D-6. Bibliografía de Iglewicz y Hoaglin

Agregar la referencia **únicamente si se utiliza directamente** para sustentar el
z modificado, el factor 0,6745, el umbral 3,5, la detección robusta de atípicos o una
definición tomada de esa fuente. Si solo se usa la explicación del NIST, citar solo
NIST (`nist_outliers` ya existe en el `.bib`). No agregar bibliografía no usada. Si se
usa: incorporarla al `.bib`, citarla en el texto, verificar existencia, incluir
DOI/ISBN/URL estable y comprobar que respalda exactamente la afirmación.

---

## Alcance aprobado de implementación

1. Retiro de ETS.
2. Corrección de Jarque–Bera.
3. Salvaguarda conservadora con Drift o Naive.
4. Corrección del bloqueo en cascada.
5. Recalibración del intervalo de predicción obligatorio del 95 %.
6. Reporte de cobertura empírica.
7. Reclasificación de enero como patrón calendario.
8. Deduplicación de alertas por periodo.
9. Corrección de la explicación real de selección de modelos.
10. Actualización de las partes afectadas de la tesis.
11. Actualización de reportes, interfaz y pruebas.
12. Incorporación de bibliografía únicamente cuando se utilice realmente.

**No implementar** recomendaciones de prioridad 3 o 4 de la auditoría que no formen
parte de esta lista (p. ej. unificación total de detectores más allá de la
deduplicación, normalización del score del selector de respaldo, migración masiva de
constantes, recalibración de los umbrales de amplitud, cambios en
`variacion_lineal`/`log_variacion`, retiro de `MIN_OBS_HISTORIAL_*`).
