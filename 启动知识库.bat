@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到 .venv\Scripts\python.exe，请先按 README.md 安装依赖。
  pause
  exit /b 1
)

echo 正在启动 AI 设计管理知识库...
start "AI设计管理知识库服务" /b ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000/"
endlocal
