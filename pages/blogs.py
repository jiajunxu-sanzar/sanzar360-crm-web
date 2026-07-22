from __future__ import annotations

import html
import json
from datetime import date

import pandas as pd
import streamlit as st

from app import auth
from app.cache import blogs_service, load_blogs_cached, load_users_cached
from app.state import bump_blogs_cache
from config.settings import (
    BLOG_MIN_POR_SEMANA,
    BLOG_TIPO_REGISTRO_NEWSLETTER,
    BLOGS_HEADERS,
    ESTADO_BLOG_OPCIONES,
)
from services.blogs_validation import (
    filter_blog_and_newsletter_rows,
    filter_blog_rows,
    is_blog_due_or_overdue,
    is_blog_publicado,
    is_blog_row,
    is_newsletter_row,
    parse_blog_date,
    week_bounds,
    weekly_blog_count,
)
from services.newsletter_service import (
    TEST_CONTACT_ID,
    TEST_NEWSLETTER_ID,
    build_unsubscribe_url,
    data_uri,
    load_linkedin_icon_bytes,
    load_logo_bytes,
    load_web_icon_bytes,
    newsletter_content_from_historial_row,
    render_newsletter_html,
    row_had_newsletter_image,
)
from services.users_service import person_select_options
from ui.components.page_header import render_page_header

BLOGS_NEW_DIALOG_KEY = "blogs_new_dialog_open"
BLOGS_NEW_NL_DIALOG_KEY = "blogs_new_newsletter_dialog_open"
BLOGS_EDIT_DIALOG_KEY = "blogs_edit_dialog_open"
BLOGS_SELECTED_ID_KEY = "blogs_selected_id"
BLOGS_SUCCESS_KEY = "blogs_success_message"
BLOGS_DELETE_STEP2_KEY = "blogs_delete_step2_id"
BLOGS_NL_DETAIL_DIALOG_KEY = "blogs_newsletter_detail_open"
BLOGS_NL_DETAIL_ID_KEY = "blogs_newsletter_detail_id"

_NEWSLETTER_ESTADO_OPCIONES: tuple[str, ...] = ("Borrador", "Publicado")

ESTADO_BADGE_COLORS: dict[str, tuple[str, str, str]] = {
    "borrador": ("#f4f4f5", "#e4e4e7", "#52525b"),
    "sin publicar": ("#fffbeb", "#fde68a", "#92400e"),
    "publicado": ("#ecfdf5", "#86efac", "#166534"),
}

_TIPO_FILTER_TODOS = "Todos"
_TIPO_FILTER_BLOG = "Blog"
_TIPO_FILTER_NEWSLETTER = "Newsletter"


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


def _tipo_badge_html(tipo: str) -> str:
    if tipo == BLOG_TIPO_REGISTRO_NEWSLETTER:
        return (
            "<span style='display:inline-block;padding:4px 10px;border-radius:8px;"
            "font-size:0.78rem;font-weight:600;background:#eff6ff;border:1px solid #bfdbfe;"
            "color:#1e40af;white-space:nowrap;'>Newsletter</span>"
        )
    return (
        "<span style='display:inline-block;padding:4px 10px;border-radius:8px;"
        "font-size:0.78rem;font-weight:600;background:#f4f4f5;border:1px solid #e4e4e7;"
        "color:#3f3f46;white-space:nowrap;'>Blog</span>"
    )


def _close_blogs_new_dialog() -> None:
    st.session_state.pop(BLOGS_NEW_DIALOG_KEY, None)


def _close_blogs_new_newsletter_dialog() -> None:
    st.session_state.pop(BLOGS_NEW_NL_DIALOG_KEY, None)


def _close_blogs_edit_dialog() -> None:
    st.session_state.pop(BLOGS_EDIT_DIALOG_KEY, None)
    st.session_state.pop(BLOGS_DELETE_STEP2_KEY, None)


def _close_newsletter_detail_dialog() -> None:
    st.session_state.pop(BLOGS_NL_DETAIL_DIALOG_KEY, None)
    st.session_state.pop(BLOGS_NL_DETAIL_ID_KEY, None)


def _row_sort_key(row: dict[str, str]) -> tuple:
    """Más recientes primero (newsletter_fecha_envio o fechas de blog)."""
    envio = str(row.get("newsletter_fecha_envio", "") or "").strip()
    if envio:
        return (0, envio)
    real = parse_blog_date(row.get("fecha_publicacion_real", ""))
    prevista = parse_blog_date(row.get("fecha_publicacion_prevista", ""))
    d = real or prevista or date.min
    return (1, d.isoformat())


def _filter_blogs(
    rows: list[dict[str, str]],
    *,
    query: str,
    estado_filter: str,
    tipo_filter: str,
) -> list[dict[str, str]]:
    q = query.strip().lower()
    out: list[dict[str, str]] = []
    for row in rows:
        if tipo_filter == _TIPO_FILTER_BLOG and not is_blog_row(row):
            continue
        if tipo_filter == _TIPO_FILTER_NEWSLETTER and not is_newsletter_row(row):
            continue
        estado = str(row.get("estado_blog", "") or "").strip()
        if estado_filter and estado != estado_filter:
            continue
        if q:
            haystack = " ".join(
                str(row.get(col, "") or "")
                for col in (
                    "titulo",
                    "persona_publica",
                    "responsable_blog",
                    "notas",
                    "estado_blog",
                    "newsletter_asunto",
                    "newsletter_enviado_por",
                    "newsletter_texto",
                )
            ).lower()
            if q not in haystack:
                continue
        out.append(row)
    out.sort(key=_row_sort_key, reverse=True)
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
    current_persona = str(values.get("persona_publica", "") or "").strip() or _actor_name()
    current_responsable = str(values.get("responsable_blog", "") or "").strip() or _actor_name()
    persona_opts = person_select_options(users, current=current_persona)
    if current_responsable and current_responsable not in persona_opts:
        persona_opts = persona_opts + [current_responsable]

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
    p1, p2 = st.columns(2)
    with p1:
        persona_publica = p1.selectbox(
            "Persona que publica",
            persona_opts,
            index=persona_opts.index(current_persona) if current_persona in persona_opts else 0,
            key=f"{prefix}_persona",
        )
    with p2:
        responsable_blog = p2.selectbox(
            "Responsable de blog",
            persona_opts,
            index=persona_opts.index(current_responsable) if current_responsable in persona_opts else 0,
            key=f"{prefix}_responsable",
        )
    link_borrador = _render_url_field("Link borrador", values.get("link_borrador", ""), key=f"{prefix}_link_borrador")
    link_publicado = _render_url_field("Link publicado", values.get("link_publicado", ""), key=f"{prefix}_link_pub")
    link_publicado_linkedin = _render_url_field(
        "Link publicado LinkedIn",
        values.get("link_publicado_linkedin", ""),
        key=f"{prefix}_link_linkedin",
    )
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
        "responsable_blog": responsable_blog,
        "link_borrador": link_borrador,
        "link_publicado": link_publicado,
        "link_publicado_linkedin": link_publicado_linkedin,
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


@st.dialog("Nuevo newsletter", width="large", on_dismiss=_close_blogs_new_newsletter_dialog)
def _blogs_new_newsletter_dialog() -> None:
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown("### Planificar newsletter")
    with head2:
        if st.button("Cerrar", key="blogs_new_nl_close", use_container_width=True):
            _close_blogs_new_newsletter_dialog()
            st.rerun()

    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    current_persona = _actor_name()
    persona_opts = person_select_options(users, current=current_persona)

    titulo = st.text_input("Título *", key="blogs_new_nl_titulo")
    persona_publica = st.selectbox(
        "Enviado por / Publica *",
        persona_opts,
        index=persona_opts.index(current_persona) if current_persona in persona_opts else 0,
        key="blogs_new_nl_persona",
    )
    link_borrador = _render_url_field("Link borrador", "", key="blogs_new_nl_link_borrador")
    estado = st.selectbox(
        "Estado",
        list(_NEWSLETTER_ESTADO_OPCIONES),
        index=0,
        key="blogs_new_nl_estado",
    )
    fecha_prevista = st.text_input(
        "Fecha publicación prevista (DD/MM/AAAA) *",
        key="blogs_new_nl_fecha_prev",
    )
    notas = st.text_area("Notas (opcional)", key="blogs_new_nl_notas", height=80)

    save_col, cancel_col = st.columns(2)
    if save_col.button("Guardar", type="primary", key="blogs_new_nl_save", use_container_width=True):
        try:
            blogs_service().create_newsletter_draft(
                titulo=titulo,
                persona_publica=str(persona_publica or ""),
                link_borrador=link_borrador,
                estado_blog=str(estado or "Borrador"),
                fecha_publicacion_prevista=fecha_prevista,
                notas=notas,
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            if _is_quota_error(exc):
                st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                return
            raise
        bump_blogs_cache()
        st.session_state[BLOGS_SUCCESS_KEY] = "Newsletter planificada."
        _close_blogs_new_newsletter_dialog()
        st.rerun()
    if cancel_col.button("Cancelar", key="blogs_new_nl_cancel", use_container_width=True):
        _close_blogs_new_newsletter_dialog()
        st.rerun()


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


@st.dialog("Detalle newsletter", width="large")
def _newsletter_detail_dialog(blogs_df: pd.DataFrame) -> None:
    nl_id = str(st.session_state.get(BLOGS_NL_DETAIL_ID_KEY, "") or "").strip()
    if not nl_id:
        st.warning("No hay newsletter seleccionada.")
        return
    matches = blogs_df[blogs_df["historial_blog_id"].astype(str).str.strip() == nl_id]
    if matches.empty:
        st.warning("La newsletter ya no existe.")
        return
    row = _row_dict(matches.iloc[0])
    content = newsletter_content_from_historial_row(row)
    enviado_por = str(row.get("newsletter_enviado_por", "") or row.get("persona_publica", "") or "—").strip() or "—"
    fecha_envio = str(row.get("newsletter_fecha_envio", "") or "—").strip() or "—"
    num_dest = str(row.get("newsletter_num_destinatarios", "") or "0").strip() or "0"
    asunto = content.asunto or content.titulo or "—"
    tiene_imagen = row_had_newsletter_image(row)
    boton = str(row.get("boton_newsletter", "") or "no").strip() or "no"

    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown(f"### {html.escape(content.titulo or nl_id[:8])}")
    with head2:
        if st.button("Cerrar", key="blogs_nl_detail_close", use_container_width=True):
            _close_newsletter_detail_dialog()
            st.rerun()

    st.markdown(f"**Enviado por:** {html.escape(enviado_por)}")
    st.markdown(f"**Fecha de envío:** {html.escape(fecha_envio)}")
    st.markdown(f"**Asunto:** {html.escape(asunto)}")
    st.markdown(f"**Destinatarios:** {html.escape(num_dest)}")
    st.markdown(f"**Botón CTA:** {html.escape(boton)}")
    if boton.lower() in {"sí", "si"} and content.cta_url:
        st.markdown(
            f"**Enlace CTA:** [{html.escape(content.cta_texto or content.cta_url)}]"
            f"({content.cta_url})"
        )
    st.markdown(f"**Imagen de cabecera:** {'sí' if tiene_imagen else 'no'}")
    if tiene_imagen:
        st.caption("Incluyó imagen de cabecera en el envío (no se guarda el archivo; el preview no la muestra).")

    try:
        destinatarios = json.loads(row.get("newsletter_destinatarios_json", "") or "[]")
    except (TypeError, ValueError):
        destinatarios = []
    if isinstance(destinatarios, list) and destinatarios:
        with st.expander(f"Lista de destinatarios ({len(destinatarios)})", expanded=False):
            for dest in destinatarios[:50]:
                if not isinstance(dest, dict):
                    continue
                nombre = str(dest.get("nombre", "") or "").strip() or "—"
                correo = str(dest.get("correo", "") or "").strip() or "—"
                st.caption(f"{nombre} · {correo}")
            if len(destinatarios) > 50:
                st.caption(f"… y {len(destinatarios) - 50} más")

    preview_html = render_newsletter_html(
        content,
        logo_src=data_uri(load_logo_bytes(), "png"),
        hero_src=None,
        unsubscribe_url=build_unsubscribe_url(TEST_CONTACT_ID, TEST_NEWSLETTER_ID) or "#",
        icon_web_src=data_uri(load_web_icon_bytes(), "png"),
        icon_linkedin_src=data_uri(load_linkedin_icon_bytes(), "png"),
    )
    st.markdown("##### Vista previa del correo")
    st.components.v1.html(preview_html, height=520, scrolling=True)


def render(_: pd.DataFrame) -> None:
    render_page_header("Blogs")
    st.caption("Planificación editorial y newsletters enviadas.")

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

    all_rows = filter_blog_and_newsletter_rows(blogs_df.fillna("").astype(str).to_dict("records"))
    blog_rows = filter_blog_rows(all_rows)
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

    toolbar1, toolbar2, toolbar3 = st.columns([2.4, 1, 1])
    with toolbar1:
        query = st.text_input("Buscar", placeholder="Título, persona, notas...", key="blogs_search")
    with toolbar2:
        if st.button("+ Nuevo blog", type="primary", use_container_width=True):
            st.session_state[BLOGS_NEW_DIALOG_KEY] = True
            st.rerun()
    with toolbar3:
        if st.button("+ Nuevo newsletter", use_container_width=True):
            st.session_state[BLOGS_NEW_NL_DIALOG_KEY] = True
            st.rerun()

    f1, f2 = st.columns(2)
    with f1:
        tipo_filter = st.selectbox(
            "Tipo",
            [_TIPO_FILTER_TODOS, _TIPO_FILTER_BLOG, _TIPO_FILTER_NEWSLETTER],
            key="blogs_filter_tipo",
        )
    with f2:
        estado_filter = st.selectbox(
            "Estado",
            [""] + list(ESTADO_BLOG_OPCIONES),
            key="blogs_filter_estado",
            format_func=lambda x: "Todos" if not x else x,
        )
    filtered = _filter_blogs(
        all_rows, query=query, estado_filter=estado_filter, tipo_filter=tipo_filter
    )

    if not filtered:
        st.info("No hay entradas que coincidan con los filtros.")
    else:
        for row in filtered:
            row_id = str(row.get("historial_blog_id", "") or "").strip()
            titulo = str(row.get("titulo", "") or "").strip() or "—"
            is_nl = is_newsletter_row(row)
            with st.container(border=True):
                if is_nl:
                    estado_nl = str(row.get("estado_blog", "") or "").strip() or "—"
                    enviado = str(row.get("newsletter_enviado_por", "") or row.get("persona_publica", "") or "—")
                    fecha_envio = str(row.get("newsletter_fecha_envio", "") or "").strip()
                    prevista = str(row.get("fecha_publicacion_prevista", "") or "").strip() or "—"
                    num_dest = str(row.get("newsletter_num_destinatarios", "") or "0")
                    top = st.columns([1.8, 0.85, 0.75, 1.1, 0.95, 0.75])
                    top[0].markdown(f"**{html.escape(titulo)}**")
                    top[1].markdown(_tipo_badge_html(BLOG_TIPO_REGISTRO_NEWSLETTER), unsafe_allow_html=True)
                    top[2].markdown(_estado_badge_html(estado_nl), unsafe_allow_html=True)
                    top[3].write(f"Prevista: {prevista}" if not fecha_envio else f"Enviado: {fecha_envio}")
                    top[4].write(f"Por: {enviado}")
                    top[5].write(f"Dest.: {num_dest}")
                    if st.button("Detalle", key=f"blogs_nl_detail_{row_id}", use_container_width=True):
                        st.session_state[BLOGS_NL_DETAIL_ID_KEY] = row_id
                        st.session_state[BLOGS_NL_DETAIL_DIALOG_KEY] = True
                        st.rerun()
                else:
                    estado = str(row.get("estado_blog", "") or "").strip()
                    prevista = str(row.get("fecha_publicacion_prevista", "") or "").strip() or "—"
                    real = str(row.get("fecha_publicacion_real", "") or "").strip() or "—"
                    persona = str(row.get("persona_publica", "") or "").strip() or "—"
                    responsable = str(row.get("responsable_blog", "") or "").strip() or "—"
                    overdue = is_blog_due_or_overdue(row)
                    top = st.columns([1.7, 0.7, 0.8, 0.95, 0.95, 0.85, 0.85])
                    top[0].markdown(f"**{html.escape(titulo)}**")
                    top[1].markdown(_tipo_badge_html("blog"), unsafe_allow_html=True)
                    top[2].markdown(_estado_badge_html(estado), unsafe_allow_html=True)
                    top[3].write(f"Prevista: {prevista}")
                    top[4].write(f"Real: {real}")
                    top[5].write(f"Publica: {persona}")
                    top[6].write(f"Resp.: {responsable}")
                    if overdue:
                        st.caption("Pendiente de publicar (fecha prevista hoy o vencida).")
                    links = st.columns([1, 1, 1, 1])
                    draft_url = str(row.get("link_borrador", "") or "").strip()
                    pub_url = str(row.get("link_publicado", "") or "").strip()
                    linkedin_url = str(row.get("link_publicado_linkedin", "") or "").strip()
                    if draft_url:
                        links[0].link_button("Borrador", draft_url, use_container_width=True)
                    if pub_url:
                        links[1].link_button("Publicado", pub_url, use_container_width=True)
                    if linkedin_url:
                        links[2].link_button("LinkedIn", linkedin_url, use_container_width=True)
                    if links[3].button("Editar", key=f"blogs_edit_{row_id}", use_container_width=True):
                        st.session_state[BLOGS_SELECTED_ID_KEY] = row_id
                        st.session_state[BLOGS_EDIT_DIALOG_KEY] = True
                        st.rerun()

    if st.session_state.get(BLOGS_NEW_DIALOG_KEY, False):
        _blogs_new_dialog()
    if st.session_state.get(BLOGS_NEW_NL_DIALOG_KEY, False):
        _blogs_new_newsletter_dialog()
    if st.session_state.get(BLOGS_EDIT_DIALOG_KEY, False):
        _blogs_edit_dialog(blogs_df)
    if st.session_state.get(BLOGS_NL_DETAIL_DIALOG_KEY, False):
        _newsletter_detail_dialog(blogs_df)
