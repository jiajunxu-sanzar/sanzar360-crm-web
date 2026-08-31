"""Permisos y navegacion de la pagina Asistencia."""
from __future__ import annotations

from app import navigation
from app.navigation import ROLE_ADMIN, ROLE_AGRO_TEAM, ROLE_EMPLOYEE, ROLE_SALES
from pages.asistencia import can_manage_asistencia


def test_only_admin_can_manage_asistencia() -> None:
    assert can_manage_asistencia(ROLE_ADMIN) is True
    assert can_manage_asistencia(" ADMIN ") is True
    assert can_manage_asistencia(ROLE_AGRO_TEAM) is False
    assert can_manage_asistencia(ROLE_SALES) is False
    assert can_manage_asistencia(ROLE_EMPLOYEE) is False
    assert can_manage_asistencia("") is False


def test_asistencia_visible_for_every_role() -> None:
    for role in (ROLE_ADMIN, ROLE_AGRO_TEAM, ROLE_SALES, ROLE_EMPLOYEE):
        assert "Asistencia" in navigation.pages_for_role(role)


def test_asistencia_sits_right_below_vacaciones_in_the_team_section() -> None:
    equipo = next(pages for title, pages in navigation.NAV_SECTIONS if title == "Equipo")
    assert equipo.index("Asistencia") == equipo.index("Vacaciones") + 1
    assert navigation.PAGES.index("Asistencia") == navigation.PAGES.index("Vacaciones") + 1
