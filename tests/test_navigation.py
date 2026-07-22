import pytest

from app import navigation


def test_page_menu_title_matches_menu_labels() -> None:
    for p in navigation.PAGES:
        assert navigation.page_menu_title(p) == navigation.PAGE_MENU_LABELS[p]


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


def test_agro_team_and_sales_have_email() -> None:
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    sal = navigation.pages_for_role(navigation.ROLE_SALES)
    adm = navigation.pages_for_role(navigation.ROLE_ADMIN)
    assert "Email" in agro
    assert "Email" in sal
    assert "Email" in adm


def test_agro_team_does_not_see_users_tab() -> None:
    pages = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    assert "Usuarios" not in pages
    assert "Contactos" in pages


def test_unknown_role_maps_to_minimal_employee_tabs() -> None:
    pages = navigation.pages_for_role("soporte_tecnico_nuevo")
    assert pages == navigation.EMPLOYEE_ALLOWED_PAGES
    assert "Compras" in pages


def test_employee_sees_compras_not_purchase_orders_legacy_name() -> None:
    emp = navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
    assert "Compras" in emp
    assert "Purchase Orders" not in navigation.PAGES


def test_referidos_visible_to_commercial_roles_not_employee() -> None:
    sales = navigation.pages_for_role(navigation.ROLE_SALES)
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    emp = navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
    assert "Referidos" in sales
    assert "Referidos" in agro
    assert "Referidos" not in emp


def test_blogs_visible_to_commercial_roles_not_employee() -> None:
    sales = navigation.pages_for_role(navigation.ROLE_SALES)
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    emp = navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
    assert "Blogs" in sales
    assert "Blogs" in agro
    assert "Blogs" not in emp
    commercial_pages = navigation.NAV_SECTIONS[0][1]
    assert "Blogs" in commercial_pages
    assert commercial_pages.index("Blogs") == commercial_pages.index("Referidos") + 1


def test_tecnico_visible_to_commercial_roles_not_employee() -> None:
    sales = navigation.pages_for_role(navigation.ROLE_SALES)
    agro = navigation.pages_for_role(navigation.ROLE_AGRO_TEAM)
    emp = navigation.pages_for_role(navigation.ROLE_EMPLOYEE)
    assert "Técnico" in sales
    assert "Técnico" in agro
    assert "Técnico" not in emp
    ops_pages = next(pages for title, pages in navigation.NAV_SECTIONS if title == "Operaciones")
    assert ops_pages.index("Técnico") == ops_pages.index("Inventario") - 1


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


def test_nav_sections_cover_pages_exactly() -> None:
    flat = [p for _, pages in navigation.NAV_SECTIONS for p in pages]
    assert sorted(flat) == sorted(navigation.PAGES)
    assert len(flat) == len(set(flat))


def test_nav_sections_for_role_match_pages_for_role() -> None:
    for role in ("admin", "sales", "agro_team", "employee"):
        visible = [p for _, pages in navigation.nav_sections_for_role(role) for p in pages]
        assert sorted(visible) == sorted(navigation.pages_for_role(role))


def test_nav_sections_for_role_hides_empty_sections() -> None:
    sections = navigation.nav_sections_for_role("employee")
    assert all(pages for _, pages in sections)


def test_page_icons_and_descriptions_complete() -> None:
    for page in navigation.PAGES:
        assert navigation.PAGE_ICONS[page].startswith(":material/")
        assert navigation.PAGE_DESCRIPTIONS[page].strip()
