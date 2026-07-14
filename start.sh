#!/bin/bash

echo "启动法律文档智能问答系统..."

echo ""
echo "[1/2] 启动后端服务..."
uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload &
BACKEND_PID=$!

sleep 3

echo ""
echo "[2/2] 启动前端服务..."
streamlit run frontend/app.py --server.port 8501 &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "系统启动完成！"
echo "后端地址: http://localhost:8000"
echo "前端地址: http://localhost:8501"
echo "API文档: http://localhost:8000/docs"
echo "========================================"
echo ""

sleep 3
echo "正在打开浏览器..."
xdg-open http://localhost:8501 2>/dev/null || open http://localhost:8501 2>/dev/null || echo "请手动打开 http://localhost:8501"

wait $BACKEND_PID $FRONTEND_PID
