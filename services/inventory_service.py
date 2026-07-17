from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import pandas as pd

from config.settings import (
    INVENTORY_HEADERS,
    INVENTORY_MODEL_FIELDS_WORKSHEET_NAME,
    INVENTORY_WORKSHEET_NAME,
    INVENTORY_MODEL_FIELD_HEADERS,
)
from services.sheets_service import SheetsService


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def normalize_model_name(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def normalize_field_key(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_inventory_serial_for_match(value: str) -> str:
    """Normalize inventory serials for comparisons without changing stored values."""
    serial = str(value or "").strip()
    if len(serial) >= 2 and serial[0] == serial[-1] and serial[0] in "\"'":
        serial = serial[1:-1].strip()
    return serial.lower()


def format_inventory_serial_with_quotes(value: str) -> str:
    """Wrap a serial in double quotes for storage when it is not already quoted."""
    serial = str(value or "").strip()
    if not serial:
        return serial
    if len(serial) >= 2 and serial[0] == serial[-1] and serial[0] in "\"'":
        return serial
    return f'"{serial}"'


@dataclass(frozen=True)
class InventoryAssetOption:
    inventory_id: str
    serial_number: str
    model: str
    label: str


@dataclass(frozen=True)
class RootAssetAssociations:
    """Associations (from Inventory) for a root asset (UC501 or UG67)."""
    sim: InventoryAssetOption | None
    probe: InventoryAssetOption | None          # UC501 → Teros10/12
    sensors: tuple[InventoryAssetOption, ...]   # UG67 → EM500/UC512/EM300 children


class InventoryService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_inventory_structure(self) -> None:
        self._sheets.get_or_create_worksheet(INVENTORY_WORKSHEET_NAME, list(INVENTORY_HEADERS))
        self._sheets.get_or_create_worksheet(INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, list(INVENTORY_MODEL_FIELD_HEADERS))

    def inventory_df(self) -> pd.DataFrame:
        self.ensure_inventory_structure()
        return self._sheets.read_worksheet_df(INVENTORY_WORKSHEET_NAME, list(INVENTORY_HEADERS))

    def model_fields_df(self) -> pd.DataFrame:
        self.ensure_inventory_structure()
        return self._sheets.read_worksheet_df(INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, list(INVENTORY_MODEL_FIELD_HEADERS))

    def upsert_inventory(self, values: dict[str, str], *, skip_conflict_check: bool = False) -> str:
        self.ensure_inventory_structure()
        row = {h: str(values.get(h, "") or "") for h in INVENTORY_HEADERS}
        row_id = row.get("inventory_id", "").strip() or str(uuid.uuid4())
        row["inventory_id"] = row_id
        if not skip_conflict_check:
            conflicts = self.check_association_conflicts(row)
            if conflicts:
                raise ValueError("\n".join(conflicts))
        row_num = self._sheets.row_numbers_by_id(INVENTORY_WORKSHEET_NAME, "inventory_id").get(row_id)
        if row_num is None:
            row["created_at"] = row.get("created_at") or _today()
        else:
            current_df = self.inventory_df()
            existing = current_df[current_df["inventory_id"].astype(str).str.strip() == row_id]
            existing_created = str(existing.iloc[0].get("created_at", "") or "").strip() if not existing.empty else ""
            row["created_at"] = row.get("created_at") or existing_created or _today()
        row["updated_at"] = _today()
        if row_num is None:
            self._sheets.append_worksheet_row(INVENTORY_WORKSHEET_NAME, list(INVENTORY_HEADERS), row)
        else:
            self._sheets.update_worksheet_row(INVENTORY_WORKSHEET_NAME, list(INVENTORY_HEADERS), row_num, row)
        return row_id

    def upsert_model_field(self, values: dict[str, str]) -> None:
        self.ensure_inventory_structure()
        row = {h: str(values.get(h, "") or "") for h in INVENTORY_MODEL_FIELD_HEADERS}
        row["model"] = normalize_model_name(row.get("model", ""))
        row["field_key"] = normalize_field_key(row.get("field_key", ""))
        row["created_at"] = row.get("created_at") or _today()
        row["updated_at"] = _today()
        df = self.model_fields_df()
        mask = (
            (df["model"].astype(str).apply(normalize_model_name) == row["model"])
            & (df["field_key"].astype(str).apply(normalize_field_key) == row["field_key"])
        ) if not df.empty else pd.Series(dtype=bool)
        if not df.empty and bool(mask.any()):
            df.loc[mask, :] = [row[h] for h in INVENTORY_MODEL_FIELD_HEADERS]
            self._sheets.write_worksheet_df(INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, df, list(INVENTORY_MODEL_FIELD_HEADERS))
        else:
            self._sheets.append_worksheet_row(INVENTORY_MODEL_FIELDS_WORKSHEET_NAME, list(INVENTORY_MODEL_FIELD_HEADERS), row)

    def merge_model_field_rows(self, rows: list[dict[str, str]]) -> None:
        """Insert or update many catalog rows in one read + one write (spares API quota)."""
        if not rows:
            return
        self.ensure_inventory_structure()
        today = _today()
        df = self.model_fields_df()
        if df.empty:
            df = pd.DataFrame(columns=list(INVENTORY_MODEL_FIELD_HEADERS))
        for col in INVENTORY_MODEL_FIELD_HEADERS:
            if col not in df.columns:
                df[col] = ""
        df = df.fillna("").astype(str)
        for raw in rows:
            row = {h: str(raw.get(h, "") or "") for h in INVENTORY_MODEL_FIELD_HEADERS}
            row["model"] = normalize_model_name(row.get("model", ""))
            row["field_key"] = normalize_field_key(row.get("field_key", ""))
            row["created_at"] = row.get("created_at") or today
            row["updated_at"] = today
            m = row["model"]
            fk = row["field_key"]
            mask = (
                df["model"].astype(str).apply(normalize_model_name) == m
            ) & (
                df["field_key"].astype(str).apply(normalize_field_key) == fk
            )
            if mask.any():
                idx = df.index[mask][0]
                for h in INVENTORY_MODEL_FIELD_HEADERS:
                    df.at[idx, h] = row[h]
            else:
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df = df[list(INVENTORY_MODEL_FIELD_HEADERS)].fillna("").astype(str)
        self._sheets.write_worksheet_df(
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME,
            df,
            list(INVENTORY_MODEL_FIELD_HEADERS),
        )

    def seed_model_fields_if_empty(self, rows: list[dict[str, str]]) -> bool:
        """Seed model field catalog using a single read + single write.

        Returns True when seed rows were written, False when catalog already had data.
        """
        self.ensure_inventory_structure()
        existing = self._sheets.read_worksheet_df(
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME,
            list(INVENTORY_MODEL_FIELD_HEADERS),
        )
        if not existing.empty:
            return False
        if not rows:
            return False
        normalized: list[dict[str, str]] = []
        today = _today()
        for raw in rows:
            row = {h: str(raw.get(h, "") or "") for h in INVENTORY_MODEL_FIELD_HEADERS}
            row["model"] = normalize_model_name(row.get("model", ""))
            row["field_key"] = normalize_field_key(row.get("field_key", ""))
            row["created_at"] = row.get("created_at") or today
            row["updated_at"] = row.get("updated_at") or today
            normalized.append(row)
        df = pd.DataFrame(normalized, columns=list(INVENTORY_MODEL_FIELD_HEADERS)).fillna("").astype(str)
        self._sheets.write_worksheet_df(
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME,
            df,
            list(INVENTORY_MODEL_FIELD_HEADERS),
        )
        return True

    def asset_options_by_models(self, models: tuple[str, ...], inv_df: pd.DataFrame | None = None) -> list[InventoryAssetOption]:
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return []
        wanted = {normalize_model_name(m) for m in models}
        out: list[InventoryAssetOption] = []
        for row in df.fillna("").astype(str).to_dict("records"):
            model = str(row.get("model", "")).strip()
            serial = str(row.get("serial_number", "")).strip()
            inv_id = str(row.get("inventory_id", "")).strip()
            if not inv_id or not serial:
                continue
            if normalize_model_name(model) not in wanted:
                continue
            out.append(
                InventoryAssetOption(
                    inventory_id=inv_id,
                    serial_number=serial,
                    model=model,
                    label=f"{model.upper()} · {serial} ({inv_id[:8]})",
                )
            )
        out.sort(key=lambda x: x.label.lower())
        return out

    def available_root_assets_for_history(
        self,
        models: tuple[str, ...],
        open_serials: set[str] | None = None,
        inv_df: pd.DataFrame | None = None,
    ) -> list[InventoryAssetOption]:
        """Like asset_options_by_models but filtered for assignment eligibility.

        An asset is eligible when:
        - ``location_type`` is not ``"cliente"`` (not currently assigned), AND
        - Its serial is not in ``open_serials`` (no open sensor history entry).
        """
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return []
        wanted = {normalize_model_name(m) for m in models}
        blocked = {
            serial
            for serial in (normalize_inventory_serial_for_match(s) for s in (open_serials or set()))
            if serial
        }
        out: list[InventoryAssetOption] = []
        for row in df.fillna("").astype(str).to_dict("records"):
            model = str(row.get("model", "")).strip()
            serial = str(row.get("serial_number", "")).strip()
            inv_id = str(row.get("inventory_id", "")).strip()
            if not inv_id or not serial:
                continue
            if normalize_model_name(model) not in wanted:
                continue
            if str(row.get("location_type", "")).strip().lower() == "cliente":
                continue
            if normalize_inventory_serial_for_match(serial) in blocked:
                continue
            out.append(InventoryAssetOption(
                inventory_id=inv_id,
                serial_number=serial,
                model=model,
                label=f"{model.upper()} · {serial} ({inv_id[:8]})",
            ))
        out.sort(key=lambda x: x.label.lower())
        return out

    def associations_for_root_asset(
        self,
        inventory_id: str,
        inv_df: pd.DataFrame | None = None,
    ) -> RootAssetAssociations:
        """Return SIM, probe (UC501) and child sensors (UG67) from Inventory.

        Inventory is the source of truth for associations; nothing is inferred
        from history strings here.
        """
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return RootAssetAssociations(sim=None, probe=None, sensors=())
        filled = df.fillna("").astype(str)
        rows = filled.to_dict("records")
        by_id: dict[str, dict[str, str]] = {
            r.get("inventory_id", "").strip(): r
            for r in rows
            if r.get("inventory_id", "").strip()
        }
        root = by_id.get(inventory_id.strip())
        if not root:
            return RootAssetAssociations(sim=None, probe=None, sensors=())

        def _to_option(row: dict[str, str] | None) -> InventoryAssetOption | None:
            if not row:
                return None
            iid = row.get("inventory_id", "").strip()
            serial = row.get("serial_number", "").strip()
            model = row.get("model", "").strip()
            if not iid or not serial:
                return None
            return InventoryAssetOption(
                inventory_id=iid,
                serial_number=serial,
                model=model,
                label=f"{model.upper()} · {serial}",
            )

        sim_id = root.get("associated_sim_inventory_id", "").strip()
        probe_id = root.get("associated_probe_inventory_id", "").strip()
        sim = _to_option(by_id.get(sim_id)) if sim_id else None
        probe = _to_option(by_id.get(probe_id)) if probe_id else None

        child_sensors: list[InventoryAssetOption] = []
        for r in rows:
            if r.get("inventory_id", "").strip() == inventory_id.strip():
                continue
            if r.get("associated_gateway_inventory_id", "").strip() == inventory_id.strip():
                opt = _to_option(r)
                if opt:
                    child_sensors.append(opt)
        child_sensors.sort(key=lambda x: x.label.lower())
        return RootAssetAssociations(sim=sim, probe=probe, sensors=tuple(child_sensors))

    def set_location_for_serials(
        self,
        serials: list[str],
        *,
        location_type: str,
        location_contact_id: str = "",
        location_detail: str = "",
    ) -> None:
        wanted = {
            serial
            for serial in (normalize_inventory_serial_for_match(s) for s in serials)
            if serial
        }
        if not wanted:
            return
        df = self.inventory_df()
        if df.empty:
            return
        changed = False
        for idx, row in df.iterrows():
            serial = normalize_inventory_serial_for_match(row.get("serial_number", ""))
            if serial not in wanted:
                continue
            df.at[idx, "location_type"] = location_type
            df.at[idx, "location_contact_id"] = location_contact_id if location_type == "cliente" else ""
            df.at[idx, "location_detail"] = location_detail
            df.at[idx, "updated_at"] = _today()
            changed = True
        if changed:
            self._sheets.write_worksheet_df(INVENTORY_WORKSHEET_NAME, df, list(INVENTORY_HEADERS))

    def reconcile_locations_for_serials(
        self,
        serials: list[str],
        open_assignments_by_serial: dict[str, dict[str, str]],
        *,
        default_location_type: str = "por_definir",
    ) -> None:
        """Recalculate inventory location for affected serials from open histories.

        ``open_assignments_by_serial`` is keyed by normalized serial and contains
        the open sensor-history row that currently owns that serial. Serial values
        are normalized for matching, but stored serial numbers are left untouched.
        """
        wanted = {
            serial
            for serial in (normalize_inventory_serial_for_match(s) for s in serials)
            if serial
        }
        if not wanted:
            return
        normalized_assignments = {
            normalize_inventory_serial_for_match(serial): row
            for serial, row in open_assignments_by_serial.items()
            if normalize_inventory_serial_for_match(serial)
        }
        fallback_location = (default_location_type or "por_definir").strip().lower()
        if fallback_location not in {"oficina", "por_definir"}:
            fallback_location = "por_definir"

        df = self.inventory_df()
        if df.empty:
            return
        changed = False
        for idx, row in df.iterrows():
            serial = normalize_inventory_serial_for_match(row.get("serial_number", ""))
            if serial not in wanted:
                continue
            assignment = normalized_assignments.get(serial)
            if assignment:
                new_location_type = "cliente"
                new_contact_id = str(assignment.get("contact_id", "") or "")
                new_detail = str(assignment.get("nombre_cliente", "") or "")
            else:
                new_location_type = fallback_location
                new_contact_id = ""
                new_detail = ""
            if (
                str(df.at[idx, "location_type"] or "") != new_location_type
                or str(df.at[idx, "location_contact_id"] or "") != new_contact_id
                or str(df.at[idx, "location_detail"] or "") != new_detail
            ):
                df.at[idx, "location_type"] = new_location_type
                df.at[idx, "location_contact_id"] = new_contact_id
                df.at[idx, "location_detail"] = new_detail
                df.at[idx, "updated_at"] = _today()
                changed = True
        if changed:
            self._sheets.write_worksheet_df(INVENTORY_WORKSHEET_NAME, df, list(INVENTORY_HEADERS))

    def count_inventory_by_model(self, model: str, inv_df: pd.DataFrame | None = None) -> int:
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return 0
        wanted = normalize_model_name(model)
        model_col = df.get("model", pd.Series(dtype=str)).fillna("").astype(str)
        return int((model_col.apply(normalize_model_name) == wanted).sum())

    def delete_model_fields_hard(self, model: str, model_fields_df: pd.DataFrame | None = None) -> int:
        self.ensure_inventory_structure()
        df = model_fields_df if model_fields_df is not None else self.model_fields_df()
        if df.empty:
            return 0
        wanted = normalize_model_name(model)
        model_col = df.get("model", pd.Series(dtype=str)).fillna("").astype(str)
        keep_mask = model_col.apply(normalize_model_name) != wanted
        removed = int((~keep_mask).sum())
        if removed <= 0:
            return 0
        cleaned = df[keep_mask].copy()
        for h in INVENTORY_MODEL_FIELD_HEADERS:
            if h not in cleaned.columns:
                cleaned[h] = ""
        self._sheets.write_worksheet_df(
            INVENTORY_MODEL_FIELDS_WORKSHEET_NAME,
            cleaned[list(INVENTORY_MODEL_FIELD_HEADERS)],
            list(INVENTORY_MODEL_FIELD_HEADERS),
        )
        return removed

    def check_association_conflicts(
        self,
        values: dict[str, str],
        inv_df: pd.DataFrame | None = None,
    ) -> list[str]:
        """Return a list of human-readable conflict messages.

        Checks whether one-to-one assets being associated are already linked to
        a different inventory item.  An empty list means the values are clean.

        ``values`` must include ``inventory_id`` (the item being saved) plus any
        association fields.
        """
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return []

        current_id = str(values.get("inventory_id", "") or "").strip()
        sim_id = str(values.get("associated_sim_inventory_id", "") or "").strip()
        probe_id = str(values.get("associated_probe_inventory_id", "") or "").strip()
        gw_id = str(values.get("associated_gateway_inventory_id", "") or "").strip()

        filled = df.fillna("").astype(str)
        messages: list[str] = []

        # Helper: find other rows that already reference the same association id
        def _conflicts_for(field: str, ref_id: str, label: str) -> list[str]:
            if not ref_id:
                return []
            col = filled.get(field, pd.Series(dtype=str)).str.strip()
            owner_serials = (
                filled[col == ref_id]
                .apply(
                    lambda r: r.get("serial_number") or r.get("inventory_id", "?"),
                    axis=1,
                )
                .tolist()
            )
            # Remove the current item from the collision list
            current_serial = str(values.get("serial_number", "") or current_id or "").strip()
            other = [s for s in owner_serials if s != current_serial and s != current_id]
            if other:
                ref_serial = self._serial_for_id(ref_id, filled)
                return [
                    f"La {label} '{ref_serial}' ya está asociada a: {', '.join(other)}. "
                    "Una misma unidad no puede estar en dos activos a la vez."
                ]
            return []

        messages.extend(_conflicts_for("associated_sim_inventory_id", sim_id, "SIM"))
        messages.extend(_conflicts_for("associated_probe_inventory_id", probe_id, "sonda"))
        inventory_ids = set(filled.get("inventory_id", pd.Series(dtype=str)).str.strip().tolist())

        # Verify referenced IDs exist in inventory
        for field, ref_id, label in [
            ("associated_sim_inventory_id", sim_id, "SIM"),
            ("associated_probe_inventory_id", probe_id, "sonda"),
            ("associated_gateway_inventory_id", gw_id, "gateway"),
        ]:
            if ref_id and ref_id not in inventory_ids:
                messages.append(
                    f"El ID de {label} '{ref_id}' no existe en inventario. "
                    "Verifica que el activo asociado esté dado de alta."
                )

        if gw_id and gw_id in inventory_ids:
            gateway_row = filled[filled.get("inventory_id", pd.Series(dtype=str)).str.strip() == gw_id].iloc[0]
            if normalize_model_name(str(gateway_row.get("model", "") or "")) != "ug67":
                messages.append(
                    f"El gateway asociado '{self._serial_for_id(gw_id, filled)}' debe ser un UG67."
                )

        return messages

    def _serial_for_id(self, inventory_id: str, filled_df: pd.DataFrame) -> str:
        """Return the serial number for an inventory_id, or a truncated ID fallback."""
        matches = filled_df[filled_df.get("inventory_id", pd.Series(dtype=str)).str.strip() == inventory_id]
        if not matches.empty:
            serial = str(matches.iloc[0].get("serial_number", "") or "").strip()
            if serial:
                return serial
        return inventory_id[:8]

    def delete_inventory_by_id(self, inventory_id: str, inv_df: pd.DataFrame | None = None) -> bool:
        self.ensure_inventory_structure()
        clean_id = str(inventory_id or "").strip()
        if not clean_id:
            return False
        df = inv_df if inv_df is not None else self.inventory_df()
        if df.empty:
            return False
        ids = df.get("inventory_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        keep_mask = ids != clean_id
        removed = int((~keep_mask).sum())
        if removed <= 0:
            return False
        cleaned = df[keep_mask].copy()
        for h in INVENTORY_HEADERS:
            if h not in cleaned.columns:
                cleaned[h] = ""
        self._sheets.write_worksheet_df(
            INVENTORY_WORKSHEET_NAME,
            cleaned[list(INVENTORY_HEADERS)],
            list(INVENTORY_HEADERS),
        )
        return True

