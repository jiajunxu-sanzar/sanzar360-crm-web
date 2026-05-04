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
