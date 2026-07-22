from __future__ import annotations

import json

import pandas as pd

from config.settings import BLOGS_HEADERS, BLOGS_WORKSHEET_NAME
from services.blogs_service import BlogsService


class FakeSheets:
    """Doble mínimo de ``SheetsService`` para las hojas usadas por BlogsService."""

    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {
            BLOGS_WORKSHEET_NAME: pd.DataFrame(columns=list(BLOGS_HEADERS)),
        }

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
        out: dict[str, int] = {}
        for i, row in df.iterrows():
            value = str(row.get(id_header, "")).strip()
            if value:
                out[value] = i + 2
        return out

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, str]) -> None:
        self.frames[name] = pd.concat(
            [self.frames[name], pd.DataFrame([{h: str(row.get(h, "") or "") for h in headers}])],
            ignore_index=True,
        )

    def update_worksheet_row(self, name: str, headers: list[str], row_num: int, row: dict[str, str]) -> None:
        idx = max(0, row_num - 2)
        df = self.frames[name].copy()
        for h in headers:
            df.at[idx, h] = str(row.get(h, "") or "")
        self.frames[name] = df

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        self.frames[name] = df[headers].fillna("").astype(str).copy()


def test_log_newsletter_send_writes_row_with_recipients() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    destinatarios = [
        {"contact_id": "c1", "nombre": "Ana", "correo": "ana@x.com"},
        {"contact_id": "c2", "nombre": "Bea", "correo": "bea@x.com"},
    ]

    newsletter_id = svc.log_newsletter_send(
        titulo="Un verano sobre ruedas",
        texto="Cuerpo de la newsletter",
        enviado_por="Jiajun Xu",
        destinatarios=destinatarios,
        newsletter_id="nl-123",
        asunto="Asunto SMTP verano",
        cta_texto="Ver más",
        cta_url="https://sanzar-group.com/promo",
        tiene_imagen=True,
    )

    assert newsletter_id == "nl-123"
    df = svc.blogs_df()
    assert len(df) == 1
    row = df.iloc[0].to_dict()
    assert row["tipo_registro"] == "newsletter"
    assert row["historial_blog_id"] == "nl-123"
    assert row["titulo"] == "Un verano sobre ruedas"
    assert row["newsletter_asunto"] == "Asunto SMTP verano"
    assert row["boton_newsletter"] == "sí"
    assert row["newsletter_cta_texto"] == "Ver más"
    assert row["link_boton_newsletter"] == "https://sanzar-group.com/promo"
    assert row["imagen"] == "sí"
    assert row["newsletter_enviado_por"] == "Jiajun Xu"
    assert row["newsletter_num_destinatarios"] == "2"
    assert json.loads(row["newsletter_destinatarios_json"]) == destinatarios
    assert json.loads(row["newsletter_bajas_json"]) == []
    # Una newsletter no debe aparecer en el listado editorial puro de blogs.
    from services.blogs_validation import filter_blog_and_newsletter_rows, filter_blog_rows

    records = df.fillna("").astype(str).to_dict("records")
    assert filter_blog_rows(records) == []
    assert len(filter_blog_and_newsletter_rows(records)) == 1


def test_create_newsletter_draft_and_list_borrador_only() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    draft_id = svc.create_newsletter_draft(
        titulo="Planning verano",
        persona_publica="Jiajun Xu",
        link_borrador="https://docs.google.com/draft",
        estado_blog="Borrador",
        fecha_publicacion_prevista="25/07/2026",
        notas="idea inicial",
    )
    svc.create_newsletter_draft(
        titulo="Ya publicada en planning",
        persona_publica="Ana",
        estado_blog="Publicado",
        fecha_publicacion_prevista="20/07/2026",
    )
    svc.log_newsletter_send(
        titulo="Enviada suelta",
        texto="x",
        enviado_por="A",
        destinatarios=[],
        newsletter_id="sent-1",
    )

    df = svc.blogs_df()
    draft = df[df["historial_blog_id"] == draft_id].iloc[0].to_dict()
    assert draft["tipo_registro"] == "newsletter"
    assert draft["estado_blog"] == "Borrador"
    assert draft["titulo"] == "Planning verano"
    assert draft["link_borrador"] == "https://docs.google.com/draft"
    assert draft["persona_publica"] == "Jiajun Xu"
    assert draft["newsletter_enviado_por"] == "Jiajun Xu"
    assert draft["newsletter_texto"] == ""
    assert draft["newsletter_num_destinatarios"] in {"", "0"} or draft["newsletter_num_destinatarios"] == ""

    drafts = svc.newsletter_draft_rows()
    assert {r["historial_blog_id"] for r in drafts} == {draft_id}
    assert all(r["estado_blog"] == "Borrador" for r in drafts)


def test_log_newsletter_send_updates_existing_draft_row() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    draft_id = svc.create_newsletter_draft(
        titulo="Planning",
        persona_publica="Jiajun Xu",
        link_borrador="https://draft.example",
        estado_blog="Borrador",
        fecha_publicacion_prevista="28/07/2026",
        notas="nota planning",
    )
    assert len(svc.blogs_df()) == 1

    returned = svc.log_newsletter_send(
        titulo="Titulo final",
        texto="Cuerpo enviado",
        enviado_por="Jiajun Xu",
        destinatarios=[{"contact_id": "c1", "nombre": "Ana", "correo": "a@x.com"}],
        newsletter_id=draft_id,
        asunto="Asunto final",
        cta_texto="Ver",
        cta_url="https://sanzar-group.com",
        tiene_imagen=True,
    )
    assert returned == draft_id
    df = svc.blogs_df()
    assert len(df) == 1
    row = df.iloc[0].to_dict()
    assert row["estado_blog"] == "Publicado"
    assert row["titulo"] == "Titulo final"
    assert row["newsletter_asunto"] == "Asunto final"
    assert row["newsletter_texto"] == "Cuerpo enviado"
    assert row["link_borrador"] == "https://draft.example"
    assert row["fecha_publicacion_prevista"] == "28/07/2026"
    assert row["boton_newsletter"] == "sí"
    assert row["imagen"] == "sí"
    assert row["newsletter_num_destinatarios"] == "1"
    assert svc.newsletter_draft_rows() == []


def test_log_newsletter_send_appends_when_id_unknown() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    svc.create_newsletter_draft(
        titulo="Otro",
        persona_publica="A",
        estado_blog="Borrador",
        fecha_publicacion_prevista="01/08/2026",
    )
    svc.log_newsletter_send(
        titulo="Nueva",
        texto="P",
        enviado_por="A",
        destinatarios=[],
        newsletter_id="brand-new-id",
    )
    assert len(svc.blogs_df()) == 2


def test_log_newsletter_send_without_cta_or_image_flags_no() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    svc.log_newsletter_send(
        titulo="T",
        texto="P",
        enviado_por="Ana",
        destinatarios=[],
        newsletter_id="nl-no-cta",
        asunto="Asunto",
        cta_texto="Ver",
        cta_url="",
        tiene_imagen=False,
    )
    row = svc.blogs_df().iloc[0].to_dict()
    assert row["boton_newsletter"] == "no"
    assert row["newsletter_cta_texto"] == ""
    assert row["link_boton_newsletter"] == ""
    assert row["imagen"] == "no"
    assert row["newsletter_asunto"] == "Asunto"


def test_log_newsletter_send_generates_id_when_not_given() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    newsletter_id = svc.log_newsletter_send(
        titulo="T", texto="P", enviado_por="Ana", destinatarios=[]
    )
    assert newsletter_id  # non-empty uuid string
    assert svc.blogs_df().iloc[0]["historial_blog_id"] == newsletter_id


def test_newsletter_rows_excludes_blogs_and_events_sorted_by_date_desc() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    svc.log_newsletter_send(titulo="Primera", texto="", enviado_por="A", destinatarios=[], newsletter_id="n1")
    svc.log_newsletter_send(titulo="Segunda", texto="", enviado_por="A", destinatarios=[], newsletter_id="n2")
    svc.upsert_blog(
        {
            "titulo": "Blog normal",
            "estado_blog": "Borrador",
            "fecha_publicacion_prevista": "20/07/2026",
        }
    )

    rows = svc.newsletter_rows()
    assert {r["historial_blog_id"] for r in rows} == {"n1", "n2"}
    assert all(r["tipo_registro"] == "newsletter" for r in rows)


def test_record_newsletter_unsubscribe_appends_to_bajas_json() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    svc.log_newsletter_send(
        titulo="T", texto="P", enviado_por="A", destinatarios=[], newsletter_id="n1"
    )

    ok = svc.record_newsletter_unsubscribe(newsletter_id="n1", contact_id="c1", nombre="Ana")
    assert ok is True

    row = svc.blogs_df().iloc[0].to_dict()
    bajas = json.loads(row["newsletter_bajas_json"])
    assert len(bajas) == 1
    assert bajas[0]["contact_id"] == "c1"
    assert bajas[0]["nombre"] == "Ana"

    # Una segunda baja del mismo envío se acumula, no sobrescribe.
    svc.record_newsletter_unsubscribe(newsletter_id="n1", contact_id="c2", nombre="Bea")
    row2 = svc.blogs_df().iloc[0].to_dict()
    bajas2 = json.loads(row2["newsletter_bajas_json"])
    assert len(bajas2) == 2


def test_record_newsletter_unsubscribe_unknown_newsletter_id_returns_false() -> None:
    sheets = FakeSheets()
    svc = BlogsService(sheets)
    assert svc.record_newsletter_unsubscribe(newsletter_id="no-existe", contact_id="c1", nombre="Ana") is False
