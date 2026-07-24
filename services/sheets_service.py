from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import gspread
import pandas as pd
import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.service_account import Credentials

from app.secrets import service_account_info
from app.telemetry import timed
from config.settings import CANONICAL_COLUMNS, CONFIG, PROJECT_ROOT
from models.contact import empty_contacts_dataframe

_T = TypeVar("_T")

# Waits (seconds) before each retry attempt: 3 retries → 4 attempts total.
_RETRY_WAITS_S = (1.5, 3.5, 7.0)


_TRANSIENT_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _is_transient_error(exc: BaseException) -> bool:
    """Return True for errors that are safe to retry (network / quota / server)."""
    if isinstance(exc, (ConnectionError, ConnectionResetError, OSError, TimeoutError, BrokenPipeError)):
        return True
    if isinstance(exc, gspread.exceptions.APIError):
        code = getattr(getattr(exc, "response", None), "status_code", 0)
        return int(code or 0) in _TRANSIENT_HTTP_STATUSES
    if isinstance(exc, requests.exceptions.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", 0)
        return int(code or 0) in _TRANSIENT_HTTP_STATUSES
    # requests.exceptions.ConnectionError and ProtocolError share the OSError base,
    # but some builds may not. Guard by checking the qualified name.
    qname = f"{type(exc).__module__}.{type(exc).__qualname__}"
    return qname in {
        "requests.exceptions.ConnectionError",
        "requests.exceptions.Timeout",
        "requests.exceptions.ReadTimeout",
        "urllib3.exceptions.ProtocolError",
        "urllib3.exceptions.MaxRetryError",
        "urllib3.exceptions.NewConnectionError",
        "http.client.RemoteDisconnected",
    }

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)


class SheetsService:
    def __init__(self, config=CONFIG) -> None:
        self.config = config
        self._spreadsheet: Any | None = None
        self._contacts_row_by_cid: dict[str, int] = {}
        self._worksheet_headers_cache: dict[str, list[str]] = {}
        # Cache de objetos Worksheet: ``spreadsheet.worksheet(name)`` de gspread
        # dispara una petición de metadatos en CADA llamada. Cachear el objeto
        # ahorra ~1 llamada API por operación de lectura/escritura.
        self._worksheet_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Retry infrastructure
    # ------------------------------------------------------------------

    def _with_retry(self, fn: Callable[[], _T]) -> _T:
        """Execute ``fn()`` with automatic retry on transient network/quota errors.

        On each failure the cached spreadsheet reference is cleared so the next
        attempt re-authenticates and opens a fresh connection.
        """
        last_exc: BaseException | None = None
        for attempt, wait in enumerate([0.0] + list(_RETRY_WAITS_S)):
            if wait > 0:
                jitter = random.uniform(0.0, wait * 0.25)
                time.sleep(wait + jitter)
            try:
                return fn()
            except BaseException as exc:
                if not _is_transient_error(exc):
                    raise
                last_exc = exc
                # Drop the cached spreadsheet so the next attempt reconnects.
                self._spreadsheet = None
                self._worksheet_cache = {}
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _credentials(self) -> Credentials:
        info = service_account_info()
        if info:
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        path = Path(self.config.google_service_account_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return Credentials.from_service_account_file(path, scopes=SCOPES)

    def client(self) -> gspread.Client:
        return gspread.authorize(self._credentials())

    def get_modified_time(self) -> str:
        """ISO timestamp del último ``modifiedTime`` del spreadsheet en Drive.

        Usa la API REST de Drive v3 con las credenciales del servicio existente.
        Llamada barata (no consume cuota de Sheets) usada por el poll de
        ``app.remote_sync`` para invalidar cachés cuando el Excel cambia.
        """
        file_id = self.config.google_sheet_id
        if not file_id:
            raise RuntimeError("GOOGLE_SHEET_ID no está configurado.")

        def _call() -> str:
            creds = self._credentials()
            if not getattr(creds, "valid", False):
                creds.refresh(GoogleAuthRequest())
            url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {creds.token}"},
                params={"fields": "modifiedTime", "supportsAllDrives": "true"},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            return str(payload.get("modifiedTime", "") or "")

        with timed("sheets.get_modified_time"):
            return self._with_retry(_call)

    def spreadsheet(self):
        if self._spreadsheet is None:
            if not self.config.google_sheet_id:
                raise RuntimeError("GOOGLE_SHEET_ID no está configurado.")
            self._spreadsheet = self._with_retry(
                lambda: self.client().open_by_key(self.config.google_sheet_id)
            )
        return self._spreadsheet

    def worksheet(self, name: str | None = None):
        name = name or self.config.google_worksheet_name
        cached = self._worksheet_cache.get(name)
        if cached is not None:
            return cached
        ws = self._with_retry(lambda: self.spreadsheet().worksheet(name))
        self._worksheet_cache[name] = ws
        return ws

    def worksheet_headers(self, name: str | None = None, *, force: bool = False) -> list[str]:
        """Cabeceras (fila 1) de una pestaña, cacheadas en memoria.

        Con ``force=True`` relee la fila 1 (1 llamada ligera) y refresca la caché.
        """
        name = name or self.config.google_worksheet_name
        if not force:
            cached = self._worksheet_headers_cache.get(name)
            if cached:
                return list(cached)
        ws = self.worksheet(name)
        headers = [str(h) for h in self._with_retry(lambda: ws.row_values(1))]
        if headers:
            self._worksheet_headers_cache[name] = list(headers)
        return headers

    def get_or_create_worksheet(self, name: str, headers: list[str]):
        # Fast path sin llamadas API: pestaña y cabeceras ya conocidas.
        cached_ws = self._worksheet_cache.get(name)
        cached_headers = self._worksheet_headers_cache.get(name, [])
        if cached_ws is not None and headers and cached_headers and all(h in cached_headers for h in headers):
            return cached_ws

        def _open() -> Any:
            sp = self.spreadsheet()
            try:
                ws = self._worksheet_cache.get(name) or sp.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = sp.add_worksheet(title=name, rows=1000, cols=max(1, len(headers)))
                ws.update([headers], "A1")
                self._worksheet_headers_cache[name] = list(headers)
                self._worksheet_cache[name] = ws
                return ws
            self._worksheet_cache[name] = ws
            cached = self._worksheet_headers_cache.get(name, [])
            if headers and cached and all(h in cached for h in headers):
                return ws
            current = ws.row_values(1)
            if not current:
                ws.update([headers], "A1")
                current = list(headers)
            else:
                missing = [header for header in headers if header not in current]
                if missing:
                    ws.update([current + missing], "A1")
                    current = current + missing
            self._worksheet_headers_cache[name] = [str(x) for x in current]
            return ws

        return self._with_retry(_open)

    def load_contacts_df(self) -> pd.DataFrame:
        with timed("sheets.load_contacts_df"):
            values = self._with_retry(lambda: self.worksheet().get_all_records())
        if not values:
            return empty_contacts_dataframe()
        df = pd.DataFrame(values).fillna("")
        for column in CANONICAL_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        df = df.astype(str)
        self._rebuild_contact_index(df)
        return df

    def _rebuild_contact_index(self, df: pd.DataFrame) -> None:
        self._contacts_row_by_cid = {}
        if "contact_id" not in df.columns:
            return
        for idx, contact_id in enumerate(df["contact_id"].astype(str).tolist(), start=2):
            if contact_id:
                self._contacts_row_by_cid[contact_id] = idx

    @staticmethod
    def _row_number_from_append_response(response: Any) -> int:
        """Extrae el número de fila (1-based) de la respuesta de ``append_row``.

        La API devuelve ``updates.updatedRange`` con formato ``'Hoja'!A42:R42``.
        Devuelve ``-1`` si no se puede determinar (p.ej. stubs de test).
        """
        try:
            rng = str(((response or {}).get("updates") or {}).get("updatedRange") or "")
        except AttributeError:
            return -1
        cell = rng.split("!")[-1].split(":")[0]
        digits = "".join(ch for ch in cell if ch.isdigit())
        try:
            return int(digits) if digits else -1
        except ValueError:
            return -1

    def refresh_contacts_row_index(self) -> dict[str, int]:
        """Reconstruye ``contact_id -> nº de fila`` leyendo SOLO la columna de ids.

        1 llamada API ligera (una columna) frente a ``get_all_values`` de la hoja
        completa. Es la fuente del índice usado por guardados y verificaciones.
        """
        headers = self.worksheet_headers()
        col_idx = self._column_index_in_header(headers, "contact_id")
        if col_idx is None:
            self._contacts_row_by_cid = {}
            return {}
        ws = self.worksheet()
        with timed("sheets.refresh_contacts_row_index"):
            column = self._with_retry(lambda: ws.col_values(col_idx + 1))
        mapping: dict[str, int] = {}
        for row_number, value in enumerate(column[1:], start=2):
            cid = str(value).strip()
            if cid:
                mapping[cid] = row_number
        self._contacts_row_by_cid = mapping
        return mapping

    def get_contact_row_fast(self, contact_id: str) -> dict[str, str] | None:
        """Lee UNA fila de contacto por id sin recorrer la hoja completa.

        Usa el índice en memoria (refrescándolo con una lectura de columna si
        hace falta) y valida que la fila leída corresponde al id pedido; si el
        índice quedó obsoleto (filas movidas por otra sesión), lo reconstruye
        una vez y reintenta.
        """
        target = str(contact_id or "").strip()
        if not target:
            return None
        headers = self.worksheet_headers()
        if not headers:
            return None

        def _read_row(row_number: int) -> dict[str, str]:
            ws = self.worksheet()
            with timed("sheets.get_contact_row_fast"):
                values = self._with_retry(lambda: ws.row_values(row_number))
            return {
                header: str(values[i]) if i < len(values) else ""
                for i, header in enumerate(headers)
            }

        row_number = self._contacts_row_by_cid.get(target) or self.refresh_contacts_row_index().get(target)
        if not row_number:
            return None
        row = _read_row(row_number)
        if str(row.get("contact_id", "")).strip() != target:
            row_number = self.refresh_contacts_row_index().get(target)
            if not row_number:
                return None
            row = _read_row(row_number)
            if str(row.get("contact_id", "")).strip() != target:
                return None
        return row

    def save_contacts_df(self, df: pd.DataFrame) -> None:
        df = df.fillna("").astype(str)
        for column in CANONICAL_COLUMNS:
            if column not in df.columns:
                df[column] = ""
        headers = list(df.columns)
        rows = [headers] + df[headers].values.tolist()
        ws = self.worksheet()
        with timed("sheets.save_contacts_df_full"):
            self._with_retry(lambda: (ws.clear(), ws.update(rows, "A1")))
        self._rebuild_contact_index(df)

    def append_contact_row(self, row: dict[str, str]) -> int:
        """Append a single Contacts row aligned to worksheet row 1 headers.

        Does not clear the sheet. Caller must ensure headers already exist.
        Returns the appended 1-based row number (``-1`` if unknown) parsed from
        the API response, updating the in-memory contact index without extra reads.
        """
        worksheet = self.worksheet()
        headers = self.worksheet_headers()
        if not headers:
            raise RuntimeError("append_contact_row requires an existing header row.")
        values = [str(row.get(header, "") or "") for header in headers]
        with timed("sheets.append_contact_row"):
            # RAW: evita que Sheets (locale es_ES) interprete "." como miles
            # (p. ej. "-3.4414" → "-34.414").
            response = self._with_retry(
                lambda: worksheet.append_row(values, value_input_option="RAW")
            )
        row_number = self._row_number_from_append_response(response)
        contact_id = str(row.get("contact_id", "") or "").strip()
        if contact_id and row_number > 1:
            self._contacts_row_by_cid[contact_id] = row_number
        return row_number

    def save_contact_rows_by_ids(self, df: pd.DataFrame, contact_ids: set[str]) -> None:
        if not contact_ids:
            return
        worksheet = self.worksheet()
        # Cabeceras SIEMPRE frescas antes de escribir una fila completa: una
        # columna añadida a mano por el admin desalinearía la escritura.
        headers = self.worksheet_headers(force=True)
        if not headers:
            self.save_contacts_df(df)
            return
        # Índice de filas con una lectura de columna (ligera), no toda la hoja.
        row_map = self.refresh_contacts_row_index()
        updates: list[dict[str, Any]] = []
        for contact_id in contact_ids:
            matches = df[df["contact_id"].astype(str) == str(contact_id)]
            if matches.empty:
                continue
            row_num = row_map.get(str(contact_id))
            if not row_num:
                blanks = int(df["contact_id"].fillna("").astype(str).str.strip().eq("").sum()) if "contact_id" in df.columns else -1
                dupes = (
                    int(df["contact_id"].fillna("").astype(str).str.strip().value_counts().gt(1).sum())
                    if "contact_id" in df.columns
                    else -1
                )
                with timed(
                    "sheets.save_contact_rows_missing_rownum_fallback",
                    contact_id=str(contact_id),
                    has_match=not matches.empty,
                    blanks=blanks,
                    duplicate_ids=dupes,
                ):
                    pass
                self.save_contacts_df(df)
                return
            row = matches.iloc[0]
            values = [str(row.get(header, "")) for header in headers]
            updates.append({"range": f"A{row_num}", "values": [values]})
        if updates:
            with timed("sheets.save_contact_rows_by_ids", rows=len(updates)):
                self._with_retry(lambda: worksheet.batch_update(updates))

    def read_worksheet_df(self, name: str, headers: list[str] | None = None) -> pd.DataFrame:
        worksheet = self.get_or_create_worksheet(name, headers or [])
        with timed("sheets.read_worksheet_df", worksheet=name):
            records = self._with_retry(lambda: worksheet.get_all_records())
        df = pd.DataFrame(records).fillna("")
        if headers:
            for header in headers:
                if header not in df.columns:
                    df[header] = ""
        return df.astype(str) if not df.empty else pd.DataFrame(columns=headers or [])

    def write_worksheet_df(self, name: str, df: pd.DataFrame, headers: list[str]) -> None:
        worksheet = self.get_or_create_worksheet(name, headers)
        df = df.fillna("").astype(str)
        for header in headers:
            if header not in df.columns:
                df[header] = ""
        rows = [headers] + df[headers].values.tolist()
        with timed("sheets.write_worksheet_df_full", worksheet=name, rows=max(0, len(rows) - 1)):
            self._with_retry(lambda: (worksheet.clear(), worksheet.update(rows, "A1")))
        self._worksheet_headers_cache[name] = list(headers)

    def _resolve_sheet_headers_for_write(self, name: str, required_headers: list[str]) -> tuple[Any, list[str]]:
        """Devuelve (worksheet, cabeceras en orden real de la fila 1).

        Siempre relee la fila 1 antes de escribir para no usar un orden de
        columnas distinto al de la hoja (evita datos en columnas locas).
        Añade columnas de ``required_headers`` que falten, con su título.
        """
        worksheet = self.get_or_create_worksheet(name, required_headers)
        raw = [str(h) for h in self._with_retry(lambda: worksheet.row_values(1))]
        while raw and not str(raw[-1]).strip():
            raw.pop()
        current = [str(h).strip() for h in raw]
        if not any(current):
            current = [h for h in required_headers if h]
            self._with_retry(lambda: worksheet.update([current], "A1"))
        else:
            # Conservar orden de la hoja; no reintroducir cabeceras vacías.
            current = [h for h in current if h]
            missing = [h for h in required_headers if h and h not in current]
            if missing:
                current = current + missing
                self._with_retry(lambda: worksheet.update([current], "A1"))
        self._worksheet_headers_cache[name] = list(current)
        return worksheet, list(current)

    def append_worksheet_row(self, name: str, headers: list[str], row: dict[str, Any]) -> int:
        """Añade una fila alineada al orden real de la fila 1.

        Devuelve el nº de fila (1-based) de ``updatedRange``, o ``-1`` si no se pudo.
        """
        worksheet, sheet_headers = self._resolve_sheet_headers_for_write(name, headers)
        values = [str(row.get(header, "") or "") for header in sheet_headers]
        with timed("sheets.append_worksheet_row", worksheet=name):
            response = self._with_retry(
                lambda: worksheet.append_row(values, value_input_option="RAW")
            )
            return self._row_number_from_append_response(response)

    def update_worksheet_row(self, name: str, headers: list[str], row_number: int, row: dict[str, Any]) -> None:
        worksheet, sheet_headers = self._resolve_sheet_headers_for_write(name, headers)
        values = [str(row.get(header, "") or "") for header in sheet_headers]
        with timed("sheets.update_worksheet_row", worksheet=name):
            self._with_retry(
                lambda: worksheet.update(
                    [values],
                    f"A{row_number}",
                    value_input_option="RAW",
                )
            )

    def row_numbers_by_id(self, name: str, id_column: str) -> dict[str, int]:
        """Mapa ``id -> nº de fila`` leyendo SOLO la columna de ids.

        Antes descargaba la hoja completa (``get_all_values``); ahora cuesta una
        lectura de una columna, con las cabeceras cacheadas en memoria.
        """
        worksheet = self.get_or_create_worksheet(name, [id_column])
        headers = self._worksheet_headers_cache.get(name) or self.worksheet_headers(name)
        idx = self._column_index_in_header([str(h) for h in headers], id_column)
        if idx is None:
            return {}
        with timed("sheets.row_numbers_by_id", worksheet=name):
            column = self._with_retry(lambda: worksheet.col_values(idx + 1))
        out: dict[str, int] = {}
        for row_number, value in enumerate(column[1:], start=2):
            row_id = str(value).strip()
            if row_id:
                out[row_id] = row_number
        return out

    def _get_worksheet_existing(self, title: str) -> Any | None:
        """Return the tab or ``None`` if it does not exist (does not create a new sheet)."""
        cached = self._worksheet_cache.get(title)
        if cached is not None:
            return cached
        try:
            ws = self.spreadsheet().worksheet(title)
        except gspread.WorksheetNotFound:
            return None
        self._worksheet_cache[title] = ws
        return ws

    @staticmethod
    def _column_index_in_header(header_row: list[str], column_name: str) -> int | None:
        want = (column_name or "").strip().lower()
        for i, raw in enumerate(header_row):
            if str(raw).strip().lower() == want:
                return i
        return None

    def _batch_delete_row_numbers(self, worksheet: Any, row_numbers_1based: list[int]) -> None:
        """Single Sheets API ``batchUpdate`` with ``deleteDimension`` (bottom rows first)."""
        unique_desc = sorted(set(row_numbers_1based), reverse=True)
        if not unique_desc:
            return
        sheet_id = worksheet.id
        requests: list[dict[str, Any]] = []
        for row in unique_desc:
            start_idx = row - 1
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": start_idx,
                            "endIndex": row,
                        }
                    }
                }
            )
        sp = self.spreadsheet()
        with timed("sheets.batch_delete_rows", rows=len(unique_desc)):
            self._with_retry(lambda: sp.batch_update({"requests": requests}))

    def delete_rows_where_column_equals(
        self,
        worksheet_title: str,
        column_name: str,
        value: str,
    ) -> int:
        """Elimina filas de datos donde ``column_name`` coincide con ``value`` (sin recrear la hoja).

        No crea la pestaña si falta. Cuenta como ~1 lectura + 1 escritura por llamada (batch de baja).
        Devuelve cuántas filas se borraron.
        """
        ws = self._get_worksheet_existing(worksheet_title)
        if ws is None:
            return 0
        target = str(value).strip()
        with timed("sheets.delete_rows_where_read", worksheet=worksheet_title):
            values = self._with_retry(lambda: ws.get_all_values())
        if len(values) < 2:
            return 0
        header = [str(h) for h in values[0]]
        col_idx = self._column_index_in_header(header, column_name)
        if col_idx is None:
            return 0
        rows_to_delete: list[int] = []
        for row_number in range(2, len(values) + 1):
            row = values[row_number - 1]
            cell = str(row[col_idx] if col_idx < len(row) else "").strip()
            if cell == target:
                rows_to_delete.append(row_number)
        if not rows_to_delete:
            return 0
        self._batch_delete_row_numbers(ws, rows_to_delete)
        return len(rows_to_delete)

    def contact_id_exists_on_contacts_sheet(self, contact_id: str) -> bool:
        """Comprueba si el id existe leyendo solo la columna de ids (1 llamada ligera)."""
        target = str(contact_id).strip()
        if not target:
            return False
        if self._get_worksheet_existing(self.config.google_worksheet_name) is None:
            return False
        with timed("sheets.contact_id_exists", worksheet=self.config.google_worksheet_name):
            mapping = self.refresh_contacts_row_index()
        return target in mapping

    @staticmethod
    def _column_letter(index_0based: int) -> str:
        """Índice de columna 0-based -> notación A1 (0->A, 25->Z, 26->AA, ...)."""
        n = index_0based + 1
        letters = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    def update_contact_field(self, contact_id: str, column: str, value: str) -> bool:
        """Actualiza UNA celda de un contacto por id, sin reescribir la fila entera.

        Pensado para operaciones puntuales desde rutas públicas sin login (p.ej.
        la baja de newsletter): cuesta como mucho 1 lectura de índice + 1
        escritura de celda, no una lectura/escritura de la hoja completa.
        Devuelve ``False`` si la columna no existe o el contacto no se encuentra.
        """
        target = str(contact_id or "").strip()
        if not target:
            return False
        headers = self.worksheet_headers()
        col_idx = self._column_index_in_header(headers, column)
        if col_idx is None:
            return False
        row_number = self._contacts_row_by_cid.get(target) or self.refresh_contacts_row_index().get(target)
        if not row_number:
            return False
        ws = self.worksheet()
        cell = f"{self._column_letter(col_idx)}{row_number}"
        with timed("sheets.update_contact_field"):
            self._with_retry(lambda: ws.update([[str(value)]], cell, value_input_option="RAW"))
        return True

    def get_contact_row_by_id(self, contact_id: str) -> dict[str, str] | None:
        df = self.load_contacts_df()
        target = str(contact_id or "").strip()
        if not target or "contact_id" not in df.columns:
            return None
        matches = df[df["contact_id"].astype(str).str.strip() == target]
        if matches.empty:
            return None
        return matches.iloc[0].fillna("").astype(str).to_dict()

    def verify_contact_subset(self, contact_id: str, expected_subset: dict[str, str]) -> bool:
        # Lectura de UNA fila (get_contact_row_fast) en vez de recargar la hoja
        # completa: antes cada verificación costaba una lectura de 350+ filas y
        # el guardado podía repetirla hasta 4 veces.
        row = self.get_contact_row_fast(contact_id)
        if row is None:
            return False
        for key, value in expected_subset.items():
            if str(row.get(str(key), "") or "").strip() != str(value or "").strip():
                return False
        return True

    # ------------------------------------------------------------------
    # Lectura multi-hoja en una sola llamada
    # ------------------------------------------------------------------

    @staticmethod
    def _values_to_df(values: list[list[Any]], headers: list[str] | None = None) -> pd.DataFrame:
        """Convierte la matriz de ``values.batchGet`` en DataFrame de strings.

        Replica la semántica de ``read_worksheet_df``: fila 1 como cabecera,
        celdas faltantes como cadena vacía y columnas requeridas garantizadas.
        """
        if not values:
            return pd.DataFrame(columns=list(headers or []))
        raw_header = [str(h) for h in values[0]]
        width = len(raw_header)
        rows: list[list[str]] = []
        for row in values[1:]:
            cells = [str(cell) for cell in row[:width]]
            cells.extend([""] * (width - len(cells)))
            rows.append(cells)
        df = pd.DataFrame(rows, columns=raw_header) if rows else pd.DataFrame(columns=raw_header)
        if headers:
            for header in headers:
                if header not in df.columns:
                    df[header] = ""
        return df.astype(str)

    def read_worksheets_batch(
        self,
        names: list[str],
        headers_by_name: dict[str, list[str]] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Lee varias pestañas en UNA llamada API (``values.batchGet``).

        Antes cada pestaña costaba 1-2 llamadas; los históricos (4-6 hojas) se
        leían en serie. No crea pestañas que falten: si alguna no existe la
        llamada falla y el llamador debe hacer fallback a ``read_worksheet_df``.
        """
        if not names:
            return {}
        headers_by_name = headers_by_name or {}
        ranges = [f"'{name}'" for name in names]
        sp = self.spreadsheet()
        with timed("sheets.read_worksheets_batch", worksheets=len(names)):
            response = self._with_retry(lambda: sp.values_batch_get(ranges))
        value_ranges = (response or {}).get("valueRanges", []) or []
        out: dict[str, pd.DataFrame] = {}
        for name, value_range in zip(names, value_ranges):
            values = (value_range or {}).get("values", []) or []
            out[name] = self._values_to_df(values, headers_by_name.get(name))
        for name in names:
            if name not in out:
                out[name] = pd.DataFrame(columns=list(headers_by_name.get(name, [])))
        return out
