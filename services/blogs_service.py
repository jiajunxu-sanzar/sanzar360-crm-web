from __future__ import annotations

import uuid
from datetime import date

import pandas as pd

from config.settings import (
    BLOG_EVENTO_ALARMA_SIN_SEMANA,
    BLOG_TIPO_REGISTRO_BLOG,
    BLOG_TIPO_REGISTRO_EVENTO,
    BLOGS_HEADERS,
    BLOGS_WORKSHEET_NAME,
)
from services.blogs_validation import filter_blog_rows, validate_blog_values, week_bounds, week_key
from services.sheets_service import SheetsService


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def _event_notas(*, week: str, employee_id: str) -> str:
    return f"evento={BLOG_EVENTO_ALARMA_SIN_SEMANA};semana={week};employee_id={employee_id}"


class BlogsService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure(self) -> None:
        self._sheets.get_or_create_worksheet(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS))

    def blogs_df(self) -> pd.DataFrame:
        self.ensure_structure()
        return self._sheets.read_worksheet_df(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS))

    def all_rows(self) -> list[dict[str, str]]:
        df = self.blogs_df()
        if df.empty:
            return []
        return df.fillna("").astype(str).to_dict("records")

    def blog_rows(self) -> list[dict[str, str]]:
        return filter_blog_rows(self.all_rows())

    def upsert_blog(self, values: dict[str, str]) -> str:
        self.ensure_structure()
        row = {h: str(values.get(h, "") or "") for h in BLOGS_HEADERS}
        row["tipo_registro"] = BLOG_TIPO_REGISTRO_BLOG
        error = validate_blog_values(row)
        if error:
            raise ValueError(error)

        row_id = row.get("historial_blog_id", "").strip() or str(uuid.uuid4())
        row["historial_blog_id"] = row_id
        row_num = self._sheets.row_numbers_by_id(BLOGS_WORKSHEET_NAME, "historial_blog_id").get(row_id)
        if row_num is None:
            row["created_at"] = row.get("created_at") or _today()
        else:
            current_df = self.blogs_df()
            existing = current_df[current_df["historial_blog_id"].astype(str).str.strip() == row_id]
            existing_created = str(existing.iloc[0].get("created_at", "") or "").strip() if not existing.empty else ""
            row["created_at"] = row.get("created_at") or existing_created or _today()
        row["updated_at"] = _today()

        if row_num is None:
            self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        else:
            self._sheets.update_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row_num, row)
        return row_id

    def delete_blog_by_id(self, blog_id: str, df: pd.DataFrame | None = None) -> bool:
        self.ensure_structure()
        clean_id = str(blog_id or "").strip()
        if not clean_id:
            return False
        source = df if df is not None else self.blogs_df()
        if source.empty:
            return False
        ids = source.get("historial_blog_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        keep_mask = ids != clean_id
        removed = int((~keep_mask).sum())
        if removed == 0:
            return False
        kept = source[keep_mask].copy()
        self._sheets.write_worksheet_df(BLOGS_WORKSHEET_NAME, kept, list(BLOGS_HEADERS))
        return True

    def log_weekly_gap_dismiss(self, *, employee_id: str, actor_name: str, week_start: date | None = None) -> str:
        self.ensure_structure()
        ref = week_start or date.today()
        start, _ = week_bounds(ref)
        week = week_key(start)
        row_id = str(uuid.uuid4())
        today = _today()
        row = {h: "" for h in BLOGS_HEADERS}
        row.update(
            {
                "historial_blog_id": row_id,
                "tipo_registro": BLOG_TIPO_REGISTRO_EVENTO,
                "titulo": "Aviso semanal descartado",
                "fecha_publicacion_prevista": start.strftime("%d/%m/%Y"),
                "persona_publica": actor_name,
                "notas": _event_notas(week=week, employee_id=employee_id),
                "created_at": today,
                "updated_at": today,
            }
        )
        self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        return row_id
