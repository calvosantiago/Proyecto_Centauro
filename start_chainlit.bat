@echo off
REM ================================================
REM  CENTAURO v3.0 - Launcher Seguro (CORREGIDO)
REM ================================================

REM 1. Asegurar que estamos en la carpeta del proyecto
cd /d "%~dp0"

echo.
echo [INFO] Buscando entorno virtual...

REM 2. Intentar activar el entorno virtual
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Entorno virtual .venv ACTIVADO correctamente.
) else (
    echo [ALERTA] No se encontro la carpeta .venv
    echo Intentando usar Python del sistema...
)

echo.
echo ================================================
echo     CENTAURO v3.0 - Iniciando Chainlit
echo ================================================
echo.

REM 3. Verificar si chainlit está instalado
python -c "import chainlit" 2>nul
if %errorlevel% neq 0 (
    echo [AVISO] Chainlit no detectado.
    echo Instalando dependencias...
    
    uv pip install -r requirements.txt 2>nul
    if %errorlevel% neq 0 (
        echo UV no encontrado, usando PIP estandar...
        pip install -r requirements.txt
    )
    echo.
)

echo [OK] Lanzando aplicacion...
echo Navegador: http://localhost:8000
echo.

REM 4. Ejecutar la app
python -m chainlit run app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] La aplicacion se cerro.
    echo Si ves un SyntaxError arriba, revisa tu archivo app.py.
)

pause