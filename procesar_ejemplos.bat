@echo off
REM Script para procesar ejemplos de buenas prácticas
REM Versión 2.0 - Con nombres de archivo cortos

echo ========================================
echo Procesador de Buenas Prácticas v2.0
echo ========================================
echo.

REM Activar entorno virtual
if exist .venv\Scripts\activate.bat (
    echo [1/3] Activando entorno virtual...
    call .venv\Scripts\activate.bat
) else (
    echo ERROR: No se encontró el entorno virtual .venv
    echo Ejecuta: python -m venv .venv
    pause
    exit /b 1
)

REM Verificar estructura
echo [2/3] Verificando estructura de carpetas...
python -m centauro.tools.mapeo_secciones
if errorlevel 1 (
    echo ERROR: Problema con mapeo de secciones
    pause
    exit /b 1
)

echo.
echo [3/3] Procesando ejemplos...
echo.

REM Procesar ejemplos
python -m centauro.tools.procesar_buenas_practicas

if errorlevel 1 (
    echo.
    echo ERROR: El procesamiento falló
    pause
    exit /b 1
)

echo.
echo ========================================
echo PROCESAMIENTO COMPLETADO
echo ========================================
echo.
echo Próximo paso:
echo   python main.py
echo.
pause
