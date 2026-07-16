from __future__ import annotations

import html


def _esc(value: object) -> str:
    return html.escape(str(value or "").strip())


def _value(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def clean_serial(value: str) -> str:
    """Quita comillas envolventes de un serial.

    En el Sheet muchos seriales numéricos se guardan como '"6126..."' para
    que Excel no los convierta a número; en la UI deben verse limpios.
    """
    v = str(value or "").strip()
    while len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].strip()
    return v


def _line(label: str, value: str) -> str:
    if not value:
        return ""
    return f'<div class="sanzar-inv-card-line"><span class="sanzar-inv-card-label">{_esc(label)}:</span> {_esc(value)}</div>'


def _kv(label: str, value: str, *, mono: bool = False) -> str:
    if not value:
        return ""
    cls = "sanzar-inv-kv-value sanzar-inv-kv-value--mono" if mono else "sanzar-inv-kv-value"
    return (
        '<div class="sanzar-inv-kv">'
        f'<span class="sanzar-inv-kv-label">{_esc(label)}</span>'
        f'<span class="{cls}">{_esc(value)}</span>'
        "</div>"
    )


_MODEL_CHIP_MODIFIER = {
    "em500": "em500",
    "uc501": "uc501",
    "uc512": "uc501",
    "em300": "em500",
    "ug67": "ug67",
    "sim": "sim",
    "solenoide": "solenoide",
    "teros10": "probe",
    "teros12": "probe",
}

_CONFIGURED_TRUE = {"si", "sí", "true", "1", "yes", "configurado"}


def _model_chip(model: str) -> str:
    modifier = _MODEL_CHIP_MODIFIER.get((model or "").strip().lower(), "default")
    label = (model or "sin modelo").upper()
    return f'<span class="sanzar-inv-chip sanzar-inv-chip--{modifier}">{_esc(label)}</span>'


def _pills_html(row: dict[str, str], contact_name_by_id: dict[str, str]) -> str:
    pills: list[str] = []
    estado = _value(row, "logistics_status")
    if estado:
        pills.append(f'<span class="sanzar-inv-pill sanzar-inv-pill--estado">{_esc(estado)}</span>')
    loc_type = _value(row, "location_type").replace("_", " ")
    loc_extra = contact_name_by_id.get(_value(row, "location_contact_id"), "") or _value(row, "location_detail")
    loc_txt = f"{loc_type} · {loc_extra}" if loc_type and loc_extra else (loc_type or loc_extra)
    if loc_txt:
        pills.append(f'<span class="sanzar-inv-pill sanzar-inv-pill--loc">{_esc(loc_txt)}</span>')
    if _value(row, "configured").lower() in _CONFIGURED_TRUE:
        pills.append('<span class="sanzar-inv-pill sanzar-inv-pill--ok">Configurado</span>')
    if not pills:
        return ""
    return f'<div class="sanzar-inv-card-pills">{"".join(pills)}</div>'


def _tech_fields_for_model(model: str) -> list[tuple[str, str, bool]]:
    """(etiqueta, columna, es_asociación) por modelo.

    Estado logístico, ubicación y configurado NO van aquí: se muestran
    como pills en la cabecera de la card.
    """
    m = (model or "").strip().lower()
    if m in {"em500", "em300", "uc512"}:
        return [("EUI", "eui", False), ("Gateway", "associated_gateway_inventory_id", True)]
    if m == "uc501":
        return [
            ("SIM asociada", "associated_sim_inventory_id", True),
            ("Sonda asociada", "associated_probe_inventory_id", True),
        ]
    if m == "ug67":
        return [("EUI", "eui", False), ("SIM asociada", "associated_sim_inventory_id", True)]
    if m == "sim":
        return [("EID", "sim_eid_number", False)]
    return [("Proveedor", "supplier", False)]


def build_inventory_card_html(
    row: dict[str, str],
    *,
    serial_by_id: dict[str, str] | None = None,
    contact_name_by_id: dict[str, str] | None = None,
) -> str:
    serial_by_id = serial_by_id or {}
    contact_name_by_id = contact_name_by_id or {}
    model = _value(row, "model")
    serial = clean_serial(_value(row, "serial_number")) or "Sin serial"

    items: list[str] = []
    for label, key, is_assoc in _tech_fields_for_model(model):
        raw = _value(row, key)
        if is_assoc:
            # Resuelve el inventory_id asociado a su serial legible; si no se
            # encuentra, enseña el id acortado en vez de un UUID entero.
            resolved = clean_serial(serial_by_id.get(raw, ""))
            display = resolved or (f"{raw[:8]}…" if len(raw) > 12 else raw)
        else:
            display = clean_serial(raw)
        items.append(_kv(label, display, mono=True))
    body = "".join(item for item in items if item)
    grid = f'<div class="sanzar-inv-card-grid">{body}</div>' if body else ""

    return f"""
<article class="sanzar-inv-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(serial)}</span>
    {_model_chip(model)}
  </div>
  {_pills_html(row, contact_name_by_id)}
  {grid}
</article>
"""


def build_occurrence_card_html(row: dict[str, str]) -> str:
    estado = _value(row, "estado")
    estado_class = "sanzar-inv-state--en-uso" if estado.lower() == "en uso" else "sanzar-inv-state--disponible"
    return f"""
<article class="sanzar-inv-assoc-card">
  <div class="sanzar-inv-card-head">
    <span class="sanzar-inv-card-sn">{_esc(clean_serial(_value(row, "serial")))}</span>
    <span class="{estado_class}">{_esc(estado)}</span>
  </div>
  {_line("Tipo", _value(row, "tipo"))}
  {_line("Asociado con", clean_serial(_value(row, "asociado_con")))}
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
    <span class="sanzar-inv-card-sn">{_esc(role_label)} · {_esc(clean_serial(serial_or_id))}</span>
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
