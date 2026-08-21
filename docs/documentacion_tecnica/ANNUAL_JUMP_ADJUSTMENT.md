# Ajuste de salto de cambio de año (diciembre → enero)

Documento técnico del comportamiento estacional de cambio de año en las series
ICOCIV, del criterio de detección, de la validación retrospectiva y de la
implementación en el software.

Fecha del análisis: 22 de julio de 2026.
Fuente de datos: `anex-ICOCIV-may2026.xlsb` (65 periodos mensuales).

---

## 1. Problema observado

Los modelos de tendencia empleados por la aplicación (Drift, lineal,
exponencial log-lineal, Holt, ETS) reparten el crecimiento de forma
aproximadamente uniforme entre los meses. Varias series ICOCIV, en cambio,
concentran una parte importante de su variación anual en la transición
diciembre → enero, por la actualización anual de precios que recoge el índice.

Consecuencia: el modelo **subestima enero** y **sobrestima el resto del año**,
aun cuando el crecimiento anual total esté bien capturado.

## 2. Diagnóstico empírico

Metodología: variaciones logarítmicas `r_t = ln(y_t / y_{t-1})`. Se separan las
transiciones diciembre → enero del resto de meses y se comparan con estadística
robusta (medianas, no medias, para no depender de un año extremo).

- `γ` = mediana de las transiciones diciembre → enero.
- `m` = mediana del valor absoluto de las variaciones del resto de meses.
- `ratio` = |γ| / m.
- `consistencia de signo` = proporción de saltos con el mismo signo que `γ`.

### Prevalencia por tabla del anexo

| Tabla | Series evaluadas | Con evidencia | % | Ratio mediano | Salto mediano |
|---|---|---|---|---|---|
| T_16 | 5 | 5 | 100.0 % | 8.18 | +2.29 % |
| T_16_1 | 17 | 17 | 100.0 % | — | — |
| T_16_2 | 46 | 46 | 100.0 % | 7.83 | +2.57 % |
| T_16_3 | 316 | 309 | 97.8 % | — | — |
| T_16_13 | 11 658 | 7 585 | 65.1 % | — | — |

El patrón es prácticamente universal en los niveles agregados (grupos y tipos de
obra) y mayoritario, pero no universal, en insumos.

### Casos específicos

| Serie | γ (salto) | m (mes típico) | Ratio | Signo | Evidencia |
|---|---|---|---|---|---|
| Vías urbanas | +2.19 % | 0.24 % | 8.95 | 1.00 | Sí |
| Caminos vecinales | +2.72 % | 0.31 % | 8.73 | 1.00 | Sí |
| Cemento | +3.49 % | 0.83 % | 4.18 | 1.00 | Sí |
| Concreto simple | +6.99 % | 1.76 % | 3.97 | 0.80 | Sí |
| Acero | −0.57 % | 1.58 % | 0.36 | — | **No** |

Los saltos observados en Vías urbanas fueron: 1.569 %, 4.809 %, 2.192 %,
1.962 %, 2.513 %. El acero se comporta como caso de control: su variación está
dominada por el mercado internacional, no por el calendario.

### Salto de calendario frente a valor atípico

Un valor atípico aislado no se distingue de un patrón de calendario mirando una
sola observación. El criterio los separa por **recurrencia** y **consistencia**:
se exigen al menos dos transiciones diciembre → enero, que el salto supere en
más de 1.5 veces el movimiento mensual típico y que al menos el 60 % de los
saltos tengan el mismo signo. Un atípico no repite en la misma posición del
calendario y por tanto no pasa el criterio. El uso de medianas evita además que
un único año extremo determine la magnitud estimada.

## 3. Modelo de ajuste

Se conserva el modelo base seleccionado por la aplicación y se aplica un factor
multiplicativo que **reconcentra** en enero el salto que el modelo base repartió
de forma uniforme:

```
f_h = exp( γ · (n_h − h/12) )

valor_ajustado(h) = valor_base(h) · f_h
```

donde `n_h` es el número de eneros contenidos en los `h` pasos proyectados desde
el último periodo observado.

Propiedad central: **en h = 12 el factor vale exactamente 1**. El ajuste
redistribuye el salto dentro del año sin alterar el crecimiento anual estimado
por el modelo base, de modo que no introduce crecimiento adicional ni cambia la
tendencia de largo plazo. Se verificó numéricamente para los doce meses de
origen posibles (`tests/test_ajuste_salto_anual.py`).

Se descartaron las alternativas de estimar un modelo con estacionalidad completa
(doce coeficientes mensuales, demasiados parámetros para series de 65 periodos),
usar variables dummy de enero dentro de la regresión (obliga a reestimar todos
los modelos del catálogo) y modelar el salto como cambio de nivel permanente
(altera el crecimiento anual, que es precisamente lo que no debe alterarse).

## 4. Validación por backtesting

Se validó con ventana expansiva walk-forward, reestimando `γ` **únicamente con
la historia anterior a cada origen**, sin fuga de información futura. Modelo
base de referencia: Drift. Entrenamiento mínimo: 36 observaciones.

Mejora porcentual en MAE (positivo = el ajuste mejora):

| Serie | h=1 | h=2 | h=3 | h=6 | h=12 | h=18 |
|---|---|---|---|---|---|---|
| Vías urbanas | +32.7 | +36.3 | +38.6 | +40.9 | 0.0 | +28.5 |
| Caminos vecinales | +31.1 | +39.6 | +46.5 | +37.4 | 0.0 | +4.3 |
| Carreteras y calles | +30.7 | +33.8 | +38.7 | +35.8 | 0.0 | +12.9 |
| Cemento | +3.2 | +13.7 | +12.5 | +15.4 | 0.0 | +3.6 |
| **Concreto simple** | +2.7 | **−0.5** | **−6.0** | +2.2 | 0.0 | +2.0 |
| Acero | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

Lecturas:

- En agregados de obra la mejora es sustancial y sistemática (30 a 45 %).
- El valor exactamente neutro en h = 12 confirma empíricamente la propiedad de
  la fórmula.
- Acero no cambia porque no supera el criterio de detección: el control se
  comporta como se esperaba.
- **Concreto simple empeora en h = 2 y h = 3** (RMSE −22.4 % en h=3). Este caso
  es la razón por la que el ajuste **no** se activa solo con detectar evidencia.

## 5. Regla de activación implementada

El ajuste se aplica únicamente si se cumplen las **tres** condiciones:

1. **Evidencia en la serie**: ≥ 2 transiciones diciembre → enero, ratio > 1.5 y
   consistencia de signo ≥ 0.6.
2. **Validación retrospectiva**: sobre las ventanas walk-forward reales de la
   serie, el ajuste no deteriora ni el MAE ni el RMSE.

Son dos, no tres. El horizonte solicitado **no** interviene en la activación
(corrección documental del 29 de julio de 2026, hallazgo H-10 de la auditoría
independiente: esta sección describía una tercera condición que el código nunca
tuvo). El patrón es una propiedad de la serie y se detecta con independencia de
lo que se pida proyectar.

Lo que sí depende del horizonte es el **efecto**, no la activación: el factor se
aplica paso a paso y, si ningún paso cae en enero, vale prácticamente uno y la
trayectoria no se desplaza. Reintroducir una condición `cruza_enero` sobre el
horizonte total rompería la regla de que los meses comunes valen lo mismo al
pedir 3, 6, 12 o 18 meses.

Ambos hechos se comunican por separado en interfaz, informes y CSV mediante
`patron_detectado_en_serie`, `efecto_en_horizonte_solicitado` y la etiqueta
única `estado_calendario_visible`.

Nunca se aplica por defecto a todas las series. En el estado actual: Vías
urbanas lo activa (mejora 21.6 % de MAE en la validación real de la aplicación),
Concreto simple lo rechaza (deterioro de 10.5 %) y Acero no llega a evaluarse
por falta de evidencia.

## 6. Implementación

- `app_icociv/estadistica/calendario_anual.py` — módulo nuevo, sin dependencias
  de interfaz:
  - `perfil_salto_anual(serie)` — detección y caracterización.
  - `eneros_en_horizonte(mes_origen, horizonte)`.
  - `factor_ajuste_calendario(gamma, mes_origen, horizonte)`.
  - `evaluar_ajuste_en_backtesting(serie, predicciones, horizonte)` — reutiliza
    las predicciones walk-forward ya calculadas; reestima `γ` por origen.
  - `aplicar_ajuste_calendario(valores_base, periodos, mes_origen, gamma)`.
  - `resumen_trazabilidad(...)` — estructura para interfaz y reportes.
- `app_icociv/estadistica/criterios.py` — umbrales `MIN_TRANSICIONES_SALTO_ANUAL`,
  `RATIO_SALTO_ANUAL`, `CONSISTENCIA_SIGNO_SALTO_ANUAL`,
  `TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO`.
- `app_icociv/proyeccion/servicio_proyeccion.py` — `_ajustar_salto_anual()`
  aplica las tres condiciones y devuelve trayectoria y trazabilidad; el
  resultado expone la clave `ajuste_calendario`. Los intervalos de predicción se
  construyen sobre la trayectoria ya ajustada.
- `app_icociv/reportes/generador_reportes.py` — `_filas_ajuste_calendario()`
  alimenta DOCX y PDF; el CSV reproducible incorpora nueve columnas nuevas.
- `app_icociv/interfaz/presentacion_resultados.py` — bloque «Patrón de cambio de
  año», visible únicamente cuando la serie presenta el patrón. Si el patrón
  existe pero el ajuste no se aplicó, además se emite una advertencia; el caso
  aplicado no genera advertencia porque no lo es.

## 7. Trazabilidad expuesta

Clave `ajuste_calendario` del resultado y columnas del CSV: si el ajuste se
aplicó, si hay evidencia, número de transiciones observadas, salto mediano en
porcentaje, movimiento mensual típico, razón salto/movimiento, consistencia de
signo, eneros dentro del horizonte, criterio de detección, ventanas de
validación, mejora en MAE y en RMSE, y el mensaje explicativo.

Los mensajes posibles distinguen: ajuste aplicado y validado con eneros dentro
del horizonte, patrón detectado y ajuste aplicado pero sin ningún enero en el
horizonte pedido (efecto neutro), y patrón detectado pero rechazado por la
validación retrospectiva (con las cifras de deterioro).

## 8. Pruebas

`tests/test_ajuste_salto_anual.py` cubre detección con patrón sintético
controlado, serie sin patrón, serie demasiado corta, neutralidad del factor en
h = 12 para los doce meses de origen, conteo de eneros en el horizonte, forma
del ajuste sobre la trayectoria, rechazo por backtesting y no aplicación sin
ventanas de validación.

`tests/test_calendario_y_clasificacion_intervalo.py` añade la separación entre
patrón y efecto: que el patrón se detecte aunque el horizonte no alcance ningún
enero, que el perfil no cambie al ampliar el horizonte y que el estado visible
llegue al CSV reproducible.

`app_icociv/estadistica/calendario_anual.py` incluye además una comprobación
propia ejecutable con `python -m app_icociv.estadistica.calendario_anual`.

## 9. Limitaciones

- `γ` se estima con pocas transiciones (5 en el anexo vigente); es una mediana
  robusta pero con incertidumbre alta, y por eso el ajuste queda condicionado a
  la validación retrospectiva.
- El ajuste supone que la magnitud del salto se mantiene estable. Un cambio
  metodológico del DANE en la actualización anual invalidaría la estimación
  histórica.
- Los intervalos de predicción se calculan sobre la trayectoria ajustada, pero
  su amplitud sigue derivándose de los errores out-of-sample del modelo base; no
  incorporan la incertidumbre propia de estimar `γ`.
- La equivalencia y el criterio final sobre el uso de una proyección ajustada
  corresponden al ingeniero responsable.
