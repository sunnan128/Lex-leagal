@echo off
chcp 65001 >nul
title LexAI 一键评估

echo ========================================
echo   LexAI 一键评估脚本
echo   模式：Baseline + Rerank
echo ========================================
echo.

set VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe
if not exist "%VENV_PYTHON%" (
    echo ❌ 未找到虚拟环境 Python: %VENV_PYTHON%
    echo    请确认 .venv 存在
    pause
    exit /b 1
)

echo 检查后端连接...
curl -s http://localhost:8002/health >nul 2>&1
if errorlevel 1 (
    echo ❌ 后端服务未运行，请先启动后端
    echo    启动命令：.\.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002
    pause
    exit /b 1
)
echo ✅ 后端连接正常
echo.

echo [1/2] 评估 Baseline 模式（无 Rerank）...
"%VENV_PYTHON%" -m eval.run_eval --mode baseline
echo.

echo [2/2] 评估 Rerank 模式（带 Rerank）...
"%VENV_PYTHON%" -m eval.run_eval --mode rerank
echo.

echo ========================================
echo   ✅ 评估完成！
echo   结果文件:
echo     eval\results\baseline_metrics.json
echo     eval\results\rerank_metrics.json
echo.
echo   运行对比报告: eval\run_comparison.bat
echo ========================================
pause
