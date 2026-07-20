"""Counts for sidebar / nav badges on the work inbox."""
from __future__ import annotations

from datetime import date

from services.blogs_validation import build_blog_due_alarm_rows, build_weekly_gap_alarm_row
from services.tareas_validation import build_tareas_alarm_rows


def pending_tareas_inbox_count(
    tareas_rows: list[dict[str, str]],
    blog_rows: list[dict[str, str]],
    *,
    today: date | None = None,
) -> int:
    """Items shown under Centro de alarmas -> Tareas (tareas + blogs)."""
    count = len(build_tareas_alarm_rows(tareas_rows, today=today))
    count += len(build_blog_due_alarm_rows(blog_rows, today=today))
    if build_weekly_gap_alarm_row(blog_rows, today=today):
        count += 1
    return count
