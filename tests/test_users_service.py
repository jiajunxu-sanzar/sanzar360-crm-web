from __future__ import annotations

from dataclasses import dataclass

from services.users_service import commercial_user_names, person_select_options


@dataclass(frozen=True)
class _User:
    nombre: str
    role: str


def test_commercial_user_names_includes_admin_agro_sales_excludes_employee() -> None:
    users = [
        _User("Ana Admin", "admin"),
        _User("Bob Agro", "agro_team"),
        _User("Carla Sales", "sales"),
        _User("Dan Emp", "employee"),
        _User("", "sales"),
    ]
    assert commercial_user_names(users) == ["Ana Admin", "Bob Agro", "Carla Sales"]


def test_person_select_options_blank_and_current_extra() -> None:
    users = [
        _User("Ana Admin", "admin"),
        _User("Dan Emp", "employee"),
    ]
    opts = person_select_options(users, current="Legacy Name", extra=["Otro Histórico"])
    assert opts[0] == ""
    assert "Ana Admin" in opts
    assert "Dan Emp" not in opts
    assert "Legacy Name" in opts
    assert "Otro Histórico" in opts


def test_person_select_options_without_blank() -> None:
    users = [_User("Ana Admin", "admin")]
    assert person_select_options(users, include_blank=False) == ["Ana Admin"]
