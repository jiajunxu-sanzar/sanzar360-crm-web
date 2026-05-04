from __future__ import annotations

import pandas as pd
import streamlit as st

from app import auth
from app.cache import clear_all_cache, load_contacts_cached, load_users_cached
from app.navigation import (
    ACCIONES_PAGE,
    PAGES_REQUIRING_CONTACTS,
    ROLE_ADMIN,
    ROLES_WITH_ACCIONES_PAGE,
    normalize_role,
    pages_for_role,
    unavailable_pages_for_role,
)
from app.telemetry import timed
from app.state import init_state
from config.settings import CONFIG
from models.contact import empty_contacts_dataframe
from pages import actions_dashboard, alarms, asset_search, contacts, dashboard, email, invoices, map, pricing, purchase_orders, vacaciones, users
from ui.theme import apply_theme


st.set_page_config(page_title="Sanzar CRM", page_icon="S", layout="wide")
apply_theme()
init_state()

with st.sidebar:
    st.title("Sanzar CRM")
    st.caption("Web · Streamlit")

    users_cache_version = st.session_state.get("users_cache_version", 0)
    app_users = load_users_cached(users_cache_version)
    if not app_users:
        st.error("No hay usuarios en 'Usuarios CRM'.")
        st.stop()

    user_options = [u.employee_id for u in app_users]
    user_by_id = {u.employee_id: u for u in app_users}

    # --- Auth guard ---
    # is_authenticated() checks both the auth_ok flag AND that a user_id is stored.
    # If the stored user_id is no longer in the current user list (e.g. after a
    # sheet edit or cache expiry) we log out cleanly — never silently switch user.
    authenticated_id = auth.get_authenticated_user_id()
    if not auth.is_authenticated() or authenticated_id not in user_by_id:
        if authenticated_id and authenticated_id not in user_by_id:
            # User list changed under us — force a clean logout.
            auth.logout()

        with st.form("login_form", clear_on_submit=False):
            # Use a key that is NEVER the same as the auth identity key so
            # Streamlit's widget machinery cannot overwrite the logged-in user.
            login_user_select = st.selectbox(
                "Usuario",
                user_options,
                format_func=lambda uid: user_by_id[uid].nombre,
                key="_login_user_select",
            )
            password_input = st.text_input("Contraseña", type="password", key="_login_password_input")
            submit_login = st.form_submit_button("Entrar", use_container_width=True)

        if submit_login:
            candidate = user_by_id.get(login_user_select)
            if candidate and password_input == candidate.password:
                auth.login(login_user_select)
                st.rerun()
            else:
                st.session_state["login_error"] = "Contraseña incorrecta."

        if st.session_state.get("login_error"):
            st.error(st.session_state["login_error"])

        st.info("Selecciona tu usuario e introduce la contraseña para acceder.")
        st.stop()

    # --- Authenticated from here onwards ---
    selected_user = user_by_id[auth.get_authenticated_user_id()]
    st.caption(f"Usuario: {selected_user.nombre}  ·  Rol: {selected_user.role}")

    available_pages = pages_for_role(selected_user.role)
    blocked_pages = unavailable_pages_for_role(selected_user.role)

    pending_nav_page = st.session_state.get("pending_nav_page", "")
    if pending_nav_page in available_pages:
        st.session_state["active_page"] = pending_nav_page
        st.session_state["nav_page"] = pending_nav_page
        st.session_state["pending_nav_page"] = ""

    active_page = st.session_state.get("active_page", available_pages[0])
    if active_page not in available_pages:
        active_page = available_pages[0]
    if "nav_page" not in st.session_state or st.session_state.get("nav_page") not in available_pages:
        st.session_state["nav_page"] = active_page

    page = st.radio("Navegación", available_pages, key="nav_page")
    if blocked_pages:
        st.markdown(
            "<div style='margin:6px 0 2px 0; color:#94a3b8; font-size:0.8rem;'>No disponible para tu rol</div>",
            unsafe_allow_html=True,
        )
        blocked_html = "".join(
            f"<div style='padding:4px 8px; margin-bottom:4px; border:1px solid #e2e8f0;"
            f" border-radius:8px; color:#94a3b8; background:#f8fafc;'>{p}</div>"
            for p in blocked_pages
        )
        st.markdown(blocked_html, unsafe_allow_html=True)

    st.session_state["_last_page"] = st.session_state.get("_last_page", page)
    if st.session_state["_last_page"] != page:
        # Page changed — close any open modal so it doesn't bleed into the new page.
        from ui import modal_state as _ms
        _ms.close_modal()
    st.session_state["_last_page"] = page
    st.session_state.active_page = page

    if page != "Email":
        st.session_state.pop("_email_portal_unlocked_uid", None)

    if st.button("Recargar datos", use_container_width=True):
        clear_all_cache()
        st.rerun()

    if st.button("Cerrar sesión", use_container_width=True, type="secondary"):
        auth.logout()
        st.rerun()

    if not CONFIG.google_sheet_id:
        st.warning("Falta GOOGLE_SHEET_ID.")

contacts_df: pd.DataFrame
if page in PAGES_REQUIRING_CONTACTS:
    try:
        with st.spinner("Cargando contactos…"):
            with timed("load_contacts_df", page=page):
                contacts_df = load_contacts_cached(st.session_state.get("contacts_cache_version", 0))
    except Exception as exc:
        st.error(f"No se pudieron cargar contactos: {exc}")
        st.stop()
else:
    contacts_df = empty_contacts_dataframe()

if page == "Dashboard":
    dashboard.render(contacts_df)
elif page == ACCIONES_PAGE:
    if normalize_role(selected_user.role) not in ROLES_WITH_ACCIONES_PAGE:
        st.error(
            "La sección Acciones solo está disponible para administradores, equipo agro y ventas (sales)."
        )
        st.stop()
    actions_dashboard.render()
elif page == "Contactos":
    contacts.render(contacts_df)
elif page == "Usuarios":
    if normalize_role(selected_user.role) != ROLE_ADMIN:
        st.error("La sección Usuarios solo está disponible para administradores.")
        st.stop()
    users.render(contacts_df)
elif page == "Buscador sensores/SIM":
    asset_search.render(contacts_df)
elif page == "Vacaciones":
    vacaciones.render(contacts_df)
elif page == "Centro de alarmas":
    alarms.render(contacts_df)
elif page == "Mapa":
    map.render(contacts_df)
elif page == "Email":
    email.render(contacts_df)
elif page == "Purchase Orders":
    purchase_orders.render(contacts_df)
elif page == "Facturas":
    invoices.render(contacts_df)
elif page == "Pricing":
    pricing.render(contacts_df)
