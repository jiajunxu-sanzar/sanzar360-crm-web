from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
import streamlit as st

from app.cache import history_service, inventory_service, load_inventory_cached, load_inventory_model_fields_cached
from app.state import bump_inventory_cache
from config.settings import INVENTORY_HEADERS, INVENTORY_MODEL_FIELD_HEADERS
from services.inventory_service import normalize_model_name
from ui.components.sn_association_viewer import render_sn_viewer_dialog

DEFAULT_MODEL_FIELDS: dict[str, list[str]] = {
    "uc501": ["serial_number", "brand", "supplier", "logistics_status", "location_type", "configured", "associated_sim_inventory_id", "associated_probe_inventory_id", "proforma_invoice_url", "payment_receipt_url"],
    "sim": ["serial_number", "brand", "supplier", "logistics_status", "location_type", "proforma_invoice_url", "payment_receipt_url"],
    "teros10": ["serial_number", "brand", "supplier", "logistics_status", "location_type", "proforma_invoice_url", "payment_receipt_url"],
    "teros12": ["serial_number", "brand", "supplier", "logistics_status", "location_type", "proforma_invoice_url", "payment_receipt_url"],
    "uc512": ["serial_number", "eui", "brand", "supplier", "logistics_status", "location_type", "configured", "proforma_invoice_url", "payment_receipt_url"],
    "em300": ["serial_number", "eui", "brand", "supplier", "logistics_status", "location_type", "configured", "proforma_invoice_url", "payment_receipt_url"],
    "em500": ["serial_number", "eui", "brand", "supplier", "logistics_status", "location_type", "gateway_config_name", "ui_password", "proforma_invoice_url", "payment_receipt_url"],
    "ug67": ["serial_number", "eui", "brand", "supplier", "logistics_status", "location_type", "configured", "ui_password", "proforma_invoice_url", "payment_receipt_url"],
    "solenoide": ["serial_number", "brand", "supplier", "logistics_status", "location_type", "proforma_invoice_url", "payment_receipt_url"],
}

FIELD_LABELS = {key: key.replace("_", " ").capitalize() for key in INVENTORY_HEADERS}
FIELD_TYPE_DEFAULTS = {
    "acquisition_date": "date",
    "loan_end_date": "date",
    "configured": "bool",
    "proforma_invoice_url": "url",
    "payment_receipt_url": "url",
    "location_type": "select",
    "acquisition_type": "select",
    "logistics_status": "select",
}
FIELD_OPTIONS = {
    "acquisition_type": ["compra", "prestamo"],
    "logistics_status": ["en_transito", "recibido"],
    "location_type": ["oficina", "cliente", "por_definir"],
    "configured": ["FALSE", "TRUE"],
}

INVENTORY_NEW_DIALOG_OPEN_KEY = "inventory_new_dialog_open"
INVENTORY_EDIT_DIALOG_OPEN_KEY = "inventory_edit_dialog_open"
INVENTORY_SN_VIEWER_OPEN_KEY = "inventory_sn_viewer_open"
INVENTORY_DIALOG_MODEL_LOCKED_KEY = "inventory_dialog_model_locked"
INVENTORY_SELECTED_ROW_ID_KEY = "inventory_selected_row_id"
INVENTORY_SELECTION_MESSAGE_KEY = "inventory_selection_message"
INVENTORY_SUCCESS_MESSAGE_KEY = "inventory_success_message"
INVENTORY_MODEL_DELETE_CONFIRM_KEY = "inventory_model_delete_confirm"
INVENTORY_DELETE_STEP2_KEY = "inventory_delete_step2_id"
INVENTORY_CREATE_DRAFT_ID_KEY = "inventory_create_draft_id"


def _normalize_model_name(model: str) -> str:
    return normalize_model_name(model)


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota exceeded" in msg or "read requests" in msg


def _seed_model_catalog_if_empty() -> None:
    svc = inventory_service()
    if st.session_state.get("inventory_model_catalog_seeded_once", False):
        return
    model_fields = load_inventory_model_fields_cached(st.session_state.get("inventory_cache_version", 0))
    if not model_fields.empty:
        st.session_state["inventory_model_catalog_seeded_once"] = True
        return
    rows_to_seed: list[dict[str, str]] = []
    for model, field_keys in DEFAULT_MODEL_FIELDS.items():
        for i, field_key in enumerate(field_keys):
            rows_to_seed.append(
                {
                    "model": model,
                    "field_key": field_key,
                    "field_label": FIELD_LABELS.get(field_key, field_key),
                    "field_type": FIELD_TYPE_DEFAULTS.get(field_key, "text"),
                    "required": "TRUE" if field_key in {"serial_number"} else "FALSE",
                    "options_csv": ",".join(FIELD_OPTIONS.get(field_key, [])),
                    "help_text": "",
                    "order_index": str(i),
                    "active": "TRUE",
                }
            )
    seeded = svc.seed_model_fields_if_empty(rows_to_seed)
    if seeded:
        bump_inventory_cache()
    st.session_state["inventory_model_catalog_seeded_once"] = True


def _inventory_options_by_model(inv_df: pd.DataFrame, model: str) -> list[tuple[str, str]]:
    if inv_df.empty:
        return []
    df = inv_df.fillna("").astype(str)
    wanted = _normalize_model_name(model)
    model_col = df.get("model", pd.Series(dtype=str))
    rows = df[model_col.apply(_normalize_model_name) == wanted]
    opts: list[tuple[str, str]] = []
    for _, row in rows.iterrows():
        inv_id = str(row.get("inventory_id", "") or "").strip()
        if not inv_id:
            continue
        sn = str(row.get("serial_number", "") or "").strip()
        label = f"{sn} ({inv_id[:8]})" if sn else inv_id
        opts.append((inv_id, label))
    opts.sort(key=lambda x: x[1].lower())
    return opts


def _render_dynamic_field(field_key: str, values: dict[str, str], *, key_prefix: str) -> None:
    key = f"{key_prefix}_{field_key}"
    label = FIELD_LABELS.get(field_key, field_key)
    current = str(values.get(field_key, "") or "")
    field_type = FIELD_TYPE_DEFAULTS.get(field_key, "text")
    if field_key in FIELD_OPTIONS:
        opts = [""] + FIELD_OPTIONS[field_key]
        idx = opts.index(current) if current in opts else 0
        values[field_key] = st.selectbox(label, opts, index=idx, key=key)
    elif field_type == "bool":
        checked = current.strip().upper() == "TRUE"
        values[field_key] = "TRUE" if st.checkbox(label, value=checked, key=key) else "FALSE"
    else:
        values[field_key] = st.text_input(label, value=current, key=key)


def _model_field_keys(model: str, model_fields_df: pd.DataFrame) -> list[str]:
    df = model_fields_df.fillna("").astype(str)
    wanted = _normalize_model_name(model)
    rows = df[(df["model"].apply(_normalize_model_name) == wanted) & (df["active"].str.upper() != "FALSE")]
    if rows.empty:
        return DEFAULT_MODEL_FIELDS.get(model.lower(), ["serial_number", "brand", "supplier"])
    rows = rows.assign(
        _order_num=pd.to_numeric(rows["order_index"], errors="coerce")
    ).sort_values(["_order_num", "order_index"], na_position="last")
    return [str(x).strip() for x in rows["field_key"].tolist() if str(x).strip() in INVENTORY_HEADERS]


def _close_inventory_new_dialog() -> None:
    st.session_state.pop(INVENTORY_NEW_DIALOG_OPEN_KEY, None)
    st.session_state.pop(INVENTORY_DIALOG_MODEL_LOCKED_KEY, None)
    st.session_state.pop(INVENTORY_CREATE_DRAFT_ID_KEY, None)


def _close_inventory_edit_dialog() -> None:
    st.session_state.pop(INVENTORY_EDIT_DIALOG_OPEN_KEY, None)
    st.session_state.pop(INVENTORY_DELETE_STEP2_KEY, None)


def _editable_field_keys(field_keys: list[str]) -> list[str]:
    return [fk for fk in field_keys if fk not in {"inventory_id", "created_at", "updated_at"}]


def _inventory_row_by_id(inv_df: pd.DataFrame, inventory_id: str) -> dict[str, str] | None:
    if inv_df.empty or not inventory_id.strip():
        return None
    df = inv_df.fillna("").astype(str)
    rows = df[df["inventory_id"].astype(str).str.strip() == inventory_id.strip()]
    if rows.empty:
        return None
    return {h: str(rows.iloc[0].get(h, "") or "") for h in INVENTORY_HEADERS}


def _infer_probe_kind_from_associated_id(inv_df: pd.DataFrame, probe_inventory_id: str) -> str:
    row = _inventory_row_by_id(inv_df, probe_inventory_id)
    if not row:
        return ""
    model = _normalize_model_name(str(row.get("model", "") or ""))
    if model == "teros10":
        return "teros10"
    if model == "teros12":
        return "teros12"
    return ""


def _reconcile_selected_inventory_id(selected_id: str, visible_ids: set[str]) -> str:
    clean = (selected_id or "").strip()
    if not clean:
        return ""
    return clean if clean in visible_ids else ""


def _render_association_fields(
    values: dict[str, str],
    field_keys: list[str],
    inv_df: pd.DataFrame,
    *,
    key_prefix: str,
    disabled: bool = False,
) -> None:
    if "associated_sim_inventory_id" in field_keys:
        sim_options = _inventory_options_by_model(inv_df, "sim")
        option_values = [""] + [inv_id for inv_id, _ in sim_options]
        label_map = {"": "Sin asociar", **{inv_id: option_label for inv_id, option_label in sim_options}}
        current = str(st.session_state.get(f"{key_prefix}_associated_sim_inventory_id", values.get("associated_sim_inventory_id", "")) or "")
        idx = option_values.index(current) if current in option_values else 0
        values["associated_sim_inventory_id"] = st.selectbox(
            "SIM asociada",
            option_values,
            index=idx,
            key=f"{key_prefix}_associated_sim_inventory_id",
            format_func=lambda x: label_map.get(x, x),
            disabled=disabled,
        )
        if not sim_options:
            st.info("Aún no hay ninguna SIM en inventario.")

    if "associated_probe_inventory_id" in field_keys:
        probe_current = str(values.get("associated_probe_inventory_id", "") or "").strip()
        probe_kind_default = ""
        if probe_current:
            probe_kind_default = _infer_probe_kind_from_associated_id(inv_df, probe_current)
        probe_kind_key = f"{key_prefix}_probe_kind"
        if probe_kind_key not in st.session_state and probe_kind_default:
            st.session_state[probe_kind_key] = probe_kind_default
        probe_kind = st.selectbox(
            "Tipo de probe asociada",
            ["", "teros10", "teros12"],
            key=probe_kind_key,
            format_func=lambda x: {"": "Selecciona tipo", "teros10": "Teros 10", "teros12": "Teros 12"}.get(x, x),
            disabled=disabled,
        )
        if not probe_kind:
            values["associated_probe_inventory_id"] = probe_current
            st.caption("Selecciona primero si la probe es Teros 10 o Teros 12.")
            return
        probe_options = _inventory_options_by_model(inv_df, probe_kind)
        option_values = [""] + [inv_id for inv_id, _ in probe_options]
        label_map = {"": "Sin asociar", **{inv_id: option_label for inv_id, option_label in probe_options}}
        current = str(st.session_state.get(f"{key_prefix}_associated_probe_inventory_id", probe_current) or "")
        if current and current not in option_values:
            st.warning("La probe asociada previamente ya no está disponible para este tipo.")
            current = ""
        idx = option_values.index(current) if current in option_values else 0
        values["associated_probe_inventory_id"] = st.selectbox(
            "Probe asociada",
            option_values,
            index=idx,
            key=f"{key_prefix}_associated_probe_inventory_id",
            format_func=lambda x: label_map.get(x, x),
            disabled=disabled,
        )
        if not probe_options:
            if probe_kind == "teros10":
                st.info("Aún no hay ninguna Teros 10 en inventario.")
            else:
                st.info("Aún no hay ninguna Teros 12 en inventario.")


def _render_inventory_form_dialog(
    model: str,
    model_fields_df: pd.DataFrame,
    inv_df: pd.DataFrame,
    *,
    mode: str = "create",
    existing: dict[str, str] | None = None,
) -> None:
    field_keys = _model_field_keys(model, model_fields_df)
    existing_row = existing or {}
    values: dict[str, str] = {h: str(existing_row.get(h, "") or "") for h in INVENTORY_HEADERS}
    today = date.today().strftime("%d/%m/%Y")
    if mode == "create":
        values["model"] = model
        draft_id = str(st.session_state.get(INVENTORY_CREATE_DRAFT_ID_KEY, "") or "").strip()
        if not draft_id:
            draft_id = str(uuid.uuid4())
            st.session_state[INVENTORY_CREATE_DRAFT_ID_KEY] = draft_id
        values["inventory_id"] = draft_id
        values["created_at"] = values.get("created_at") or today
        values["updated_at"] = today
    else:
        values["model"] = values.get("model") or model
        values["inventory_id"] = values.get("inventory_id", "")
        values["created_at"] = values.get("created_at") or today
        values["updated_at"] = today
    safe_prefix = "".join(c if c.isalnum() else "_" for c in model)[:40]
    prefix = f"invdlg_{mode}_{safe_prefix}_{values.get('inventory_id', '')[:8]}"
    editable_keys = _editable_field_keys(field_keys)
    _render_association_fields(values, editable_keys, inv_df, key_prefix=prefix)

    with st.form(f"inventory_dialog_form_{prefix}"):
        if mode == "edit":
            st.caption(f"Editando inventario **{values.get('inventory_id', '')}** del modelo **{values.get('model', model)}**.")
        else:
            st.caption(f"Completa los datos del modelo **{model}**.")
        for fk in editable_keys:
            if fk in {"associated_sim_inventory_id", "associated_probe_inventory_id"}:
                continue
            _render_dynamic_field(fk, values, key_prefix=prefix)
        c1, c2 = st.columns(2)
        save_label = "Guardar cambios" if mode == "edit" else "Guardar inventario"
        save = c1.form_submit_button(save_label, type="primary", width="stretch")
        cancel = c2.form_submit_button("Cancelar", width="stretch")

    if cancel:
        if mode == "edit":
            _close_inventory_edit_dialog()
        else:
            _close_inventory_new_dialog()
        st.rerun()

    if save:
        if not values.get("serial_number", "").strip():
            st.error("El Número de serie (SN) es obligatorio.")
            return
        if (values.get("acquisition_type", "") == "prestamo") and not values.get("loan_end_date", "").strip():
            st.error("Si acquisition_type es préstamo, indica loan_end_date.")
            return
        try:
            inventory_service().upsert_inventory(values)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            if _is_quota_error(exc):
                st.error("No se pudo guardar por límite temporal de Google Sheets (429). Reintenta en unos segundos.")
                return
            raise
        if mode == "edit":
            st.session_state[INVENTORY_SUCCESS_MESSAGE_KEY] = "Inventario actualizado."
        else:
            st.session_state[INVENTORY_SUCCESS_MESSAGE_KEY] = "Inventario guardado."
        bump_inventory_cache()
        if mode == "edit":
            _close_inventory_edit_dialog()
        else:
            _close_inventory_new_dialog()
        st.rerun()

    if mode == "edit":
        inv_id = str(values.get("inventory_id", "") or "").strip()
        st.divider()
        ask_delete = st.button(
            "Eliminar inventario",
            key=f"{prefix}_delete_step1",
            width="stretch",
            type="secondary",
        )
        if ask_delete:
            st.session_state[INVENTORY_DELETE_STEP2_KEY] = inv_id
            st.session_state[INVENTORY_EDIT_DIALOG_OPEN_KEY] = True
            st.rerun()
        if str(st.session_state.get(INVENTORY_DELETE_STEP2_KEY, "") or "").strip() == inv_id:
            c1, c2 = st.columns(2)
            if c1.button(
                "Confirmar eliminación",
                key=f"btn_destruct_{prefix}_step2_confirm",
                width="stretch",
                type="primary",
            ):
                deleted = inventory_service().delete_inventory_by_id(inv_id, inv_df=inv_df)
                if not deleted:
                    st.warning("No se encontró ese inventario para eliminar.")
                    return
                bump_inventory_cache()
                st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = ""
                st.session_state[INVENTORY_SELECTION_MESSAGE_KEY] = "Inventario eliminado correctamente."
                _close_inventory_edit_dialog()
                st.rerun()
            if c2.button(
                "Cancelar eliminación",
                key=f"btn_neutral_{prefix}_step2_cancel",
                width="stretch",
            ):
                st.session_state.pop(INVENTORY_DELETE_STEP2_KEY, None)
                st.session_state[INVENTORY_EDIT_DIALOG_OPEN_KEY] = True
                st.rerun()


@st.dialog("Nuevo inventario")
def _inventory_new_dialog() -> None:
    ver = st.session_state.get("inventory_cache_version", 0)
    try:
        model_fields_df = load_inventory_model_fields_cached(ver)
        inv_df = load_inventory_cached(ver)
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("Google Sheets está temporalmente sin cuota de lectura (429). Reintenta en unos segundos.")
            return
        raise
    models = sorted(
        {
            m.strip().lower()
            for m in model_fields_df.get("model", pd.Series(dtype=str)).fillna("").astype(str).tolist()
            if str(m).strip()
        }
    )

    head1, head2 = st.columns([1, 0.22])
    with head1:
        st.markdown("### Alta de inventario")
    with head2:
        if st.button("Cerrar", key="inventory_dialog_header_close", width="stretch"):
            _close_inventory_new_dialog()
            st.rerun()

    locked = str(st.session_state.get(INVENTORY_DIALOG_MODEL_LOCKED_KEY, "") or "").strip()

    if locked:
        st.info(f"Modelo seleccionado: **{locked}**")
        if st.button("Elegir otro modelo", key="inventory_dialog_pick_other"):
            st.session_state.pop(INVENTORY_DIALOG_MODEL_LOCKED_KEY, None)
            st.session_state[INVENTORY_NEW_DIALOG_OPEN_KEY] = True
            st.rerun()
        _render_inventory_form_dialog(locked, model_fields_df, inv_df)
        return

    with st.expander("Gestionar modelos", expanded=False):
        model_to_delete = st.selectbox(
            "Modelo a borrar de InventarioCamposModelo",
            [""] + models,
            key="inventory_dialog_delete_model_pick",
        )
        st.checkbox(
            "Confirmo que quiero borrar este modelo del catálogo",
            key=INVENTORY_MODEL_DELETE_CONFIRM_KEY,
        )
        if st.button("Borrar modelo", key="inventory_dialog_delete_model_btn", type="secondary"):
            clean_model = (model_to_delete or "").strip()
            if not clean_model:
                st.error("Selecciona un modelo para borrar.")
                return
            if not bool(st.session_state.get(INVENTORY_MODEL_DELETE_CONFIRM_KEY, False)):
                st.error("Marca la confirmación antes de borrar.")
                return
            svc = inventory_service()
            in_use = svc.count_inventory_by_model(clean_model, inv_df=inv_df)
            if in_use > 0:
                st.error(f"No se puede borrar el modelo '{clean_model}' porque tiene {in_use} activos en Inventario.")
                return
            removed = svc.delete_model_fields_hard(clean_model, model_fields_df=model_fields_df)
            if removed <= 0:
                st.warning("No había filas de plantilla para ese modelo.")
                return
            bump_inventory_cache()
            st.success(f"Modelo '{clean_model}' borrado del catálogo ({removed} filas eliminadas).")
            st.session_state[INVENTORY_MODEL_DELETE_CONFIRM_KEY] = False
            st.session_state[INVENTORY_NEW_DIALOG_OPEN_KEY] = True
            st.rerun()

    pick = st.selectbox(
        "Modelo",
        [""] + models + ["Añadir modelo nuevo"],
        key="inventory_dialog_model_pick",
        help="Elige un modelo del catálogo o crea uno nuevo y define qué columnas usará.",
    )

    if pick == "Añadir modelo nuevo":
        st.markdown("##### Definir modelo nuevo")
        new_name = st.text_input("Nombre del modelo (único, minúsculas recomendado)", key="inventory_dialog_new_model_name")
        all_keys = [k for k in INVENTORY_HEADERS if k not in {"inventory_id", "created_at", "updated_at"}]
        st.caption("Selecciona con checkboxes qué campos estarán disponibles para este nuevo modelo.")
        selected_fields: list[str] = []
        default_fields = {"serial_number", "brand", "supplier"}
        for field_key in all_keys:
            cb_key = f"inventory_dialog_new_model_field_{field_key}"
            if cb_key not in st.session_state:
                st.session_state[cb_key] = field_key in default_fields
            checked = st.checkbox(FIELD_LABELS.get(field_key, field_key), key=cb_key)
            if checked:
                selected_fields.append(field_key)
        if st.button("Guardar plantilla y continuar", type="primary", key="inventory_dialog_save_template"):
            clean = (new_name or "").strip().lower()
            if not clean:
                st.error("Indica un nombre de modelo.")
                return
            if not selected_fields:
                st.error("Selecciona al menos un campo.")
                return
            today = date.today().strftime("%d/%m/%Y")
            rows: list[dict[str, str]] = []
            for i, field_key in enumerate(selected_fields):
                rows.append(
                    {
                        "model": clean,
                        "field_key": field_key,
                        "field_label": FIELD_LABELS.get(field_key, field_key),
                        "field_type": FIELD_TYPE_DEFAULTS.get(field_key, "text"),
                        "required": "TRUE" if field_key == "serial_number" else "FALSE",
                        "options_csv": ",".join(FIELD_OPTIONS.get(field_key, [])),
                        "help_text": "",
                        "order_index": str(i),
                        "active": "TRUE",
                        "created_at": today,
                        "updated_at": today,
                    }
                )
            inventory_service().merge_model_field_rows(rows)
            bump_inventory_cache()
            st.session_state[INVENTORY_DIALOG_MODEL_LOCKED_KEY] = clean
            st.session_state[INVENTORY_NEW_DIALOG_OPEN_KEY] = True
            st.rerun()
        return

    if not pick:
        st.caption("Selecciona un modelo o **Añadir modelo nuevo**.")
        return

    st.session_state[INVENTORY_DIALOG_MODEL_LOCKED_KEY] = pick
    st.session_state[INVENTORY_NEW_DIALOG_OPEN_KEY] = True
    st.rerun()


@st.dialog("Editar inventario")
def _inventory_edit_dialog() -> None:
    ver = st.session_state.get("inventory_cache_version", 0)
    model_fields_df = load_inventory_model_fields_cached(ver)
    inv_df = load_inventory_cached(ver)
    selected_id = str(st.session_state.get(INVENTORY_SELECTED_ROW_ID_KEY, "") or "").strip()
    current = _inventory_row_by_id(inv_df, selected_id)
    if not current:
        st.error("No se encontró el inventario seleccionado. Actualiza la lista y vuelve a intentarlo.")
        if st.button("Cerrar", key="inventory_edit_close_missing", width="stretch"):
            _close_inventory_edit_dialog()
            st.rerun()
        return
    model = str(current.get("model", "") or "").strip().lower()
    _render_inventory_form_dialog(model, model_fields_df, inv_df, mode="edit", existing=current)


def render(_: pd.DataFrame) -> None:
    st.title("Inventario")
    try:
        _seed_model_catalog_if_empty()
        inv_df = load_inventory_cached(st.session_state.get("inventory_cache_version", 0))
    except Exception as exc:
        if _is_quota_error(exc):
            st.error("No se pudo cargar Inventario por límite temporal de lectura en Google Sheets (429). Reintenta en unos segundos.")
            return
        raise

    col1, col2, col3 = st.columns([0.55, 0.22, 0.23])
    query = col1.text_input("Buscar inventario", key="inventory_query", placeholder="SN, modelo, proveedor, ubicacion...")
    with col2:
        st.text("")
        if st.button("🔗 Ver asociados SN", key="inventory_btn_sn_viewer", width="stretch"):
            st.session_state[INVENTORY_SN_VIEWER_OPEN_KEY] = True
            st.rerun()
    with col3:
        st.text("")
        if st.button("+ Nuevo inventario", key="inventory_btn_new", width="stretch", type="primary"):
            st.session_state[INVENTORY_NEW_DIALOG_OPEN_KEY] = True
            st.session_state.pop(INVENTORY_DIALOG_MODEL_LOCKED_KEY, None)
            st.rerun()

    filtered = inv_df.copy()
    if not filtered.empty and (query or "").strip():
        q = query.strip().lower()
        mask = filtered.apply(lambda row: any(q in str(v).lower() for v in row.values), axis=1)
        filtered = filtered[mask]
    if st.session_state.get(INVENTORY_SELECTION_MESSAGE_KEY):
        st.info(str(st.session_state.pop(INVENTORY_SELECTION_MESSAGE_KEY)))
    if st.session_state.get(INVENTORY_SUCCESS_MESSAGE_KEY):
        st.success(str(st.session_state.pop(INVENTORY_SUCCESS_MESSAGE_KEY)))

    visible_ids = set(filtered.get("inventory_id", pd.Series(dtype=str)).fillna("").astype(str).str.strip().tolist())
    selected = _reconcile_selected_inventory_id(
        str(st.session_state.get(INVENTORY_SELECTED_ROW_ID_KEY, "") or ""),
        visible_ids,
    )
    if str(st.session_state.get(INVENTORY_SELECTED_ROW_ID_KEY, "") or "") != selected:
        st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = selected
        if not selected and visible_ids:
            st.session_state[INVENTORY_SELECTION_MESSAGE_KEY] = "La fila seleccionada ya no está visible con el filtro actual."

    if filtered.empty:
        st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = ""
        st.dataframe(filtered, width="stretch", hide_index=True, height=420)
    else:
        display_df = filtered.copy()
        selected_col: list[bool] = []
        for row in display_df.fillna("").astype(str).to_dict("records"):
            selected_col.append(str(row.get("inventory_id", "")).strip() == selected)
        display_df.insert(0, "Seleccionar", selected_col)
        edited = st.data_editor(
            display_df,
            width="stretch",
            hide_index=True,
            height=420,
            key="inventory_table_editor",
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn(
                    "Seleccionar",
                    help="Marca una fila para editarla",
                    default=False,
                )
            },
            disabled=[c for c in display_df.columns if c != "Seleccionar"],
        )
        picked_ids = edited[edited["Seleccionar"] == True]["inventory_id"].fillna("").astype(str).str.strip().tolist()
        picked_ids = [x for x in picked_ids if x]
        if len(picked_ids) > 1:
            st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = picked_ids[0]
            st.session_state[INVENTORY_SELECTION_MESSAGE_KEY] = "Solo se puede editar una fila a la vez. Se tomó la primera seleccionada."
            st.rerun()
        st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = picked_ids[0] if picked_ids else ""

    selected_now = str(st.session_state.get(INVENTORY_SELECTED_ROW_ID_KEY, "") or "").strip()
    if selected_now:
        if st.button("Editar inventario seleccionado", width="stretch", key="inventory_edit_selected_btn", type="primary"):
            if selected_now not in visible_ids:
                st.session_state[INVENTORY_SELECTED_ROW_ID_KEY] = ""
                st.session_state[INVENTORY_SELECTION_MESSAGE_KEY] = "La selección ya no está en la lista filtrada. Elige otra fila."
                st.rerun()
            st.session_state[INVENTORY_EDIT_DIALOG_OPEN_KEY] = True
            st.rerun()

    if st.session_state.pop(INVENTORY_NEW_DIALOG_OPEN_KEY, False):
        _inventory_new_dialog()
    if st.session_state.pop(INVENTORY_EDIT_DIALOG_OPEN_KEY, False):
        _inventory_edit_dialog()
    if st.session_state.get(INVENTORY_SN_VIEWER_OPEN_KEY):
        st.session_state.pop(INVENTORY_SN_VIEWER_OPEN_KEY, None)
        _occurrences = history_service().search_sensor_assets()
        render_sn_viewer_dialog(inv_df, _occurrences)
