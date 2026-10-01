param()

$ErrorActionPreference = "Stop"
$bridgeDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$bridgeScript = Join-Path $bridgeDirectory "kitkat_bridge.py"
$stateDirectory = Join-Path $env:APPDATA "KitKat Bridge"
$logFile = Join-Path $stateDirectory "bridge.log"
$errorLogFile = Join-Path $stateDirectory "bridge-error.log"
$script:bridgeProcess = $null
$script:allowRestart = $true
$createdNew = $false
$singleInstanceMutex = New-Object System.Threading.Mutex($true, "Local\KitKatBridgeTray", [ref]$createdNew)

if (-not $createdNew) {
    exit
}

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null

function Find-Python {
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{ File = $pyLauncher.Source; Arguments = @("-3", "-u", "`"$bridgeScript`"") }
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; Arguments = @("-u", "`"$bridgeScript`"") }
    }

    throw "Python 3 was not found. Install Python 3, then start KitKat Bridge again."
}

function Start-BridgeProcess {
    if ($script:bridgeProcess -and -not $script:bridgeProcess.HasExited) {
        return
    }

    $pythonCommand = Find-Python
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "`r`n[$timestamp] Starting KitKat Bridge..."

    $script:bridgeProcess = Start-Process `
        -FilePath $pythonCommand.File `
        -ArgumentList $pythonCommand.Arguments `
        -WorkingDirectory $bridgeDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError $errorLogFile `
        -PassThru
}

function Stop-BridgeProcess {
    if ($script:bridgeProcess -and -not $script:bridgeProcess.HasExited) {
        Stop-Process -Id $script:bridgeProcess.Id -Force -ErrorAction SilentlyContinue
        $script:bridgeProcess.WaitForExit(3000) | Out-Null
    }
    $script:bridgeProcess = $null
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$openKitKat = $menu.Items.Add("Open KitKat")
$viewLog = $menu.Items.Add("View bridge log")
$restartBridge = $menu.Items.Add("Restart bridge")
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null
$stopBridge = $menu.Items.Add("Stop bridge and exit")

$trayIcon = New-Object System.Windows.Forms.NotifyIcon
$trayIcon.Icon = [System.Drawing.SystemIcons]::Application
$trayIcon.Text = "KitKat Bridge"
$trayIcon.ContextMenuStrip = $menu
$trayIcon.Visible = $true

$openKitKat.Add_Click({ Start-Process "https://kitkat-topaz.vercel.app/" })
$viewLog.Add_Click({
    if (-not (Test-Path $logFile)) {
        New-Item -ItemType File -Path $logFile -Force | Out-Null
    }
    Start-Process "notepad.exe" -ArgumentList "`"$logFile`""
})
$restartBridge.Add_Click({
    $script:allowRestart = $false
    Stop-BridgeProcess
    $script:allowRestart = $true
    Start-BridgeProcess
    $trayIcon.ShowBalloonTip(2500, "KitKat Bridge", "The bridge has restarted.", [System.Windows.Forms.ToolTipIcon]::Info)
})
$stopBridge.Add_Click({
    $script:allowRestart = $false
    Stop-BridgeProcess
    $trayIcon.Visible = $false
    [System.Windows.Forms.Application]::ExitThread()
})
$trayIcon.Add_DoubleClick({ Start-Process "https://kitkat-topaz.vercel.app/" })

$healthTimer = New-Object System.Windows.Forms.Timer
$healthTimer.Interval = 5000
$healthTimer.Add_Tick({
    if ($script:allowRestart -and $script:bridgeProcess -and $script:bridgeProcess.HasExited) {
        try {
            Start-BridgeProcess
        }
        catch {
            $trayIcon.Text = "KitKat Bridge - needs attention"
        }
    }
})

try {
    Start-BridgeProcess
    $healthTimer.Start()
    $trayIcon.ShowBalloonTip(2500, "KitKat Bridge", "Connected in the background. KitKat will start automatically with Windows.", [System.Windows.Forms.ToolTipIcon]::Info)
    [System.Windows.Forms.Application]::Run()
}
catch {
    $trayIcon.Visible = $false
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "KitKat Bridge", "OK", "Error") | Out-Null
}
finally {
    $healthTimer.Stop()
    Stop-BridgeProcess
    $trayIcon.Dispose()
    $menu.Dispose()
    if ($createdNew) {
        $singleInstanceMutex.ReleaseMutex()
    }
    $singleInstanceMutex.Dispose()
}
