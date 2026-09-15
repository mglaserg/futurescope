from __future__ import annotations

import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def _command(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SystemExit(f"{name} was not found on PATH.")
    return value


def main() -> int:
    npm = _command("npm")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("Installing Futurescope web API dependencies (first run only)…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-web.txt")], cwd=ROOT, check=True)
    if not (FRONTEND / "node_modules").exists():
        print("Installing Futurescope React dependencies (first run only)…")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)

    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "futurescope.api:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
    )
    web = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=FRONTEND,
    )
    try:
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5173")
        print("Futurescope React: http://127.0.0.1:5173")
        print("Futurescope API docs: http://127.0.0.1:8000/docs")
        while api.poll() is None and web.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in (web, api):
            if process.poll() is None:
                process.terminate()
        for process in (web, api):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
