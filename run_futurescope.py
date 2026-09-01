from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from futurescope.launcher import build_streamlit_command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Futurescope Streamlit dashboard.")
    parser.add_argument("--port", type=int, default=None, help="Optional Streamlit server port.")
    parser.add_argument("--address", default=None, help="Optional Streamlit bind address, e.g. 127.0.0.1.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    command = build_streamlit_command(root, port=args.port, address=args.address)
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
