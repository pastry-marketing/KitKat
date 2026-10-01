@echo off
setlocal
title KitKat Bridge
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 kitkat_bridge.py
  goto finished
)

where python >nul 2>nul
if not errorlevel 1 (
  python kitkat_bridge.py
  goto finished
)

echo Python 3 is required to run KitKat Bridge.
echo Install Python from https://www.python.org/downloads/windows/

:finished
if errorlevel 1 pause
endlocal
