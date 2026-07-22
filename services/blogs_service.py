from __future__ import annotations

import json
import uuid
from datetime import date, datetime

import pandas as pd

from config.settings import (
    BLOG_EVENTO_ALARMA_SIN_SEMANA,
    BLOG_TIPO_REGISTRO_BLOG,
    BLOG_TIPO_REGISTRO_EVENTO,
    BLOG_TIPO_REGISTRO_NEWSLETTER,
    BLOGS_HEADERS,
    BLOGS_WORKSHEET_NAME,
)
from services.blogs_validation import filter_blog_rows, validate_blog_values, week_bounds, week_key
from services.sheets_service import SheetsService


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _event_notas(*, week: str, employee_id: str) -> str:
    return f"evento={BLOG_EVENTO_ALARMA_SIN_SEMANA};semana={week};employee_id={employee_id}"


class BlogsService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure(self) -> None:
        self._sheets.get_or_create_worksheet(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS))

    def blogs_df(self) -> pd.DataFrame:
        self.ensure_structure()
        return self._sheets.read_worksheet_df(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS))

    def all_rows(self) -> list[dict[str, str]]:
        df = self.blogs_df()
        if df.empty:
            return []
        return df.fillna("").astype(str).to_dict("records")

    def blog_rows(self) -> list[dict[str, str]]:
        return filter_blog_rows(self.all_rows())

    def upsert_blog(self, values: dict[str, str]) -> str:
        self.ensure_structure()
        row = {h: str(values.get(h, "") or "") for h in BLOGS_HEADERS}
        row["tipo_registro"] = BLOG_TIPO_REGISTRO_BLOG
        error = validate_blog_values(row)
        if error:
            raise ValueError(error)

        row_id = row.get("historial_blog_id", "").strip() or str(uuid.uuid4())
        row["historial_blog_id"] = row_id
        row_num = self._sheets.row_numbers_by_id(BLOGS_WORKSHEET_NAME, "historial_blog_id").get(row_id)
        if row_num is None:
            row["created_at"] = row.get("created_at") or _today()
        else:
            current_df = self.blogs_df()
            existing = current_df[current_df["historial_blog_id"].astype(str).str.strip() == row_id]
            existing_created = str(existing.iloc[0].get("created_at", "") or "").strip() if not existing.empty else ""
            row["created_at"] = row.get("created_at") or existing_created or _today()
        row["updated_at"] = _today()

        if row_num is None:
            self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        else:
            self._sheets.update_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row_num, row)
        return row_id

    def delete_blog_by_id(self, blog_id: str, df: pd.DataFrame | None = None) -> bool:
        self.ensure_structure()
        clean_id = str(blog_id or "").strip()
        if not clean_id:
            return False
        source = df if df is not None else self.blogs_df()
        if source.empty:
            return False
        ids = source.get("historial_blog_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        keep_mask = ids != clean_id
        removed = int((~keep_mask).sum())
        if removed == 0:
            return False
        kept = source[keep_mask].copy()
        self._sheets.write_worksheet_df(BLOGS_WORKSHEET_NAME, kept, list(BLOGS_HEADERS))
        return True

    def log_weekly_gap_dismiss(self, *, employee_id: str, actor_name: str, week_start: date | None = None) -> str:
        self.ensure_structure()
        ref = week_start or date.today()
        start, _ = week_bounds(ref)
        week = week_key(start)
        row_id = str(uuid.uuid4())
        today = _today()
        row = {h: "" for h in BLOGS_HEADERS}
        row.update(
            {
                "historial_blog_id": row_id,
                "tipo_registro": BLOG_TIPO_REGISTRO_EVENTO,
                "titulo": "Aviso semanal descartado",
                "fecha_publicacion_prevista": start.strftime("%d/%m/%Y"),
                "persona_publica": actor_name,
                "notas": _event_notas(week=week, employee_id=employee_id),
                "created_at": today,
                "updated_at": today,
            }
        )
        self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        return row_id

    # ------------------------------------------------------------------
    # Registro de envíos de newsletter (tipo_registro="newsletter")
    # ------------------------------------------------------------------

    def log_newsletter_send(
        self,
        *,
        titulo: str,
        texto: str,
        enviado_por: str,
        destinatarios: list[dict[str, str]],
        newsletter_id: str | None = None,
    ) -> str:
        """Registra un envío de newsletter como fila nueva en Blogs.

        ``destinatarios`` es una lista de ``{"contact_id", "nombre", "correo"}``
        de todos los contactos a los que se mandó (no incluye envíos de prueba).
        ``newsletter_id`` debe ser el mismo id ya usado para firmar los enlaces
        de baja incluidos en esos correos (se genera ANTES de enviar, para
        poder embeberlo en cada enlace); si no se pasa, se genera aquí.
        Devuelve el ``historial_blog_id`` usado como ``newsletter_id``.
        """
        self.ensure_structure()
        row_id = str(newsletter_id or "").strip() or str(uuid.uuid4())
        today = _today()
        row = {h: "" for h in BLOGS_HEADERS}
        row.update(
            {
                "historial_blog_id": row_id,
                "tipo_registro": BLOG_TIPO_REGISTRO_NEWSLETTER,
                "titulo": str(titulo or "").strip() or "Newsletter",
                "estado_blog": "Publicado",
                "fecha_publicacion_prevista": today,
                "fecha_publicacion_real": today,
                "persona_publica": enviado_por,
                "responsable_blog": enviado_por,
                "notas": str(texto or "").strip(),
                "newsletter_texto": str(texto or "").strip(),
                "newsletter_enviado_por": enviado_por,
                "newsletter_destinatarios_json": json.dumps(destinatarios, ensure_ascii=False),
                "newsletter_num_destinatarios": str(len(destinatarios)),
                "newsletter_fecha_envio": _now(),
                "newsletter_bajas_json": "[]",
                "created_at": today,
                "updated_at": today,
            }
        )
        self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        return row_id

    def newsletter_rows(self) -> list[dict[str, str]]:
        """Filas de Blogs con ``tipo_registro='newsletter'``, más recientes primero."""
        rows = [
            row
            for row in self.all_rows()
            if str(row.get("tipo_registro", "") or "").strip() == BLOG_TIPO_REGISTRO_NEWSLETTER
        ]
        rows.sort(key=lambda r: str(r.get("newsletter_fecha_envio", "") or ""), reverse=True)
        return rows

    def record_newsletter_unsubscribe(self, *, newsletter_id: str, contact_id: str, nombre: str) -> bool:
        """Añade una baja al registro de un envío de newsletter concreto.

        Se usa desde la página pública de baja (sin login). No falla el flujo de
        baja si el ``newsletter_id`` ya no existe en Blogs (p.ej. borrado a
        mano): en ese caso simplemente no hay nada que anotar aquí.
        """
        clean_id = str(newsletter_id or "").strip()
        if not clean_id:
            return False
        self.ensure_structure()
        row_nums = self._sheets.row_numbers_by_id(BLOGS_WORKSHEET_NAME, "historial_blog_id")
        row_num = row_nums.get(clean_id)
        if row_num is None:
            return False
        df = self.blogs_df()
        match = df[df["historial_blog_id"].astype(str).str.strip() == clean_id]
        if match.empty:
            return False
        current_row = match.iloc[0].to_dict()
        try:
            bajas = json.loads(current_row.get("newsletter_bajas_json", "") or "[]")
            if not isinstance(bajas, list):
                bajas = []
        except (TypeError, ValueError):
            bajas = []
        bajas.append({"contact_id": str(contact_id or ""), "nombre": str(nombre or ""), "fecha": _now()})
        updated_row = {h: str(current_row.get(h, "") or "") for h in BLOGS_HEADERS}
        updated_row["newsletter_bajas_json"] = json.dumps(bajas, ensure_ascii=False)
        updated_row["updated_at"] = _today()
        self._sheets.update_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row_num, updated_row)
        return True
