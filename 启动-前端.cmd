@echo off
chcp 65001 >nul
cd /d "%~dp0frontend"
title 前端页面 (5173)
echo 正在启动前端... 这个窗口不要关！
call npm run dev
echo.
echo ============================================
echo  前端已停止或出错。按任意键关闭此窗口。
echo  如果上面有报错，截图发给我。
echo ============================================
pause
