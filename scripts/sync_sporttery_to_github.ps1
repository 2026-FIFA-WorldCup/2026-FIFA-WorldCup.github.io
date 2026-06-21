# Sync sporttery cache to GitHub (run on China network)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\sync_sporttery_to_github.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[1/4] Fetch sporttery odds..."
python scripts/update_sporttery_cache.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/4] Check git changes..."
git add data/sporttery_cache.json
$status = git status --porcelain data/sporttery_cache.json
if (-not $status) {
    Write-Host "No changes, skip push."
    exit 0
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm"
Write-Host "[3/4] Commit..."
git commit -m "chore: update sporttery cache $ts"

Write-Host "[4/4] Push to GitHub..."
git push

Write-Host "Done. Site will update in 1-2 min: https://2026-fifa-worldcup.github.io/"
