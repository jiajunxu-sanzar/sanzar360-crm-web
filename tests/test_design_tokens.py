from __future__ import annotations

import ui.design_tokens as design_tokens
from ui.design_tokens import (
    color,
    component,
    css_variables,
    load_design_tokens,
    mix_hex,
    pastel_triplet,
    reset_cache,
)
from ui.palette import (
    ACCENT_BUCKET_FUTURE,
    ACCENT_BUCKET_PAST,
    ACCENT_BUCKET_TODAY,
    STATUS_SUCCESS,
    contact_status_style,
    dash_bucket_button_style,
)


def setup_function() -> None:
    reset_cache()


def test_load_merges_cal_and_sanzar_colors() -> None:
    tokens = load_design_tokens()
    colors = tokens["colors"]
    assert colors["canvas"] == "#ffffff"
    assert colors["brand-accent"] == "#2D6A4F"
    assert colors["semantic-success"] == "#4CAF78"
    assert colors["bucket-future"] == "#6EB5E0"


def test_component_refs_resolve() -> None:
    btn = component("button-primary")
    assert btn["backgroundColor"] == "#2D6A4F"
    assert btn["textColor"] == "#FFFFFF"
    strong = component("button-primary-strong")
    assert strong["backgroundColor"] == "#111111"


def test_color_default_fallback() -> None:
    assert color("nonexistent-token", default="#abcdef") == "#abcdef"


def test_css_variables_include_brand_and_buckets() -> None:
    css = css_variables()
    assert "--ui-accent: #2D6A4F;" in css
    assert "--ui-bucket-past: #B0B8C1;" in css
    assert "--ui-bucket-today: #2D6A4F;" in css
    assert "--ui-bucket-future: #6EB5E0;" in css
    assert "--ui-primary-strong: #111111;" in css


def test_pastel_triplet_and_mix_hex() -> None:
    bg, border, fg = pastel_triplet("#4CAF78")
    assert fg == "#4CAF78"
    assert bg.startswith("#")
    assert border.startswith("#")
    mixed = mix_hex("#ffffff", "#000000", 0.5)
    assert mixed in {"#808080", "#7f7f7f"}


def test_palette_uses_design_tokens() -> None:
    assert ACCENT_BUCKET_PAST == "#B0B8C1"
    assert ACCENT_BUCKET_TODAY == "#2D6A4F"
    assert ACCENT_BUCKET_FUTURE == "#6EB5E0"
    assert contact_status_style("Cliente") == STATUS_SUCCESS
    _, _, _, left = dash_bucket_button_style("future", "future")
    assert left == "3px solid #6EB5E0"
    _, _, _, tomorrow_left = dash_bucket_button_style("tomorrow", "tomorrow")
    assert tomorrow_left == "3px solid #6EB5E0"


def test_cache_reset_reloads() -> None:
    first = load_design_tokens()
    reset_cache()
    second = load_design_tokens()
    assert first is not second
    assert first["colors"]["brand-accent"] == second["colors"]["brand-accent"]
