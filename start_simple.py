#!/usr/bin/env python3
"""
Simple launcher for Legal QA System
Starts backend and frontend in separate processes
"""
import os
import sys
import time
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 60)
    print("  法律文档智能问答系统 - Legal QA System")
    print("=" * 60)
    print()
    print("请按以下步骤启动系统：")
    print()
    print("1. 打开新的终端/命令行窗口，运行后端：")
    print("   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload")
    print()
    print("2. 再打开另一个终端/命令行窗口，运行前端：")
    print("   python -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false")
    print()
    print("3. 访问系统：")
    print("   - 前端: http://localhost:8501")
    print("   - 后端 API: http://localhost:8000")
    print("   - API 文档: http://localhost:8000/docs")
    print()
    print("=" * 60)
    print()
    
    try:
        # Try to auto-launch backend first
        print("尝试自动启动后端服务...")
        os.system("start cmd /k \"cd /d " + os.path.dirname(os.path.abspath(__file__)) + " && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload\"")
        time.sleep(3)
        print("后端服务已启动！")
        print()
        print("尝试自动启动前端服务...")
        os.system("start cmd /k \"cd /d " + os.path.dirname(os.path.abspath(__file__)) + " && python -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false\"")
        print("前端服务已启动！")
        print()
        print("系统启动完成！")
        print("请查看新打开的命令行窗口。")
    except Exception as e:
        print(f"自动启动失败: {e}")
        print()
        print("请手动运行上面的命令。")

if __name__ == "__main__":
    main()
