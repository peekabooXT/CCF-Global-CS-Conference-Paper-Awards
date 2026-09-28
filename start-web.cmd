@echo off
REM 一键启动新版 Vue 前端（FastAPI 后端 + Vite 开发服务器）
cd /d "%~dp0"
set PY=%~dp0Global-CS-Paper-Awards-main\Scripts\python.exe

echo [1/2] 启动后端 FastAPI (http://127.0.0.1:8000) ...
start "ccf-api" cmd /k ""%PY%" -m uvicorn api:app --host 127.0.0.1 --port 8000"

echo [2/2] 启动前端 Vite (http://127.0.0.1:5173) ...
start "ccf-web" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo 两个窗口已分别启动：
echo   后端 API 文档：http://127.0.0.1:8000/docs
echo   前端页面：     http://127.0.0.1:5173
echo.
echo 关闭对应的命令行窗口即可停止服务。
pause
