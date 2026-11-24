#!/usr/bin/env bash
# AI 智能题库与刷题平台 — 启动脚本
set -e
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "==> 创建虚拟环境..."
  python -m venv .venv
fi
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate

echo "==> 安装依赖..."
pip install -r requirements.txt -q

if [ ! -f ".env" ]; then
  echo "==> 生成 .env（默认配置，可修改）..."
  cp .env.example .env
fi

echo "==> 启动服务: http://127.0.0.1:8017"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8017 --reload
