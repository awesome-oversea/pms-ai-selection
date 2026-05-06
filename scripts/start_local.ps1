#!/usr/bin/env powershell

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Set-Location $rootDir
$venvReadyMarker = Join-Path $rootDir ".venv\.pms_python_ready"

$pythonCandidates = @()
if (Test-Path $venvReadyMarker) {
    $pythonCandidates = @(
        (Join-Path $rootDir ".venv\Scripts\python.exe"),
        (Join-Path $rootDir ".venv\bin\python")
    )
}

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    }
}

if (-not $python) {
    Write-Error "Python is required. Create .venv or install python on PATH first."
    exit 1
}

$knownCommands = @("bootstrap", "summary", "check", "plan", "up")
$forwardedArgs = @()

if ($args.Length -gt 0 -and $knownCommands -contains $args[0]) {
    $forwardedArgs = $args
} else {
    $forwardedArgs = @("up", "--skip-deps", "--preflight") + $args
}

& $python "scripts/local_runtime_manager.py" @forwardedArgs
exit $LASTEXITCODE
