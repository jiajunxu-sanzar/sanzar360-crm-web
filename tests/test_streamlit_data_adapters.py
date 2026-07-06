import importlib.util

from services.email_service import render_template, validate_placeholders
from services.invoice_pdf_web import (
    InvoiceData,
    InvoiceItem,
    _invoice_item_row_height,
    _notes_block_height,
    _wrap_multiline_text,
    generate_invoice_pdf,
)


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


def test_invoice_pdf_without_notes_unchanged() -> None:
    data = InvoiceData(
        invoice_number="TEST-NO-NOTES",
        customer_name="Cliente Demo",
        notes="   ",
        items=[InvoiceItem(reference="REF", description="Servicio", quantity=1, unit_price_excl_vat=100)],
    )
    assert generate_invoice_pdf(data).startswith(b"%PDF")
    assert _notes_block_height(data.notes) == 0.0


def test_notes_block_height() -> None:
    assert _notes_block_height("") == 0.0
    assert _notes_block_height("   ") == 0.0
    assert _notes_block_height("Una linea") > 0.0
    assert _notes_block_height("Linea 1\nLinea 2") > _notes_block_height("Una linea")
    long_line = " ".join(["palabra"] * 40)
    assert _notes_block_height(long_line) > _notes_block_height("Una linea")


def test_invoice_pdf_with_notes() -> None:
    note_text = "Pago a 30 dias.\nGracias."
    base_items = [InvoiceItem(reference="REF", description="Servicio", quantity=1, unit_price_excl_vat=100)]
    data = InvoiceData(
        invoice_number="TEST-NOTES",
        customer_name="Cliente Demo",
        notes=note_text,
        items=base_items,
    )
    pdf = generate_invoice_pdf(data)
    assert pdf.startswith(b"%PDF")
    if importlib.util.find_spec("reportlab") is not None:
        pdf_without = generate_invoice_pdf(
            InvoiceData(
                invoice_number="TEST-NOTES",
                customer_name="Cliente Demo",
                notes="",
                items=base_items,
            )
        )
        assert pdf != pdf_without


def test_wrap_multiline_text_splits_long_description() -> None:
    long_text = (
        "Suscripcion anual de sanzar360, con acceso a la app, soporte, mantenimiento "
        "y asesoria tecnica personalizada para el cliente."
    )
    lines = _wrap_multiline_text(long_text, "Helvetica", 9.0, 180.0)
    assert len(lines) >= 2


def test_invoice_item_row_height_grows_with_wrapped_text() -> None:
    short = _invoice_item_row_height("REF", "Corta", ref_col_width=95.0, desc_col_width=205.0)
    long = _invoice_item_row_height(
        "REF-LARGA-CON-TEXTO",
        "Descripcion muy larga que deberia ocupar varias lineas en el PDF de factura",
        ref_col_width=95.0,
        desc_col_width=205.0,
    )
    assert long > short


def test_invoice_pdf_long_description_generates() -> None:
    data = InvoiceData(
        invoice_number="TEST-WRAP",
        customer_name="Cliente Demo",
        items=[
            InvoiceItem(
                reference="SW-AGRO-SUSC-EXTRA",
                description=(
                    "Suscripcion anual de sanzar360, con acceso a la app, soporte, "
                    "mantenimiento y asesoria tecnica extendida para varias parcelas."
                ),
                quantity=1,
                unit_price_excl_vat=360.0,
            )
        ],
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
