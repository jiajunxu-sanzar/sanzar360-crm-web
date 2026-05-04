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

    @property
    def total(self) -> float:
        base = sum(item.total for item in self.items)
        vat = round(base * self.vat_rate, 2)
        return round(base + vat, 2)


def generate_invoice_pdf(data: InvoiceData) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
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

    # Header
    logo_path = _resolve_logo_path()
    if logo_path is not None:
        try:
            pdf.drawImage(
                str(logo_path),
                left,
                height - 160,
                width=120,
                height=120,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawRightString(right, height - 62, "INVOICE")
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(right, height - 86, f"INVOICE IN-{data.invoice_number}")
    pdf.drawRightString(right, height - 108, f"Fecha: {data.issue_date.strftime('%d/%m/%Y')}")

    y = height - 185
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y, "Facutrar a:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left + 88, y, (data.customer_name or "").strip())
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

    # Items table
    table_top = y
    width_table = 510.0
    row_h = 28.0
    col_ref = 95.0
    col_desc = 205.0
    col_qty = 60.0
    col_unit = 80.0
    col_amount = width_table - col_ref - col_desc - col_qty - col_unit

    x_ref = left + col_ref
    x_desc = x_ref + col_desc
    x_qty = x_desc + col_qty
    x_unit = x_qty + col_unit

    pdf.setLineWidth(1)
    # Draw header without bottom border to avoid double separator
    pdf.line(left, table_top + row_h, left + width_table, table_top + row_h)  # top
    pdf.line(left, table_top, left, table_top + row_h)  # left side
    pdf.line(left + width_table, table_top, left + width_table, table_top + row_h)  # right side
    pdf.line(x_ref, table_top, x_ref, table_top + row_h)
    pdf.line(x_desc, table_top, x_desc, table_top + row_h)
    pdf.line(x_qty, table_top, x_qty, table_top + row_h)
    pdf.line(x_unit, table_top, x_unit, table_top + row_h)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left + 4, table_top + 10, "Referencia")
    pdf.drawString(x_ref + 4, table_top + 10, "Descripcion")
    pdf.drawString(x_desc + 4, table_top + 10, "Cantidad")
    pdf.drawString(x_qty + 4, table_top + 10, "P. unit.")
    pdf.drawString(x_unit + 4, table_top + 10, "Importe")

    item_h = 36.0
    item_top = table_top - item_h
    pdf.setFont("Helvetica", 9)
    cleaned_items = data.items or [InvoiceItem(description=DEFAULT_DESCRIPTION, quantity=1, unit_price_excl_vat=BASE_EUR)]
    base_amount = 0.0
    for item in cleaned_items:
        quantity = max(1, int(item.quantity))
        unit_price = max(0.0, float(item.unit_price_excl_vat))
        line_amount = round(quantity * unit_price, 2)
        base_amount += line_amount

        pdf.rect(left, item_top, width_table, item_h, stroke=1, fill=0)
        pdf.line(x_ref, item_top, x_ref, item_top + item_h)
        pdf.line(x_desc, item_top, x_desc, item_top + item_h)
        pdf.line(x_qty, item_top, x_qty, item_top + item_h)
        pdf.line(x_unit, item_top, x_unit, item_top + item_h)
        pdf.drawString(left + 4, item_top + 13, (item.reference or DEFAULT_REFERENCE).strip())
        pdf.drawString(x_ref + 4, item_top + 13, (item.description or DEFAULT_DESCRIPTION).strip()[:45])
        pdf.drawString(x_desc + 4, item_top + 13, str(quantity))
        pdf.drawRightString(x_unit - 4, item_top + 13, fmt_eur(unit_price))
        pdf.drawRightString(left + width_table - 4, item_top + 13, fmt_eur(line_amount))
        item_top -= item_h
    base_amount = round(base_amount, 2)

    vat_amount = round(base_amount * data.vat_rate, 2)
    total_amount = round(base_amount + vat_amount, 2)
    summary_top = item_top - 24
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(right, summary_top, f"Base imponible: {fmt_eur(base_amount)}")
    pdf.drawRightString(right, summary_top - 20, f"IVA ({int(data.vat_rate * 100)}%): {fmt_eur(vat_amount)}")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(right, summary_top - 44, f"TOTAL: {fmt_eur(total_amount)}")

    # Footer blocks
    footer_top = min(max(summary_top - 36, 334.0), 354.0)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, footer_top, "Condiciones:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left, footer_top - 24, "Moneda:")
    pdf.drawString(left + 100, footer_top - 24, "EURO")
    pdf.drawString(left, footer_top - 44, "Transporte:")
    pdf.drawString(left + 100, footer_top - 44, "N/A")
    pdf.drawString(left, footer_top - 64, "Seguro de transporte:")
    pdf.drawString(left + 100, footer_top - 64, "N/A")
    pdf.drawString(left, footer_top - 84, "Otros seguros")
    pdf.drawString(left + 100, footer_top - 84, "Inc N/A luido")

    right_x = 330.0
    pdf.drawString(right_x, footer_top - 24, "Compania")
    pdf.drawString(right_x + 100, footer_top - 24, "Agroaerospace S.L.")
    pdf.drawString(right_x, footer_top - 44, "CIF/ VAT")
    pdf.drawString(right_x + 100, footer_top - 44, "ESB88360565")
    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(right_x, footer_top - 64, "Forma de pago:")
    pdf.drawString(right_x + 100, footer_top - 64, "A la vista")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(right_x, footer_top - 84, "Codigo cliente:")
    pdf.drawString(right_x + 100, footer_top - 84, "N/A")

    bank_top = footer_top - 118
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, bank_top, "Datos bancarios:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left, bank_top - 24, "IBAN")
    pdf.drawString(left + 100, bank_top - 24, "ES79 0049 1889 00 2010490242")
    pdf.drawString(left, bank_top - 44, "BIC/CODIGO SWIFT.")
    pdf.drawString(left + 100, bank_top - 44, "BSCHESMMXXX")
    pdf.drawString(left, bank_top - 64, "BANK NAME:")
    pdf.drawString(left + 100, bank_top - 64, "BANCO SANTANDER, S.A.")

    contact_top = bank_top - 92
    pdf.drawString(left, contact_top, "Si tiene alguna pregunta no dude en ponerse en contacto con nosotros.")
    pdf.drawString(left, contact_top - 24, "Oficinas")
    pdf.drawString(left + 100, contact_top - 24, "Parque Tecnologico, Av. Gregorio Peces Barba, 1. 28919. Leganes,")
    pdf.drawString(left, contact_top - 42, "Centrales:")
    pdf.drawString(left + 100, contact_top - 42, "Madrid. Spain")
    pdf.drawString(left, contact_top - 60, "Telefono:")
    pdf.drawString(left + 100, contact_top - 60, "+34 670 272 900")
    pdf.drawString(left + 100, contact_top - 78, "+34 698 908 037")

    pdf.showPage()
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


def _resolve_logo_path() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "assets" / "branding" / "sanzar_logo.png",  # sanzar-crm-web/assets/branding
        here.parents[2] / "sanzar-crm" / "assets" / "branding" / "sanzar_logo.png",  # sibling project
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None
