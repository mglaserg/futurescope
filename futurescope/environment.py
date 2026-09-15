from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


@dataclass(frozen=True)
class EnvironmentStatus:
    env_file_exists: bool
    databento_configured: bool
    goldprice_configured: bool


def load_futurescope_env(repo_root: str | Path | None = None) -> EnvironmentStatus:
    """Load Futurescope's repo-root .env file deterministically.

    ``python-dotenv``'s bare ``load_dotenv()`` searches relative to the calling
    context. That happened to work for Streamlit pages but was unreliable once
    Uvicorn was launched as a separate process. Always resolving from the repo
    root keeps Streamlit, FastAPI, tests, and Windows launchers consistent.
    """
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path, override=False)

    return EnvironmentStatus(
        env_file_exists=env_path.is_file(),
        databento_configured=bool(os.getenv("DATABENTO_API_KEY")),
        goldprice_configured=bool(os.getenv("GOLDPRICE_API_KEY")),
    )
