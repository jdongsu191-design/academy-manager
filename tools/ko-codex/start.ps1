param([Parameter(Mandatory=$true)][string]$Origin)
$ErrorActionPreference = 'Stop'
python -c "import pymupdf"
if ($LASTEXITCODE -ne 0) { throw 'python -m pip install -r requirements.txt 를 먼저 실행하세요.' }
codex login status
if ($LASTEXITCODE -ne 0) { throw 'codex login 으로 로그인하세요.' }
python "$PSScriptRoot/bridge.py" --origin $Origin
