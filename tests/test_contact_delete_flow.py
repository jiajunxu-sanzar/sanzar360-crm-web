from __future__ import annotations

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
    def __init__(self, sensor_rows: list[dict[str, str]] | None = None) -> None:
        self.invalidated = False
        self.sensor_rows = sensor_rows or []
        self.open_assignment_calls: list[tuple[list[str], str]] = []

    def rows_for_contact(self, kind: str, contact_id: str) -> list[dict[str, str]]:
        if kind != "sensores":
            return []
        return [row for row in self.sensor_rows if row.get("contact_id") == contact_id]

    def open_sensor_assignment_rows_for_serials(
        self,
        serials: list[str],
        *,
        exclude_contact_id: str = "",
    ) -> dict[str, dict[str, str]]:
        self.open_assignment_calls.append((serials, exclude_contact_id))
        return {}

    def invalidate_all(self) -> None:
        self.invalidated = True


class _FakeInventoryService:
    def __init__(self) -> None:
        self.reconciled: list[tuple[list[str], dict[str, dict[str, str]], str]] = []

    def reconcile_locations_for_serials(
        self,
        serials: list[str],
        open_assignments_by_serial: dict[str, dict[str, str]],
        *,
        default_location_type: str = "por_definir",
    ) -> None:
        self.reconciled.append((serials, open_assignments_by_serial, default_location_type))


def test_delete_contact_and_related_data_deletes_all_related_rows(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=True, removed_contacts=1)
    fake_hist = _FakeHistoryService()
    fake_inv = _FakeInventoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    monkeypatch.setattr("services.contact_deletion.inventory_service", lambda: fake_inv)

    delete_contact_and_related_data(sheets, "  CID-1  ")  # type: ignore[arg-type]

    called_ws = [item[0] for item in sheets.deleted_calls]
    for spec in HISTORY_SPECS.values():
        assert spec.worksheet_name in called_ws
    assert CONFIG.google_activity_log_worksheet_name in called_ws
    assert CONFIG.google_worksheet_name in called_ws
    assert fake_hist.invalidated
    assert fake_inv.reconciled == []


def test_delete_contact_and_related_data_raises_when_contact_missing(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=False, removed_contacts=0)
    fake_hist = _FakeHistoryService()
    fake_inv = _FakeInventoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    monkeypatch.setattr("services.contact_deletion.inventory_service", lambda: fake_inv)
    try:
        delete_contact_and_related_data(sheets, "CID-404")  # type: ignore[arg-type]
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "No existe el contacto" in str(exc)


def test_delete_contact_and_related_data_raises_when_main_row_not_removed(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=True, removed_contacts=0)
    fake_hist = _FakeHistoryService()
    fake_inv = _FakeInventoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    monkeypatch.setattr("services.contact_deletion.inventory_service", lambda: fake_inv)
    try:
        delete_contact_and_related_data(sheets, "CID-1")  # type: ignore[arg-type]
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "No se pudo eliminar la fila del contacto" in str(exc)


def test_delete_contact_reconciles_open_sensor_inventory(monkeypatch) -> None:
    sheets = _FakeSheetsDelete(exists=True, removed_contacts=1)
    fake_hist = _FakeHistoryService(
        [
            {
                "contact_id": "CID-1",
                "estado_cierre_sensor": "abierto",
                "sensor_serial_number": 'ug67-"6222E3615254"-SIM900,em500-"6126E51316512025"',
            },
            {
                "contact_id": "CID-1",
                "estado_cierre_sensor": "cerrado",
                "sensor_serial_number": "uc501-CLOSED-T10-SIM",
            },
        ]
    )
    fake_inv = _FakeInventoryService()
    monkeypatch.setattr("services.contact_deletion.history_service", lambda: fake_hist)
    monkeypatch.setattr("services.contact_deletion.inventory_service", lambda: fake_inv)

    delete_contact_and_related_data(sheets, "CID-1")  # type: ignore[arg-type]

    assert len(fake_inv.reconciled) == 1
    serials, assignments, default_location = fake_inv.reconciled[0]
    assert set(serials) == {"6222E3615254", "SIM900", "6126E51316512025"}
    assert assignments == {}
    assert default_location == "por_definir"
    assert fake_hist.open_assignment_calls[0][1] == "CID-1"
