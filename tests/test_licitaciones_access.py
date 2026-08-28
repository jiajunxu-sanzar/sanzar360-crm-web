import pytest

from pages.licitaciones import can_use_licitaciones


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("admin", True),
        (" ADMIN ", True),
        ("agro_team", False),
        ("sales", False),
        ("employee", False),
        ("", False),
        ("unknown_role", False),
    ],
)
def test_can_use_licitaciones(role: str, expected: bool) -> None:
    assert can_use_licitaciones(role) is expected
