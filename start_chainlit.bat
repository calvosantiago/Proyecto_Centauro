@echo off
setlocal

REM Centauro Chainlit launcher (robust Windows batch)
cd /d "%~dp0"

REM Force UTF-8 mode for Python I/O
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo [INFO] Starting Centauro Chainlit...

REM Prefer project virtual environment
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
  echo [OK] Using .venv Python
) else (
  set "PYTHON_EXE=python"
  echo [WARN] .venv not found, using system Python
)

REM Kill stale process on port 8000
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo [WARN] Port 8000 in use by PID %%P. Killing stale process...
  taskkill /F /PID %%P >nul 2>nul
)

REM Validate key dependencies in selected interpreter
%PYTHON_EXE% -c "import chainlit, chromadb" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Missing dependencies in selected Python environment.
  echo [ERROR] Install with:
  echo         .venv\Scripts\python -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo [OK] Launching app at http://localhost:8000
echo [INFO] First startup can take 30-60 seconds...

%PYTHON_EXE% -m chainlit run app.py --host 127.0.0.1 --port 8000

if errorlevel 1 (
  echo.
  echo [ERROR] Chainlit stopped with an error.
)

pause
endlocal
