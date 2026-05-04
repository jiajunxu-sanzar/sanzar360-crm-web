from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Any, Iterator

import streamlit as st

logger = logging.getLogger("sanzar.crm.web")


@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    duration_ms: int
    success: bool
    metadata: dict[str, Any]


def _events_buffer() -> list[dict[str, Any]]:
    if "telemetry_events" not in st.session_state:
        st.session_state["telemetry_events"] = []
    return st.session_state["telemetry_events"]


def track_event(name: str, duration_ms: int, success: bool, **metadata: Any) -> None:
    event = TelemetryEvent(
        name=name,
        duration_ms=max(0, int(duration_ms)),
        success=bool(success),
        metadata=metadata,
    )
    _events_buffer().append(asdict(event))
    logger.info("telemetry_event=%s", asdict(event))


@contextmanager
def timed(name: str, **metadata: Any) -> Iterator[None]:
    started_at = time.perf_counter()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        track_event(name, elapsed_ms, success, **metadata)
