"""Tablero diario de Clientes: filtro, orden y helpers de visto/flags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from config.settings import TIPO_RELACION_OPCIONES

TIPO_RELACION_BOARD: frozenset[str] = frozenset({"Cliente", "Potencial cliente"})
VER_TODOS: str = "Ver todos"


def is_sheet_true(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "si", "sí"}


def sheet_bool_str(checked: bool) -> str:
    return "TRUE" if checked else "FALSE"


def parse_visto_fecha(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def is_visto_hoy(value: object, *, today: date | None = None) -> bool:
    parsed = parse_visto_fecha(value)
    if parsed is None:
        return False
    return parsed == (today or date.today())


def visto_fecha_hoy(*, today: date | None = None) -> str:
    return (today or date.today()).isoformat()


def filter_clientes_board(
    df: pd.DataFrame,
    responsable: str | None = None,
) -> pd.DataFrame:
    """Contactos con tipo_relacion Cliente/Potencial; opcionalmente por responsable_cliente."""
    if df is None or df.empty or "tipo_relacion" not in df.columns:
        return df.iloc[0:0].copy() if df is not None else pd.DataFrame()

    work = df.copy()
    tipo = work["tipo_relacion"].fillna("").astype(str).str.strip()
    mask = tipo.isin(TIPO_RELACION_BOARD)
    filtered = work.loc[mask].copy()

    resp = str(responsable or "").strip()
    if resp and resp != VER_TODOS:
        if "responsable_cliente" not in filtered.columns:
            return filtered.iloc[0:0].copy()
        owner = filtered["responsable_cliente"].fillna("").astype(str).str.strip()
        filtered = filtered.loc[owner == resp].copy()
    return filtered


def _tipo_sort_key(tipo: str) -> int:
    if tipo == "Cliente":
        return 0
    if tipo == "Potencial cliente":
        return 1
    return 2


def sort_clientes_board(df: pd.DataFrame, *, today: date | None = None) -> pd.DataFrame:
    """No vistos primero; luego Cliente antes que Potencial; luego nombre."""
    if df is None or df.empty:
        return df.iloc[0:0].copy() if df is not None else pd.DataFrame()

    work = df.copy()
    today_d = today or date.today()
    visto_col = (
        work["visto_cliente_fecha"]
        if "visto_cliente_fecha" in work.columns
        else pd.Series([""] * len(work), index=work.index)
    )
    work["_visto_hoy"] = visto_col.map(lambda v: is_visto_hoy(v, today=today_d))
    tipo_col = (
        work["tipo_relacion"].fillna("").astype(str).str.strip()
        if "tipo_relacion" in work.columns
        else pd.Series([""] * len(work), index=work.index)
    )
    work["_tipo_rank"] = tipo_col.map(_tipo_sort_key)
    nombre_col = (
        work["nombre"].fillna("").astype(str).str.strip().str.casefold()
        if "nombre" in work.columns
        else pd.Series([""] * len(work), index=work.index)
    )
    work["_nombre_sort"] = nombre_col
    work = work.sort_values(
        by=["_visto_hoy", "_tipo_rank", "_nombre_sort"],
        ascending=[True, True, True],
        kind="mergesort",
    )
    return work.drop(columns=["_visto_hoy", "_tipo_rank", "_nombre_sort"])


@dataclass(frozen=True)
class ClienteCardPayload:
    contact_id: str
    nombre: str
    tipo_relacion: str
    visto_hoy: bool
    umbrales_activadas: bool
    suelo_seco: bool
    num_sensores: str
    proxima_accion: str
    incidencias: str


def _overview_row(overview: pd.DataFrame, contact_id: str) -> dict[str, str]:
    if overview is None or overview.empty or "contact_id" not in overview.columns:
        return {}
    match = overview[overview["contact_id"].astype(str) == contact_id]
    if match.empty:
        return {}
    return {str(k): str(v or "") for k, v in match.iloc[0].to_dict().items()}


def _format_proxima(fecha: str, detalle: str) -> str:
    fecha_s = str(fecha or "").strip()
    detalle_s = str(detalle or "").strip()
    if fecha_s and detalle_s:
        return f"{fecha_s} · {detalle_s}"
    return fecha_s or detalle_s or "—"


def build_cliente_card_payloads(
    df: pd.DataFrame,
    overview: pd.DataFrame | None = None,
    *,
    today: date | None = None,
) -> list[ClienteCardPayload]:
    today_d = today or date.today()
    ov = overview if overview is not None else pd.DataFrame()
    payloads: list[ClienteCardPayload] = []
    for row in df.fillna("").astype(str).to_dict("records"):
        cid = str(row.get("contact_id", "") or "").strip()
        if not cid:
            continue
        ov_row = _overview_row(ov, cid)
        num = str(ov_row.get("num_sensores", "") or "").strip() or "0"
        prox = _format_proxima(
            str(ov_row.get("proxima_accion_fecha", "") or ""),
            str(ov_row.get("proxima_accion_detalle", "") or ""),
        )
        incid = str(ov_row.get("incidencias_abiertas", "") or "").strip()
        if not incid or incid == "0":
            incidencias = "Sin incidencias abiertas"
        else:
            detalle = str(ov_row.get("incidencias_detalle", "") or "").strip()
            incidencias = detalle or f"{incid} incidencia{'s' if incid != '1' else ''} abierta{'s' if incid != '1' else ''}"
        tipo = str(row.get("tipo_relacion", "") or "").strip()
        payloads.append(
            ClienteCardPayload(
                contact_id=cid,
                nombre=str(row.get("nombre", "") or "").strip() or "(sin nombre)",
                tipo_relacion=tipo if tipo in TIPO_RELACION_OPCIONES else tipo,
                visto_hoy=is_visto_hoy(row.get("visto_cliente_fecha", ""), today=today_d),
                umbrales_activadas=is_sheet_true(row.get("umbrales_activadas", "")),
                suelo_seco=is_sheet_true(row.get("suelo_seco", "")),
                num_sensores=num,
                proxima_accion=prox,
                incidencias=incidencias,
            )
        )
    return payloads


def values_for_visto_toggle(*, checked: bool, today: date | None = None) -> dict[str, str]:
    return {"visto_cliente_fecha": visto_fecha_hoy(today=today) if checked else ""}


def values_for_flag(field: str, *, checked: bool) -> dict[str, str]:
    if field not in {"umbrales_activadas", "suelo_seco"}:
        raise ValueError(f"Campo de flag no válido: {field}")
    return {field: sheet_bool_str(checked)}
