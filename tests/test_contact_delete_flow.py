from config.settings import CONFIG
from services.contact_deletion import delete_contact_and_related_data
from services.history_service import HISTORY_SPECS


class _FakeSheetsDelete:
    def __init__(self, *, exists: bool = True, removed_contacts: int = 1) -> None:
        self.exists = exists
        self.removed_contacts = removed_contacts
        self.deleted_calls: list[tuple[str, str, str]] = []

    def contact_id_exists_on_contacts_sheet(self, contact_id: str) -> bool:
        _ = contact_id
        return self.exists

    def delete_rows_where_column_equals(self, worksheet_title: str, column_name: str, value: str) -> int:
        self.deleted_calls.append((worksheet_title, column_name, value))
        if worksheet_title == CONFIG.google_worksheet_name:
            return self.removed_contacts
        return 1


class _FakeHistoryService:
    def __init__(self) -> None:
        self.invalidated = False

    def invalidate_all(self) -> None:
        self.invalidated = True


def test_delete_contact_and_related_data_deletes_all_related_rows(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=True, removed_contacts=1)
    fake_hist = _FakeHistoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)

    delete_contact_and_related_data(sheets, "  CID-1  ")  # type: ignore[arg-type]

    called_ws = [item[0] for item in sheets.deleted_calls]
    for spec in HISTORY_SPECS.values():
        assert spec.worksheet_name in called_ws
    assert CONFIG.google_activity_log_worksheet_name in called_ws
    assert CONFIG.google_worksheet_name in called_ws
    assert fake_hist.invalidated


def test_delete_contact_and_related_data_raises_when_contact_missing(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=False, removed_contacts=0)
    fake_hist = _FakeHistoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    try:
        delete_contact_and_related_data(sheets, "CID-404")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "No existe el contacto" in str(exc)


def test_delete_contact_and_related_data_raises_when_main_row_not_removed(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=True, removed_contacts=0)
    fake_hist = _FakeHistoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    try:
        delete_contact_and_related_data(sheets, "CID-1")  # type: ignore[arg-type]
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "No se pudo eliminar la fila del contacto" in str(exc)
