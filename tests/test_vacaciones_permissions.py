"""Permisos de la página Vacaciones."""
from __future__ import annotations

from app.navigation import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_SALES
from pages.vacaciones import can_manage_vacaciones


def test_can_manage_vacaciones_only_admin() -> None:
    assert can_manage_vacaciones(ROLE_ADMIN) is True
    assert can_manage_vacaciones(" ADMIN ") is True
    assert can_manage_vacaciones(ROLE_SALES) is False
    assert can_manage_vacaciones(ROLE_EMPLOYEE) is False
    assert can_manage_vacaciones("") is False
