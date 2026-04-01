param(
    [switch]$Install,
    [switch]$InstallPython,
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    param([string]$Version)

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py "-$Version" -c "import sys; print(sys.version)" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return @("py", "-$Version")
        }
    }

    return $null
}

function Invoke-CheckedCommand {
    param(
        [string]$Exe,
        [string[]]$CommandArgs
    )

    & $Exe @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Exe $($CommandArgs -join ' ')"
    }
}

function Install-PythonVersion {
    param([string]$Version)

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python $Version is required. Install winget or install Python manually from https://www.python.org/downloads/windows/"
    }

    Invoke-CheckedCommand -Exe "winget" -CommandArgs @("install", "--id", "Python.Python.$Version", "-e")
}

$pythonCmd = Get-PythonCommand -Version $PythonVersion
if (-not $pythonCmd) {
    if ($InstallPython) {
        Install-PythonVersion -Version $PythonVersion
        $pythonCmd = Get-PythonCommand -Version $PythonVersion
    }
}

if (-not $pythonCmd) {
    throw "Python $PythonVersion is required. Install it with: winget install --id Python.Python.$PythonVersion -e"
}

$pythonExe = $pythonCmd[0]
$pythonArgs = @()
if ($pythonCmd.Length -gt 1) {
    $pythonArgs = $pythonCmd[1..($pythonCmd.Length - 1)]
}
$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Invoke-CheckedCommand -Exe $pythonExe -CommandArgs ($pythonArgs + @("-m", "venv", ".venv"))
}

$venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to detect Python version inside .venv."
}

if ($venvVersion -ne $PythonVersion) {
    throw ".venv uses Python $venvVersion, expected $PythonVersion. Delete .venv and rerun after installing Python $PythonVersion."
}

if ($Install) {
    Invoke-CheckedCommand -Exe $venvPython -CommandArgs @("-m", "pip", "install", "-U", "pip", "setuptools", "wheel")
    Invoke-CheckedCommand -Exe $venvPython -CommandArgs @("-m", "pip", "install", "-r", "requirements-dev.txt")
}

& $venvPython -c "import pytest"
if ($LASTEXITCODE -ne 0) {
    throw "pytest is not installed in .venv. Run .\scripts\run-tests.ps1 -Install"
}

Invoke-CheckedCommand -Exe $venvPython -CommandArgs @("-m", "pytest", "-q", "tests\components\qld_fuel")
Invoke-CheckedCommand -Exe $venvPython -CommandArgs @(
    "-m", "mypy", "--config-file", "mypy.ini",
    "custom_components\qld_fuel"
)
