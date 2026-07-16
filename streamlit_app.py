from __future__ import annotations

import pandas as pd
import streamlit as st

from app import auth
from app.cache import load_contacts_cached, load_users_cached, sheets_service
from app.navigation import (
    ACCIONES_PAGE,
    PAGES_REQUIRING_CONTACTS,
    ROLE_ADMIN,
    ROLES_WITH_ACCIONES_PAGE,
    normalize_role,
    page_menu_title,
    pages_for_role,
    unavailable_pages_for_role,
)
from app.remote_sync import check_remote_changes, reset_remote_sync_state
from app.telemetry import timed
from app.state import (
    hard_refresh_preserving_auth,
    init_state,
    pop_contacts_df_override,
    soft_reload_data,
)
from config.settings import CONFIG
from models.contact import empty_contacts_dataframe
from services.activity_log import init_activity_sheet
from services.contacts_schema import init_contacts_schema
from pages import (
    actions_dashboard,
    alarms,
    asset_search,
    clientes,
    contacts,
    dashboard,
    email,
    inventory,
    invoices,
    map,
    pricing,
    compras,
    referidos,
    vacaciones,
    users,
)
from ui.theme import apply_theme


st.set_page_config(page_title="Sanzar CRM", page_icon="S", layout="wide")
apply_theme()
init_state()

@st.cache_resource(show_spinner=False)
def _ensure_sheet_schemas_once() -> bool:
    """Valida/repara esquemas UNA vez por proceso.

    Antes se ejecutaba en cada rerun de Streamlit (cada interacción de cada
    usuario), y ``ensure_contacts_schema`` descargaba la hoja de contactos
    completa: una fuga silenciosa de cuota de la API.
    """
    init_activity_sheet(sheets_service())
    init_contacts_schema(sheets_service())
    return True


if CONFIG.google_sheet_id:
    try:
        _ensure_sheet_schemas_once()
    except Exception:
        pass


def _close_all_overlays() -> None:
    """Best-effort cleanup of transient overlays across pages."""
    from ui import modal_state as _ms

    _ms.close_modal()
    for key in (
        "new_contact_flow_state",
        "contact_create_confirm_open",
        "contact_creating_in_progress",
        "dialog_new_contact_nombre",
        "_create_contact_nombre",
        "new_contact_similar_candidates",
        "new_contact_require_second_confirm",
        "new_contact_confirmed_override",
        "vac_manage_absences_open",
        "vacaciones.manage_absences_open",
        "pricing_open_dialog",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if (
            key.startswith("show_history_")
            or key.startswith("contact_delete_open_")
            or key.startswith("hist_table_select_")
            or key.startswith("hist_table_version_")
        ):
            st.session_state.pop(key, None)

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
            submit_login = st.form_submit_button("Entrar", width="stretch")

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

    page = st.radio(
        "Navegación",
        available_pages,
        key="nav_page",
        format_func=page_menu_title,
    )
    if blocked_pages:
        st.markdown(
            "<p class='sanzar-nav-blocked-label'>No disponible para tu rol</p>",
            unsafe_allow_html=True,
        )
        blocked_html = "".join(
            f"<div class='sanzar-nav-blocked-item'>{page_menu_title(p)}</div>"
            for p in blocked_pages
        )
        st.markdown(blocked_html, unsafe_allow_html=True)

    st.session_state["_last_page"] = st.session_state.get("_last_page", page)
    if st.session_state["_last_page"] != page:
        # Page changed — close any open overlay so it doesn't bleed into the new page.
        _close_all_overlays()
    st.session_state["_last_page"] = page
    st.session_state.active_page = page

    if page != "Email":
        st.session_state.pop("_email_portal_unlocked_uid", None)

    reload_col, reset_col = st.columns(2, gap="small")
    if reload_col.button(
        "🔄 Recargar datos",
        width="stretch",
        help="Vuelve a leer desde Google Sheets sin perder filtros ni selección.",
    ):
        soft_reload_data()
        reset_remote_sync_state()
        st.toast("Datos recargados", icon="✅")
        st.rerun()

    if reset_col.button(
        "🧹 Reiniciar sesión",
        width="stretch",
        type="secondary",
        help="Limpia toda la sesión (filtros, selección, diálogos) manteniendo el login.",
    ):
        _close_all_overlays()
        hard_refresh_preserving_auth()
        reset_remote_sync_state()
        st.toast("Sesión reiniciada", icon="🧹")
        st.rerun()

    if st.button("Cerrar sesión", width="stretch", type="secondary"):
        auth.logout()
        st.rerun()

    if not CONFIG.google_sheet_id:
        st.warning("Falta GOOGLE_SHEET_ID.")

if check_remote_changes():
    st.toast("Datos actualizados desde Excel", icon="🔄")

_CONTACTS_SEEN_VERSION_KEY = "_contacts_seen_version"


def _load_contacts_for_page(current_page: str) -> pd.DataFrame:
    """Devuelve el DataFrame de contactos para la página actual.

    Sólo muestra el spinner si la lectura va a tocar Google Sheets (cache miss
    o invalidación). En cache hit la operación es instantánea y mostrar un
    spinner produce un parpadeo innecesario que se percibe como lentitud.
    """
    override_df = pop_contacts_df_override()
    if isinstance(override_df, pd.DataFrame):
        return override_df

    current_version = int(st.session_state.get("contacts_cache_version", 0))
    last_seen = st.session_state.get(_CONTACTS_SEEN_VERSION_KEY)
    is_cache_miss = last_seen != current_version

    def _fetch() -> pd.DataFrame:
        with timed("load_contacts_df", page=current_page, cache_miss=is_cache_miss):
            return load_contacts_cached(current_version)

    if is_cache_miss:
        with st.spinner("Cargando contactos…"):
            df = _fetch()
    else:
        df = _fetch()
    st.session_state[_CONTACTS_SEEN_VERSION_KEY] = current_version
    return df


contacts_df: pd.DataFrame
if page in PAGES_REQUIRING_CONTACTS:
    try:
        contacts_df = _load_contacts_for_page(page)
        selected_contact_id = str(st.session_state.get("selected_contact_id", "") or "").strip()
        if selected_contact_id and "contact_id" in contacts_df.columns:
            has_selected = not contacts_df[
                contacts_df["contact_id"].astype(str).str.strip() == selected_contact_id
            ].empty
            if not has_selected and not bool(st.session_state.get("_contacts_forced_reload_once", False)):
                st.session_state["_contacts_forced_reload_once"] = True
                with st.spinner("Sincronizando contactos…"):
                    contacts_df = sheets_service().load_contacts_df()
            else:
                st.session_state["_contacts_forced_reload_once"] = False
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
elif page == "Clientes":
    clientes.render(contacts_df)
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
elif page == "Inventario":
    inventory.render(contacts_df)
elif page == "Compras":
    compras.render(contacts_df)
elif page == "Facturas":
    invoices.render(contacts_df)
elif page == "Pricing":
    pricing.render(contacts_df)
elif page == "Referidos":
    referidos.render(contacts_df)
