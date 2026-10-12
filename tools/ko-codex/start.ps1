param([Parameter(Mandatory=$true)][string]$Origin, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
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
python "$PSScriptRoot/bridge.py" --origin $Origin --codex $codexExecutable
