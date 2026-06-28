# CHRONOS launcher (Windows PowerShell)
# Builds the plant memory if needed, then starts the app.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Building CHRONOS plant memory..." -ForegroundColor Cyan
python -m chronos.pipeline

Write-Host "Starting CHRONOS server on http://127.0.0.1:8000 ..." -ForegroundColor Green
python -m chronos.server
