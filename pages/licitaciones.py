"""Ventana 'Licitaciones' (Operaciones): revision manual de licitaciones PLACSP.

Pipeline de origen (fuera de este CRM, sanzar-licitaciones-process) rellena
la pestana 'Licitaciones' del Google Sheet con lo que scrapea/clasifica un
LLM. Aqui solo se revisa, prioriza, descarta o se deja pasar. Ver
licitaciones-ventana-crm-diseno.md (proyecto de Claude) para el diseno.
"""

from __future__ import annotations

import html
from datetime import datetime

import pandas as pd
import streamlit as st

from app import auth
from app.cache import licitaciones_service, load_licitaciones_cached, load_users_cached
from app.navigation import ROLE_ADMIN, normalize_role
from app.state import bump_licitaciones_cache
from config.settings import LICITACIONES_PRIORIDAD_OPCIONES, LICITACIONES_URGENTE_DIAS_HABILES
from services.licitaciones_service import dias_habiles_restantes, es_urgente, esta_caducada, parse_fecha
from ui.components.cards import chip
from ui.components.page_header import render_page_header
from ui.palette import (
    STATUS_DANGER,
    STATUS_INFO,
    STATUS_NEUTRAL,
    STATUS_PURPLE,
    STATUS_SUCCESS,
    STATUS_WARNING,
)

PAGE_SIZE = 10
_CLEANUP_KEY = "licitaciones_cleanup_last_check_ts"
_CLEANUP_INTERVAL_S = 6 * 3600  # como mucho 1 comprobacion cada 6h por sesion, no en cada rerun
_PAGE_KEY = "licitaciones_page"
_FP_KEY = "licitaciones_filters_fp"

SECTOR_ORDER: tuple[str, ...] = ("agro", "software", "aeroespacial", "observacion_tierra")
SECTOR_LABELS: dict[str, str] = {
    "agro": "Agro",
    "software": "Software",
    "aeroespacial": "Aeroespacial",
    "observacion_tierra": "Observación de la Tierra",
}
SECTOR_STYLES = {
    "agro": STATUS_SUCCESS,
    "software": STATUS_INFO,
    "aeroespacial": STATUS_PURPLE,
    "observacion_tierra": STATUS_WARNING,
}

PRIORIDAD_LABELS: dict[str, str] = {"aplicar": "Aplicar sí o sí", "duda": "En duda"}

ORDEN_OPCIONES: dict[str, tuple[str, bool]] = {
    "Fecha fin (más próxima primero)": ("fecha_fin_presentacion", True),
    "Fecha fin (más lejana primero)": ("fecha_fin_presentacion", False),
    "Importe (mayor primero)": ("importe", False),
    "Importe (menor primero)": ("importe", True),
}


def can_use_licitaciones(role: str) -> bool:
    """Solo administradores pueden consultar y gestionar licitaciones."""
    return normalize_role(role) == ROLE_ADMIN


def _authenticated_user_role() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for user in users:
        if user.employee_id == uid:
            return str(user.role or "")
    return ""


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota exceeded" in msg or "read requests" in msg


def _sectores_list(raw: str) -> list[str]:
    return [s.strip() for s in str(raw or "").split(",") if s.strip()]


def _format_importe(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        return text
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"{formatted} €"


def _format_fecha(raw: str) -> str:
    parsed = parse_fecha(raw)
    return parsed.strftime("%d/%m/%Y") if parsed else (str(raw or "").strip() or "—")


def _exclude_caducadas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    mask = ~df["fecha_fin_presentacion"].astype(str).map(esta_caducada)
    return df[mask].copy()


def _apply_filters(df: pd.DataFrame, *, sectores: list[str], solo_error: bool) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if sectores:
        wanted = set(sectores)
        out = out[
            out["sectores_match"].astype(str).map(lambda raw: bool(wanted & set(_sectores_list(raw))))
        ]
    if solo_error:
        out = out[out["descartado"].astype(str).str.strip().str.lower() == "error"]
    return out


def _sort_df(df: pd.DataFrame, orden_label: str) -> pd.DataFrame:
    if df.empty:
        return df
    column, ascending = ORDEN_OPCIONES.get(orden_label, ("fecha_fin_presentacion", True))
    out = df.copy()
    if column == "importe":
        out["_sort_key"] = pd.to_numeric(out["importe"], errors="coerce")
    else:
        out["_sort_key"] = out["fecha_fin_presentacion"].astype(str).map(parse_fecha)
    out = out.sort_values("_sort_key", ascending=ascending, na_position="last")
    return out.drop(columns=["_sort_key"])


def _run_cleanup_if_due(full_df: pd.DataFrame) -> None:
    """Borra caducadas en Sheets como mucho una vez cada _CLEANUP_INTERVAL_S por sesion."""
    now = datetime.now().timestamp()
    last = float(st.session_state.get(_CLEANUP_KEY, 0.0))
    if (now - last) < _CLEANUP_INTERVAL_S:
        return
    st.session_state[_CLEANUP_KEY] = now
    try:
        removed = licitaciones_service().limpiar_caducadas(full_df)
    except Exception:
        return  # best-effort: si falla, se reintenta en el siguiente throttle
    if removed > 0:
        bump_licitaciones_cache()
        st.toast(f"{removed} licitación(es) caducada(s) eliminada(s) automáticamente.", icon="🗑️")
        st.rerun()


def _render_chips(row: pd.Series) -> str:
    chips = "".join(
        chip(SECTOR_LABELS.get(s, s), SECTOR_STYLES.get(s, STATUS_NEUTRAL))
        for s in _sectores_list(str(row.get("sectores_match", "") or ""))
    )
    descartado = str(row.get("descartado", "") or "").strip().lower()
    if descartado == "error":
        chips += chip("Error de clasificación", STATUS_WARNING)
    dias = dias_habiles_restantes(str(row.get("fecha_fin_presentacion", "") or ""))
    if dias is not None and 0 <= dias <= LICITACIONES_URGENTE_DIAS_HABILES:
        chips += chip(f"Vence en {dias} día(s) hábil(es)", STATUS_DANGER)
    prioridad = str(row.get("prioridad", "") or "").strip()
    if prioridad in PRIORIDAD_LABELS:
        chips += chip(PRIORIDAD_LABELS[prioridad], STATUS_SUCCESS if prioridad == "aplicar" else STATUS_INFO)
    return chips


def _render_licitacion_card(row: pd.Series, *, key_suffix: str) -> None:
    licitacion_id = str(row.get("id", "") or "").strip()
    with st.container(border=True):
        top = st.columns([3.2, 1.0, 1.0])
        top[0].markdown(f"**{html.escape(str(row.get('titulo', '') or '—'))}**")
        top[1].markdown(_format_importe(str(row.get("importe", ""))))
        top[2].markdown(f"Vence: {_format_fecha(str(row.get('fecha_fin_presentacion', '')))}")

        st.caption(html.escape(str(row.get("organo", "") or "—")))
        st.markdown(_render_chips(row), unsafe_allow_html=True)

        resumen = str(row.get("resumen_tecnico", "") or "").strip()
        if resumen and resumen.lower() != "nan":
            st.caption(resumen)
        porque = str(row.get("porque_decision", "") or "").strip()
        if porque and porque.lower() != "nan":
            st.caption(f"Motivo del pipeline: {porque}")
        nota_actual = str(row.get("nota_prioridad", "") or "").strip()
        if nota_actual:
            st.caption(f"Nota de prioridad: {nota_actual}")

        action_cols = st.columns([1.0, 1.0, 1.2])
        enlace = str(row.get("enlace", "") or "").strip()
        if enlace:
            action_cols[0].link_button("Ir a licitación", enlace, use_container_width=True)
        else:
            action_cols[0].button(
                "Sin enlace", key=f"lic_no_link_{key_suffix}", disabled=True, use_container_width=True
            )

        if action_cols[1].button("Descartar", key=f"lic_discard_{key_suffix}", use_container_width=True):
            try:
                ok = licitaciones_service().descartar(licitacion_id)
            except Exception as exc:
                if _is_quota_error(exc):
                    st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                    return
                raise
            if ok:
                bump_licitaciones_cache()
                st.toast("Licitación descartada.", icon="🗑️")
                st.rerun()
            else:
                st.warning("No se encontró la licitación (puede que ya se haya borrado).")

        with action_cols[2].popover("Prioridad", use_container_width=True):
            current_prioridad = str(row.get("prioridad", "") or "").strip()
            options = ["", *LICITACIONES_PRIORIDAD_OPCIONES]
            prioridad_choice = st.radio(
                "Clasificación",
                options,
                index=options.index(current_prioridad) if current_prioridad in options else 0,
                format_func=lambda v: PRIORIDAD_LABELS.get(v, "Sin clasificar"),
                key=f"lic_prioridad_radio_{key_suffix}",
            )
            nota = st.text_area(
                "Nota (por qué aplicar sí o sí / por qué en duda)",
                value=nota_actual,
                key=f"lic_prioridad_nota_{key_suffix}",
            )
            if st.button("Guardar prioridad", key=f"lic_prioridad_save_{key_suffix}", use_container_width=True):
                try:
                    licitaciones_service().guardar_prioridad(row.to_dict(), prioridad_choice, nota)
                except Exception as exc:
                    if _is_quota_error(exc):
                        st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                        return
                    raise
                bump_licitaciones_cache()
                st.toast("Prioridad guardada.", icon="✅")
                st.rerun()


def _render_paginated(df: pd.DataFrame, *, filters_fp: str) -> None:
    if st.session_state.get(_FP_KEY) != filters_fp:
        st.session_state[_FP_KEY] = filters_fp
        st.session_state[_PAGE_KEY] = 0

    total = len(df)
    if total == 0:
        st.info("No hay licitaciones que coincidan con los filtros.")
        return

    max_page = max(0, (total - 1) // PAGE_SIZE)
    page = max(0, min(int(st.session_state.get(_PAGE_KEY, 0) or 0), max_page))
    st.session_state[_PAGE_KEY] = page

    nav_prev, nav_info, nav_next = st.columns([0.15, 0.7, 0.15], gap="small")
    with nav_prev:
        if st.button("← Anterior", key="lic_page_prev", disabled=page <= 0, use_container_width=True):
            st.session_state[_PAGE_KEY] = page - 1
            st.rerun()
    with nav_info:
        start = page * PAGE_SIZE + 1
        end = min((page + 1) * PAGE_SIZE, total)
        st.caption(f"Mostrando {start}–{end} de {total}")
    with nav_next:
        if st.button("Siguiente →", key="lic_page_next", disabled=page >= max_page, use_container_width=True):
            st.session_state[_PAGE_KEY] = page + 1
            st.rerun()

    offset = page * PAGE_SIZE
    for i, (_, row) in enumerate(df.iloc[offset : offset + PAGE_SIZE].iterrows()):
        _render_licitacion_card(row, key_suffix=str(row.get("id", "") or f"row{offset + i}"))


def render(_: pd.DataFrame) -> None:
    render_page_header("Licitaciones")

    if not can_use_licitaciones(_authenticated_user_role()):
        st.warning(
            "Solo los administradores pueden consultar y gestionar licitaciones. "
            "Si necesitas acceso, pídeselo a un administrador del CRM."
        )
        return

    st.caption(
        "Licitaciones públicas relevantes desde PLACSP: prioriza, descarta y revisa antes de la fecha límite."
    )

    ver = st.session_state.get("licitaciones_cache_version", 0)
    try:
        raw_df = load_licitaciones_cached(ver)
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("Google Sheets sin cuota de lectura (429). Reintenta en unos segundos.")
            return
        raise

    if raw_df.empty:
        st.info(
            "Aún no hay licitaciones en la hoja. Pega el Excel en la pestaña "
            "'Licitaciones' del Google Sheet y recarga."
        )
        return

    _run_cleanup_if_due(raw_df)
    vigentes_df = _exclude_caducadas(raw_df)

    urgentes_df = vigentes_df[vigentes_df["fecha_fin_presentacion"].astype(str).map(es_urgente)]
    if not urgentes_df.empty:
        urgentes_df = _sort_df(urgentes_df, "Fecha fin (más próxima primero)")
        st.markdown(f"### 🚨 Vencen en ≤{LICITACIONES_URGENTE_DIAS_HABILES} días hábiles ({len(urgentes_df)})")
        st.caption("Revísalas en detalle: descártalas o clasifícalas como 'Aplicar sí o sí' / 'En duda'.")
        for i, (_, row) in enumerate(urgentes_df.iterrows()):
            _render_licitacion_card(row, key_suffix=f"urg_{row.get('id', '') or i}")
        st.divider()

    st.markdown("### Todas las licitaciones")
    f1, f2, f3 = st.columns([2.0, 1.2, 1.4])
    sectores = f1.multiselect(
        "Sector",
        SECTOR_ORDER,
        format_func=lambda s: SECTOR_LABELS.get(s, s),
        key="licitaciones_filter_sectores",
    )
    solo_error = f2.checkbox("Solo con error de clasificación", key="licitaciones_filter_error")
    orden_label = f3.selectbox("Ordenar por", list(ORDEN_OPCIONES.keys()), key="licitaciones_filter_orden")

    filtered_df = _sort_df(
        _apply_filters(vigentes_df, sectores=sectores, solo_error=solo_error),
        orden_label,
    )
    filters_fp = f"{sorted(sectores)}|{solo_error}|{orden_label}"
    _render_paginated(filtered_df, filters_fp=filters_fp)
