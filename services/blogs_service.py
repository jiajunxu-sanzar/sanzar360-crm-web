from __future__ import annotations

import json
import uuid
from datetime import date, datetime

import pandas as pd

from config.settings import (
    BLOG_EVENTO_ALARMA_SIN_NEWSLETTER_SEMANA,
    BLOG_TIPO_REGISTRO_BLOG,
    BLOG_TIPO_REGISTRO_EVENTO,
    BLOG_TIPO_REGISTRO_NEWSLETTER,
    BLOGS_HEADERS,
    BLOGS_WORKSHEET_NAME,
)
from services.blogs_validation import filter_blog_rows, validate_blog_values, week_bounds, week_key
from services.sheet_date_format import is_valid_dd_mm_yyyy
from services.sheets_service import SheetsService


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def _now() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _event_notas(*, week: str, employee_id: str) -> str:
    return (
        f"evento={BLOG_EVENTO_ALARMA_SIN_NEWSLETTER_SEMANA};"
        f"semana={week};employee_id={employee_id}"
    )


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
                "titulo": "Aviso semanal newsletter descartado",
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

    def create_newsletter_draft(
        self,
        *,
        titulo: str,
        persona_publica: str,
        link_borrador: str = "",
        estado_blog: str = "Borrador",
        fecha_publicacion_prevista: str = "",
        notas: str = "",
    ) -> str:
        """Crea una fila de newsletter en planning (sin envío real todavía)."""
        self.ensure_structure()
        clean_titulo = str(titulo or "").strip()
        if not clean_titulo:
            raise ValueError("El título de la newsletter es obligatorio.")
        estado = str(estado_blog or "").strip() or "Borrador"
        if estado not in {"Borrador", "Publicado"}:
            raise ValueError("El estado debe ser Borrador o Publicado.")
        prevista = str(fecha_publicacion_prevista or "").strip()
        if not prevista:
            raise ValueError("La fecha de publicación prevista es obligatoria.")
        if not is_valid_dd_mm_yyyy(prevista):
            raise ValueError("La fecha de publicación prevista debe estar en formato DD/MM/AAAA.")

        persona = str(persona_publica or "").strip()
        today = _today()
        row_id = str(uuid.uuid4())
        row = {h: "" for h in BLOGS_HEADERS}
        row.update(
            {
                "historial_blog_id": row_id,
                "tipo_registro": BLOG_TIPO_REGISTRO_NEWSLETTER,
                "titulo": clean_titulo,
                "estado_blog": estado,
                "fecha_publicacion_prevista": prevista,
                "fecha_publicacion_real": today if estado == "Publicado" else "",
                "persona_publica": persona,
                "responsable_blog": persona,
                "link_borrador": str(link_borrador or "").strip(),
                "notas": str(notas or "").strip(),
                "newsletter_enviado_por": persona,
                "newsletter_bajas_json": "[]",
                "boton_newsletter": "no",
                "imagen": "no",
                "created_at": today,
                "updated_at": today,
            }
        )
        self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        return row_id

    def newsletter_draft_rows(self) -> list[dict[str, str]]:
        """Newsletters en estado Borrador (candidatas a enviar desde Email)."""
        rows = [
            row
            for row in self.newsletter_rows()
            if str(row.get("estado_blog", "") or "").strip().lower() == "borrador"
        ]
        rows.sort(
            key=lambda r: (
                str(r.get("fecha_publicacion_prevista", "") or ""),
                str(r.get("titulo", "") or "").lower(),
            )
        )
        return rows

    def log_newsletter_send(
        self,
        *,
        titulo: str,
        texto: str,
        enviado_por: str,
        destinatarios: list[dict[str, str]],
        newsletter_id: str | None = None,
        asunto: str = "",
        cta_texto: str = "",
        cta_url: str = "",
        tiene_imagen: bool = False,
    ) -> str:
        """Registra un envío de newsletter: actualiza la fila si el id existe, si no append.

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
        cta_t = str(cta_texto or "").strip()
        cta_u = str(cta_url or "").strip()
        has_cta = bool(cta_t and cta_u)

        row_nums = self._sheets.row_numbers_by_id(BLOGS_WORKSHEET_NAME, "historial_blog_id")
        row_num = row_nums.get(row_id)
        existing: dict[str, str] = {}
        if row_num is not None:
            df = self.blogs_df()
            match = df[df["historial_blog_id"].astype(str).str.strip() == row_id]
            if not match.empty:
                existing = {h: str(match.iloc[0].get(h, "") or "") for h in BLOGS_HEADERS}
            else:
                row_num = None

        row = {h: "" for h in BLOGS_HEADERS}
        if existing:
            row.update(existing)

        row.update(
            {
                "historial_blog_id": row_id,
                "tipo_registro": BLOG_TIPO_REGISTRO_NEWSLETTER,
                "titulo": str(titulo or "").strip() or existing.get("titulo", "") or "Newsletter",
                "estado_blog": "Publicado",
                "fecha_publicacion_prevista": existing.get("fecha_publicacion_prevista", "") or today,
                "fecha_publicacion_real": today,
                "persona_publica": enviado_por or existing.get("persona_publica", ""),
                "responsable_blog": enviado_por or existing.get("responsable_blog", ""),
                "link_borrador": existing.get("link_borrador", ""),
                "notas": str(texto or "").strip() or existing.get("notas", ""),
                "newsletter_texto": str(texto or "").strip(),
                "newsletter_enviado_por": enviado_por,
                "newsletter_destinatarios_json": json.dumps(destinatarios, ensure_ascii=False),
                "newsletter_num_destinatarios": str(len(destinatarios)),
                "newsletter_fecha_envio": _now(),
                "newsletter_bajas_json": existing.get("newsletter_bajas_json", "") or "[]",
                "newsletter_asunto": str(asunto or "").strip(),
                "boton_newsletter": "sí" if has_cta else "no",
                "newsletter_cta_texto": cta_t if has_cta else "",
                "link_boton_newsletter": cta_u if has_cta else "",
                "imagen": "sí" if tiene_imagen else "no",
                "created_at": existing.get("created_at", "") or today,
                "updated_at": today,
            }
        )

        if row_num is None:
            self._sheets.append_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row)
        else:
            self._sheets.update_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row_num, row)
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

    def update_newsletter_publish_links(
        self,
        historial_blog_id: str,
        *,
        link_publicado: str,
        link_publicado_linkedin: str,
    ) -> bool:
        """Actualiza solo los links publicados de una fila newsletter."""
        clean_id = str(historial_blog_id or "").strip()
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
        current = match.iloc[0].to_dict()
        if str(current.get("tipo_registro", "") or "").strip() != BLOG_TIPO_REGISTRO_NEWSLETTER:
            raise ValueError("La fila no es una newsletter.")
        updated_row = {h: str(current.get(h, "") or "") for h in BLOGS_HEADERS}
        updated_row["link_publicado"] = str(link_publicado or "").strip()
        updated_row["link_publicado_linkedin"] = str(link_publicado_linkedin or "").strip()
        updated_row["updated_at"] = _today()
        self._sheets.update_worksheet_row(BLOGS_WORKSHEET_NAME, list(BLOGS_HEADERS), row_num, updated_row)
        return True
