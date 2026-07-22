"""Navegación lateral por rol — única fuente de verdad para pestañas visibles.

Jerarquía de pestañas (inclusión):

- ``admin``: todas las rutas declaradas en ``PAGES``.
- ``agro_team``: operación completa excepto administración (sin «Usuarios»); **incluye** Email.
- ``sales``: mismo alcance de operación para equipo comercial (**incluye** Email).
- ``employee`` (y cualquier rol desconocido): subconjunto mínimo declarado explícitamente.

Para cambiar quién ve qué, edita solo las constantes de este módulo; el orden
del menú sigue siempre ``PAGES`` (canonical). Las etiquetas visibles del radio
(incl. emojis) están en ``PAGE_MENU_LABELS``; ``page_menu_title()`` devuelve
ese texto para cabeceras de página y el sidebar.
"""

from __future__ import annotations

from typing import Final

PAGES: Final[tuple[str, ...]] = (
    "Dashboard",
    "Acciones",
    "Centro de alarmas",
    "Contactos",
    "Clientes",
    "Usuarios",
    "Vacaciones",
    "Buscador sensores/SIM",
    "Mapa",
    "Email",
    "Técnico",
    "Inventario",
    "Compras",
    "Facturas",
    "Pricing",
    "Referidos",
    "Blogs",
)

# Texto del menú lateral (emojis sólo visuales; ``PAGES`` sigue siendo la clave interna).
PAGE_MENU_LABELS: Final[dict[str, str]] = {
    "Dashboard": "📊 Dashboard",
    "Acciones": "⚡ Acciones",
    "Centro de alarmas": "🚨 Centro de alarmas",
    "Contactos": "👥 Contactos",
    "Clientes": "🏢 Clientes",
    "Usuarios": "🔐 Usuarios",
    "Vacaciones": "🏖️ Vacaciones",
    "Buscador sensores/SIM": "🔎 Buscador sensores/SIM",
    "Mapa": "🗺️ Mapa",
    "Email": "✉️ Email",
    "Técnico": "🛠️ Técnico",
    "Inventario": "📦 Inventario",
    "Compras": "🛒 Compras",
    "Facturas": "🧾 Facturas",
    "Pricing": "💰 Pricing",
    "Referidos": "🤝 Referidos",
    "Blogs": "📝 Blogs",
}


def page_menu_title(canonical_page: str) -> str:
    """Misma etiqueta que el menú lateral (emoji + nombre) para una clave de ``PAGES``."""
    return PAGE_MENU_LABELS[canonical_page]


# Iconos Material Symbols para la navegación (Streamlit ``icon=":material/...:"``).
PAGE_ICONS: Final[dict[str, str]] = {
    "Dashboard": ":material/monitoring:",
    "Acciones": ":material/bolt:",
    "Centro de alarmas": ":material/notifications_active:",
    "Contactos": ":material/group:",
    "Clientes": ":material/potted_plant:",
    "Usuarios": ":material/admin_panel_settings:",
    "Vacaciones": ":material/beach_access:",
    "Buscador sensores/SIM": ":material/search:",
    "Mapa": ":material/map:",
    "Email": ":material/mail:",
    "Técnico": ":material/engineering:",
    "Inventario": ":material/inventory_2:",
    "Compras": ":material/shopping_cart:",
    "Facturas": ":material/receipt_long:",
    "Pricing": ":material/payments:",
    "Referidos": ":material/handshake:",
    "Blogs": ":material/article:",
}

# Subtítulo mostrado bajo el título en la cabecera de cada página.
PAGE_DESCRIPTIONS: Final[dict[str, str]] = {
    "Dashboard": "Visión general del pipeline y próximas acciones",
    "Acciones": "Actividad comercial del equipo por semana y canal",
    "Centro de alarmas": "Bandeja de trabajo: incidencias y seguimientos pendientes",
    "Contactos": "Fichas, seguimiento comercial e históricos",
    "Clientes": "Tablero diario de clientes y potenciales",
    "Usuarios": "Gestión de usuarios y roles del CRM",
    "Vacaciones": "Ausencias, teletrabajo y festivos del equipo",
    "Buscador sensores/SIM": "Localiza un activo por serial o SIM y consulta su disponibilidad",
    "Mapa": "Contactos geolocalizados sobre el mapa",
    "Email": "Envío de emails con plantillas y seguimiento",
    "Técnico": "Cálculo de umbrales de riego y cultivos Kc",
    "Inventario": "Sensores, SIMs, gateways y sus asociaciones",
    "Compras": "Pedidos de compra y proveedores",
    "Facturas": "Generación de facturas en PDF",
    "Pricing": "Calculadora de precios",
    "Referidos": "Programa de referidos",
    "Blogs": "Planificación y seguimiento de publicaciones del blog",
}

# Agrupación visual del menú lateral (no afecta a permisos: cada sección se
# filtra por rol y las secciones vacías se ocultan).
NAV_SECTIONS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "Comercial",
        (
            "Dashboard",
            "Acciones",
            "Contactos",
            "Clientes",
            "Centro de alarmas",
            "Mapa",
            "Email",
            "Referidos",
            "Blogs",
        ),
    ),
    (
        "Operaciones",
        (
            "Técnico",
            "Inventario",
            "Buscador sensores/SIM",
            "Compras",
            "Facturas",
            "Pricing",
        ),
    ),
    (
        "Equipo",
        (
            "Vacaciones",
            "Usuarios",
        ),
    ),
)


def nav_sections_for_role(role: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Secciones del menú con solo las páginas visibles para el rol (vacías fuera)."""
    allowed = frozenset(pages_for_role(role))
    out: list[tuple[str, tuple[str, ...]]] = []
    for section_title, section_pages in NAV_SECTIONS:
        visible = tuple(p for p in section_pages if p in allowed)
        if visible:
            out.append((section_title, visible))
    return tuple(out)


_PAGES_SET: Final[frozenset[str]] = frozenset(PAGES)

ACCIONES_PAGE: Final[str] = "Acciones"

ROLE_ADMIN: Final[str] = "admin"
ROLE_AGRO_TEAM: Final[str] = "agro_team"
ROLE_SALES: Final[str] = "sales"
ROLE_EMPLOYEE: Final[str] = "employee"

KNOWN_APP_ROLES: Final[frozenset[str]] = frozenset(
    {
        ROLE_ADMIN,
        ROLE_AGRO_TEAM,
        ROLE_SALES,
        ROLE_EMPLOYEE,
    }
)

ROLE_LABELS: Final[dict[str, str]] = {
    ROLE_ADMIN: "admin",
    ROLE_AGRO_TEAM: "agro_team",
    ROLE_SALES: "sales",
    ROLE_EMPLOYEE: "employee",
}

# Pestañas que sólo aparecen si el rol es admin (ej. configuración sensible).
_PAGES_EXCLUSIVE_TO_ADMIN: Final[frozenset[str]] = frozenset({"Usuarios"})

# Sin «Usuarios» (admin-only). Email está disponible para admin, sales y agro_team.
AGRO_TEAM_DENIED_PAGES: Final[frozenset[str]] = _PAGES_EXCLUSIVE_TO_ADMIN

_EMPLOYEE_TAB_KEYS: Final[frozenset[str]] = frozenset(
    {"Vacaciones", "Compras", "Facturas"}
)
EMPLOYEE_ALLOWED_PAGES: Final[tuple[str, ...]] = tuple(p for p in PAGES if p in _EMPLOYEE_TAB_KEYS)

ROLES_WITH_ACCIONES_PAGE: Final[frozenset[str]] = frozenset(
    {ROLE_ADMIN, ROLE_AGRO_TEAM, ROLE_SALES}
)


def normalize_role(role: str) -> str:
    """Devuelve un rol de aplicación conocido; valores desconocidos → employee (menor privilegio)."""
    slug = (role or "").strip().lower()
    if slug in KNOWN_APP_ROLES:
        return slug
    return ROLE_EMPLOYEE


# Pages that load the main Contacts dataframe from Google Sheets (skip on other pages).
PAGES_REQUIRING_CONTACTS: Final[frozenset[str]] = frozenset(
    {"Dashboard", "Contactos", "Clientes", "Centro de alarmas", "Mapa", "Email", "Facturas", "Inventario", "Técnico"}
)

# ── Integrity (fail fast si alguien añade pestañas incoherentes) ────────────


def _assert_navigation_contract() -> None:
    if not EMPLOYEE_ALLOWED_PAGES:
        raise AssertionError("EMPLOYEE_ALLOWED_PAGES must not be empty")
    emp = frozenset(EMPLOYEE_ALLOWED_PAGES)
    if not emp.issubset(_PAGES_SET):
        raise AssertionError("EMPLOYEE_ALLOWED_PAGES must be a subset of PAGES")
    if not AGRO_TEAM_DENIED_PAGES.issubset(_PAGES_SET):
        raise AssertionError("AGRO_TEAM_DENIED_PAGES must reference only PAGES identifiers")
    # Monotonicité: pestañas de employee ⊆ agro (sin admin-only)
    staff_visible = frozenset(p for p in PAGES if p not in _PAGES_EXCLUSIVE_TO_ADMIN)
    if not emp.issubset(staff_visible):
        raise AssertionError("Employee-visible pages must be a subset of agro_team-visible pages")
    if ACCIONES_PAGE in emp:
        raise AssertionError("Acciones debe ser sólo administración / equipo agro.")
    sales_pages = frozenset(pages_for_role(ROLE_SALES))
    agro_pages = frozenset(pages_for_role(ROLE_AGRO_TEAM))
    if "Email" not in agro_pages:
        raise AssertionError("La pestaña Email debe estar en agro_team.")
    if "Email" not in sales_pages:
        raise AssertionError("La pestaña Email debe estar en sales.")
    if not emp.issubset(sales_pages):
        raise AssertionError("Las pestañas de employee deben ser visibles también para sales.")
    if frozenset(PAGE_MENU_LABELS.keys()) != _PAGES_SET:
        raise AssertionError("PAGE_MENU_LABELS keys must match PAGES exactly")
    if frozenset(PAGE_ICONS.keys()) != _PAGES_SET:
        raise AssertionError("PAGE_ICONS keys must match PAGES exactly")
    if frozenset(PAGE_DESCRIPTIONS.keys()) != _PAGES_SET:
        raise AssertionError("PAGE_DESCRIPTIONS keys must match PAGES exactly")
    section_pages_flat = [p for _, pages in NAV_SECTIONS for p in pages]
    if len(section_pages_flat) != len(set(section_pages_flat)):
        raise AssertionError("NAV_SECTIONS must not repeat pages")
    if frozenset(section_pages_flat) != _PAGES_SET:
        raise AssertionError("NAV_SECTIONS must cover PAGES exactly")


def pages_for_role(role: str) -> tuple[str, ...]:
    slug = normalize_role(role)
    if slug == ROLE_ADMIN:
        return PAGES
    if slug == ROLE_SALES:
        return tuple(p for p in PAGES if p not in _PAGES_EXCLUSIVE_TO_ADMIN)
    if slug == ROLE_AGRO_TEAM:
        return tuple(p for p in PAGES if p not in AGRO_TEAM_DENIED_PAGES)
    return EMPLOYEE_ALLOWED_PAGES


def unavailable_pages_for_role(role: str) -> tuple[str, ...]:
    allowed = frozenset(pages_for_role(role))
    return tuple(page for page in PAGES if page not in allowed)


_assert_navigation_contract()
