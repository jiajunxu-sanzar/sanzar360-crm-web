"""Formulario compartido de alta/edición de cultivos Kc (Técnico y Contactos)."""
from __future__ import annotations

from typing import Callable

import streamlit as st

from app.cache import cultivos_kc_service
from app.state import bump_cultivos_kc_cache
from services.locale_numbers import parse_locale_float, parse_p_tabla

FAO56_PDF_URL = "https://www.fao.org/4/x0490s/x0490s.pdf"


def _num(value: object, default: float) -> float:
    parsed = parse_locale_float(value)
    return default if parsed is None else parsed


def _num_p(value: object, default: float) -> float:
    parsed = parse_p_tabla(value)
    return default if parsed is None else parsed


def render_cultivo_kc_fields(
    values: dict[str, str],
    *,
    key_prefix: str,
    show_fao_link: bool = True,
) -> dict[str, str]:
    """Renderiza inputs L/kc/p y devuelve el draft (sin guardar)."""
    if show_fao_link:
        st.link_button(
            "FAO-56: L en pág. 125 · Kc en pág. 131",
            FAO56_PDF_URL,
            use_container_width=True,
        )
    nombre = st.text_input("Nombre *", value=values.get("nombre", ""), key=f"{key_prefix}_nombre")
    c1, c2 = st.columns(2)
    with c1:
        L1 = st.number_input(
            "L1 (fin etapa inicial)",
            min_value=0.0,
            value=_num(values.get("L1"), 30.0),
            step=1.0,
            key=f"{key_prefix}_L1",
        )
        L2 = st.number_input(
            "L2 (fin desarrollo)",
            min_value=0.0,
            value=_num(values.get("L2"), 90.0),
            step=1.0,
            key=f"{key_prefix}_L2",
        )
        L3 = st.number_input(
            "L3 (fin etapa media)",
            min_value=0.0,
            value=_num(values.get("L3"), 130.0),
            step=1.0,
            key=f"{key_prefix}_L3",
        )
        L4 = st.number_input(
            "L4 (cosecha)",
            min_value=0.0,
            value=_num(values.get("L4"), 210.0),
            step=1.0,
            key=f"{key_prefix}_L4",
        )
    with c2:
        kc_ini = st.number_input(
            "Kc ini",
            min_value=0.0,
            value=_num(values.get("kc_ini"), 0.30),
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}_kc_ini",
        )
        kc_med = st.number_input(
            "Kc med",
            min_value=0.0,
            value=_num(values.get("kc_med"), 0.70),
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}_kc_med",
        )
        kc_fin = st.number_input(
            "Kc fin",
            min_value=0.0,
            value=_num(values.get("kc_fin"), 0.45),
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}_kc_fin",
        )
        p_tabla = st.number_input(
            "p_tabla FAO-56 (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=_num_p(values.get("p_tabla"), 0.40),
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}_p_tabla",
        )
    return {
        **values,
        "nombre": nombre,
        "L1": str(L1),
        "L2": str(L2),
        "L3": str(L3),
        "L4": str(L4),
        "kc_ini": str(kc_ini),
        "kc_med": str(kc_med),
        "kc_fin": str(kc_fin),
        "p_tabla": str(p_tabla),
    }


def save_cultivo_kc(
    draft: dict[str, str],
    *,
    actor_name: str,
    mode: str = "create",
) -> str:
    """Persiste el cultivo y refresca cache. Devuelve cultivo_kc_id."""
    saved_id = cultivos_kc_service().upsert_cultivo(draft, actor_name=actor_name, mode=mode)
    bump_cultivos_kc_cache()
    return saved_id


def render_new_cultivo_kc_dialog_body(
    *,
    key_prefix: str,
    actor_name: str,
    on_saved: Callable[[str, str], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> None:
    """Cuerpo de diálogo «Nuevo cultivo»: fields + Guardar/Cancelar.

    ``on_saved(cultivo_id, nombre)`` se llama tras guardar OK.
    """
    draft = render_cultivo_kc_fields({}, key_prefix=key_prefix)
    save_col, cancel_col = st.columns(2)
    if save_col.button("Guardar", type="primary", key=f"{key_prefix}_save", use_container_width=True):
        try:
            saved_id = save_cultivo_kc(draft, actor_name=actor_name, mode="create")
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg:
                st.error("Google Sheets sin cuota (429). Reintenta en unos segundos.")
                return
            raise
        nombre = str(draft.get("nombre", "") or "").strip()
        if on_saved:
            on_saved(saved_id, nombre)
        st.rerun()
    if cancel_col.button("Cancelar", key=f"{key_prefix}_cancel", use_container_width=True):
        if on_cancel:
            on_cancel()
        st.rerun()
