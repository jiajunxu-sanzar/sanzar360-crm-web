"""Flags diarios de la ficha de contacto: visto hoy, umbrales activadas, suelo seco.

Antes vivían en ``services/clientes_board.py``, junto al tablero de la pestaña
Clientes. Esa pestaña se eliminó; los toggles siguen existiendo dentro de la
ficha de Contactos, así que los helpers de lectura/escritura viven aquí.
"""
from __future__ import annotations

from datetime import date

TIPO_RELACION_BOARD: frozenset[str] = frozenset({"Cliente", "Potencial cliente"})


def is_sheet_true(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "si", "sí"}


def sheet_bool_str(checked: bool) -> str:
    return "TRUE" if checked else "FALSE"


def parse_visto_fecha(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def is_visto_hoy(value: object, *, today: date | None = None) -> bool:
    parsed = parse_visto_fecha(value)
    if parsed is None:
        return False
    return parsed == (today or date.today())


def visto_fecha_hoy(*, today: date | None = None) -> str:
    return (today or date.today()).isoformat()


def values_for_visto_toggle(*, checked: bool, today: date | None = None) -> dict[str, str]:
    return {"visto_cliente_fecha": visto_fecha_hoy(today=today) if checked else ""}


def values_for_flag(field: str, *, checked: bool) -> dict[str, str]:
    if field not in {"umbrales_activadas", "suelo_seco"}:
        raise ValueError(f"Campo de flag no válido: {field}")
    return {field: sheet_bool_str(checked)}
