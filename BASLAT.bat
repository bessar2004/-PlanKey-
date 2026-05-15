@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY="
set "VENV_PYW="
set "RUNNER="
set "NEED_SETUP=0"

call :detect_venv

if not defined VENV_PY (
    set "NEED_SETUP=1"
) else (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if errorlevel 1 set "NEED_SETUP=1"

    "%VENV_PY%" -c "import requests, pyperclip, pynput" >nul 2>nul
    if errorlevel 1 set "NEED_SETUP=1"
)

if "%NEED_SETUP%"=="1" (
    echo [INFO] Sanal ortam eksik veya bozuk. Kurulum/onarim baslatiliyor...
    call "%~dp0kurulum.bat"
    if errorlevel 1 (
        echo [HATA] Kurulum basarisiz. Program baslatilamadi.
        pause
        exit /b 1
    )
    call :detect_venv
)

set "RUNNER=%VENV_PYW%"
if not exist "%RUNNER%" set "RUNNER=%VENV_PY%"

if not exist "%RUNNER%" (
    echo [HATA] Python calistiricisi bulunamadi.
    pause
    exit /b 1
)

start "PlanKey" "%RUNNER%" "%~dp0main.pyw"
exit /b 0

:detect_venv
set "VENV_PY="
set "VENV_PYW="
if exist "%VENV_DIR%\Scripts\python.exe" (
    set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
    set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"
    exit /b 0
)
if exist "%VENV_DIR%\bin\python.exe" (
    set "VENV_PY=%VENV_DIR%\bin\python.exe"
    set "VENV_PYW="
    exit /b 0
)
exit /b 0
