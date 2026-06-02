from __future__ import annotations

import html


def _esc(value: object) -> str:
    return html.escape(str(value or "").strip())


def _value(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _line(label: str, value: str) -> str:
    if not value:
        return ""
    return f'<div class="sanzar-inv-card-line"><span class="sanzar-inv-card-label">{_esc(label)}:</span> {_esc(value)}</div>'


def _inventory_fields_for_model(model: str) -> list[tuple[str, str]]:
    m = (model or "").strip().lower()
    if m == "em500":
        return [
            ("EUI", "eui"),
            ("Gateway", "associated_gateway_inventory_id"),
            ("Estado logístico", "logistics_status"),
            ("Ubicación", "location_type"),
        ]
    if m == "uc501":
        return [
            ("SIM asociada", "associated_sim_inventory_id"),
            ("Probe asociada", "associated_probe_inventory_id"),
            ("Configurado", "configured"),
            ("Ubicación", "location_type"),
        ]
    if m == "ug67":
        return [
            ("EUI", "eui"),
            ("SIM asociada", "associated_sim_inventory_id"),
            ("Configurado", "configured"),
            ("Ubicación", "location_type"),
        ]
    if m == "sim":
        return [
            ("EID", "sim_eid_number"),
            ("Estado logístico", "logistics_status"),
            ("Ubicación", "location_type"),
        ]
    return [
        ("Estado logístico", "logistics_status"),
        ("Ubicación", "location_type"),
        ("Proveedor", "supplier"),
    ]


def build_inventory_card_html(row: dict[str, str]) -> str:
    model = _value(row, "model").lower()
    inv_id = _value(row, "inventory_id")
    serial = _value(row, "serial_number")
    lines = []
    for label, key in _inventory_fields_for_model(model):
        lines.append(_line(label, _value(row, key)))
    body = "".join(line for line in lines if line)
    return f"""
<article class="sanzar-inv-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(serial or "Sin serial")}</span>
    <span class="sanzar-inv-card-model">{_esc(model or "sin modelo")}</span>
  </div>
  <div class="sanzar-inv-card-meta">{_esc(inv_id)}</div>
  {body}
</article>
"""


def build_occurrence_card_html(row: dict[str, str]) -> str:
    estado = _value(row, "estado")
    estado_class = "sanzar-inv-state--en-uso" if estado.lower() == "en uso" else "sanzar-inv-state--disponible"
    return f"""
<article class="sanzar-inv-assoc-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(_value(row, "serial"))}</span>
    <span class="{estado_class}">{_esc(estado)}</span>
  </div>
  {_line("Tipo", _value(row, "tipo"))}
  {_line("Asociado con", _value(row, "asociado_con"))}
  {_line("Cliente", _value(row, "cliente"))}
  {_line("Inicio", _value(row, "fecha_inicio"))}
  {_line("Fin", _value(row, "fecha_fin"))}
</article>
"""


def build_association_group_html(
    role_label: str,
    serial_or_id: str,
    location_caption: str,
    children_lines: list[str],
    has_conflict: bool,
) -> str:
    conflict_badge = '<span class="sanzar-inv-state--disponible">Incidencia</span>' if has_conflict else ""
    children_html = "".join(children_lines) if children_lines else '<div class="sanzar-muted">Sin activos asociados.</div>'
    return f"""
<article class="sanzar-inv-assoc-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(role_label)} · {_esc(serial_or_id)}</span>
    {conflict_badge}
  </div>
  <div class="sanzar-inv-card-meta">{_esc(location_caption)}</div>
  {children_html}
</article>
"""


def build_conflict_card_html(title: str, description: str) -> str:
    return f"""
<article class="sanzar-inv-conflict-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(title)}</span>
  </div>
  <div class="sanzar-inv-card-line">{_esc(description)}</div>
</article>
"""
