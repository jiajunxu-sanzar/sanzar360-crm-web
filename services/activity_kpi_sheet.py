from __future__ import annotations

import pandas as pd

from services.sheets_service import SheetsService

KPI_HEADERS = ("metric", "value")


def save_kpi_summary(sheets_service: SheetsService, metrics: dict[str, int | float | str]) -> None:
    df = pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()])
    sheets_service.write_worksheet_df("ResumenSemanal", df, list(KPI_HEADERS))
