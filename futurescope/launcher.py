from __future__ import annotations

import sys
from pathlib import Path


def build_streamlit_command(
    repo_root: str | Path,
    port: int | None = None,
    address: str | None = None,
) -> list[str]:
    root = Path(repo_root).resolve()
    command = [sys.executable, "-m", "streamlit", "run", str(root / "app.py")]
    if port is not None:
        command.extend(["--server.port", str(int(port))])
    if address:
        command.extend(["--server.address", str(address)])
    return command
