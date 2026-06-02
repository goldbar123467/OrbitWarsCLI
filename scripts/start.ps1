$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$python = "py"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
  $python = "python"
}

if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
  Write-Error "Python was not found. Install Python 3.11+ from python.org or the Microsoft Store, then rerun this script."
}

if (-not (Test-Path ".venv")) {
  & $python -m venv .venv
}

& ".\.venv\Scripts\Activate.ps1"
python -m pip install -U pip
python -m pip install -e .
kab start
