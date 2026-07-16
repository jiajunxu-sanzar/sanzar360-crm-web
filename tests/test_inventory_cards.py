"""Tests de las cards de inventario rediseñadas (plan visual 2.0)."""

from __future__ import annotations

from ui.components.inventory_cards import build_inventory_card_html, clean_serial


def test_clean_serial_strips_wrapping_quotes() -> None:
    assert clean_serial('"6126e47633682020"') == "6126e47633682020"
    assert clean_serial("'ABC-123'") == "ABC-123"
    assert clean_serial(' "X" ') == "X"
    assert clean_serial("sin comillas") == "sin comillas"
    assert clean_serial("") == ""


def _em500_row(**overrides: str) -> dict[str, str]:
    base = {
        "inventory_id": "46b49cae-1619-4a0f-8c65-ce0d059479b6",
        "model": "EM500",
        "serial_number": '"6126e47633682020"',
        "eui": "24E124126E476336",
        "associated_gateway_inventory_id": "c90bd3ab-9b3d-4a35-a3ac-3ad295242cb0",
        "logistics_status": "recibido",
        "location_type": "cliente",
        "location_contact_id": "c-1",
        "configured": "",
    }
    base.update(overrides)
    return base


def test_card_shows_serial_without_quotes_and_no_raw_uuid() -> None:
    html = build_inventory_card_html(_em500_row())
    assert "6126e47633682020" in html
    assert '"6126e47633682020"' not in html
    # El inventory_id crudo ya no se muestra en la card.
    assert "46b49cae-1619-4a0f-8c65-ce0d059479b6" not in html


def test_card_resolves_gateway_and_contact_names() -> None:
    html = build_inventory_card_html(
        _em500_row(),
        serial_by_id={"c90bd3ab-9b3d-4a35-a3ac-3ad295242cb0": '"GW-UG67-042"'},
        contact_name_by_id={"c-1": "Finca La Vega"},
    )
    assert "GW-UG67-042" in html                      # serial resuelto, sin comillas
    assert "c90bd3ab-9b3d-4a35-a3ac-3ad295242cb0" not in html
    assert "Finca La Vega" in html                    # ubicación con nombre de cliente
    assert "recibido" in html                         # pill de estado logístico


def test_card_unresolved_association_shows_shortened_id() -> None:
    html = build_inventory_card_html(_em500_row())
    assert "c90bd3ab…" in html


def test_card_configured_pill() -> None:
    html = build_inventory_card_html(_em500_row(configured="sí"))
    assert "Configurado" in html
