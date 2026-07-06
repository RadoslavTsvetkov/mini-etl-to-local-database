@echo off
setlocal

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Virtual environment not found.
    echo Run install.bat first ^(double-click it^), then try run.bat again.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo No command given -- running the pipeline with default settings
    echo ^(offline sample data, no credentials needed^). See README.md for
    echo other commands: run.bat view / browse / dashboard / setup-db
    echo.
    "%VENV_PY%" "%~dp0src\manage.py" run
    echo.
    pause
) else (
    "%VENV_PY%" "%~dp0src\manage.py" %*
)

endlocal
