from services.sheet_date_format import (
    is_valid_dd_mm_yyyy,
    is_valid_sensor_serial_number,
    normalize_sensor_serial_number,
)


def test_validates_dd_mm_yyyy_dates() -> None:
    assert is_valid_dd_mm_yyyy("")
    assert is_valid_dd_mm_yyyy("05/04/2026")
    assert not is_valid_dd_mm_yyyy("2026-04-05")
    assert not is_valid_dd_mm_yyyy("31/02/2026")


def test_sensor_serial_allows_uc501_ug67_and_standalone_node() -> None:
    assert is_valid_sensor_serial_number("uc501-UC001-TE001-SIM001")
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
