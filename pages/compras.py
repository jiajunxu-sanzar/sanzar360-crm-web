from __future__ import annotations

import html
from datetime import date, datetime

import pandas as pd
import streamlit as st

from app.cache import compras_service, load_compras_cached
from app.navigation import page_menu_title
from app.state import bump_compras_cache
from config.settings import COMPRAS_ESTADOS, COMPRAS_HEADERS, PERSONA_COMERCIAL_OPCIONES
from services.compras_service import (
    PoLineItem,
    PoLineasPayload,
    compra_warnings,
    parse_po_lineas_json,
    serialize_po_lineas_json,
)
from services.purchase_order_pdf import PurchaseOrderData, PurchaseOrderItem, generate_purchase_order_pdf

SHIP_TO_DEFAULT = (
    "Sanzar. Marco Ruano\n"
    "AGROAEROSPACE SL\n"
    "Avenida Gregorio Peces Barba 1\n"
    "28919. Leganes. Spain\n"
    "+34 670 272 900"
)

COMPRAS_NEW_DIALOG_KEY = "compras_new_dialog_open"
COMPRAS_EDIT_DIALOG_KEY = "compras_edit_dialog_open"
COMPRAS_SELECTED_ID_KEY = "compras_selected_id"
COMPRAS_VIEW_FILTER_KEY = "compras_view_filter"
COMPRAS_SUCCESS_KEY = "compras_success_message"
COMPRAS_DELETE_STEP2_KEY = "compras_delete_step2_id"
COMPRAS_PO_LINES_KEY = "compras_po_lines_draft"

ESTADO_LABELS = {
    "comparando": "Comparando PIs",
    "pendiente": "Pendiente",
    "en_transito": "En tránsito",
    "recibida": "Recibida",
    "cancelada": "Cancelada",
}

ESTADO_BADGE_COLORS: dict[str, tuple[str, str, str]] = {
    "comparando": ("#eff6ff", "#bfdbfe", "#1e40af"),
    "pendiente": ("#fffbeb", "#fde68a", "#92400e"),
    "en_transito": ("#eef2ff", "#c7d2fe", "#3730a3"),
    "recibida": ("#ecfdf5", "#86efac", "#166534"),
    "cancelada": ("#fef2f2", "#fecaca", "#991b1b"),
}


def _format_importe(row: pd.Series) -> str:
    raw = str(row.get("importe_total", "") or "").strip()
    if not raw:
        return "—"
    moneda = str(row.get("moneda", "EUR") or "EUR").strip().upper()
    try:
        amount = float(raw.replace(",", "."))
    except ValueError:
        return f"{raw} €" if moneda == "EUR" else f"{raw} {moneda}"
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if moneda == "EUR":
        return f"{formatted} €"
    return f"{formatted} {moneda}"


def _estado_badge_html(estado: str) -> str:
    estado_norm = str(estado or "").strip().lower()
    label = ESTADO_LABELS.get(estado_norm, estado or "—")
    bg, border, fg = ESTADO_BADGE_COLORS.get(estado_norm, ("#f4f4f5", "#e5e5e5", "#52525b"))
    return (
        f"<span style='display:inline-block;padding:4px 10px;border-radius:8px;"
        f"font-size:0.78rem;font-weight:600;background:{bg};border:1px solid {border};"
        f"color:{fg};white-space:nowrap;'>{html.escape(label)}</span>"
    )


def _close_compras_new_dialog() -> None:
    st.session_state.pop(COMPRAS_NEW_DIALOG_KEY, None)
    st.session_state.pop(f"{COMPRAS_PO_LINES_KEY}_new", None)


def _close_compras_edit_dialog() -> None:
    st.session_state.pop(COMPRAS_EDIT_DIALOG_KEY, None)
    st.session_state.pop(COMPRAS_DELETE_STEP2_KEY, None)
    compra_id = str(st.session_state.get(COMPRAS_SELECTED_ID_KEY, "") or "").strip()
    if compra_id:
        st.session_state.pop(f"{COMPRAS_PO_LINES_KEY}_{compra_id}", None)


def _parse_sheet_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota exceeded" in msg or "read requests" in msg


def _row_dict(row: pd.Series) -> dict[str, str]:
    return {h: str(row.get(h, "") or "") for h in COMPRAS_HEADERS}


def _empty_row() -> dict[str, str]:
    today = date.today().strftime("%d/%m/%Y")
    return {
        "compra_id": "",
        "referencia": "",
        "descripcion": "",
        "proveedor": "",
        "proveedor_contacto": "",
        "proveedor_direccion": "",
        "proveedor_telefono": "",
        "proveedor_email": "",
        "estado": "comparando",
        "fecha_solicitud": today,
        "fecha_pedido": "",
        "fecha_recepcion": "",
        "importe_total": "",
        "moneda": "EUR",
        "proforma_invoice_url": "",
        "pis_comparativas_carpeta_url": "",
        "payment_receipt_url": "",
        "po_lineas_json": "",
        "ship_to": SHIP_TO_DEFAULT,
        "po_notas": "",
        "responsable": "",
        "notas": "",
        "created_at": "",
        "updated_at": "",
    }


def _filter_df(
    df: pd.DataFrame,
    *,
    view: str,
    query: str,
    proveedor: str,
    responsable: str,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    view_norm = (view or "Todas").strip()
    estados = out["estado"].fillna("").astype(str).str.strip().str.lower()
    if view_norm == "Pendientes":
        out = out[estados.isin({"comparando", "pendiente", "en_transito"})]
    elif view_norm == "Completadas":
        out = out[estados == "recibida"]
    q = (query or "").strip().lower()
    if q:
        text = out.fillna("").astype(str)
        mask = pd.Series(False, index=out.index)
        for col in ("referencia", "descripcion", "proveedor", "responsable", "notas"):
            if col in text.columns:
                mask = mask | text[col].str.lower().str.contains(q, regex=False, na=False)
        out = out[mask]
    if proveedor:
        out = out[out["proveedor"].astype(str).str.strip() == proveedor]
    if responsable:
        out = out[out["responsable"].astype(str).str.strip() == responsable]
    return out


def _sort_df(df: pd.DataFrame, view: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if (view or "") == "Completadas":
        out["_sort"] = out["fecha_recepcion"].map(_parse_sheet_date)
        out = out.sort_values(by="_sort", ascending=False, na_position="last")
    else:
        out["_sort"] = out["fecha_solicitud"].map(_parse_sheet_date)
        out = out.sort_values(by="_sort", ascending=True, na_position="last")
    return out.drop(columns=["_sort"], errors="ignore")


def _kpi_metrics(df: pd.DataFrame) -> tuple[int, int, int]:
    if df.empty:
        return 0, 0, 0
    estados = df["estado"].fillna("").astype(str).str.strip().str.lower()
    pendientes = int(estados.isin({"comparando", "pendiente"}).sum())
    en_transito = int((estados == "en_transito").sum())
    year = date.today().year
    recibidas_year = 0
    for _, row in df[estados == "recibida"].iterrows():
        d = _parse_sheet_date(str(row.get("fecha_recepcion", "") or ""))
        if d and d.year == year:
            recibidas_year += 1
    return pendientes, en_transito, recibidas_year


def _po_lines_draft(compra_id: str, values: dict[str, str]) -> list[dict[str, object]]:
    key = f"{COMPRAS_PO_LINES_KEY}_{compra_id or 'new'}"
    if key not in st.session_state:
        payload = parse_po_lineas_json(values.get("po_lineas_json", ""))
        if payload.items:
            st.session_state[key] = [
                {
                    "item_no": item.item_no,
                    "description": item.description,
                    "qty": item.qty,
                    "unit_price": item.unit_price,
                }
                for item in payload.items
            ]
        else:
            desc = str(values.get("descripcion", "") or "").strip()
            st.session_state[key] = [
                {"item_no": "1", "description": desc, "qty": 1.0, "unit_price": 0.0}
            ]
    return st.session_state[key]


def _render_url_field(label: str, value: str, *, key: str) -> str:
    col1, col2 = st.columns([4, 1])
    with col1:
        url = st.text_input(label, value=value, key=key)
    with col2:
        st.write("")
        st.write("")
        if (url or "").strip():
            st.link_button("Abrir", url.strip(), use_container_width=True)
    return url


def _current_po_lines_from_widgets(prefix: str, items: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for idx, row in enumerate(items):
        out.append(
            {
                "item_no": str(st.session_state.get(f"{prefix}_po_no_{idx}", row.get("item_no", idx + 1))),
                "description": str(st.session_state.get(f"{prefix}_po_desc_{idx}", row.get("description", ""))),
                "qty": float(st.session_state.get(f"{prefix}_po_qty_{idx}", row.get("qty", 1.0))),
                "unit_price": float(st.session_state.get(f"{prefix}_po_up_{idx}", row.get("unit_price", 0.0))),
            }
        )
    return out


def _render_po_lines_editor(compra_id: str, values: dict[str, str], *, prefix: str) -> PoLineasPayload:
    payload_existing = parse_po_lineas_json(values.get("po_lineas_json", ""))
    lines_key = f"{COMPRAS_PO_LINES_KEY}_{compra_id or 'new'}"
    items = _po_lines_draft(compra_id, values)

    if st.button("+ Añadir línea", key=f"{prefix}_add_po_line"):
        items.append(
            {"item_no": str(len(items) + 1), "description": "", "qty": 1.0, "unit_price": 0.0}
        )
        st.session_state[lines_key] = items
        st.rerun()

    subtotal = 0.0
    parsed_items: list[PoLineItem] = []
    for idx, row in enumerate(items):
        cols = st.columns([0.8, 3.5, 1.0, 1.2, 1.0, 0.35], gap="small")
        item_no = cols[0].text_input("ITEM #", value=str(row.get("item_no", idx + 1)), key=f"{prefix}_po_no_{idx}")
        description = cols[1].text_input("DESCRIPTION", value=str(row.get("description", "")), key=f"{prefix}_po_desc_{idx}")
        qty = cols[2].number_input("QTY", min_value=0.0, value=float(row.get("qty", 1.0)), step=1.0, key=f"{prefix}_po_qty_{idx}")
        unit_price = cols[3].number_input(
            "UNIT PRICE", min_value=0.0, value=float(row.get("unit_price", 0.0)), step=0.01, key=f"{prefix}_po_up_{idx}"
        )
        total = qty * unit_price
        cols[4].text_input("TOTAL", value=f"{total:.2f}", disabled=True, key=f"{prefix}_po_total_{idx}")
        with cols[5]:
            st.write("")
            st.write("")
            if st.button(
                "✕",
                key=f"{prefix}_po_del_{idx}",
                disabled=len(items) <= 1,
                help="Quitar línea",
                use_container_width=True,
            ):
                remaining = _current_po_lines_from_widgets(prefix, items)
                remaining.pop(idx)
                for i, item in enumerate(remaining):
                    item["item_no"] = str(i + 1)
                st.session_state[lines_key] = remaining
                st.rerun()
        subtotal += total
        parsed_items.append(
            PoLineItem(
                item_no=item_no,
                description=description,
                qty=qty,
                unit_price=unit_price,
            )
        )
        items[idx] = {
            "item_no": item_no,
            "description": description,
            "qty": qty,
            "unit_price": unit_price,
        }
    st.session_state[lines_key] = items

    st.caption(f"Subtotal líneas: {subtotal:.2f}")
    show_shipping_table = st.checkbox(
        "Mostrar tabla envío (REQUISITIONER / SHIP VIA / F.O.B / SHIPPING TERMS)",
        value=payload_existing.show_shipping_table,
        key=f"{prefix}_po_show_ship_table",
    )
    requisitioner = payload_existing.requisitioner
    ship_via = payload_existing.ship_via
    fob = payload_existing.fob
    shipping_terms = payload_existing.shipping_terms
    if show_shipping_table:
        tcols = st.columns(4)
        requisitioner = tcols[0].text_input("REQUISITIONER", value=requisitioner, key=f"{prefix}_po_req")
        ship_via = tcols[1].text_input("SHIP VIA", value=ship_via, key=f"{prefix}_po_ship_via")
        fob = tcols[2].text_input("F.O.B", value=fob, key=f"{prefix}_po_fob")
        shipping_terms = tcols[3].text_input("SHIPPING TERMS", value=shipping_terms, key=f"{prefix}_po_ship_terms")

    sum_cols = st.columns(3)
    tax_pct = sum_cols[0].number_input("TAX (%)", min_value=0.0, value=float(payload_existing.tax_pct), step=0.1, key=f"{prefix}_po_tax")
    shipping = sum_cols[1].number_input("SHIPPING", min_value=0.0, value=float(payload_existing.shipping), step=0.01, key=f"{prefix}_po_shipping")
    other = sum_cols[2].number_input("OTHER", min_value=0.0, value=float(payload_existing.other), step=0.01, key=f"{prefix}_po_other")
    comments = st.text_area(
        "Comments or Special Instructions",
        value=payload_existing.comments or str(values.get("po_notas", "") or ""),
        height=80,
        key=f"{prefix}_po_comments",
    )

    return PoLineasPayload(
        items=tuple(parsed_items),
        tax_pct=tax_pct,
        shipping=shipping,
        other=other,
        show_shipping_table=show_shipping_table,
        requisitioner=requisitioner,
        ship_via=ship_via,
        fob=fob,
        shipping_terms=shipping_terms,
        comments=comments,
    )


def _build_po_pdf(values: dict[str, str], po_payload: PoLineasPayload) -> bytes:
    subtotal = sum(item.total for item in po_payload.items)
    tax_amount = subtotal * (po_payload.tax_pct / 100.0)
    grand_total = subtotal + tax_amount + po_payload.shipping + po_payload.other
    po_date = str(values.get("fecha_pedido", "") or "").strip() or date.today().strftime("%d/%m/%Y")
    po_number = str(values.get("referencia", "") or "").strip()
    items = [
        PurchaseOrderItem(
            item_no=item.item_no,
            description=item.description,
            qty=item.qty,
            unit_price=item.unit_price,
            total=item.total,
        )
        for item in po_payload.items
    ]
    payload = PurchaseOrderData(
        po_date=po_date,
        po_number=po_number,
        vendor_name=str(values.get("proveedor", "") or ""),
        vendor_contact=str(values.get("proveedor_contacto", "") or ""),
        vendor_address=str(values.get("proveedor_direccion", "") or ""),
        vendor_phone=str(values.get("proveedor_telefono", "") or ""),
        vendor_email=str(values.get("proveedor_email", "") or ""),
        ship_to=str(values.get("ship_to", "") or SHIP_TO_DEFAULT),
        show_shipping_table=po_payload.show_shipping_table,
        requisitioner=po_payload.requisitioner,
        ship_via=po_payload.ship_via,
        fob=po_payload.fob,
        shipping_terms=po_payload.shipping_terms,
        items=items,
        comments=po_payload.comments or str(values.get("po_notas", "") or ""),
        subtotal=subtotal,
        tax_pct=po_payload.tax_pct,
        tax_amount=tax_amount,
        shipping=po_payload.shipping,
        other=po_payload.other,
        grand_total=grand_total,
    )
    return generate_purchase_order_pdf(payload)


def _render_compra_form(values: dict[str, str], *, mode: str, compras_df: pd.DataFrame) -> None:
    prefix = f"compras_{mode}"
    compra_id = str(values.get("compra_id", "") or "").strip()

    st.markdown("#### General")
    g1, g2 = st.columns(2)
    with g1:
        referencia = g1.text_input("Referencia (PO#)", value=values.get("referencia", ""), key=f"{prefix}_referencia")
        descripcion = g1.text_area("Descripción", value=values.get("descripcion", ""), key=f"{prefix}_descripcion")
        estado = g1.selectbox(
            "Estado",
            list(COMPRAS_ESTADOS),
            index=list(COMPRAS_ESTADOS).index(values.get("estado", "comparando") or "comparando")
            if (values.get("estado", "comparando") or "comparando") in COMPRAS_ESTADOS
            else 0,
            format_func=lambda x: ESTADO_LABELS.get(x, x),
            key=f"{prefix}_estado",
        )
    with g2:
        fecha_solicitud = g2.text_input("Fecha solicitud", value=values.get("fecha_solicitud", ""), key=f"{prefix}_fecha_sol")
        fecha_pedido = g2.text_input("Fecha pedido", value=values.get("fecha_pedido", ""), key=f"{prefix}_fecha_ped")
        fecha_recepcion = g2.text_input("Fecha recepción", value=values.get("fecha_recepcion", ""), key=f"{prefix}_fecha_rec")
        responsable_opts = [""] + list(PERSONA_COMERCIAL_OPCIONES)
        current_resp = str(values.get("responsable", "") or "").strip()
        responsable = g2.selectbox(
            "Responsable",
            responsable_opts if current_resp in responsable_opts else responsable_opts + [current_resp],
            index=(responsable_opts.index(current_resp) if current_resp in responsable_opts else len(responsable_opts)),
            key=f"{prefix}_responsable",
        )
        importe_total = g2.text_input("Importe total", value=values.get("importe_total", ""), key=f"{prefix}_importe")
        moneda = g2.text_input("Moneda", value=values.get("moneda", "EUR") or "EUR", key=f"{prefix}_moneda")

    st.markdown("#### Proveedor")
    p1, p2 = st.columns(2)
    with p1:
        proveedor = p1.text_input("Proveedor", value=values.get("proveedor", ""), key=f"{prefix}_proveedor")
        proveedor_contacto = p1.text_input("Contacto", value=values.get("proveedor_contacto", ""), key=f"{prefix}_contacto")
        proveedor_direccion = p1.text_area("Dirección", value=values.get("proveedor_direccion", ""), height=80, key=f"{prefix}_direccion")
    with p2:
        proveedor_telefono = p2.text_input("Teléfono", value=values.get("proveedor_telefono", ""), key=f"{prefix}_telefono")
        proveedor_email = p2.text_input("Email", value=values.get("proveedor_email", ""), key=f"{prefix}_email")
        ship_to = p2.text_area("Ship to (PO)", value=values.get("ship_to", SHIP_TO_DEFAULT) or SHIP_TO_DEFAULT, height=120, key=f"{prefix}_ship_to")

    st.markdown("#### Enlaces")
    proforma_invoice_url = _render_url_field(
        "Proforma invoice (PI elegida)",
        values.get("proforma_invoice_url", ""),
        key=f"{prefix}_pi_url",
    )
    pis_comparativas_carpeta_url = _render_url_field(
        "Carpeta PIs comparativas",
        values.get("pis_comparativas_carpeta_url", ""),
        key=f"{prefix}_pis_folder",
    )
    payment_receipt_url = _render_url_field(
        "Justificante de pago",
        values.get("payment_receipt_url", ""),
        key=f"{prefix}_payment_url",
    )

    st.markdown("#### Líneas del Purchase Order")
    po_payload = _render_po_lines_editor(compra_id, values, prefix=prefix)

    st.markdown("#### Notas")
    po_notas = st.text_area("Notas PO / internas", value=values.get("po_notas", ""), key=f"{prefix}_po_notas")
    notas = st.text_area("Notas internas", value=values.get("notas", ""), key=f"{prefix}_notas")

    draft = {
        **values,
        "referencia": referencia,
        "descripcion": descripcion,
        "estado": estado,
        "fecha_solicitud": fecha_solicitud,
        "fecha_pedido": fecha_pedido,
        "fecha_recepcion": fecha_recepcion,
        "responsable": responsable,
        "importe_total": importe_total,
        "moneda": moneda,
        "proveedor": proveedor,
        "proveedor_contacto": proveedor_contacto,
        "proveedor_direccion": proveedor_direccion,
        "proveedor_telefono": proveedor_telefono,
        "proveedor_email": proveedor_email,
        "ship_to": ship_to,
        "proforma_invoice_url": proforma_invoice_url,
        "pis_comparativas_carpeta_url": pis_comparativas_carpeta_url,
        "payment_receipt_url": payment_receipt_url,
        "po_notas": po_notas,
        "notas": notas,
        "po_lineas_json": serialize_po_lineas_json(
            PoLineasPayload(
                items=po_payload.items,
                tax_pct=po_payload.tax_pct,
                shipping=po_payload.shipping,
                other=po_payload.other,
                show_shipping_table=po_payload.show_shipping_table,
                requisitioner=po_payload.requisitioner,
                ship_via=po_payload.ship_via,
                fob=po_payload.fob,
                shipping_terms=po_payload.shipping_terms,
                comments=po_payload.comments or po_notas,
            )
        ),
    }

    for warning in compra_warnings(draft):
        st.warning(warning)

    pdf_bytes = _build_po_pdf(draft, po_payload)
    st.download_button(
        "Descargar Purchase Order PDF",
        data=pdf_bytes,
        file_name=f"purchase_order_{referencia or compra_id or 'draft'}.pdf",
        mime="application/pdf",
        key=f"{prefix}_download_pdf",
        use_container_width=True,
    )
    mark_transito = st.checkbox(
        "Al guardar, marcar como en tránsito y rellenar fecha pedido si falta",
        value=False,
        key=f"{prefix}_mark_transito",
    )

    save_col, cancel_col = st.columns(2)
    if save_col.button("Guardar", type="primary", key=f"{prefix}_save", use_container_width=True):
        if mark_transito:
            draft["estado"] = "en_transito"
            if not str(draft.get("fecha_pedido", "") or "").strip():
                draft["fecha_pedido"] = date.today().strftime("%d/%m/%Y")
        try:
            saved_id = compras_service().upsert_compra(draft)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            if _is_quota_error(exc):
                st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                return
            raise
        bump_compras_cache()
        st.session_state.pop(f"{COMPRAS_PO_LINES_KEY}_{compra_id or 'new'}", None)
        st.session_state[COMPRAS_SUCCESS_KEY] = "Compra guardada."
        st.session_state[COMPRAS_SELECTED_ID_KEY] = saved_id
        if mode == "edit":
            _close_compras_edit_dialog()
        else:
            _close_compras_new_dialog()
        st.rerun()

    if cancel_col.button("Cancelar", key=f"{prefix}_cancel", use_container_width=True):
        if mode == "edit":
            _close_compras_edit_dialog()
        else:
            _close_compras_new_dialog()
        st.rerun()

    if mode == "edit" and compra_id:
        st.divider()
        if st.button("Eliminar compra", key=f"{prefix}_delete_step1", type="secondary"):
            st.session_state[COMPRAS_DELETE_STEP2_KEY] = compra_id
            st.session_state[COMPRAS_EDIT_DIALOG_KEY] = True
            st.rerun()
        if str(st.session_state.get(COMPRAS_DELETE_STEP2_KEY, "") or "").strip() == compra_id:
            c1, c2 = st.columns(2)
            if c1.button("Confirmar eliminación", key=f"{prefix}_delete_confirm", type="primary", use_container_width=True):
                deleted = compras_service().delete_compra_by_id(compra_id, df=compras_df)
                if not deleted:
                    st.warning("No se encontró la compra.")
                    return
                bump_compras_cache()
                st.session_state[COMPRAS_SELECTED_ID_KEY] = ""
                st.session_state[COMPRAS_EDIT_DIALOG_KEY] = False
                st.session_state.pop(COMPRAS_DELETE_STEP2_KEY, None)
                st.session_state[COMPRAS_SUCCESS_KEY] = "Compra eliminada."
                st.rerun()
            if c2.button("Cancelar eliminación", key=f"{prefix}_delete_cancel", use_container_width=True):
                st.session_state.pop(COMPRAS_DELETE_STEP2_KEY, None)
                st.session_state[COMPRAS_EDIT_DIALOG_KEY] = True
                st.rerun()


@st.dialog("Nueva compra", width="large", on_dismiss=_close_compras_new_dialog)
def _compras_new_dialog(compras_df: pd.DataFrame) -> None:
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown("### Alta de compra")
    with head2:
        if st.button("Cerrar", key="compras_new_close", use_container_width=True):
            _close_compras_new_dialog()
            st.rerun()
    _render_compra_form(_empty_row(), mode="new", compras_df=compras_df)


@st.dialog("Editar compra", on_dismiss=_close_compras_edit_dialog)
def _compras_edit_dialog(compras_df: pd.DataFrame) -> None:
    compra_id = str(st.session_state.get(COMPRAS_SELECTED_ID_KEY, "") or "").strip()
    if not compra_id:
        st.warning("No hay compra seleccionada.")
        return
    matches = compras_df[compras_df["compra_id"].astype(str).str.strip() == compra_id]
    if matches.empty:
        st.warning("La compra ya no existe.")
        return
    values = _row_dict(matches.iloc[0])
    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown(f"### {values.get('referencia') or values.get('descripcion') or compra_id[:8]}")
    with head2:
        if st.button("Cerrar", key="compras_edit_close", use_container_width=True):
            _close_compras_edit_dialog()
            st.rerun()
    _render_compra_form(values, mode="edit", compras_df=compras_df)


def _render_links_row(row: pd.Series) -> None:
    cols = st.columns([1, 1, 1, 1, 1])
    pi = str(row.get("proforma_invoice_url", "") or "").strip()
    folder = str(row.get("pis_comparativas_carpeta_url", "") or "").strip()
    payment = str(row.get("payment_receipt_url", "") or "").strip()
    compra_id = str(row.get("compra_id", "") or "").strip()
    if pi:
        cols[0].link_button("PI", pi, use_container_width=True)
    if folder:
        cols[1].link_button("Comparativas", folder, use_container_width=True)
    if payment:
        cols[2].link_button("Pago", payment, use_container_width=True)
    if cols[3].button("Editar", key=f"compras_edit_{compra_id}", use_container_width=True):
        st.session_state[COMPRAS_SELECTED_ID_KEY] = compra_id
        st.session_state[COMPRAS_EDIT_DIALOG_KEY] = True
        st.rerun()


def render(_: pd.DataFrame) -> None:
    st.title(page_menu_title("Compras"))
    st.caption("Seguimiento de compras, PIs comparativas y generación de Purchase Orders.")

    success = str(st.session_state.pop(COMPRAS_SUCCESS_KEY, "") or "").strip()
    if success:
        st.success(success)

    ver = st.session_state.get("compras_cache_version", 0)
    try:
        compras_df = load_compras_cached(ver)
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("Google Sheets sin cuota de lectura (429). Reintenta en unos segundos.")
            return
        raise

    pendientes, en_transito, recibidas_year = _kpi_metrics(compras_df)
    k1, k2, k3 = st.columns(3)
    k1.metric("Pendientes", pendientes)
    k2.metric("En tránsito", en_transito)
    k3.metric(f"Recibidas {date.today().year}", recibidas_year)

    if COMPRAS_VIEW_FILTER_KEY not in st.session_state:
        st.session_state[COMPRAS_VIEW_FILTER_KEY] = "Todas"

    toolbar1, toolbar2 = st.columns([3, 1])
    with toolbar1:
        query = st.text_input("Buscar", placeholder="Referencia, descripción, proveedor...", key="compras_search")
    with toolbar2:
        if st.button("+ Nueva compra", type="primary", use_container_width=True):
            st.session_state[COMPRAS_NEW_DIALOG_KEY] = True
            st.session_state.pop(f"{COMPRAS_PO_LINES_KEY}_new", None)
            st.rerun()

    proveedores = sorted(
        {str(x).strip() for x in compras_df.get("proveedor", pd.Series(dtype=str)).fillna("").astype(str).tolist() if str(x).strip()}
    )
    responsables = sorted(
        {str(x).strip() for x in compras_df.get("responsable", pd.Series(dtype=str)).fillna("").astype(str).tolist() if str(x).strip()}
    )
    f1, f2, f3 = st.columns(3)
    view = f1.radio(
        "Vista",
        ["Pendientes", "Completadas", "Todas"],
        horizontal=True,
        key=COMPRAS_VIEW_FILTER_KEY,
    )
    proveedor_filter = f2.selectbox("Proveedor", [""] + proveedores, key="compras_filter_proveedor")
    responsable_filter = f3.selectbox("Responsable", [""] + responsables, key="compras_filter_responsable")

    filtered = _sort_df(
        _filter_df(
            compras_df,
            view=view,
            query=query,
            proveedor=proveedor_filter,
            responsable=responsable_filter,
        ),
        view,
    )

    if filtered.empty:
        st.info("No hay compras que coincidan con los filtros.")
    else:
        for _, row in filtered.iterrows():
            estado = str(row.get("estado", "") or "").strip().lower()
            ref = str(row.get("referencia", "") or "").strip() or "—"
            desc = str(row.get("descripcion", "") or "").strip() or "—"
            prov = str(row.get("proveedor", "") or "").strip() or "—"
            importe = _format_importe(row)
            fecha = str(row.get("fecha_recepcion" if view == "Completadas" else "fecha_solicitud", "") or "").strip() or "—"
            with st.container(border=True):
                top = st.columns([1.0, 2.2, 1.0, 0.9, 1.0, 0.9])
                top[0].markdown(f"**{html.escape(ref)}**")
                top[1].write(desc)
                top[2].write(prov)
                top[3].markdown(f"**{html.escape(importe)}**")
                top[4].markdown(_estado_badge_html(estado), unsafe_allow_html=True)
                top[5].write(fecha)
                _render_links_row(row)

    if st.session_state.pop(COMPRAS_NEW_DIALOG_KEY, False):
        _compras_new_dialog(compras_df)
    if st.session_state.pop(COMPRAS_EDIT_DIALOG_KEY, False):
        _compras_edit_dialog(compras_df)
