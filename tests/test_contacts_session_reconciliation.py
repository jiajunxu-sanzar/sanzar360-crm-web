import pandas as pd

from app.state import reconcile_selected_contact_id


def test_reconcile_selected_contact_id_keeps_existing() -> None:
    df = pd.DataFrame([{"contact_id": "C1"}, {"contact_id": "C2"}])
    assert reconcile_selected_contact_id(df, "C2") == "C2"


def test_reconcile_selected_contact_id_clears_missing() -> None:
    df = pd.DataFrame([{"contact_id": "C1"}, {"contact_id": "C2"}])
    assert reconcile_selected_contact_id(df, "C3") == ""
