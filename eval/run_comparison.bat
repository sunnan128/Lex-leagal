@echo off
chcp 65001 >nul
title LexAI 对比报告

echo ========================================
echo   LexAI 优化前后 A/B 对比报告
echo ========================================
echo.

set VENV_PYTHON=%~dp0..\.venv\Scripts\python.exe
if not exist "%VENV_PYTHON%" (
    echo ❌ 未找到虚拟环境 Python: %VENV_PYTHON%
    pause
    exit /b 1
)

if not exist "%~dp0results\baseline_metrics.json" (
    echo ⚠️  未找到 baseline 评估结果
    echo    请先运行 eval\run_all_eval.bat
    pause
    exit /b 1
)
if not exist "%~dp0results\rerank_metrics.json" (
    echo ⚠️  未找到 rerank 评估结果
    echo    请先运行 eval\run_all_eval.bat
    pause
    exit /b 1
)

"%VENV_PYTHON%" -m eval.comparison
echo.
echo 报告已保存: eval\results\comparison_report.json
pause
