# Animatica bootstrap for Windows.
#
#   irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
#
# One command: source, Python + manim, ffmpeg and (optionally) LaTeX, then a
# verification that only reports success when a render can actually work. On an
# interactive terminal it then launches `animatica setup`; unattended installs
# skip the wizard and print the command to run later.
#
# Windows needs no separate cairo/pango step: the Windows wheels of pycairo and
# manimpango contain the DLLs, so `pip install` alone gives a working manim.
# (That is what the bash installer has to fetch a bundle for on bare Linux.)
#
# Environment (all optional):
#   ANIMATICA_HOME        where to put the checkout      (default %USERPROFILE%\animatica-manim)
#   ANIMATICA_REF         git branch/tag to install      (default main)
#   ANIMATICA_TEX=0       skip the LaTeX step
#   ANIMATICA_SKIP_SETUP=1 install only; do not launch the setup wizard
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

function Test-InteractiveTerminal {
    if ($env:ANIMATICA_SKIP_SETUP -eq "1" -or $env:CI -or $env:GITHUB_ACTIONS) {
        return $false
    }
    try {
        return -not [Console]::IsInputRedirected
    } catch {
        return $false
    }
}

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

function Sync-ExistingCheckout {
    param([string]$Path)

    if (-not (Test-Path (Join-Path $Path ".git"))) {
        throw "The existing source at $Path is not a Git checkout, so it cannot be safely updated to '$ghRef'. Set ANIMATICA_HOME to a new folder (for example `$HOME\animatica-manim-test) and rerun."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is needed to update the existing checkout at $Path. Install Git or set ANIMATICA_HOME to a new folder."
    }

    Push-Location $Path
    $savedPreference = $ErrorActionPreference
    try {
        # Native git stderr must not become a terminating PowerShell error; check exit codes.
        $ErrorActionPreference = "Continue"
        $status = (& git status --porcelain 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect the existing checkout at $Path." }
        if ($status) {
            throw "The existing checkout at $Path has local changes. It was left untouched. Set ANIMATICA_HOME to a new folder and rerun to test $ghRef safely."
        }

        $remoteRef = "refs/remotes/origin/$ghRef"
        & git fetch --quiet origin "+refs/heads/${ghRef}:$remoteRef" 2>$null | Out-Null
        $fetchCode = $LASTEXITCODE
        if ($fetchCode -eq 0) {
            & git show-ref --quiet --verify "refs/heads/$ghRef" 2>$null
            $localBranchCode = $LASTEXITCODE
            if ($localBranchCode -eq 0) {
                & git merge-base --is-ancestor "refs/heads/$ghRef" $remoteRef 2>$null
                if ($LASTEXITCODE -ne 0) {
                    throw "Local branch $ghRef has commits not on origin; it was left untouched. Set ANIMATICA_HOME to a new folder to test safely."
                }
                & git switch --quiet $ghRef 2>$null
                if ($LASTEXITCODE -ne 0) { throw "Could not switch to branch $ghRef." }
                & git merge --ff-only --quiet $remoteRef 2>$null
                if ($LASTEXITCODE -ne 0) { throw "Could not fast-forward branch $ghRef to origin." }
            } else {
                & git switch --quiet --track --create $ghRef $remoteRef 2>$null
                if ($LASTEXITCODE -ne 0) { throw "Could not create local branch $ghRef from origin." }
            }
        } else {
            & git fetch --quiet origin "refs/tags/${ghRef}:refs/tags/${ghRef}" 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not fetch branch or tag '$ghRef' from origin. Check the ref/network, or use a fresh ANIMATICA_HOME folder."
            }
            & git switch --quiet --detach "refs/tags/$ghRef" 2>$null
            if ($LASTEXITCODE -ne 0) { throw "Could not check out tag $ghRef." }
        }

        $branch = (& git branch --show-current 2>$null | Out-String).Trim()
        $head = (& git rev-parse --short HEAD 2>$null | Out-String).Trim()
        if ($branch) { Write-Host "  -> $branch @ $head" }
        else { Write-Host "  -> tag $ghRef @ $head" }
    } finally {
        $ErrorActionPreference = $savedPreference
        Pop-Location
    }
}

# --------------------------------------------------------------------------- #
# 0. source: a checkout, a git clone, or a plain ZIP (no git needed)
# --------------------------------------------------------------------------- #
$useExistingRoot = $false
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "..\src\animatica\__init__.py"))) {
    $root = Split-Path $PSScriptRoot -Parent
    Write-Host "Using the checkout at $root"
} else {
    $root = if ($env:ANIMATICA_HOME) { $env:ANIMATICA_HOME } else { Join-Path $env:USERPROFILE "animatica-manim" }
    if (Test-Path (Join-Path $root "src\animatica\__init__.py")) {
        Write-Host "Using the existing checkout at $root"
        $useExistingRoot = $true
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
if ($useExistingRoot) { Sync-ExistingCheckout -Path $root }
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

# uv venvs ship without pip; add it so `pip install <extra>` works for the user too.
$ErrorActionPreference = "Continue"
& $py -m ensurepip --upgrade *> $null
$ErrorActionPreference = "Stop"

Write-Host "  installing animatica + manim + TUI (this is the slow part)"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Invoke-Checked "uv pip install" { uv pip install --python $py -e ".[tui]" }
} else {
    Invoke-Checked "pip install" { & $py -m pip install --disable-pip-version-check -q -e ".[tui]" }
}
$animatica = Join-Path $root ".venv\Scripts\animatica.exe"
if (-not (Test-Path $animatica)) { throw "animatica.exe was not created in .venv\Scripts." }

# --------------------------------------------------------------------------- #
# 3. LaTeX (optional: needed for MathTex, not for text or shapes)
# --------------------------------------------------------------------------- #
if ($doTex) {
    Write-Step "3/4" "LaTeX for equations (optional)"

    # The prebuilt Windows bundle is tried first: it is a verified download,
    # while the upstream TinyTeX installer is a live network call that failed
    # with HTTP 504 in CI. The bundle is only used when its sha256 is known
    # and matches; otherwise `animatica doctor --fix` falls back to upstream.
    $texDir = Join-Path $root ".tex"
    $texBin = Join-Path $texDir "bin\windows"
    if (Test-Path (Join-Path $texBin "latex.exe")) {
        Write-Host "  -> LaTeX bundle already unpacked in $texDir"
    } else {
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
$parsed = $raw | ConvertFrom-Json
$checkResults = New-Object 'System.Collections.Generic.List[object]'
function Add-DoctorCheck {
    param([object]$Value, [System.Collections.Generic.List[object]]$Results)
    if ($null -eq $Value) { return }
    if ($Value -is [System.Array]) {
        foreach ($item in $Value) { Add-DoctorCheck -Value $item -Results $Results }
    } else {
        [void]$Results.Add($Value)
    }
}
Add-DoctorCheck -Value $parsed -Results $checkResults
$checks = $checkResults.ToArray()
if ($checks.Count -eq 0) { throw "doctor --json returned no checks; refusing to report success." }
foreach ($c in $checks) {
    if ($null -eq $c -or $c.PSObject.Properties.Name -notcontains "name" -or
        $c.PSObject.Properties.Name -notcontains "ok" -or
        $c.name -isnot [string] -or $c.ok -isnot [bool]) {
        throw "doctor --json returned an unexpected result; refusing to report success."
    }
}
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

# In CI (or any scripted use) make the fresh tools visible to later steps.
if ($env:GITHUB_PATH) {
    Add-Content $env:GITHUB_PATH (Join-Path $root ".venv\Scripts")
    $uvDir = Split-Path (Get-Command uv -ErrorAction SilentlyContinue).Source -ErrorAction SilentlyContinue
    if ($uvDir) { Add-Content $env:GITHUB_PATH $uvDir }
}

Write-Host ""
Write-Host "Install complete and verified."
if (Test-InteractiveTerminal) {
    Write-Host "Starting Animatica setup. Choose Template for offline examples, or an AI provider."
    $ErrorActionPreference = "Continue"
    & $animatica setup
    $setupExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($setupExitCode -ne 0) {
        Write-Host "Setup wizard exited with status $setupExitCode. The install is complete; rerun:"
        Write-Host "  $animatica setup"
        throw "First-run setup did not finish (exit code $setupExitCode)."
    }
    Write-Host ""
    Write-Host "Setup complete. Open Animatica Studio with:"
    Write-Host "  $animatica tui"
} else {
    if ($env:ANIMATICA_SKIP_SETUP -eq "1") {
        Write-Host "Interactive setup skipped (ANIMATICA_SKIP_SETUP=1)."
    } else {
        Write-Host "No interactive terminal detected; install is ready."
    }
    Write-Host "Run this in a terminal to configure your provider:"
    Write-Host "  $animatica setup"
}
