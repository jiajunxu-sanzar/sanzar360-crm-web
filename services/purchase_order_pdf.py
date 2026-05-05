from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


@dataclass(frozen=True)
class PurchaseOrderItem:
    item_no: str
    description: str
    qty: float
    unit_price: float
    total: float


@dataclass(frozen=True)
class PurchaseOrderData:
    po_date: str
    po_number: str
    vendor_name: str
    vendor_contact: str
    vendor_address: str
    vendor_phone: str
    vendor_email: str
    ship_to: str
    show_shipping_table: bool
    requisitioner: str
    ship_via: str
    fob: str
    shipping_terms: str
    items: list[PurchaseOrderItem]
    comments: str
    subtotal: float
    tax_pct: float
    tax_amount: float
    shipping: float
    other: float
    grand_total: float


def generate_purchase_order_pdf(data: PurchaseOrderData) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ModuleNotFoundError:
        return _minimal_pdf_bytes(data)

    dark_green = colors.HexColor("#276749")
    light_green = colors.HexColor("#f0fff4")
    medium_gray = colors.HexColor("#4a5568")
    light_gray = colors.HexColor("#e2e8f0")
    black = colors.HexColor("#1a202c")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x0 = 15 * mm
    x1 = width - 15 * mm
    y = height - 16 * mm

    pdf.setFillColor(light_green)
    pdf.rect(x0, y - 16 * mm, x1 - x0, 16 * mm, fill=1, stroke=0)
    logo_path = _resolve_logo_path()
    logo_drawn = False
    if logo_path is not None:
        try:
            pdf.drawImage(
                str(logo_path),
                x1 - 34 * mm,
                y - 13.5 * mm,
                width=28 * mm,
                height=12 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
            logo_drawn = True
        except Exception:
            pass
    pdf.setFillColor(dark_green)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(x0 + 4 * mm, y - 9 * mm, "PURCHASE ORDER")
    pdf.setFont("Helvetica-Bold", 10)
    right_text_x = x1 - (38 * mm if logo_drawn else 4 * mm)
    pdf.drawRightString(right_text_x, y - 6 * mm, f"DATE: {data.po_date}")
    pdf.drawRightString(right_text_x, y - 11.5 * mm, f"PO#: {data.po_number}")
    y -= 23 * mm

    pdf.setFillColor(black)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x0, y, "Agroaerospace SL")
    pdf.setFont("Helvetica", 9)
    company_lines = [
        "Avenida Gregorio Peces Barba 1",
        "28919. Leganes. Spain",
        "Phone: +34670272900",
        "VAT: ESB88360565",
        "Website: www.sanzar-group.com",
    ]
    for line in company_lines:
        y -= 4.5 * mm
        pdf.drawString(x0, y, line)

    blocks_top_y = y
    gap = 4 * mm
    block_w = (x1 - x0 - gap) / 2
    block_h = 34 * mm

    vendor_x = x0
    vendor_y = blocks_top_y
    pdf.setFillColor(light_green)
    pdf.setStrokeColor(light_gray)
    pdf.rect(vendor_x, vendor_y - block_h, block_w, block_h, fill=1, stroke=1)
    pdf.setFillColor(dark_green)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(vendor_x + 2 * mm, vendor_y - 4 * mm, "VENDOR")
    pdf.setFillColor(black)
    pdf.setFont("Helvetica", 9)
    vendor_lines = [
        f"Name: {data.vendor_name}",
        f"Contact: {data.vendor_contact}",
        f"Address: {data.vendor_address}",
        f"Phone: {data.vendor_phone}",
        f"Email: {data.vendor_email}",
    ]
    yv = vendor_y - 9 * mm
    for line in vendor_lines:
        pdf.drawString(vendor_x + 2 * mm, yv, line[:55])
        yv -= 4.5 * mm

    ship_x = vendor_x + block_w + gap
    ship_y = blocks_top_y
    pdf.setFillColor(light_green)
    pdf.setStrokeColor(light_gray)
    pdf.rect(ship_x, ship_y - block_h, block_w, block_h, fill=1, stroke=1)
    pdf.setFillColor(dark_green)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(ship_x + 2 * mm, ship_y - 4 * mm, "SHIP TO")
    pdf.setFillColor(black)
    pdf.setFont("Helvetica", 9)
    ys = ship_y - 9 * mm
    for line in (data.ship_to or "").splitlines():
        pdf.drawString(ship_x + 2 * mm, ys, line[:52])
        ys -= 4.5 * mm
    y = blocks_top_y - block_h - 6 * mm

    if data.show_shipping_table:
        pdf.setFillColor(light_green)
        pdf.setStrokeColor(light_gray)
        pdf.rect(x0, y - 11 * mm, x1 - x0, 11 * mm, fill=1, stroke=1)
        pdf.setFillColor(dark_green)
        pdf.setFont("Helvetica-Bold", 8)
        headers = ["REQUISITIONER", "SHIP VIA", "F.O.B", "SHIPPING TERMS"]
        values = [data.requisitioner, data.ship_via, data.fob, data.shipping_terms]
        col_w = (x1 - x0) / 4
        for i, header in enumerate(headers):
            pdf.drawString(x0 + i * col_w + 2 * mm, y - 3.5 * mm, header)
        pdf.setFillColor(black)
        pdf.setFont("Helvetica", 8)
        for i, value in enumerate(values):
            pdf.drawString(x0 + i * col_w + 2 * mm, y - 8 * mm, str(value)[:26])
        y -= 15 * mm

    pdf.setFillColor(dark_green)
    pdf.rect(x0, y - 7 * mm, x1 - x0, 7 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    item_headers = ["ITEM #", "DESCRIPTION", "QTY", "UNIT PRICE", "TOTAL"]
    col_widths = [20 * mm, 88 * mm, 18 * mm, 30 * mm, 30 * mm]
    cx = x0 + 2 * mm
    for header, cw in zip(item_headers, col_widths):
        pdf.drawString(cx, y - 4.8 * mm, header)
        cx += cw
    y -= 7 * mm

    pdf.setFont("Helvetica", 8.5)
    fill_toggle = False
    for item in data.items:
        if y < 55 * mm:
            pdf.showPage()
            y = height - 20 * mm
        if fill_toggle:
            pdf.setFillColor(light_green)
            pdf.rect(x0, y - 6.5 * mm, x1 - x0, 6.5 * mm, fill=1, stroke=0)
        fill_toggle = not fill_toggle
        pdf.setFillColor(black)
        cx = x0 + 2 * mm
        values = [
            item.item_no,
            item.description[:58],
            f"{item.qty:g}",
            f"{item.unit_price:.2f}",
            f"{item.total:.2f}",
        ]
        for value, cw in zip(values, col_widths):
            pdf.drawString(cx, y - 4.7 * mm, str(value))
            cx += cw
        y -= 6.5 * mm

    y -= 3 * mm
    pdf.setFillColor(light_green)
    pdf.setStrokeColor(light_gray)
    pdf.rect(x0, y - 20 * mm, 112 * mm, 20 * mm, fill=1, stroke=1)
    pdf.setFillColor(dark_green)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x0 + 2 * mm, y - 4 * mm, "Comments or Special Instructions")
    pdf.setFillColor(black)
    pdf.setFont("Helvetica", 8.5)
    comment_y = y - 8.5 * mm
    for line in (data.comments or "").splitlines()[:3]:
        pdf.drawString(x0 + 2 * mm, comment_y, line[:78])
        comment_y -= 4 * mm

    total_x = x0 + 116 * mm
    pdf.setFillColor(light_green)
    pdf.setStrokeColor(light_gray)
    pdf.rect(total_x, y - 31 * mm, x1 - total_x, 31 * mm, fill=1, stroke=1)
    pdf.setFillColor(medium_gray)
    pdf.setFont("Helvetica", 8.5)
    labels = [
        ("SUBTOTAL", data.subtotal),
        (f"TAX ({data.tax_pct:.2f}%)", data.tax_amount),
        ("SHIPPING", data.shipping),
        ("OTHER", data.other),
    ]
    ty = y - 5 * mm
    for label, value in labels:
        pdf.drawString(total_x + 2 * mm, ty, label)
        pdf.drawRightString(x1 - 3 * mm, ty, f"{value:.2f}")
        ty -= 5.5 * mm
    pdf.setFillColor(dark_green)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(total_x + 2 * mm, ty, "TOTAL")
    pdf.drawRightString(x1 - 3 * mm, ty, f"{data.grand_total:.2f}")

    y -= 38 * mm
    pdf.setFillColor(black)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(
        x0,
        y,
        "If you have any questions about this purchase order, please contact",
    )
    y -= 4 * mm
    pdf.drawString(
        x0,
        y,
        "[Marco Ruano, Phone +34670272900, E-mail: marco.ruano@sanzar-group.com]",
    )
    y -= 7 * mm
    pdf.setFont("Helvetica-Oblique", 7.7)
    pdf.drawString(
        x0,
        y,
        "This document is property of AgroAerospace S.L. and shall not be used distributed or reproduce",
    )
    y -= 3.5 * mm
    pdf.drawString(
        x0,
        y,
        "without prior written authorization of AgroAerospace S.L.",
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _minimal_pdf_bytes(data: PurchaseOrderData) -> bytes:
    text = (
        f"PURCHASE ORDER\\n"
        f"DATE: {data.po_date}\\n"
        f"PO#: {data.po_number}\\n"
        f"VENDOR: {data.vendor_name}\\n"
        f"TOTAL: {data.grand_total:.2f}"
    )
    stream = f"BT /F1 12 Tf 72 740 Td ({text.replace('(', '[').replace(')', ']')}) Tj ET"
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
