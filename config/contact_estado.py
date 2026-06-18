"""Normalización y reglas del embudo comercial de contactos."""
from __future__ import annotations

import unicodedata

from config.settings import (
    CONTACT_ESTADO_LEGACY_ALIASES,
    CONTACT_ESTADO_OPCIONES,
    CONTACT_ESTADO_STAGNATION_DAYS,
    CONTACT_ESTADO_TERMINAL,
)


def _normalize_estado_key(value: str) -> str:
    text = (value or "").strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def normalize_contact_estado(value: str) -> str:
    """Map legacy / variant spellings to canonical ``CONTACT_ESTADO_OPCIONES`` labels."""
    key = _normalize_estado_key(value)
    if not key:
        return ""
    legacy = CONTACT_ESTADO_LEGACY_ALIASES.get(key)
    if legacy:
        return legacy
    for option in CONTACT_ESTADO_OPCIONES:
        if _normalize_estado_key(option) == key:
            return option
    return (value or "").strip()


def is_terminal_contact_estado(value: str) -> bool:
    return normalize_contact_estado(value) in CONTACT_ESTADO_TERMINAL


def is_contact_perdido(value: str) -> bool:
    return normalize_contact_estado(value) == "Perdido"


def stagnation_threshold_days(estado: str) -> int | None:
    normalized = normalize_contact_estado(estado)
    if not normalized or is_terminal_contact_estado(normalized):
        return None
    return CONTACT_ESTADO_STAGNATION_DAYS.get(normalized)
