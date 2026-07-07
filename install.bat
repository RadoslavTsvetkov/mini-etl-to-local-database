@echo off
setlocal

echo ============================================
echo  Shopmetrics Survey ETL - Install
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and re-run this script.
    echo ^(during install, make sure "Add python.exe to PATH" is checked^).
    echo.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.10 or newer is required ^(this project's code uses
    echo newer type-hint syntax that fails immediately on anything older^).
    echo Install a current version from https://www.python.org/downloads/
    echo ^(check "Add python.exe to PATH"^) and re-run this script.
    echo.
    pause
    exit /b 1
)

echo Creating virtual environment in .venv ...
python -m venv "%~dp0.venv"
if errorlevel 1 (
    echo ERROR: Failed to create the virtual environment.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing core requirements (SQLite backend -- no third-party packages needed) ...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install core requirements.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing optional SQL Server support (pyodbc) ...
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements-sqlserver.txt"
if errorlevel 1 (
    echo WARNING: pyodbc failed to install. The SQLite backend will still work;
    echo the SQL Server backend ^(DB_BACKEND=sqlserver^) will not be available
    echo until this is resolved.
    echo.
)

if not exist "%~dp0.env" (
    echo Creating .env from template ...
    copy "%~dp0.env.example" "%~dp0.env" >nul
    echo.
)

echo ============================================
echo  Install complete!
echo.
echo  Next step: double-click run.bat. It scrapes surveys from the live
echo  Shopmetrics API, then generates and opens a new numbered dashboard
echo  ^(reports\dashboard1.html, dashboard2.html, ...^) in your browser.
echo.
echo  - First run: you'll be asked for your Shopmetrics API Client ID and
echo    Client Secret ^(created in Shopmetrics under Administration -^>
echo    Tools and Settings -^> Site Settings -^> Other -^> API v2
echo    Authorization - Client Credentials^). They are saved to .env
echo    ^(gitignored^) so you're only asked once per machine.
echo  - Offline instead: run.bat run --mode file ^(sample data, no
echo    credentials or network needed^).
echo  - Edit config\config.json to change default settings; .env for
echo    secrets and local overrides ^(see .env.example^).
echo ============================================
echo.
pause

endlocal
