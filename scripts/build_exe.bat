@echo off
REM Compila la aplicacion SAVIP como ejecutable de Windows.
REM Envoltorio de scripts\build_exe.ps1 para quienes prefieren cmd.exe.
REM
REM   build_exe.bat              compilacion de distribucion
REM   build_exe.bat diagnostico  compilacion con consola visible

setlocal

set "SCRIPT_DIR=%~dp0"

if /I "%~1"=="diagnostico" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_exe.ps1" -Diagnostico
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_exe.ps1"
)

set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" (
    echo.
    echo La compilacion fallo con codigo %CODIGO%.
    exit /b %CODIGO%
)

echo.
echo Compilacion finalizada correctamente.
exit /b 0
