"""Resumen diario del CRM: próximas acciones y tareas de hoy, más lo atrasado.

Se usa en el envío automático de las 6:00 (``scripts/send_daily_digest.py``).
Todo el módulo es puro: recibe filas ya leídas de Google Sheets y devuelve
estructuras + HTML. Así se puede testear sin red y sin Streamlit.

Cuatro bloques, en este orden:

1. Próximas acciones para hoy (seguimiento comercial).
2. Tareas para hoy.
3. Seguimiento comercial atrasado que sigue pendiente.
4. Tareas atrasadas que siguen pendientes.

Una próxima acción se considera pendiente mientras la última fila de
seguimiento comercial de ese contacto siga apuntando a una fecha pasada: si
alguien registra un contacto nuevo, esa fila deja de ser la última y el
pendiente desaparece solo.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from services.sheet_date_format import parse_sheet_date
from services.tareas_validation import is_tarea_abierta

SIN_ENCARGADO = "Sin asignar"
SIN_CLIENTE = "Sin cliente"
SIN_DETALLE = "Sin detalle"

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def fecha_larga(day: date) -> str:
    return f"{_DIAS[day.weekday()]} {day.day} de {_MESES[day.month - 1]} de {day.year}"


def _clean(value: object) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class DigestItem:
    """Una línea del resumen: qué hay que hacer, quién y con qué cliente."""

    cliente: str
    detalle: str
    encargado: str
    fecha: str
    contexto: str = ""
    canal: str = ""
    dias_retraso: int = 0

    @property
    def fecha_orden(self) -> date:
        return parse_sheet_date(self.fecha) or date.max


@dataclass
class DailyDigest:
    dia: date
    acciones_hoy: list[DigestItem] = field(default_factory=list)
    tareas_hoy: list[DigestItem] = field(default_factory=list)
    acciones_atrasadas: list[DigestItem] = field(default_factory=list)
    tareas_atrasadas: list[DigestItem] = field(default_factory=list)

    @property
    def total_hoy(self) -> int:
        return len(self.acciones_hoy) + len(self.tareas_hoy)

    @property
    def total_atrasado(self) -> int:
        return len(self.acciones_atrasadas) + len(self.tareas_atrasadas)

    @property
    def total(self) -> int:
        return self.total_hoy + self.total_atrasado

    @property
    def vacio(self) -> bool:
        return self.total == 0


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
        if cid.strip():
            out[cid.strip()] = nombre.strip()
    return out


def _sort_key(row: dict[str, str]) -> tuple:
    """Última fila de seguimiento comercial de un contacto (fecha + hora)."""
    fecha = parse_sheet_date(_clean(row.get("fecha_contacto"))) or date.min
    hora = _clean(row.get("hora_contacto"))
    minutos = 0
    if ":" in hora:
        h, _, m = hora.partition(":")
        try:
            minutos = int(h) * 60 + int(m[:2])
        except ValueError:
            minutos = 0
    return (fecha, minutos)


def latest_accion_por_contacto(acciones_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Una fila por contacto: la más reciente por fecha y hora de contacto."""
    best: dict[str, tuple[tuple, dict[str, str]]] = {}
    for row in acciones_rows:
        cid = _clean(row.get("contact_id"))
        if not cid:
            continue
        key = _sort_key(row)
        prev = best.get(cid)
        if prev is None or key >= prev[0]:
            best[cid] = (key, row)
    return {cid: row for cid, (_, row) in best.items()}


def build_acciones_items(
    acciones_rows: list[dict[str, str]],
    *,
    contacts_df: pd.DataFrame | None = None,
    today: date | None = None,
) -> tuple[list[DigestItem], list[DigestItem]]:
    """(próximas acciones de hoy, próximas acciones atrasadas y aún pendientes)."""
    today_d = today or date.today()
    names = _contact_names(contacts_df)
    hoy: list[DigestItem] = []
    atrasadas: list[DigestItem] = []

    for cid, row in latest_accion_por_contacto(acciones_rows).items():
        fecha_raw = _clean(row.get("proxima_accion_fecha"))
        due = parse_sheet_date(fecha_raw)
        if due is None or due > today_d:
            continue
        cliente = _clean(row.get("nombre_cliente")) or names.get(cid, "") or SIN_CLIENTE
        detalle = _clean(row.get("proxima_accion_detalle")) or SIN_DETALLE
        encargado = (
            _clean(row.get("proxima_accion_persona"))
            or _clean(row.get("persona_contacto"))
            or SIN_ENCARGADO
        )
        canal = _clean(row.get("proxima_accion_canal"))
        ultimo = _clean(row.get("fecha_contacto"))
        if due == today_d:
            hoy.append(
                DigestItem(
                    cliente=cliente,
                    detalle=detalle,
                    encargado=encargado,
                    fecha=fecha_raw,
                    canal=canal,
                    contexto=f"Último contacto: {ultimo}" if ultimo else "",
                )
            )
        else:
            retraso = (today_d - due).days
            atrasadas.append(
                DigestItem(
                    cliente=cliente,
                    detalle=detalle,
                    encargado=encargado,
                    fecha=fecha_raw,
                    canal=canal,
                    contexto=f"Vencida hace {retraso} día{'s' if retraso != 1 else ''}",
                    dias_retraso=retraso,
                )
            )

    hoy.sort(key=lambda i: (i.encargado.lower(), i.cliente.lower()))
    atrasadas.sort(key=lambda i: (-i.dias_retraso, i.encargado.lower(), i.cliente.lower()))
    return hoy, atrasadas


def build_tareas_items(
    tareas_rows: list[dict[str, str]],
    *,
    contacts_df: pd.DataFrame | None = None,
    today: date | None = None,
) -> tuple[list[DigestItem], list[DigestItem]]:
    """(tareas con límite hoy, tareas con límite pasado y aún sin terminar)."""
    today_d = today or date.today()
    names = _contact_names(contacts_df)
    hoy: list[DigestItem] = []
    atrasadas: list[DigestItem] = []

    for row in tareas_rows:
        if not is_tarea_abierta(row.get("estado_tarea", "")):
            continue
        fecha_raw = _clean(row.get("fecha_limite"))
        due = parse_sheet_date(fecha_raw)
        if due is None or due > today_d:
            continue
        cid = _clean(row.get("contact_id"))
        cliente = _clean(row.get("nombre_cliente")) or names.get(cid, "") or SIN_CLIENTE
        titulo = _clean(row.get("titulo"))
        notas = _clean(row.get("notas"))
        detalle = " — ".join([p for p in (titulo, notas) if p]) or SIN_DETALLE
        encargado = (
            _clean(row.get("persona_gestiona"))
            or _clean(row.get("persona_creacion"))
            or SIN_ENCARGADO
        )
        tipo = _clean(row.get("tipo_tarea"))
        estado = _clean(row.get("estado_tarea"))
        contexto_base = " · ".join([p for p in (tipo, estado) if p])
        if due == today_d:
            hoy.append(
                DigestItem(
                    cliente=cliente,
                    detalle=detalle,
                    encargado=encargado,
                    fecha=fecha_raw,
                    contexto=contexto_base,
                )
            )
        else:
            retraso = (today_d - due).days
            sufijo = f"Vencida hace {retraso} día{'s' if retraso != 1 else ''}"
            atrasadas.append(
                DigestItem(
                    cliente=cliente,
                    detalle=detalle,
                    encargado=encargado,
                    fecha=fecha_raw,
                    contexto=" · ".join([p for p in (contexto_base, sufijo) if p]),
                    dias_retraso=retraso,
                )
            )

    hoy.sort(key=lambda i: (i.encargado.lower(), i.cliente.lower()))
    atrasadas.sort(key=lambda i: (-i.dias_retraso, i.encargado.lower(), i.cliente.lower()))
    return hoy, atrasadas


def build_daily_digest(
    *,
    acciones_rows: list[dict[str, str]],
    tareas_rows: list[dict[str, str]],
    contacts_df: pd.DataFrame | None = None,
    today: date | None = None,
) -> DailyDigest:
    today_d = today or date.today()
    acciones_hoy, acciones_atrasadas = build_acciones_items(
        acciones_rows, contacts_df=contacts_df, today=today_d
    )
    tareas_hoy, tareas_atrasadas = build_tareas_items(
        tareas_rows, contacts_df=contacts_df, today=today_d
    )
    return DailyDigest(
        dia=today_d,
        acciones_hoy=acciones_hoy,
        tareas_hoy=tareas_hoy,
        acciones_atrasadas=acciones_atrasadas,
        tareas_atrasadas=tareas_atrasadas,
    )


# ── Render ────────────────────────────────────────────────────────────────

_BRAND = "#2D6A4F"
_INK = "#1B2A22"
_MUTED = "#6B7A72"
_LINE = "#E2E8E4"
_BG = "#F5F7F6"
_AMBER = "#B45309"
_AMBER_BG = "#FEF6E7"

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
)


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def _item_html(item: DigestItem, *, acento: str) -> str:
    meta = " · ".join([p for p in (item.canal, item.contexto) if p])
    meta_html = (
        f"<div style=\"margin:6px 0 0;font-size:12px;color:{_MUTED};\">{_esc(meta)}</div>"
        if meta
        else ""
    )
    return (
        f'<tr><td style="padding:0 0 10px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1px solid {_LINE};border-left:3px solid {acento};border-radius:6px;'
        f'background:#FFFFFF;">'
        f'<tr><td style="padding:12px 14px;">'
        f'<div style="font-size:15px;font-weight:600;color:{_INK};line-height:1.35;">'
        f"{_esc(item.cliente)}</div>"
        f'<div style="margin:6px 0 0;font-size:14px;color:{_INK};line-height:1.5;">'
        f"{_esc(item.detalle)}</div>"
        f'<div style="margin:8px 0 0;font-size:13px;color:{_MUTED};">'
        f'Encargado: <span style="color:{_INK};font-weight:600;">{_esc(item.encargado)}</span>'
        f"&nbsp;&nbsp;·&nbsp;&nbsp;Fecha: {_esc(item.fecha)}</div>"
        f"{meta_html}"
        f"</td></tr></table></td></tr>"
    )


def _section_html(titulo: str, items: list[DigestItem], *, acento: str, vacio: str) -> str:
    cuerpo = (
        "".join(_item_html(item, acento=acento) for item in items)
        if items
        else (
            f'<tr><td style="padding:12px 14px;border:1px dashed {_LINE};border-radius:6px;'
            f'font-size:14px;color:{_MUTED};background:#FFFFFF;">{_esc(vacio)}</td></tr>'
        )
    )
    contador = (
        f'<span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:10px;'
        f'background:{_BG};color:{_MUTED};font-size:12px;font-weight:600;">{len(items)}</span>'
        if items
        else ""
    )
    return (
        f'<tr><td style="padding:24px 0 10px;">'
        f'<div style="font-size:13px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'color:{_INK};">{_esc(titulo)}{contador}</div>'
        f"</td></tr>"
        f'<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0">{cuerpo}</table></td></tr>'
    )


def render_digest_html(digest: DailyDigest) -> str:
    """Email HTML con tablas y estilos en línea, legible en Gmail y Outlook."""
    resumen = (
        f"{digest.total_hoy} para hoy · {digest.total_atrasado} pendiente"
        f"{'s' if digest.total_atrasado != 1 else ''} de días anteriores"
    )

    secciones = (
        _section_html(
            "Próxima acción · hoy",
            digest.acciones_hoy,
            acento=_BRAND,
            vacio="No hay próximas acciones fijadas para hoy.",
        )
        + _section_html(
            "Tareas · hoy",
            digest.tareas_hoy,
            acento=_BRAND,
            vacio="No hay tareas con fecha límite hoy.",
        )
    )

    pendientes = ""
    if digest.total_atrasado:
        pendientes = (
            f'<tr><td style="padding:28px 0 0;">'
            f'<div style="border-top:1px solid {_LINE};padding-top:20px;">'
            f'<div style="display:inline-block;padding:4px 10px;border-radius:4px;'
            f'background:{_AMBER_BG};color:{_AMBER};font-size:12px;font-weight:700;'
            f'letter-spacing:0.04em;text-transform:uppercase;">Pendiente de días anteriores</div>'
            f"</div></td></tr>"
            + _section_html(
                "Seguimiento comercial atrasado",
                digest.acciones_atrasadas,
                acento=_AMBER,
                vacio="Nada atrasado.",
            )
            + _section_html(
                "Tareas atrasadas",
                digest.tareas_atrasadas,
                acento=_AMBER,
                vacio="Nada atrasado.",
            )
        )

    return (
        '<!DOCTYPE html><html lang="es"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Resumen diario CRM · {_esc(digest.dia.strftime('%d/%m/%Y'))}</title>"
        "</head>"
        f'<body style="margin:0;padding:0;background:{_BG};">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_esc(resumen)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_BG};padding:24px 12px;">'
        '<tr><td align="center">'
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:640px;width:100%;background:#FFFFFF;border:1px solid {_LINE};'
        f'border-radius:10px;font-family:{_FONT};">'
        f'<tr><td style="padding:24px 28px 20px;border-bottom:1px solid {_LINE};'
        f'border-top:3px solid {_BRAND};border-radius:10px 10px 0 0;">'
        f'<div style="font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:{_BRAND};">Sanzar CRM</div>'
        f'<h1 style="margin:8px 0 0;font-size:20px;font-weight:650;color:{_INK};'
        f'letter-spacing:-0.01em;">Resumen diario</h1>'
        f'<div style="margin:6px 0 0;font-size:14px;color:{_MUTED};">'
        f"{_esc(fecha_larga(digest.dia))}</div>"
        f'<div style="margin:10px 0 0;font-size:13px;color:{_MUTED};">{_esc(resumen)}</div>'
        "</td></tr>"
        f'<tr><td style="padding:0 28px 28px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{secciones}{pendientes}"
        "</table></td></tr>"
        f'<tr><td style="padding:16px 28px 20px;border-top:1px solid {_LINE};font-size:12px;'
        f'color:{_MUTED};line-height:1.5;">'
        "Envío automático del CRM a las 6:00. Las próximas acciones salen del último "
        "seguimiento comercial de cada contacto; las tareas, del histórico de tareas."
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _item_texto(item: DigestItem) -> str:
    lineas = [
        f"  - {item.cliente}",
        f"    Detalle: {item.detalle}",
        f"    Encargado: {item.encargado}",
        f"    Fecha: {item.fecha}",
    ]
    meta = " · ".join([p for p in (item.canal, item.contexto) if p])
    if meta:
        lineas.append(f"    {meta}")
    return "\n".join(lineas)


def _seccion_texto(titulo: str, items: list[DigestItem], vacio: str) -> str:
    cuerpo = "\n\n".join(_item_texto(i) for i in items) if items else f"  {vacio}"
    return f"{titulo.upper()}\n{cuerpo}"


def render_digest_text(digest: DailyDigest) -> str:
    """Versión en texto plano (respaldo del correo HTML)."""
    bloques = [
        f"RESUMEN DIARIO CRM — {fecha_larga(digest.dia)}",
        f"{digest.total_hoy} para hoy · {digest.total_atrasado} pendientes de días anteriores",
        "",
        _seccion_texto(
            "Próxima acción · hoy", digest.acciones_hoy, "No hay próximas acciones para hoy."
        ),
        "",
        _seccion_texto("Tareas · hoy", digest.tareas_hoy, "No hay tareas con fecha límite hoy."),
    ]
    if digest.total_atrasado:
        bloques += [
            "",
            "PENDIENTE DE DÍAS ANTERIORES",
            "",
            _seccion_texto(
                "Seguimiento comercial atrasado", digest.acciones_atrasadas, "Nada atrasado."
            ),
            "",
            _seccion_texto("Tareas atrasadas", digest.tareas_atrasadas, "Nada atrasado."),
        ]
    return "\n".join(bloques)


def digest_subject(digest: DailyDigest) -> str:
    fecha = digest.dia.strftime("%d/%m/%Y")
    if digest.vacio:
        return f"CRM {fecha} · sin acciones ni tareas para hoy"
    partes = [f"{digest.total_hoy} para hoy"]
    if digest.total_atrasado:
        partes.append(f"{digest.total_atrasado} atrasado{'s' if digest.total_atrasado != 1 else ''}")
    return f"CRM {fecha} · {' · '.join(partes)}"
