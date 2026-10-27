# GAME-only unsigned Windows EXE build entrypoint for Repository-Provisioner-game.
# Never creates an MSIX or invents Partner Center Store Identity.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path ([System.IO.Path]::GetTempPath()) ('signal-sprint-builder-' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $root 'dist/game/SignalSprint.exe'
try {
    Set-Location -LiteralPath $root
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $venv
    } else {
        & python -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed' }
    $venvPython = Join-Path $venv 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Isolated Python executable missing'
    }
    & $venvPython -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required for reproducible GAME build' }

    & $venvPython -m unittest discover -s products/signal-sprint/tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Real GAME gameplay smoke tests failed' }
    & $venvPython -m pip install --disable-pip-version-check 'pyinstaller==6.16.0'
    if ($LASTEXITCODE -ne 0) { throw 'Pinned PyInstaller installation failed' }
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --name SignalSprint --distpath dist/game --workpath dist/work --specpath dist/spec products/signal-sprint/main.py
    if ($LASTEXITCODE -ne 0) { throw 'Unsigned Windows GAME EXE build failed' }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'GAME EXE output missing' }
    $bytes = [System.IO.File]::ReadAllBytes($target)
    if ($bytes.Length -lt 100000 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) {
        throw 'GAME output is not a plausible Windows PE executable'
    }
    $sha = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "GAME_UNSIGNED_EXE=$target"
    Write-Host "GAME_UNSIGNED_EXE_SHA256=$sha"
    Write-Host 'OFFICIAL_IDENTITY=HOLD; MSIX=NOT_BUILT; STORE_SUBMISSION=FORBIDDEN'
} finally {
    if (Test-Path -LiteralPath $venv) {
        Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue
    }
}
