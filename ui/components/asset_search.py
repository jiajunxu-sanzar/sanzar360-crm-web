from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from services.history_service import SensorAssetOccurrence


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def asset_occurrences_df(occurrences: list[SensorAssetOccurrence]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    today = date.today()
    for occurrence in occurrences:
        end = _parse_date(occurrence.fecha_fin)
        active = end is None or end >= today
        rows.append(
            {
                "tipo": occurrence.asset.asset_type,
                "serial": occurrence.asset.serial,
                "disponibilidad": "En uso" if active else "Disponible",
                "cliente": occurrence.nombre_cliente,
                "contact_id": occurrence.contact_id,
                "asociado_con": occurrence.associated_with,
                "fecha_inicio": occurrence.fecha_inicio,
                "fecha_fin": occurrence.fecha_fin,
                "red": occurrence.red,
                "aws_user_id": occurrence.aws_user_id,
                "historial_sensor_id": occurrence.historial_sensor_id,
            }
        )
    return pd.DataFrame(rows)
