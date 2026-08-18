<#
.SYNOPSIS
    Elimina las salidas de compilacion de SAVIP.

.DESCRIPTION
    Borra build/ y dist/. Con -TodoIncluidoRelease borra tambien release/.
    No toca el codigo fuente, la documentacion ni el historial de Git.

.EXAMPLE
    .\scripts\clean_build.ps1
    .\scripts\clean_build.ps1 -TodoIncluidoRelease
#>
[CmdletBinding()]
param(
    [switch]$TodoIncluidoRelease
)

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz

Write-Host "== Limpieza de salidas de compilacion ==" -ForegroundColor Cyan

$objetivos = @("build", "dist")
if ($TodoIncluidoRelease) { $objetivos += "release" }

foreach ($carpeta in $objetivos) {
    $ruta = Join-Path $Raiz $carpeta
    if (Test-Path $ruta) {
        Remove-Item $ruta -Recurse -Force
        Write-Host "  eliminada: $carpeta" -ForegroundColor Yellow
    } else {
        Write-Host "  no existia: $carpeta"
    }
}

# Archivos .spec temporales generados por PyInstaller en la raiz (el .spec
# definitivo vive en packaging/ y no debe borrarse).
Get-ChildItem -Path $Raiz -Filter "*.spec" -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "  eliminado spec temporal: $($_.Name)" -ForegroundColor Yellow
    }

Write-Host "`nLimpieza completada." -ForegroundColor Green
Write-Host "El codigo fuente, packaging/SAVIP.spec y los scripts permanecen intactos."
