# 一键准备本地开发环境（Windows PowerShell）
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

Write-Host "[1/4] 创建虚拟环境 .venv ..."
if (-not (Test-Path ".venv")) { python -m venv .venv }

Write-Host "[2/4] 升级 pip ..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "[3/4] 安装依赖（先 acps-sdk，后 wit-framework）..."
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "[4/4] 版本预检 ..."
& .\.venv\Scripts\policy-agent.exe preflight

Write-Host ""
Write-Host "完成。下一步："
Write-Host "  Copy-Item .env.example .env   # 填入 OPENAI_API_KEY"
Write-Host "  .\.venv\Scripts\policy-agent.exe import .\data\docs"
Write-Host "  .\.venv\Scripts\policy-agent.exe search \"关键词\""
