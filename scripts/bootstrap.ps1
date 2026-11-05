# Animatica bootstrap for Windows.
# Installs uv if missing, clones the repo, installs Python deps into .venv, installs TinyTeX
# (official upstream installer, via `animatica doctor --fix --yes`) if LaTeX is missing, then
# verifies with `animatica doctor`. It only prints "Done" if that final check passes.
#
# Usage (from a clone):   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
# Usage (one-liner):      irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
#
# Failures use `throw` (not `exit`) so a failure under `irm | iex` does not close your terminal.
$ErrorActionPreference = "Stop"
# Python warnings (e.g. a SyntaxWarning inside a dependency on a new Python) are written to stderr. In
# Windows PowerShell, with "Stop" and a redirect, stderr text becomes a terminating error and killed step 3
# on a real PC. Silence them for child processes, and never treat stderr text as failure (exit codes decide).
$env:PYTHONWARNINGS = "ignore"

$ghRepo = if ($env:ANIMATICA_GH_REPO) { $env:ANIMATICA_GH_REPO } else { "Abu103/animatica-manim" }

# Run a native command and fail loudly on a nonzero exit code
# ($ErrorActionPreference does not stop on failing native programs).
function Invoke-Checked {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

# Locate or clone the repo (works from a clone and when piped via irm | iex)
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "..\src\animatica\__init__.py"))) {
    $root = Split-Path $PSScriptRoot -Parent
} else {
    $root = Join-Path $env:USERPROFILE "animatica-manim"
    if (-not (Test-Path (Join-Path $root "src\animatica\__init__.py"))) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "Git is not installed. Install it (winget install Git.Git), open a NEW terminal, and re-run; or download the repo ZIP from https://github.com/$ghRepo and run scripts\bootstrap.ps1 from it."
        }
        Invoke-Checked "git clone" { git clone "https://github.com/$ghRepo.git" $root }
    }
}
Set-Location $root
Write-Host "Repo: $root"

# [1/4] uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[1/4] installing uv"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    # The installer updates the user PATH for NEW shells only; find uv for this one.
    foreach ($d in @("$env:USERPROFILE\.local\bin", "$env:LOCALAPPDATA\Programs\uv\bin", "$env:USERPROFILE\.cargo\bin")) {
        if (Test-Path (Join-Path $d "uv.exe")) { $env:PATH = "$d;$env:PATH"; break }
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv was installed but is not on PATH for this session. Open a NEW terminal and re-run this script."
    }
} else {
    Write-Host "[1/4] uv already installed"
}

# [2/4] python deps (reuses an existing .venv)
Write-Host "[2/4] python deps (uv)"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Invoke-Checked "uv venv" { uv venv .venv }
}
Invoke-Checked "uv pip install" { uv pip install --python ".\.venv\Scripts\python.exe" -e . }
$animatica = Join-Path $root ".venv\Scripts\animatica.exe"
if (-not (Test-Path $animatica)) { throw "animatica.exe was not created in .venv\Scripts." }

# [3/4] LaTeX. Windows needs a Windows-native TeX; the official TinyTeX installer is used.
# (animatica itself finds a TinyTeX install even if it is not on PATH.)
Write-Host "[3/4] checking LaTeX / ffmpeg"
$ErrorActionPreference = "Continue"
& $animatica doctor *> $null
$doctorExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($doctorExit -ne 0) {
    Write-Host "Something is missing -- running: animatica doctor --fix --yes"
    $ErrorActionPreference = "Continue"
    & $animatica doctor --fix --yes
    $ErrorActionPreference = "Stop"
    # exit status of this command reflects the state AFTER the fix attempt
}

# [4/4] final verification: the only thing allowed to say 'Done'
Write-Host "[4/4] verifying"
Invoke-Checked "animatica doctor" { & $animatica doctor }

Write-Host ""
Write-Host "Done. Activate with:  .venv\Scripts\Activate.ps1"
Write-Host "Then try:  animatica make 'graph of sin(x)' -o out"
Write-Host "Animatica finds TinyTeX itself. For other tools, open a NEW terminal so the PATH change takes effect."
