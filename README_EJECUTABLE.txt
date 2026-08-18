===============================================================================
SAVIP - Sistema de Analisis de Variaciones de Precios
Version 0.3.0-rc3  (candidata de revision interna - NO DISTRIBUIR)
===============================================================================

QUE ES ESTO
-------------------------------------------------------------------------------
Aplicacion de escritorio para consultar series del Indice de Costos de la
Construccion de Obras Civiles (ICOCIV) del DANE, analizarlas, proyectarlas,
aplicar el empalme ICCP-ICOCIV y generar informes. La aplicacion se llama
SAVIP; ICOCIV e ICCP son los indices oficiales del DANE que analiza.

No necesita tener Python instalado. Todo lo necesario viaja en esta carpeta.


COMO SE USA
-------------------------------------------------------------------------------
1. Mantenga esta carpeta completa. No mueva SAVIP.exe fuera de ella:
   necesita la carpeta _internal que esta a su lado.

2. Haga doble clic en SAVIP.exe

3. La primera vez Windows puede mostrar un aviso de SmartScreen porque el
   ejecutable no tiene firma digital. Si es asi, elija "Mas informacion" y
   luego "Ejecutar de todas formas". Vease la seccion AVISOS.

4. Cargue un anexo ICOCIV (.xlsb o .xlsx) desde el menu Archivo > Cargar Excel.
   Los anexos NO vienen incluidos: los publica el DANE y los selecciona usted.


DONDE QUEDAN SUS ARCHIVOS
-------------------------------------------------------------------------------
Los resultados NO se guardan dentro de esta carpeta, para que sobrevivan a una
actualizacion de la aplicacion:

  Informes y exportables    Documentos\SAVIP\reportes_generados
  Sesiones guardadas        Documentos\SAVIP\sesiones
  Registros de ejecucion    %LOCALAPPDATA%\SAVIP\logs

Al guardar un informe la aplicacion propone esas carpetas, pero usted puede
elegir cualquier otra ubicacion.

Para abrir la carpeta de registros: menu Ayuda > Abrir carpeta de registros.


SI LA APLICACION NO ABRE O FALLA
-------------------------------------------------------------------------------
1. Revise el archivo de registro mas reciente en:
       %LOCALAPPDATA%\SAVIP\logs
   Puede pegar esa ruta en la barra del Explorador de Windows.

2. El registro contiene la fecha, la version, el sistema operativo y el detalle
   tecnico del error. No contiene datos de sus contratos.

3. Comparta ese archivo con el responsable tecnico del proyecto.


QUE VERSION TENGO
-------------------------------------------------------------------------------
  - Menu Ayuda > Acerca de SAVIP
  - Barra de titulo de la ventana
  - Archivo VERSION.txt de esta carpeta


AVISOS
-------------------------------------------------------------------------------
- Esta es una version candidata (release candidate) destinada exclusivamente a
  revision interna. NO es la version final y NO debe distribuirse.

- El ejecutable no esta firmado digitalmente. Windows SmartScreen o algunos
  antivirus pueden advertir sobre el. Es un comportamiento normal para
  aplicaciones sin firma; la firma digital esta prevista como mejora futura.

- Los indices proyectados son estimaciones estadisticas de apoyo tecnico. No
  reemplazan la produccion estadistica oficial del DANE ni el criterio del
  profesional responsable.

- Las equivalencias ICCP-ICOCIV son selecciones tecnicas que debe validar el
  ingeniero responsable.

- Para verificar la integridad de la descarga compare el SHA-256 del archivo
  ZIP con el contenido del archivo .sha256 que lo acompana:

      Get-FileHash -Path SAVIP-0.3.0-rc3-windows.zip -Algorithm SHA256


===============================================================================
