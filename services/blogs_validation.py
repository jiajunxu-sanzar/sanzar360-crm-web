"""Validación y lógica de alarmas del módulo Blogs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from config.settings import (
    BLOG_EVENTO_ALARMA_SIN_SEMANA,
    BLOG_MIN_POR_SEMANA,
    BLOG_TIPO_REGISTRO_BLOG,
    BLOG_TIPO_REGISTRO_EVENTO,
    BLOG_TIPO_REGISTRO_NEWSLETTER,
    ESTADO_BLOG_OPCIONES,
)
from services.sheet_date_format import is_valid_dd_mm_yyyy


def parse_blog_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            candidate = raw[:10] if fmt == "%Y-%m-%d" else raw
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def week_bounds(reference: date) -> tuple[date, date]:
    start = reference - timedelta(days=reference.weekday())
    end = start + timedelta(days=6)
    return start, end


def week_key(reference: date) -> str:
    iso = reference.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def is_blog_row(row: dict[str, str]) -> bool:
    tipo = str(row.get("tipo_registro", "") or "").strip().lower()
    return tipo in {"", BLOG_TIPO_REGISTRO_BLOG}


def is_newsletter_row(row: dict[str, str]) -> bool:
    tipo = str(row.get("tipo_registro", "") or "").strip().lower()
    return tipo == BLOG_TIPO_REGISTRO_NEWSLETTER


def is_evento_row(row: dict[str, str]) -> bool:
    tipo = str(row.get("tipo_registro", "") or "").strip().lower()
    return tipo == BLOG_TIPO_REGISTRO_EVENTO


def is_blog_publicado(estado: object) -> bool:
    return str(estado or "").strip().lower() == "publicado"


def filter_blog_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if is_blog_row(row)]


def filter_blog_and_newsletter_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filas visibles en la página Blogs (blogs + newsletters; sin eventos)."""
    return [row for row in rows if not is_evento_row(row)]


def blogs_in_week(rows: list[dict[str, str]], week_start: date) -> list[dict[str, str]]:
    _, week_end = week_bounds(week_start)
    out: list[dict[str, str]] = []
    for row in filter_blog_rows(rows):
        parsed = parse_blog_date(row.get("fecha_publicacion_prevista", ""))
        if parsed is None:
            continue
        if week_start <= parsed <= week_end:
            out.append(row)
    return out


def weekly_blog_count(rows: list[dict[str, str]], *, today: date | None = None) -> int:
    today_d = today or date.today()
    week_start, _ = week_bounds(today_d)
    return len(blogs_in_week(rows, week_start))


def _event_payload_matches_week(notas: str, week: str) -> bool:
    text = str(notas or "")
    return f"evento={BLOG_EVENTO_ALARMA_SIN_SEMANA}" in text and f"semana={week}" in text


def is_weekly_gap_dismissed(rows: list[dict[str, str]], week_start: date) -> bool:
    week = week_key(week_start)
    for row in rows:
        if str(row.get("tipo_registro", "") or "").strip().lower() != BLOG_TIPO_REGISTRO_EVENTO:
            continue
        if _event_payload_matches_week(str(row.get("notas", "") or ""), week):
            return True
    return False


def should_show_weekly_gap_alarm(
    rows: list[dict[str, str]],
    *,
    today: date | None = None,
) -> bool:
    today_d = today or date.today()
    week_start, _ = week_bounds(today_d)
    if weekly_blog_count(rows, today=today_d) >= BLOG_MIN_POR_SEMANA:
        return False
    return not is_weekly_gap_dismissed(rows, week_start)


def validate_blog_values(values: dict[str, str]) -> str | None:
    if not str(values.get("titulo", "") or "").strip():
        return "El título del blog es obligatorio."
    estado = str(values.get("estado_blog", "") or "").strip()
    if estado not in ESTADO_BLOG_OPCIONES:
        return "El estado debe ser Borrador, Sin publicar o Publicado."
    for col in ("fecha_publicacion_prevista", "fecha_publicacion_real"):
        raw = str(values.get(col, "") or "").strip()
        if raw and not is_valid_dd_mm_yyyy(raw):
            return f"{col} debe estar en formato DD/MM/AAAA."
    if not str(values.get("fecha_publicacion_prevista", "") or "").strip():
        return "La fecha de publicación prevista es obligatoria."
    return None


def is_blog_due_or_overdue(row: dict[str, str], *, today: date | None = None) -> bool:
    if is_blog_publicado(row.get("estado_blog", "")):
        return False
    parsed = parse_blog_date(row.get("fecha_publicacion_prevista", ""))
    if parsed is None:
        return False
    return parsed <= (today or date.today())


@dataclass(frozen=True)
class BlogAlarmRow:
    title: str
    priority: str
    due: str
    owner: str
    suggested_action: str
    detail: str
    alarm_key: str
    context_line: str
    dismissible: bool = False


def build_blog_due_alarm_rows(
    rows: list[dict[str, str]],
    *,
    today: date | None = None,
) -> list[BlogAlarmRow]:
    today_d = today or date.today()
    items: list[BlogAlarmRow] = []
    for row in filter_blog_rows(rows):
        if not is_blog_due_or_overdue(row, today=today_d):
            continue
        prevista_raw = str(row.get("fecha_publicacion_prevista", "") or "").strip()
        prevista = parse_blog_date(prevista_raw)
        if prevista is None:
            continue
        delta = (today_d - prevista).days
        if delta > 0:
            ctx = f"Publicación prevista vencida hace {delta} día{'s' if delta != 1 else ''}"
            priority = "Alta"
        else:
            ctx = "Publicación prevista hoy"
            priority = "Media"
        estado = str(row.get("estado_blog", "") or "").strip()
        titulo = str(row.get("titulo", "") or "").strip() or "Blog"
        blog_id = str(row.get("historial_blog_id", "") or "").strip()
        items.append(
            BlogAlarmRow(
                title=titulo,
                priority=priority,
                due=prevista_raw,
                owner=str(row.get("persona_publica", "") or "").strip(),
                suggested_action="Publicar el blog o actualizar su estado en la sección Blogs",
                detail=f"Estado: {estado}" if estado else "",
                alarm_key=f"blog:{blog_id}" if blog_id else "blog:unknown",
                context_line=ctx,
            )
        )
    items.sort(key=lambda i: (parse_blog_date(i.due) or date.max, i.title))
    return items


def build_weekly_gap_alarm_row(
    rows: list[dict[str, str]],
    *,
    today: date | None = None,
) -> BlogAlarmRow | None:
    if not should_show_weekly_gap_alarm(rows, today=today):
        return None
    today_d = today or date.today()
    week_start, week_end = week_bounds(today_d)
    week = week_key(week_start)
    return BlogAlarmRow(
        title="No hay blog previsto esta semana",
        priority="Alta",
        due=week_start.strftime("%d/%m/%Y"),
        owner="",
        suggested_action="Programar al menos un blog con fecha prevista en la semana actual",
        detail=f"Semana {week} ({week_start.strftime('%d/%m')} – {week_end.strftime('%d/%m')})",
        alarm_key=f"blog_gap:{week}",
        context_line=f"Objetivo: al menos {BLOG_MIN_POR_SEMANA} blog por semana",
        dismissible=True,
    )
