# Guía de compilación del ejecutable de Windows

Procedimiento reproducible para generar `SAVIP.exe` a partir del código fuente.
El ejecutable **no reemplaza al repositorio**: el código, la documentación, las
pruebas y el historial de Git siguen siendo la fuente de verdad, y cada versión
del ejecutable se regenera desde ellos.

Última actualización: 23 de julio de 2026 · Versión generada: `0.1.0-beta`

---

## 1. Herramienta elegida: PyInstaller

Se evaluaron tres alternativas:

| Herramienta | Valoración |
|---|---|
| **PyInstaller** | **Elegida.** Hooks oficiales para PySide6, pandas, matplotlib, scikit-learn y openpyxl, ya incluidos. Recompilación rápida, depuración sencilla (modo consola) e inclusión declarativa de datos mediante `.spec` versionable. |
| Nuitka | Compila a C y puede producir binarios más rápidos, pero cada compilación tarda mucho más, lo que penaliza el ciclo de iteración. Ventaja de rendimiento irrelevante aquí: el costo está en el cálculo estadístico, no en el arranque. |
| cx_Freeze | Soporte de Qt6 más débil y menos hooks mantenidos para el conjunto científico del proyecto; exigiría resolver a mano dependencias que PyInstaller ya cubre. |

Se prioriza la facilidad de mantenimiento porque el ejecutable deberá
regenerarse cada vez que cambie la aplicación.

## 2. Requisitos

- Windows 10 u 11 de 64 bits.
- Python 3.12 (probado con 3.12.10); el script exige 3.10 o superior.
- PowerShell (incluido en Windows).
- Unos 2 GB libres en disco para el entorno de compilación y las salidas.

No hace falta instalar PyInstaller a mano: el script lo instala dentro de un
entorno virtual dedicado.

## 3. Compilación

Desde la raíz del repositorio:

```powershell
.\scripts\build_exe.ps1
```

Eso es todo. El script realiza, en orden:

1. Verifica la versión de Python.
2. Lee la versión de la aplicación desde `VERSION`.
3. Crea o reutiliza el entorno virtual `.venv-build`.
4. Instala `requirements.txt` y `requirements-build.txt` en ese entorno.
5. Ejecuta las pruebas mínimas previas.
6. Limpia `build/` y `dist/`.
7. Ejecuta PyInstaller con `packaging/SAVIP.spec`.
8. Copia la distribución a `release/SAVIP-<VERSION>-windows/`.
9. Añade `README_EJECUTABLE.txt` y genera `VERSION.txt`.
10. Verifica que el ejecutable y los recursos internos estén presentes.
11. Ejecuta la autocomprobación sobre el ejecutable ya empaquetado.

Opciones:

```powershell
.\scripts\build_exe.ps1 -Diagnostico   # genera SAVIP-debug.exe con consola
.\scripts\build_exe.ps1 -Recrear       # recrea .venv-build desde cero
.\scripts\build_exe.ps1 -SinPruebas    # omite las pruebas previas
```

Desde `cmd.exe`: `scripts\build_exe.bat` (o `scripts\build_exe.bat diagnostico`).

### Por qué se compila en un entorno virtual dedicado

PyInstaller empaqueta lo que encuentra instalado en el intérprete que lo
ejecuta. En una primera compilación con el Python global de este equipo, la
distribución alcanzó **4168 MB** porque arrastró PyTorch, torchvision,
onnxruntime y pyarrow, ninguno usado por el proyecto. Con `.venv-build`, que
solo contiene lo declarado en `requirements.txt`, la distribución baja a
**284 MB**. Por eso el script nunca usa el Python global.

Como defensa adicional, `packaging/SAVIP.spec` excluye explícitamente esas
librerías, por si alguien compila fuera del entorno dedicado.

## 4. Empaquetado para distribuir

```powershell
.\scripts\package_release.ps1
```

Genera:

- `release/SAVIP-<VERSION>-windows.zip`
- `release/SAVIP-<VERSION>-windows.zip.sha256`

El ZIP contiene solo la distribución: no incluye código fuente, entorno
virtual, archivos de construcción ni el repositorio `.git`.

## 5. Limpieza

```powershell
.\scripts\clean_build.ps1                     # borra build/ y dist/
.\scripts\clean_build.ps1 -TodoIncluidoRelease  # borra además release/
```

Nunca toca el código fuente, `packaging/SAVIP.spec` ni los scripts.

## 6. Estructura de la salida

```
release/SAVIP-0.1.0-beta-windows/
├── SAVIP.exe                  ejecutable principal (sin consola)
├── VERSION.txt                 versión, fecha y entorno de compilación
├── README_EJECUTABLE.txt       instrucciones para el usuario final
└── _internal/                  dependencias y recursos empaquetados
    ├── VERSION
    ├── app_icociv/datos/iccp_historico.json
    ├── app_icociv/interfaz/estilos/estilo.qss
    ├── PySide6/, pandas/, numpy/, scipy/, sklearn/, matplotlib/, docx/ ...
    └── (DLL y bibliotecas de Python)
```

La carpeta completa debe mantenerse junta: `SAVIP.exe` necesita `_internal`.

## 7. Clasificación de archivos

### Recursos internos (viajan con la aplicación, solo lectura)

| Recurso | Ruta en el repositorio |
|---|---|
| Anexo 10 ICCP histórico | `app_icociv/datos/iccp_historico.json` |
| Hoja de estilos de la interfaz | `app_icociv/interfaz/estilos/estilo.qss` |
| Versión | `VERSION` |

Se declaran en la lista `datas` de `packaging/SAVIP.spec`, conservando la
misma ruta relativa que en el repositorio, porque `ruta_recurso()` los busca
con esa estructura.

### Archivos que selecciona el usuario (nunca se empaquetan)

Anexos ICOCIV (`.xlsb`, `.xlsx`) publicados por el DANE, documentos
contractuales y cualquier archivo externo de análisis.

### Archivos que genera la aplicación (fuera de la carpeta del programa)

| Salida | Ubicación empaquetado | Ubicación en desarrollo |
|---|---|---|
| Informes y exportables | `Documentos\SAVIP\reportes_generados` | `reportes_generados/` |
| Sesiones | `Documentos\SAVIP\sesiones` | `sesiones/` |
| Registros | `%LOCALAPPDATA%\SAVIP\logs` | `logs/` |

Nunca se escribe dentro de `_internal` ni de `_MEIPASS`: en modo *onefile* esa
carpeta es temporal y se borra al cerrar, y bajo `Program Files` es de solo
lectura.

## 8. Manejo de rutas

Toda la resolución de rutas está centralizada en
[`app_icociv/config/rutas.py`](../../app_icociv/config/rutas.py). Es el único
módulo que consulta `sys.frozen`; el resto de la aplicación importa rutas ya
resueltas.

| Función | Uso |
|---|---|
| `ruta_recurso(rel)` | Recursos internos de solo lectura |
| `carpeta_datos_usuario()` | Raíz de reportes, exportables y sesiones |
| `carpeta_logs()` | Registros de ejecución |
| `asegurar_carpeta(ruta)` | Crea la carpeta si falta, sin lanzar excepción |
| `version_aplicacion()` | Lee `VERSION` |
| `es_ejecutable_congelado()` | Distingue ejecutable de código fuente |

Al añadir un recurso nuevo: colóquelo en el repositorio, decláre­lo en `datas`
dentro del `.spec` y cárguelo con `ruta_recurso()`. No use `__file__` para
recursos.

## 9. Versión

El archivo [`VERSION`](../../VERSIÓN) de la raíz es la **única fuente de
verdad**. Lo leen la aplicación (barra de título y «Acerca de»), el `.spec` y
los scripts de compilación.

Para publicar una versión nueva:

1. Edite `VERSION` (por ejemplo `0.2.0-beta`).
2. Actualice `filevers`, `prodvers`, `FileVersion` y `ProductVersion` en
   `packaging/version_info.txt`. Los cuatro números deben ser enteros; el
   sufijo `-beta` solo va en las cadenas de texto.
3. Añada la entrada correspondiente en `CHANGELOG.md`.

Se usa versionamiento semántico `MAJOR.MINOR.PATCH`.

## 10. Flujo completo tras cambios en el código

```powershell
git pull
# ... modificar el código ...
.\scripts\clean_build.ps1
.\scripts\build_exe.ps1
.\scripts\package_release.ps1
```

Antes de publicar:

1. Ejecutar las pruebas del repositorio (`tests/` y `pruebas/`).
2. Actualizar `VERSION` y `packaging/version_info.txt`.
3. Registrar los cambios en `CHANGELOG.md`.
4. Compilar y probar la distribución.
5. Generar el ZIP y su checksum.

## 11. Autocomprobación

El ejecutable admite un modo sin interfaz que ejercita las rutas críticas:

```powershell
.\release\SAVIP-0.1.0-beta-windows\SAVIP.exe --autocomprobacion
```

Comprueba recursos internos, carga del histórico ICCP, cálculo de empalme,
flujo de proyección, generación de DOCX y CSV, y escritura fuera del bundle.
Devuelve `0` si todas pasan. El script de compilación lo ejecuta
automáticamente al final.

Como `SAVIP.exe` se compila sin consola, su salida no aparece en pantalla: el
resultado queda en el código de salida y en el registro. Para ver el detalle
por pantalla, use la compilación de diagnóstico.

## 12. Compilación de diagnóstico

```powershell
.\scripts\build_exe.ps1 -Diagnostico
.\release\SAVIP-0.1.0-beta-windows\SAVIP-debug.exe --autocomprobacion
```

`SAVIP-debug.exe` mantiene la consola abierta y muestra trazas completas.
Úsela para identificar imports faltantes, excepciones de arranque o problemas
de rutas y carga de recursos.

## 13. Registros

Ubicación empaquetado: `%LOCALAPPDATA%\SAVIP\logs\savip_AAAAMMDD.log`
(en desarrollo: `logs/` en el repositorio). Rotan a 1 MB con 5 copias.

Cada ejecución registra fecha y hora, versión, sistema operativo, versión de
Python, modo (empaquetado o código fuente) y cualquier excepción no controlada
con su traza. **No se registran** documentos contractuales, credenciales ni
datos personales.

Desde la aplicación: menú **Ayuda > Abrir carpeta de registros**.

## 14. Prueba en un equipo limpio

Pendiente de ejecución. Lista de comprobación para hacerla en una máquina
virtual, Windows Sandbox, otro computador o un usuario de Windows distinto,
**sin Python ni entorno de desarrollo**:

- [ ] Copiar únicamente el ZIP y verificar su SHA-256.
- [ ] Descomprimir y ejecutar `SAVIP.exe`; la ventana debe abrir.
- [ ] Menú Ayuda > Acerca de: la versión debe coincidir.
- [ ] Cargar un anexo ICOCIV real; deben detectarse las tablas.
- [ ] Recorrer el selector jerárquico y recuperar una serie histórica.
- [ ] Ejecutar proyecciones de 1, 3 y 12 meses (esta última cruza el cambio de año).
- [ ] Abrir la gráfica y comprobar zoom y desplazamiento.
- [ ] Generar informe DOCX y exportable CSV; confirmar que se guardan en
      `Documentos\SAVIP\reportes_generados`.
- [ ] Módulo de empalme: comprobar que carga el Anexo 10 ICCP interno, las
      listas de series ICCP, el cálculo general, el cálculo especial de acero y
      la exportación a Excel.
- [ ] Confirmar que se crea `%LOCALAPPDATA%\SAVIP\logs` con el registro.
- [ ] Cerrar y reabrir: las preferencias (tema) deben conservarse.

Si algo falla, repetir con `SAVIP-debug.exe` y adjuntar el registro.

## 15. Errores comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| La distribución pesa varios GB | Se compiló con un Python que tiene librerías ajenas | Usar `.\scripts\build_exe.ps1` (crea `.venv-build`); si persiste, `-Recrear` |
| `ModuleNotFoundError` al usar una función | Import dinámico no detectado | Añadirlo a `hiddenimports` en `packaging/SAVIP.spec` |
| La aplicación abre y se cierra sola | Excepción de arranque | Revisar `%LOCALAPPDATA%\SAVIP\logs`; reproducir con `-Diagnostico` |
| No se guarda un informe | Carpeta sin permisos de escritura | Elegir otra ubicación en el diálogo; verificar `Documentos\SAVIP` |
| No aparece un recurso nuevo | Falta declararlo | Añadirlo a `datas` en el `.spec` y cargarlo con `ruta_recurso()` |
| El script aborta al llamar a PyInstaller | stderr de comando nativo en PowerShell 5.1 | Ya contemplado en el script; no invocar el `.ps1` con `2>&1` |

## 16. Limitaciones

- Distribución de unos 284 MB (ZIP de 123 MB) por PySide6, pandas, matplotlib,
  scikit-learn y scipy. Es lo esperable en una aplicación científica con Qt.
- Solo Windows de 64 bits. Para otras plataformas habría que compilar en ellas:
  PyInstaller no hace compilación cruzada.
- Sin icono propio: se usa el de PyInstaller hasta definir un icono
  institucional autorizado. Si se añade `packaging/icono.ico`, el `.spec` lo
  toma automáticamente.
- Modalidad `onefile` no generada. La `onedir` se validó primero por facilitar
  la depuración y arrancar más rápido; `onefile` puede prepararse después.
- Sin actualizador automático por internet. Cada versión se distribuye como ZIP.

## 17. Firma digital (mejora futura)

El ejecutable no está firmado, por lo que Windows SmartScreen puede advertir en
el primer arranque. Está documentado para el usuario final en
`README_EJECUTABLE.txt`. **No debe intentarse evadir antivirus.** Lo apropiado
es obtener un certificado de firma de código y firmar tanto el ejecutable como
un futuro instalador, publicando además el checksum SHA-256 que ya genera
`package_release.ps1`.

## 18. Archivos del sistema de empaquetado

| Archivo | Función | ¿Se versiona? |
|---|---|---|
| `VERSION` | Fuente única de versión | Sí |
| `CHANGELOG.md` | Registro de cambios | Sí |
| `requirements-build.txt` | Dependencias de compilación | Sí |
| `packaging/SAVIP.spec` | Especificación de PyInstaller | Sí |
| `packaging/version_info.txt` | Metadatos de Windows | Sí |
| `scripts/build_exe.ps1` | Compilación completa | Sí |
| `scripts/build_exe.bat` | Envoltorio para `cmd.exe` | Sí |
| `scripts/clean_build.ps1` | Limpieza | Sí |
| `scripts/package_release.ps1` | ZIP y checksum | Sí |
| `README_EJECUTABLE.txt` | Instrucciones al usuario final | Sí |
| `.venv-build/`, `build/`, `dist/`, `release/` | Salidas generadas | No |
