from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from app import auth
from app.cache import blogs_service, load_blogs_cached, load_users_cached
from app.state import bump_blogs_cache
from config.settings import BLOG_MIN_POR_SEMANA, BLOGS_HEADERS, ESTADO_BLOG_OPCIONES
from services.blogs_validation import (
    filter_blog_rows,
    is_blog_due_or_overdue,
    is_blog_publicado,
    parse_blog_date,
    week_bounds,
    weekly_blog_count,
)
from services.users_service import crm_user_names
from ui.components.page_header import render_page_header

BLOGS_NEW_DIALOG_KEY = "blogs_new_dialog_open"
BLOGS_EDIT_DIALOG_KEY = "blogs_edit_dialog_open"
BLOGS_SELECTED_ID_KEY = "blogs_selected_id"
BLOGS_SUCCESS_KEY = "blogs_success_message"
BLOGS_DELETE_STEP2_KEY = "blogs_delete_step2_id"

ESTADO_BADGE_COLORS: dict[str, tuple[str, str, str]] = {
    "borrador": ("#f4f4f5", "#e4e4e7", "#52525b"),
    "sin publicar": ("#fffbeb", "#fde68a", "#92400e"),
    "publicado": ("#ecfdf5", "#86efac", "#166534"),
}


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota exceeded" in msg or "read requests" in msg


def _actor_name() -> str:
    uid = auth.get_authenticated_user_id()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    for user in users:
        if user.employee_id == uid:
            return user.nombre
    return uid


def _empty_row() -> dict[str, str]:
    return {h: "" for h in BLOGS_HEADERS}


def _row_dict(row: pd.Series) -> dict[str, str]:
    return {h: str(row.get(h, "") or "") for h in BLOGS_HEADERS}


def _estado_badge_html(estado: str) -> str:
    estado_norm = str(estado or "").strip().lower()
    label = estado or "—"
    bg, border, fg = ESTADO_BADGE_COLORS.get(estado_norm, ("#f4f4f5", "#e5e5e5", "#52525b"))
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:8px;"
        f"font-size:0.78rem;font-weight:600;background:{bg};border:1px solid {border};"
        f"color:{fg};white-space:nowrap;'>{html.escape(label)}</span>"
    )


def _close_blogs_new_dialog() -> None:
    st.session_state.pop(BLOGS_NEW_DIALOG_KEY, None)


def _close_blogs_edit_dialog() -> None:
    st.session_state.pop(BLOGS_EDIT_DIALOG_KEY, None)
    st.session_state.pop(BLOGS_DELETE_STEP2_KEY, None)


def _filter_blogs(
    rows: list[dict[str, str]],
    *,
    query: str,
    estado_filter: str,
) -> list[dict[str, str]]:
    q = query.strip().lower()
    out: list[dict[str, str]] = []
    for row in rows:
        estado = str(row.get("estado_blog", "") or "").strip()
        if estado_filter and estado != estado_filter:
            continue
        if q:
            haystack = " ".join(
                str(row.get(col, "") or "")
                for col in ("titulo", "persona_publica", "notas", "estado_blog")
            ).lower()
            if q not in haystack:
                continue
        out.append(row)
    out.sort(
        key=lambda r: (
            parse_blog_date(r.get("fecha_publicacion_prevista", "")) or date.max,
            str(r.get("titulo", "") or "").lower(),
        )
    )
    return out


def _pending_publish_count(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if is_blog_due_or_overdue(row))


def _next_scheduled(rows: list[dict[str, str]]) -> str:
    today = date.today()
    upcoming = [
        parse_blog_date(row.get("fecha_publicacion_prevista", ""))
        for row in rows
        if not is_blog_publicado(row.get("estado_blog", ""))
    ]
    upcoming = [d for d in upcoming if d is not None and d >= today]
    if not upcoming:
        return "—"
    return min(upcoming).strftime("%d/%m/%Y")


def _render_url_field(label: str, value: str, *, key: str) -> str:
    col1, col2 = st.columns([4, 1])
    with col1:
        url = st.text_input(label, value=value, key=key)
    with col2:
        st.write("")
        st.write("")
        if (url or "").strip():
            st.link_button("Abrir", url.strip(), use_container_width=True)
    return url


def _render_blog_form(values: dict[str, str], *, mode: str) -> None:
    prefix = f"blogs_{mode}"
    blog_id = str(values.get("historial_blog_id", "") or "").strip()
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    persona_opts = [""] + crm_user_names(users)
    current_persona = str(values.get("persona_publica", "") or "").strip() or _actor_name()
    if current_persona and current_persona not in persona_opts:
        persona_opts = persona_opts + [current_persona]

    titulo = st.text_input("Título *", value=values.get("titulo", ""), key=f"{prefix}_titulo")
    estado = st.selectbox(
        "Estado",
        list(ESTADO_BLOG_OPCIONES),
        index=list(ESTADO_BLOG_OPCIONES).index(values.get("estado_blog", "Borrador") or "Borrador")
        if (values.get("estado_blog", "Borrador") or "Borrador") in ESTADO_BLOG_OPCIONES
        else 0,
        key=f"{prefix}_estado",
    )
    c1, c2 = st.columns(2)
    with c1:
        fecha_prevista = c1.text_input(
            "Fecha publicación prevista (DD/MM/AAAA) *",
            value=values.get("fecha_publicacion_prevista", ""),
            key=f"{prefix}_fecha_prev",
        )
    with c2:
        fecha_real = c2.text_input(
            "Fecha publicación real (DD/MM/AAAA)",
            value=values.get("fecha_publicacion_real", ""),
            key=f"{prefix}_fecha_real",
        )
    persona_publica = st.selectbox(
        "Persona que publica",
        persona_opts,
        index=persona_opts.index(current_persona) if current_persona in persona_opts else 0,
        key=f"{prefix}_persona",
    )
    link_borrador = _render_url_field("Link borrador", values.get("link_borrador", ""), key=f"{prefix}_link_borrador")
    link_publicado = _render_url_field("Link publicado", values.get("link_publicado", ""), key=f"{prefix}_link_pub")
    notas = st.text_area("Notas internas", value=values.get("notas", ""), key=f"{prefix}_notas", height=80)

    draft = {
        **values,
        "historial_blog_id": blog_id,
        "tipo_registro": "blog",
        "titulo": titulo,
        "estado_blog": estado,
        "fecha_publicacion_prevista": fecha_prevista,
        "fecha_publicacion_real": fecha_real,
        "persona_publica": persona_publica,
        "link_borrador": link_borrador,
        "link_publicado": link_publicado,
        "notas": notas,
    }
    if estado == "Publicado" and not str(draft.get("fecha_publicacion_real", "") or "").strip():
        draft["fecha_publicacion_real"] = date.today().strftime("%d/%m/%Y")

    save_col, cancel_col = st.columns(2)
    if save_col.button("Guardar", type="primary", key=f"{prefix}_save", use_container_width=True):
        try:
            saved_id = blogs_service().upsert_blog(draft)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            if _is_quota_error(exc):
                st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                return
            raise
        bump_blogs_cache()
        st.session_state[BLOGS_SUCCESS_KEY] = "Blog guardado."
        st.session_state[BLOGS_SELECTED_ID_KEY] = saved_id
        if mode == "edit":
            _close_blogs_edit_dialog()
        else:
            _close_blogs_new_dialog()
        st.rerun()

    if cancel_col.button("Cancelar", key=f"{prefix}_cancel", use_container_width=True):
        if mode == "edit":
            _close_blogs_edit_dialog()
        else:
            _close_blogs_new_dialog()
        st.rerun()

    if mode == "edit" and blog_id:
        st.divider()
        if st.button("Eliminar blog", key=f"{prefix}_delete_step1", type="secondary"):
            st.session_state[BLOGS_DELETE_STEP2_KEY] = blog_id
            st.session_state[BLOGS_EDIT_DIALOG_KEY] = True
            st.rerun()
        if str(st.session_state.get(BLOGS_DELETE_STEP2_KEY, "") or "").strip() == blog_id:
            c1, c2 = st.columns(2)
            if c1.button("Confirmar eliminación", key=f"{prefix}_delete_confirm", type="primary", use_container_width=True):
                deleted = blogs_service().delete_blog_by_id(blog_id)
                if not deleted:
                    st.warning("No se encontró el blog.")
                    return
                bump_blogs_cache()
                st.session_state[BLOGS_SELECTED_ID_KEY] = ""
                st.session_state[BLOGS_EDIT_DIALOG_KEY] = False
                st.session_state.pop(BLOGS_DELETE_STEP2_KEY, None)
                st.session_state[BLOGS_SUCCESS_KEY] = "Blog eliminado."
                st.rerun()
            if c2.button("Cancelar eliminación", key=f"{prefix}_delete_cancel", use_container_width=True):
                st.session_state.pop(BLOGS_DELETE_STEP2_KEY, None)
                st.session_state[BLOGS_EDIT_DIALOG_KEY] = True
                st.rerun()


@st.dialog("Nuevo blog", width="large", on_dismiss=_close_blogs_new_dialog)
def _blogs_new_dialog() -> None:
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown("### Alta de blog")
    with head2:
        if st.button("Cerrar", key="blogs_new_close", use_container_width=True):
            _close_blogs_new_dialog()
            st.rerun()
    _render_blog_form(_empty_row(), mode="new")


@st.dialog("Editar blog", width="large", on_dismiss=_close_blogs_edit_dialog)
def _blogs_edit_dialog(blogs_df: pd.DataFrame) -> None:
    blog_id = str(st.session_state.get(BLOGS_SELECTED_ID_KEY, "") or "").strip()
    if not blog_id:
        st.warning("No hay blog seleccionado.")
        return
    matches = blogs_df[blogs_df["historial_blog_id"].astype(str).str.strip() == blog_id]
    if matches.empty:
        st.warning("El blog ya no existe.")
        return
    values = _row_dict(matches.iloc[0])
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown(f"### {values.get('titulo') or blog_id[:8]}")
    with head2:
        if st.button("Cerrar", key="blogs_edit_close", use_container_width=True):
            _close_blogs_edit_dialog()
            st.rerun()
    _render_blog_form(values, mode="edit")


def render(_: pd.DataFrame) -> None:
    render_page_header("Blogs")
    st.caption("Planificación editorial: fechas, responsables y enlaces de borrador/publicación.")

    success = str(st.session_state.pop(BLOGS_SUCCESS_KEY, "") or "").strip()
    if success:
        st.success(success)

    ver = st.session_state.get("blogs_cache_version", 0)
    try:
        blogs_df = load_blogs_cached(ver)
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("Google Sheets sin cuota de lectura (429). Reintenta en unos segundos.")
            return
        raise

    blog_rows = filter_blog_rows(blogs_df.fillna("").astype(str).to_dict("records"))
    week_start, week_end = week_bounds(date.today())
    count_week = weekly_blog_count(blog_rows)
    pending = _pending_publish_count(blog_rows)

    k1, k2, k3 = st.columns(3)
    k1.metric(
        f"Esta semana ({week_start.strftime('%d/%m')}–{week_end.strftime('%d/%m')})",
        f"{count_week} / {BLOG_MIN_POR_SEMANA}",
    )
    k2.metric("Pendientes de publicar", pending)
    k3.metric("Próxima prevista", _next_scheduled(blog_rows))

    if count_week < BLOG_MIN_POR_SEMANA:
        st.warning("No hay ningún blog previsto para esta semana. Programa al menos uno.")

    toolbar1, toolbar2 = st.columns([3, 1])
    with toolbar1:
        query = st.text_input("Buscar", placeholder="Título, persona, notas...", key="blogs_search")
    with toolbar2:
        if st.button("+ Nuevo blog", type="primary", use_container_width=True):
            st.session_state[BLOGS_NEW_DIALOG_KEY] = True
            st.rerun()

    estado_filter = st.selectbox(
        "Estado",
        [""] + list(ESTADO_BLOG_OPCIONES),
        key="blogs_filter_estado",
        format_func=lambda x: "Todos" if not x else x,
    )
    filtered = _filter_blogs(blog_rows, query=query, estado_filter=estado_filter)

    if not filtered:
        st.info("No hay blogs que coincidan con los filtros.")
    else:
        for row in filtered:
            blog_id = str(row.get("historial_blog_id", "") or "").strip()
            titulo = str(row.get("titulo", "") or "").strip() or "—"
            estado = str(row.get("estado_blog", "") or "").strip()
            prevista = str(row.get("fecha_publicacion_prevista", "") or "").strip() or "—"
            real = str(row.get("fecha_publicacion_real", "") or "").strip() or "—"
            persona = str(row.get("persona_publica", "") or "").strip() or "—"
            overdue = is_blog_due_or_overdue(row)
            with st.container(border=True):
                top = st.columns([2.2, 1.0, 1.0, 1.0, 0.8])
                top[0].markdown(f"**{html.escape(titulo)}**")
                top[1].markdown(_estado_badge_html(estado), unsafe_allow_html=True)
                top[2].write(f"Prevista: {prevista}")
                top[3].write(f"Real: {real}")
                top[4].write(persona)
                if overdue:
                    st.caption("Pendiente de publicar (fecha prevista hoy o vencida).")
                links = st.columns([1, 1, 1])
                draft_url = str(row.get("link_borrador", "") or "").strip()
                pub_url = str(row.get("link_publicado", "") or "").strip()
                if draft_url:
                    links[0].link_button("Borrador", draft_url, use_container_width=True)
                if pub_url:
                    links[1].link_button("Publicado", pub_url, use_container_width=True)
                if links[2].button("Editar", key=f"blogs_edit_{blog_id}", use_container_width=True):
                    st.session_state[BLOGS_SELECTED_ID_KEY] = blog_id
                    st.session_state[BLOGS_EDIT_DIALOG_KEY] = True
                    st.rerun()

    if st.session_state.get(BLOGS_NEW_DIALOG_KEY, False):
        _blogs_new_dialog()
    if st.session_state.get(BLOGS_EDIT_DIALOG_KEY, False):
        _blogs_edit_dialog(blogs_df)
