# 本地定时同步体育彩票到 GitHub Pages
#
# 用法（PowerShell）：
#   .\scripts\sync_sporttery_to_github.ps1
#
# 定时任务（每天/每30分钟）：
#   1. Win+R → taskschd.msc → 创建基本任务
#   2. 操作 → 启动程序 → 程序：powershell.exe
#   3. 参数：-ExecutionPolicy Bypass -File "D:\DESKTOP\fifa\scripts\sync_sporttery_to_github.ps1"
#
# 前提：本机已 git push 授权（gh auth 或 credential manager）

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> 抓取体育彩票..."
python scripts/update_sporttery_cache.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> 检查是否有变化..."
git add data/sporttery_cache.json
$status = git status --porcelain data/sporttery_cache.json
if (-not $status) {
    Write-Host "缓存无变化，跳过推送"
    exit 0
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "chore: 更新体育彩票缓存 $ts"
Write-Host "==> 推送到 GitHub（将触发 Pages 自动部署）..."
git push

Write-Host "完成。约 1～2 分钟后访问 https://2026-fifa-worldcup.github.io/"
