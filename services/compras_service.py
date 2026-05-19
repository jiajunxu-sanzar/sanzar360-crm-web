from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date

import pandas as pd

from config.settings import (
    COMPRAS_ESTADOS,
    COMPRAS_ESTADOS_PENDIENTES,
    COMPRAS_HEADERS,
    COMPRAS_WORKSHEET_NAME,
)
from services.sheet_date_format import is_valid_dd_mm_yyyy
from services.sheets_service import SheetsService


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


@dataclass(frozen=True)
class PoLineItem:
    item_no: str
    description: str
    qty: float
    unit_price: float

    @property
    def total(self) -> float:
        return self.qty * self.unit_price


@dataclass(frozen=True)
class PoLineasPayload:
    items: tuple[PoLineItem, ...]
    tax_pct: float = 0.0
    shipping: float = 0.0
    other: float = 0.0
    show_shipping_table: bool = True
    requisitioner: str = "AGROAEROSPACE SL"
    ship_via: str = "Air"
    fob: str = "Yes"
    shipping_terms: str = "No insurance"
    comments: str = ""


def parse_po_lineas_json(raw: str) -> PoLineasPayload:
    text = (raw or "").strip()
    if not text:
        return PoLineasPayload(items=())
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return PoLineasPayload(items=())

    if isinstance(parsed, list):
        return PoLineasPayload(items=_parse_items(parsed))

    if isinstance(parsed, dict):
        items_raw = parsed.get("items", [])
        if not isinstance(items_raw, list):
            items_raw = []
        return PoLineasPayload(
            items=_parse_items(items_raw),
            tax_pct=_as_float(parsed.get("tax_pct", 0)),
            shipping=_as_float(parsed.get("shipping", 0)),
            other=_as_float(parsed.get("other", 0)),
            show_shipping_table=bool(parsed.get("show_shipping_table", True)),
            requisitioner=str(parsed.get("requisitioner", "AGROAEROSPACE SL") or "AGROAEROSPACE SL"),
            ship_via=str(parsed.get("ship_via", "Air") or "Air"),
            fob=str(parsed.get("fob", "Yes") or "Yes"),
            shipping_terms=str(parsed.get("shipping_terms", "No insurance") or "No insurance"),
            comments=str(parsed.get("comments", "") or ""),
        )
    return PoLineasPayload(items=())


def serialize_po_lineas_json(payload: PoLineasPayload) -> str:
    data = {
        "items": [
            {
                "item_no": item.item_no,
                "description": item.description,
                "qty": item.qty,
                "unit_price": item.unit_price,
            }
            for item in payload.items
        ],
        "tax_pct": payload.tax_pct,
        "shipping": payload.shipping,
        "other": payload.other,
        "show_shipping_table": payload.show_shipping_table,
        "requisitioner": payload.requisitioner,
        "ship_via": payload.ship_via,
        "fob": payload.fob,
        "shipping_terms": payload.shipping_terms,
        "comments": payload.comments,
    }
    return json.dumps(data, ensure_ascii=False)


def _parse_items(items_raw: list[object]) -> tuple[PoLineItem, ...]:
    out: list[PoLineItem] = []
    for idx, row in enumerate(items_raw):
        if not isinstance(row, dict):
            continue
        out.append(
            PoLineItem(
                item_no=str(row.get("item_no", idx + 1) or idx + 1),
                description=str(row.get("description", "") or ""),
                qty=_as_float(row.get("qty", 0)),
                unit_price=_as_float(row.get("unit_price", 0)),
            )
        )
    return tuple(out)


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def validate_compra_row(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    estado = str(values.get("estado", "") or "").strip().lower()
    if estado and estado not in COMPRAS_ESTADOS:
        errors.append(f"Estado inválido: {estado}. Valores: {', '.join(COMPRAS_ESTADOS)}.")

    for col in ("fecha_solicitud", "fecha_pedido", "fecha_recepcion"):
        raw = str(values.get(col, "") or "").strip()
        if raw and not is_valid_dd_mm_yyyy(raw):
            errors.append(f"{col} debe estar en formato DD/MM/AAAA.")

    if estado == "recibida" and not str(values.get("fecha_recepcion", "") or "").strip():
        errors.append("fecha_recepcion es obligatoria cuando estado es recibida.")

    raw_json = str(values.get("po_lineas_json", "") or "").strip()
    if raw_json:
        try:
            json.loads(raw_json)
        except json.JSONDecodeError:
            errors.append("po_lineas_json no es JSON válido.")
    return errors


def compra_warnings(values: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    estado = str(values.get("estado", "") or "").strip().lower()
    pi = str(values.get("proforma_invoice_url", "") or "").strip()
    if estado in {"pendiente", "en_transito", "recibida"} and not pi:
        warnings.append("Se recomienda indicar proforma_invoice_url para este estado.")
    return warnings


class ComprasService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure(self) -> None:
        self._sheets.get_or_create_worksheet(COMPRAS_WORKSHEET_NAME, list(COMPRAS_HEADERS))

    def compras_df(self) -> pd.DataFrame:
        self.ensure_structure()
        return self._sheets.read_worksheet_df(COMPRAS_WORKSHEET_NAME, list(COMPRAS_HEADERS))

    def upsert_compra(self, values: dict[str, str]) -> str:
        self.ensure_structure()
        row = {h: str(values.get(h, "") or "") for h in COMPRAS_HEADERS}
        row["estado"] = str(row.get("estado", "") or "comparando").strip().lower()
        errors = validate_compra_row(row)
        if errors:
            raise ValueError("\n".join(errors))

        row_id = row.get("compra_id", "").strip() or str(uuid.uuid4())
        row["compra_id"] = row_id
        row_num = self._sheets.row_numbers_by_id(COMPRAS_WORKSHEET_NAME, "compra_id").get(row_id)
        if row_num is None:
            row["created_at"] = row.get("created_at") or _today()
        else:
            current_df = self.compras_df()
            existing = current_df[current_df["compra_id"].astype(str).str.strip() == row_id]
            existing_created = str(existing.iloc[0].get("created_at", "") or "").strip() if not existing.empty else ""
            row["created_at"] = row.get("created_at") or existing_created or _today()
        row["updated_at"] = _today()

        if row_num is None:
            self._sheets.append_worksheet_row(COMPRAS_WORKSHEET_NAME, list(COMPRAS_HEADERS), row)
        else:
            self._sheets.update_worksheet_row(COMPRAS_WORKSHEET_NAME, list(COMPRAS_HEADERS), row_num, row)
        return row_id

    def delete_compra_by_id(self, compra_id: str, df: pd.DataFrame | None = None) -> bool:
        self.ensure_structure()
        clean_id = str(compra_id or "").strip()
        if not clean_id:
            return False
        source = df if df is not None else self.compras_df()
        if source.empty:
            return False
        ids = source.get("compra_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        keep_mask = ids != clean_id
        removed = int((~keep_mask).sum())
        if removed <= 0:
            return False
        cleaned = source[keep_mask].copy()
        for h in COMPRAS_HEADERS:
            if h not in cleaned.columns:
                cleaned[h] = ""
        self._sheets.write_worksheet_df(
            COMPRAS_WORKSHEET_NAME,
            cleaned[list(COMPRAS_HEADERS)],
            list(COMPRAS_HEADERS),
        )
        return True

    @staticmethod
    def is_pending(estado: str) -> bool:
        return str(estado or "").strip().lower() in COMPRAS_ESTADOS_PENDIENTES

    @staticmethod
    def is_completed(estado: str) -> bool:
        return str(estado or "").strip().lower() == "recibida"
