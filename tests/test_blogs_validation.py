from __future__ import annotations

from datetime import date

import pandas as pd

from config.settings import BLOGS_HEADERS, BLOGS_WORKSHEET_NAME
from services.blogs_service import BlogsService
from services.blogs_validation import (
    build_blog_due_alarm_rows,
    build_weekly_gap_alarm_row,
    filter_blog_rows,
    should_show_weekly_gap_alarm,
    weekly_blog_count,
)


class FakeSheets:
    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            BLOGS_WORKSHEET_NAME: pd.DataFrame(columns=list(BLOGS_HEADERS)),
        }

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        if name not in self.frames:
            self.frames[name] = pd.DataFrame(columns=headers)

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str)

    def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
        df = self.frames[name].fillna("").astype(str)
        out: dict[str, int] = {}
        for i, row in df.iterrows():
            value = str(row.get(id_header, "")).strip()
            if value:
                out[value] = i + 2
        return out

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, str]) -> None:
        self.frames[name] = pd.concat(
            [self.frames[name], pd.DataFrame([{h: str(row.get(h, "") or "") for h in headers}])],
            ignore_index=True,
        )

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict[str, str]) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()


def _blog_row(**kwargs: str) -> dict[str, str]:
    row = {h: "" for h in BLOGS_HEADERS}
    row.update(
        {
            "tipo_registro": "blog",
            "titulo": "Post test",
            "estado_blog": "Borrador",
            "fecha_publicacion_prevista": "20/07/2026",
            **kwargs,
        }
    )
    return row


def test_weekly_blog_count_includes_published_in_same_week() -> None:
    today = date(2026, 7, 20)  # Monday
    rows = [
        _blog_row(estado_blog="Publicado", fecha_publicacion_prevista="22/07/2026"),
    ]
    assert weekly_blog_count(rows, today=today) == 1
    assert not should_show_weekly_gap_alarm(rows, today=today)


def test_weekly_gap_alarm_when_no_blog_scheduled() -> None:
    today = date(2026, 7, 20)
    rows: list[dict[str, str]] = []
    assert should_show_weekly_gap_alarm(rows, today=today)
    gap = build_weekly_gap_alarm_row(rows, today=today)
    assert gap is not None
    assert gap.dismissible is True


def test_due_alarm_until_published() -> None:
    today = date(2026, 7, 20)
    rows = [_blog_row(fecha_publicacion_prevista="19/07/2026", estado_blog="Sin publicar")]
    alarms = build_blog_due_alarm_rows(rows, today=today)
    assert len(alarms) == 1
    rows[0]["estado_blog"] = "Publicado"
    assert build_blog_due_alarm_rows(rows, today=today) == []


def test_log_weekly_gap_dismiss_writes_event_row() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    svc.log_weekly_gap_dismiss(employee_id="EMP001", actor_name="David Ortiz", week_start=date(2026, 7, 20))
    df = svc.blogs_df()
    assert len(df) == 1
    row = df.iloc[0].to_dict()
    assert row["tipo_registro"] == "evento"
    assert row["persona_publica"] == "David Ortiz"
    assert "semana=2026-W30" in row["notas"]
    assert filter_blog_rows(df.fillna("").astype(str).to_dict("records")) == []


def test_alarms_blog_items_includes_weekly_gap_for_empty_list() -> None:
    # This mirrors the integration point in `pages/alarms.py`:
    # if `_blog_items([])` returns the gap row, then removing the guard
    # ensures the card appears even when `HistorialBlog` is empty.
    from pages.alarms import _blog_items

    items = _blog_items([])
    assert len(items) == 1
    assert items[0].dismissible is True
    assert "No hay blog previsto esta semana" in items[0].title
