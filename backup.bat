@echo off
rem MethodFlow - create a consistent database backup (safe while the server is running).
rem Optional:  backup.bat --data D:\other\data
setlocal
cd /d "%~dp0"
chcp 65001 >nul 2>nul

set "PYEXE="
set "PYARGS="
rem Optional: full path to python.exe in the METHODFLOW_PYTHON environment variable
if defined METHODFLOW_PYTHON if exist "%METHODFLOW_PYTHON%" (
    set "PYEXE=%METHODFLOW_PYTHON%"
    goto :found
)
py -3 --version >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARGS=-3"
    goto :found
)
python --version >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=python"
    goto :found
)
echo [ERROR] Python not found.
pause
exit /b 1

:found
"%PYEXE%" %PYARGS% tools\backup.py %*
set "RC=%errorlevel%"
echo.
pause
endlocal
exit /b %RC%
