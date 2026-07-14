#!/usr/bin/env python3
"""
Simple launcher for Legal QA System
"""
import os
import sys
import time
import webbrowser

def main():
    print("=" * 60)
    print("  法律文档智能问答系统 - Legal QA System")
    print("=" * 60)
    print()
    print("推荐启动方式：")
    print()
    print("步骤 1 - 启动后端（在新的终端窗口中运行）：")
    print("-" * 60)
    print("  cd /d", os.path.dirname(os.path.abspath(__file__)))
    print("  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload")
    print()
    print("步骤 2 - 启动前端（在另一个新的终端窗口中运行）：")
    print("-" * 60)
    print("  cd /d", os.path.dirname(os.path.abspath(__file__)))
    print("  python -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false")
    print()
    print("访问系统：")
    print("-" * 60)
    print("  前端界面: http://localhost:8501")
    print("  后端 API: http://localhost:8002")
    print("  API 文档: http://localhost:8002/docs")
    print()
    print("=" * 60)
    print()
    
    input("按回车键尝试自动启动...")
    
    # Try auto-launch
    try:
        print("\n正在启动后端服务...")
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        os.system("start cmd /k python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload")
        
        print("\n等待后端启动...")
        time.sleep(5)
        
        print("\n正在启动前端服务...")
        os.system("start cmd /k python -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false")
        
        print("\n" + "=" * 60)
        print("服务已在新窗口中启动！")
        print("正在打开浏览器...")
        print("=" * 60)
        
        # 等待服务就绪后自动打开浏览器
        time.sleep(3)
        webbrowser.open('http://localhost:8501')
        
    except Exception as e:
        print(f"\n启动失败: {e}")
        print("\n请按照上面的步骤手动启动服务。")

if __name__ == "__main__":
    main()
