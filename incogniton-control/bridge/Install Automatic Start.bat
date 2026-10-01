@echo off
setlocal
title KitKat Bridge Setup

set "BRIDGE_DIR=%~dp0"
set "INSTALL_DIR=%LOCALAPPDATA%\KitKat Bridge\App"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\KitKat Bridge.lnk"
set "LAUNCHER=%INSTALL_DIR%\Start KitKat Bridge Silently.vbs"
set "KITKAT_SHORTCUT=%SHORTCUT%"
set "KITKAT_LAUNCHER=%LAUNCHER%"
set "KITKAT_BRIDGE_DIR=%INSTALL_DIR%"
set "KITKAT_SOURCE_DIR=%BRIDGE_DIR%"

if not exist "%APPDATA%\KitKat Bridge\session.json" goto first_sign_in

echo.
echo Installing KitKat Bridge automatic start...

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Path $env:KITKAT_BRIDGE_DIR -Force | Out-Null; Copy-Item -Path (Join-Path $env:KITKAT_SOURCE_DIR '*') -Destination $env:KITKAT_BRIDGE_DIR -Recurse -Force; $shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($env:KITKAT_SHORTCUT); $shortcut.TargetPath = (Join-Path $env:WINDIR 'System32\wscript.exe'); $shortcut.Arguments = [char]34 + $env:KITKAT_LAUNCHER + [char]34; $shortcut.WorkingDirectory = $env:KITKAT_BRIDGE_DIR; $shortcut.Description = 'Start KitKat Bridge with Windows'; $shortcut.Save()"

if errorlevel 1 (
  echo.
  echo KitKat could not enable automatic start.
  echo Right-click this file and choose Run as administrator, then try again.
  echo.
  pause
  exit /b 1
)

start "" wscript.exe "%LAUNCHER%"

echo.
echo Done. KitKat Bridge is now running quietly in the background.
echo It will start automatically whenever you sign in to Windows.
echo The installed bridge is stored safely in your Windows user folder.
echo.
echo Look for the KitKat Bridge icon near the Windows clock.
echo Right-click the icon to open KitKat, restart the bridge, or stop it.
echo.
pause
exit /b 0

:first_sign_in
echo.
echo You need to sign in once before KitKat can run quietly.
echo The normal bridge will open now. Enter your KitKat email and password.
echo After it says the bridge is connected, close it and run this installer again.
echo.
pause
call "%BRIDGE_DIR%Start KitKat Bridge.bat"
