# Run the FasalDesk backend (Windows PowerShell).
#   backend\scripts\dev.ps1            -> http://localhost:8000
#   backend\scripts\dev.ps1 -Port 8080
param(
    [int]$Port = 8000,
    [string]$BindHost = "0.0.0.0",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$BackendDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "venv python not found at $Python"
}

Push-Location $BackendDir
try {
    $arguments = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", $Port)
    if (-not $NoReload) { $arguments += "--reload" }
    Write-Host "FasalDesk backend on http://localhost:$Port (docs at /docs)"
    & $Python @arguments
}
finally {
    Pop-Location
}
