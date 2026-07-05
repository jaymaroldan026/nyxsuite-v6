$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$updaterSpec = Join-Path $PSScriptRoot "updater.spec"

function Test-PythonLauncher($path) {
    if (!(Test-Path $path)) {
        return $false
    }
    try {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $path -c "import sys; print(sys.executable)" 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Resolve-PackagingPython {
    $candidates = @(
        (Join-Path $root "venv\Scripts\python.exe")
    )
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "NyxSuite\venv\Scripts\python.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-PythonLauncher $candidate) {
            return $candidate
        }
    }

    throw "No working packaging Python found. Create the v6 venv (see packaging\V6_RELEASE.md)."
}

$venvPython = Resolve-PackagingPython

if (!(Test-Path $updaterSpec)) {
    throw "Updater spec not found at $updaterSpec"
}

Push-Location $root
try {
    & $venvPython -m PyInstaller --noconfirm --clean $updaterSpec
} finally {
    Pop-Location
}

$distExe = Join-Path $root "dist\Updater.exe"
if (!(Test-Path $distExe)) {
    throw "Updater.exe was not produced at $distExe"
}

Write-Host "Updater built at: $distExe"
