import argparse
import importlib.util
import os
from pathlib import Path
import re
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
    if subprocess.run([str(local_python), "-m", "pip", "--version"], capture_output=True, timeout=30).returncode:
        subprocess.run([str(local_python), "-m", "ensurepip", "--upgrade"], check=True, timeout=180)
    subprocess.run(
        [str(local_python), "-m", "pip", "install", "--disable-pip-version-check",
         "--retries", "2", "--timeout", "30", "-r", str(base / "requirements.txt")],
        cwd=base, check=True, timeout=900,
    )
    return subprocess.call(
        [str(local_python), "-u", str(base / "main.py"), *sys.argv[1:]],
        cwd=base, env={**os.environ, marker: str(environment)},
    )


def check_frontend(base):
    """启动前检查首页、脚本、样式及其字体文件是否完整。"""
    dist = base / "frontend" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError("缺少内置界面文件，请重新下载完整项目后运行 main.py。")
    assets = re.findall(r'(?:src|href)=[\"\'](/assets/[^\"\']+)', index.read_text(encoding="utf-8"))
    for asset in list(assets):
        path = (dist / asset.lstrip("/")).resolve()
        if not path.is_relative_to(dist.resolve()) or not path.is_file():
            raise RuntimeError("界面资源不完整，请重新下载完整项目（包含 frontend/dist 目录）。")
        if path.suffix == ".css":
            assets.extend(re.findall(r'url\([\"\']?(/assets/[^)\"\']+)', path.read_text(encoding="utf-8")))
    if any(not (dist / asset.lstrip("/")).is_file() for asset in assets):
        raise RuntimeError("界面字体等资源缺失，请重新下载完整项目（包含 frontend/dist/assets 目录）。")


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
    check_frontend(base)
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
                    try:
                        if not webbrowser.open(url):
                            print("[TIP] 未能自动打开浏览器，请打开上方工作台地址。", flush=True)
                    except (OSError, webbrowser.Error):
                        print("[TIP] 未能自动打开浏览器，请打开上方工作台地址。", flush=True)
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
