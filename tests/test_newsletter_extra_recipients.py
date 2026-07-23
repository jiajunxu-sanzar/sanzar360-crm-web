from __future__ import annotations

import pandas as pd

from config.settings import NEWSLETTER_SANZAR_CC_DEFAULT
from pages.email import (
    _dataframe_selection_state,
    build_newsletter_send_targets,
    merge_newsletter_recipient_emails,
)


def test_merge_newsletter_recipient_emails_dedupes_case_insensitive() -> None:
    merged = merge_newsletter_recipient_emails(
        table_emails=["Ana@X.com", "bea@x.com"],
        include_sanzar=True,
        sanzar_emails=("ana@x.com", "carla@sanzar-group.com"),
        extra_emails=["bea@x.com", "extra@y.com"],
    )
    norms = [e.lower() for e in merged]
    assert norms.count("ana@x.com") == 1
    assert "bea@x.com" in norms
    assert "carla@sanzar-group.com" in norms
    assert "extra@y.com" in norms


def test_merge_skips_sanzar_when_checkbox_off() -> None:
    merged = merge_newsletter_recipient_emails(
        table_emails=["a@x.com"],
        include_sanzar=False,
        sanzar_emails=NEWSLETTER_SANZAR_CC_DEFAULT,
        extra_emails=["b@y.com"],
    )
    assert [e.lower() for e in merged] == ["a@x.com", "b@y.com"]


def test_build_newsletter_send_targets_table_and_extras() -> None:
    contacts = pd.DataFrame(
        [
            {"contact_id": "c1", "nombre": "Ana", "correo": "ana@x.com", "newsletter_suscrito": "", "no_recibir_emails": ""},
            {"contact_id": "c2", "nombre": "Baja", "correo": "baja@x.com", "newsletter_suscrito": "no", "no_recibir_emails": ""},
            {"contact_id": "c3", "nombre": "OptOut", "correo": "opt@x.com", "newsletter_suscrito": "", "no_recibir_emails": "sí"},
        ]
    )
    targets, n_table, n_extra = build_newsletter_send_targets(
        contacts,
        ["c1", "c2", "c3"],
        include_sanzar=True,
        extra_emails=["extra@z.com"],
        sanzar_emails=("jiajun.xu@sanzar-group.com",),
    )
    emails = {t["correo"].lower() for t in targets}
    assert emails == {"ana@x.com", "jiajun.xu@sanzar-group.com", "extra@z.com"}
    assert n_table == 1
    assert n_extra == 2
    assert any(t["contact_id"] == "" and t["correo"].lower() == "extra@z.com" for t in targets)


def test_build_newsletter_send_targets_extras_only() -> None:
    contacts = pd.DataFrame(columns=["contact_id", "nombre", "correo", "newsletter_suscrito"])
    targets, n_table, n_extra = build_newsletter_send_targets(
        contacts,
        [],
        include_sanzar=False,
        extra_emails=["solo@extra.com"],
    )
    assert n_table == 0
    assert n_extra == 1
    assert len(targets) == 1
    assert targets[0]["correo"] == "solo@extra.com"


def test_dataframe_selection_state_for_select_all() -> None:
    assert _dataframe_selection_state([0, 1, 2]) == {
        "selection": {"rows": [0, 1, 2], "columns": []}
    }
    assert _dataframe_selection_state([]) == {"selection": {"rows": [], "columns": []}}


def test_sanzar_cc_default_includes_expected_addresses() -> None:
    assert "andrei.pop@sanzar-group.com" in NEWSLETTER_SANZAR_CC_DEFAULT
    assert "jiajun.xu@sanzar-group.com" in NEWSLETTER_SANZAR_CC_DEFAULT
    assert len(NEWSLETTER_SANZAR_CC_DEFAULT) == 9
