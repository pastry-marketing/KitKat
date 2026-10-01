Option Explicit

Dim shell, fileSystem, bridgeFolder, trayScript, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

bridgeFolder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
trayScript = fileSystem.BuildPath(bridgeFolder, "kitkat_bridge_tray.ps1")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & trayScript & """"

shell.Run command, 0, False
