param([Parameter(Mandatory=$true)][string]$Origin, [switch]$Remove)
$ErrorActionPreference = 'Stop'
$startupDirectory = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupDirectory 'BMAPS Codex Worker.lnk'
if ($Remove) {
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
    Write-Host 'Automatic startup removed. Stop the worker from http://127.0.0.1:8765/connect'
    return
}
if ($Origin -notmatch '^https://[a-zA-Z0-9.-]+(:[0-9]+)?$') { throw 'Use an exact HTTPS origin.' }
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + "$PSScriptRoot\start.ps1" + '" -Origin "' + $Origin + '" -Background'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7
$shortcut.Save()
& "$PSScriptRoot/start.ps1" -Origin $Origin -Background
Write-Host 'Background worker and sign-in startup configured. Open BMAPS and click Codex connect.'
