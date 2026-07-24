"""Historial de umbrales y razón textura en campañas."""
from __future__ import annotations

import json

from services.history_service import (
    CAMPANAS_FORM_FIELD_ORDER,
    HISTORY_SPECS,
    merge_historial_umbrales,
    parse_historial_umbrales,
    serialize_historial_umbrales,
    summarize_historial_umbrales,
    umbrales_draft_is_empty,
)


def test_campanas_spec_has_new_columns_at_end() -> None:
    headers = list(HISTORY_SPECS["campanas"].headers)
    assert list(headers[-2:]) == ["razon_textura_suelo", "historial_umbrales_json"]
    assert "coordenadas_parcela" not in headers


def test_campanas_form_field_order_puts_detalles_last_after_sensor() -> None:
    order = list(CAMPANAS_FORM_FIELD_ORDER)
    assert order[-1] == "detalles"
    assert order.index("historial_sensor_id") < order.index("detalles")
    assert order.index("longitud") < order.index("detalles")
    assert order.index("razon_textura_suelo") == order.index("textura_suelo") + 1
    assert "historial_umbrales_json" not in order  # sección dedicada, no text_input


def test_parse_serialize_historial_umbrales_roundtrip() -> None:
    raw = json.dumps(
        [
            {
                "fecha_actualizacion": "01/03/2026",
                "umbral_superior": "32.5",
                "umbral_inferior": "18",
                "razon": "Visita",
            }
        ],
        ensure_ascii=False,
    )
    parsed = parse_historial_umbrales(raw)
    assert len(parsed) == 1
    assert parsed[0]["umbral_superior"] == "32.5"
    assert serialize_historial_umbrales(parsed) == (
        '[{"fecha_actualizacion":"01/03/2026","umbral_superior":"32.5",'
        '"umbral_inferior":"18","razon":"Visita"}]'
    )


def test_parse_historial_umbrales_bad_json_returns_empty() -> None:
    assert parse_historial_umbrales("not-json") == []
    assert parse_historial_umbrales("") == []
    assert parse_historial_umbrales("{}") == []


def test_merge_add_appends_and_empty_draft_keeps_list() -> None:
    base = serialize_historial_umbrales(
        [
            {
                "fecha_actualizacion": "01/01/2026",
                "umbral_superior": "30",
                "umbral_inferior": "15",
                "razon": "inicial",
            }
        ]
    )
    added, err = merge_historial_umbrales(
        base,
        mode="add",
        fecha_actualizacion="15/02/2026",
        umbral_superior="31,5",
        umbral_inferior="16",
        razon="ajuste",
    )
    assert err is None
    entries = parse_historial_umbrales(added)
    assert len(entries) == 2
    assert entries[-1]["umbral_superior"] == "31,5"
    assert entries[-1]["razon"] == "ajuste"

    same, err2 = merge_historial_umbrales(
        added,
        mode="add",
        fecha_actualizacion="22/07/2026",
        umbral_superior="",
        umbral_inferior="",
        razon="",
    )
    assert err2 is None
    assert parse_historial_umbrales(same) == entries


def test_merge_edit_last_replaces_only_last() -> None:
    base = serialize_historial_umbrales(
        [
            {
                "fecha_actualizacion": "01/01/2026",
                "umbral_superior": "30",
                "umbral_inferior": "15",
                "razon": "a",
            },
            {
                "fecha_actualizacion": "10/01/2026",
                "umbral_superior": "31",
                "umbral_inferior": "16",
                "razon": "b",
            },
        ]
    )
    out, err = merge_historial_umbrales(
        base,
        mode="edit_last",
        fecha_actualizacion="11/01/2026",
        umbral_superior="32",
        umbral_inferior="17",
        razon="b-edit",
    )
    assert err is None
    entries = parse_historial_umbrales(out)
    assert len(entries) == 2
    assert entries[0]["razon"] == "a"
    assert entries[1]["razon"] == "b-edit"
    assert entries[1]["fecha_actualizacion"] == "11/01/2026"


def test_merge_validates_partial_draft() -> None:
    _, err = merge_historial_umbrales(
        "",
        mode="add",
        fecha_actualizacion="01/01/2026",
        umbral_superior="30",
        umbral_inferior="",
        razon="x",
    )
    assert err is not None
    assert "inferior" in err.lower()


def test_umbrales_draft_is_empty_ignores_fecha() -> None:
    assert umbrales_draft_is_empty(umbral_superior="", umbral_inferior="", razon="")
    assert not umbrales_draft_is_empty(umbral_superior="1", umbral_inferior="", razon="")


def test_summarize_historial_umbrales() -> None:
    raw = serialize_historial_umbrales(
        [
            {
                "fecha_actualizacion": "01/01/2026",
                "umbral_superior": "30",
                "umbral_inferior": "15",
                "razon": "a",
            },
            {
                "fecha_actualizacion": "02/01/2026",
                "umbral_superior": "32",
                "umbral_inferior": "16",
                "razon": "b",
            },
        ]
    )
    assert summarize_historial_umbrales(raw) == "2 · 32/16"
    assert summarize_historial_umbrales("") == ""
