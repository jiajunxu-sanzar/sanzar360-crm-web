"""Pricing calculator — mirrors the sanzar-crm desktop PricingView.

Two modes:
  · Cliente   (default) — sensor price 700 EUR
  · Proveedor (locked)  — sensor price 325 EUR, unlocked with password
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SENSOR_CLIENT_EUR   = 700.0
_SENSOR_PROVIDER_EUR = 325.0
_ANNUAL_EUR          = 360.0
_MONTHLY_EUR         = 45.0
_PROVIDER_PASSWORD   = "sanzar"

_MEDIA_DIR  = Path(__file__).resolve().parents[1] / "assets" / "media"
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_KEY_PROVIDER = "pricing.provider_mode"


def _ensure_state() -> None:
    st.session_state.setdefault(_KEY_PROVIDER, False)


def _load_media() -> list[Path]:
    if not _MEDIA_DIR.is_dir():
        return []
    return sorted(p for p in _MEDIA_DIR.iterdir() if p.suffix.lower() in _IMAGE_EXTS)


@st.dialog("Cambiar vista")
def _view_switch_dialog() -> None:
    is_provider: bool = st.session_state[_KEY_PROVIDER]
    if is_provider:
        st.markdown("Estás en **vista proveedor**. ¿Volver a vista cliente?")
        if st.button("Volver a vista cliente", width="stretch", type="primary"):
            st.session_state[_KEY_PROVIDER] = False
            st.rerun()
    else:
        st.markdown("Introduce la contraseña para ver **precios de proveedor**.")
        pwd = st.text_input("Contraseña", type="password", key="pricing_pwd_input")
        if st.button("Desbloquear", width="stretch", type="primary"):
            if pwd.strip() == _PROVIDER_PASSWORD:
                st.session_state[_KEY_PROVIDER] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")


def render(_: pd.DataFrame) -> None:
    _ensure_state()

    is_provider: bool = st.session_state[_KEY_PROVIDER]

    # --- Header row: title + mode badge + swap icon ---
    h_left, h_mid, h_right = st.columns([0.72, 0.2, 0.08])
    h_left.title("Pricing")
    badge_color = "#d97706" if is_provider else "#6b7280"
    badge_label = "PROVEEDOR" if is_provider else "CLIENTE"
    h_mid.markdown(
        f"<div style='padding-top:1.4rem;text-align:right;"
        f"color:{badge_color};font-weight:700;font-size:0.85rem'>{badge_label}</div>",
        unsafe_allow_html=True,
    )
    h_right.markdown("<div style='padding-top:1.8rem'>", unsafe_allow_html=True)
    if h_right.button("🔄", key="pricing_swap_btn", help="Cambiar vista cliente / proveedor"):
        _view_switch_dialog()
    h_right.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # --- Inputs (left) + Desglose (right) ---
    sensor_price = _SENSOR_PROVIDER_EUR if is_provider else _SENSOR_CLIENT_EUR

    c1, c2 = st.columns([0.6, 0.4], gap="large")

    with c1:
        include_sensor  = st.checkbox("Sensor UC501 + Teros 10",         value=True, key="pricing_sensor")
        include_annual  = st.checkbox("Suscripción anual (360 EUR)",      value=True, key="pricing_annual")
        include_monthly = st.checkbox("Suscripción mensual (45 EUR/mes)", value=False, key="pricing_monthly")
        months = 12
        if include_monthly:
            months = st.number_input(
                "Número de meses", min_value=1, max_value=120, value=12, step=1, key="pricing_months"
            )

    total = 0.0
    lines: list[str] = []
    if include_sensor:
        total += sensor_price
        lines.append(f"Sensor: **{sensor_price:.2f} EUR**")
    if include_annual:
        total += _ANNUAL_EUR
        lines.append(f"Suscripción anual: **{_ANNUAL_EUR:.2f} EUR**")
    if include_monthly:
        monthly_total = round(months * _MONTHLY_EUR, 2)
        total += monthly_total
        lines.append(f"Suscripción mensual ({months} × {_MONTHLY_EUR:.2f}): **{monthly_total:.2f} EUR**")
    total = round(total, 2)

    with c2:
        st.markdown("#### Desglose")
        if lines:
            for line in lines:
                st.markdown(f"- {line}")
        else:
            st.caption("Selecciona al menos un componente.")
        st.markdown(f"### Total: {total:.2f} EUR")
        monthly_year = _MONTHLY_EUR * 12.0
        savings_pct  = round(((monthly_year - _ANNUAL_EUR) / monthly_year) * 100.0, 2)
        st.info(
            f"Pago anual ({_ANNUAL_EUR:.2f} EUR) vs mensual "
            f"(12 × {_MONTHLY_EUR:.2f} = {monthly_year:.2f} EUR) → "
            f"**ahorro: {savings_pct:.2f}%**"
        )

    # --- Image gallery (no captions) ---
    st.markdown("---")
    images = _load_media()
    if images:
        st.markdown("#### Galería de producto")
        cols = st.columns(min(len(images), 6))
        for col, img_path in zip(cols, images[:6]):
            col.image(str(img_path), width="stretch")
