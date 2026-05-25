$ErrorActionPreference = "Stop"

$adminRoot = Split-Path -Parent $PSScriptRoot
Set-Location $adminRoot

# The backend uses a src/ layout; --app-dir makes local startup deterministic.
python -m uvicorn aqp_admin.main:app --port 8900 --app-dir src
