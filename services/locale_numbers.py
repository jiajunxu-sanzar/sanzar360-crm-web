"""Parseo de números con coma o punto (Sheets / locale es_ES)."""
from __future__ import annotations


def parse_locale_float(raw: object) -> float | None:
    """Convierte str/número a float aceptando ``0,45`` y ``0.45``.

    Si hay ambos separadores, el último actúa como decimal
    (``1.234,56`` → 1234.56; ``1,234.56`` → 1234.56).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value != value:  # NaN
            return None
        return value
    text = str(raw).strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_p_tabla(raw: object) -> float | None:
    """p FAO-56 en [0, 1]; corrige mangling típico de Sheets es_ES (``0.3``→``3``)."""
    value = parse_locale_float(raw)
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return value
    # USER_ENTERED + locale ES: "0.3" → 3, "0.45" → 45
    if abs(value - round(value)) < 1e-9:
        as_int = int(round(value))
        if 1 <= as_int <= 9:
            return as_int / 10.0
        if 10 <= as_int <= 99:
            healed = as_int / 100.0
            if 0.0 <= healed <= 1.0:
                return healed
    return None
