# Animatica fast full-quality bootstrap for Windows (~30-60s).
# Self-contained: installs uv if missing, clones the repo, installs Python deps,
# downloads the pre-baked TinyTeX zip, then verifies with animatica doctor.
# Usage: irm https://raw.githubusercontent.com/Abu103/animatica-manim/main/scripts/bootstrap.ps1 | iex
$ErrorActionPreference = "Stop"

$ghRepo   = if ($env:ANIMATICA_GH_REPO) { $env:ANIMATICA_GH_REPO } else { "Abu103/animatica-manim" }
$tinytexUrl = $env:ANIMATICA_TINYTEX_URL

# Locate or clone the repo (works both from a clone and when piped via irm|iex)
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "..\src\animatica\__init__.py"))) {
    $root = Split-Path $PSScriptRoot -Parent
} else {
    $root = Join-Path $env:USERPROFILE "animatica-manim"
    if (-not (Test-Path (Join-Path $root "src\animatica\__init__.py"))) {
        git clone "https://github.com/$ghRepo.git" $root
    }
}
Set-Location $root
Write-Host "Repo: $root"

# [0/3] uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[0/3] installing uv"
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:LOCALAPPDATA\Programs\uv\bin;$env:PATH"
}

# [1/3] python deps
Write-Host "[1/3] python deps (uv)"
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -e .

# [2/3] pre-baked TinyTeX zip (gh handles private repos when logged in)
Write-Host "[2/3] TinyTeX artifact"
$texOk = $false
$zip = Join-Path $env:TEMP "tinytex-manim.zip"
if ($tinytexUrl) {
    Invoke-WebRequest -Uri $tinytexUrl -OutFile $zip
    $texOk = $true
} elseif (Get-Command gh -ErrorAction SilentlyContinue) {
    gh release download --repo $ghRepo --pattern tinytex-manim.zip -O $zip --clobber
    if ($LASTEXITCODE -eq 0) { $texOk = $true }
}
if ($texOk) {
    $texDir = Join-Path $root ".tex"
    Expand-Archive -Force $zip $texDir
    $texBin = (Get-ChildItem (Join-Path $texDir "bin") -Directory | Select-Object -First 1).FullName
    Write-Host "TinyTeX ready. For this session: `$env:PATH = '$texBin;' + `$env:PATH"
} else {
    Write-Host "TinyTeX artifact unavailable -- falling back to doctor --fix"
    .\.venv\Scripts\animatica.exe doctor --fix
}

# [3/3] verify
Write-Host "[3/3] verifying"
.\.venv\Scripts\animatica.exe doctor
Write-Host "Done. Then: .venv\Scripts\activate; animatica make 'graph of sin(x)' -o out/"
