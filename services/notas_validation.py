"""Validación de filas del histórico de notas."""
from __future__ import annotations

from config.settings import ESTADO_NOTA_OPCIONES


def validate_nota_history_values(values: dict[str, str]) -> str | None:
    if not str(values.get("titulo", "") or "").strip():
        return "El título de la nota es obligatorio."
    if not str(values.get("notas", "") or "").strip():
        return "El texto de la nota es obligatorio."
    if not str(values.get("tipo_nota", "") or "").strip():
        return "El tipo de nota es obligatorio."
    estado = str(values.get("estado_nota", "") or "").strip()
    if estado not in ESTADO_NOTA_OPCIONES:
        return "El estado de la nota debe ser Útil u Obsoleta."
    return None
