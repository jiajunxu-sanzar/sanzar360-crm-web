import pytest

from app import navigation


def test_pages_subset_hierarchy() -> None:
    admin = frozenset(navigation.pages_for_role("admin"))
    agro = frozenset(navigation.pages_for_role("agro_team"))
    emp = frozenset(navigation.pages_for_role("employee"))
    assert emp <= agro <= admin


def test_admin_sees_users_tab() -> None:
    pages = navigation.pages_for_role(navigation.ROLE_ADMIN)
    assert "Usuarios" in pages


def test_acciones_page_requires_admin_or_agro_in_catalog() -> None:
    """Acciones aparece sólo fuera del rol employee (admin, agro, sales tienen entrada en menú)."""
    admin = navigation.pages_for_role(navigation.ROLE_ADMIN)
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    sal = navigation.pages_for_role(navigation.ROLE_SALES)
    emp = navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
    assert navigation.ACCIONES_PAGE in admin
    assert navigation.ACCIONES_PAGE in agro
    assert navigation.ACCIONES_PAGE in sal
    assert navigation.ACCIONES_PAGE not in emp


def test_agro_team_blocked_from_email_sales_has_email() -> None:
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    sal = navigation.pages_for_role(navigation.ROLE_SALES)
    adm = navigation.pages_for_role(navigation.ROLE_ADMIN)
    assert "Email" not in agro
    assert "Email" in sal
    assert "Email" in adm


def test_agro_team_does_not_see_users_tab() -> None:
    pages = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    assert "Usuarios" not in pages
    assert "Contactos" in pages


def test_unknown_role_maps_to_minimal_employee_tabs() -> None:
    pages = navigation.pages_for_role("soporte_tecnico_nuevo")
    assert pages == navigation.EMPLOYEE_ALLOWED_PAGES


def test_normalize_role() -> None:
    assert navigation.normalize_role(" ADMIN ") == navigation.ROLE_ADMIN
    assert navigation.normalize_role("sales") == navigation.ROLE_SALES
    assert navigation.normalize_role("") == navigation.ROLE_EMPLOYEE


@pytest.mark.parametrize(
    ("role", "expected_exclusive_count"),
    [
        ("admin", len(navigation.PAGES)),
        ("sales", len(navigation.PAGES) - 1),
        ("agro_team", len(navigation.PAGES) - len(navigation.AGRO_TEAM_DENIED_PAGES)),
        ("employee", len(navigation.EMPLOYEE_ALLOWED_PAGES)),
    ],
)
def test_catalog_sizes(role: str, expected_exclusive_count: int) -> None:
    assert len(navigation.pages_for_role(role)) == expected_exclusive_count


def test_unblocked_list_ordered_like_pages() -> None:
    unavailable = navigation.unavailable_pages_for_role("employee")
    idx = [navigation.PAGES.index(p) for p in unavailable]
    assert idx == sorted(idx)
