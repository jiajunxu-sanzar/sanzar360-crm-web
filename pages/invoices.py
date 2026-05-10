from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.invoice_pdf_web import (
    BASE_EUR,
    DEFAULT_DESCRIPTION,
    DEFAULT_REFERENCE,
    InvoiceData,
    InvoiceItem,
    generate_invoice_pdf,
)


def render(_contacts_df: pd.DataFrame) -> None:
    st.title("Facturas")
    customer_name = st.text_input(
        "Nombre cliente (en la factura)",
        value="",
        help="Texto que aparecerá en el PDF. Rellénalo manualmente; no se enlaza con la lista de contactos.",
    )
    invoice_number = st.text_input("INVOICE IN-", value="2026-001")
    issue_date = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
    customer_cif = st.text_input("CIF", value="")

    st.markdown("### Lineas de factura")
    line_count = st.number_input("Numero de lineas", min_value=1, max_value=10, value=1, step=1)
    items: list[InvoiceItem] = []
    for idx in range(int(line_count)):
        c1, c2, c3, c4 = st.columns([1.2, 3.0, 1.0, 1.4])
        reference = c1.text_input(
            f"Referencia {idx + 1}",
            value=DEFAULT_REFERENCE if idx == 0 else "",
            key=f"invoice_ref_{idx}",
        )
        description = c2.text_input(
            f"Descripcion {idx + 1}",
            value=DEFAULT_DESCRIPTION if idx == 0 else "",
            key=f"invoice_desc_{idx}",
        )
        quantity = int(
            c3.number_input(f"Cantidad {idx + 1}", min_value=1, value=1, step=1, key=f"invoice_qty_{idx}")
        )
        unit_price = float(
            c4.number_input(
                f"P. unit (sin IVA) {idx + 1}",
                min_value=0.0,
                value=BASE_EUR if idx == 0 else 0.0,
                step=10.0,
                key=f"invoice_unit_{idx}",
            )
        )
        items.append(
            InvoiceItem(
                reference=reference.strip() or DEFAULT_REFERENCE,
                description=description.strip() or DEFAULT_DESCRIPTION,
                quantity=quantity,
                unit_price_excl_vat=unit_price,
            )
        )

    data = InvoiceData(
        invoice_number=invoice_number,
        customer_name=customer_name.strip(),
        customer_cif=customer_cif.strip(),
        issue_date=issue_date,
        items=items,
    )
    pdf = generate_invoice_pdf(data)
    st.download_button(
        "Descargar PDF",
        data=pdf,
        file_name=f"{invoice_number or 'factura'}.pdf",
        mime="application/pdf",
    )
