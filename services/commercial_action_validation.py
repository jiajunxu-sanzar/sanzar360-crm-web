"""Validation for commercial follow-up rows (hoja Acciones)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from config.settings import CANAL_CONTACTO_OPCIONES, EMAIL_CLASIFICACION_OPCIONES, RESULTADO_CONTACTO_OPCIONES
from services.sheet_date_format import is_valid_dd_mm_yyyy

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def is_valid_hora_contacto(value: str) -> bool:
    return bool(_TIME_RE.match((value or "").strip()))


def is_valid_email_url(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_commercial_action_values(values: dict[str, str]) -> str | None:
    resultado = (values.get("resultado_contacto", "") or "").strip().lower()
    if resultado and resultado not in RESULTADO_CONTACTO_OPCIONES:
        return "Resultado de contacto no válido."

    fecha = (values.get("fecha_contacto", "") or "").strip()
    hora = (values.get("hora_contacto", "") or "").strip()
    if not fecha:
        return "La fecha de contacto es obligatoria."
    if not is_valid_dd_mm_yyyy(fecha):
        return "Fecha de contacto no válida (usa dd/mm/aaaa)."
    if hora and not is_valid_hora_contacto(hora):
        return "Hora de contacto no válida (usa HH:MM en 24h)."

    canal = (values.get("canal_contacto", "") or "").strip().lower()
    if not canal:
        return "El canal de contacto es obligatorio."
    if canal not in CANAL_CONTACTO_OPCIONES:
        return "Canal de contacto no válido."

    email_url = (values.get("email_url", "") or "").strip()
    email_clas = (values.get("email_clasificacion", "") or "").strip().lower()
    if canal != "email":
        if email_url or email_clas:
            return "URL y clasificación de email solo aplican cuando el canal es email."
    else:
        if not email_clas:
            return "Indica la clasificación del email (primer email, seguimiento o contestación)."
        if email_clas not in EMAIL_CLASIFICACION_OPCIONES:
            return "Clasificación de email no válida."
        if email_url and not is_valid_email_url(email_url):
            return "La URL del email no es válida (usa http:// o https://)."

    prox_fecha = (values.get("proxima_accion_fecha", "") or "").strip()
    prox_persona = (values.get("proxima_accion_persona", "") or "").strip()
    prox_canal = (values.get("proxima_accion_canal", "") or "").strip().lower()
    prox_detalle = (values.get("proxima_accion_detalle", "") or "").strip()
    prox_any = any([prox_fecha, prox_persona, prox_canal, prox_detalle])
    if prox_any:
        if not prox_fecha or not is_valid_dd_mm_yyyy(prox_fecha):
            return "Si defines próxima acción, la fecha debe ser válida (dd/mm/aaaa)."
        if not prox_persona:
            return "Si defines próxima acción, indica la persona responsable."
        if not prox_canal or prox_canal not in CANAL_CONTACTO_OPCIONES:
            return "Si defines próxima acción, indica el canal (email, llamada o en persona)."

    return None
