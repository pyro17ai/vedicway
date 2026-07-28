[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8015,
    [string]$Python = "C:\Users\Huawei\.codex\mcp\pyjhora-mcp\.venv\Scripts\python.exe",
    [string]$PyJhoraSource = "C:\Users\Huawei\.codex\mcp\pyjhora-mcp\src",
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA "VedicWay\codex-runner"),
    [string]$FreeModel = "gpt-5.6-luna",
    [string]$PaidModel = "gpt-5.6-terra",
    [switch]$BootstrapAuthFromCurrentUser
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = (Resolve-Path -LiteralPath (Join-Path $backendRoot "src")).Path
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$pyJhoraPath = (Resolve-Path -LiteralPath $PyJhoraSource).Path
$runtimePath = [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($RuntimeRoot))
$codexHome = Join-Path $runtimePath "codex-home"
$agentWorkdir = Join-Path $runtimePath "empty-workdir"
$dataDir = Join-Path $runtimePath ("data-" + $Port)

New-Item -ItemType Directory -Force -Path $codexHome, $agentWorkdir, $dataDir | Out-Null

$authTarget = Join-Path $codexHome "auth.json"
if ($BootstrapAuthFromCurrentUser -and -not (Test-Path -LiteralPath $authTarget)) {
    $authSource = Join-Path $HOME ".codex\auth.json"
    if (-not (Test-Path -LiteralPath $authSource)) {
        throw "auth.json was not found in the current Codex profile. Run codex login first."
    }
    Copy-Item -LiteralPath $authSource -Destination $authTarget
}
if (-not (Test-Path -LiteralPath $authTarget)) {
    throw "Dedicated CODEX_HOME is not authenticated. Run once with -BootstrapAuthFromCurrentUser."
}
if (Get-ChildItem -Force -LiteralPath $agentWorkdir | Select-Object -First 1) {
    throw "Agent workdir must stay empty: $agentWorkdir"
}

$codexWrapper = (Get-Command codex.cmd -ErrorAction Stop).Source
$npmRoot = Split-Path -Parent $codexWrapper
$nativePattern = Join-Path $npmRoot "node_modules\@openai\codex\node_modules\@openai\codex-win32-*\vendor\*\bin\codex.exe"
$codexExecutable = Get-ChildItem -Path $nativePattern -File | Select-Object -First 1 -ExpandProperty FullName
if (-not $codexExecutable) {
    throw "Native npm Codex executable was not found. Reinstall @openai/codex."
}
$env:CODEX_HOME = $codexHome
& $codexExecutable login status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Dedicated CODEX_HOME authentication check failed."
}

$env:PYTHONPATH = $sourceRoot
$env:VEDICWAY_ENV = "development"
$env:VEDICWAY_DATA_DIR = $dataDir
$env:VEDICWAY_TEST_PAYMENTS = "1"
$env:VEDICWAY_PYJHORA_SOURCE = $pyJhoraPath
$env:VEDICWAY_INTERPRETATION_PROVIDER = "codex"
$env:VEDICWAY_CODEX_HOME = $codexHome
$env:VEDICWAY_AGENT_WORKDIR = $agentWorkdir
$env:VEDICWAY_CODEX_EXECUTABLE = $codexExecutable
$env:VEDICWAY_CODEX_FREE_MODEL = $FreeModel
$env:VEDICWAY_CODEX_PAID_MODEL = $PaidModel
$env:VEDICWAY_CODEX_FREE_REASONING = "low"
$env:VEDICWAY_CODEX_PAID_REASONING = "medium"
$env:VEDICWAY_CODEX_SERVICE_TIER = "fast"
$env:VEDICWAY_CODEX_FREE_TIMEOUT_SECONDS = "90"

Write-Host ("VedicWay Codex backend: http://127.0.0.1:" + $Port)
Write-Host ("Isolated runtime: " + $runtimePath)
& $pythonPath -m uvicorn vedicway_backend.main:app --host 127.0.0.1 --port $Port
