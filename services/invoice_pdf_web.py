from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path

DEFAULT_REFERENCE = "SW-AGRO-SUSC"
DEFAULT_DESCRIPTION = (
    "Suscripcion anual de sanzar360, con acceso a la app, soporte, mantenimiento y asesoria tecnica."
)
VAT_RATE = 0.21
BASE_EUR = 360.0

# Layout (pts, PDF bottom-left coords; reserve space so table/summary/footer never overlap).
_INVOICE_PAGE_BOTTOM_MARGIN = 55.0
_INVOICE_TABLE_HEADER_H = 28.0
_INVOICE_ITEM_ROW_MIN_H = 36.0
_INVOICE_ITEM_LINE_H = 11.0
_INVOICE_ITEM_CELL_PADDING = 8.0
_INVOICE_ITEM_FONT = "Helvetica"
_INVOICE_ITEM_FONT_SIZE = 9.0
_INVOICE_ITEM_CELL_INSET = 4.0
_INVOICE_GAP_TABLE_TO_SUMMARY = 24.0
_INVOICE_SUMMARY_TOP_TO_FOOTER_TOP = 92.0  # clears TOTAL line + gap before "Condiciones:"
_INVOICE_FOOTER_BELOW_TITLE = 290.0  # footer_top downward to lowest contact line
_INVOICE_NOTES_TITLE_H = 16.0
_INVOICE_NOTES_LINE_H = 12.0
_INVOICE_NOTES_GAP_BEFORE_CONDICIONES = 24.0
_INVOICE_NOTES_FONT = "Helvetica"
_INVOICE_NOTES_FONT_SIZE = 10.0
_INVOICE_NOTES_MAX_WIDTH = 510.0
# Distance from page top (points) to table *bottom* edge on continuation pages; must clear
# the "(continua)" banner (drawn at height-48 / height-66) so the table header does not overlap.
_CONTINUATION_TOP_Y = 120.0


@dataclass(frozen=True)
class InvoiceItem:
    description: str
    quantity: int = 1
    unit_price_excl_vat: float = BASE_EUR
    reference: str = DEFAULT_REFERENCE

    @property
    def total(self) -> float:
        return round(float(self.quantity) * float(self.unit_price_excl_vat), 2)


@dataclass(frozen=True)
class InvoiceData:
    invoice_number: str
    customer_name: str
    customer_cif: str = ""
    items: list[InvoiceItem] = field(default_factory=lambda: [InvoiceItem(description=DEFAULT_DESCRIPTION, quantity=1, unit_price_excl_vat=BASE_EUR)])
    vat_rate: float = VAT_RATE
    issue_date: date = date.today()
    notes: str = ""

    @property
    def total(self) -> float:
        base = sum(item.total for item in self.items)
        vat = round(base * self.vat_rate, 2)
        return round(base + vat, 2)


def _wrap_text_to_width(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    from reportlab.pdfbase import pdfmetrics

    words = (text or "").strip().split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrap_multiline_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return [""]
    lines: list[str] = []
    for paragraph in raw.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        lines.extend(_wrap_text_to_width(paragraph, font_name, font_size, max_width))
    return lines or [""]


def _invoice_item_row_height(
    reference: str,
    description: str,
    *,
    ref_col_width: float,
    desc_col_width: float,
) -> float:
    ref_lines = _wrap_multiline_text(
        reference,
        _INVOICE_ITEM_FONT,
        _INVOICE_ITEM_FONT_SIZE,
        ref_col_width - 2 * _INVOICE_ITEM_CELL_INSET,
    )
    desc_lines = _wrap_multiline_text(
        description,
        _INVOICE_ITEM_FONT,
        _INVOICE_ITEM_FONT_SIZE,
        desc_col_width - 2 * _INVOICE_ITEM_CELL_INSET,
    )
    line_count = max(len(ref_lines), len(desc_lines), 1)
    content_h = line_count * _INVOICE_ITEM_LINE_H
    return max(_INVOICE_ITEM_ROW_MIN_H, content_h + 2 * _INVOICE_ITEM_CELL_PADDING)


def _notes_wrapped_lines(notes: str, max_width: float = _INVOICE_NOTES_MAX_WIDTH) -> list[str]:
    return _wrap_multiline_text(
        notes,
        _INVOICE_NOTES_FONT,
        _INVOICE_NOTES_FONT_SIZE,
        max_width,
    )


def _notes_block_height(notes: str, max_width: float = _INVOICE_NOTES_MAX_WIDTH) -> float:
    cleaned = (notes or "").strip()
    if not cleaned:
        return 0.0
    line_count = len(_notes_wrapped_lines(cleaned, max_width)) or 1
    return (
        _INVOICE_NOTES_TITLE_H
        + line_count * _INVOICE_NOTES_LINE_H
        + _INVOICE_NOTES_GAP_BEFORE_CONDICIONES
    )


def _invoice_summary_and_footer_fit_on_page(summary_top: float, notes_extra: float = 0.0) -> bool:
    footer_top = summary_top - _INVOICE_SUMMARY_TOP_TO_FOOTER_TOP
    condiciones_y = footer_top - notes_extra
    lowest = condiciones_y - _INVOICE_FOOTER_BELOW_TITLE
    return lowest >= _INVOICE_PAGE_BOTTOM_MARGIN


def generate_invoice_pdf(data: InvoiceData) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ModuleNotFoundError:
        return _minimal_pdf_bytes(data)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    black = colors.black

    def fmt_eur(value: float) -> str:
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"

    left = 42.0
    right = width - 42.0
    width_table = 510.0
    row_h = _INVOICE_TABLE_HEADER_H
    col_ref = 95.0
    col_desc = 205.0
    col_qty = 60.0
    col_unit = 80.0
    x_ref = left + col_ref
    x_desc = x_ref + col_desc
    x_qty = x_desc + col_qty
    x_unit = x_qty + col_unit

    # Header — logo inside a fixed box, aspect preserved, anchored top-left (no crop)
    logo_path = _resolve_logo_path()
    ir = _logo_image_reader(logo_path) if logo_path is not None else None
    if ir is not None:
        try:
            box_w = 94.0
            box_h = 74.0
            top_gap = 24.0
            y_box = height - top_gap - box_h
            pdf.drawImage(
                ir,
                left,
                y_box,
                width=box_w,
                height=box_h,
                preserveAspectRatio=True,
                anchor="nw",
            )
        except Exception:
            pass

    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawRightString(right, height - 62, "INVOICE")
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(right, height - 86, f"INVOICE IN-{data.invoice_number}")
    pdf.drawRightString(right, height - 108, f"Fecha: {data.issue_date.strftime('%d/%m/%Y')}")

    y = height - 175
    name_line = (data.customer_name or "").strip()
    if name_line:
        pdf.setFont("Helvetica", 11)
        pdf.drawString(left, y, name_line)
        y -= 22
    if data.customer_cif.strip():
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, "CIF:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left + 88, y, data.customer_cif.strip())
        y -= 24

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Direccion de facturacion")
    pdf.setFont("Helvetica", 10)
    fixed_addr = "Avenida Gregorio Peces-Barba, 1 - Pq. Cientifico UC3M, Leganes, 28919, Madrid"
    text = pdf.beginText(left, y - 16)
    text.textLines(fixed_addr)
    pdf.drawText(text)
    y -= 56

    def stroke_table_columns(table_top_local: float) -> None:
        pdf.setLineWidth(1)
        pdf.line(left, table_top_local + row_h, left + width_table, table_top_local + row_h)
        pdf.line(left, table_top_local, left, table_top_local + row_h)
        pdf.line(left + width_table, table_top_local, left + width_table, table_top_local + row_h)
        pdf.line(x_ref, table_top_local, x_ref, table_top_local + row_h)
        pdf.line(x_desc, table_top_local, x_desc, table_top_local + row_h)
        pdf.line(x_qty, table_top_local, x_qty, table_top_local + row_h)
        pdf.line(x_unit, table_top_local, x_unit, table_top_local + row_h)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(left + 4, table_top_local + 10, "Referencia")
        pdf.drawString(x_ref + 4, table_top_local + 10, "Descripcion")
        pdf.drawString(x_desc + 4, table_top_local + 10, "Cantidad")
        pdf.drawString(x_qty + 4, table_top_local + 10, "P. unit.")
        pdf.drawString(x_unit + 4, table_top_local + 10, "Importe")

    def continuation_table_anchor() -> float:
        return height - _CONTINUATION_TOP_Y

    def start_continuation_table() -> float:
        """New page + minimal banner + column headings. Returns y below header for next row."""
        pdf.showPage()
        pdf.setFillColor(black)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawRightString(right, height - 48, f"INVOICE IN-{data.invoice_number}")
        pdf.setFont("Helvetica", 10)
        pdf.drawRightString(right, height - 66, "(continua)")
        t_top = continuation_table_anchor()
        stroke_table_columns(t_top)
        return t_top

    def draw_invoice_row_lines(
        item_bottom: float,
        row_height: float,
        item: InvoiceItem,
        line_amount: float,
    ) -> None:
        qty = max(1, int(item.quantity))
        up = max(0.0, float(item.unit_price_excl_vat))
        reference = (item.reference or DEFAULT_REFERENCE).strip()
        description = (item.description or DEFAULT_DESCRIPTION).strip()
        ref_lines = _wrap_multiline_text(
            reference,
            _INVOICE_ITEM_FONT,
            _INVOICE_ITEM_FONT_SIZE,
            col_ref - 2 * _INVOICE_ITEM_CELL_INSET,
        )
        desc_lines = _wrap_multiline_text(
            description,
            _INVOICE_ITEM_FONT,
            _INVOICE_ITEM_FONT_SIZE,
            col_desc - 2 * _INVOICE_ITEM_CELL_INSET,
        )
        pdf.setFont(_INVOICE_ITEM_FONT, _INVOICE_ITEM_FONT_SIZE)
        pdf.rect(left, item_bottom, width_table, row_height, stroke=1, fill=0)
        pdf.line(x_ref, item_bottom, x_ref, item_bottom + row_height)
        pdf.line(x_desc, item_bottom, x_desc, item_bottom + row_height)
        pdf.line(x_qty, item_bottom, x_qty, item_bottom + row_height)
        pdf.line(x_unit, item_bottom, x_unit, item_bottom + row_height)
        first_line_y = item_bottom + row_height - _INVOICE_ITEM_CELL_PADDING - 9
        for line_idx, line in enumerate(ref_lines):
            pdf.drawString(
                left + _INVOICE_ITEM_CELL_INSET,
                first_line_y - line_idx * _INVOICE_ITEM_LINE_H,
                line,
            )
        for line_idx, line in enumerate(desc_lines):
            pdf.drawString(
                x_ref + _INVOICE_ITEM_CELL_INSET,
                first_line_y - line_idx * _INVOICE_ITEM_LINE_H,
                line,
            )
        pdf.drawString(x_desc + _INVOICE_ITEM_CELL_INSET, first_line_y, str(qty))
        pdf.drawRightString(x_unit - _INVOICE_ITEM_CELL_INSET, first_line_y, fmt_eur(up))
        pdf.drawRightString(left + width_table - _INVOICE_ITEM_CELL_INSET, first_line_y, fmt_eur(line_amount))

    def draw_summary_block(summary_basis_top: float, base_amt: float, vat_amt: float, total_amt: float) -> None:
        pdf.setFont("Helvetica", 10)
        pdf.drawRightString(right, summary_basis_top, f"Base imponible: {fmt_eur(base_amt)}")
        pdf.drawRightString(right, summary_basis_top - 20, f"IVA ({int(data.vat_rate * 100)}%): {fmt_eur(vat_amt)}")
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawRightString(right, summary_basis_top - 44, f"TOTAL: {fmt_eur(total_amt)}")

    def draw_notes_block(footer_anchor_y: float, notes: str) -> float:
        """Draw optional notes above Condiciones; return y for the Condiciones: line."""
        cleaned = (notes or "").strip()
        if not cleaned:
            return footer_anchor_y
        note_lines = _notes_wrapped_lines(cleaned, width_table)
        extra = (
            _INVOICE_NOTES_TITLE_H
            + len(note_lines) * _INVOICE_NOTES_LINE_H
            + _INVOICE_NOTES_GAP_BEFORE_CONDICIONES
        )
        condiciones_y = footer_anchor_y - extra
        notes_title_y = condiciones_y + extra - _INVOICE_NOTES_TITLE_H
        pdf.setFont("Helvetica-Bold", _INVOICE_NOTES_FONT_SIZE)
        pdf.drawString(left, notes_title_y, "Notas:")
        pdf.setFont(_INVOICE_NOTES_FONT, _INVOICE_NOTES_FONT_SIZE)
        body_top_y = notes_title_y - 14
        for line_idx, line in enumerate(note_lines):
            pdf.drawString(left, body_top_y - line_idx * _INVOICE_NOTES_LINE_H, line)
        return condiciones_y

    def draw_footer_block(footer_y: float) -> None:
        right_x = 330.0
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, footer_y, "Condiciones:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left, footer_y - 24, "Moneda:")
        pdf.drawString(left + 100, footer_y - 24, "EURO")
        pdf.drawString(left, footer_y - 44, "Transporte:")
        pdf.drawString(left + 100, footer_y - 44, "N/A")
        pdf.drawString(left, footer_y - 64, "Seguro de transporte:")
        pdf.drawString(left + 100, footer_y - 64, "N/A")
        pdf.drawString(left, footer_y - 84, "Otros seguros")
        pdf.drawString(left + 100, footer_y - 84, "Inc N/A luido")

        pdf.drawString(right_x, footer_y - 24, "Compania")
        pdf.drawString(right_x + 100, footer_y - 24, "Agroaerospace S.L.")
        pdf.drawString(right_x, footer_y - 44, "CIF/ VAT")
        pdf.drawString(right_x + 100, footer_y - 44, "ESB88360565")
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.drawString(right_x, footer_y - 64, "Forma de pago:")
        pdf.drawString(right_x + 100, footer_y - 64, "A la vista")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(right_x, footer_y - 84, "Codigo cliente:")
        pdf.drawString(right_x + 100, footer_y - 84, "N/A")

        bank_y = footer_y - 118
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, bank_y, "Datos bancarios:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left, bank_y - 24, "IBAN")
        pdf.drawString(left + 100, bank_y - 24, "ES79 0049 1889 00 2010490242")
        pdf.drawString(left, bank_y - 44, "BIC/CODIGO SWIFT.")
        pdf.drawString(left + 100, bank_y - 44, "BSCHESMMXXX")
        pdf.drawString(left, bank_y - 64, "BANK NAME:")
        pdf.drawString(left + 100, bank_y - 64, "BANCO SANTANDER, S.A.")

        contact_y = bank_y - 92
        pdf.drawString(left, contact_y, "Si tiene alguna pregunta no dude en ponerse en contacto con nosotros.")
        pdf.drawString(left, contact_y - 24, "Oficinas")
        pdf.drawString(left + 100, contact_y - 24, "Parque Tecnologico, Av. Gregorio Peces Barba, 1. 28919. Leganes,")
        pdf.drawString(left, contact_y - 42, "Centrales:")
        pdf.drawString(left + 100, contact_y - 42, "Madrid. Spain")
        pdf.drawString(left, contact_y - 60, "Telefono:")
        pdf.drawString(left + 100, contact_y - 60, "+34 670 272 900")
        pdf.drawString(left + 100, contact_y - 78, "+34 698 908 037")

    # Items table — first page
    table_top = float(y)
    stroke_table_columns(table_top)
    row_cursor_y = table_top

    cleaned_items = data.items or [InvoiceItem(description=DEFAULT_DESCRIPTION, quantity=1, unit_price_excl_vat=BASE_EUR)]
    notes_extra = _notes_block_height(data.notes)

    idx = 0
    base_amount = 0.0
    while idx < len(cleaned_items):
        item_row = cleaned_items[idx]
        is_last = idx == len(cleaned_items) - 1
        row_height = _invoice_item_row_height(
            (item_row.reference or DEFAULT_REFERENCE).strip(),
            (item_row.description or DEFAULT_DESCRIPTION).strip(),
            ref_col_width=col_ref,
            desc_col_width=col_desc,
        )
        item_bottom = row_cursor_y - row_height

        need_break = False
        if item_bottom < _INVOICE_PAGE_BOTTOM_MARGIN:
            need_break = True
        elif is_last:
            cand_summary = item_bottom - _INVOICE_GAP_TABLE_TO_SUMMARY
            if not _invoice_summary_and_footer_fit_on_page(cand_summary, notes_extra):
                need_break = True

        if need_break:
            row_cursor_y = start_continuation_table()
            continue

        qty = max(1, int(item_row.quantity))
        unit_price = max(0.0, float(item_row.unit_price_excl_vat))
        line_amount = round(qty * unit_price, 2)
        base_amount += line_amount
        draw_invoice_row_lines(item_bottom, row_height, item_row, line_amount)

        idx += 1
        row_cursor_y = item_bottom

    base_amount = round(base_amount, 2)
    vat_amount = round(base_amount * data.vat_rate, 2)
    total_amount = round(base_amount + vat_amount, 2)

    summary_top = row_cursor_y - _INVOICE_GAP_TABLE_TO_SUMMARY
    if not _invoice_summary_and_footer_fit_on_page(summary_top, notes_extra):
        pdf.showPage()
        pdf.setFillColor(black)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawRightString(right, height - 62, "INVOICE")
        pdf.setFont("Helvetica", 11)
        pdf.drawRightString(right, height - 86, f"INVOICE IN-{data.invoice_number}")
        pdf.drawRightString(right, height - 108, f"Fecha: {data.issue_date.strftime('%d/%m/%Y')}")
        summary_top = height - 200.0

    draw_summary_block(summary_top, base_amount, vat_amount, total_amount)
    footer_top = summary_top - _INVOICE_SUMMARY_TOP_TO_FOOTER_TOP
    condiciones_y = draw_notes_block(footer_top, data.notes)
    draw_footer_block(condiciones_y)

    pdf.save()
    return buffer.getvalue()


def _minimal_pdf_bytes(data: InvoiceData) -> bytes:
    text = (
        f"Sanzar - Factura\\n"
        f"N factura: {data.invoice_number}\\n"
        f"Cliente: {data.customer_name}\\n"
        f"Total: {data.total:.2f} EUR"
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({text.replace('(', '[').replace(')', ']')}) Tj ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj",
    ]
    body = "\n".join(objects)
    return ("%PDF-1.4\n" + body + "\n%%EOF\n").encode("latin-1", errors="replace")


_LOGO_FILENAMES = (
    "SANZAR_LOGO VERDE.png",
    "SANZAR_LOGO_VERDE.png",
    "SANZAR LOGO VERDE.png",
    "sanzar_logo_verde.png",
    "sanzar_logo.png",
)


def _logo_search_directories() -> list[Path]:
    here = Path(__file__).resolve().parents[1]
    return [
        here / "assets" / "branding",
        here / "assets",
        here,
        here.parent / "sanzar-crm" / "assets" / "branding",
    ]


def _resolve_logo_path() -> Path | None:
    for directory in _logo_search_directories():
        if not directory.is_dir():
            continue
        for name in _LOGO_FILENAMES:
            path = directory / name
            if path.is_file():
                return path
    return None


def _logo_image_reader(logo_path: Path) -> ImageReader | None:
    """RGB PNG via Pillow avoids mask/alpha glitches in ReportLab that can look 'cut off'."""
    from reportlab.lib.utils import ImageReader

    try:
        from PIL import Image

        im = Image.open(logo_path)
        if im.mode == "P":
            if "transparency" in im.info:
                im = im.convert("RGBA")
            else:
                im = im.convert("RGBA")
        elif im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        if im.mode == "RGBA":
            white = Image.new("RGB", im.size, (255, 255, 255))
            white.paste(im, mask=im.split()[3])
            out = white
        else:
            out = im
        buf = BytesIO()
        out.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        pass
    try:
        return ImageReader(str(logo_path))
    except Exception:
        return None
