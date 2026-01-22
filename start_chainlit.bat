@echo off
REM Script para iniciar Centauro v3.0 con Chainlit

echo ================================================
echo     CENTAURO v3.0 - Iniciando Interfaz Web
echo ================================================
echo.

REM Verificar si chainlit está instalado
python -c "import chainlit" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Chainlit no esta instalado.
    echo.
    echo Instalando dependencias...
    pip install -r requirements.txt
    echo.
)

echo [OK] Iniciando servidor Chainlit...
echo.
echo Abriendo navegador en: http://localhost:8000
echo.
echo Presiona CTRL+C para detener el servidor
echo ================================================
echo.

chainlit run app.py -w

pause
