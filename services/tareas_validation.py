"""Helpers y validación del histórico de tareas."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from config.settings import ESTADO_TAREA_OPCIONES


def validate_tarea_history_values(values: dict[str, str]) -> str | None:
    if not str(values.get("titulo", "") or "").strip():
        return "El título de la tarea es obligatorio."
    if not str(values.get("notas", "") or "").strip():
        return "El texto de la tarea es obligatorio."
    if not str(values.get("tipo_tarea", "") or "").strip():
        return "El tipo de tarea es obligatorio."
    estado = str(values.get("estado_tarea", "") or "").strip()
    if estado not in ESTADO_TAREA_OPCIONES:
        return "El estado de la tarea debe ser Sin iniciar, En progreso o Terminado."
    return None


def is_tarea_abierta(estado: object) -> bool:
    return str(estado or "").strip() != "Terminado"


def filter_open_tareas(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if is_tarea_abierta(row.get("estado_tarea", ""))]


def _parse_limite(value: object) -> date | None:
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


def sort_tareas_by_fecha_limite(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Ascendente por fecha_limite; sin fecha al final."""

    def key(row: dict[str, str]) -> tuple[int, date]:
        parsed = _parse_limite(row.get("fecha_limite", ""))
        if parsed is None:
            return (1, date.max)
        return (0, parsed)

    return sorted(rows, key=key)


def next_open_tarea(
    rows: list[dict[str, str]],
) -> tuple[int, dict[str, str] | None]:
    """Return (open_count, next_task_by_fecha_limite) for header summary."""
    open_rows = sort_tareas_by_fecha_limite(filter_open_tareas(rows))
    if not open_rows:
        return 0, None
    return len(open_rows), open_rows[0]


def is_tarea_vencida_o_hoy(row: dict[str, str], *, today: date | None = None) -> bool:
    if not is_tarea_abierta(row.get("estado_tarea", "")):
        return False
    parsed = _parse_limite(row.get("fecha_limite", ""))
    if parsed is None:
        return False
    return parsed <= (today or date.today())


@dataclass(frozen=True)
class TareaAlarmRow:
    title: str
    priority: str
    due: str
    owner: str
    suggested_action: str
    detail: str
    contact_id: str
    context_line: str


def build_tareas_alarm_rows(
    rows: list[dict[str, str]],
    *,
    today: date | None = None,
) -> list[TareaAlarmRow]:
    today_d = today or date.today()
    items: list[TareaAlarmRow] = []
    for row in rows:
        if not is_tarea_vencida_o_hoy(row, today=today_d):
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        limite_raw = str(row.get("fecha_limite", "") or "").strip()
        limite = _parse_limite(limite_raw)
        if limite is None:
            continue
        delta = (today_d - limite).days
        if delta > 0:
            ctx = f"Vencida hace {delta} día{'s' if delta != 1 else ''}"
            priority = "Alta"
        else:
            ctx = "Vence hoy"
            priority = "Media"
        titulo = str(row.get("titulo", "") or "").strip() or "Tarea"
        cliente = str(row.get("nombre_cliente", "") or "").strip()
        title = f"{titulo} · {cliente}" if cliente else titulo
        tipo = str(row.get("tipo_tarea", "") or "").strip()
        estado = str(row.get("estado_tarea", "") or "").strip()
        notas = str(row.get("notas", "") or "").strip()
        detail_parts = [p for p in [tipo, estado, notas] if p]
        items.append(
            TareaAlarmRow(
                title=title,
                priority=priority,
                due=limite_raw,
                owner=str(row.get("persona_gestiona", "") or "").strip(),
                suggested_action="Completar o actualizar la tarea en la ficha del contacto",
                detail=" · ".join(detail_parts),
                contact_id=cid,
                context_line=ctx,
            )
        )
    items.sort(key=lambda i: (_parse_limite(i.due) or date.max, i.priority, i.title))
    return items
