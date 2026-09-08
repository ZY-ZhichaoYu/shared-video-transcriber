param([switch]$Check,[switch]$InstallOnly,[switch]$SkipBrowser)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$forward = @()
if ($Check) { $forward += '--check' }
if ($InstallOnly) { $forward += '--install-only' }
if ($SkipBrowser) { $forward += '--skip-browser' }
if ($env:VIDEO_PYTHON) {
    if (-not (Test-Path -LiteralPath $env:VIDEO_PYTHON -PathType Leaf)) { throw 'VIDEO_PYTHON must point to an installed Python executable.' }
    & $env:VIDEO_PYTHON bootstrap.py @forward
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 bootstrap.py @forward
} elseif (Test-Path -LiteralPath '.venv\Scripts\python.exe') {
    & '.venv\Scripts\python.exe' bootstrap.py @forward
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand -or $pythonCommand.Source -like '*WindowsApps*') {
        Write-Host 'Python was not found. Install 64-bit Python 3.12 from https://www.python.org/downloads/'
        Write-Host 'Enable Add python.exe to PATH. Reopen this launcher after installation.'
        exit 1
    }
    & $pythonCommand.Source bootstrap.py @forward
}
exit $LASTEXITCODE
