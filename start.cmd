@echo off
cd /d "%~dp0"
"%~dp0Global-CS-Paper-Awards-main\Scripts\python.exe" -m streamlit run "%~dp0streamlit_app.py" --server.port 8501 --server.headless false
pause
