"""Export inventory association map to PDF (roots UC501/UG67 + standalone assets)."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from io import BytesIO

import pandas as pd

from config.settings import INVENTORY_HEADERS
from services.inventory_service import normalize_model_name
from ui.components.sn_association_viewer import (
    AssociationGroup,
    IntegrityConflict,
    build_inventory_association_map,
)


def _root_and_child_ids(groups: Iterable[AssociationGroup]) -> tuple[set[str], set[str]]:
    root_ids: set[str] = set()
    child_ids: set[str] = set()
    for g in groups:
        rid = (g.inventory_id or "").strip()
        if rid:
            root_ids.add(rid)
        for c in g.children:
            cid = (c.inventory_id or "").strip()
            if cid:
                child_ids.add(cid)
    return root_ids, child_ids


def _association_note_for_individual(row: dict[str, str]) -> str:
    model = normalize_model_name(str(row.get("model", "") or ""))
    sim = str(row.get("associated_sim_inventory_id", "") or "").strip()
    probe = str(row.get("associated_probe_inventory_id", "") or "").strip()
    gateway = str(row.get("associated_gateway_inventory_id", "") or "").strip()

    if model == "em500" and not gateway:
        return "Sin gateway UG67"
    if model in {"uc512", "em300"} and not gateway:
        return "Sin gateway UG67"
    if model == "uc501" and not sim and not probe:
        return "Sin SIM ni sonda enlazadas"
    if model == "ug67" and not sim:
        return "Sin SIM enlazada"
    if sim or probe or gateway:
        return "Enlaces no mostrados como hijo en mapa (revisar datos)"
    return "Sin asociados"


def collect_individual_inventory_rows(
    inv_df: pd.DataFrame,
    groups: list[AssociationGroup],
) -> list[dict[str, str]]:
    if inv_df.empty:
        return []
    root_ids, child_ids = _root_and_child_ids(groups)
    df = inv_df.fillna("").astype(str)
    out: list[dict[str, str]] = []
    for _, row in df.iterrows():
        iid = str(row.get("inventory_id", "") or "").strip()
        if not iid:
            continue
        if iid in root_ids or iid in child_ids:
            continue
        record = {h: str(row.get(h, "") or "") for h in INVENTORY_HEADERS}
        out.append(record)
    # Stable sort: model, serial
    out.sort(
        key=lambda r: (
            normalize_model_name(str(r.get("model", "") or "")),
            str(r.get("serial_number", "") or "").lower(),
        )
    )
    return out


def _escape_xml(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _role_label(role: str) -> str:
    role = (role or "").strip().lower()
    if role == "uc501":
        return "UC501"
    if role == "ug67":
        return "UG67"
    return role.upper()


def _child_role_label(role: str) -> str:
    mapping = {"sim": "SIM", "probe": "Sonda", "sensor": "Sensor"}
    return mapping.get((role or "").strip().lower(), role or "?")


def build_association_map_pdf_bytes(inv_df: pd.DataFrame, *, exported_at: datetime | None = None) -> tuple[bytes, str]:
    """Return (pdf_bytes, suggested_filename_without_path)."""
    now = exported_at or datetime.now()
    filename = f"inventario_mapa_asociacion_{now.strftime('%Y%m%d_%H%M')}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ModuleNotFoundError:
        minimal = (
            "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            "3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\n"
            "trailer<</Root 1 0 R>>\n%%EOF\n"
        )
        return minimal.encode("latin-1"), filename

    groups, conflicts = build_inventory_association_map(inv_df)
    individuals = collect_individual_inventory_rows(inv_df, groups)
    total_assets = len(inv_df) if inv_df is not None and not inv_df.empty else 0

    buf = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="AssocTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        name="AssocH2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(name="AssocBody", parent=styles["Normal"], fontSize=9, leading=11)

    story: list = []
    story.append(Paragraph(_escape_xml("Inventario · Mapa de asociación"), title_style))
    story.append(
        Paragraph(
            _escape_xml(f"Generado el {now.strftime('%d/%m/%Y %H:%M')}"),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    summary_lines = (
        f"Total activos en inventario: {total_assets} · "
        f"Grupos asociados (UC501/UG67): {len(groups)} · "
        f"Individuales fuera del mapa: {len(individuals)}"
    )
    story.append(Paragraph(_escape_xml(summary_lines), body_style))
    if total_assets == 0:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(_escape_xml("Sin datos de inventario."), body_style))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(_escape_xml("1. Grupos asociados"), h2_style))
    if not groups:
        story.append(Paragraph(_escape_xml("Sin grupos UC501/UG67."), body_style))
    else:
        for idx, g in enumerate(groups, start=1):
            loc_detail = str(g.location_detail or "").strip()
            loc_type = str(g.location_type or "").strip()
            ubic = ""
            if loc_type or loc_detail:
                ubic = " · ".join(p for p in [loc_type, loc_detail] if p)
            else:
                ubic = "(ubicación sin indicar)"

            hdr = (
                f"{idx}. {_role_label(g.role)} — {g.model.upper()} · SN {g.serial_number} "
                f"— Ubicación: {ubic}"
            )
            story.append(Paragraph(_escape_xml(hdr), body_style))
            story.append(Spacer(1, 0.15 * cm))
            if not g.children:
                story.append(Paragraph(_escape_xml("— Sin asociados"), body_style))
            else:
                lines_html: list[str] = []
                for c in g.children:
                    line = (
                        f"  · {_child_role_label(c.role)} ({c.model}): {c.serial_number}"
                    )
                    if (c.role or "").lower() == "sim" and str(c.sim_eid_number or "").strip():
                        line += f" · EID {str(c.sim_eid_number).strip()}"
                    lines_html.append(_escape_xml(line))
                story.append(Paragraph("<br/>".join(lines_html), body_style))
            story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph(_escape_xml("2. Activos individuales sin mapa jerárquico"), h2_style))
    if not individuals:
        story.append(Paragraph(_escape_xml("(Ningún activo pendiente fuera del mapa.)"), body_style))
    else:
        tbl_data: list[list[str]] = [["Modelo", "Serial", "Ubicación", "Quién lo tiene / detalle", "Nota"]]
        for r in individuals:
            loc_type = str(r.get("location_type", "") or "").strip()
            who = str(r.get("location_detail", "") or "").strip()
            contact_id = str(r.get("location_contact_id", "") or "").strip()
            if not who and contact_id:
                who = f"contact_id: {contact_id}"
            tbl_data.append(
                [
                    str(r.get("model", "") or ""),
                    str(r.get("serial_number", "") or ""),
                    loc_type,
                    who or "—",
                    _association_note_for_individual(r),
                ]
            )
        tw = doc.width
        tbl = Table(
            tbl_data,
            colWidths=[tw * 0.12, tw * 0.22, tw * 0.12, tw * 0.28, tw * 0.26],
        )
        tbl.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(tbl)

    if conflicts:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(_escape_xml("3. Conflictos de integridad detectados"), h2_style))
        for cf in conflicts:
            line = f"[{cf.kind}] {_escape_xml(cf.description)}"
            story.append(Paragraph(line, body_style))

    doc.build(story)
    return buf.getvalue(), filename
