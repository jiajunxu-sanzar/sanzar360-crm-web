from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from app.telemetry import timed
from config.settings import CONFIG
from services.inventory_service import normalize_inventory_serial_for_match
from services.sheet_date_format import is_valid_sensor_serial_number, normalize_sensor_serial_number
from services.sheets_service import SheetsService

HistoryKind = str
SubscriptionStatus = str


@dataclass(frozen=True)
class HistorySpec:
    kind: HistoryKind
    title: str
    worksheet_name: str
    id_column: str
    date_column: str
    headers: tuple[str, ...]
    summary_columns: tuple[str, ...]


@dataclass(frozen=True)
class SensorAsset:
    asset_type: str
    serial: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.asset_type.lower(), self.serial.lower())


@dataclass(frozen=True)
class SensorAssignmentConflict:
    asset: SensorAsset
    contact_id: str
    nombre_cliente: str
    fecha_inicio: str
    fecha_fin: str
    historial_sensor_id: str


@dataclass(frozen=True)
class SensorAssetOccurrence:
    asset: SensorAsset
    contact_id: str
    nombre_cliente: str
    fecha_inicio: str
    fecha_fin: str
    historial_sensor_id: str
    associated_with: str
    sensor_serial_number: str
    red: str
    red_otro: str
    tipo_operacion: str
    aws_user_id: str
    detalles: str


@dataclass(frozen=True)
class ProjectIotAssignment:
    projectiotid: str
    sensors: tuple[str, ...]


HISTORY_SPECS: dict[HistoryKind, HistorySpec] = {
    "sensores": HistorySpec(
        "sensores",
        "Histórico de sensores",
        "HistoricoSensores",
        "historial_sensor_id",
        "fecha_inicio",
        (
            "historial_sensor_id",
            "contact_id",
            "nombre_cliente",
            "fecha_inicio",
            "fecha_fin",
            "sensor_serial_number",
            "cantidad_sensores",
            "tipo_operacion",
            "estado_sensor",
            "estado_cierre_sensor",
            "ultima_revision",
            "red",
            "red_otro",
            "cuenta_usuario",
            "projectiotid",
            "aws_user_id",
            "detalles",
            "created_at",
            "updated_at",
        ),
        (
            "fecha_inicio",
            "fecha_fin",
            "estado_sensor",
            "ultima_revision",
            "cantidad_sensores",
            "tipo_operacion",
            "red",
        ),
    ),
    "campanas": HistorySpec(
        "campanas",
        "Histórico de campañas",
        "HistoricoCampanas",
        "historial_campana_id",
        "fecha_campana_inicio",
        (
            "historial_campana_id",
            "contact_id",
            "nombre_cliente",
            "historial_sensor_id",
            "nombre_campana",
            "fecha_campana_inicio",
            "fecha_campana_fin",
            "estado_cierre_campana",
            "dias_campana",
            "p_tabla",
            "k_1",
            "k_3",
            "k_5",
            "porcentaje_fase_1",
            "porcentaje_fase_2",
            "porcentaje_fase_3",
            "porcentaje_fase_4",
            "cultivo",
            "parcela",
            "coordenadas_parcela",
            "tipo_suelo",
            "detalles",
            "created_at",
            "updated_at",
        ),
        (
            "nombre_campana",
            "fecha_campana_inicio",
            "fecha_campana_fin",
            "cultivo",
            "parcela",
            "tipo_suelo",
        ),
    ),
    "suscripciones": HistorySpec(
        "suscripciones",
        "Histórico de suscripciones",
        "HistoricoSuscripciones",
        "historial_suscripcion_id",
        "fecha_pago",
        (
            "historial_suscripcion_id",
            "contact_id",
            "nombre_cliente",
            "fecha_pago",
            "cantidad_pago",
            "moneda",
            "suscripcion_fecha_inicio",
            "suscripcion_fecha_fin",
            "estado_suscripcion",
            "factura_url",
            "factura_pago_url",
            "metodo_pago",
            "detalles",
            "created_at",
            "updated_at",
        ),
        (
            "fecha_pago",
            "cantidad_pago",
            "suscripcion_fecha_inicio",
            "suscripcion_fecha_fin",
            "estado_suscripcion",
        ),
    ),
    "incidencias": HistorySpec(
        "incidencias",
        "Histórico de incidencias",
        "HistoricoIncidencias",
        "historial_incidencia_id",
        "fecha_apertura",
        (
            "historial_incidencia_id",
            "contact_id",
            "nombre_cliente",
            "fecha_apertura",
            "fecha_cierre",
            "tipo_incidencia",
            "estado",
            "prioridad",
            "historial_sensor_id",
            "sensor_serial_number",
            "historial_campana_id",
            "nombre_campana",
            "detalle",
            "resolucion",
            "created_at",
            "updated_at",
        ),
        (
            "fecha_apertura",
            "estado",
            "prioridad",
            "tipo_incidencia",
            "sensor_serial_number",
            "nombre_campana",
        ),
    ),
    "seguimiento_comercial": HistorySpec(
        "seguimiento_comercial",
        "Histórico de seguimiento comercial",
        CONFIG.google_activity_log_worksheet_name,
        "historial_accion_id",
        "fecha_contacto",
        (
            "historial_accion_id",
            "contact_id",
            "nombre_cliente",
            "resultado_contacto",
            "fecha_contacto",
            "hora_contacto",
            "persona_contacto",
            "canal_contacto",
            "email_url",
            "email_clasificacion",
            "notas_contacto",
            "proxima_accion_canal",
            "proxima_accion_persona",
            "proxima_accion_fecha",
            "proxima_accion_detalle",
            "origen_registro",
            "created_at",
            "updated_at",
        ),
        (
            "fecha_contacto",
            "hora_contacto",
            "persona_contacto",
            "canal_contacto",
            "resultado_contacto",
            "proxima_accion_fecha",
            "proxima_accion_persona",
        ),
    ),
}


def _today() -> str:
    return date.today().strftime("%d/%m/%Y")


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def _overlap(start_a: date | None, end_a: date | None, start_b: date | None, end_b: date | None) -> bool:
    min_date = date(1900, 1, 1)
    max_date = date(9999, 12, 31)
    a0, a1 = start_a or min_date, end_a or max_date
    b0, b1 = start_b or min_date, end_b or max_date
    return a0 <= b1 and b0 <= a1


def count_sensor_assets(sensor_serial_number: str) -> int:
    return len(parse_sensor_assets(sensor_serial_number))


def sensor_asset_tokens(sensor_serial_number: str) -> list[str]:
    """Return unique normalized sensor tokens like ``uc501-UC001``."""
    seen: set[str] = set()
    out: list[str] = []
    for asset, _ in parse_sensor_assets(sensor_serial_number):
        token = f"{asset.asset_type.lower()}-{asset.serial}"
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def sensor_association_tokens(sensor_serial_number: str) -> list[str]:
    """Return association tokens preserving comma-delimited pack/group inputs.

    For ProjectIoTId mapping, users expect each original comma-delimited item
    to be selectable as one token (e.g. ``uc501-a-b-c`` as a full pack).
    """
    value = (sensor_serial_number or "").strip()
    if not value:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in value.split(","):
        token = raw.strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def parse_projectiotid_assignments(raw: str) -> list[ProjectIotAssignment]:
    value = (raw or "").strip()
    if not value:
        return []
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        # Legacy single-value mode: treat whole cell as one project id.
        return [ProjectIotAssignment(projectiotid=value, sensors=tuple())]
    if not isinstance(payload, list):
        return []
    out: list[ProjectIotAssignment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("projectiotid", "") or "").strip()
        sensors_raw = item.get("sensors", [])
        if not pid:
            continue
        sensors: list[str] = []
        if isinstance(sensors_raw, list):
            for token in sensors_raw:
                token_clean = str(token or "").strip()
                if token_clean:
                    sensors.append(token_clean)
        out.append(ProjectIotAssignment(projectiotid=pid, sensors=tuple(sensors)))
    return out


def serialize_projectiotid_assignments(assignments: list[ProjectIotAssignment]) -> str:
    payload = [
        {"projectiotid": item.projectiotid, "sensors": list(item.sensors)}
        for item in assignments
        if item.projectiotid.strip()
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def validate_projectiotid_assignments(
    assignments: list[ProjectIotAssignment],
    available_tokens: list[str],
) -> str | None:
    allowed = {token.lower() for token in available_tokens}
    used: set[str] = set()
    for item in assignments:
        if not item.projectiotid.strip():
            return "Cada bloque ProjectIoTId debe tener un id."
        for token in item.sensors:
            key = token.lower()
            if key not in allowed:
                return f"El sensor asociado '{token}' no existe en sensor_serial_number."
            if key in used:
                return f"El sensor '{token}' no puede pertenecer a más de un ProjectIoTId."
            used.add(key)
    return None


def parse_sensor_assets(sensor_serial_number: str) -> list[tuple[SensorAsset, str]]:
    sensor_serial_number = normalize_sensor_serial_number(sensor_serial_number)
    if not is_valid_sensor_serial_number(sensor_serial_number):
        return []
    assets: list[tuple[SensorAsset, str]] = []
    current_gateway = ""
    for item in [part.strip() for part in (sensor_serial_number or "").split(",") if part.strip()]:
        lower = item.lower()
        if lower.startswith("uc501-"):
            parts = item.split("-")
            if len(parts) == 4:
                assets.extend(
                    [
                        (SensorAsset("uc501", parts[1]), item),
                        (SensorAsset("teros10", parts[2]), item),
                        (SensorAsset("sim", parts[3]), item),
                    ]
                )
            elif len(parts) == 2:
                assets.append((SensorAsset("uc501", parts[1]), item))
            current_gateway = ""
        elif lower.startswith("ug67-"):
            parts = item.split("-")
            if len(parts) == 3:
                gateway_token = f"ug67-{parts[1]}"
                current_gateway = gateway_token
                assets.extend(
                    [
                        (SensorAsset("ug67", parts[1]), gateway_token),
                        (SensorAsset("sim", parts[2]), gateway_token),
                    ]
                )
            elif len(parts) == 2:
                gateway_token = f"ug67-{parts[1]}"
                current_gateway = gateway_token
                assets.append((SensorAsset("ug67", parts[1]), gateway_token))
        elif lower.startswith("solenoide-"):
            serial = item.split("-", 1)[1].strip()
            assets.append((SensorAsset("solenoide", serial), item))
            current_gateway = ""
        elif lower.startswith("sim-"):
            serial = item.split("-", 1)[1].strip()
            assets.append((SensorAsset("sim", serial), item))
            current_gateway = ""
        elif "-" in item:
            asset_type, serial = item.split("-", 1)
            assets.append((SensorAsset(asset_type.lower(), serial), current_gateway or item))
    return assets


def parse_sensor_asset_occurrences(rows: list[dict[str, str]]) -> list[SensorAssetOccurrence]:
    occurrences: list[SensorAssetOccurrence] = []
    for row in rows:
        serial_text = row.get("sensor_serial_number", "")
        for asset, associated_with in parse_sensor_assets(serial_text):
            occurrences.append(
                SensorAssetOccurrence(
                    asset=asset,
                    contact_id=row.get("contact_id", ""),
                    nombre_cliente=row.get("nombre_cliente", ""),
                    fecha_inicio=row.get("fecha_inicio", ""),
                    fecha_fin=row.get("fecha_fin", ""),
                    historial_sensor_id=row.get("historial_sensor_id", ""),
                    associated_with=associated_with,
                    sensor_serial_number=serial_text,
                    red=row.get("red", ""),
                    red_otro=row.get("red_otro", ""),
                    tipo_operacion=row.get("tipo_operacion", ""),
                    aws_user_id=row.get("aws_user_id", ""),
                    detalles=row.get("detalles", ""),
                )
            )
    return occurrences


def sensor_serials_from_sensor_serial_number(sensor_serial_number: str) -> list[str]:
    """Return normalized serial values represented by a sensor history string."""
    seen: set[str] = set()
    serials: list[str] = []
    for asset, _ in parse_sensor_assets(sensor_serial_number):
        normalized = normalize_inventory_serial_for_match(asset.serial)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        serials.append(asset.serial)
    return serials


class HistoryService:
    def __init__(self, sheets_service: SheetsService) -> None:
        self._sheets_service = sheets_service
        self._frames: dict[HistoryKind, pd.DataFrame] = {
            kind: pd.DataFrame(columns=spec.headers) for kind, spec in HISTORY_SPECS.items()
        }
        self._loaded: set[HistoryKind] = set()
        self._row_numbers: dict[HistoryKind, dict[str, int]] = {kind: {} for kind in HISTORY_SPECS}
        self._sensor_occurrences_cache: list[SensorAssetOccurrence] | None = None

    def invalidate_all(self) -> None:
        self._frames = {
            kind: pd.DataFrame(columns=spec.headers) for kind, spec in HISTORY_SPECS.items()
        }
        self._loaded.clear()
        self._row_numbers = {kind: {} for kind in HISTORY_SPECS}
        self._sensor_occurrences_cache = None

    def load_all(self) -> None:
        for kind in HISTORY_SPECS:
            self.load_kind(kind, force=True)

    def load_kind(self, kind: HistoryKind, *, force: bool = False) -> None:
        if not force and kind in self._loaded:
            return
        spec = HISTORY_SPECS[kind]
        with timed("history.load_kind", kind=kind):
            df = self._sheets_service.read_worksheet_df(spec.worksheet_name, list(spec.headers))
            self._frames[kind] = self._normalize_dataframe(df, spec)
            framed = self._frames[kind]
            if spec.id_column in framed.columns:
                mapping: dict[str, int] = {}
                for idx, row_id in enumerate(framed[spec.id_column].astype(str).tolist(), start=2):
                    if row_id:
                        mapping[row_id] = idx
                self._row_numbers[kind] = mapping
            else:
                self._row_numbers[kind] = {}
            if kind == "sensores":
                self._sensor_occurrences_cache = None
            self._loaded.add(kind)

    def _normalize_dataframe(self, df: pd.DataFrame, spec: HistorySpec) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=spec.headers)
        df = df.fillna("").astype(str)
        for header in spec.headers:
            if header not in df.columns:
                df[header] = ""
        return df[list(spec.headers)]

    def frame(self, kind: HistoryKind) -> pd.DataFrame:
        self.load_kind(kind)
        return self._frames[kind].copy()

    def rows(self, kind: HistoryKind) -> list[dict[str, str]]:
        self.load_kind(kind)
        return self._frames[kind].to_dict("records")

    def rows_for_contact(self, kind: HistoryKind, contact_id: str) -> list[dict[str, str]]:
        self.load_kind(kind)
        df = self._frames[kind]
        if df.empty:
            return []
        sub = df[df["contact_id"].astype(str) == str(contact_id)]
        if sub.empty:
            return []
        rows = sub.to_dict("records")
        return sorted(rows, key=lambda row: _parse_date(row.get(HISTORY_SPECS[kind].date_column, "")) or date.min, reverse=True)

    def latest_for_contact(self, kind: HistoryKind, contact_id: str) -> dict[str, str] | None:
        rows = self.rows_for_contact(kind, contact_id)
        return rows[0] if rows else None

    def add_row(self, kind: HistoryKind, values: dict[str, str]) -> dict[str, str]:
        spec = HISTORY_SPECS[kind]
        self.load_kind(kind)
        now = _today()
        row = {header: str(values.get(header, "") or "") for header in spec.headers}
        row[spec.id_column] = row.get(spec.id_column) or str(uuid.uuid4())
        row["created_at"] = row.get("created_at") or now
        row["updated_at"] = now
        if kind == "sensores":
            row["cantidad_sensores"] = str(count_sensor_assets(row.get("sensor_serial_number", "")))
        if kind == "campanas":
            row["dias_campana"] = self._campaign_days(row)
        if kind == "seguimiento_comercial" and not str(row.get("origen_registro", "") or "").strip():
            row["origen_registro"] = "manual"
        self._sheets_service.append_worksheet_row(spec.worksheet_name, list(spec.headers), row)
        df = pd.concat([self._frames[kind], pd.DataFrame([row])], ignore_index=True)
        self._frames[kind] = self._normalize_dataframe(df, spec)
        self._row_numbers[kind] = self._sheets_service.row_numbers_by_id(spec.worksheet_name, spec.id_column)
        if kind == "sensores":
            self._sensor_occurrences_cache = None
        self._loaded.add(kind)
        return row

    def update_row(self, kind: HistoryKind, row_id: str, values: dict[str, str]) -> dict[str, str]:
        spec = HISTORY_SPECS[kind]
        self.load_kind(kind)
        df = self._frames[kind].copy()
        if df.empty or spec.id_column not in df.columns:
            raise ValueError(f"No existe {row_id}")
        mask = df[spec.id_column].astype(str) == str(row_id)
        if not mask.any():
            raise ValueError(f"No existe {row_id}")
        for header in spec.headers:
            if header in values:
                df.loc[mask, header] = str(values.get(header, "") or "")
        df.loc[mask, "updated_at"] = _today()
        if kind == "sensores":
            df.loc[mask, "cantidad_sensores"] = str(
                count_sensor_assets(str(df.loc[mask, "sensor_serial_number"].iloc[0]))
            )
        if kind == "campanas":
            df.loc[mask, "dias_campana"] = self._campaign_days(df.loc[mask].iloc[0].to_dict())
        updated_row = df.loc[mask].iloc[0].to_dict()
        row_number = self._row_numbers.get(kind, {}).get(str(row_id))
        if row_number is None:
            self._row_numbers[kind] = self._sheets_service.row_numbers_by_id(spec.worksheet_name, spec.id_column)
            row_number = self._row_numbers.get(kind, {}).get(str(row_id))
        if row_number is None:
            raise ValueError(f"No existe {row_id}")
        self._sheets_service.update_worksheet_row(
            spec.worksheet_name,
            list(spec.headers),
            row_number,
            updated_row,
        )
        self._frames[kind] = self._normalize_dataframe(df, spec)
        if kind == "sensores":
            self._sensor_occurrences_cache = None
        self._loaded.add(kind)
        return updated_row

    def delete_row(self, kind: HistoryKind, row_id: str) -> None:
        spec = HISTORY_SPECS[kind]
        self.load_kind(kind)
        df = self._frames[kind].copy()
        if df.empty or spec.id_column not in df.columns:
            raise ValueError(f"No existe {row_id}")
        mask = df[spec.id_column].astype(str) == str(row_id)
        if not mask.any():
            raise ValueError(f"No existe {row_id}")
        df = df.loc[~mask].copy()
        removed = self._sheets_service.delete_rows_where_column_equals(
            spec.worksheet_name,
            spec.id_column,
            str(row_id),
        )
        if removed < 1:
            raise ValueError(f"No existe {row_id}")
        self._frames[kind] = self._normalize_dataframe(df, spec)
        self._row_numbers[kind] = self._sheets_service.row_numbers_by_id(spec.worksheet_name, spec.id_column)
        if kind == "sensores":
            self._sensor_occurrences_cache = None
        self._loaded.add(kind)

    @staticmethod
    def _campaign_days(row: dict[str, str]) -> str:
        start = _parse_date(row.get("fecha_campana_inicio", ""))
        end = _parse_date(row.get("fecha_campana_fin", ""))
        if not start or not end:
            return ""
        return str(max(0, (end - start).days))

    def sensor_assignment_conflicts(
        self,
        candidate: dict[str, str],
        *,
        ignore_historial_sensor_id: str = "",
    ) -> list[SensorAssignmentConflict]:
        candidate_assets = {asset.key: asset for asset, _ in parse_sensor_assets(candidate.get("sensor_serial_number", ""))}
        if not candidate_assets:
            return []
        candidate_start = _parse_date(candidate.get("fecha_inicio", ""))
        candidate_end = _parse_date(candidate.get("fecha_fin", ""))
        candidate_contact_id = str(candidate.get("contact_id", ""))
        conflicts: list[SensorAssignmentConflict] = []
        for row in self.rows("sensores"):
            if ignore_historial_sensor_id and row.get("historial_sensor_id") == ignore_historial_sensor_id:
                continue
            estado = str(row.get("estado_cierre_sensor", "")).strip().lower()
            if estado == "cerrado":
                continue
            if str(row.get("contact_id", "")) == candidate_contact_id:
                continue
            if not _overlap(candidate_start, candidate_end, _parse_date(row.get("fecha_inicio", "")), _parse_date(row.get("fecha_fin", ""))):
                continue
            for asset, _ in parse_sensor_assets(row.get("sensor_serial_number", "")):
                if asset.key in candidate_assets:
                    conflicts.append(
                        SensorAssignmentConflict(
                            asset=asset,
                            contact_id=row.get("contact_id", ""),
                            nombre_cliente=row.get("nombre_cliente", ""),
                            fecha_inicio=row.get("fecha_inicio", ""),
                            fecha_fin=row.get("fecha_fin", ""),
                            historial_sensor_id=row.get("historial_sensor_id", ""),
                        )
                    )
        return conflicts

    def search_sensor_assets(self, query: str = "", asset_type: str = "") -> list[SensorAssetOccurrence]:
        query_norm = (query or "").strip().lower()
        type_norm = (asset_type or "").strip().lower()
        occurrences = self._sensor_occurrences()
        results: list[SensorAssetOccurrence] = []
        for occurrence in occurrences:
            if type_norm and occurrence.asset.asset_type.lower() != type_norm:
                continue
            haystack = {
                occurrence.asset.asset_type.lower(),
                occurrence.asset.serial.lower(),
                f"{occurrence.asset.asset_type.lower()}-{occurrence.asset.serial.lower()}",
                occurrence.associated_with.lower(),
                occurrence.nombre_cliente.lower(),
                occurrence.contact_id.lower(),
                occurrence.aws_user_id.lower(),
            }
            if query_norm and not any(query_norm in item for item in haystack):
                continue
            results.append(occurrence)
        return results

    def _sensor_occurrences(self) -> list[SensorAssetOccurrence]:
        if self._sensor_occurrences_cache is None:
            self._sensor_occurrences_cache = parse_sensor_asset_occurrences(self.rows("sensores"))
        return self._sensor_occurrences_cache

    def subscription_status_for_contact(self, contact_id: str) -> SubscriptionStatus:
        latest = self.latest_for_contact("suscripciones", contact_id)
        if not latest:
            return "inactiva"
        end = _parse_date(latest.get("suscripcion_fecha_fin", ""))
        if not end:
            return "activa" if latest.get("estado_suscripcion", "").lower() == "activa" else "inactiva"
        today = date.today()
        if end < today:
            return "inactiva"
        if end <= today + timedelta(days=31):
            return "caduca pronto"
        return "activa"

    def open_asset_serials(self, exclude_historial_id: str = "") -> set[str]:
        """Return lowercase serial numbers of all assets in open sensor history rows.

        Open = ``estado_cierre_sensor`` is not "cerrado".
        Pass ``exclude_historial_id`` to skip the row being edited (avoids
        marking the current record's assets as unavailable).
        """
        open_serials: set[str] = set()
        for row in self.rows("sensores"):
            if exclude_historial_id and row.get("historial_sensor_id", "") == exclude_historial_id:
                continue
            estado = str(row.get("estado_cierre_sensor", "")).strip().lower()
            if estado == "cerrado":
                continue
            ssn = str(row.get("sensor_serial_number", "")).strip()
            if not ssn:
                continue
            for asset, _ in parse_sensor_assets(ssn):
                open_serials.add(asset.serial.lower())
        return open_serials

    def open_sensor_assignment_rows_for_serials(
        self,
        serials: list[str],
        *,
        exclude_historial_sensor_id: str = "",
        exclude_contact_id: str = "",
    ) -> dict[str, dict[str, str]]:
        """Return current open sensor-history owners for the requested serials.

        Keys are normalized with the same rules inventory uses for serial
        matching, so quoted and unquoted serial values are equivalent.
        """
        wanted = {
            serial
            for serial in (normalize_inventory_serial_for_match(s) for s in serials)
            if serial
        }
        if not wanted:
            return {}

        candidate_rows: list[tuple[date, date, dict[str, str], set[str]]] = []
        for row in self.rows("sensores"):
            if exclude_historial_sensor_id and row.get("historial_sensor_id", "") == exclude_historial_sensor_id:
                continue
            if exclude_contact_id and str(row.get("contact_id", "") or "").strip() == exclude_contact_id:
                continue
            estado = str(row.get("estado_cierre_sensor", "")).strip().lower()
            if estado == "cerrado":
                continue
            row_serials = {
                normalize_inventory_serial_for_match(asset.serial)
                for asset, _ in parse_sensor_assets(str(row.get("sensor_serial_number", "") or ""))
            }
            matched = wanted & {s for s in row_serials if s}
            if not matched:
                continue
            candidate_rows.append(
                (
                    _parse_date(row.get("fecha_inicio", "")) or date.min,
                    _parse_date(row.get("updated_at", "")) or date.min,
                    row,
                    matched,
                )
            )

        assignments: dict[str, dict[str, str]] = {}
        for _, _, row, matched in sorted(candidate_rows, key=lambda item: (item[0], item[1]), reverse=True):
            for serial in matched:
                assignments.setdefault(serial, row)
        return assignments

    def has_open_incidents(self, contact_id: str) -> bool:
        from services.contact_sensor_overview import is_incidencia_abierta

        for row in self.rows_for_contact("incidencias", contact_id):
            if is_incidencia_abierta(row):
                return True
        return False
