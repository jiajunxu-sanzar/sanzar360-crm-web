from ui.components.dashboard_cards import (
    _funnel_display_order,
    build_funnel_card_html,
    build_ranked_bar_card_html,
    rank_fill_width,
)


def test_rank_fill_width() -> None:
    assert rank_fill_width(10, 10) == 100.0
    assert rank_fill_width(5, 10) == 50.0
    assert rank_fill_width(0, 10) == 0.0
    assert rank_fill_width(5, 0) == 0.0


def test_build_funnel_card_html_contains_estado_and_pct() -> None:
    html = build_funnel_card_html("Cliente", 3, 10)
    assert "Cliente" in html
    assert "30.0%" in html
    assert "sanzar-dash-funnel-card" in html


def test_build_ranked_bar_card_html() -> None:
    html = build_ranked_bar_card_html("Almería", 8, 10)
    assert "Almería" in html
    assert "80.0%" in html or 'width:80.0%' in html
    assert "sanzar-dash-rank-card" in html


def test_funnel_display_order_follows_contact_estado_order() -> None:
    funnel = {
        "Cliente": 5,
        "Nuevo contacto": 2,
        "Contacto inicial": 3,
        "En Contacto": 1,
    }
    ordered = _funnel_display_order(funnel)
    labels = [label for label, _count in ordered]
    assert labels.index("Nuevo contacto") < labels.index("Contacto inicial")
    assert labels.index("Contacto inicial") < labels.index("Cliente")
    assert sum(count for _label, count in ordered) == 11
