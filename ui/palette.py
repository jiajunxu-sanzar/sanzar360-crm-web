from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualStatusStyle:
    bg: str
    border: str
    fg: str

    def css(self) -> str:
        return f"background:{self.bg};border:1px solid {self.border};color:{self.fg};"


# ── Minimal cohesive chip palette (muted surfaces + readable text) ─────────
STATUS_NEUTRAL = VisualStatusStyle("#fafafa", "#e5e5e5", "#404040")
STATUS_INFO = VisualStatusStyle("#f0f9ff", "#bae6fd", "#0369a1")
STATUS_SUCCESS = VisualStatusStyle("#f0fdf4", "#bbf7d0", "#15803d")
STATUS_WARNING = VisualStatusStyle("#fffbeb", "#fde68a", "#b45309")
STATUS_DANGER = VisualStatusStyle("#fef2f2", "#fecaca", "#b91c1c")
STATUS_PURPLE = VisualStatusStyle("#faf5ff", "#e9d5ff", "#6d28d9")

# Accents for “next action” filter buttons (thin left stripe when selected)
ACCENT_BUCKET_PAST = "#e11d48"
ACCENT_BUCKET_TODAY = "#ca8a04"
ACCENT_BUCKET_TOMORROW = "#16a34a"

# Idle state (all buckets)
_BTN_IDLE_BG = "#ffffff"
_BTN_IDLE_BORDER = "#e5e5e5"
_BTN_IDLE_FG = "#525252"
# Selected: shared neutral lift + coloured left accent in contacts markup
_BTN_ON_BG = "#f4f4f5"
_BTN_ON_BORDER = "#d4d4d8"
_BTN_ON_FG = "#18181b"


def dash_bucket_button_style(active_bucket: str, kind: str) -> tuple[str, str, str, str]:
    """Return (background, border, color, border_left) for próximas acciones buttons."""
    is_on = active_bucket == kind
    accent = {
        "past": ACCENT_BUCKET_PAST,
        "today": ACCENT_BUCKET_TODAY,
        "tomorrow": ACCENT_BUCKET_TOMORROW,
    }[kind]
    if is_on:
        return _BTN_ON_BG, _BTN_ON_BORDER, _BTN_ON_FG, f"3px solid {accent}"
    return _BTN_IDLE_BG, _BTN_IDLE_BORDER, _BTN_IDLE_FG, "3px solid transparent"


def _normalize_visual_text(value: object) -> str:
    if isinstance(value, bool):
        return "abierta" if value else "cerrada"
    value = ("" if value is None else str(value)).strip().lower()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )
    return value


def contact_status_style(value: str) -> VisualStatusStyle:
    text = _normalize_visual_text(value)
    if text == "cliente":
        return STATUS_SUCCESS
    if text in {"en negociacion", "en contacto"}:
        return STATUS_INFO
    if text == "perdido":
        return STATUS_DANGER
    if text == "nuevo contacto":
        return STATUS_WARNING
    return STATUS_NEUTRAL


def next_action_style(value: str) -> VisualStatusStyle:
    return STATUS_WARNING if (value or "").strip() else STATUS_NEUTRAL


def commercial_result_style(resultado: str) -> VisualStatusStyle:
    text = _normalize_visual_text(resultado)
    if text == "exitoso":
        return STATUS_SUCCESS
    if text == "fallido":
        return STATUS_DANGER
    return STATUS_NEUTRAL


def commercial_seg_card_modifier(resultado: str) -> str:
    """CSS modifier suffix for seguimiento cards: exitoso | fallido | neutral."""
    text = _normalize_visual_text(resultado)
    if text == "exitoso":
        return "exitoso"
    if text == "fallido":
        return "fallido"
    return "neutral"


def history_open_closed_modifier(field: str, value: str) -> str:
    """CSS modifier for abierto/cerrado history fields: exitoso | fallido | neutral."""
    del field  # reserved for field-specific rules later
    text = _normalize_visual_text(value)
    if text == "abierto":
        return "exitoso"
    if text == "cerrado":
        return "fallido"
    return "neutral"


def history_open_closed_style(value: str) -> VisualStatusStyle:
    modifier = history_open_closed_modifier("", value)
    if modifier == "exitoso":
        return STATUS_SUCCESS
    if modifier == "fallido":
        return STATUS_DANGER
    return STATUS_NEUTRAL


def history_subscription_modifier(estado_suscripcion: str) -> str:
    """CSS modifier for subscription cards: exitoso | warning | fallido | neutral."""
    text = _normalize_visual_text(estado_suscripcion)
    if "caduca" in text or "pronto" in text:
        return "warning"
    if "activa" in text and "inactiva" not in text:
        return "exitoso"
    if "inactiva" in text:
        return "fallido"
    return "neutral"


def history_subscription_style(value: str) -> VisualStatusStyle:
    modifier = history_subscription_modifier(value)
    if modifier == "warning":
        return STATUS_WARNING
    if modifier == "exitoso":
        return STATUS_SUCCESS
    if modifier == "fallido":
        return STATUS_DANGER
    return STATUS_NEUTRAL


def history_incident_modifier(estado: str) -> str:
    """CSS modifier for incident history cards (open=green, closed=red)."""
    text = _normalize_visual_text(estado)
    if text in {"cerrada", "cerrado", "resuelta", "resuelto"}:
        return "fallido"
    if text in {"abierta", "en curso", "bloqueada"}:
        return "exitoso"
    return "neutral"


def history_incident_style(value: str) -> VisualStatusStyle:
    modifier = history_incident_modifier(value)
    if modifier == "exitoso":
        return STATUS_SUCCESS
    if modifier == "fallido":
        return STATUS_DANGER
    return STATUS_NEUTRAL


def subscription_status_style(value: str) -> VisualStatusStyle:
    text = _normalize_visual_text(value)
    if "caduca" in text or "pronto" in text:
        return STATUS_WARNING
    if "activa" in text and "inactiva" not in text:
        return STATUS_SUCCESS
    if "no" == text or "inactiva" in text:
        return STATUS_DANGER
    return STATUS_NEUTRAL


def incident_status_style(value: object) -> VisualStatusStyle:
    text = _normalize_visual_text(value)
    if text in {"cerrada", "cerrado", "resuelta", "resuelto"}:
        return STATUS_SUCCESS
    if text:
        return STATUS_DANGER
    return STATUS_NEUTRAL


def sensor_status_style(value: str) -> VisualStatusStyle:
    text = _normalize_visual_text(value)
    if text in {"activo", "en uso", "instalado"}:
        return STATUS_SUCCESS
    if text in {"revision", "en revision", "mantenimiento"}:
        return STATUS_WARNING
    if text in {"devuelto", "baja", "perdido", "roto"}:
        return STATUS_DANGER
    return STATUS_NEUTRAL


def alarm_category_style(has_alarm: bool, active: bool) -> tuple[VisualStatusStyle, int]:
    return (STATUS_DANGER if has_alarm else STATUS_NEUTRAL, 3 if active else 1)


def valor_oportunidad_style(value: str) -> VisualStatusStyle:
    """Pipeline value (Bajo / Medio / Alto) — quick visual cue in detail header."""
    t = _normalize_visual_text(value)
    if not t:
        return STATUS_NEUTRAL
    if "alto" in t:
        return STATUS_WARNING
    if "bajo" in t:
        return STATUS_SUCCESS
    return STATUS_INFO


def priority_style(priority: str) -> VisualStatusStyle:
    """Alarm / work-inbox stripe + chip mapping from textual priority."""
    t = _normalize_visual_text(str(priority))
    if not t:
        return STATUS_NEUTRAL
    if t in {"urgente", "critico", "critica"}:
        return STATUS_DANGER
    if t in {"alta", "alto"}:
        return STATUS_WARNING
    if t in {"media", "medio"}:
        return STATUS_INFO
    if t in {"baja", "bajo"}:
        return STATUS_NEUTRAL
    return STATUS_NEUTRAL
