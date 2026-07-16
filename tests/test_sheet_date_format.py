from services.sheet_date_format import (
    contact_soft_warnings,
    is_valid_dd_mm_yyyy,
    is_valid_sensor_serial_number,
    normalize_dd_mm_yyyy,
    normalize_sensor_serial_number,
    parse_sheet_date,
)


def test_contact_soft_warnings_flags_bad_email_and_phone() -> None:
    warnings = contact_soft_warnings({"correo": "d", "telefono": "abc123"})
    assert any("Correo" in w for w in warnings)
    assert any("Teléfono" in w for w in warnings)


def test_contact_soft_warnings_accepts_valid_and_multivalue() -> None:
    assert contact_soft_warnings({"correo": "a@b.com", "telefono": "+34 626 784 074"}) == []
    assert contact_soft_warnings({}) == []
    # Un valor válido y otro inválido en el mismo campo: solo avisa del malo.
    warnings = contact_soft_warnings({"correo": "a@b.com, mal"})
    assert warnings == ["Correo con formato dudoso: mal"]


def test_validates_dd_mm_yyyy_dates() -> None:
    assert is_valid_dd_mm_yyyy("")
    assert is_valid_dd_mm_yyyy("05/04/2026")
    assert not is_valid_dd_mm_yyyy("2026-04-05")
    assert not is_valid_dd_mm_yyyy("31/02/2026")


def test_parse_sheet_date_accepts_iso_and_normalizes() -> None:
    assert parse_sheet_date("2026-06-02") == parse_sheet_date("02/06/2026")
    assert normalize_dd_mm_yyyy("2026-06-02") == "02/06/2026"
    assert normalize_dd_mm_yyyy("") == ""
    assert parse_sheet_date("invalid") is None


def test_sensor_serial_allows_uc501_ug67_and_standalone_node() -> None:
    assert is_valid_sensor_serial_number("uc501-UC001-TE001-SIM001")
    assert is_valid_sensor_serial_number("uc501-6772F19007800001")
    assert is_valid_sensor_serial_number("ug67-UG001-SIM900, em500-EM50001, uc512-UC51201")
    assert is_valid_sensor_serial_number("uc512-UCDEM00341")
    assert is_valid_sensor_serial_number("sim-SIM001")
    assert is_valid_sensor_serial_number("ug67-UG001-SIM900")


def test_sensor_serial_ug67_with_sim_without_child_nodes() -> None:
    assert is_valid_sensor_serial_number("ug67-6222E3615254-SIM900")


def test_sensor_serial_ug67_serial_with_or_without_quotes() -> None:
    assert is_valid_sensor_serial_number('ug67-"6222E3615254"-SIM900')
    assert is_valid_sensor_serial_number("ug67-6222E3615254-SIM900")
    assert normalize_sensor_serial_number('ug67-"6222E3615254"-SIM900') == "ug67-6222E3615254-SIM900"
