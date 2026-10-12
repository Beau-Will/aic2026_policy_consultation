#!/usr/bin/env bash
# 一键准备本地开发环境（Linux / macOS）
#
#   bash scripts/setup.sh
#
# 作用：创建 data/docs、生成 .env、建 .venv、按顺序安装两个平台 wheel 与依赖、跑版本预检。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[错误] 未找到 $PYTHON_BIN。请先安装 Python 3.12 ~ 3.14。" >&2
  exit 1
fi

PY_VER="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$PY_VER" in
  3.12|3.13|3.14) ;;
  *) echo "[警告] 检测到 Python $PY_VER；wit 要求 3.12 ~ 3.14，安装可能失败。" >&2 ;;
esac

echo "[1/5] 准备目录与 .env ..."
mkdir -p data/docs
if [ ! -f .env ]; then
  cp .env.example .env
  echo "      已生成 .env（记得填 OPENAI_API_KEY）"
else
  echo "      .env 已存在，保持不变"
fi

echo "[2/5] 创建虚拟环境 .venv ..."
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
VENV_PY="./.venv/bin/python"

echo "[3/5] 升级 pip ..."
"$VENV_PY" -m pip install --upgrade pip

echo "[4/5] 安装依赖（顺序不可颠倒：先 acps-sdk 2.2.0，再 wit-framework 2.1.0）..."
"$VENV_PY" -m pip install -r requirements.txt

echo "[5/5] 发行预检 ..."
./.venv/bin/policy-agent preflight

cat <<'DONE'

完成。接下来：
  1) 编辑 .env，填入 OPENAI_API_KEY（DeepSeek）
  2) 把法律法规原文放到 data/docs/（支持 md / txt / html / pdf / docx，可分子目录）
  3) 开始使用：
       source .venv/bin/activate
       policy-agent import ./data/docs
       policy-agent brief "你的问题" --out brief.md --json brief.json
     或者不激活虚拟环境，直接用：
       ./.venv/bin/policy-agent import ./data/docs

  Docker 方式见 README「快速开始 · Docker」。
DONE