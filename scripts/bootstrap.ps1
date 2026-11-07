# Animatica bootstrap for Windows.
#
#   irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
#
# One command: source, Python + manim, ffmpeg and (optionally) LaTeX, then a
# verification that only prints "Ready" when a render can actually work.
# Afterwards run `animatica tui` - the studio is where quality, theme, provider
# and API keys are set, and the choices are remembered.
#
# Windows needs no separate cairo/pango step: the Windows wheels of pycairo and
# manimpango contain the DLLs, so `pip install` alone gives a working manim.
# (That is what the bash installer has to fetch a bundle for on bare Linux.)
#
# Environment (all optional):
#   ANIMATICA_HOME        where to put the checkout      (default %USERPROFILE%\animatica-manim)
#   ANIMATICA_REF         git branch/tag to install      (default main)
#   ANIMATICA_TEX=0       skip the LaTeX step
#
# Failures use `throw` (not `exit`) so a failure under `irm | iex` does not close
# your terminal.
$ErrorActionPreference = "Stop"
# Python warnings (e.g. a SyntaxWarning inside a dependency on a new Python) are written to
# stderr. In Windows PowerShell, with "Stop" and a redirect, stderr text becomes a terminating
# error and can kill a later step. Silence them for child processes; exit codes decide.
$env:PYTHONWARNINGS = "ignore"

$ghRepo = if ($env:ANIMATICA_GH_REPO) { $env:ANIMATICA_GH_REPO } else { "Abu103/animatica-manim" }
$ghRef = if ($env:ANIMATICA_REF) { $env:ANIMATICA_REF } else { "main" }
$doTex = $env:ANIMATICA_TEX -ne "0"

function Invoke-Checked {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function Write-Step {
    param([string]$Number, [string]$Text)
    Write-Host ""
    Write-Host "[$Number] $Text"
}

# --------------------------------------------------------------------------- #
# 0. source: a checkout, a git clone, or a plain ZIP (no git needed)
# --------------------------------------------------------------------------- #
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "..\src\animatica\__init__.py"))) {
    $root = Split-Path $PSScriptRoot -Parent
    Write-Host "Using the checkout at $root"
} else {
    $root = if ($env:ANIMATICA_HOME) { $env:ANIMATICA_HOME } else { Join-Path $env:USERPROFILE "animatica-manim" }
    if (Test-Path (Join-Path $root "src\animatica\__init__.py")) {
        Write-Host "Using the existing checkout at $root"
    } else {
        Write-Step "0/4" "downloading Animatica ($ghRef)"
        if (Get-Command git -ErrorAction SilentlyContinue) {
            Invoke-Checked "git clone" { git clone --depth 1 --branch $ghRef "https://github.com/$ghRepo.git" $root }
        } else {
            $tmp = Join-Path $env:TEMP ("animatica-src-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
            New-Item -ItemType Directory -Path $tmp | Out-Null
            $zip = Join-Path $tmp "source.zip"
            Invoke-WebRequest "https://codeload.github.com/$ghRepo/zip/refs/heads/$ghRef" -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
            if (-not $inner) { throw "the downloaded archive did not contain a folder" }
            if (Test-Path $root) { Remove-Item $root -Recurse -Force }
            Move-Item $inner.FullName $root
            Remove-Item $tmp -Recurse -Force
        }
    }
}
Set-Location $root
Write-Host "  -> $root"

# --------------------------------------------------------------------------- #
# 1. cairo + pango: already inside the Windows wheels, so this is a check
# --------------------------------------------------------------------------- #
Write-Step "1/4" "cairo/pango"
Write-Host "  -> nothing to install: the pycairo/manimpango Windows wheels ship the DLLs"

# --------------------------------------------------------------------------- #
# 2. python env + animatica
# --------------------------------------------------------------------------- #
Write-Step "2/4" "python environment"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  installing uv"
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Write-Host "  uv installer unavailable; using python -m venv instead"
    }
    # The installer updates the user PATH for NEW shells only; find uv for this one.
    foreach ($d in @("$env:USERPROFILE\.local\bin", "$env:LOCALAPPDATA\Programs\uv\bin", "$env:USERPROFILE\.cargo\bin")) {
        if (Test-Path (Join-Path $d "uv.exe")) { $env:PATH = "$d;$env:PATH"; break }
    }
}
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Invoke-Checked "uv venv" { uv venv .venv }
    } else {
        Invoke-Checked "python -m venv" { python -m venv .venv }
    }
}
Write-Host "  -> $py"

Write-Host "  installing animatica + manim (this is the slow part)"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Invoke-Checked "uv pip install" { uv pip install --python $py -e . }
} else {
    Invoke-Checked "pip install" { & $py -m pip install --disable-pip-version-check -q -e . }
}
$animatica = Join-Path $root ".venv\Scripts\animatica.exe"
if (-not (Test-Path $animatica)) { throw "animatica.exe was not created in .venv\Scripts." }

# --------------------------------------------------------------------------- #
# 3. LaTeX (optional: needed for MathTex, not for text or shapes)
# --------------------------------------------------------------------------- #
if ($doTex) {
    Write-Step "3/4" "LaTeX for equations (optional)"
    $ErrorActionPreference = "Continue"
    & $animatica doctor *> $null
    $doctorExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($doctorExit -ne 0) {
        Write-Host "  running: animatica doctor --fix --yes"
        $ErrorActionPreference = "Continue"
        & $animatica doctor --fix --yes
        $ErrorActionPreference = "Stop"
    } else {
        Write-Host "  -> already available"
    }
} else {
    Write-Step "3/4" "LaTeX: skipped (ANIMATICA_TEX=0)"
}

# --------------------------------------------------------------------------- #
# 4. verify (LaTeX is optional, so only the other checks decide success)
# --------------------------------------------------------------------------- #
Write-Step "4/4" "verifying"
$ErrorActionPreference = "Continue"
$raw = (& $animatica doctor --json) -join "`n"
$ErrorActionPreference = "Stop"
$checks = @($raw | ConvertFrom-Json)
foreach ($c in $checks) {
    if ($c.ok) {
        Write-Host ("[OK ] {0}: {1}" -f $c.name, $c.detail)
        if ($c.fix) { Write-Host ("       tip: {0}" -f $c.fix) }
    } else {
        Write-Host ("[FAIL] {0}: {1}" -f $c.name, $c.detail)
        if ($c.fix) { Write-Host ("       fix: {0}" -f $c.fix) }
    }
}
$required = @($checks | Where-Object { -not $_.ok -and $_.name -ne "latex" })
if ($required.Count -gt 0) {
    throw "Setup is not complete (see the FAIL lines above). Re-run this script, or: `"$animatica`" doctor --fix --yes"
}

$latexMissing = @($checks | Where-Object { -not $_.ok -and $_.name -eq "latex" }).Count -gt 0
if ($latexMissing) {
    Write-Host ""
    Write-Host "Note: LaTeX is missing, so MathTex/equation scenes will warn."
    Write-Host "      Text, shapes, charts and everything else render fine."
    Write-Host "      Add it later with: animatica doctor --fix"
}

Write-Host ""
Write-Host "Ready. Two commands from here:"
Write-Host ""
Write-Host "  $animatica tui                 # do everything, and set your defaults, here"
Write-Host "  $animatica make `"graph of sin(x)`" -o out"
Write-Host ""
Write-Host "The studio is where you pick quality, theme, provider and API keys: pick with"
Write-Host "the arrow keys or start typing to filter the list. Choices are remembered."
