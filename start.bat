@echo off
rem AI 智能题库与刷题平台 — Windows 启动脚本
cd /d "%~dp0backend"

if not exist ".venv" (
  echo ==^> 创建虚拟环境...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo ==^> 安装依赖...
pip install -r requirements.txt -q

if not exist ".env" (
  echo ==^> 生成 .env...
  copy .env.example .env >nul
)

echo ==^> 启动服务: http://127.0.0.1:8017
python -m uvicorn app.main:app --host 0.0.0.0 --port 8017
pause
