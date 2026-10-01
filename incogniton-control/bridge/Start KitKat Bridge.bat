@echo off
setlocal
title KitKat Bridge
cd /d "%~dp0"

:: Find Python
set PYTHON=
where py >nul 2>nul
if not errorlevel 1 (set PYTHON=py -3) else (
  where python >nul 2>nul
  if not errorlevel 1 (set PYTHON=python) else (
    echo Python 3 is required to run KitKat Bridge.
    echo Install Python from https://www.python.org/downloads/windows/
    pause
    goto :eof
  )
)

:: Install dependencies on first run
if exist requirements.txt (
  echo Checking dependencies...
  %PYTHON% -m pip install -r requirements.txt -q 2>nul
  %PYTHON% -m playwright install chromium 2>nul
)

:: Run the bridge
%PYTHON% kitkat_bridge.py
if errorlevel 1 pause
endlocal
