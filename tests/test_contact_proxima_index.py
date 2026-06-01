from datetime import date, timedelta

import pandas as pd

from services.contact_proxima_index import (
    build_contact_proxima_action_index,
    enrich_contacts_with_proxima,
    latest_commercial_contact_row,
    sort_commercial_rows_by_contact_date,
)


def test_index_picks_latest_contact_row_with_proxima() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": yesterday.strftime("%d/%m/%Y"),
                "hora_contacto": "10:00",
                "proxima_accion_fecha": "01/01/2099",
                "proxima_accion_persona": "Ana",
                "proxima_accion_detalle": "vieja",
                "proxima_accion_canal": "email",
            },
            {
                "contact_id": "c1",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "11:00",
                "proxima_accion_fecha": today.strftime("%d/%m/%Y"),
                "proxima_accion_persona": "Betty",
                "proxima_accion_detalle": "nueva",
                "proxima_accion_canal": "llamada",
            },
        ]
    )
    idx = build_contact_proxima_action_index(acciones)
    assert len(idx) == 1
    row = idx.iloc[0]
    assert row["proxima_accion_detalle"] == "nueva"
    assert row["persona_proxima_accion"] == "Betty"


def test_enrich_drops_legacy_columns_and_merges() -> None:
    contacts = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "nombre": "Cliente",
                "proxima_accion_fecha": "01/01/2000",
                "fecha_veces_sin_respuesta": "x",
            }
        ]
    )
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": date.today().strftime("%d/%m/%Y"),
                "hora_contacto": "",
                "proxima_accion_fecha": date.today().strftime("%d/%m/%Y"),
                "proxima_accion_persona": "David Ortiz",
                "proxima_accion_detalle": "Llamar",
                "proxima_accion_canal": "llamada",
            }
        ]
    )
    out = enrich_contacts_with_proxima(contacts, acciones)
    assert "fecha_veces_sin_respuesta" not in out.columns
    assert out.iloc[0]["proxima_accion_detalle"] == "Llamar"


def test_latest_commercial_contact_row_picks_newest_by_datetime() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": yesterday.strftime("%d/%m/%Y"),
                "hora_contacto": "15:00",
                "resultado_contacto": "fallido",
                "persona_contacto": "Ana",
            },
            {
                "contact_id": "c1",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "09:00",
                "resultado_contacto": "exitoso",
                "persona_contacto": "Betty",
            },
            {
                "contact_id": "c2",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "12:00",
                "resultado_contacto": "exitoso",
            },
        ]
    )
    row = latest_commercial_contact_row(acciones, "c1")
    assert row is not None
    assert row["resultado_contacto"] == "exitoso"
    assert row["persona_contacto"] == "Betty"
    assert latest_commercial_contact_row(acciones, "missing") is None


def test_sort_commercial_rows_newest_first() -> None:
    rows = [
        {"fecha_contacto": "01/01/2026", "hora_contacto": "10:00", "notas_contacto": "old"},
        {"fecha_contacto": "02/01/2026", "hora_contacto": "09:00", "notas_contacto": "new"},
    ]
    sorted_rows = sort_commercial_rows_by_contact_date(rows)
    assert sorted_rows[0]["notas_contacto"] == "new"


def test_strict_index_ignores_proxima_on_older_row_if_latest_empty() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": yesterday.strftime("%d/%m/%Y"),
                "hora_contacto": "10:00",
                "proxima_accion_fecha": "01/01/2099",
                "proxima_accion_persona": "Ana",
            },
            {
                "contact_id": "c1",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "11:00",
                "proxima_accion_fecha": "",
                "proxima_accion_persona": "",
            },
        ]
    )
    idx = build_contact_proxima_action_index(acciones)
    assert idx.empty


def test_index_normalizes_iso_proxima_fecha_on_latest_row() -> None:
    today = date.today()
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "09:00",
                "proxima_accion_fecha": today.strftime("%Y-%m-%d"),
                "proxima_accion_persona": "David Ortiz",
                "proxima_accion_detalle": "Llamar",
                "proxima_accion_canal": "llamada",
            }
        ]
    )
    idx = build_contact_proxima_action_index(acciones)
    assert len(idx) == 1
    assert idx.iloc[0]["proxima_accion_fecha"] == today.strftime("%d/%m/%Y")
