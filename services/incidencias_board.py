"""Tablero de Incidencias: clasificación por estado y payloads para las tarjetas.

Tres cubos, en este orden de prioridad:

1. ``cerrada``  — tiene ``fecha_cierre`` o su ``estado`` es de cierre.
2. ``pendiente`` — ``estado`` es «pendiente de aprobar» (revisión antes de dar
   la incidencia por buena/abierta).
3. ``abierta``  — cualquier otra cosa (abierta, en curso, bloqueada, vacío).

El resto de la app sigue usando ``is_incidencia_abierta`` de
``services.contact_sensor_overview``: una incidencia pendiente de aprobar NO
está resuelta, así que allí cuenta como abierta. Aquí se separa solo para la
pestaña Incidencias.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

import pandas as pd

from services.sheet_date_format import parse_sheet_date

ESTADO_PENDIENTE_APROBAR: str = "pendiente de aprobar"
ESTADO_ABIERTA: str = "abierta"
ESTADO_CERRADA: str = "cerrada"

BUCKET_ABIERTAS: str = "abiertas"
BUCKET_PENDIENTES: str = "pendientes"
BUCKET_CERRADAS: str = "cerradas"

BUCKET_LABELS: dict[str, str] = {
    BUCKET_ABIERTAS: "Abiertas",
    BUCKET_PENDIENTES: "Pendientes de aprobar",
    BUCKET_CERRADAS: "Cerradas",
}

_ESTADOS_CIERRE: frozenset[str] = frozenset({"cerrada", "cerrado", "resuelta", "resuelto"})
_ESTADOS_PENDIENTE: frozenset[str] = frozenset(
    {"pendiente de aprobar", "pendiente aprobar", "pendiente de aprobacion"}
)

VER_TODOS: str = "Ver todos"


def _norm(value: object) -> str:
    text = ("" if value is None else str(value)).strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def is_estado_cerrada(estado: object) -> bool:
    return _norm(estado) in _ESTADOS_CIERRE


def is_estado_pendiente_aprobar(estado: object) -> bool:
    return _norm(estado) in _ESTADOS_PENDIENTE


def incidencia_bucket(row: dict[str, str]) -> str:
    """Cubo del tablero para una fila de HistoricoIncidencias."""
    if str(row.get("fecha_cierre", "") or "").strip():
        return BUCKET_CERRADAS
    estado = row.get("estado", "")
    if is_estado_cerrada(estado):
        return BUCKET_CERRADAS
    if is_estado_pendiente_aprobar(estado):
        return BUCKET_PENDIENTES
    return BUCKET_ABIERTAS


@dataclass(frozen=True)
class IncidenciaCardPayload:
    incidencia_id: str
    contact_id: str
    cliente: str
    tipo: str
    estado: str
    prioridad: str
    fecha_apertura: str
    fecha_cierre: str
    detalle: str
    resolucion: str
    sensor: str
    campana: str
    bucket: str
    dias_abierta: int | None

    @property
    def antiguedad_label(self) -> str:
        if self.dias_abierta is None:
            return ""
        if self.bucket == BUCKET_CERRADAS:
            if self.dias_abierta == 0:
                return "Resuelta el mismo día"
            return f"Resuelta en {self.dias_abierta} día{'s' if self.dias_abierta != 1 else ''}"
        if self.dias_abierta == 0:
            return "Abierta hoy"
        return f"{self.dias_abierta} día{'s' if self.dias_abierta != 1 else ''} abierta"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _contact_names(contacts_df: pd.DataFrame | None) -> dict[str, str]:
    if contacts_df is None or contacts_df.empty:
        return {}
    if "contact_id" not in contacts_df.columns or "nombre" not in contacts_df.columns:
        return {}
    out: dict[str, str] = {}
    for cid, nombre in zip(
        contacts_df["contact_id"].fillna("").astype(str),
        contacts_df["nombre"].fillna("").astype(str),
    ):
        key = cid.strip()
        if key:
            out[key] = nombre.strip()
    return out


def _dias(fecha_apertura: str, fecha_cierre: str, *, today: date) -> int | None:
    inicio = parse_sheet_date(fecha_apertura)
    if inicio is None:
        return None
    fin = parse_sheet_date(fecha_cierre) or today
    delta = (fin - inicio).days
    return delta if delta >= 0 else None


def build_incidencia_payloads(
    rows: list[dict[str, str]],
    *,
    contacts_df: pd.DataFrame | None = None,
    today: date | None = None,
) -> list[IncidenciaCardPayload]:
    today_d = today or date.today()
    names = _contact_names(contacts_df)
    payloads: list[IncidenciaCardPayload] = []
    for row in rows:
        cid = _clean(row.get("contact_id"))
        cliente = _clean(row.get("nombre_cliente")) or names.get(cid, "") or "(sin cliente)"
        fecha_apertura = _clean(row.get("fecha_apertura"))
        fecha_cierre = _clean(row.get("fecha_cierre"))
        payloads.append(
            IncidenciaCardPayload(
                incidencia_id=_clean(row.get("historial_incidencia_id")),
                contact_id=cid,
                cliente=cliente,
                tipo=_clean(row.get("tipo_incidencia")) or "Incidencia",
                estado=_clean(row.get("estado")) or ESTADO_ABIERTA,
                prioridad=_clean(row.get("prioridad")),
                fecha_apertura=fecha_apertura,
                fecha_cierre=fecha_cierre,
                detalle=_clean(row.get("detalle")),
                resolucion=_clean(row.get("resolucion")),
                sensor=_clean(row.get("sensor_serial_number")),
                campana=_clean(row.get("nombre_campana")),
                bucket=incidencia_bucket(row),
                dias_abierta=_dias(fecha_apertura, fecha_cierre, today=today_d),
            )
        )
    return payloads


_PRIORIDAD_RANK: dict[str, int] = {"alta": 0, "media": 1, "baja": 2}


def _sort_key(payload: IncidenciaCardPayload) -> tuple:
    prioridad = _PRIORIDAD_RANK.get(_norm(payload.prioridad), 3)
    if payload.bucket == BUCKET_CERRADAS:
        cierre = parse_sheet_date(payload.fecha_cierre)
        return (0, -(cierre.toordinal() if cierre else 0), prioridad, _norm(payload.cliente))
    apertura = parse_sheet_date(payload.fecha_apertura)
    return (prioridad, apertura.toordinal() if apertura else 10**9, 0, _norm(payload.cliente))


def bucket_payloads(
    payloads: list[IncidenciaCardPayload],
    bucket: str,
) -> list[IncidenciaCardPayload]:
    """Payloads de un cubo, ya ordenados (abiertas: prioridad y más antigua primero)."""
    return sorted([p for p in payloads if p.bucket == bucket], key=_sort_key)


def bucket_counts(payloads: list[IncidenciaCardPayload]) -> dict[str, int]:
    counts = {BUCKET_ABIERTAS: 0, BUCKET_PENDIENTES: 0, BUCKET_CERRADAS: 0}
    for p in payloads:
        counts[p.bucket] = counts.get(p.bucket, 0) + 1
    return counts


def filter_payloads(
    payloads: list[IncidenciaCardPayload],
    *,
    cliente: str = "",
    tipo: str = "",
    prioridad: str = "",
    query: str = "",
) -> list[IncidenciaCardPayload]:
    """Filtros de la pestaña. Cadena vacía o ``VER_TODOS`` = sin filtrar."""

    def keep(p: IncidenciaCardPayload) -> bool:
        if cliente and cliente != VER_TODOS and p.cliente != cliente:
            return False
        if tipo and tipo != VER_TODOS and _norm(p.tipo) != _norm(tipo):
            return False
        if prioridad and prioridad != VER_TODOS and _norm(p.prioridad) != _norm(prioridad):
            return False
        q = _norm(query)
        if q:
            haystack = _norm(
                " ".join(
                    (p.cliente, p.tipo, p.detalle, p.resolucion, p.sensor, p.campana, p.incidencia_id)
                )
            )
            if q not in haystack:
                return False
        return True

    return [p for p in payloads if keep(p)]


def cliente_options(payloads: list[IncidenciaCardPayload]) -> list[str]:
    return [VER_TODOS] + sorted({p.cliente for p in payloads if p.cliente}, key=_norm)


def tipo_options(payloads: list[IncidenciaCardPayload]) -> list[str]:
    return [VER_TODOS] + sorted({p.tipo for p in payloads if p.tipo}, key=_norm)


def values_for_aprobar() -> dict[str, str]:
    """Aprobar una incidencia pendiente: pasa a abierta."""
    return {"estado": ESTADO_ABIERTA}


def values_for_marcar_pendiente() -> dict[str, str]:
    return {"estado": ESTADO_PENDIENTE_APROBAR}


def values_for_cerrar(*, resolucion: str = "", today: date | None = None) -> dict[str, str]:
    """Cerrar una incidencia: estado cerrada + fecha de cierre de hoy."""
    values = {
        "estado": ESTADO_CERRADA,
        "fecha_cierre": (today or date.today()).strftime("%d/%m/%Y"),
    }
    limpia = _clean(resolucion)
    if limpia:
        values["resolucion"] = limpia
    return values


def values_for_reabrir() -> dict[str, str]:
    """Reabrir una incidencia cerrada: estado abierta y sin fecha de cierre."""
    return {"estado": ESTADO_ABIERTA, "fecha_cierre": ""}
