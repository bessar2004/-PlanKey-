@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PY="
set "VENV_PYW="
set "PY_CMD="

echo [1/5] Python kontrol ediliyor...

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo [HATA] Python 3.8 veya daha yeni bir surum bulunamadi.
    echo [HATA] Python kurup tekrar deneyin: https://www.python.org/downloads/
    exit /b 1
)

echo [2/5] Sanal ortam kontrol ediliyor...
call :detect_venv

if defined VENV_PY (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo [UYARI] Mevcut .venv bozuk gorunuyor. Yeniden olusturuluyor...
        rmdir /s /q "%VENV_DIR%"
        if exist "%VENV_DIR%" (
            echo [HATA] Bozuk .venv silinemedi. Acik Python sureclerini kapatip tekrar deneyin.
            exit /b 1
        )
    )
) else (
    if exist "%VENV_DIR%" (
        echo [UYARI] Mevcut .venv taninamadi. Yeniden olusturuluyor...
        rmdir /s /q "%VENV_DIR%"
        if exist "%VENV_DIR%" (
            echo [HATA] .venv silinemedi. Acik Python sureclerini kapatip tekrar deneyin.
            exit /b 1
        )
    )
)

call :detect_venv
if not defined VENV_PY (
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [HATA] .venv olusturulamadi.
        exit /b 1
    )
)

call :detect_venv
if not defined VENV_PY (
    echo [HATA] .venv olustu ama Python calistiricisi bulunamadi.
    exit /b 1
)

echo [3/5] pip guncelleniyor...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [HATA] pip guncellenemedi.
    exit /b 1
)

echo [4/5] Paketler kuruluyor...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [HATA] Paket kurulumu basarisiz.
    exit /b 1
)

"%VENV_PY%" -c "import requests, pyperclip, pynput" >nul 2>nul
if errorlevel 1 (
    echo [HATA] Paketler kuruldu ama dogrulama basarisiz oldu.
    exit /b 1
)

echo [5/5] Ollama kontrol ediliyor...
where ollama >nul 2>nul
if errorlevel 1 (
    echo [UYARI] Ollama komutu bulunamadi. Ollama'yi kurun ve gemma3:1b modelini indirin.
) else (
    ollama list | findstr /I "gemma3:1b" >nul 2>nul
    if errorlevel 1 (
        echo [UYARI] gemma3:1b modeli bulunamadi.
        echo [BILGI] Indirmek icin: ollama pull gemma3:1b
    )
)

if not exist "%VENV_PYW%" (
    echo [UYARI] pythonw.exe bulunamadi; BASLAT.bat python.exe ile calistirmayi deneyecek.
)

echo [OK] Kurulum tamamlandi.
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
