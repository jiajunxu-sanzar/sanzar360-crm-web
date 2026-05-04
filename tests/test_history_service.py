from services.history_service import count_sensor_assets, parse_sensor_asset_occurrences, parse_sensor_assets


def test_parse_sensor_assets_extracts_physical_assets() -> None:
    assets = parse_sensor_assets("uc501-UC001-TE001-SIM001")
    keys = {asset.key for asset, _ in assets}
    assert ("uc501", "uc001") in keys
    assert ("teros10", "te001") in keys
    assert ("sim", "sim001") in keys
    assert count_sensor_assets("uc501-UC001-TE001-SIM001") == 3


def test_parse_sensor_asset_occurrences_includes_context() -> None:
    rows = [
        {
            "contact_id": "c1",
            "nombre_cliente": "Demo",
            "fecha_inicio": "01/01/2026",
            "sensor_serial_number": "uc512-UCDEM00341",
            "aws_user_id": "aws-demo",
        }
    ]
    occurrences = parse_sensor_asset_occurrences(rows)
    assert len(occurrences) == 1
    assert occurrences[0].asset.asset_type == "uc512"
    assert occurrences[0].aws_user_id == "aws-demo"
