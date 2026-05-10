from __future__ import annotations

import random
import time
from dataclasses import dataclass

from app.telemetry import track_event
from services.sheets_service import SheetsService

_RETRY_DELAYS_MS = (150, 350, 800)


@dataclass(frozen=True)
class WriteVerificationResult:
    status: str  # confirmed | ambiguous | failed
    attempts: int
    message: str = ""


def _safe_track(name: str, success: bool, **metadata: object) -> None:
    try:
        track_event(name, 0, success, **metadata)
    except Exception:
        # Tests executed outside `streamlit run` may not have usable session_state.
        pass


def verify_contact_write_with_retry(
    *,
    sheets: SheetsService,
    contact_id: str,
    expected_subset: dict[str, str],
    operation: str,
) -> WriteVerificationResult:
    target = str(contact_id or "").strip()
    if not target:
        return WriteVerificationResult(status="failed", attempts=0, message="contact_id vacío")
    attempts = 0
    for delay_ms in (0, *_RETRY_DELAYS_MS):
        attempts += 1
        if delay_ms:
            jitter = int(delay_ms * 0.2)
            time.sleep(max(0.0, (delay_ms + random.randint(-jitter, jitter)) / 1000.0))
        try:
            ok = sheets.verify_contact_subset(target, expected_subset)
        except Exception as exc:
            _safe_track(
                "contacts.write.verify.error",
                False,
                operation=operation,
                contact_id=target,
                attempt=attempts,
                error=exc.__class__.__name__,
            )
            if attempts >= len(_RETRY_DELAYS_MS) + 1:
                return WriteVerificationResult(status="ambiguous", attempts=attempts, message=str(exc))
            continue
        _safe_track(
            "contacts.write.verify.attempt",
            ok,
            operation=operation,
            contact_id=target,
            attempt=attempts,
            backoff_ms=delay_ms,
        )
        if ok:
            return WriteVerificationResult(status="confirmed", attempts=attempts)
    return WriteVerificationResult(
        status="ambiguous",
        attempts=attempts,
        message="No se pudo confirmar lectura consistente tras guardar.",
    )
