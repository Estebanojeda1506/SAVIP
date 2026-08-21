# Sistema visual de SAVIP

Referencia del lenguaje visual de la aplicación. Fecha: 26 de julio de 2026.
Framework: **PySide6 6.11 sobre Qt Widgets** (no QML).

---

## 1. Identidad

**Concepto: «la línea que sube y el dato que la sostiene».** El lenguaje se
construye sobre los elementos propios de una serie temporal —trazo ascendente,
banda de intervalo, nodo de dato— y no sobre metáforas literales de obra civil.

El **isotipo** materializa ese concepto: una curva de índice con inflexión, la
banda de intervalo abriéndose bajo el trazo y el nodo de dato proyectado en el
extremo, sobre un cuadrado redondeado con el degradado profundo de la rampa. Se
genera por código (`scripts/generar_isotipo.py`) para heredar siempre la paleta
y poder rehacerse a cualquier tamaño; verificado legible desde 16 px.

La franja de la pantalla de inicio dibuja **la serie que el usuario tiene
cargada**: la identidad la generan sus datos, no una ilustración prestada. Con
menos de dos observaciones no se dibuja nada.

El isotipo anterior se sustituyó en esta segunda iteración; el **nombre SAVIP
se conserva sin cambios**. El archivo previo quedó respaldado fuera del
repositorio antes de regenerarlo.

Inspiración declarada: los principios de superficie redondeada, jerarquía por
elevación y movimiento breve de One UI. **No se copió** ningún recurso, icono,
paleta, tipografía ni componente de Samsung, ni su disposición característica.

---

## 2. Arquitectura

```text
app_icociv/interfaz/
├── tema/
│   ├── tokens.py        Espaciado, radios, elevación, movimiento, tipografía
│   ├── colores.py       Paletas claro/oscuro, utilidades rgba/mezcla/contraste
│   ├── tipografia.py    Resolución de familias contra el sistema
│   ├── plantilla.qss    Hoja con marcadores; sin un solo color literal
│   └── estilos.py       Compone y valida la hoja del tema activo
├── componentes/
│   ├── tarjetas.py      Tarjeta, TarjetaMetrica
│   ├── navegacion.py    NavegacionLateral, CabeceraApp
│   ├── notificaciones.py  Notificacion, GestorNotificaciones
│   ├── carga.py         VeloCarga
│   └── inicio.py        PantallaInicio, FranjaSerie, TarjetaDato
├── animaciones/
│   ├── transiciones.py      Desvanecidos, deslizamientos, cambios de tamaño
│   └── microinteracciones.py  Elevación y realimentación de contacto
├── efectos/
│   └── ventana.py       Mica, modo oscuro nativo, alto contraste
└── estilos/
    └── constantes_visuales.py  Capa de compatibilidad con la API anterior
```

`estilos/constantes_visuales.py` se conserva porque varios módulos importan de
ahí: reexporta los tokens y `paleta_tema` devuelve la paleta nueva **más los
alias históricos** (`fondo_secundario`, `bordes`, `acento`, `grafica`…), de modo
que el código existente sigue funcionando sin tocarlo.

### Por qué desapareció `estilo.qss`

El sistema anterior escribía los colores en hexadecimal dentro del QSS y
obtenía el tema oscuro **reemplazando cadena por cadena**. Bastaba con
introducir un color nuevo sin registrarlo en el diccionario de sustituciones
para que quedara fijado en claro dentro del tema oscuro. La plantilla actual no
admite colores literales y `validar_plantilla()` lo comprueba; la prueba
`test_plantilla_sin_colores_literales` impide la regresión.

---

## 3. Color

La paleta deriva de la **referencia cromática aportada por el usuario**: una
rampa teal de croma 36 del negro al casi blanco, sobre fondo crema cálido.

```text
#000000  #04222A  #073540  #0A4C5C  #0E6E7C  #2A8296  #4A97A8
#6BAEC0  #8CC8DC  #A9DEF0  #C4EBFA  #DDF3FC  #F2FAFE      crema #FAF7F2
```

La rampa está en `colores.RAMPA`, indexada por posición (`t05`…`t95`), y la
paleta la cita en lugar de repetir hexadecimales sueltos.

### Marca

| Rol | Claro | Oscuro |
|---|---|---|
| Principal | `#0E6E7C` (t30) | `#6BAEC0` (t60) |
| Secundario | `#2A8296` (t40) | `#4A97A8` (t50) |
| Acento | `#2A8296` (t40) | `#8CC8DC` (t70) |

**El morado se retiró por completo.** Antes el foco y la selección usaban
`#5B4BD6`/`#9A8CFF`, ajenos al tronco cromático. Ahora el foco es teal profundo
(`t20`) en claro y **blanco suave** (`t95`) en oscuro, que es el realce más
sobrio sobre fondo profundo.

### Estado

| Rol | Claro | Oscuro |
|---|---|---|
| Éxito | `#1A6B4F` | `#4CC397` |
| Advertencia | `#8A5709` | `#E0A54B` |
| Error | `#A33129` | `#ED8177` |

Desaturados a propósito para convivir con la paleta fría. El color **nunca es el
único portador de significado**: cada estado lleva símbolo (`OK`, `!`, `×`, `i`)
y las series de la gráfica se distinguen también por marcador y trazo.

### Superficies

**Claro** — gris azulado muy claro y neutro:

| Token | Valor | Uso |
|---|---|---|
| `fondo` | `#F4F7F8` | Área de contenido |
| `barra_lateral` | `#FFFFFF` | Panel de navegación y cabecera |
| `superficie` | `#FFFFFF` | Tarjetas |
| `superficie_2` | `#F1F5F6` | Superficies secundarias |
| `superficie_3` | `#E7EEF0` | Encabezados de tabla, chips |

El crema de la referencia se probó como fondo pero tiraba a amarillo en
pantalla. Se conserva el teal frío de acción y se descarta la calidez del fondo.

**Oscuro** — negro grafito de fondo, teal profundo en las tarjetas:

| Token | Valor | Uso |
|---|---|---|
| `fondo` | `#0B0E10` | Área de contenido |
| `barra_lateral` | `#12181B` | Panel de navegación, cabecera y menús |
| `superficie` | `#072C34` | Tarjetas |
| `superficie_2` | `#0A353F` | Superficies secundarias |
| `superficie_3` | `#0E404C` | Elevadas |

**Este es el arreglo del contraste en oscuro.** Antes fondo y tarjeta compartían
el azul verdoso de la rampa y la ventana entera se leía como una sola masa de
color; ahora el grafito del fondo despega las tarjetas sin perder la identidad
turquesa.

### Jerarquía de profundidad dentro de una vista

La superficie de una tarjeta no sirve para un formulario que ocupa la pantalla
entera: a esa escala el teal deja de ser acento y se vuelve fondo. Por eso hay
tres niveles distintos, no uno:

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `superficie` | `#FFFFFF` | `#072C34` | Tarjetas de dato y portada; teal de identidad |
| `superficie_formulario` | `#FFFFFF` | `#0F1A1D` | Contenedores de formulario (`QGroupBox`) |
| `campo` | `#F5F8F9` | `#070F12` | Controles de entrada; se hunden en su contenedor |

En Empalme y Proyecciones los campos compartían tono con su contenedor y el
módulo entero se leía como una masa plana. Ahora el campo se hunde y el
contenedor apenas se eleva sobre el fondo.

`deshabilitado` es más apagado que cualquier superficie: antes usaba
`superficie_3`, más claro que los controles activos, de modo que un control
inhabilitado destacaba más que uno usable.

### Áreas de desplazamiento

Un `QScrollArea` sin fondo declarado hereda la paleta del sistema, que en
Windows con tema oscuro es negra. Ocurrió dos veces durante el rediseño —panel
de navegación y módulo de Empalme— y en ambos casos el módulo salía en negro
sobre el tema claro. La plantilla incluye una **regla general** para todo
`QScrollArea` y su widget interno, que cubre también los scroll sin nombre que
crean los widgets de módulo. `test_las_areas_de_desplazamiento_declaran_fondo`
impide que desaparezca.

### Tokens de interacción

`acento_hover`, `acento_presionado`, `navegacion_seleccionada` y
`navegacion_hover` tienen valor propio por tema, en lugar de derivarse de una
opacidad genérica sobre el texto.

### Contraste medido

| Tema | Texto sobre superficies | Secundario | Acentos |
|---|---|---|---|
| Claro | ≥ 14,10:1 | ≥ 5,65:1 | ≥ 4,44:1 |
| Oscuro | ≥ 9,51:1 | ≥ 5,57:1 | ≥ 4,43:1 |

Medido sobre las cinco superficies, incluida la barra lateral.

Todo por encima de WCAG AA. Verificado en `test_contraste_de_texto_cumple_wcag_aa`.

## 4. Forma y ritmo

Escala de espaciado de **base 4** (`ESPACIO_1`=4 … `ESPACIO_8`=40). No hay
excepciones: `test_escala_de_espaciado_es_multiplo_de_cuatro` lo garantiza.

Radios: `pequeño 6` (controles menores), `medio 10` (controles y menús),
`grande 14` (tarjetas), `extra 20` (portada), `píldora 999`.
Un radio uniforme en todo haría que los controles parecieran hinchados.

Controles: alto de **38 px** (44 en botones grandes), navegación de 42 px.

---

## 5. Elevación

QSS **no admite `box-shadow`**: la sombra se aplica con
`QGraphicsDropShadowEffect`, que es costoso, así que se reserva a superficies de
primer nivel (tarjetas, panel de carga, notificaciones) y **nunca** a filas de
tabla ni a controles repetidos.

| Nivel | Desenfoque | Desplazamiento | Opacidad | Uso |
|---|---|---|---|---|
| 1 | 12 | 2 | 0.06 | Tarjetas en reposo |
| 2 | 22 | 4 | 0.10 | Tarjeta con cursor encima, avisos |
| 3 | 34 | 8 | 0.14 | Panel de carga |

Un widget solo admite **un** `QGraphicsEffect`: como las animaciones de opacidad
también usan uno, el efecto de sombra se retira antes de desvanecer.
`establecer_sombras(False)` degrada todo a bordes.

---

## 6. Movimiento

Qt Widgets **no admite transiciones CSS**. Se anima lo que Qt puede interpolar
—geometría, opacidad, tamaños— y los cambios de color de `hover`/`pressed` se
resuelven en la hoja de estilos, de forma instantánea por diseño del framework.

| Interacción | Duración | Curva |
|---|---|---|
| Microinteracción | 140 ms | OutCubic |
| Cambio de vista | 200 ms | OutCubic |
| Panel lateral | 240 ms | InOutCubic |
| Entrada escalonada | 180 ms + 40 de retardo | OutCubic |
| Aviso | 220 ms | OutCubic |

Las animaciones vivas se guardan en un conjunto: sin una referencia, el
recolector de Python las destruye a mitad y el widget queda a medio camino.

**Movimiento reducido**: `establecer_movimiento_reducido(True)` no omite el
efecto, aplica su **estado final**. Ninguna función depende de que una animación
llegue a ejecutarse. Se sincroniza con la opción de accesibilidad de Windows
(`SPI_GETCLIENTAREAANIMATION`) al arrancar.

---

## 7. Transparencia y material

**Simulada** (estable en cualquier Windows): `rgba()` sobre superficie sólida en
cabecera, separadores y velo de carga.

**Real (Mica)**: solo en el fondo de la ventana, solo en **Windows 11 build
22621 o superior**, mediante `DwmSetWindowAttribute` con
`DWMWA_SYSTEMBACKDROP_TYPE`, que es API documentada.

Se **descartó** el atajo habitual para Windows 10
(`SetWindowCompositionAttribute`): es una función no documentada y produce
parpadeos al redimensionar.

Nunca se aplica transparencia detrás de tablas de datos ni de la gráfica.

---

## 8. Degradación

| Situación | Comportamiento |
|---|---|
| Sin Mica | Fondo opaco; el resto idéntico |
| Movimiento reducido | Estado final inmediato |
| Alto contraste de Windows | Sin sombras y sin movimiento |
| Sombras desactivadas | Bordes en lugar de elevación |
| Sin fuente preferida | Siguiente familia de la lista |

Detección en `efectos/ventana.py`; ningún fallo impide que la ventana abra.

---

## 9. Estructura de la ventana

```text
┌─ Barra de menú (Qt) ─────────────────────────────────┐
├─ CabeceraApp: logo · SAVIP/vista · estado · tema ────┤
├──────────────┬───────────────────────────────────────┤
│ Navegación   │ Área de contenido                     │
│ + archivo    │ (4 vistas apiladas)                   │
│ + sesión     │                                       │
└──────────────┴───────────────────────────────────────┘
```

Vistas: **Inicio**, Resultados, Proyecciones ICOCIV, Empalme ICCP-ICOCIV.

**Una sola columna lateral, con la navegación primero.** Cargar archivo, abrir y
guardar sesión vivían en una segunda columna dedicada solo a eso; ahora son
acciones del propio panel, **debajo** de las entradas de módulo, tras un
separador y bajo el rótulo «Archivo y sesiones». El orden importa: los módulos
son el destino y el archivo es el medio, así que se leen en ese orden.

Cargar conserva el estilo de acción principal dentro de su grupo; abrir y
guardar pasan a secundarias para no competir con la navegación.

Al contraer se contrae todo junto: las entradas quedan en su inicial, los
botones en una marca corta (`＋`, `↥`, `↧`) y los nombres pasan al tooltip. El
contenido va dentro de un `QScrollArea`, de modo que con poca altura el panel se
desplaza en lugar de recortar entradas; el control de contraer vive fuera de esa
área y permanece siempre visible. El orden de tabulación se fija explícitamente
para seguir el orden visual, no el de creación de los widgets.

`seleccionar()` emite la señal de navegación además de marcar la entrada;
`marcar_seleccion()` solo refleja el estado. Esa distinción es lo que hace que
los accesos rápidos naveguen de verdad: `setChecked` por sí solo no emite
`idClicked`, que Qt reserva a los clics del usuario.

---

## 10. Reglas para quien continúe

1. Ningún color ni medida literal fuera de `tema/`. Si hace falta un valor
   nuevo, se añade como token.
2. La plantilla QSS usa `{{ }}` para llaves literales: se resuelve con
   `str.format` y una llave simple delimita un token.
3. Sombra solo en superficies de primer nivel.
4. Toda animación debe funcionar con el movimiento desactivado.
5. El estado nunca se comunica solo con color.
6. Un recurso nuevo se declara en `packaging/SAVIP.spec` **y** en
   `tests/test_rutas_empaquetado.py`.
