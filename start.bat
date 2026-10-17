@echo off
rem MethodFlow launcher - ASCII only on purpose (cmd.exe reads .bat files in the system code page).
rem Extra arguments are passed to run.py, e.g.  start.bat --port 8790 --no-browser
setlocal
cd /d "%~dp0"
chcp 65001 >nul 2>nul
title MethodFlow

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
echo.
echo [ERROR] Python 3.9 or newer was not found.
echo         Install Python from https://www.python.org/ and tick "Add python.exe to PATH",
echo         then double-click start.bat again.
echo.
pause
exit /b 1

:found
"%PYEXE%" %PYARGS% -c "import fastapi, uvicorn, docx, bcrypt, matplotlib" >nul 2>nul
if not errorlevel 1 goto :run

echo.
echo Some required Python packages are missing (see requirements.txt).
choice /c YN /m "Install them now with pip"
if errorlevel 2 (
    echo Cancelled. Run:  python -m pip install -r requirements.txt
    pause
    exit /b 1
)
"%PYEXE%" %PYARGS% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed. Check your network / proxy and try again.
    pause
    exit /b 1
)

:run
echo Starting MethodFlow ...
"%PYEXE%" %PYARGS% run.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo MethodFlow stopped with exit code %RC%.
    pause
)
endlocal
exit /b %RC%
