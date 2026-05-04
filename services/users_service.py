from __future__ import annotations

from dataclasses import dataclass
import time

import pandas as pd

from app.navigation import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_SALES
from services.sheets_service import SheetsService

USERS_WS = "Usuarios CRM"
USER_HEADERS = ["nombre", "employee_id", "rol", "password"]


@dataclass(frozen=True)
class AppUser:
    employee_id: str
    nombre: str
    role: str
    password: str


def _default_users() -> list[AppUser]:
    role_by_name = {
        "Jiajun Xu": ROLE_SALES,
        "David Ortiz": ROLE_ADMIN,
        "Andrei Pop": ROLE_EMPLOYEE,
        "Viviana Castañeda": "agro_team",
        "Victor Gonzalez": ROLE_EMPLOYEE,
        "Pablo Sacristán": ROLE_EMPLOYEE,
        "Kabir Caravotta": ROLE_SALES,
        "Carla Moreno": "agro_team",
        "Carolina Simoes": ROLE_EMPLOYEE,
        "Marco Ruano": "agro_team",
    }
    return [
        AppUser(
            employee_id=f"EMP{idx:03d}",
            nombre=name,
            role=role,
            password="2026",
        )
        for idx, (name, role) in enumerate(role_by_name.items(), start=1)
    ]


def ensure_users_sheet_seed(sheets: SheetsService) -> None:
    """Seed the Users sheet only if it is genuinely empty (no rows, no API error)."""
    users_df, had_error = _read_users_df_with_retry(sheets)
    # Never overwrite when the empty result is caused by an API / quota error —
    # that would silently reset every user's password to the hardcoded default.
    if had_error or not users_df.empty:
        return
    rows = [
        {
            "nombre": user.nombre,
            "employee_id": user.employee_id,
            "rol": user.role,
            "password": user.password,
        }
        for user in _default_users()
    ]
    sheets.write_worksheet_df(USERS_WS, pd.DataFrame(rows), USER_HEADERS)


def load_users(sheets: SheetsService) -> list[AppUser]:
    ensure_users_sheet_seed(sheets)
    users_df, had_error = _read_users_df_with_retry(sheets)
    if users_df.empty:
        # Only fall back to hardcoded defaults as a last resort display fallback;
        # this data is never written back to Sheets from here.
        return _default_users()
    out: list[AppUser] = []
    for _, row in users_df.iterrows():
        employee_id = str(row.get("employee_id", "")).strip()
        nombre = str(row.get("nombre", "")).strip()
        role = str(row.get("rol", ROLE_EMPLOYEE)).strip().lower() or ROLE_EMPLOYEE
        password = str(row.get("password", "")).strip()
        if not employee_id or not nombre:
            continue
        out.append(AppUser(employee_id=employee_id, nombre=nombre, role=role, password=password))
    return out or _default_users()


def _read_users_df_with_retry(sheets: SheetsService) -> tuple[pd.DataFrame, bool]:
    """Return (dataframe, had_error).

    had_error=True means the sheet could not be read due to an API/network
    problem, so an empty dataframe must NOT be treated as "sheet is empty".
    """
    delays = (0.3, 0.9, 1.8)
    for idx, delay in enumerate(delays):
        try:
            df = sheets.read_worksheet_df(USERS_WS, USER_HEADERS)
            return df, False
        except Exception as exc:  # noqa: BLE001
            if idx == len(delays) - 1 or not _is_quota_error(exc):
                break
            time.sleep(delay)
    return pd.DataFrame(columns=USER_HEADERS), True


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "quota" in message or "429" in message or "rate limit" in message
