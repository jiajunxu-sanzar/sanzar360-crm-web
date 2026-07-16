"""Pricing calculator — tiered annual/monthly subscription by sensor count."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ui.components.page_header import render_page_header
from services.pricing_calculator import (
    compare_annual_vs_monthly,
    compute_quote,
    sensor_unit_price,
)

_MEDIA_DIR = Path(__file__).resolve().parents[1] / "assets" / "media"
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_KEY_PROVIDER = "pricing.provider_mode"
_MODE_ANNUAL = "Pago anual (recomendado)"
_MODE_MONTHLY = "Pago mensual"


def _ensure_state() -> None:
    st.session_state.setdefault(_KEY_PROVIDER, False)


def _load_media() -> list[Path]:
    if not _MEDIA_DIR.is_dir():
        return []
    return sorted(p for p in _MEDIA_DIR.iterdir() if p.suffix.lower() in _IMAGE_EXTS)


def _format_eur(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render(_: pd.DataFrame) -> None:
    _ensure_state()

    is_provider: bool = bool(st.session_state[_KEY_PROVIDER])

    st.markdown(
        """
        <style>
        h1#pricing { margin-bottom: 0.35rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_page_header("Pricing")

    c1, c2 = st.columns([0.6, 0.4], gap="large")

    with c1:
        badge_col, toggle_col = st.columns([0.78, 0.22], vertical_alignment="center")
        badge_class = "sanzar-badge-proveedor" if is_provider else "sanzar-badge-cliente"
        badge_label = "PROVEEDOR" if is_provider else "CLIENTE"
        badge_col.markdown(
            f"<span class='{badge_class}'>{badge_label}</span>",
            unsafe_allow_html=True,
        )
        with toggle_col:
            st.toggle(
                "Proveedor",
                key=_KEY_PROVIDER,
                label_visibility="collapsed",
                help="Vista proveedor (hardware a 325 €/sensor)",
            )

        n_sensors = int(
            st.number_input(
                "Número de sensores",
                min_value=1,
                max_value=150,
                value=4,
                step=1,
                key="pricing_n_sensors",
            )
        )
        payment_label = st.radio(
            "Modalidad de suscripción",
            options=[_MODE_ANNUAL, _MODE_MONTHLY],
            index=0,
            key="pricing_payment_mode",
        )
        include_sensor = st.checkbox(
            "Incluir coste de sensor (UC501 + Teros 10, 2 años de garantía incluidos)",
            value=True,
            key="pricing_include_sensor",
        )
        months = 12
        if payment_label == _MODE_MONTHLY:
            months = int(
                st.number_input(
                    "Meses de suscripción",
                    min_value=1,
                    max_value=120,
                    value=12,
                    step=1,
                    key="pricing_months",
                )
            )

        unit = sensor_unit_price(provider_mode=is_provider)
        st.caption(
            f"Hardware por sensor (2 años de garantía incluidos): **{_format_eur(unit)} €** "
            f"({'proveedor' if is_provider else 'cliente'})."
        )

    mode = "annual" if payment_label == _MODE_ANNUAL else "monthly"
    quote = compute_quote(
        n_sensors,
        mode,
        include_sensor=include_sensor,
        provider_mode=is_provider,
    )
    comparison = compare_annual_vs_monthly(n_sensors)

    with c2:
        st.markdown("#### Desglose")
        period_unit = "€/año" if mode == "annual" else "€/mes"
        for line in quote.subscription.lines:
            st.markdown(f"- {line.label}: **{_format_eur(line.amount)} {line.unit}**")

        st.markdown(
            f"**Total suscripción:** {_format_eur(quote.subscription.subscription_total)} {period_unit}"
        )

        if quote.hardware_line:
            st.markdown(
                f"- {quote.hardware_line.label}: **{_format_eur(quote.hardware_total)} €**"
            )
            st.markdown(f"**Total hardware:** {_format_eur(quote.hardware_total)} €")

        if mode == "monthly":
            subscription_period = round(quote.subscription.subscription_total * months, 2)
            grand = round(subscription_period + quote.hardware_total, 2)
            st.markdown(
                f"**Total suscripción ({months} meses):** "
                f"{_format_eur(subscription_period)} €"
            )
            st.markdown(f"### Total general: {_format_eur(grand)} €")
            st.info(
                f"Si pagas **anual**, la suscripción sería "
                f"**{_format_eur(comparison.annual_subscription)} €/año** en lugar de "
                f"**{_format_eur(comparison.monthly_subscription_per_year)} €/año** "
                f"(12 × {_format_eur(comparison.monthly_subscription_per_month)} €/mes). "
                f"**Ahorro: {_format_eur(comparison.savings_eur)} € "
                f"({comparison.savings_pct:g}%)**"
            )
        else:
            st.markdown(f"### Total general: {_format_eur(quote.grand_total)} €")
            st.info(
                f"El pago mensual equivalente (12 meses) costaría "
                f"**{_format_eur(comparison.monthly_subscription_per_year)} €/año** "
                f"vs **{_format_eur(comparison.annual_subscription)} €/año** en anual. "
                f"**Ahorro con anual: {_format_eur(comparison.savings_eur)} € "
                f"({comparison.savings_pct:g}%)**"
            )

        if quote.subscription.custom_pricing_note:
            st.warning(quote.subscription.custom_pricing_note)

    st.markdown("---")
    images = _load_media()
    if images:
        st.markdown("#### Galería de producto")
        cols = st.columns(min(len(images), 6))
        for col, img_path in zip(cols, images[:6]):
            col.image(str(img_path), width="stretch")
