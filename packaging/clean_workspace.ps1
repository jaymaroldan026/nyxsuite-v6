param(
    [switch]$IncludeBuilds,
    [switch]$IncludeLogs,
    [switch]$IncludeOldReleases
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

function Remove-IfExists {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -Recurse -Force -LiteralPath $Path
        Write-Host "Removed: $Path"
    }
}

# ---------------------------------------------------------------------------
# Always: __pycache__ (all Python cache dirs, excluding venv)
# ---------------------------------------------------------------------------

Get-ChildItem -Path $root -Recurse -Filter "__pycache__" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "*\venv\*" } |
    ForEach-Object { Remove-IfExists $_.FullName }

# ---------------------------------------------------------------------------
# Always: temp/comparison folders
# ---------------------------------------------------------------------------

Remove-IfExists (Join-Path $root ".tmp_compare_v21")

# ---------------------------------------------------------------------------
# Always: legacy VBS launchers (replaced by PS1 equivalents)
# ---------------------------------------------------------------------------

foreach ($legacyPath in @(
    "run_bulk_ui.vbs",
    "run_play_ui.vbs",
    "run_nyx_ui.vbs",
    "portable_launch_nyx1.ps1",
    "fix_powershell_policy.bat"
)) {
    Remove-IfExists (Join-Path $root $legacyPath)
}

# ---------------------------------------------------------------------------
# Optional: build and dist artifacts
# ---------------------------------------------------------------------------

if ($IncludeBuilds) {
    Remove-IfExists (Join-Path $root "build")
    Remove-IfExists (Join-Path $root "dist")
}

# ---------------------------------------------------------------------------
# Optional: log files
# ---------------------------------------------------------------------------

if ($IncludeLogs) {
    Remove-IfExists (Join-Path $root "logs")
}

# ---------------------------------------------------------------------------
# Optional: old release versions and legacy extension zips.
#           Use -IncludeOldReleases to free several gigabytes of old builds.
# ---------------------------------------------------------------------------

if ($IncludeOldReleases) {
    foreach ($old in @("Nyx", "Nyx v2", "Nyx v2.1", "Nyx v2.2", "Nyx_repack", "Nyx v3_repack")) {
        Remove-IfExists (Join-Path $root "release\$old")
    }
    foreach ($zipName in @(
        "nyx_extension.zip",
        "Nyx_repack_extension.zip",
        "nyx_v2_1_extension.zip",
        "nyx_v2_extension.zip"
    )) {
        Remove-IfExists (Join-Path $root "release\$zipName")
    }
}

# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "Workspace cleanup complete." -ForegroundColor Green

if (-not $IncludeOldReleases) {
    Write-Host ""
    Write-Host "Tip: run with -IncludeOldReleases to also remove old release folders (several GB)." -ForegroundColor Yellow
}
