from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pandas as pd

from config.settings import CULTIVOS_KC_HEADERS, CULTIVOS_KC_WORKSHEET_NAME
from services.locale_numbers import parse_locale_float, parse_p_tabla
from services.riego_umbrales import validar_cultivo
from services.sheets_service import SheetsService

DEFAULT_SEED_CULTIVO: dict[str, str] = {
    "nombre": "viña - uva",
    "L1": "30",
    "L2": "90",
    "L3": "130",
    "L4": "210",
    "kc_ini": "0.3",
    "kc_med": "0.7",
    "kc_fin": "0.45",
    "p_tabla": "0.4",
}


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def _nombre_key(value: object) -> str:
    return str(value or "").strip().lower()


class CultivosKcService:
    def __init__(self, sheets: SheetsService) -> None:
        self._sheets = sheets

    def ensure_structure(self) -> None:
        self._sheets.get_or_create_worksheet(CULTIVOS_KC_WORKSHEET_NAME, list(CULTIVOS_KC_HEADERS))

    def cultivos_df(self) -> pd.DataFrame:
        self.ensure_structure()
        return self._sheets.read_worksheet_df(CULTIVOS_KC_WORKSHEET_NAME, list(CULTIVOS_KC_HEADERS))

    def seed_if_empty(self, *, actor_name: str = "sistema") -> bool:
        """Inserta el cultivo por defecto si la hoja está vacía. Returns True if seeded."""
        df = self.cultivos_df()
        if not df.empty:
            return False
        self.upsert_cultivo(dict(DEFAULT_SEED_CULTIVO), actor_name=actor_name, mode="create")
        return True

    def list_cultivos(self) -> list[dict[str, Any]]:
        df = self.cultivos_df()
        if df.empty:
            return []
        rows = df.fillna("").astype(str).to_dict("records")
        out: list[dict[str, Any]] = []
        for row in rows:
            nombre = str(row.get("nombre", "") or "").strip()
            if not nombre:
                continue
            try:
                L1 = parse_locale_float(row["L1"])
                L2 = parse_locale_float(row["L2"])
                L3 = parse_locale_float(row["L3"])
                L4 = parse_locale_float(row["L4"])
                kc_ini = parse_locale_float(row["kc_ini"])
                kc_med = parse_locale_float(row["kc_med"])
                kc_fin = parse_locale_float(row["kc_fin"])
                if None in (L1, L2, L3, L4, kc_ini, kc_med, kc_fin):
                    continue
                out.append(
                    {
                        "cultivo_kc_id": str(row.get("cultivo_kc_id", "") or "").strip(),
                        "nombre": nombre,
                        "L1": L1,
                        "L2": L2,
                        "L3": L3,
                        "L4": L4,
                        "kc_ini": kc_ini,
                        "kc_med": kc_med,
                        "kc_fin": kc_fin,
                        "p_tabla": parse_p_tabla(row.get("p_tabla")),
                        "creado_por": str(row.get("creado_por", "") or ""),
                        "created_at": str(row.get("created_at", "") or ""),
                        "updated_at": str(row.get("updated_at", "") or ""),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        out.sort(key=lambda c: str(c["nombre"]).lower())
        return out

    def upsert_cultivo(
        self,
        values: dict[str, str],
        *,
        actor_name: str,
        mode: str = "create",
    ) -> str:
        self.ensure_structure()
        payload = {
            "nombre": str(values.get("nombre", "") or "").strip(),
            "L1": values.get("L1", ""),
            "L2": values.get("L2", ""),
            "L3": values.get("L3", ""),
            "L4": values.get("L4", ""),
            "kc_ini": values.get("kc_ini", ""),
            "kc_med": values.get("kc_med", ""),
            "kc_fin": values.get("kc_fin", ""),
            "p_tabla": values.get("p_tabla", ""),
        }
        validar_cultivo(payload)

        row = {h: str(values.get(h, "") or "") for h in CULTIVOS_KC_HEADERS}
        row["nombre"] = payload["nombre"]
        for key in ("L1", "L2", "L3", "L4", "kc_ini", "kc_med", "kc_fin"):
            parsed = parse_locale_float(payload[key])
            if parsed is None:
                raise ValueError(f"{key} no es un número válido.")
            row[key] = str(parsed)
        p_ok = parse_p_tabla(payload.get("p_tabla", ""))
        row["p_tabla"] = str(p_ok) if p_ok is not None else ""

        row_id = str(row.get("cultivo_kc_id", "") or "").strip()
        df = self.cultivos_df()
        names = (
            df["nombre"].fillna("").astype(str).map(_nombre_key)
            if not df.empty and "nombre" in df.columns
            else pd.Series(dtype=str)
        )
        target_name = _nombre_key(row["nombre"])

        if mode == "create" or not row_id:
            if not names.empty and target_name in set(names.tolist()):
                raise ValueError(f"Ya existe un cultivo con el nombre «{row['nombre']}».")
            row_id = str(uuid.uuid4())
            row["cultivo_kc_id"] = row_id
            row["creado_por"] = actor_name
            row["created_at"] = _today()
            row["updated_at"] = _today()
            self._sheets.append_worksheet_row(CULTIVOS_KC_WORKSHEET_NAME, list(CULTIVOS_KC_HEADERS), row)
            return row_id

        # edit
        row_num = self._sheets.row_numbers_by_id(CULTIVOS_KC_WORKSHEET_NAME, "cultivo_kc_id").get(row_id)
        if row_num is None:
            raise ValueError("No se encontró el cultivo a editar.")
        existing = df[df["cultivo_kc_id"].astype(str).str.strip() == row_id]
        if existing.empty:
            raise ValueError("No se encontró el cultivo a editar.")
        other = names.copy()
        if not other.empty:
            mask_other = df["cultivo_kc_id"].astype(str).str.strip() != row_id
            other_names = set(names[mask_other].tolist())
            if target_name in other_names:
                raise ValueError(f"Ya existe un cultivo con el nombre «{row['nombre']}».")
        ex = existing.iloc[0]
        row["creado_por"] = str(ex.get("creado_por", "") or "") or actor_name
        row["created_at"] = str(ex.get("created_at", "") or "") or _today()
        row["updated_at"] = _today()
        row["cultivo_kc_id"] = row_id
        self._sheets.update_worksheet_row(CULTIVOS_KC_WORKSHEET_NAME, list(CULTIVOS_KC_HEADERS), row_num, row)
        return row_id

    def delete_cultivo_by_id(self, cultivo_id: str, df: pd.DataFrame | None = None) -> bool:
        self.ensure_structure()
        clean_id = str(cultivo_id or "").strip()
        if not clean_id:
            return False
        source = df if df is not None else self.cultivos_df()
        if source.empty:
            return False
        ids = source.get("cultivo_kc_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        keep_mask = ids != clean_id
        if int((~keep_mask).sum()) == 0:
            return False
        kept = source[keep_mask].copy()
        self._sheets.write_worksheet_df(CULTIVOS_KC_WORKSHEET_NAME, kept, list(CULTIVOS_KC_HEADERS))
        return True
