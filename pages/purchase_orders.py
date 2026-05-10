from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.purchase_order_pdf import (
    PurchaseOrderData,
    PurchaseOrderItem,
    generate_purchase_order_pdf,
)

COMPANY_BLOCK = (
    "Agroaerospace SL\n"
    "Avenida Gregorio Peces Barba 1\n"
    "28919. Leganes. Spain\n"
    "Phone: +34670272900\n"
    "VAT: ESB88360565\n"
    "Website: www.sanzar-group.com"
)

SHIP_TO_DEFAULT = (
    "Sanzar. Marco Ruano\n"
    "AGROAEROSPACE SL\n"
    "Avenida Gregorio Peces Barba 1\n"
    "28919. Leganes. Spain\n"
    "+34 670 272 900"
)


def _po_items_state() -> list[dict[str, object]]:
    if "po_items" not in st.session_state:
        st.session_state["po_items"] = [
            {"item_no": "1", "description": "", "qty": 1.0, "unit_price": 0.0}
        ]
    return st.session_state["po_items"]


def render(_: pd.DataFrame) -> None:
    st.title("PURCHASE ORDER")
    st.text(COMPANY_BLOCK)

    top_left, top_right = st.columns(2, gap="large")
    with top_left:
        po_date = st.text_input("DATE", value=date.today().strftime("%d/%m/%Y"))
        po_number = st.text_input("PO#", value="")

    block_left, block_right = st.columns(2, gap="large")
    with block_left:
        st.markdown("#### VENDOR")
        vendor_name = st.text_input("Vendor name", value="")
        vendor_contact = st.text_input("Contact person", value="")
        vendor_address = st.text_area("Address", value="", height=80)
        vendor_phone = st.text_input("Phone", value="")
        vendor_email = st.text_input("Email", value="")
    with block_right:
        st.markdown("#### SHIP TO")
        ship_to = st.text_area("SHIP TO", value=SHIP_TO_DEFAULT, height=210)

    show_shipping_table = st.checkbox("Mostrar tabla logística (REQUISITIONER / SHIP VIA / F.O.B / SHIPPING TERMS)", value=True)
    requisitioner = "AGROAEROSPACE SL"
    ship_via = "Air"
    fob = "Yes"
    shipping_terms = "No insurance"
    if show_shipping_table:
        table1_cols = st.columns(4)
        requisitioner = table1_cols[0].text_input("REQUISITIONER", value=requisitioner)
        ship_via = table1_cols[1].text_input("SHIP VIA", value=ship_via)
        fob = table1_cols[2].text_input("F.O.B", value=fob)
        shipping_terms = table1_cols[3].text_input("SHIPPING TERMS", value=shipping_terms)

    st.markdown("#### ITEMS")
    if st.button("+ Añadir item", width="content"):
        items = _po_items_state()
        items.append(
            {
                "item_no": str(len(items) + 1),
                "description": "",
                "qty": 1.0,
                "unit_price": 0.0,
            }
        )
        st.rerun()

    item_rows: list[dict[str, object]] = []
    subtotal = 0.0
    for idx, row in enumerate(_po_items_state()):
        cols = st.columns([0.9, 3.8, 1.0, 1.2, 1.2], gap="small")
        item_no = cols[0].text_input("ITEM #", value=str(row.get("item_no", idx + 1)), key=f"po_item_no_{idx}")
        description = cols[1].text_input("DESCRIPTION", value=str(row.get("description", "")), key=f"po_item_desc_{idx}")
        qty = cols[2].number_input("QTY", min_value=0.0, value=float(row.get("qty", 1.0)), step=1.0, key=f"po_item_qty_{idx}")
        unit_price = cols[3].number_input(
            "UNIT PRICE", min_value=0.0, value=float(row.get("unit_price", 0.0)), step=0.01, key=f"po_item_up_{idx}"
        )
        total = qty * unit_price
        cols[4].text_input("TOTAL", value=f"{total:.2f}", disabled=True, key=f"po_item_total_{idx}")
        subtotal += total
        item_rows.append(
            {
                "item_no": item_no,
                "description": description,
                "qty": qty,
                "unit_price": unit_price,
                "total": total,
            }
        )

    comments = st.text_area("Comments or Special Instructions", value="", height=120)

    sums_cols = st.columns(2, gap="large")
    with sums_cols[0]:
        st.empty()
    with sums_cols[1]:
        tax_pct = st.number_input("TAX (%)", min_value=0.0, value=0.0, step=0.1)
        tax_amount = subtotal * (tax_pct / 100.0)
        shipping = st.number_input("SHIPPING", min_value=0.0, value=0.0, step=0.01)
        other = st.number_input("OTHER", min_value=0.0, value=0.0, step=0.01)
        grand_total = subtotal + tax_amount + shipping + other
        st.text_input("SUBTOTAL", value=f"{subtotal:.2f}", disabled=True)
        st.text_input("TOTAL", value=f"{grand_total:.2f}", disabled=True)

    st.markdown(
        "If you have any questions about this purchase order, please contact\n"
        "[Marco Ruano, Phone +34670272900, E-mail: marco.ruano@sanzar-group.com]"
    )
    st.markdown(
        "This document is property of AgroAerospace S.L. and shall not be used distributed or reproduce "
        "without prior written authorization of AgroAerospace S.L."
    )

    items = [
        PurchaseOrderItem(
            item_no=str(row["item_no"]),
            description=str(row["description"]),
            qty=float(row["qty"]),
            unit_price=float(row["unit_price"]),
            total=float(row["total"]),
        )
        for row in item_rows
    ]
    payload = PurchaseOrderData(
        po_date=po_date,
        po_number=po_number,
        vendor_name=vendor_name,
        vendor_contact=vendor_contact,
        vendor_address=vendor_address,
        vendor_phone=vendor_phone,
        vendor_email=vendor_email,
        ship_to=ship_to,
        show_shipping_table=show_shipping_table,
        requisitioner=requisitioner,
        ship_via=ship_via,
        fob=fob,
        shipping_terms=shipping_terms,
        items=items,
        comments=comments,
        subtotal=subtotal,
        tax_pct=tax_pct,
        tax_amount=tax_amount,
        shipping=shipping,
        other=other,
        grand_total=grand_total,
    )
    pdf_bytes = generate_purchase_order_pdf(payload)
    st.download_button(
        "Descargar Purchase Order",
        data=pdf_bytes,
        file_name=f"purchase_order_{po_number or 'draft'}.pdf",
        mime="application/pdf",
        width="stretch",
    )
