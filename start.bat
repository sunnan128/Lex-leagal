@echo off
chcp 65001 >nul
echo Starting Legal QA System...

echo.
echo [1/2] Starting Backend Service...
start "Legal QA Backend" cmd /k "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload"

timeout /t 5 /nobreak >nul

echo.
echo [2/2] Starting Frontend Service...
set STREAMLIT_SERVER_HEADLESS=true
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set STREAMLIT_SERVER_PORT=8501
start "Legal QA Frontend" cmd /k "python -m streamlit run frontend/app.py --server.headless true --browser.gatherUsageStats false"

echo.
echo ========================================
echo System Started Successfully!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:8501
echo API Docs: http://localhost:8002/docs
echo ========================================
echo.
echo Opening browser...
timeout /t 3 /nobreak >nul
start http://localhost:8501
