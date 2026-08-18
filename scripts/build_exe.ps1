<#
.SYNOPSIS
    Compila la aplicacion SAVIP como ejecutable de Windows (PyInstaller, onedir).

.DESCRIPTION
    Verifica el entorno, instala dependencias de compilacion, limpia salidas
    previas, ejecuta PyInstaller con packaging/SAVIP.spec y deja la
    distribucion en release/SAVIP-<VERSION>-windows/.

.PARAMETER Diagnostico
    Genera SAVIP-debug.exe con consola visible, para depurar imports o rutas.

.PARAMETER SinPruebas
    Omite la ejecucion de las pruebas previas. No recomendado para una version
    que se vaya a distribuir.

.PARAMETER Recrear
    Elimina y vuelve a crear el entorno virtual de compilacion (.venv-build).
    Util cuando cambian las dependencias declaradas.

.EXAMPLE
    .\scripts\build_exe.ps1
    .\scripts\build_exe.ps1 -Diagnostico
    .\scripts\build_exe.ps1 -Recrear
#>
[CmdletBinding()]
param(
    [switch]$Diagnostico,
    [switch]$SinPruebas,
    [switch]$Recrear
)

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

Write-Host "== SAVIP: compilacion de ejecutable ==" -ForegroundColor Cyan
Write-Host "Raiz del proyecto: $Raiz"

# --- 1. Version de Python -------------------------------------------------
$python = "python"
$versionPython = & $python --version 2>&1
if ($LASTEXITCODE -ne 0) { throw "No se encontro Python en el PATH." }
Write-Host "Python detectado: $versionPython"

$minima = [version]"3.10"
if ($versionPython -notmatch '(\d+)\.(\d+)\.(\d+)') {
    throw "No se pudo interpretar la version de Python: $versionPython"
}
$detectada = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
if ($detectada -lt $minima) { throw "Se requiere Python $minima o superior; detectado $detectada." }

# --- 2. Version de la aplicacion -----------------------------------------
$archivoVersion = Join-Path $Raiz "VERSION"
if (-not (Test-Path $archivoVersion)) { throw "Falta el archivo VERSION en la raiz." }
$Version = (Get-Content $archivoVersion -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Version)) { throw "El archivo VERSION esta vacio." }
Write-Host "Version de la aplicacion: $Version"

# --- 3. Entorno virtual aislado desde el lock -----------------------------
# La compilacion NO usa el Python global: PyInstaller empaqueta lo que
# encuentra instalado, y un entorno con librerias ajenas al proyecto (por
# ejemplo PyTorch) produce distribuciones de varios gigabytes.
#
# RA-02 (reauditoria de 0.3.0-rc2): antes se instalaba requirements.txt, que
# solo fija statsmodels y deja abiertas las demas dependencias directas. El
# ejecutable resultante llevaba pandas 3.0.5, numpy 2.5.1, scipy 1.18.0,
# scikit-learn 1.9.0 y matplotlib 3.11.1 frente a 2.3.3, 2.4.2, 1.17.1, 1.8.0 y
# 3.10.9 del lock: no era reconstruible desde el entorno productivo declarado.
#
# Desde rc3 el entorno se recrea SIEMPRE desde cero y se instala unicamente
# requirements-lock.txt. requirements.txt se conserva como lista de
# dependencias directas para desarrollo, pero no interviene en el ejecutable.
$lock = Join-Path $Raiz "requirements-lock.txt"
if (-not (Test-Path $lock)) { throw "Falta requirements-lock.txt: sin lock no hay build reproducible." }

$venv = Join-Path $Raiz ".venv-build"
$pythonVenv = Join-Path $venv "Scripts\python.exe"

# Recreacion incondicional: reutilizar el entorno permitiria que una version
# instalada en una compilacion anterior sobreviviera a un cambio del lock.
if (Test-Path $venv) {
    Write-Host "`n-- Eliminando entorno de compilacion previo --" -ForegroundColor Yellow
    Remove-Item $venv -Recurse -Force
}
if ($Recrear) { Write-Host "  (-Recrear es redundante: el entorno se recrea siempre)" -ForegroundColor DarkGray }

Write-Host "`n-- Creando entorno virtual de compilacion (.venv-build) --" -ForegroundColor Cyan
& $python -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual en $venv." }

Write-Host "-- Instalando requirements-lock.txt (versiones exactas) --" -ForegroundColor Cyan
$preferenciaPip = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $pythonVenv -m pip install --disable-pip-version-check -q --upgrade pip
& $pythonVenv -m pip install --disable-pip-version-check -q --no-deps -r $lock
$codigoPip = $LASTEXITCODE
$ErrorActionPreference = $preferenciaPip
if ($codigoPip -ne 0) { throw "Fallo la instalacion de requirements-lock.txt." }

# El lock ya es el cierre transitivo completo; --no-deps impide que pip
# resuelva y suba ninguna version por su cuenta.

Write-Host "-- Instalando herramientas de compilacion (requirements-build.txt) --" -ForegroundColor Cyan
$ErrorActionPreference = "Continue"
& $pythonVenv -m pip install --disable-pip-version-check -q -r requirements-build.txt
$codigoPip = $LASTEXITCODE
$ErrorActionPreference = $preferenciaPip
if ($codigoPip -ne 0) { throw "Fallo la instalacion de requirements-build.txt." }

# A partir de aqui toda la compilacion usa el interprete del entorno aislado.
$python = $pythonVenv

# --- 3b. Verificacion del lock ANTES de invocar PyInstaller ----------------
# Barrera dura: si falta o difiere una sola version, no se compila. El registro
# deja las versiones exactas para que la evidencia sea contrastable.
Write-Host "`n-- Verificando versiones exactas del lock --" -ForegroundColor Cyan
$registroLock = Join-Path $Raiz "release\verificacion_lock.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $registroLock) | Out-Null

$ErrorActionPreference = "Continue"
& $python (Join-Path $Raiz "scripts\verificar_lock.py") --lock $lock --json $registroLock
$codigoLock = $LASTEXITCODE
$ErrorActionPreference = $preferenciaPip
if ($codigoLock -ne 0) {
    throw "El entorno de compilacion no reproduce requirements-lock.txt. Se aborta antes de PyInstaller."
}
Write-Host "  Registro de versiones: $registroLock" -ForegroundColor DarkGray

# --- 4. Pruebas previas ---------------------------------------------------
if (-not $SinPruebas) {
    Write-Host "`n-- Pruebas previas --" -ForegroundColor Cyan
    $env:QT_QPA_PLATFORM = "offscreen"
    foreach ($prueba in @("tests\test_imports_modulos.py",
                          "tests\test_empalme_iccp_icociv.py",
                          "tests\test_auditoria_formulas_estadisticas.py")) {
        & $python $prueba | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Fallo la prueba $prueba. Corrija antes de compilar." }
        Write-Host "  OK  $prueba"
    }
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}

# --- 5. Limpieza ----------------------------------------------------------
Write-Host "`n-- Limpiando salidas previas --" -ForegroundColor Cyan
foreach ($carpeta in @("build", "dist")) {
    if (Test-Path $carpeta) { Remove-Item $carpeta -Recurse -Force; Write-Host "  limpiada: $carpeta" }
}

# --- 6. PyInstaller -------------------------------------------------------
if ($Diagnostico) {
    $env:SAVIP_BUILD = "diagnostico"
    $nombreExe = "SAVIP-debug"
    Write-Host "`n-- Compilando (modo DIAGNOSTICO, con consola) --" -ForegroundColor Yellow
} else {
    $env:SAVIP_BUILD = "distribucion"
    $nombreExe = "SAVIP"
    Write-Host "`n-- Compilando (modo distribucion) --" -ForegroundColor Cyan
}

# PyInstaller escribe sus mensajes INFO en stderr. En Windows PowerShell 5.1
# eso se convierte en NativeCommandError y, con ErrorActionPreference=Stop,
# abortaria la compilacion aunque haya terminado bien. Se aisla la llamada y
# se decide unicamente por el codigo de salida.
$preferenciaPrevia = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $python -m PyInstaller "packaging\SAVIP.spec" --noconfirm --clean
$codigo = $LASTEXITCODE
$ErrorActionPreference = $preferenciaPrevia
Remove-Item Env:\SAVIP_BUILD -ErrorAction SilentlyContinue
if ($codigo -ne 0) { throw "PyInstaller fallo con codigo $codigo." }

$origen = Join-Path $Raiz "dist\$nombreExe"
if (-not (Test-Path $origen)) { throw "No se genero la carpeta esperada: $origen" }

# --- 7. Carpeta de version ------------------------------------------------
Write-Host "`n-- Preparando distribucion --" -ForegroundColor Cyan
$destino = Join-Path $Raiz "release\SAVIP-$Version-windows"
if (Test-Path $destino) { Remove-Item $destino -Recurse -Force }
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item "$origen\*" $destino -Recurse -Force

# --- 8. Archivos complementarios -----------------------------------------
$leeme = Join-Path $Raiz "README_EJECUTABLE.txt"
if (Test-Path $leeme) { Copy-Item $leeme $destino -Force }

# RA-08: VERSION.txt no expone el equipo de compilacion. El hostname no aporta
# trazabilidad util al lector del artefacto y sí filtra un identificador de
# maquina personal. La trazabilidad de la compilacion queda en el lock
# verificado y en la version unica.
$infoVersion = @"
SAVIP - Sistema de Analisis de Variaciones de Precios
Version: $Version
Compilado: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Python: $versionPython
Modo: $(if ($Diagnostico) { "diagnostico (consola visible)" } else { "distribucion" })
Dependencias: requirements-lock.txt verificado version a version antes de compilar
Naturaleza: ejecutable temporal de revision, NO DISTRIBUIR
"@
Set-Content -Path (Join-Path $destino "VERSION.txt") -Value $infoVersion -Encoding utf8

# --- 9. Verificaciones minimas -------------------------------------------
Write-Host "`n-- Verificaciones --" -ForegroundColor Cyan
$exe = Join-Path $destino "$nombreExe.exe"
if (-not (Test-Path $exe)) { throw "No se encontro el ejecutable: $exe" }
Write-Host "  OK  ejecutable presente"

foreach ($recurso in @("_internal\app_icociv\datos\iccp_historico.json",
                       "_internal\app_icociv\interfaz\tema\plantilla.qss",
                       "_internal\VERSION")) {
    if (Test-Path (Join-Path $destino $recurso)) {
        Write-Host "  OK  recurso: $recurso"
    } else {
        Write-Warning "  FALTA recurso empaquetado: $recurso"
    }
}

# Autocomprobacion sobre la distribucion ya empaquetada: ejercita recursos,
# datos ICCP, empalme, proyeccion, exportables y escritura externa. Es la
# verificacion que distingue "el exe arranca" de "el exe funciona".
Write-Host "`n-- Autocomprobacion de la distribucion --" -ForegroundColor Cyan
$preferenciaCheck = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $exe --autocomprobacion
$codigoCheck = $LASTEXITCODE
$ErrorActionPreference = $preferenciaCheck

if ($codigoCheck -eq 0) {
    Write-Host "  OK  autocomprobacion superada" -ForegroundColor Green
} else {
    Write-Warning "  La autocomprobacion fallo (codigo $codigoCheck)."
    Write-Warning "  Revise el registro en %LOCALAPPDATA%\ICOCIV\logs"
    Write-Warning "  Para ver el detalle: .\scripts\build_exe.ps1 -Diagnostico"
}

$tam = [math]::Round(((Get-ChildItem $destino -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB), 1)

Write-Host "`n== Compilacion completada ==" -ForegroundColor Green
Write-Host "Ejecutable: $exe"
Write-Host "Tamano de la distribucion: $tam MB"
Write-Host "`nSiguiente paso: .\scripts\package_release.ps1"
