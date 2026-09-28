@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 后端 API (8000)
echo 正在启动后端... 这个窗口不要关！
"%~dp0Global-CS-Paper-Awards-main\Scripts\python.exe" -m uvicorn api:app --host 127.0.0.1 --port 8000
echo.
echo ============================================
echo  后端已停止或出错。按任意键关闭此窗口。
echo  如果上面有红色报错，截图发给我。
echo ============================================
pause
