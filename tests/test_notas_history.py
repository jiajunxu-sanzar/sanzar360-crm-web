from __future__ import annotations

from datetime import date

import pandas as pd

from config.settings import ESTADO_NOTA_OPCIONES, TIPO_NOTA_OPCIONES
from pages.contacts_common import (
    filter_util_notas,
    is_nota_util,
    _apply_smart_defaults,
    _history_smart_defaults,
)
from services.history_service import HISTORY_SPECS, HistoryService
from services.notas_validation import validate_nota_history_values


def test_notas_spec_registered() -> None:
    spec = HISTORY_SPECS["notas"]
    assert spec.worksheet_name == "HistoricoNotas"
    assert spec.id_column == "historial_nota_id"
    assert spec.date_column == "fecha_update"
    assert "estado_nota" in spec.headers
    assert "titulo" in spec.headers
    assert "notas" in spec.headers


def test_tipo_y_estado_opciones() -> None:
    assert "Riego" in TIPO_NOTA_OPCIONES
    assert "Fertilización" in TIPO_NOTA_OPCIONES
    assert "Trabajo en campo" in TIPO_NOTA_OPCIONES
    assert "General" in TIPO_NOTA_OPCIONES
    assert ESTADO_NOTA_OPCIONES == ("Útil", "Obsoleta")


def test_is_nota_util_and_filter() -> None:
    assert is_nota_util("Útil") is True
    assert is_nota_util("") is True
    assert is_nota_util("Obsoleta") is False
    rows = [
        {"historial_nota_id": "1", "estado_nota": "Útil"},
        {"historial_nota_id": "2", "estado_nota": "Obsoleta"},
        {"historial_nota_id": "3", "estado_nota": ""},
    ]
    filtered = filter_util_notas(rows)
    assert [r["historial_nota_id"] for r in filtered] == ["1", "3"]


def test_validate_notas_requires_titulo_y_notas() -> None:
    base = {
        "titulo": "",
        "notas": "texto",
        "tipo_nota": "Riego",
        "estado_nota": "Útil",
        "fecha_creacion": "17/07/2026",
        "fecha_update": "17/07/2026",
    }
    assert validate_nota_history_values(base) is not None
    base["titulo"] = "Titulo"
    base["notas"] = ""
    assert validate_nota_history_values(base) is not None
    base["notas"] = "cuerpo"
    base["tipo_nota"] = ""
    assert validate_nota_history_values(base) is not None
    base["tipo_nota"] = "Riego"
    assert validate_nota_history_values(base) is None


class _FakeSheets:
    def __init__(self) -> None:
        headers = list(HISTORY_SPECS["notas"].headers)
        self.frames = {"HistoricoNotas": pd.DataFrame(columns=headers)}

    def get_or_create_worksheet(self, name: str, headers: list[str]) -> None:
        if name not in self.frames:
            self.frames[name] = pd.DataFrame(columns=headers)

    def read_worksheet_df(self, name: str, headers: list[str]) -> pd.DataFrame:
        df = self.frames.get(name, pd.DataFrame(columns=headers)).copy()
        for h in headers:
            if h not in df.columns:
                df[h] = ""
        return df[headers].fillna("").astype(str)

    def row_numbers_by_id(self, name: str, id_header: str) -> dict[str, int]:
        df = self.frames[name].fillna("").astype(str)
        return {
            str(row[id_header]).strip(): i + 2
            for i, row in df.iterrows()
            if str(row.get(id_header, "")).strip()
        }


def test_rows_for_contact_sorted_by_fecha_update_desc() -> None:
    sheets = _FakeSheets()
    headers = list(HISTORY_SPECS["notas"].headers)
    sheets.frames["HistoricoNotas"] = pd.DataFrame(
        [
            {
                **{h: "" for h in headers},
                "historial_nota_id": "a",
                "contact_id": "c1",
                "titulo": "vieja",
                "fecha_update": "10/07/2026",
                "estado_nota": "Útil",
            },
            {
                **{h: "" for h in headers},
                "historial_nota_id": "b",
                "contact_id": "c1",
                "titulo": "nueva",
                "fecha_update": "17/07/2026",
                "estado_nota": "Útil",
            },
            {
                **{h: "" for h in headers},
                "historial_nota_id": "c",
                "contact_id": "c1",
                "titulo": "media",
                "fecha_update": "15/07/2026",
                "estado_nota": "Obsoleta",
            },
        ]
    )
    svc = HistoryService(sheets)  # type: ignore[arg-type]
    svc.load_kind("notas", force=True)
    rows = svc.rows_for_contact("notas", "c1")
    assert [r["historial_nota_id"] for r in rows] == ["b", "c", "a"]


def test_notas_smart_defaults_new_and_edit(monkeypatch) -> None:
    today = date.today().strftime("%d/%m/%Y")
    monkeypatch.setattr("pages.contacts_common._actor_name", lambda: "David Ortiz")
    monkeypatch.setattr(
        "pages.contacts_common.commercial_user_names",
        lambda users: ["David Ortiz", "Ana"],
    )
    monkeypatch.setattr("pages.contacts_common.load_users_cached", lambda version=0: [])
    defaults = _history_smart_defaults("notas")
    assert defaults["fecha_creacion"] == today
    assert defaults["fecha_update"] == today
    assert defaults["estado_nota"] == "Útil"
    assert defaults["persona_nota"] == "David Ortiz"

    edited = _apply_smart_defaults(
        "notas",
        {"fecha_creacion": "01/01/2025", "fecha_update": "01/01/2025", "titulo": "x"},
        is_new=False,
    )
    assert edited["fecha_creacion"] == "01/01/2025"
    assert edited["fecha_update"] == today
