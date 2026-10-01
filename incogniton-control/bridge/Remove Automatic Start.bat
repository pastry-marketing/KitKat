@echo off
setlocal
title KitKat Bridge Setup

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KitKat Bridge.lnk"

if exist "%SHORTCUT%" del /f /q "%SHORTCUT%"

echo.
echo KitKat Bridge will no longer start automatically with Windows.
echo To stop the bridge now, right-click its icon near the Windows clock
echo and choose "Stop bridge and exit".
echo.
pause
