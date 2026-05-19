"""Pestaña Referidos — modelo económico y gráfica combinada (Plotly)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from app.navigation import page_menu_title

# ── Modelo económico ────────────────────────────────────────────────────────
ANNUAL_SUBSCRIPTION_EUR = 360
MONTH_DISCOUNT_REFERRER_EUR = 30
MONTH_DISCOUNT_NEW_EUR = 30
COST_PER_CLOSED_REFERRAL_EUR = MONTH_DISCOUNT_REFERRER_EUR + MONTH_DISCOUNT_NEW_EUR  # 60
NET_PER_REFERRAL_EUR = ANNUAL_SUBSCRIPTION_EUR - COST_PER_CLOSED_REFERRAL_EUR  # 300

REFERRALS_FOR_SENSOR_GIFT = 20
SENSOR_GIFT_VALUE_EUR = 560

LTV_EUR = 1080
LTV_CAC_HEALTHY_RATIO = 3.0

# Separación vertical entre paneles del subplot (fraction del área; más alto → más hueco).
FIG_VERTICAL_SPACING = 0.11
FIG_PX_HEIGHT = 1280


def _one_time_gift_cost(n_refs: int) -> float:
    return float(SENSOR_GIFT_VALUE_EUR if n_refs >= REFERRALS_FOR_SENSOR_GIFT else 0)


def _cost_total(n_refs: int) -> float:
    return float(n_refs) * float(COST_PER_CLOSED_REFERRAL_EUR) + _one_time_gift_cost(n_refs)


def build_referidos_figure() -> go.Figure:
    # Paleta marca (sin Perplexity template)
    c_net = "#15803d"
    c_cost = "#dc2626"
    c_pct = "#4338ca"
    c_ann = "#6b7280"

    referidos = list(range(1, 26))

    # --- Panel 1: neto año 1 ---
    neto_panel1 = [float(n) * NET_PER_REFERRAL_EUR - _one_time_gift_cost(n) for n in referidos]
    y_top = max(neto_panel1) * 1.15

    # --- Panel 2–3: escenarios ---
    casos = [1, 5, 10, 15, 20, 25]
    etiquetas = ["1 ref.", "5 refs.", "10 refs.", "15 refs.", "20 refs.*", "25 refs."]
    ingresos_brutos = [float(n) * ANNUAL_SUBSCRIPTION_EUR for n in casos]
    costes = [_cost_total(n) for n in casos]
    netos_esc = [ib - c for ib, c in zip(ingresos_brutos, costes)]
    pct_coste = [round(c / ib * 100, 1) if ib else 0.0 for c, ib in zip(costes, ingresos_brutos)]

    text_outside = [
        (f"{v:.0f}€" if (i % 4 == 0 or i == 19) else "")
        for i, v in enumerate(neto_panel1)
    ]

    fig = make_subplots(
        rows=5,
        cols=1,
        row_heights=[0.22, 0.19, 0.15, 0.26, 0.18],
        vertical_spacing=FIG_VERTICAL_SPACING,
        subplot_titles=(
            f"Ingreso neto año 1 por referidos cerrados (≈ {NET_PER_REFERRAL_EUR:.0f} €/referido · regalo sensor a partir de {REFERRALS_FOR_SENSOR_GIFT})",
            "Ingresos netos vs coste del programa (€) — puntos representativos",
            "% del coste sobre ingreso bruto total",
            "Ingresos acumulados vs coste del programa (€)",
            f"Ratio LTV/CAC (LTV supuesto {LTV_EUR:.0f} €) · mínimo recomendado {LTV_CAC_HEALTHY_RATIO:.0f}x",
        ),
        specs=[
            [{"secondary_y": False}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
        ],
    )

    # Row 1
    fig.add_trace(
        go.Bar(
            x=referidos,
            y=neto_panel1,
            name="Ingreso neto año 1",
            marker_color=c_net,
            showlegend=True,
            text=text_outside,
            textposition="outside",
            textfont=dict(size=11),
            hovertemplate="Referidos cerrados=%{x}<br>Neto=%{y:.0f} €<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_shape(
        type="line",
        x0=float(REFERRALS_FOR_SENSOR_GIFT) - 0.5,
        x1=float(REFERRALS_FOR_SENSOR_GIFT) - 0.5,
        y0=0,
        y1=y_top,
        line=dict(color=c_ann, width=2, dash="dash"),
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=float(REFERRALS_FOR_SENSOR_GIFT) + 1.8,
        y=y_top * 0.93,
        text="Sensor regalo",
        showarrow=False,
        font=dict(size=12, color=c_ann),
        xref="x",
        yref="y",
    )

    # Row 2 — barras apiladas (neto + coste = bruto)
    fig.add_trace(
        go.Bar(
            x=etiquetas,
            y=netos_esc,
            name="Ingreso neto",
            marker_color=c_net,
            showlegend=True,
            text=[f"{v:.0f} €" for v in netos_esc],
            textposition="inside",
            textfont=dict(size=12, color="white"),
            hovertemplate="%{x}<br>Neto=%{y:.0f} €<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=etiquetas,
            y=costes,
            name="Coste programa",
            marker_color=c_cost,
            showlegend=True,
            text=[f"{v:.0f} €" for v in costes],
            textposition="inside",
            textfont=dict(size=12, color="white"),
            hovertemplate="%{x}<br>Coste=%{y:.0f} €<extra></extra>",
        ),
        row=2,
        col=1,
    )

    tp_pct = ["top center"] * 4 + ["bottom center", "top center"]
    fig.add_trace(
        go.Scatter(
            name="% coste / ingreso bruto",
            x=etiquetas,
            y=pct_coste,
            mode="lines+markers+text",
            line=dict(width=3, color=c_pct),
            marker=dict(size=10, color=c_pct),
            text=[f"<b>{p}%</b>" for p in pct_coste],
            textposition=tp_pct,
            textfont=dict(size=12, color=c_pct),
            fill="tozeroy",
            fillcolor="rgba(67,56,202,0.10)",
            showlegend=True,
            hovertemplate="%{x}<br>% coste=%{y:.1f}%<extra></extra>",
        ),
        row=3,
        col=1,
    )

    # Row 4–5: acumulado + LTV/CAC
    ingresos_acum = [float(n) * ANNUAL_SUBSCRIPTION_EUR for n in referidos]
    costes_acum = [_cost_total(n) for n in referidos]
    cac_series = [_cost_total(n) / float(n) for n in referidos]
    ltv_cac_series = [round(LTV_EUR / c, 1) if c > 0 else 0 for c in cac_series]

    fig.add_trace(
        go.Scatter(
            x=referidos,
            y=ingresos_acum,
            name="Ingresos generados",
            mode="lines",
            line=dict(width=2.5, color=c_net),
            fill="tozeroy",
            fillcolor="rgba(21,128,61,0.14)",
            showlegend=True,
            hovertemplate="n=%{x}<br>Ingresos=%{y:.0f} €<extra></extra>",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=referidos,
            y=costes_acum,
            name="Coste del programa",
            mode="lines",
            line=dict(width=2.5, color=c_cost),
            fill="tozeroy",
            fillcolor="rgba(220,38,38,0.15)",
            showlegend=True,
            hovertemplate="n=%{x}<br>Coste=%{y:.0f} €<extra></extra>",
        ),
        row=4,
        col=1,
    )
    ix20 = REFERRALS_FOR_SENSOR_GIFT - 1  # índice 0-based para 20 referidos
    fig.add_annotation(
        xref="x4",
        yref="y4",
        x=REFERRALS_FOR_SENSOR_GIFT,
        y=ingresos_acum[ix20] + 450,
        text=f"<b>{ingresos_acum[ix20]:.0f} €</b>",
        showarrow=False,
        font=dict(size=11, color=c_net),
    )
    fig.add_annotation(
        xref="x4",
        yref="y4",
        x=REFERRALS_FOR_SENSOR_GIFT,
        y=costes_acum[ix20] + 450,
        text=f"<b>{costes_acum[ix20]:.0f} €</b>",
        showarrow=False,
        font=dict(size=11, color=c_cost),
    )

    fig.add_trace(
        go.Scatter(
            x=referidos,
            y=ltv_cac_series,
            name="Ratio LTV/CAC",
            mode="lines+markers",
            line=dict(width=3, color=c_pct),
            marker=dict(size=7, color=c_pct),
            fill="tozeroy",
            fillcolor="rgba(67,56,202,0.10)",
            showlegend=True,
            hovertemplate="n=%{x}<br>LTV/CAC=%{y:.1f}x<extra></extra>",
        ),
        row=5,
        col=1,
    )

    fig.add_hline(
        y=LTV_CAC_HEALTHY_RATIO,
        line_dash="dot",
        line_color="red",
        line_width=2,
        row=5,
        col=1,
        annotation_text=f"Mínimo recomendado: {LTV_CAC_HEALTHY_RATIO:.0f}x",
        annotation_position="top right",
        annotation_font=dict(size=11, color="red"),
    )

    for idx, lx in [(0, 1), (9, 10), (19, 20), (24, 25)]:
        lv = ltv_cac_series[idx]
        fig.add_annotation(
            xref="x5",
            yref="y5",
            x=lx,
            y=lv + 1.9,
            text=f"<b>{lv}x</b>",
            showarrow=False,
            font=dict(size=11, color=c_pct),
        )

    fig.update_layout(
        title=dict(
            text=(
                "<b>Programa de referidos — Sanzar360</b>"
                "<br><sup>Cada suscripción anual cuenta como 360 € de ingreso bruto;"
                " 60 € de descuentos combinados por cierre;"
                f" regalo único sensor ({SENSOR_GIFT_VALUE_EUR} €) tras {REFERRALS_FOR_SENSOR_GIFT} referidos cerrados · * incluye ese hit.</sup>"
            )
        ),
        font=dict(size=13),
        barmode="stack",
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
        ),
        margin=dict(l=72, r=210, t=132, b=52),
        height=FIG_PX_HEIGHT,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    fig.update_yaxes(title_text="Ingreso neto (€)", gridcolor="#eee", row=1, col=1)
    fig.update_xaxes(title_text="Nº referidos cerrados", tickmode="linear", dtick=2, row=1, col=1, showgrid=False)

    fig.update_yaxes(title_text="Euros (€)", gridcolor="#eee", row=2, col=1)
    fig.update_xaxes(showgrid=False, row=2, col=1)

    fig.update_yaxes(title="% coste", range=[0, 28], gridcolor="#eee", row=3, col=1)
    fig.update_xaxes(showgrid=False, row=3, col=1)

    fig.update_yaxes(title_text="Euros (€)", gridcolor="#eee", row=4, col=1)
    fig.update_xaxes(showgrid=False, row=4, col=1)

    fig.update_yaxes(title_text="LTV / CAC (×)", range=[0, 25], gridcolor="#eee", row=5, col=1)
    fig.update_xaxes(
        title_text="Nº referidos cerrados",
        tickmode="linear",
        tick0=1,
        dtick=2,
        row=5,
        col=1,
        showgrid=False,
    )

    fig.update_traces(cliponaxis=False)
    fig.update_layout(hovermode="closest")

    return fig


def render(_: pd.DataFrame) -> None:
    st.title(page_menu_title("Referidos"))

    paid_by_new_farmer = ANNUAL_SUBSCRIPTION_EUR - MONTH_DISCOUNT_NEW_EUR

    st.markdown(
        f"""
### Estrategia referidos

- **Agricultor que refiere**: recibe **{MONTH_DISCOUNT_REFERRER_EUR} €** de descuento (equivalente a **un mes descontado** sobre la cuota habitual).
- **Agricultor nuevo** (referido): si cumple las condiciones y hace **pago anual**, tiene el **primer mes descontado ({MONTH_DISCOUNT_NEW_EUR} €)**; el cobro efectivo orientativo es **{paid_by_new_farmer} €** sobre la cuota **anual tipo {ANNUAL_SUBSCRIPTION_EUR} €** (es decir, **{ANNUAL_SUBSCRIPTION_EUR} − {MONTH_DISCOUNT_NEW_EUR} €** una vez aplicado ese mes de descuento al nuevo).

En los gráficos, cada referido **cerrado** se modela como **{ANNUAL_SUBSCRIPTION_EUR} € de ingreso bruto** menos **{COST_PER_CLOSED_REFERRAL_EUR} €**
({MONTH_DISCOUNT_REFERRER_EUR} € + {MONTH_DISCOUNT_NEW_EUR} € de descuentos), es decir **≈ {NET_PER_REFERRAL_EUR:.0f} € netos incrementales por referido** en el año 1 (antes del regalo masivo).

- **Hito regalo**: cuando el agricultor referidor llega a **{REFERRALS_FOR_SENSOR_GIFT} referidos cerrados**, se le regala un sensor con **valor comercial orientativo de {SENSOR_GIFT_VALUE_EUR} €** (coste contable/regalo único modelado en los gráficos a partir de ese volumen).

*Supuesto de LTV*: **{LTV_EUR:.0f} €** (tres años de esa misma base económica) para el ratio **LTV/CAC** inferior; el umbral habitual en SaaS de **{LTV_CAC_HEALTHY_RATIO:.0f}x** se muestra como referencia orientativa.

---
"""
    )

    fig = build_referidos_figure()
    st.plotly_chart(fig, use_container_width=True)
