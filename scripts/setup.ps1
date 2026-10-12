# 一键准备本地开发环境（Windows PowerShell）
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
#
# 作用：创建 data\docs、生成 .env、建 .venv、按顺序安装两个平台 wheel 与依赖、跑版本预检。
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

Write-Host "[1/5] 准备目录与 .env ..."
New-Item -ItemType Directory -Force -Path "data\docs" | Out-Null
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "      已生成 .env（记得填 OPENAI_API_KEY）"
} else {
    Write-Host "      .env 已存在，保持不变"
}

Write-Host "[2/5] 创建虚拟环境 .venv ..."
if (-not (Test-Path ".venv")) { python -m venv .venv }

Write-Host "[3/5] 升级 pip ..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "[4/5] 安装依赖（顺序不可颠倒：先 acps-sdk 2.2.0，再 wit-framework 2.1.0）..."
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "[5/5] 发行预检 ..."
& .\.venv\Scripts\policy-agent.exe preflight

Write-Host ""
Write-Host "完成。接下来："
Write-Host "  1) 编辑 .env，填入 OPENAI_API_KEY（DeepSeek）"
Write-Host "  2) 把法律法规原文放到 data\docs\（支持 md / txt / html / pdf / docx，可分子目录）"
Write-Host "  3) 开始使用："
Write-Host "       .\.venv\Scripts\Activate.ps1"
Write-Host "       policy-agent import .\data\docs"
Write-Host "       policy-agent brief \"你的问题\" --out brief.md --json brief.json"
Write-Host ""
Write-Host "  Docker 方式见 README「快速开始 · Docker」；Linux / macOS 用 bash scripts/setup.sh。"
