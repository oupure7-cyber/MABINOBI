# Build with an isolated DLL search path. Third-party image tools can otherwise
# inject obsolete Windows API DLLs into the standalone executable.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$originalPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$(Split-Path -Parent $pythonExe)"
    & $pythonExe -m PyInstaller --clean --noconfirm --distpath $projectRoot `
        --workpath (Join-Path $PSScriptRoot 'build') `
        (Join-Path $PSScriptRoot 'mabinobi.spec')
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $LASTEXITCODE" }
} finally {
    $env:PATH = $originalPath
}
