"""Centro de alarmas — bandeja de trabajo (prioridad, plazos, responsable, acción sugerida)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from app.cache import history_service, load_acciones_cached
from ui.components.page_header import render_page_header
from services.contact_proxima_index import enrich_contacts_with_proxima
from app.state import select_contact
from config.contact_estado import is_terminal_contact_estado, normalize_contact_estado
from services.estado_stagnation_alarms import stagnation_alarms
from services.history_service import HistoryService
from services.tareas_validation import build_tareas_alarm_rows
from ui.components.alarms import WorkAlarmItem, render_work_inbox_row


CAT_TAREAS = "Tareas"
CAT_FUNNEL = "Embudo comercial"
CAT_INCIDENTS = "Incidencias"
CAT_SUBS = "Suscripciones"
CAT_SENSORS = "Sensores"
CAT_CAMPAIGNS = "Campañas"


def _parse_sheet_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _sentence_proxima(raw: str) -> str:
    d = _parse_sheet_date(raw)
    if not d:
        return ""
    delta = (d - date.today()).days
    if delta < 0:
        return f"Próxima acción vencida hace {abs(delta)} días"
    if delta == 0:
        return "Próxima acción: hoy"
    return f"Próxima acción en {delta} día{'s' if delta != 1 else ''}"


def _high_priority(p: str) -> bool:
    return (p or "").strip().lower() in {
        "alta",
        "alto",
        "urgente",
        "critica",
        "crítica",
    }


def _priority_key(item: WorkAlarmItem) -> tuple[int, str]:
    order = {"urgente": 0, "crítica": 0, "critica": 0, "alta": 1, "alto": 1, "media": 2, "medio": 2, "baja": 3, "bajo": 3}
    p = (item.priority or "").strip().lower()
    return (order.get(p, 4), item.title or "")


def _due_date_key(item: WorkAlarmItem) -> date:
    return _parse_sheet_date(item.due) or date.max


def _sort_items(items: list[WorkAlarmItem], mode: str) -> list[WorkAlarmItem]:
    if mode == "Fecha":
        return sorted(items, key=lambda i: (_due_date_key(i), _priority_key(i)))
    return sorted(items, key=lambda i: (_priority_key(i), _due_date_key(i)))


def _render_inbox_for_category(
    category_label: str,
    items: list[WorkAlarmItem],
    *,
    sort_mode: str,
    only_high: bool,
) -> None:
    total = len(items)
    high_n = sum(1 for i in items if _high_priority(i.priority))
    items = _sort_items(items, sort_mode)
    if only_high:
        items = [i for i in items if _high_priority(i.priority)]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("En bandeja", total)
    with c2:
        st.metric("Alta / urgente · Alto", high_n)
    with c3:
        st.metric("Visibles ahora", len(items))

    if not items:
        st.info("No hay ítems en esta categoría con los filtros actuales.")
        return

    for i, item in enumerate(items):
        if render_work_inbox_row(item, row_index=i, category_label=category_label):
            if item.contact_id:
                select_contact(str(item.contact_id))
            st.rerun()


def _funnel_embudo_df(contacts_df: pd.DataFrame) -> pd.DataFrame:
    if contacts_df.empty or "estado" not in contacts_df.columns:
        return contacts_df.iloc[0:0].copy()
    mask = contacts_df["estado"].fillna("").astype(str).map(
        lambda value: not is_terminal_contact_estado(normalize_contact_estado(value))
    )
    return contacts_df[mask].copy()


def _funnel_items(contacts_df: pd.DataFrame) -> list[WorkAlarmItem]:
    funnel_df = _funnel_embudo_df(contacts_df)
    if funnel_df.empty:
        return []

    merged: dict[str, dict[str, object]] = {}

    for row in stagnation_alarms(funnel_df):
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        dia = row.get("dias_en_estado", "")
        estado_label = row.get("estado_normalizado") or row.get("estado", "")
        umbral = row.get("umbral_estado", "")
        parts: list[str] = [f"{dia} días en «{estado_label}» (umbral: {umbral})"]
        prox = _sentence_proxima(str(row.get("proxima_accion_fecha", "")))
        if prox:
            parts.append(prox)
        merged[cid] = {
            "row": row,
            "context_parts": parts,
        }

    now = date.today()
    records = funnel_df.fillna("").astype(str).to_dict("records")
    for row in records:
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        raw_due = str(row.get("proxima_accion_fecha", "") or "").strip()
        d = _parse_sheet_date(raw_due)
        if not d or d > now:
            continue
        prox = _sentence_proxima(raw_due)
        existing = merged.get(cid)
        if existing:
            parts_list = list(existing["context_parts"])
            if prox and prox not in parts_list:
                parts_list.insert(0, prox)
            existing["context_parts"] = parts_list
        else:
            merged[cid] = {"row": row, "context_parts": [prox] if prox else []}

    items: list[WorkAlarmItem] = []
    for bundle in merged.values():
        row = bundle["row"]
        if not isinstance(row, dict):
            continue
        raw_due = str(row.get("proxima_accion_fecha", "") or "").strip()
        due_display = raw_due or str(row.get("fecha_estado", "") or "").strip() or "—"
        ctx = " · ".join(p for p in bundle["context_parts"] if isinstance(p, str))  # type: ignore[index]
        val = str(row.get("valor", "") or "").strip()
        items.append(
            WorkAlarmItem(
                title=str(row.get("nombre", "Contacto")),
                priority=val or "Medio",
                due=due_display,
                owner=str(row.get("persona_proxima_accion", "") or ""),
                suggested_action=str(row.get("proxima_accion_detalle", "") or "Definir siguiente paso"),
                detail=f'Estado: {row.get("estado", "—")}',
                contact_id=str(row.get("contact_id", "")),
                context_line=ctx,
            )
        )

    items.sort(key=lambda i: (-int(_high_priority(i.priority)), i.title or ""))
    return items


def _tareas_items(rows: list[dict[str, str]]) -> list[WorkAlarmItem]:
    return [
        WorkAlarmItem(
            title=item.title,
            priority=item.priority,
            due=item.due,
            owner=item.owner,
            suggested_action=item.suggested_action,
            detail=item.detail,
            contact_id=item.contact_id,
            context_line=item.context_line,
        )
        for item in build_tareas_alarm_rows(rows)
    ]


def _incidents_open(rows: list[dict[str, str]]) -> list[WorkAlarmItem]:
    closed = {"cerrada", "cerrado", "resuelta", "resuelto"}
    items: list[WorkAlarmItem] = []
    for row in rows:
        estado = (row.get("estado", "") or "").strip().lower()
        if estado in closed:
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        open_raw = str(row.get("fecha_apertura", "") or "").strip()
        ctx = ""
        if open_raw:
            d = _parse_sheet_date(open_raw)
            if d:
                ctx = f"Abierta hace {(date.today() - d).days} días"
        pr_reg = str(row.get("prioridad", "") or "").strip()
        if pr_reg:
            ctx = f"{ctx} · prioridad {pr_reg}" if ctx else f"Prioridad {pr_reg}"
        tipo = str(row.get("tipo_incidencia", "") or "").strip()
        cliente = str(row.get("nombre_cliente", "") or "").strip()
        title = tipo or "Incidencia"
        if cliente:
            title = f"{title} · {cliente}" if tipo else cliente
        items.append(
            WorkAlarmItem(
                title=title,
                priority=str(row.get("prioridad", "") or "Media"),
                due=open_raw or "—",
                owner="",
                suggested_action=str(row.get("resolucion", "") or "").strip()
                or "Actualizar estado o registrar avance en la ficha",
                detail=str(row.get("detalle", "") or ""),
                contact_id=cid,
                context_line=ctx,
            )
        )
    return items


def _subscriptions_items(contacts_df: pd.DataFrame, hs: HistoryService) -> list[WorkAlarmItem]:
    items: list[WorkAlarmItem] = []
    if contacts_df.empty:
        return items
    horizon = timedelta(days=31)

    for _, crow in contacts_df.iterrows():
        cid = str(crow.get("contact_id", "") or "").strip()
        if not cid:
            continue
        latest = hs.latest_for_contact("suscripciones", cid)
        if not latest:
            continue
        end_raw = str(latest.get("suscripcion_fecha_fin", "") or "").strip()
        end = _parse_sheet_date(end_raw)
        if not end:
            continue
        today = date.today()
        priority = str(crow.get("valor", "") or "").strip()
        estado_sub = str(latest.get("estado_suscripcion", "") or "").strip()
        if end >= today:
            if end > today + horizon:
                continue
            delta = (end - today).days
            ctx = "Finaliza hoy" if delta == 0 else f"Finaliza en {delta} días (≤31)"
            sug = str(latest.get("detalles", "") or "").strip() or "Renovar o revisar cobro antes del vencimiento"
        else:
            ctx = f'Caducada hace {(today - end).days} día{"s" if (today - end).days != 1 else ""}'
            sug = str(latest.get("detalles", "") or "").strip() or "Renovar contrato u oferta comercial desde ficha contacto"

        items.append(
            WorkAlarmItem(
                title=str(crow.get("nombre", "") or latest.get("nombre_cliente", "Suscripción")),
                priority=priority or ("Alta" if end < today else "Alto"),
                due=end_raw,
                owner=str(
                    crow.get("persona_proxima_accion", "")
                ),
                suggested_action=sug,
                detail=f"Estado registro · {estado_sub or '—'}",
                contact_id=cid,
                context_line=ctx,
            )
        )

    items.sort(key=lambda i: (_due_date_key(i), _priority_key(i)))
    return items


def _sensors_items(contacts_df: pd.DataFrame, hs: HistoryService) -> list[WorkAlarmItem]:
    items: list[WorkAlarmItem] = []
    rows = hs.rows("sensores")
    if not rows:
        return items
    today = date.today()
    horizon = today + timedelta(days=7)
    contacts_by_id: dict[str, dict[str, str]] = {
        str(row.get("contact_id", "")).strip(): row
        for row in contacts_df.fillna("").astype(str).to_dict("records")
    }
    for row in rows:
        if str(row.get("estado_cierre_sensor", "")).strip().lower() == "cerrado":
            continue
        end_raw = str(row.get("fecha_fin", "") or "").strip()
        end = _parse_sheet_date(end_raw)
        if not end:
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        if end > horizon:
            continue
        if end < today:
            days = (today - end).days
            priority = "Alta"
            ctx = f'Finalizado hace {days} día{"s" if days != 1 else ""}'
            suggested = "Cerrar histórico o registrar renovación del sensor"
        else:
            days = (end - today).days
            priority = "Media"
            ctx = "Finaliza hoy" if days == 0 else f"Finaliza en {days} días (<=7)"
            suggested = "Planificar renovación antes de fecha fin"
        contact_row = contacts_by_id.get(cid, {})
        sensor_label = str(row.get("sensor_serial_number", "") or "").strip() or "Sensor"
        items.append(
            WorkAlarmItem(
                title=str(row.get("nombre_cliente", "") or contact_row.get("nombre", "") or "Sensor"),
                priority=priority,
                due=end_raw,
                owner=str(contact_row.get("persona_proxima_accion", "") or ""),
                suggested_action=str(row.get("detalles", "") or "").strip() or suggested,
                detail=sensor_label,
                contact_id=cid,
                context_line=ctx,
            )
        )
    items.sort(key=lambda i: (_due_date_key(i), _priority_key(i)))
    return items


def _campaigns_items(contacts_df: pd.DataFrame, hs: HistoryService) -> list[WorkAlarmItem]:
    items: list[WorkAlarmItem] = []
    rows = hs.rows("campanas")
    if not rows:
        return items
    today = date.today()
    horizon = today + timedelta(days=7)
    contacts_by_id: dict[str, dict[str, str]] = {
        str(row.get("contact_id", "")).strip(): row
        for row in contacts_df.fillna("").astype(str).to_dict("records")
    }
    for row in rows:
        if str(row.get("estado_cierre_campana", "")).strip().lower() == "cerrado":
            continue
        end_raw = str(row.get("fecha_campana_fin", "") or "").strip()
        end = _parse_sheet_date(end_raw)
        if not end:
            continue
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        if end > horizon:
            continue
        if end < today:
            days = (today - end).days
            priority = "Alta"
            ctx = f'Finalizada hace {days} día{"s" if days != 1 else ""}'
            suggested = "Cerrar campaña o crear la siguiente fase"
        else:
            days = (end - today).days
            priority = "Media"
            ctx = "Finaliza hoy" if days == 0 else f"Finaliza en {days} días (<=7)"
            suggested = "Revisar cierre de campaña antes de fecha fin"
        contact_row = contacts_by_id.get(cid, {})
        campaign_name = str(row.get("nombre_campana", "") or "").strip() or "Campaña"
        items.append(
            WorkAlarmItem(
                title=str(row.get("nombre_cliente", "") or contact_row.get("nombre", "") or "Campaña"),
                priority=priority,
                due=end_raw,
                owner=str(contact_row.get("persona_proxima_accion", "") or ""),
                suggested_action=str(row.get("detalles", "") or "").strip() or suggested,
                detail=campaign_name,
                contact_id=cid,
                context_line=ctx,
            )
        )
    items.sort(key=lambda i: (_due_date_key(i), _priority_key(i)))
    return items


def render(contacts_df: pd.DataFrame) -> None:
    render_page_header("Centro de alarmas")
    st.caption("Bandeja de trabajo: prioridad, plazos y siguiente acción sobre la ficha del contacto")

    contacts_df = enrich_contacts_with_proxima(
        contacts_df,
        load_acciones_cached(st.session_state.get("history_cache_version", 0)),
    )

    try:
        hs = history_service()
    except Exception as exc:
        st.error(f"No se pudieron cargar históricos: {exc}")
        hs = None

    funnel_items = _funnel_items(contacts_df)

    tareas_items: list[WorkAlarmItem] = []
    incidents_items: list[WorkAlarmItem] = []
    subs_items: list[WorkAlarmItem] = []
    sensors_items: list[WorkAlarmItem] = []
    campaigns_items: list[WorkAlarmItem] = []

    if hs is not None:
        try:
            tareas_items = _tareas_items(hs.rows("tareas"))
        except Exception as exc:
            st.warning(f"Tareas: {exc}")

        try:
            incidents_items = _incidents_open(hs.rows("incidencias"))
        except Exception as exc:
            st.warning(f"Incidencias: {exc}")

        try:
            subs_items = _subscriptions_items(contacts_df, hs)
        except Exception as exc:
            st.warning(f"Suscripciones: {exc}")
        try:
            sensors_items = _sensors_items(contacts_df, hs)
        except Exception as exc:
            st.warning(f"Sensores: {exc}")
        try:
            campaigns_items = _campaigns_items(contacts_df, hs)
        except Exception as exc:
            st.warning(f"Campañas: {exc}")

    items_by_category = {
        CAT_TAREAS: tareas_items,
        CAT_FUNNEL: funnel_items,
        CAT_INCIDENTS: incidents_items,
        CAT_SUBS: subs_items,
        CAT_SENSORS: sensors_items,
        CAT_CAMPAIGNS: campaigns_items,
    }

    total_all = sum(len(v) for v in items_by_category.values())
    if total_all == 0:
        st.success("No hay alarmas activas en este momento.")
        return

    st.caption("Prioriza tu día; cada fila muestra siguiente acción y abre la ficha del contacto.")

    sort_mode = st.radio(
        "Ordenar por",
        ("Prioridad", "Fecha"),
        horizontal=True,
        key="alarms_sort_mode",
    )
    only_high = st.checkbox("Solo alta / urgente / alto valor", key="alarms_only_high")

    configs = (
        ("Tareas", CAT_TAREAS),
        ("Embudo", CAT_FUNNEL),
        ("Incidencias", CAT_INCIDENTS),
        ("Suscripciones", CAT_SUBS),
        ("Sensores", CAT_SENSORS),
        ("Campañas", CAT_CAMPAIGNS),
    )
    tabs = st.tabs([c[0] for c in configs])
    for idx, (_, cat_key) in enumerate(configs):
        with tabs[idx]:
            _render_inbox_for_category(
                cat_key,
                items_by_category[cat_key],
                sort_mode=sort_mode,
                only_high=only_high,
            )