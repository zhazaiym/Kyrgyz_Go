param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\kyrgyzgo_ec2_deploy'),
    [string]$PythonExecutable = 'python',
    [switch]$Check,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$arguments = @('--key', $KeyPath)
if ($Check) { $arguments += '--check' }
if ($SkipTests) { $arguments += '--skip-tests' }

Push-Location $projectRoot
try {
    & $PythonExecutable -m scripts.manual_deploy @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment failed (exit code $LASTEXITCODE). See the error above."
    }
}
finally {
    Pop-Location
}
