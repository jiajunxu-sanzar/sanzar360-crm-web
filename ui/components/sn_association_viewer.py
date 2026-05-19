"""SN Association Viewer – popup that lets the user search any serial number
and see exactly where it is (history-based) and how it is wired to other
inventory assets (inventory-based hierarchical map).

Also surfaces integrity conflicts:
- Same SIM linked to more than one active asset
- Same probe linked to more than one UC501
- Association fields pointing to non-existent inventory IDs
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
import streamlit as st

from services.history_service import SensorAssetOccurrence
from services.inventory_service import normalize_model_name


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AssociationChild:
    role: str          # "sim" | "probe" | "sensor"
    inventory_id: str
    model: str
    serial_number: str
    sim_eid_number: str = ""


@dataclass
class AssociationGroup:
    """Root asset (UC501 or UG67) with all its linked children."""
    role: str          # "uc501" | "ug67"
    inventory_id: str
    model: str
    serial_number: str
    children: list[AssociationChild] = field(default_factory=list)
    location_type: str = ""      # e.g. "cliente" | "oficina" | ""
    location_detail: str = ""    # client name or other location detail


@dataclass
class IntegrityConflict:
    kind: str          # "sim_duplicate" | "probe_duplicate" | "broken_link"
    description: str
    affected_serials: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Association map builder (Fase 2)
# ---------------------------------------------------------------------------

_SIM_MODELS = {"sim"}
_PROBE_MODELS = {"teros10", "teros12"}
_UC501_MODELS = {"uc501"}
_UG67_MODELS = {"ug67"}
_SENSOR_MODELS = {"em500", "uc512", "em300"}


def build_inventory_association_map(
    inv_df: pd.DataFrame,
) -> tuple[list[AssociationGroup], list[IntegrityConflict]]:
    """Build hierarchical association tree + detect integrity conflicts.

    Returns (groups, conflicts).
    """
    if inv_df is None or inv_df.empty:
        return [], []

    df = inv_df.fillna("").astype(str).copy()

    # id → row mapping
    by_id: dict[str, dict[str, str]] = {}
    for row in df.to_dict("records"):
        iid = row.get("inventory_id", "").strip()
        if iid:
            by_id[iid] = row

    groups: list[AssociationGroup] = []

    # --- UC501 groups ---
    for row in df.to_dict("records"):
        model_norm = normalize_model_name(row.get("model", ""))
        if model_norm not in _UC501_MODELS:
            continue
        iid = row.get("inventory_id", "").strip()
        sim_id = row.get("associated_sim_inventory_id", "").strip()
        probe_id = row.get("associated_probe_inventory_id", "").strip()
        children: list[AssociationChild] = []
        if sim_id:
            sim_row = by_id.get(sim_id)
            eid = str(sim_row.get("sim_eid_number", "") or "").strip() if sim_row else ""
            children.append(AssociationChild(
                role="sim",
                inventory_id=sim_id,
                model=sim_row.get("model", "") if sim_row else "???",
                serial_number=sim_row.get("serial_number", sim_id[:8]) if sim_row else sim_id[:8],
                sim_eid_number=eid,
            ))
        if probe_id:
            probe_row = by_id.get(probe_id)
            children.append(AssociationChild(
                role="probe",
                inventory_id=probe_id,
                model=probe_row.get("model", "") if probe_row else "???",
                serial_number=probe_row.get("serial_number", probe_id[:8]) if probe_row else probe_id[:8],
            ))
        groups.append(AssociationGroup(
            role="uc501",
            inventory_id=iid,
            model=row.get("model", ""),
            serial_number=row.get("serial_number", ""),
            children=children,
            location_type=row.get("location_type", "").strip().lower(),
            location_detail=row.get("location_detail", "").strip(),
        ))

    # --- UG67 groups ---
    for row in df.to_dict("records"):
        model_norm = normalize_model_name(row.get("model", ""))
        if model_norm not in _UG67_MODELS:
            continue
        iid = row.get("inventory_id", "").strip()
        sim_id = row.get("associated_sim_inventory_id", "").strip()
        children = []
        if sim_id:
            sim_row = by_id.get(sim_id)
            eid = str(sim_row.get("sim_eid_number", "") or "").strip() if sim_row else ""
            children.append(AssociationChild(
                role="sim",
                inventory_id=sim_id,
                model=sim_row.get("model", "") if sim_row else "???",
                serial_number=sim_row.get("serial_number", sim_id[:8]) if sim_row else sim_id[:8],
                sim_eid_number=eid,
            ))
        # sensors that declare this UG67 as their gateway
        for child_row in df.to_dict("records"):
            if child_row.get("inventory_id", "").strip() == iid:
                continue
            child_gw = child_row.get("associated_gateway_inventory_id", "").strip()
            if child_gw == iid:
                children.append(AssociationChild(
                    role="sensor",
                    inventory_id=child_row.get("inventory_id", "").strip(),
                    model=child_row.get("model", ""),
                    serial_number=child_row.get("serial_number", ""),
                ))
        groups.append(AssociationGroup(
            role="ug67",
            inventory_id=iid,
            model=row.get("model", ""),
            serial_number=row.get("serial_number", ""),
            children=children,
            location_type=row.get("location_type", "").strip().lower(),
            location_detail=row.get("location_detail", "").strip(),
        ))

    conflicts = _detect_integrity_conflicts(df, by_id)
    return groups, conflicts


def _detect_integrity_conflicts(
    df: pd.DataFrame, by_id: dict[str, dict[str, str]]
) -> list[IntegrityConflict]:
    conflicts: list[IntegrityConflict] = []

    # Count how many rows reference each SIM / probe
    sim_usage: dict[str, list[str]] = {}      # sim_id → [row_serial, ...]
    probe_usage: dict[str, list[str]] = {}    # probe_id → [row_serial, ...]

    for row in df.to_dict("records"):
        owner_serial = row.get("serial_number", row.get("inventory_id", "?"))
        sim_id = row.get("associated_sim_inventory_id", "").strip()
        probe_id = row.get("associated_probe_inventory_id", "").strip()
        if sim_id:
            sim_usage.setdefault(sim_id, []).append(owner_serial)
        if probe_id:
            probe_usage.setdefault(probe_id, []).append(owner_serial)

    # SIM duplicate
    for sim_id, owners in sim_usage.items():
        if len(owners) > 1:
            sim_row = by_id.get(sim_id)
            sim_serial = sim_row.get("serial_number", sim_id[:8]) if sim_row else sim_id[:8]
            conflicts.append(IntegrityConflict(
                kind="sim_duplicate",
                description=(
                    f"SIM '{sim_serial}' está asociada a {len(owners)} activos simultáneamente: "
                    + ", ".join(owners)
                ),
                affected_serials=[sim_serial] + owners,
            ))

    # Probe duplicate
    for probe_id, owners in probe_usage.items():
        if len(owners) > 1:
            probe_row = by_id.get(probe_id)
            probe_serial = probe_row.get("serial_number", probe_id[:8]) if probe_row else probe_id[:8]
            conflicts.append(IntegrityConflict(
                kind="probe_duplicate",
                description=(
                    f"Sonda '{probe_serial}' está asociada a {len(owners)} UC501 simultáneamente: "
                    + ", ".join(owners)
                ),
                affected_serials=[probe_serial] + owners,
            ))

    # Broken links
    assoc_fields = [
        "associated_sim_inventory_id",
        "associated_probe_inventory_id",
        "associated_gateway_inventory_id",
    ]
    for row in df.to_dict("records"):
        owner_serial = row.get("serial_number", row.get("inventory_id", "?"))
        for fld in assoc_fields:
            ref_id = row.get(fld, "").strip()
            if ref_id and ref_id not in by_id:
                conflicts.append(IntegrityConflict(
                    kind="broken_link",
                    description=(
                        f"'{owner_serial}' referencia '{ref_id}' en '{fld}' "
                        "pero ese ID no existe en inventario."
                    ),
                    affected_serials=[owner_serial],
                ))

    return conflicts


# ---------------------------------------------------------------------------
# Occurrence helpers (Fase 1)
# ---------------------------------------------------------------------------

def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime((value or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _occurrences_to_df(occurrences: list[SensorAssetOccurrence]) -> pd.DataFrame:
    today = date.today()
    rows = []
    for o in occurrences:
        end = _parse_date(o.fecha_fin)
        active = end is None or end >= today
        rows.append({
            "tipo": o.asset.asset_type,
            "serial": o.asset.serial,
            "estado": "En uso" if active else "Disponible",
            "asociado_con": o.associated_with,
            "cliente": o.nombre_cliente,
            "contact_id": o.contact_id,
            "fecha_inicio": o.fecha_inicio,
            "fecha_fin": o.fecha_fin,
            "red": o.red,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["tipo", "serial", "estado", "asociado_con", "cliente", "contact_id", "fecha_inicio", "fecha_fin", "red"]
    )


def _filter_occurrences(
    occurrences: list[SensorAssetOccurrence],
    query: str,
    asset_type: str,
) -> list[SensorAssetOccurrence]:
    q = query.strip().lower()
    t = asset_type.strip().lower()
    out = []
    for o in occurrences:
        if t and o.asset.asset_type.lower() != t:
            continue
        if q:
            haystack = " ".join([
                o.asset.asset_type,
                o.asset.serial,
                o.associated_with,
                o.nombre_cliente,
                o.contact_id,
                o.aws_user_id,
                o.red,
            ]).lower()
            if q not in haystack:
                continue
        out.append(o)
    return out


def _group_matches_query(group: AssociationGroup, query: str) -> bool:
    """Returns True if this group's root or any child matches the query."""
    q = query.strip().lower()
    if not q:
        return True
    candidates = [group.serial_number, group.model, group.inventory_id]
    for child in group.children:
        candidates.extend([child.serial_number, child.model, child.inventory_id, child.sim_eid_number])
    return any(q in c.lower() for c in candidates)


# ---------------------------------------------------------------------------
# Role icons / labels
# ---------------------------------------------------------------------------

_ROLE_ICON = {
    "uc501": "📡",
    "ug67": "🌐",
    "sim": "📶",
    "probe": "🌱",
    "sensor": "📊",
}
_ROLE_LABEL = {
    "uc501": "UC501",
    "ug67": "UG67",
    "sim": "SIM",
    "probe": "Sonda",
    "sensor": "Sensor",
}
_CONFLICT_ICON = {
    "sim_duplicate": "⚠️",
    "probe_duplicate": "⚠️",
    "broken_link": "🔴",
}


# ---------------------------------------------------------------------------
# Streamlit dialog (Fase 1 + 2 + 4)
# ---------------------------------------------------------------------------

@st.dialog("Ver asociados por SN", width="large")
def render_sn_viewer_dialog(
    inv_df: pd.DataFrame,
    occurrences: list[SensorAssetOccurrence],
) -> None:
    """Full-screen popup for SN search + association map + integrity view."""

    # --- Build association map and conflicts from inventory ---
    groups, conflicts = build_inventory_association_map(inv_df)

    # --- Search controls ---
    st.markdown("### Buscar activo")
    col_q, col_t = st.columns([3, 1])
    query = col_q.text_input(
        "Serial number, cliente, asociación…",
        key="sn_viewer_query",
        placeholder="Ej: UC-0023, SIM-45, FincaEjemplo",
    )
    asset_type = col_t.selectbox(
        "Tipo",
        ["", "uc501", "ug67", "sim", "teros10", "teros12", "em500", "uc512", "em300"],
        key="sn_viewer_type",
        label_visibility="collapsed",
    )

    # --- Tabs ---
    conflict_label = f"Incidencias ({len(conflicts)})" if conflicts else "Incidencias"
    tab_list, tab_map, tab_conflicts = st.tabs(["Lista (historial)", "Mapa de asociación", conflict_label])

    # ---------------------------------------------------------------
    # Tab 1 – flat list from history occurrences
    # ---------------------------------------------------------------
    with tab_list:
        filtered_occ = _filter_occurrences(occurrences, query, asset_type)
        occ_df = _occurrences_to_df(filtered_occ)

        c1, c2, c3 = st.columns(3)
        c1.metric("Resultados", len(occ_df))
        in_use = int((occ_df.get("estado", pd.Series(dtype=str)) == "En uso").sum()) if not occ_df.empty else 0
        available = int((occ_df.get("estado", pd.Series(dtype=str)) == "Disponible").sum()) if not occ_df.empty else 0
        c2.metric("En uso", in_use)
        c3.metric("Disponibles", available)

        if occ_df.empty:
            if (query or asset_type):
                st.info("No se encontraron activos con esos criterios en el historial.")
            else:
                st.info("No hay datos de historial cargados.")
        else:
            st.dataframe(
                occ_df,
                width="stretch",
                hide_index=True,
                height=380,
                key="sn_viewer_occ_table",
                column_config={
                    "estado": st.column_config.TextColumn("Estado"),
                    "tipo": st.column_config.TextColumn("Tipo"),
                    "serial": st.column_config.TextColumn("Serial"),
                    "asociado_con": st.column_config.TextColumn("Asociado con"),
                    "cliente": st.column_config.TextColumn("Cliente"),
                    "fecha_inicio": st.column_config.TextColumn("Inicio"),
                    "fecha_fin": st.column_config.TextColumn("Fin"),
                    "red": st.column_config.TextColumn("Red"),
                    "contact_id": None,
                },
            )

    # ---------------------------------------------------------------
    # Tab 2 – hierarchical map from inventory associations
    # ---------------------------------------------------------------
    with tab_map:
        filtered_groups = [g for g in groups if _group_matches_query(g, query) and (not asset_type or asset_type.lower() in {g.role, normalize_model_name(g.model)})]

        if not filtered_groups:
            if groups:
                st.info("Ningún grupo coincide con la búsqueda.")
            else:
                st.info("No hay activos con asociaciones definidas en inventario.")
        else:
            st.caption(f"{len(filtered_groups)} grupo(s) encontrado(s)")
            for group in filtered_groups:
                icon = _ROLE_ICON.get(group.role, "📦")
                label = _ROLE_LABEL.get(group.role, group.role.upper())
                has_conflict = any(
                    group.serial_number in c.affected_serials
                    or any(ch.serial_number in c.affected_serials for ch in group.children)
                    for c in conflicts
                )
                header = f"{icon} **{label}** · `{group.serial_number or group.inventory_id[:8]}`"
                if has_conflict:
                    header += "  ⚠️"
                with st.expander(header, expanded=len(filtered_groups) <= 5):
                    if group.location_type == "cliente" and group.location_detail:
                        st.caption(f"Asignado a: **{group.location_detail}**")
                    elif group.location_type == "cliente":
                        st.caption("Asignado a cliente (sin nombre registrado)")
                    elif group.location_type == "oficina":
                        st.caption("Ubicación: oficina")
                    if not group.children:
                        st.caption("Sin activos asociados en inventario.")
                    else:
                        for child in group.children:
                            child_icon = _ROLE_ICON.get(child.role, "•")
                            child_label = _ROLE_LABEL.get(child.role, child.role)
                            child_conflict = any(
                                child.serial_number in c.affected_serials or child.inventory_id in c.affected_serials
                                for c in conflicts
                            )
                            flag = " ⚠️" if child_conflict else ""
                            eid_part = ""
                            if child.role == "sim" and child.sim_eid_number:
                                eid_part = f" · EID `{child.sim_eid_number}`"
                            st.markdown(
                                f"&nbsp;&nbsp;{child_icon} **{child_label}** · "
                                f"`{child.serial_number or child.inventory_id[:8]}`"
                                f"{eid_part}"
                                f" _(modelo: {child.model})_{flag}"
                            )

    # ---------------------------------------------------------------
    # Tab 3 – integrity conflicts (Fase 4)
    # ---------------------------------------------------------------
    with tab_conflicts:
        if not conflicts:
            st.success("No se detectaron incidencias de integridad.")
        else:
            st.error(f"Se encontraron **{len(conflicts)}** incidencia(s). Revisa y corrige en Inventario.")
            for c in conflicts:
                icon = _CONFLICT_ICON.get(c.kind, "⚠️")
                kind_label = {
                    "sim_duplicate": "SIM duplicada",
                    "probe_duplicate": "Sonda duplicada",
                    "broken_link": "Enlace roto",
                }.get(c.kind, c.kind)
                st.markdown(f"**{icon} {kind_label}:** {c.description}")
