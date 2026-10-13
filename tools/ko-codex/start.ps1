param([Parameter(Mandatory=$true)][string]$Origin, [switch]$CheckOnly, [switch]$Background)
$ErrorActionPreference = 'Stop'
if ($Background) {
    $existingBridge = $null
    try {
        $existingBridge = Invoke-WebRequest 'http://127.0.0.1:8765/connect' -UseBasicParsing -TimeoutSec 3
    } catch {
        if ($_.Exception.Response) { throw 'Port 8765 is already in use. Close the previous worker.' }
    }
    if ($existingBridge) {
        if ($existingBridge.Headers['X-BMAPS-Bridge-Version'] -eq '4') { return }
        throw 'An older worker is running. Close its window before restarting.'
    }
}
python -c "import pymupdf"
if ($LASTEXITCODE -ne 0) { throw 'Run python -m pip install -r requirements.txt first.' }
$codexCommand = Get-Command codex -ErrorAction SilentlyContinue
$codexExecutable = if ($codexCommand) { $codexCommand.Source } else { $null }
if (-not $codexExecutable) {
    $codexRoots = @(
        (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'),
        (Join-Path $env:USERPROFILE 'AppData\Local\OpenAI\Codex\bin')
    ) | Select-Object -Unique
    $codexCandidates = foreach ($codexRoot in $codexRoots) {
        if (Test-Path -LiteralPath $codexRoot) {
            Get-ChildItem -LiteralPath $codexRoot -Directory | ForEach-Object {
                $candidate = Join-Path $_.FullName 'codex.exe'
                if (Test-Path -LiteralPath $candidate) { Get-Item -LiteralPath $candidate }
            }
        }
    }
    $codexExecutable = ($codexCandidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName
}
if (-not $codexExecutable) { throw 'Codex CLI was not found. Install/open the Codex desktop app, then retry.' }
Write-Host "Codex executable: $codexExecutable"
& $codexExecutable login status
if ($LASTEXITCODE -ne 0) { throw "Sign in first: & '$codexExecutable' login" }
if ($CheckOnly) { Write-Host 'Python and Codex login checks passed.'; return }
if ($Background) {
    $workerData = Join-Path $env:USERPROFILE '.bmaps-ko-worker'
    New-Item -ItemType Directory -Force -Path $workerData | Out-Null
    $workerPython = (Get-Command python).Source
    $workerArgs = @('-u', ('"' + "$PSScriptRoot/bridge.py" + '"'), '--origin', ('"' + $Origin + '"'), '--codex', ('"' + $codexExecutable + '"'))
    $worker = Start-Process -FilePath $workerPython -ArgumentList $workerArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workerData 'worker.log') -RedirectStandardError (Join-Path $workerData 'worker-error.log')
    $worker.Id | Set-Content (Join-Path $workerData 'worker.pid')
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($worker.HasExited) { throw "Worker exited. Check $workerData\worker-error.log" }
        try {
            $ready = Invoke-WebRequest 'http://127.0.0.1:8765/connect' -UseBasicParsing -TimeoutSec 1
            if ($ready.Headers['X-BMAPS-Bridge-Version'] -eq '4') { return }
        } catch { }
    }
    throw "Worker did not become ready. Check $workerData\worker-error.log"
}
python "$PSScriptRoot/bridge.py" --origin $Origin --codex $codexExecutable
