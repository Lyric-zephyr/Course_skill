import argparse
import importlib.util
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser


def prepare_runtime(base, environment, local_python):
    """首次启动时在项目内补齐依赖，重启后只再检查一次。"""
    marker = "COURSE_SKILL_SETUP_ATTEMPTED"
    if os.environ.get(marker) == str(environment):
        raise RuntimeError("自动安装依赖后仍无法启动，请查看上方错误信息后重新运行 main.py。")
    print("[SYS] 首次启动，正在自动准备运行环境；完成后会打开界面，请稍候。", flush=True)
    if not local_python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, timeout=180)
    subprocess.run(
        [str(local_python), "-m", "pip", "install", "--disable-pip-version-check",
         "--retries", "2", "--timeout", "30", "-r", str(base / "requirements.txt")],
        cwd=base, check=True, timeout=900,
    )
    return subprocess.call(
        [str(local_python), "-u", str(base / "main.py"), *sys.argv[1:]],
        cwd=base, env={**os.environ, marker: str(environment)},
    )


def main():
    parser = argparse.ArgumentParser(description="Course_Skill 课程复习工作台")
    parser.add_argument("--no-browser", action="store_true", help="仅启动服务")
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    if sys.version_info < (3, 10):
        raise RuntimeError("请使用 Python 3.10 或更新版本运行 main.py。")
    # 使用项目内环境，避免从 VS Code 或系统 Python 启动时找不到依赖。
    environment = base / ".venv"
    local_python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if local_python.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        return subprocess.call([str(local_python), "-u", str(base / "main.py"), *sys.argv[1:]], cwd=base)
    if not (base / "frontend" / "dist" / "index.html").is_file():
        raise RuntimeError("缺少内置界面文件，请重新下载完整项目后运行 main.py。")
    if any(importlib.util.find_spec(name) is None for name in ("uvicorn", "fastapi", "psutil", "pymupdf", "playwright")):
        return prepare_runtime(base, environment, local_python)
    try:
        import uvicorn
        from launcher.web_api import create_app
    except ImportError:
        return prepare_runtime(base, environment, local_python)
    token = secrets.token_urlsafe(32)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(port, token)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, timeout_graceful_shutdown=5))
    url = f"http://127.0.0.1:{port}/?session={token}"
    def ready():
        while not server.should_exit:
            if server.started:
                print(f"工作台已启动：{url}\n关闭网页后任务继续运行；在此终端按 Ctrl+C 退出。", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return
            time.sleep(.1)
    threading.Thread(target=ready, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        app.state.manager.close()
        sock.close()
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[SYS] 程序已停止。", flush=True)
        sys.exit(130)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"[ERR] 无法启动界面：{error}", file=sys.stderr, flush=True)
        sys.exit(1)
