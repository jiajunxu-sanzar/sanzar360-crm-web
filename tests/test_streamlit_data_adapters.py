import importlib.util

from services.email_service import render_template, validate_placeholders
from services.invoice_pdf_web import InvoiceData, InvoiceItem, generate_invoice_pdf


def test_email_template_placeholders() -> None:
    assert validate_placeholders("Hola {Nombre} {unknown}") == ["unknown"]
    assert render_template("Hola {Nombre}", {"nombre": "Cliente Demo"}) == "Hola Cliente Demo"


def test_invoice_pdf_generation_returns_pdf_bytes() -> None:
    data = InvoiceData(
        invoice_number="TEST-1",
        customer_name="Cliente Demo",
        customer_cif="B00000000",
        items=[InvoiceItem(reference="REF", description="Servicio", quantity=1, unit_price_excl_vat=100)],
    )
    assert generate_invoice_pdf(data).startswith(b"%PDF")


def test_invoice_pdf_many_lines_paginates_without_error() -> None:
    items = [
        InvoiceItem(
            reference=f"R{i:03d}",
            description=f"Linea de producto larga numero {i}",
            quantity=1,
            unit_price_excl_vat=10.0 + i,
        )
        for i in range(18)
    ]
    data = InvoiceData(
        invoice_number="TEST-MULTI",
        customer_name="Cliente varias lineas",
        items=items,
    )
    pdf = generate_invoice_pdf(data)
    assert pdf.startswith(b"%PDF")
    # Full layout only when ReportLab is installed (otherwise minimal fallback).
    if importlib.util.find_spec("reportlab") is not None:
        assert len(pdf) > 2000
        assert pdf.count(b"/Type /Page") >= 3  # multiple pages vs single-page minimal fallback
