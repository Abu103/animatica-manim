# Animatica fast full-quality bootstrap for Windows (~25-40s).
# Self-contained: installs uv if missing, installs Python deps and downloads the
# pre-baked TinyTeX zip IN PARALLEL, then verifies with animatica doctor.
# Usage: irm <raw>/scripts/bootstrap.ps1 | iex
$ErrorActionPreference = "Continue"
$ghRepo = if ($env:ANIMATICA_GH_REPO) { $env:ANIMATICA_GH_REPO } else { "Abu103/animatica-manim" }
# When piped via irm|iex, $PSScriptRoot is empty: clone into a fresh folder instead
if ($PSScriptRoot -and (Test-Path "$PSScriptRoot\..\src\animatica")) {
    Set-Location "$PSScriptRoot\.."
    $root = (Get-Location).Path
} else {
    $root = Join-Path $env:USERPROFILE "animatica-manim"
    if (-not (Test-Path "$root\src\animatica")) {
        git clone "https://github.com/$ghRepo.git" $root
    }
    Set-Location $root
}

$tinytexUrl = $env:ANIMATICA_TINYTEX_URL
$ghRepo = if ($env:ANIMATICA_GH_REPO) { $env:ANIMATICA_GH_REPO } else { "Abu103/animatica-manim" }
$tinytexDir = Join-Path $root ".tex"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[0/3] installing uv"
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH = "$env:LOCALAPPDATA\uv\bin;$env:PATH"
}

Write-Host "[1/3] python deps (uv, parallel with TeX download)"
$py = Start-Process -PassThru -NoNewWindow -Wait:$false powershell -ArgumentList \
    "uv venv '$root\.venv'; uv pip install --python '$root\.venv\Scripts\python.exe' -e '$root'"
$texScript = @"
if ('$tinytexUrl') { Invoke-WebRequest -Uri '$tinytexUrl' -OutFile '$env:TEMP\tinytex-manim.zip' }
elseif (Get-Command gh -ErrorAction SilentlyContinue) {
    gh release download --repo '$ghRepo' --pattern tinytex-manim.zip -O '$env:TEMP\tinytex-manim.zip'
} else { exit 1 }
"@
$tex = Start-Process -PassThru -NoNewWindow -Wait:$false powershell -ArgumentList $texScript
Wait-Process -Id $py.Id
$texOk = (Wait-Process -Id $tex.Id -PassThru).ExitCode -eq 0

if ($texOk) {
    Expand-Archive -Force "$env:TEMP\tinytex-manim.zip" $tinytexDir
    $texBin = (Get-ChildItem "$tinytexDir\bin" -Directory | Select-Object -First 1).FullName
    Write-Host "[2/3] TinyTeX ready. For this session: `$env:PATH = '$texBin;`$env:PATH'"
} else {
    Write-Host "[2/3] pre-baked TinyTeX zip unavailable -- falling back to doctor --fix"
    & "$root\.venv\Scripts\animatica.exe" doctor --fix
}

Write-Host "[3/3] verifying"
& "$root\.venv\Scripts\animatica.exe" doctor
Write-Host "Done. Then: .venv\Scripts\activate; animatica make 'graph of sin(x)' -o out/"
