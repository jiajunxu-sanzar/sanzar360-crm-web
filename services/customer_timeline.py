"""Fusión cronológica de históricos del cliente para la línea de tiempo unificada."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class CustomerTimelineEvent:
    """Suceso ordenable para pintar una sola entrada en UI."""

    on_date: date
    kind_slug: str
    headline: str
    lines: tuple[str, ...]
    tie_break: tuple[str, ...]


_KIND_ORDER = {
    "incidencia_cierra": 0,
    "incidencia_abre": 1,
    "pago_fin": 2,
    "pago_hito": 3,
    "campana_fin": 4,
    "campana_inicio": 5,
    "sensor_revision": 6,
    "sensor_fin": 7,
    "sensor_inicio": 8,
}


def _clean(value: object) -> str:
    raw = "" if value is None else str(value).strip()
    return "" if not raw or raw.casefold() == "nan" else raw


def _parse_date_any(value: str) -> date | None:
    raw = _clean(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _lines_from(parts: dict[str, str]) -> tuple[str, ...]:
    ordered = [f"{lbl}: {val}" for lbl, val in parts.items() if _clean(val)]
    return tuple(ordered[:6])


def build_customer_timeline(
    *,
    sensores_rows: list[dict[str, str]],
    campanas_rows: list[dict[str, str]],
    suscripciones_rows: list[dict[str, str]],
    incidencias_rows: list[dict[str, str]],
) -> list[CustomerTimelineEvent]:
    """Normaliza todas las fuentes históricas en eventos de una sola secuencia."""
    events: list[CustomerTimelineEvent] = []

    for row in sensores_rows:
        sid = _clean(row.get("historial_sensor_id", ""))
        serial = _clean(row.get("sensor_serial_number", ""))
        base_meta = {"Serial": serial, "Tipo": _clean(row.get("tipo_operacion", "")), "Estado": _clean(row.get("estado_sensor", ""))}

        fi = _parse_date_any(row.get("fecha_inicio", ""))
        if fi:
            events.append(
                CustomerTimelineEvent(
                    on_date=fi,
                    kind_slug="sensor_inicio",
                    headline="Sensores · inicio del periodo",
                    lines=_lines_from(
                        {"Serial": serial, "Operación": base_meta["Tipo"], "Estado sensor": base_meta["Estado"]}
                    ),
                    tie_break=("s", sid, "i"),
                )
            )
        ff = _parse_date_any(row.get("fecha_fin", ""))
        if ff and ff != fi:
            events.append(
                CustomerTimelineEvent(
                    on_date=ff,
                    kind_slug="sensor_fin",
                    headline="Sensores · cierre del periodo",
                    lines=_lines_from({"Serial": serial}),
                    tie_break=("s", sid, "f"),
                )
            )
        ur = _parse_date_any(row.get("ultima_revision", ""))
        if ur and ur not in {fi, ff}:
            events.append(
                CustomerTimelineEvent(
                    on_date=ur,
                    kind_slug="sensor_revision",
                    headline="Sensores · revisión registrada",
                    lines=_lines_from({"Serial": serial, "Estado": _clean(row.get("estado_sensor", ""))}),
                    tie_break=("s", sid, "r"),
                )
            )

    for row in campanas_rows:
        cid = _clean(row.get("historial_campana_id", ""))
        nombre = _clean(row.get("nombre_campana", "")) or "Campaña"
        cultivo = _clean(row.get("cultivo", ""))

        fc_i = _parse_date_any(row.get("fecha_campana_inicio", ""))
        if fc_i:
            parts = {"Campaña": nombre}
            if cultivo:
                parts["Cultivo"] = cultivo
            pq = _clean(row.get("parcela", ""))
            if pq:
                parts["Parcela"] = pq
            events.append(
                CustomerTimelineEvent(
                    on_date=fc_i,
                    kind_slug="campana_inicio",
                    headline="Campaña · arranque",
                    lines=_lines_from(parts),
                    tie_break=("c", cid, "i"),
                )
            )
        fc_f = _parse_date_any(row.get("fecha_campana_fin", ""))
        if fc_f and fc_f != fc_i:
            events.append(
                CustomerTimelineEvent(
                    on_date=fc_f,
                    kind_slug="campana_fin",
                    headline=f"Campaña · cierre ({nombre})",
                    lines=_lines_from({"Campaña": nombre}),
                    tie_break=("c", cid, "f"),
                )
            )

    for row in suscripciones_rows:
        hid = _clean(row.get("historial_suscripcion_id", ""))
        monto = _clean(row.get("cantidad_pago", ""))
        moneda = _clean(row.get("moneda", ""))
        metodo = _clean(row.get("metodo_pago", ""))
        estado = _clean(row.get("estado_suscripcion", ""))

        fp = _parse_date_any(row.get("fecha_pago", ""))
        if fp:
            pay_parts: dict[str, str] = {}
            if monto or moneda:
                pay_parts["Importe"] = f"{monto} {moneda}".strip()
            if metodo:
                pay_parts["Método"] = metodo
            if estado:
                pay_parts["Estado"] = estado
            events.append(
                CustomerTimelineEvent(
                    on_date=fp,
                    kind_slug="pago_hito",
                    headline="Pago de suscripción",
                    lines=_lines_from(pay_parts),
                    tie_break=("u", hid, "p"),
                )
            )
        f_end = _parse_date_any(row.get("suscripcion_fecha_fin", ""))
        if f_end and f_end != fp:
            events.append(
                CustomerTimelineEvent(
                    on_date=f_end,
                    kind_slug="pago_fin",
                    headline="Suscripción · fin de periodo registrado",
                    lines=_lines_from({"Estado suscripción": estado} if estado else {}),
                    tie_break=("u", hid, "e"),
                )
            )

    for row in incidencias_rows:
        iid = _clean(row.get("historial_incidencia_id", ""))
        tipo = _clean(row.get("tipo_incidencia", "")) or "Incidencia"
        pri = _clean(row.get("prioridad", ""))
        est = _clean(row.get("estado", ""))
        det = _clean(row.get("detalle", ""))
        teaser = det[:160] + ("…" if len(det) > 160 else "") if det else ""

        fa = _parse_date_any(row.get("fecha_apertura", ""))
        if fa:
            oparts: dict[str, str] = {"Tipo": tipo}
            if pri:
                oparts["Prioridad"] = pri
            if est:
                oparts["Estado"] = est
            if teaser:
                oparts["Resumen"] = teaser
            events.append(
                CustomerTimelineEvent(
                    on_date=fa,
                    kind_slug="incidencia_abre",
                    headline="Incidencia · abierta",
                    lines=_lines_from(oparts),
                    tie_break=("i", iid, "a"),
                )
            )

        fc = _parse_date_any(row.get("fecha_cierre", ""))
        res = _clean(row.get("resolucion", ""))
        res_teaser = res[:160] + ("…" if len(res) > 160 else "") if res else ""
        if fc and fc != fa:
            cparts = {"Tipo": tipo}
            if res_teaser:
                cparts["Cierre"] = res_teaser
            events.append(
                CustomerTimelineEvent(
                    on_date=fc,
                    kind_slug="incidencia_cierra",
                    headline="Incidencia · cerrada",
                    lines=_lines_from(cparts),
                    tie_break=("i", iid, "c"),
                )
            )

    def _sort_key(e: CustomerTimelineEvent) -> tuple[date, int, tuple]:
        prio = _KIND_ORDER.get(e.kind_slug, 99)
        return (e.on_date, prio, e.tie_break)

    return sorted(events, key=_sort_key)


def timeline_events_grouped_months(events: list[CustomerTimelineEvent], *, reverse_chrono: bool) -> list[tuple[str, list[CustomerTimelineEvent]]]:
    """Agrupa eventos en meses naturales preservando el orden de la secuencia dada."""

    def _sort_key(e: CustomerTimelineEvent) -> tuple[date, int, tuple[str, ...]]:
        return e.on_date, _KIND_ORDER.get(e.kind_slug, 99), e.tie_break

    seq = sorted(events, key=_sort_key)
    if reverse_chrono:
        seq = list(reversed(seq))

    buckets: dict[str, list[CustomerTimelineEvent]] = {}
    month_order: list[str] = []

    def _month_label(key: str) -> str:
        y_str, m_str = key.split("-")
        meses = (
            "",
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
        return f"{meses[int(m_str)].capitalize()} {y_str}"

    for ev in seq:
        k = f"{ev.on_date.year:04d}-{ev.on_date.month:02d}"
        if k not in buckets:
            month_order.append(k)
            buckets[k] = []
        buckets[k].append(ev)

    return [(_month_label(k), buckets[k]) for k in month_order]


__all__ = ["CustomerTimelineEvent", "build_customer_timeline", "timeline_events_grouped_months"]
