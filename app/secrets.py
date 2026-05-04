from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _streamlit_secrets() -> Any | None:
    try:
        import streamlit as st

        return st.secrets
    except Exception:
        return None


def get_secret(name: str, default: str = "") -> str:
    secrets = _streamlit_secrets()
    if secrets is not None:
        try:
            value = secrets.get(name)
            if value is not None:
                return str(value)
        except Exception:
            pass
    return os.getenv(name, default)


def get_bool_secret(name: str, default: bool = False) -> bool:
    raw = get_secret(name, str(default).lower()).strip().lower()
    return raw in {"1", "true", "yes", "y", "si", "sí"}


def get_int_secret(name: str, default: int) -> int:
    try:
        return int(get_secret(name, str(default)))
    except ValueError:
        return default


def service_account_info() -> dict[str, Any] | None:
    secrets = _streamlit_secrets()
    if secrets is None:
        return None
    try:
        info = secrets.get("gcp_service_account")
    except Exception:
        return None
    if not info:
        return None
    return dict(info)
