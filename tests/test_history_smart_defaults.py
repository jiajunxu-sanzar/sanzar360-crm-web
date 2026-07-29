"""Tests de los valores por defecto inteligentes en históricos (Fase 3)."""

from __future__ import annotations

import pages.contacts_common as contacts
from services.madrid_time import madrid_dd_mm_yyyy, madrid_hh_mm


def _today() -> str:
    return madrid_dd_mm_yyyy()


def test_new_sensor_history_defaults_fecha_inicio_to_today() -> None:
    initial = {"fecha_inicio": "", "fecha_fin": ""}
    out = contacts._apply_smart_defaults("sensores", dict(initial), is_new=True)
    assert out["fecha_inicio"] == _today()
    assert out["fecha_fin"] == ""


def test_existing_rows_are_never_touched() -> None:
    initial = {"fecha_inicio": "", "fecha_fin": ""}
    out = contacts._apply_smart_defaults("sensores", dict(initial), is_new=False)
    assert out["fecha_inicio"] == ""


def test_defaults_do_not_overwrite_user_values() -> None:
    initial = {"fecha_inicio": "01/01/2024"}
    out = contacts._apply_smart_defaults("sensores", dict(initial), is_new=True)
    assert out["fecha_inicio"] == "01/01/2024"


def test_incidencia_and_suscripcion_and_campana_defaults() -> None:
    assert contacts._history_smart_defaults("incidencias")["fecha_apertura"] == _today()
    assert contacts._history_smart_defaults("suscripciones")["fecha_pago"] == _today()
    assert contacts._history_smart_defaults("campanas") == {}


def test_seguimiento_defaults_use_logged_user_when_valid(monkeypatch) -> None:
    persona_valida = "David Ortiz"
    monkeypatch.setattr(contacts, "_actor_name", lambda: persona_valida)
    monkeypatch.setattr(contacts, "commercial_user_names", lambda users: [persona_valida, "Marco Ruano"])
    monkeypatch.setattr(contacts, "load_users_cached", lambda version=0: [])
    defaults = contacts._history_smart_defaults("seguimiento_comercial")
    assert defaults["fecha_contacto"] == _today()
    assert defaults["hora_contacto"] == madrid_hh_mm()
    assert defaults["persona_contacto"] == persona_valida
    assert defaults["proxima_accion_persona"] == persona_valida


def test_seguimiento_defaults_blank_persona_when_unknown_user(monkeypatch) -> None:
    monkeypatch.setattr(contacts, "_actor_name", lambda: "No Existe")
    monkeypatch.setattr(contacts, "commercial_user_names", lambda users: ["David Ortiz"])
    monkeypatch.setattr(contacts, "load_users_cached", lambda version=0: [])
    defaults = contacts._history_smart_defaults("seguimiento_comercial")
    assert defaults["persona_contacto"] == ""
    assert defaults["proxima_accion_persona"] == ""
