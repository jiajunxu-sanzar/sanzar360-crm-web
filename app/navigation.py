"""Navegación lateral por rol — única fuente de verdad para pestañas visibles.

Jerarquía de pestañas (inclusión):

- ``admin``: todas las rutas declaradas en ``PAGES``.
- ``agro_team``: operación completa excepto administración, **sin** pestaña Email.
- ``sales``: mismo alcance histórico de operación para equipo comercial (**incluye** Email).
- ``employee`` (y cualquier rol desconocido): subconjunto mínimo declarado explícitamente.

Para cambiar quién ve qué, edita solo las constantes de este módulo; el orden
del menú sigue siempre ``PAGES`` (canonical).
"""

from __future__ import annotations

from typing import Final

PAGES: Final[tuple[str, ...]] = (
    "Dashboard",
    "Acciones",
    "Centro de alarmas",
    "Contactos",
    "Usuarios",
    "Vacaciones",
    "Buscador sensores/SIM",
    "Mapa",
    "Email",
    "Purchase Orders",
    "Facturas",
    "Pricing",
)

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

# Sin «Usuarios» (admin-only) ni «Email» (reservado a admin + sales).
AGRO_TEAM_DENIED_PAGES: Final[frozenset[str]] = _PAGES_EXCLUSIVE_TO_ADMIN | frozenset({"Email"})

_EMPLOYEE_TAB_KEYS: Final[frozenset[str]] = frozenset(
    {"Vacaciones", "Purchase Orders", "Facturas"}
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
    {"Dashboard", "Contactos", "Centro de alarmas", "Mapa", "Email", "Facturas"}
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
    if "Email" in agro_pages:
        raise AssertionError("La pestaña Email no debe estar en agro_team.")
    if "Email" not in sales_pages:
        raise AssertionError("La pestaña Email debe estar en sales.")
    if not emp.issubset(sales_pages):
        raise AssertionError("Las pestañas de employee deben ser visibles también para sales.")


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
