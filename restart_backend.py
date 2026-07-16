#!/usr/bin/env python3
"""
后端自恢复脚本
功能：检测端口占用 → 清理残留进程 → 重启后端服务
被前端重试按钮调用，也可独立运行。

用法：python restart_backend.py
"""
import os
import sys
import time
import subprocess

PORT = 8002
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_process_on_port(port: int) -> list:
    """查找占用指定端口的进程 PID 列表"""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        pids = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.append(int(pid))
        return pids
    except Exception:
        return []


def kill_processes(pids: list):
    """强制终止进程列表（Windows 用 taskkill /F，避免 os.kill 不兼容）"""
    for pid in pids:
        try:
            result = subprocess.run(
                f'taskkill /F /PID {pid}',
                shell=True, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print(f"  已终止 PID {pid}")
        except Exception as e:
            print(f"  无法终止 PID {pid}: {e}")


def restart_backend() -> bool:
    """
    重启后端服务
    返回 True 表示启动成功，False 表示失败
    """
    print(f"[1/3] 检查端口 {PORT} 占用情况...")
    pids = find_process_on_port(PORT)
    if pids:
        print(f"  发现 {len(pids)} 个进程占用端口 {PORT}: {pids}")
        kill_processes(pids)
        time.sleep(1)
    else:
        print("  端口未被占用")

    print(f"\n[2/3] 启动后端服务 (端口 {PORT})...")
    backend_dir = os.path.join(PROJECT_DIR, "backend")
    if not os.path.exists(backend_dir):
        print(f"  ❌ 后端目录不存在: {backend_dir}")
        return False

    try:
        subprocess.Popen(
            [
                sys.executable, '-m', 'uvicorn', 'backend.main:app',
                '--host', '0.0.0.0', '--port', str(PORT), '--reload'
            ],
            cwd=PROJECT_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print(f"  后端启动命令已发送 (PID 将显示在新窗口中)")
    except Exception as e:
        print(f"  ❌ 启动失败: {e}")
        return False

    print(f"\n[3/3] 等待服务就绪...")
    import urllib.request
    for i in range(30):  # 最多等待 30 秒
        try:
            resp = urllib.request.urlopen(f'http://localhost:{PORT}/health', timeout=2)
            if resp.status == 200:
                print(f"  ✅ 后端服务已就绪 (耗时 {i+1} 秒)")
                return True
        except Exception:
            pass
        time.sleep(1)

    print(f"  ⚠ 后端服务启动超时，请检查新窗口中是否有报错")
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("    LexAI 后端自恢复脚本")
    print("=" * 50)
    success = restart_backend()
    print("\n" + "=" * 50)
    if success:
        print("  结果: ✅ 服务已恢复")
    else:
        print("  结果: ❌ 启动失败，请手动检查")
    print("=" * 50)
    sys.exit(0 if success else 1)
