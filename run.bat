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

if not "%~1"=="" goto :passthrough

echo No command given -- scraping surveys from the live Shopmetrics API
echo ^(read-only Query API; mark-opened stays mocked^). If credentials are
echo missing you'll be asked for them once and they are saved to .env.
echo A new numbered report ^(reports\dashboard1.html, dashboard2.html, ...^)
echo is generated and opened in your browser when the run succeeds, after
echo which a menu here lets you pick what to do next -- no commands to
echo remember. ^(See README.md for the full command-line reference, or use
echo "run.bat run --mode file" for the old offline sample-data run.^)
echo.

"%VENV_PY%" "%~dp0src\manage.py" run --mode api --no-open
if errorlevel 1 goto :finish

rem Open the newest generated report (dir /o-d lists newest first).
set "LATEST="
for /f "delims=" %%F in ('dir /b /o-d "%~dp0reports\dashboard*.html" 2^>nul') do if not defined LATEST set "LATEST=%%F"
if defined LATEST (
    echo Opening the new dashboard: %~dp0reports\%LATEST%
    start "" "%~dp0reports\%LATEST%"
) else (
    echo No dashboard file found in reports\ to open.
)

echo.
"%VENV_PY%" "%~dp0src\menu.py"

:finish
echo.
pause
endlocal
exit /b

:passthrough
"%VENV_PY%" "%~dp0src\manage.py" %*
endlocal
