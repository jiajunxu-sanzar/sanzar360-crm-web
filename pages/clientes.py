"""Pestaña Clientes: tablero diario con autoguardado."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app import auth
from app.cache import load_contact_sensor_overview_cached, load_users_cached, sheets_service
from ui.components.page_header import render_page_header
from app.state import bump_contacts_cache, select_contact, set_contacts_df_override
from services.clientes_board import (
    VER_TODOS,
    build_cliente_card_payloads,
    filter_clientes_board,
    sort_clientes_board,
    values_for_flag,
    values_for_visto_toggle,
)
from services.contact_use_cases import save_contact_by_id
from services.users_service import crm_user_names
from ui.components.cliente_cards import cliente_card_shell_html


def _actor_name() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for u in users:
        if u.employee_id == uid:
            return u.nombre
    return uid


def _default_responsable_filter(names: list[str]) -> str:
    actor = _actor_name().strip()
    if actor and actor in names:
        return actor
    return VER_TODOS


def _row_index_for_contact(df: pd.DataFrame, contact_id: str) -> int | None:
    if df.empty or "contact_id" not in df.columns:
        return None
    match = df.index[df["contact_id"].astype(str) == str(contact_id)].tolist()
    return int(match[0]) if match else None


def _autosave_contact_fields(
    df: pd.DataFrame,
    *,
    contact_id: str,
    updates: dict[str, str],
) -> pd.DataFrame:
    row_idx = _row_index_for_contact(df, contact_id)
    if row_idx is None:
        st.error("No se encontró el contacto para guardar.")
        return df
    values = {"contact_id": contact_id, **updates}
    new_df, verify = save_contact_by_id(
        df,
        row_idx=row_idx,
        contact_id=contact_id,
        values=values,
        sheets=sheets_service(),
    )
    bump_contacts_cache()
    set_contacts_df_override(new_df)
    if verify.status != "confirmed":
        st.caption(f"Guardado con verificación: {verify.status}")
    else:
        st.toast("Guardado", icon="✅")
    st.rerun()
    return new_df  # pragma: no cover


def _render_cliente_card(df: pd.DataFrame, payload, *, cache_ver: int) -> pd.DataFrame:
    cid = payload.contact_id
    cid_safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in cid)
    key_suffix = f"{cid_safe}_{cache_ver}"

    st.markdown(cliente_card_shell_html(payload), unsafe_allow_html=True)

    visto_key = f"cli_visto_{key_suffix}"
    umbrales_key = f"cli_umbrales_{key_suffix}"
    suelo_key = f"cli_suelo_{key_suffix}"

    if visto_key not in st.session_state:
        st.session_state[visto_key] = payload.visto_hoy
    if umbrales_key not in st.session_state:
        st.session_state[umbrales_key] = payload.umbrales_activadas
    if suelo_key not in st.session_state:
        st.session_state[suelo_key] = payload.suelo_seco

    visto = st.checkbox("Visto hoy", key=visto_key)
    if visto != payload.visto_hoy:
        return _autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_visto_toggle(checked=visto),
        )

    t1, t2 = st.columns(2)
    with t1:
        umbrales = st.toggle("Umbrales activadas", key=umbrales_key)
    with t2:
        suelo = st.toggle("Suelo seco", key=suelo_key)

    if umbrales != payload.umbrales_activadas:
        return _autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_flag("umbrales_activadas", checked=umbrales),
        )
    if suelo != payload.suelo_seco:
        return _autosave_contact_fields(
            df,
            contact_id=cid,
            updates=values_for_flag("suelo_seco", checked=suelo),
        )

    if st.button("Ir a ficha", key=f"cli_ficha_{key_suffix}", width="stretch"):
        select_contact(cid)
        st.rerun()

    return df


def render(df: pd.DataFrame) -> None:
    render_page_header("Clientes")
    today = date.today()
    st.caption(today.strftime("%d/%m/%Y"))

    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    names = crm_user_names(users)
    filter_opts = [VER_TODOS] + names

    filter_key = "clientes_responsable_filter"
    if filter_key not in st.session_state:
        st.session_state[filter_key] = _default_responsable_filter(names)
    if st.session_state[filter_key] not in filter_opts:
        st.session_state[filter_key] = VER_TODOS

    responsable = st.selectbox(
        "Responsable",
        filter_opts,
        key=filter_key,
        help="Filtra por responsable del cliente. «Ver todos» muestra el tablero completo.",
    )

    board = sort_clientes_board(filter_clientes_board(df, responsable), today=today)
    overview = load_contact_sensor_overview_cached(st.session_state.get("history_cache_version", 0))
    payloads = build_cliente_card_payloads(board, overview, today=today)

    if not payloads:
        st.info("No hay clientes ni potenciales con este filtro.")
        return

    st.caption(f"{len(payloads)} ficha{'s' if len(payloads) != 1 else ''}")
    cache_ver = int(st.session_state.get("contacts_cache_version", 0))
    cols = st.columns(2, gap="medium")
    working = df
    for i, payload in enumerate(payloads):
        with cols[i % 2]:
            with st.container(border=True):
                working = _render_cliente_card(working, payload, cache_ver=cache_ver)
