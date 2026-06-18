from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.estado_stagnation_alarms import stagnation_alarms


def _contact_row(estado: str, fecha_estado: str, *, contact_id: str = "c1") -> dict[str, str]:
    return {
        "contact_id": contact_id,
        "nombre": "Demo",
        "estado": estado,
        "fecha_estado": fecha_estado,
    }


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).strftime("%d/%m/%Y")


def test_stagnation_triggers_at_state_threshold() -> None:
    df = pd.DataFrame([_contact_row("Contacto inicial", _days_ago(22))])
    alarms = stagnation_alarms(df)
    assert len(alarms) == 1
    assert alarms[0]["umbral_estado"] == "21"
    assert alarms[0]["estado_normalizado"] == "Contacto inicial"


def test_stagnation_below_threshold_is_empty() -> None:
    df = pd.DataFrame([_contact_row("Contacto inicial", _days_ago(20))])
    assert stagnation_alarms(df) == []


def test_terminal_states_are_excluded() -> None:
    df = pd.DataFrame(
        [
            _contact_row("Cliente", _days_ago(100), contact_id="c-cliente"),
            _contact_row("Perdido", _days_ago(100), contact_id="c-perdido"),
        ]
    )
    assert stagnation_alarms(df) == []


def test_legacy_en_contacto_uses_contacto_inicial_threshold() -> None:
    df = pd.DataFrame([_contact_row("En Contacto", _days_ago(22))])
    alarms = stagnation_alarms(df)
    assert len(alarms) == 1
    assert alarms[0]["estado_normalizado"] == "Contacto inicial"
    assert alarms[0]["umbral_estado"] == "21"


def test_piloto_activo_threshold_is_sixty_days() -> None:
    below = pd.DataFrame([_contact_row("Piloto activo", _days_ago(59))])
    assert stagnation_alarms(below) == []
    at_threshold = pd.DataFrame([_contact_row("Piloto activo", _days_ago(60))])
    alarms = stagnation_alarms(at_threshold)
    assert len(alarms) == 1
    assert alarms[0]["umbral_estado"] == "60"
