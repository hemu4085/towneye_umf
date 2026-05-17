<#
.SYNOPSIS
  Bundle Towneye UMF for offline development under C:\aiops (override with -Root).

.DESCRIPTION
  - Mirrors the repository into <Root>\towneye_umf (excludes common junk dirs).
  - pip download requirements into <Root>\wheels (Windows Python) or
    <Root>\wheels-wsl when -UseWslPython is set (Linux-compatible wheels).
  - Writes requirements copy + install_offline.ps1 / install_offline.sh helpers.

.PARAMETER Root
  Output root. Default: C:\aiops

.PARAMETER UseWslPython
  Run pip inside WSL so wheels match Linux (typical when you code in Ubuntu WSL).

.PARAMETER SkipRepoCopy
  Only download wheels and helper scripts (faster if repo already synced).

.PARAMETER PythonExe
  Windows Python launcher or full path. Ignored when -UseWslPython is set.
#>
[CmdletBinding()]
param(
    [string]$Root = "C:\aiops",
    [switch]$UseWslPython,
    [switch]$SkipRepoCopy,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$ReqSrc = Join-Path $RepoRoot "requirements.txt"
if (-not (Test-Path -LiteralPath $ReqSrc)) {
    throw "requirements.txt not found at: $ReqSrc"
}

if ($UseWslPython) {
    $wslProbe = Start-Process -FilePath "wsl.exe" -ArgumentList @("--", "bash", "-lc", "echo ok") -Wait -PassThru -NoNewWindow
    if ($wslProbe.ExitCode -ne 0) {
        throw "WSL is required for -UseWslPython but 'wsl.exe' failed (exit $($wslProbe.ExitCode)). Install WSL or run without -UseWslPython."
    }
} else {
    & $PythonExe -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.10+ not found as '$PythonExe'. Pass -PythonExe 'py -3.12' or install Python."
    }
}

$destRoot = $Root.TrimEnd("\")
New-Item -ItemType Directory -Force -Path $destRoot | Out-Null

$wheelsRel = if ($UseWslPython) { "wheels-wsl" } else { "wheels" }
$wheelsDir = Join-Path $destRoot $wheelsRel
New-Item -ItemType Directory -Force -Path $wheelsDir | Out-Null

Write-Host "Repo:        $RepoRoot"
Write-Host "Bundle root: $destRoot"
Write-Host "Wheels dir:  $wheelsDir"

function ConvertTo-WslPath([string]$winPath) {
    if ($winPath -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLower()
        $rest = ($Matches[2] -replace '\\', '/').TrimEnd('/')
        return "/mnt/$drive/$rest"
    }
    throw "Path must be like C:\aiops for WSL conversion: $winPath"
}

if (-not $SkipRepoCopy) {
    $destRepo = Join-Path $destRoot "towneye_umf"
    New-Item -ItemType Directory -Force -Path $destRepo | Out-Null
    Write-Host "Mirroring repo -> $destRepo (robocopy /E, excludes venv caches)..."
    $rc = Start-Process -FilePath "robocopy.exe" -ArgumentList @(
        $RepoRoot, $destRepo, "/E",
        "/XD", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".ruff_cache",
        "/NFL", "/NDL", "/NJH", "/NJS", "/NS", "/NC", "/NP"
    ) -Wait -PassThru
    if ($rc.ExitCode -ge 8) {
        throw "robocopy failed with exit code $($rc.ExitCode)"
    }
}

Copy-Item -LiteralPath $ReqSrc -Destination (Join-Path $destRoot "requirements.txt") -Force

if ($UseWslPython) {
    $wslWheels = ConvertTo-WslPath $wheelsDir
    $wslReq = (ConvertTo-WslPath $destRoot) + "/requirements.txt"
    Write-Host "Downloading wheels via WSL pip -> $wslWheels ..."
    wsl.exe -- bash -lc "set -e; python3 -m pip install -q -U pip; python3 -m pip download -r `"$wslReq`" -d `"$wslWheels`""
} else {
    Write-Host "Downloading wheels via Windows pip..."
    & $PythonExe -m pip install -q -U pip
    & $PythonExe -m pip download -r (Join-Path $destRoot "requirements.txt") -d $wheelsDir
}

$installPs1 = @"
# Run after copying this folder to an offline machine (Windows Python).
`$here = Split-Path -Parent `$MyInvocation.MyCommand.Path
python -m pip install --no-index --find-links="`$(Join-Path `$here '$wheelsRel')" -r (Join-Path `$here "requirements.txt")
"@
Set-Content -Path (Join-Path $destRoot "install_offline.ps1") -Value $installPs1 -Encoding UTF8

$installShPath = Join-Path $destRoot "install_offline.sh"
$installShLines = @(
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
    ('python3 -m pip install --no-index --find-links="$here/' + $wheelsRel + '" -r "$here/requirements.txt"')
)
Set-Content -Path $installShPath -Value ($installShLines -join "`n") -Encoding UTF8

$envHint = @"
# Copy to .env on the offline machine (fill values while you still have secrets handy).
# DATABASE_URL=postgresql://...   # optional; omit for HashLinker offline mode
# GEMINI_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# TAVILY_API_KEY=
# TOWNEYE_LLM_MODEL=
"@
Set-Content -Path (Join-Path $destRoot "env.offline.example") -Value $envHint.TrimEnd() -Encoding UTF8

Write-Host "Done. Next offline:"
Write-Host "  Windows:  powershell -ExecutionPolicy Bypass -File `"$destRoot\install_offline.ps1`""
Write-Host "  Linux/WSL: bash `"$destRoot/install_offline.sh`"   (expects $wheelsRel + Linux wheels)"
