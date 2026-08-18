<#
.SYNOPSIS
    Empaqueta la distribucion de SAVIP en un ZIP con su checksum SHA-256.

.DESCRIPTION
    Toma release/SAVIP-<VERSION>-windows/ (generada por build_exe.ps1),
    produce el ZIP y el archivo .sha256 para verificar integridad.
    No incluye codigo fuente, entorno virtual, .git ni archivos de construccion.

.EXAMPLE
    .\scripts\package_release.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

Write-Host "== Empaquetado de la distribucion SAVIP ==" -ForegroundColor Cyan

$archivoVersion = Join-Path $Raiz "VERSION"
if (-not (Test-Path $archivoVersion)) { throw "Falta el archivo VERSION en la raiz." }
$Version = (Get-Content $archivoVersion -Raw).Trim()

$carpeta = Join-Path $Raiz "release\SAVIP-$Version-windows"
if (-not (Test-Path $carpeta)) {
    throw "No existe $carpeta. Ejecute primero .\scripts\build_exe.ps1"
}

$zip = Join-Path $Raiz "release\SAVIP-$Version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

Write-Host "Comprimiendo $carpeta ..."
Compress-Archive -Path $carpeta -DestinationPath $zip -CompressionLevel Optimal
if (-not (Test-Path $zip)) { throw "No se genero el ZIP." }

# --- Checksum SHA-256 ------------------------------------------------------
$hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLower()
$archivoHash = "$zip.sha256"
$nombreZip = Split-Path $zip -Leaf
Set-Content -Path $archivoHash -Value "$hash  $nombreZip" -Encoding ascii

$tamZip = [math]::Round(((Get-Item $zip).Length / 1MB), 1)

Write-Host "`n== Empaquetado completado ==" -ForegroundColor Green
Write-Host "ZIP:      $zip"
Write-Host "Tamano:   $tamZip MB"
Write-Host "SHA-256:  $hash"
Write-Host "Checksum: $archivoHash"
Write-Host "`nVerificacion en el equipo de destino:"
Write-Host "  Get-FileHash -Path '$nombreZip' -Algorithm SHA256"
