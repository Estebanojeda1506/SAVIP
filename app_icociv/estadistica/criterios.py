"""Registro de criterios estadisticos ICOCIV.

Este modulo centraliza los umbrales que antes aparecian dispersos en la
aplicacion. No todos los valores son "reglas estadísticas universales": muchos
son parametros operativos internos que ayudan a clasificar evidencia, activar
diagnosticos o comunicar cautelas. Por eso cada criterio queda identificado por
tipo, sustento y accion de gobierno metodologico.

Cada entrada declara su ``tipo`` con uno de siete estados. La asignacion se
verifico contra el codigo realmente invocado el 04-08-2026; el procedimiento y
su salida estan en la carpeta de control de esa fecha.

``bibliografico``
    Una fuente externa respalda el metodo y el valor.
``derivacion_matematica``
    El valor se deduce de la definicion del estadistico y no admite otro.
``operativo_tecnico``
    Parametro de implementacion, de coste o de validacion de entrada, sin
    efecto estadistico sobre el resultado.
``operativo_interno_sin_sustento``
    Decision propia del proyecto, sin fuente externa. No debe presentarse como
    regla universal.
``muerto``
    Definido en el codigo pero sin ningun consumidor en la ruta viva. Se
    conserva la fila para dejar constancia de que no decide nada.
``experimental``
    Medido en sesiones de experimentacion y no integrado en el producto.
``pendiente_de_decision``
    Requiere una decision autorizada antes de modificarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TIPO_BIBLIOGRAFICO = "bibliografico"
TIPO_DERIVACION = "derivacion_matematica"
TIPO_OPERATIVO_TECNICO = "operativo_tecnico"
TIPO_OPERATIVO = "operativo_interno_sin_sustento"
TIPO_MUERTO = "muerto"
TIPO_EXPERIMENTAL = "experimental"
TIPO_PENDIENTE = "pendiente_de_decision"

#: Unicos valores admitidos en el campo ``tipo``.
TIPOS_ADMITIDOS = frozenset(
    {
        TIPO_BIBLIOGRAFICO,
        TIPO_DERIVACION,
        TIPO_OPERATIVO_TECNICO,
        TIPO_OPERATIVO,
        TIPO_MUERTO,
        TIPO_EXPERIMENTAL,
        TIPO_PENDIENTE,
    }
)


# Calidad y ventanas temporales.
MIN_OBS_MODELACION = 8
ADVERTENCIA_MIN_OBS = 18
MIN_OBS_RECOMENDADAS = 24
MIN_ITERACIONES_WF = 6
# Ventanas minimas para admitir un horizonte SOLO como escenario. Entre este
# valor y MIN_ITERACIONES_WF la evidencia existe pero es reducida: el horizonte
# se puede calcular con advertencia, no se puede certificar como proyeccion
# tecnica validada. Por debajo de este valor no hay evidencia utilizable.
MIN_ITERACIONES_WF_ESCENARIO = 3
# P0-E, 12-08-2026: RETIRADOS `MIN_OBS_WF_INICIAL = 18` y
# `PROPORCION_ENTRENAMIENTO_WF = 0.60`. Eran dos literales sin fuente que
# decidian el primer origen del backtesting y, con el, cuantos pares fuera de
# muestra existen, el RMSE global y el modelo entregado por C-SEL-001.
# Verificado contra el original: FPP3 5.10 -el procedimiento aplicado- NO da
# ninguna proporcion; la unica del libro, 5.8, es «about 20 %» de conjunto de
# PRUEBA para una particion unica (80 % de entrenamiento, no 60 %) y pertenece a
# otro procedimiento. Tashman (2000) no fija ventana inicial ni proporcion.
# El primer origen vive ahora en `modelos_interpretables.observaciones_minimas_catalogo`
# y se deriva de la estimabilidad de los candidatos que compiten.

# Salto de cambio de anio (efecto calendario diciembre-enero).
# Calibrados con el diagnostico del 19 de julio de 2026 sobre el anexo ICOCIV:
# en las series agregadas el salto dic-ene supera 7 veces el movimiento mensual
# tipico, mientras que series sin patron (p. ej. Acero) quedan por debajo de 0.4.
MIN_TRANSICIONES_SALTO_ANUAL = 2
RATIO_SALTO_ANUAL = 1.5
CONSISTENCIA_SIGNO_SALTO_ANUAL = 0.6
# El ajuste solo se activa si no deteriora MAE ni RMSE mas alla de este factor.
TOLERANCIA_DETERIORO_AJUSTE_CALENDARIO = 1.00

# Criterios robustos y tolerancias numericas.
UMBRAL_Z_MODIFICADO_ATIPICO = 3.5
FACTOR_Z_MODIFICADO = 0.6745
# D-8: se retira MULTIPLICADOR_MAD_ERRORES_EXTREMOS = 3.0. Comparaba |e| contra
# mediana(|e|) + 3 MAD, un corte de implementacion sin respaldo. La deteccion de
# errores inusuales usa ahora el mismo puntaje z modificado que la serie, con el
# umbral 3.5 de Iglewicz y Hoaglin (1993) recogido por el NIST.
EPS_NUMERICO = 1e-12

# Diagnostico residual.
# D-2: los cortes fijos de Durbin-Watson (0,8 / 3,2 / 1,5 / 2,5) se retiraron.
# No proceden de Durbin y Watson (1951) ni de ningun manual: el contraste se
# resuelve con las tablas d_L y d_U, dependientes de n y del numero de
# regresores, que la aplicacion no implementa. El estadistico se sigue
# calculando y publicando como dato descriptivo; la autocorrelacion se
# contrasta con Ljung-Box, que si produce un valor p.
ALPHA_PRUEBAS_RESIDUALES = 0.05
# Ljung-Box, especificado tras la auditoria de julio de 2026. Antes se usaban
# valores por omision sin documentar y la prueba solo corria si statsmodels
# estaba instalado por casualidad.
MAX_LAG_LJUNG_BOX = 10
# MIN_OBS_LJUNG_BOX = 12 retirado el 04-08-2026: estaba muerto. D-10 lo
# sustituyo por la condicion derivada `n > rezagos efectivos`, que vive en
# `calcular_ljung_box`. El minimo fijo era ademas MAS restrictivo que la
# condicion matematica: exigia 12 residuos donde el contraste existe desde 5.
MODEL_DF_LJUNG_BOX = 0
# Jarque-Bera: minimo de residuos para que el contraste sea calculable.
MIN_OBS_JARQUE_BERA = 8
MIN_RESIDUOS_DIAGNOSTICO = 12
# D-7: se retiran UMBRAL_CORR_HETEROCEDASTICIDAD = 0.55 y
# UMBRAL_MEDIA_RESIDUAL_DESV = 0.25. Ninguno era un contraste: no producian
# estadistico, grados de libertad ni valor p, y sus cortes carecian de fuente.
# La media residual se contrasta con la prueba t de una muestra y la
# heterocedasticidad con Breusch-Pagan (1979).
CONSECUENCIA_INFORMATIVA = (
    "Informativa; no modifica automaticamente el pronostico."
)

# Calidad predictiva. Son parametros operativos internos, no universales.
UMBRAL_MASE_ADVERTENCIA = 1.0
# D-9: se retiran las bandas internas de interpretacion de metricas.
#   UMBRAL_MASE_MEDIA = 0.8
#   UMBRAL_MAPE_ALTA_CONFIANZA = 3.0, _MEDIA_CONFIANZA = 8.0, _ALTO = 15.0, _EXTREMO = 25.0
#   UMBRAL_SMAPE_ALTO = 20.0, _EXTREMO = 30.0, _EVIDENCIA_OK = 10.0
#   UMBRAL_SESGO_MAE = 0.75
# Ninguna procedia de una fuente: clasificaban el error en categorias de
# confianza, bloqueaban horizontes y recortaban el maximo recomendado. Las
# metricas se siguen calculando y publicando con sus unidades. La unica lectura
# comparativa que se conserva es MASE frente a 1 (Hyndman y Koehler, 2006),
# que es el sentido con el que la metrica fue definida.
# UMBRAL_ESTABILIDAD_ALTA_CONFIANZA = 0.75 retirado el 04-08-2026: estaba
# muerto. Solo el corte de inestabilidad se consulta en la ruta viva.
UMBRAL_ESTABILIDAD_INESTABLE = 1.0
# D-8: se retiran UMBRAL_ERRORES_EXTREMOS_ADVERTENCIA = 15, _BLOQUEO = 25 y
# _BLOQUEO_HORIZONTE = 50. Eran porcentajes internos sin fuente que convertian
# una proporcion descriptiva en advertencia, degradacion a escenario y bloqueo
# de horizonte. La cantidad, la proporcion y el puntaje z por observacion se
# siguen publicando; ninguna decision depende ya de ellos.

# Comparacion contra benchmarks.
TOLERANCIA_RRMSE_BENCHMARK = 1.10
UMBRAL_RRMSE_PEOR_BENCHMARK = 1.25

# Intervalos e incertidumbre.
# `_cuantiles_intervalo` toma SIEMPRE el maximo entre el cuantil de orden con
# correccion de muestra finita y la prediccion t de Student, para cualquier n.
# No existe un cambio de metodo por tamano de muestra.
#
# Retiradas el 04-08-2026 por estar muertas (definidas e importadas, nunca
# leidas en ningun cuerpo de funcion):
#   MIN_ERRORES_OOS_PERCENTILES = 10  -> documentaba un cambio de metodo en n=10
#                                        que el codigo no implementa.
#   PERCENTIL_IC80_INF/_SUP = 10/90 y PERCENTIL_IC95_INF/_SUP = 2.5/97.5
#                                     -> el intervalo no usa np.percentile.
#
# La cobertura empirica se EVALUA por origen movil (D-12b-C, 04-08-2026): cada
# error se contrasta contra el rango de sus anteriores del mismo paso. Ese
# procedimiento no necesita partir la muestra, de modo que mide tambien los
# horizontes largos.
#
# MIN_ERRORES_COBERTURA_EMPIRICA sigue gobernando la VERIFICABILIDAD del paso
# solicitado, que es cosa distinta de que su cobertura se pueda evaluar: un paso
# con 15 errores ya tiene cobertura medida, pero no se declara verificado.
# D-1b-B, que propone retirar este minimo, no esta integrada.
MIN_ERRORES_COBERTURA_EMPIRICA = 16
# Tolerancia de comunicacion: por debajo de esta cobertura observada al 95% se
# advierte explicitamente. No es un objetivo de ajuste (calibrar contra la
# muestra de prueba invalidaria la verificacion); es el umbral de aviso.
TOLERANCIA_COBERTURA_IC95 = 0.90
# Clasificacion del intervalo segun la cobertura empirica medida, autorizada el
# 28 de julio de 2026 tras el hallazgo H-05 de la auditoria independiente.
#
# Son CRITERIOS OPERATIVOS INTERNOS, no reglas estadisticas universales: fijan
# como se comunica una banda cuya cobertura no alcanza el nominal, no corrigen
# el calculo. El semiancho no se toca; los pronosticos puntuales tampoco.
#
# Sensibilidad medida y documentada en
# docs/remediacion_auditoria/SENSIBILIDAD_UMBRALES_COBERTURA.md
# CONVERTIDO EN DESCRIPTIVO el 07-08-2026. Conserva su valor y pierde su
# funcion decisoria: ya no encabeza la escalera de clasificacion, solo elige
# entre dos redacciones de un resultado que no se degrada en ninguna de las
# dos. Su efecto decisorio aislado medido fue 0 estados y 0 tipos de banda
# (variante E-090-AISLADO sobre los cincuenta escenarios). NO se sustituyo por
# 0,95 ni por ningun otro corte.
COBERTURA_IC95_ACEPTABLE = 0.90     # descriptivo: separa dos redacciones
COBERTURA_IC95_ADVERTENCIA = 0.80   # >= : no se degrada
                                    # <  : rango de referencia y horizonte a escenario
                                    # Es el UNICO corte de proporcion con efecto.
UMBRAL_INTERVALO_ADVERTENCIA = 0.30
# UMBRAL_INTERVALO_CRITICO = 0.40 retirado el 04-08-2026: su unico consumidor
# era `analisis_series.determinar_horizonte_maximo`, funcion exportada y jamas
# invocada, retirada en la misma fecha.
#
# Cortes de amplitud relativa del IC95. Son NUEVE, no siete: ademas de las
# siete constantes de abajo, `_umbrales_incertidumbre` lleva escritos en linea
# 0.45 y 0.65, que no tienen constante propia.
#
# El que mas bloquea es UMBRAL_IC95_REL_EXTENDIDO_CERCANO (0.50): es el
# "no_recomendado" de h<=12 y ademas el corte explicito que bloquea el tramo
# 13..18 antes de que 0.55 llegue a aplicarse. UMBRAL_IC95_REL_EXTENDIDO (0.55)
# NO decide nada: en 13..18 cualquier ancho >= 0.50 ya bloquea por la rama
# inmediatamente posterior, de modo que 0.55 solo elige el texto de la razon.
UMBRAL_IC95_REL_OPERATIVO = 0.10
UMBRAL_IC95_REL_CORTO = 0.20
UMBRAL_IC95_REL_MEDIO = 0.30
UMBRAL_IC95_REL_LARGO = 0.40
UMBRAL_IC95_REL_EXTENDIDO_CERCANO = 0.50
UMBRAL_IC95_REL_EXTENDIDO = 0.55
UMBRAL_IC95_REL_EXPLORATORIO = 0.75

# Horizontes. 18 meses es una opcion de interfaz, no un maximo estadistico fijo.
# El limite real de busqueda es HORIZONTE_MAXIMO_AUDITORIA, definido en
# `servicio_proyeccion`, y es constante: no lo modula la longitud historica.
#
# Retiradas el 04-08-2026 por estar muertas (sin ningun consumidor):
#   HORIZONTES_OPERATIVOS_UI = (1, 3, 6, 12, 18) -> la interfaz no la lee.
#   H_MAX_BUSQUEDA_DEFAULT = 18, _HISTORIAL_MEDIO = 24, _HISTORIAL_LARGO = 30
#   MIN_OBS_HISTORIAL_MEDIO = 84, MIN_OBS_HISTORIAL_LARGO = 96
#       -> documentaban una busqueda modulada por longitud que no existe.
HORIZONTE_LARGO = 18

# Activacion progresiva de modelos.
MIN_OBS_NIVEL_2 = 24
MIN_OBS_HUBER = 8


@dataclass(frozen=True)
class CriterioEstadistico:
    """Fila de la matriz de auditoria metodológica."""

    id: str
    criterio: str
    ubicacion: str
    tipo: str
    valor: str
    fuente: str
    justificacion: str
    accion: str

    def como_fila_markdown(self) -> str:
        valores = [
            self.id,
            self.criterio,
            self.ubicacion,
            self.tipo,
            self.valor,
            self.fuente,
            self.justificacion,
            self.accion,
        ]
        return "| " + " | ".join(_escapar_md(v) for v in valores) + " |"


CRITERIOS_ESTADISTICOS: tuple[CriterioEstadistico, ...] = (
    CriterioEstadistico(
        "C-DAT-001",
        "Mínimo computacional para modelacion",
        "app_icociv/estadística/analisis_series.py; backtesting.py",
        TIPO_OPERATIVO,
        str(MIN_OBS_MODELACION),
        "Parámetro interno documentado",
        "Evita ajustar modelos con muy pocos puntos y sin ventanas minimas.",
        "Mantener como configurable; no presentarlo como regla universal.",
    ),
    CriterioEstadistico(
        "C-DAT-002",
        "Advertencia por serie corta",
        "app_icociv/estadística/métricas.py; analisis_series.py",
        TIPO_OPERATIVO,
        str(ADVERTENCIA_MIN_OBS),
        "Parámetro interno documentado",
        "Marca series útiles para descripción pero debiles para validación temporal.",
        "Mantener como advertencia operativa configurable.",
    ),
    CriterioEstadistico(
        "C-DAT-003",
        "Longitud recomendada para modelacion mensual",
        "app_icociv/estadística/métricas.py; analisis_series.py",
        TIPO_OPERATIVO,
        str(MIN_OBS_RECOMENDADAS),
        "Criterio metodológico interno",
        "Dos años de datos mensuales permiten variación anual y backtesting básico.",
        "Mantener como recomendación, no como bloqueo automático.",
    ),
    CriterioEstadistico(
        "C-WF-001",
        "Mínimo de iteraciones walk-forward (descriptivo)",
        "app_icociv/validación/backtesting.py; servicio_proyeccion.py",
        TIPO_OPERATIVO,
        str(MIN_ITERACIONES_WF),
        "Parámetro interno documentado; ninguna fuente fija el valor 6",
        "Señala cuándo el error fuera de muestra reúne pocas ventanas y es menos estable. "
        "P0-G, 16-08-2026: no decide. No admite, no degrada y no niega ningún horizonte; su "
        "único efecto es la advertencia con la que se publica el número exacto de ventanas.",
        "Mantener como configurable y reportar en informes. No devolverle efecto decisorio.",
    ),
    CriterioEstadistico(
        "C-WF-002",
        "Primer origen de la validación temporal",
        "app_icociv/estadistica/modelos_interpretables.py; validación/backtesting.py",
        # P0-E, verificación adversarial del 12-08-2026: la derivación se auditó
        # y NO es suficiente como regla del primer origen. `N0 = max_m N_min(m)`
        # es condición NECESARIA de comparabilidad -verificada- pero no se ha
        # demostrado suficiente, y ninguna fuente determina dónde empieza la
        # evaluación. Publicarlo como `derivacion_matematica` afirmaba un cierre
        # que no existe.
        # P0-E, 15-08-2026. CORRECCIÓN DE TEXTO PUBLICADO, no de comportamiento.
        # El valor decía «mínimo identificable» y la interpretación definía la
        # identificación como «el número de ecuaciones supera al de incógnitas».
        # Ambas afirmaciones son incorrectas: contar parámetros da una condición
        # NECESARIA, no suficiente, y no equivale a identificabilidad. Este campo
        # es descriptivo -se publica en la tabla auditable y no interviene en
        # ninguna decisión-, de modo que la corrección no altera ningún
        # resultado. El número 6 no cambia.
        TIPO_PENDIENTE,
        "N0 = max sobre los candidatos de su mínimo operativo codificado para intentar el ajuste (hoy 6, por Holt amortiguado)",
        "Tashman (2000) y FPP3 §5.10 sustentan el esquema de origen móvil; ninguna fuente determina el primer origen",
        (
            "Cada modelo declara un mínimo de observaciones por CARDINALIDAD: el número de "
            "parámetros más uno, que es la condición necesaria para intentar el ajuste sin "
            "interpolar. Holt amortiguado tiene cinco parámetros, luego su mínimo codificado "
            "es seis. Ese valor NO constituye un mínimo de identificabilidad estadística "
            "demostrado: contar parámetros no garantiza que la muestra los identifique. Se "
            "toma el máximo del catálogo porque C-SEL-001 compara sobre la muestra común, y "
            "un candidato no ajustable en los primeros orígenes la encogería para todos."
        ),
        (
            "P0-E, 12-08-2026: sustituye a max(18, 0,60n). Los dos literales carecían de "
            "fuente y la atribución a Hyndman y Athanasopoulos era falsa: FPP3 §5.10 no da "
            "proporción y §5.8 da 20 % de PRUEBA para una partición única. "
            "P0-E, 15-08-2026: N0 = 6 se mantiene como DECISIÓN PROVISIONAL del diseño del "
            "backtesting. No está determinado por fuente ni por derivación completa, y su "
            "variación cambia el modelo seleccionado en parte de las series evaluadas. "
            "Limitación declarada: FPP3 §5.10 pide que el entrenamiento no sea «pequeño» "
            "pero no operacionaliza el término, y esta regla tampoco."
        ),
    ),
    CriterioEstadistico(
        "C-ATI-001",
        "Valor atípico por Z robusto modificado",
        "app_icociv/estadistica/analisis_series.py",
        TIPO_BIBLIOGRAFICO,
        f"|M_i| > {UMBRAL_Z_MODIFICADO_ATIPICO}",
        "NIST/SEMATECH e-Handbook of Statistical Methods, sección 1.3.5.17",
        "Umbral estándar para el Z modificado con MAD y factor 0.6745.",
        "Mantener; eliminar subrangos fijos no sustentados.",
    ),
    CriterioEstadistico(
        "C-ATI-003",
        "Clasificación de alertas por periodo (deduplicadas)",
        "app_icociv/estadistica/analisis_series.py",
        TIPO_OPERATIVO,
        "patron_calendario / posible_error_datos / posible_cambio_nivel / posible_atipico_aislado",
        "Politica interna; el patron calendario se confirma con C-CAL-001",
        "Un enero del patron recurrente de cambio de anio no es un atípico; contarlo como tal "
        "triplicaba las alertas y penalizaba series válidas. Ningun valor se elimina.",
        "Mantener; la clasificación es descriptiva y no altera la serie.",
    ),
    CriterioEstadistico(
        "C-ATI-002",
        "Subrangos leve/moderado/fuerte de atípicos",
        "Documento Overleaf y versión previa de analisis_series.py",
        TIPO_OPERATIVO,
        "3.5-4.5; 4.5-5.0; >5.0",
        "Sin calibración empírica documentada",
        "Los subrangos podian sonar a estándar externo aunque eran internos.",
        "Eliminar como criterio fijo; usar solo posible_atipico o calibrar empiricamente.",
    ),
    CriterioEstadistico(
        "C-DW-001",
        "Durbin-Watson como estadistico descriptivo",
        "app_icociv/estadistica/diagnostico_residuos.py",
        TIPO_BIBLIOGRAFICO,
        "Se reporta el valor en [0, 4]; sin cortes de clasificacion",
        "Durbin y Watson (1951), Biometrika 38(1-2), pp. 159-177",
        "El estadistico se calcula y se publica. Su contraste formal exige las tablas d_L y d_U, "
        "que dependen de n y del numero de regresores y no estan implementadas, de modo que no se "
        "emite ningun veredicto categorico. La autocorrelacion se contrasta con Ljung-Box, que si "
        "produce un valor p.",
        "Mantener como dato descriptivo. Decision D-2: los cortes 0,8 / 3,2 / 1,5 / 2,5 se "
        "retiraron por carecer de fuente; no procedian de Durbin y Watson ni de ningun manual.",
    ),
    CriterioEstadistico(
        "C-RES-001",
        "Nivel de significancia Ljung-Box/Jarque-Bera",
        "app_icociv/estadistica/diagnostico_residuos.py",
        TIPO_BIBLIOGRAFICO,
        f"alpha = {ALPHA_PRUEBAS_RESIDUALES}",
        "Convencion estadística usual al 5%; Ljung y Box; Jarque y Bera",
        "Ayuda a detectar patrones residuales y no normalidad aproximada.",
        "Mantener; reportar como diagnostico, no como decisión única.",
    ),
    CriterioEstadistico(
        "C-HET-001",
        "Heterocedasticidad de los residuos",
        "app_icociv/estadistica/diagnostico_residuos.py",
        TIPO_BIBLIOGRAFICO,
        "Breusch-Pagan sobre [1, t]; se rechaza si p < " + str(ALPHA_PRUEBAS_RESIDUALES),
        "Breusch y Pagan (1979); statsmodels.stats.diagnostic.het_breuschpagan",
        "Contrasta si la varianza residual depende del indice temporal, con estadistico LM y valor p.",
        "Mantener. Consecuencia informativa: no bloquea, no degrada y no altera pronostico ni intervalo (D-7).",
    ),
    CriterioEstadistico(
        "C-RES-002",
        "Media residual igual a cero",
        "app_icociv/estadistica/diagnostico_residuos.py",
        TIPO_BIBLIOGRAFICO,
        "Prueba t de una muestra bilateral; se rechaza si p < " + str(ALPHA_PRUEBAS_RESIDUALES),
        "Prueba t de una muestra; scipy.stats.ttest_1samp",
        "Contrasta si la media poblacional de los residuos difiere de cero, con estadistico, grados de libertad y valor p.",
        "Mantener. Consecuencia informativa: no bloquea, no degrada y no altera pronostico ni intervalo (D-7).",
    ),
    CriterioEstadistico(
        "C-MASE-001",
        "MASE como señal de cautela",
        "app_icociv/validación/backtesting.py; métricas.py",
        TIPO_BIBLIOGRAFICO,
        "> 1 frente a escala naive in-sample",
        "Hyndman y Koehler (2006)",
        "Mide error respecto a naive in-sample no estacional.",
        "Mantener como métrica auxiliar; no usar como veto único.",
    ),
    CriterioEstadistico(
        "C-ERR-001",
        "Errores de backtesting inusuales por puntaje z modificado",
        "app_icociv/estadistica/metricas.py; validacion/backtesting.py",
        TIPO_BIBLIOGRAFICO,
        f"|M_i| > {UMBRAL_Z_MODIFICADO_ATIPICO} con M_i = {FACTOR_Z_MODIFICADO} (|e_i| - mediana) / MAD",
        "Iglewicz y Hoaglin (1993); NIST/SEMATECH e-Handbook 1.3.5.17",
        "Marca ventanas de backtesting con error inusual usando el mismo criterio de atipico que la serie.",
        "Mantener. Salida descriptiva: no bloquea, no degrada y no altera modelo, pronostico ni intervalo (D-8).",
    ),
    CriterioEstadistico(
        "C-INT-001",
        "Construccion del intervalo de prediccion (FPP3 5.5)",
        "app_icociv/proyeccion/servicio_proyeccion.py::_cuantiles_intervalo",
        # RECLASIFICADO el 09-08-2026 (P0-C). El 04-08 esta fila figuraba como
        # bibliografica describiendo una regla max() que no lo era, y por eso se
        # degrado a operativa. Ahora la CONSTRUCCION COMPLETA tiene fuente
        # -FPP3 5.5- y el multiplicador con sigma estimada es una derivacion, de
        # modo que vuelve a ser bibliografica con pleno derecho.
        TIPO_BIBLIOGRAFICO,
        "pronostico +/- c * sigma_h, con sigma_h = sqrt(SUM e^2 / n) sobre los errores OOS del "
        "paso exacto y c el cuantil t con n grados de libertad del nivel nominal",
        "Hyndman y Athanasopoulos (2021), FPP3 5.5: yhat +/- c*sigma_h, con sigma_h estimada de "
        "los errores. El multiplicador t es la derivacion exacta cuando sigma_h se estima",
        "CORREGIDO el 09-08-2026 (auditoria P0-C). La construccion anterior tomaba el MAXIMO entre un "
        "cuantil de orden y una prediccion t, centraba ambas en la media del error y aplicaba despues dos "
        "correcciones. CINCO de sus componentes carecian de fuente: la combinacion max(), incluir el "
        "semiancho del 80 % dentro del maximo del 95 %, el centrado en la media del error, la correccion "
        "que forzaba el pronostico dentro de su banda y la envolvente monotona entre pasos. Tres de ellos "
        "ensanchaban la banda y uno la desplazaba. Se adopta la construccion completa de FPP3 5.5. "
        "Sobre el centrado, FPP3 5.4 es explicito en que el sesgo se corrige sumando la media a los "
        "PRONOSTICOS, no desplazando el intervalo. Tres reglas desaparecen POR CONSTRUCCION: al haber una "
        "sola construccion no hay que combinar nada; al centrar en el pronostico este queda dentro por "
        "definicion; y con la misma sigma_h y c80 < c95 el intervalo del 80 % queda contenido en el del "
        "95 %. Medicion sobre 10 series y 24 pasos: la cobertura observada al 95 % pasa de 0,922 a 0,949 y "
        "al 80 % de 0,765 a 0,832, ambas mas cerca del nominal. El metodo NO se eligio por su cobertura "
        "-eso lo prohiben los requisitos- sino por corresponder al problema; la cobertura es corroboracion.",
        "Mantener. La construccion completa tiene fuente. LO QUE GARANTIZA: la cobertura nominal si los "
        "supuestos -normalidad aproximada de la distribucion de pronostico y errores de media cero- se "
        "cumplen. LO QUE NO GARANTIZA: cobertura bajo no normalidad, sesgo o dependencia temporal; por eso "
        "la cobertura observada se mide y se publica, y nunca se declara garantizada. PENDIENTE fuera de "
        "P0-C: SAVIP publica sesgo_medio pero NO corrige el pronostico como manda FPP3 5.4.",
    ),
    CriterioEstadistico(
        "C-INT-002",
        "Condicion de existencia del cuantil de orden al 95 %",
        "app_icociv/proyeccion/servicio_proyeccion.py::_semiancho_conformal",
        TIPO_DERIVACION,
        "k = ceil((n+1)(1-alfa)) <= n, es decir n >= 1/alfa - 1 = 19 errores al 95 %",
        "Lei et al. (2018); Angelopoulos y Bates (2023)",
        "Por debajo de 19 errores del horizonte exacto ningun dato observado ocupa esa posicion de la cola: no es "
        "que el cuantil sea poco fiable, es que no existe, y la banda se sostiene en el respaldo parametrico t. "
        "Cada paso p usa los errores walk-forward a horizonte exactamente p, sin reescalar los de otro horizonte. "
        "La banda del 80 % se calcula solo como diagnostico interno y no se publica en ninguna salida.",
        "Mantener. CORREGIDO el 04-08-2026: la version anterior describia percentiles empiricos 2,5/97,5 con "
        "n >= 10, construccion que el codigo no realiza y cuyas cuatro constantes estaban muertas.",
    ),
    CriterioEstadistico(
        "C-INT-004",
        "Cobertura empírica por evaluacion de origen movil",
        "app_icociv/proyeccion/servicio_proyeccion.py::evaluacion_cobertura_origen_movil",
        TIPO_OPERATIVO_TECNICO,
        "cada error se contrasta contra el rango construido con los errores ANTERIORES del mismo "
        "paso; con n errores se obtienen n-2 contrastes",
        "Christoffersen (1998), International Economic Review 39(4), 841-862, para la evaluacion "
        "de una SECUENCIA de intervalos por su sucesion de aciertos y su cobertura incondicional; "
        "Tashman (2000) y Hyndman y Athanasopoulos (2021) 5.10 para la evaluacion de origen rodante",
        "ATRIBUCION CORREGIDA el 09-08-2026 (auditoria de fundamentacion, I-01). D-12b-C se venia "
        "declarando «procedimiento propio, documentado», declaracion MAS DEBIL que sus fuentes: "
        "Christoffersen (1998) establece precisamente la evaluacion de intervalos por la sucesion "
        "de indicadores de acierto fuera de muestra. Lo que se reporta es la cobertura "
        "INCONDICIONAL; la cobertura condicional de Christoffersen -que anade un contraste de "
        "independencia- no se calcula, y esa limitacion se declara. "
        "La cobertura nominal del 95% se comprueba y se reporta con su minimo; si el paso no reune la "
        "muestra exigida, se declara no verificable. La del 80% queda como diagnostico interno. "
        "El error evaluado no interviene en su propio rango y no se consulta ningun error posterior. "
        "Limitacion: amortigua los cambios de regimen, porque el rango los absorbe al ocurrir.",
        "Mantener. Integrado el 04-08-2026 (D-12b-C) en sustitucion de la particion temporal fija "
        f"50/50, que exigia n >= {MIN_ERRORES_COBERTURA_EMPIRICA} y dejaba sin medir los horizontes "
        "largos. El metodo se publica desde el resultado y nunca como frase fija en los informes.",
    ),
    CriterioEstadistico(
        "C-INT-003",
        "Ancho relativo de IC95 por horizonte",
        "app_icociv/proyeccion/servicio_proyeccion.py::_umbrales_incertidumbre",
        TIPO_OPERATIVO,
        "NUEVE cortes: 0.10 operativo; 0.20 corto; 0.30 medio; 0.40 largo; 0.50 extendido cercano; "
        "0.55 extendido; 0.75 exploratorio; mas 0.45 y 0.65 escritos en linea sin constante propia",
        "Politica interna de comunicacion de incertidumbre. Ninguna fuente respalda estos valores",
        "DESCRIPTIVO. Tras el cierre del 08-08-2026 ninguno de los nueve cortes decide: "
        "`_estado_por_horizonte` dejo de compararlos y en `_clasificar_evidencia_horizonte` el ancho "
        "relativo solo elige el texto de una advertencia. El ancho se publica siempre con su valor. "
        "CORREGIDO el 09-08-2026 (auditoria de fundamentacion, K-01): esta fila seguia atribuyendo a "
        "los cortes de amplitud un efecto de veto sobre el horizonte, y senalando a 0.50 como el mas "
        "restrictivo. Era la descripcion de un comportamiento retirado el 08-08-2026 que se seguia "
        "publicando en la tesis y en el anexo.",
        "Mantener como configurable y descriptivo. CORREGIDO el 04-08-2026: la version "
        "anterior listaba seis valores, omitia 0.50 y omitia los dos literales sin constante.",
    ),
    CriterioEstadistico(
        "C-INT-005",
        "Clasificación del intervalo del 95 % por cobertura empírica",
        "app_icociv/proyeccion/servicio_proyeccion.py; criterios.py",
        TIPO_OPERATIVO,
        # `valor` y `fuente` son las dos columnas que SI se publican en las
        # tablas de la tesis y del anexo, sobre columnas estrechas. Se mantienen
        # cortas a proposito: el detalle vive en `efecto` y `recomendacion`, que
        # no se publican. Alargar estas dos produce overfull hbox.
        "ningun corte de cobertura degrada el horizonte; solo degrada que la "
        "cobertura no sea calculable",
        "Cobertura observada por origen movil (D-12b-C); Hyndman y Koehler (2006)",
        "CIERRE 08-08-2026: los tres cortes de cobertura pierden su papel decisorio. "
        f"{COBERTURA_IC95_ACEPTABLE} ya era descriptivo desde el 07-08. Ahora tambien lo son "
        f"{COBERTURA_IC95_ADVERTENCIA} -que solo elige la redaccion de la advertencia- y "
        f"{MIN_ERRORES_COBERTURA_EMPIRICA}, que pasa a ser una referencia de tamano de muestra. "
        "Ninguno tenia fuente identificada: ninguna referencia fija una cobertura observada "
        "minima por debajo de la cual un intervalo deje de poder comunicarse, ni un numero de "
        "errores por debajo del cual una medicion valida deba ocultarse. Lo unico que sigue "
        "degradando es que la cobertura NO SE PUEDA CALCULAR, que es una imposibilidad y no un "
        "juicio de calidad. La distincion se implementa separando `no_calculable` de "
        "`medida_con_muestra_reducida`.",
        "SUPERADA por P0-C (16-08-2026, V-CODEX-3). Esta recomendacion de 'publicar siempre la "
        "cobertura' es del CIERRE 08-08-2026, anterior a P0-C. Desde P0-C, `resultado["
        "\"cobertura_empirica\"]` se fija a `None` en el limite publico de "
        "`_retirar_intervalo_de_publicacion` (app_icociv/proyeccion/servicio_proyeccion.py): la "
        "cobertura empirica queda fuera de TODA salida (objeto, DataFrame, JSON de sesion, CSV, "
        "interfaz, DOCX, PDF, HTML), no solo de las tablas de la tesis. El calculo permanece dentro "
        "de `_ejecutar_proyeccion_base` como diagnostico interno que no decide nada. "
        f"Mantener {COBERTURA_IC95_ADVERTENCIA} y {MIN_ERRORES_COBERTURA_EMPIRICA} unicamente como "
        "referencias internas del calculo diagnostico, nunca como puertas ni como dato publicado.",
    ),
    CriterioEstadistico(
        "C-SEL-001",
        "Seleccion del modelo por RMSE fuera de muestra global",
        "app_icociv/proyeccion/servicio_proyeccion.py::seleccionar_modelo_por_rmse_oos_global",
        TIPO_BIBLIOGRAFICO,
        "m* = argmin RMSE_global(m) sobre la muestra comun de pares (objetivo, horizonte)",
        "RMSE: Hyndman y Koehler (2006); FPP3 5.8 (medidas dependientes de escala son "
        "las adecuadas dentro de una misma serie). Validacion de origen movil: "
        "Tashman (2000); FPP3 5.10. La muestra de evaluacion es el rango entregable "
        "h=1..h_max, deducido del contrato de un modelo por trayectoria",
        "CIERRE 08-08-2026, H-9. Hasta esta fecha el modelo lo elegia el promedio del RMSE "
        "relativo al mejor de cada horizonte, ponderado con peso 1/h. Ese peso no tenia fuente "
        "-la justificacion era operativa- y cambiaba el modelo entregado, de modo que era la "
        "ultima heuristica decisoria del producto. La regla nueva minimiza la perdida cuadratica "
        "fuera de muestra realmente observada y no tiene ningun parametro libre. La comparacion "
        "se restringe a la muestra comun: los pares (objetivo, horizonte) en los que todos los "
        "candidatos tienen error finito, para que ninguno gane por tener menos observaciones. "
        "Sobre el anexo de mayo de 2026 la perdida por interseccion es 0,00 % en las diez series "
        "y las dos reglas discrepan en una. Ponderacion implicita declarada: cada observacion "
        "pesa igual, pero los horizontes largos aportan errores mayores; en C-05, h=18 pone el "
        "2,6 % de las observaciones y el 8,8 % de la suma de cuadrados. El desempate ante empate "
        "exacto es el orden de aparicion del banco, estable y sin preferencia por identidad. "
        "FUNDAMENTACION DEL CONJUNTO DE EVALUACION (09-08-2026, P0-D). RMSE_global no es una "
        "agregacion de metricas distintas: es el RMSE calculado sobre una MUESTRA DE EVALUACION. "
        "Lo que hay que justificar es la muestra, y esta se deduce del contrato del producto. "
        "SAVIP entrega UN solo modelo por serie y publica TODOS los meses desde h=1 hasta el mes "
        "objetivo que el usuario pida, hasta h_max; verificado sobre C-05: pedir 3, 6, 18 o 24 "
        "meses publica 3, 6, 18 o 24 filas mensuales. La muestra de evaluacion pertinente es por "
        "tanto el conjunto de pronosticos que el modelo tendra que producir: todos los origenes "
        "por todos los horizontes ENTREGABLES, es decir h=1..h_max. La rejilla evaluada coincide "
        "exactamente con ese rango. "
        "POR QUE NO SE ESCALAN LOS ERRORES: el escalado (MASE y similares) resuelve la "
        "comparacion ENTRE SERIES de unidades distintas -es el problema del M4 con 100.000 series-; "
        "FPP3 5.8 es explicito en que para comparar metodos sobre UNA SOLA serie, o series con las "
        "mismas unidades, las medidas dependientes de escala son las adecuadas. Aqui todos los "
        "errores estan en puntos de indice de la misma serie, incluidos los de los modelos que "
        "operan sobre transformaciones, porque el error se mide siempre retransformado a nivel. "
        "LIMITACION DECLARADA: Clements y Hendry (1993) muestran que la comparacion de MSFE "
        "multihorizonte no es invariante ante representaciones isomorfas; evaluar todos los "
        "candidatos en la misma metrica de nivel acota ese problema, no lo elimina. "
        "CORREGIDO el 09-08-2026: una version anterior de esta fila atribuia a la rejilla un "
        "alcance mayor que el del producto. La verificacion mostro que ambos coinciden y esa "
        "atribucion se retira.",
        "Mantener. La muestra de evaluacion se deduce del contrato de un modelo por trayectoria; "
        "si ese contrato cambiara, debe revisarse. No reintroducir pesos por horizonte.",
    ),
    # CORREGIDO 18-08-2026 (pasada mecanica sobre la tesis, item F/G). Esta
    # ficha describia una parada en el primer horizonte no recomendable como
    # vigente. P0-H (16-08-2026) retiro exactamente esa conducta: en el bucle
    # de `_evaluar_horizontes_proyeccion`, el `break` que propagaba el fallo se
    # sustituyo por `continue`, de modo que un horizonte no recomendable ya NO
    # detiene la evaluacion de los posteriores. Verificado por el propio
    # comentario en el codigo ("P0-H, 12-08-2026: era `break`") y por la prueba
    # `test_h1_el_bucle_no_se_detiene_en_el_primer_horizonte_no_recomendable`.
    CriterioEstadistico(
        "C-ALC-001",
        "Continuidad de la evaluacion pese a un horizonte no recomendable (parada retirada)",
        "app_icociv/proyeccion/servicio_proyeccion.py::_evaluar_horizontes_proyeccion",
        TIPO_DERIVACION,
        "el bucle evalua TODOS los horizontes de la rejilla; un horizonte no recomendable no "
        "detiene la evaluacion de los siguientes (continue, no break)",
        "Consecuencia tecnica: cada horizonte tiene su propia evidencia fuera de muestra, "
        "independiente de la de los demas",
        "CIERRE 08-08-2026: tras retirar los vetos sin fuente, lo unico que puede declarar un "
        "horizonte no recomendable son imposibilidades de calculo -banda no valida y similares-. "
        "P0-H, 16-08-2026 (V-CODEX-3): esa imposibilidad puntual DEJO DE PROPAGARSE a los "
        "horizontes posteriores, porque ninguna fuente exige que los horizontes validos formen "
        "un prefijo. Con h1 PASS, h2 FAIL y h3 PASS, h3 se entrega con su propia evidencia.",
        "Mantener. No reintroducir la parada. Prueba: "
        "tests/test_integracion_fhg.py::test_h1_el_bucle_no_se_detiene_en_el_primer_horizonte_no_recomendable.",
    ),
    CriterioEstadistico(
        "C-ALC-002",
        "Horizonte maximo publicado: RETIRADO el prefijo consecutivo",
        "app_icociv/proyeccion/servicio_proyeccion.py::_mayor_horizonte_con",
        TIPO_OPERATIVO_TECNICO,
        "el maximo publicado es el mayor horizonte que cumple con su propia evidencia; "
        "los horizontes validos NO tienen que formar un prefijo",
        "Ninguna fuente exige continuidad; cada horizonte se evalua con su propia muestra de errores",
        "RETIRADO el 16-08-2026 (P0-H, V-CODEX-3). La convencion anterior fijaba el maximo en la "
        "racha inicial sin huecos desde h=1, de modo que un fallo en h=1 lo dejaba en 0 aunque "
        "h=2..24 cumplieran. Se habia conservado 'para no alterar el contrato de salida', razon "
        "que no es un sustento: como enunciado sobre hasta donde usar el resultado, es una "
        "REDUCCION DE HORIZONTE y exige respaldo igual que un bloqueo. Un prefijo continuo no lo "
        "tiene. Ademas producia una salida contradictoria: con h1 tecnico, h2 no viable y h3-h4 "
        "tecnicos, la aplicacion entregaba h=4 y publicaba a la vez 'maximo recomendado: 1'. El "
        "hueco no se oculta: se informa en `primer_horizonte_no_viable` y el horizonte fallido "
        "sigue marcado como no permitido.",
        "Retirado. Guardado conductualmente en tests/test_cierre_metodologico.py y "
        "tests/test_regresiones_auditoria_independiente_bghc.py (H1-H3).",
    ),
    CriterioEstadistico(
        "C-ALC-003",
        "Seleccion del horizonte y del modelo entregados",
        "app_icociv/proyeccion/servicio_proyeccion.py::_seleccionar_horizonte_permitido",
        TIPO_OPERATIVO_TECNICO,
        "mayor horizonte permitido menor o igual al solicitado",
        "Regla de entrega; no es un criterio de calidad",
        "De esa evaluacion sale el objeto de modelo con el que se construye toda la "
        "trayectoria, el ajuste de calendario, los intervalos y la cobertura. Es por tanto la "
        "regla que garantiza UN modelo por trayectoria, propiedad que el proyecto adopto "
        "deliberadamente y que el experimento D-5b rechazo romper.",
        "Mantener. La consistencia de trayectoria se comprueba sobre las diez series.",
    ),
    CriterioEstadistico(
        "C-SAL-001",
        "Salvaguarda por benchmark, retirada como decisora",
        "app_icociv/proyeccion/servicio_proyeccion.py::_aplicar_salvaguarda_benchmarks",
        TIPO_OPERATIVO,
        "diagnostico: evalua drift y naive y publica el resultado; no sustituye",
        "Decision operativa D-3; el criterio de aceptacion no tenia fuente",
        "Hasta el 08-08-2026 sustituia el modelo principal en TODA la trayectoria cuando un "
        "benchmark ampliaba el horizonte admisible (h_bench > h_antes): mas horizonte, no menos "
        "error. Sobre el anexo de mayo entregaba un Drift con RMSE peor que el modelo "
        "descartado en h=3, 6, 12 y 18 -hasta un 78 % peor en h=18- y fabricaba los diez "
        "benchmarks que la regla de h>=13 despues castigaba. Se retira la sustitucion y se "
        "conserva el diagnostico: que horizontes no cubre el principal y hasta donde llegaria "
        "un benchmark.",
        "Mantener solo como diagnostico. El modelo entregado es el que selecciona el desempeno "
        "fuera de muestra.",
    ),
    CriterioEstadistico(
        "C-HOR-001",
        "Horizontes operativos de interfaz",
        "app_icociv/interfaz (valores propios de cada widget)",
        TIPO_MUERTO,
        "1, 3, 6, 12, 18",
        "Decisión de UX institucional",
        "No decide nada: la constante HORIZONTES_OPERATIVOS_UI se definia en este modulo y ningun widget la leia. "
        "Los accesos rapidos de la interfaz llevan sus propios valores.",
        "Constante retirada el 04-08-2026. La fila se conserva para dejar constancia de que este criterio no "
        "gobernaba la interfaz; el máximo se calcula dinamicamente.",
    ),
    CriterioEstadistico(
        "C-HOR-002",
        "Límite de búsqueda del horizonte",
        "app_icociv/proyeccion/servicio_proyeccion.py::_limites_auditoria_horizontes",
        TIPO_OPERATIVO_TECNICO,
        "HORIZONTE_MAXIMO_AUDITORIA = 30 meses, constante",
        "Politica computacional interna",
        "Acota el costo computacional de la busqueda. No lo modula la longitud historica.",
        "Mantener como parámetro técnico; no confundir con horizonte recomendado. CORREGIDO el 04-08-2026: la "
        "version anterior describia una busqueda escalonada 18/24/30 segun 84 o 96 observaciones que el codigo "
        "nunca implemento; sus cinco constantes estaban muertas y se retiraron.",
    ),
    CriterioEstadistico(
        "C-HOR-003",
        "Niveles de evidencia fuera de muestra por horizonte",
        "app_icociv/proyeccion/servicio_proyeccion.py",
        TIPO_OPERATIVO,
        "0 ventanas (h > n - N0): no evaluable, por inexistencia del error fuera de muestra; "
        "1 o mas: se entrega, con el numero de ventanas declarado",
        "Derivacion aritmetica: evaluar h con ventana expansiva exige n - N0 - h + 1 >= 1, "
        "luego h <= n - N0. Por encima no existe ningun error fuera de muestra que medir",
        "CIERRE 08-08-2026: el nivel intermedio dejo de degradar. Que un horizonte tenga entre "
        f"{MIN_ITERACIONES_WF_ESCENARIO} y {MIN_ITERACIONES_WF - 1} ventanas hace su error menos "
        "estable, y eso se advierte con el numero exacto; no lo hace incalculable. "
        "CORREGIDO el 16-08-2026 (P0-G, V-CODEX-3): hasta esa fecha esta ficha declaraba que "
        f"'el unico corte que sigue decidiendo es {MIN_ITERACIONES_WF_ESCENARIO}', y su propia "
        "justificacion lo delataba: la derivacion citada -desviacion tipica muestral con n >= 2 y "
        "evaluacion de cobertura por origen movil con n-2 contrastes- es la del INTERVALO y su "
        "verificacion, eje que P0-C retiro del producto. Un requisito de la BANDA estaba "
        "recortando los horizontes en que se entrega el PUNTO, que no depende de las ventanas "
        "sino del ajuste. Codex lo demostro end-to-end: con n=8 y h=2 la rejilla quedaba en (1,) "
        "y `proyeccion_generada` era False pese a existir un punto finito. El corte pasa a ser la "
        "cota de existencia, que no es un umbral elegido. "
        f"`MIN_ITERACIONES_WF_ESCENARIO` = {MIN_ITERACIONES_WF_ESCENARIO} y "
        f"`MIN_ITERACIONES_WF` = {MIN_ITERACIONES_WF} NO desaparecen: sobreviven como cortes "
        "DESCRIPTIVOS con los que se comunica cuanta evidencia sostiene el horizonte. "
        "Sigue distinguiendo 'no se pudo medir' de 'se midio y salio mal'.",
        "Mantener la cota de existencia, que es aritmetica; el resto es informacion publicada.",
    ),
    CriterioEstadistico(
        "C-MOD-002",
        "Parametros de Holt estimados por minimizacion del SSE",
        "app_icociv/estadistica/modelos_interpretables.py::estimar_parametros_holt",
        TIPO_BIBLIOGRAFICO,
        "alpha, beta*, l0 y b0 estimados; phi estimado en [0.80, 0.98] en la variante amortiguada; "
        "restriccion 0 < beta* <= alpha",
        "Hyndman y Athanasopoulos (2021), FPP3, secciones 8.1-8.2; Gardner (2006), Exponential "
        "smoothing: the state of the art - Part II",
        "CORREGIDO el 09-08-2026 (auditoria de fundamentacion, C-01). Hasta esta fecha los "
        "coeficientes eran constantes fijadas internamente -alpha=0,65; beta=0,20; phi=0,88- SIN "
        "FUENTE, mientras el metodo se publicaba como «Holt» citando a FPP3, que lo define "
        "estimandolos: «The smoothing parameters, alpha and beta*, and the initial values l0 and b0 "
        "are estimated by minimising the SSE for the one-step training errors». Gardner (2006) es "
        "explicito: «there is no longer any excuse for using arbitrary parameters». Se sustituye la "
        "parametrizacion fija por la estimacion que la fuente define; lo unico que queda fijado son "
        "las COTAS, que si tienen fuente. La estimacion se repite en CADA origen del backtesting con "
        "solo la historia previa, y de nuevo con toda la historia para el pronostico final, de modo "
        "que no hay fuga. Es determinista -rejilla gruesa fija mas refinamiento local- y no depende "
        "del entorno, con lo que el hallazgo H-01 sigue cerrado. Medicion: sobre las diez series el "
        "optimo satura alpha->1 y beta->0, es decir, Holt correctamente estimado se aproxima a un "
        "paseo aleatorio con deriva en estas series; en C-05 el SSE baja de 112,90 a 73,92.",
        "Mantener. Los parametros son estimados por serie y por origen; publicarlos como tales. No "
        "reintroducir constantes fijas sin una fuente que las respalde.",
    ),
    CriterioEstadistico(
        # CORREGIDO 17-08-2026 (cierre documental). Esta ficha describia la
        # ACTIVACION POR NIVELES como vigente, y se publica en las dos tablas
        # LaTeX auditables. P0-B la retiro el 09-08-2026: los siete literales que
        # la gobernaban -`horizonte>=7`, `volatilidad>0.035`, `n_obs>=48`,
        # `MIN_OBS_NIVEL_2=24`, `volatilidad>0.05`, `horizonte<=6 and n_obs>=24` y
        # `MIN_OBS_HUBER=8`- decidian QUE MODELOS COMPETIAN y, por esa via, cual
        # podia ganar. Hoy `_modelos_para_analisis` devuelve el catalogo completo
        # sin condicion alguna. Solo cambia lo que la ficha AFIRMA; el
        # comportamiento no se toca.
        "C-MOD-001",
        "Elegibilidad de candidatos por estimabilidad (activación por niveles retirada)",
        "app_icociv/proyeccion/servicio_proyeccion.py; modelos_interpretables.py",
        TIPO_DERIVACION,
        "Compiten los 10 candidatos del catalogo; un modelo se excluye solo si n < N_min(m), "
        "derivado de su propia formulacion",
        "N_min se deriva por familia, no por una regla unica: forma cerrada (naive, drift) exige "
        "solo que existan las observaciones que la formula usa; ajuste por minimizacion (OLS, "
        "Huber, Holt) exige n >= k + 1 contando TODO parametro estimado -en Huber tambien la "
        "escala; en Holt tambien alpha, beta*, phi y los dos estados iniciales-; y los modelos "
        "sobre variaciones exigen ademas un minimo de variaciones finitas",
        "La elegibilidad es una condicion de calculo, no una decision de producto. Retirada la "
        "activacion por niveles (P0-B), ningun literal sin fuente decide que modelos compiten.",
        "Mantener. No reintroducir activacion condicionada por horizonte, longitud ni alertas.",
    ),
    CriterioEstadistico(
        "C-BEN-001",
        "Comparación contra Naive/Drift: constantes retiradas de la logica decisoria",
        "app_icociv/estadistica/criterios.py (constantes sin consumidor decisorio)",
        TIPO_MUERTO,
        "ningun corte vigente; la lectura viva es C-BEN-002 frente a 1",
        "Sin fuente para 1,10 ni para 1,25; el inventario RC3 los declaro margen de gracia sin fuente",
        "CORREGIDO el 09-08-2026 (auditoria de fundamentacion, K-02). Esta fila seguia publicando "
        f"«favorable <= {TOLERANCIA_RRMSE_BENCHMARK}; peor > {UMBRAL_RRMSE_PEOR_BENCHMARK}» como "
        "criterio vigente y contradecia a C-BEN-002 en la misma tabla. El cierre del 08-08-2026 "
        "retiro ambos cortes de la logica decisoria; las constantes siguen definidas en el modulo "
        "pero ninguna funcion decisoria las consulta, extremo que fija "
        "tests/test_cierre_metodologico.py.",
        "No reintroducir. La comparacion viva frente a benchmarks es C-BEN-002, descriptiva y "
        "leida frente a 1.",
    ),
    CriterioEstadistico(
        "C-BEN-002",
        "Error relativo frente al benchmark, lectura descriptiva",
        "app_icociv/proyeccion/servicio_proyeccion.py::peor_que_benchmark_naive",
        TIPO_BIBLIOGRAFICO,
        "no es_benchmark y rRMSE frente a naive > 1; se informa, no decide",
        "Hyndman y Koehler (2006): el error relativo se define frente a UN metodo de "
        "referencia y 1 es su punto de equivalencia",
        "Historia en dos pasos. El 08-08-2026 se unificaron dos lecturas redundantes -una miraba "
        "solo naive sin eximir a los benchmarks; la otra usaba el minimo sobre naive y drift, que "
        "no corresponde a ninguna definicion publicada- en una puerta unica con el corte 1.25. Ese "
        "mismo dia se cerro que 1.25 no tiene fuente identificada: el inventario RC3 ya lo habia "
        "declarado margen de gracia sin fuente. CIERRE 08-08-2026: se retira el corte y se retira "
        "el bloqueo. Lo que la definicion publicada sustenta es la metrica y su lectura frente a "
        "1; lo que no sustenta es convertir esa lectura en un veto. El modelo lo elige el "
        "desempeno fuera de muestra agregado; esta lectura solo informa, por horizonte, si el "
        "modelo quedo por encima o por debajo de su referencia.",
        "Mantener como metrica publicada. No reintroducir ningun margen de gracia sobre el 1.",
    ),
    CriterioEstadistico(
        "C-CAL-001",
        "Detección del salto de cambio de anio",
        "app_icociv/estadistica/calendario_anual.py",
        TIPO_OPERATIVO,
        f">= {MIN_TRANSICIONES_SALTO_ANUAL} transiciones; ratio > {RATIO_SALTO_ANUAL}; "
        f"signo >= {CONSISTENCIA_SIGNO_SALTO_ANUAL}",
        "Estadística robusta (medianas); calibrado con el anexo ICOCIV de mayo de 2026",
        "Exige recurrencia y consistencia para distinguir efecto calendario de un atípico aislado.",
        "Mantener como criterio interno calibrado; revisar si cambia la metodología DANE.",
    ),
    # CORREGIDO 17-08-2026 (V-CODEX-R3, residual 5). Esta ficha describia la
    # salvaguarda como VIGENTE y se publica en las dos tablas LaTeX auditables,
    # de modo que la tesis afirmaba que el ajuste se aplica cuando no deteriora
    # el error. P0-F lo retiro el 12-08-2026: `aplicado = False` de forma
    # incondicional, y la salvaguarda no llega a evaluarse sobre el pronostico.
    CriterioEstadistico(
        "C-CAL-002",
        "Tratamiento del salto de cambio de año: RETIRADO, no se aplica",
        "app_icociv/estadística/calendario_anual.py; servicio_proyeccion.py",
        TIPO_OPERATIVO,
        "aplicado = False de forma incondicional; y_ajustado = y_futuro",
        "P0-F, 12-08-2026: ningun componente del tratamiento tiene sustento completo "
        "(gamma como estimador del salto futuro, la forma del factor, las puertas de "
        "activacion calibradas sobre el propio anexo y el conjunto de validacion)",
        "La trayectoria entregada es la del modelo base. El perfil se mide y se publica "
        "como diagnostico; no modifica el pronostico. La salvaguarda por backtesting no "
        "llega a evaluarse porque el ajuste no se aplica en ningun caso.",
        "No reintroducir. Falta un metodo publicado para tratar el fenomeno, que si esta "
        "medido; es una limitacion declarada, no un pendiente de implementacion.",
    ),
    CriterioEstadistico(
        "C-CAL-003",
        "Separacion entre patron detectado y efecto en el horizonte",
        "app_icociv/estadistica/calendario_anual.py",
        TIPO_OPERATIVO,
        "patron_detectado_en_serie, horizonte_cruza_cambio_anio y efecto_en_horizonte_solicitado se informan por separado",
        "Politica interna autorizada el 29-jul-2026 (hallazgo H-10); redaccion completada el 14-08-2026",
        "Tres hechos distintos, cada uno con su campo. (1) El PATRON es una propiedad de la serie y se detecta con independencia del horizonte: patron_detectado_en_serie. (2) La GEOMETRIA temporal del horizonte pedido: eneros_en_horizonte cuenta los eneros contenidos y horizonte_cruza_cambio_anio indica si hay al menos uno; ninguno depende del tratamiento. (3) El EFECTO del tratamiento aplicado: efecto_en_horizonte_solicitado = (tratamiento aplicado) Y (eneros > 0). Al exigir las DOS condiciones, un horizonte que cruza enero puede tener efecto=False si no se aplica ningun tratamiento, que es la situacion vigente desde que P0-F retiro el ajuste por falta de sustento. El factor se aplicaba por paso, de modo que los meses comunes valian lo mismo al pedir 3, 6, 12 o 18 meses.",
        "Mantener; no reintroducir una condicion sobre el horizonte total (cruza_enero) ni leer efecto_en_horizonte_solicitado como sinonimo de cruce de anio.",
    ),
    CriterioEstadistico(
        "C-EST-001",
        "Estabilidad del error entre ventanas (coeficiente de variación)",
        "app_icociv/estadistica/analisis_series.py; proyeccion/servicio_proyeccion.py",
        TIPO_OPERATIVO,
        f"inestable > {UMBRAL_ESTABILIDAD_INESTABLE}",
        "Coeficiente de variación de |errores| OOS; parámetro interno",
        "Detecta desempeño erratico entre origenes aunque el promedio sea aceptable. Emite advertencia.",
        "Mantener como configurable; reportar junto a las métricas. CORREGIDO el 04-08-2026: el corte de "
        "'favorable <= 0,75' figuraba en esta fila pero su constante estaba muerta y se retiro; solo el corte "
        "de inestabilidad se consulta.",
    ),
)


def matriz_criterios() -> tuple[CriterioEstadistico, ...]:
    """Devuelve la matriz de criterios estadisticos."""
    return CRITERIOS_ESTADISTICOS


def validar_tipos_criterios(
    criterios: Iterable[CriterioEstadistico] = CRITERIOS_ESTADISTICOS,
) -> None:
    """Comprueba que todo ``tipo`` sea uno de los siete estados admitidos.

    Impide que una fila reaparezca con una categoria inventada, que es como la
    matriz llego a describir calculos que el codigo no ejecutaba.
    """
    invalidos = sorted({c.tipo for c in criterios if c.tipo not in TIPOS_ADMITIDOS})
    if invalidos:
        raise ValueError(
            "Tipos de criterio no admitidos: "
            + ", ".join(invalidos)
            + ". Admitidos: "
            + ", ".join(sorted(TIPOS_ADMITIDOS))
        )


def exportar_matriz_criterios_markdown(ruta: str | Path) -> Path:
    """Exporta la matriz de criterios a Markdown."""
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(generar_markdown_criterios(CRITERIOS_ESTADISTICOS), encoding="utf-8")
    return destino


def generar_markdown_criterios(criterios: Iterable[CriterioEstadistico] = CRITERIOS_ESTADISTICOS) -> str:
    """Construye la tabla Markdown solicitada para auditoria."""
    encabezado = (
        "# Auditoria de criterios estadísticos ICOCIV\n\n"
        "Esta matriz distingue criterios bibliograficos, estándares estadísticos, "
        "parámetros computacionales y reglas operativas internas. Los criterios "
        "operativos no deben presentarse como verdades universales; son parámetros "
        "documentados y configurables de la aplicación.\n\n"
        "| ID | Criterio | Ubicacion en código/documento | Tipo de criterio | Valor o umbral | Fuente o sustento | Justificación | Accion |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    cuerpo = "\n".join(criterio.como_fila_markdown() for criterio in criterios)
    return encabezado + cuerpo + "\n"


def _escapar_md(valor: object) -> str:
    texto = str(valor).replace("\n", " ").strip()
    return texto.replace("|", "\\|")
