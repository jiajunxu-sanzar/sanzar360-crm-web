from __future__ import annotations

import streamlit as st

from ui.design_tokens import css_variables


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        """
        + css_variables()
        + """
        body, .stApp { font-family: var(--ui-font) !important; }
        /* Ocultar chrome de Streamlit (Deploy / menú / decoración) pero
           mantener el header vivo: ahí vive el botón >> para reabrir el
           sidebar cuando está compactado (stExpandSidebarButton). */
        [data-testid="stDecoration"] { display: none !important; }
        [data-testid="stAppDeployButton"],
        [data-testid="stToolbarActions"],
        [data-testid="stMainMenu"],
        [data-testid="stStatusWidget"] {
          display: none !important;
        }
        header[data-testid="stHeader"] {
          background: transparent !important;
        }
        /* Reabrir sidebar: siempre visible y clicable cuando el menú
           izquierdo está compactado. */
        [data-testid="stExpandSidebarButton"] {
          display: flex !important;
          visibility: visible !important;
          opacity: 1 !important;
          pointer-events: auto !important;
          position: fixed !important;
          top: 0.55rem !important;
          left: 0.55rem !important;
          z-index: 1000000 !important;
        }
        [data-testid="stExpandSidebarButton"] button {
          background: var(--ui-bg-elevated) !important;
          border: 1px solid var(--ui-border) !important;
          border-radius: 8px !important;
          color: var(--ui-text) !important;
          box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08) !important;
        }
        /* Page */
        .block-container {
          padding-top: 2rem;
          padding-bottom: 2rem;
          max-width: 1480px;
        }
        .main .block-container { background: var(--ui-bg-page); }
        div[data-testid="stSidebar"] {
          background: var(--ui-sidebar);
          border-right: 1px solid var(--ui-border);
        }
        /* Typography rhythm */
        h1 { font-weight: 600 !important; letter-spacing: -0.02em; color: var(--ui-text) !important; }
        h2, h3 { font-weight: 600 !important; color: var(--ui-text) !important; }
        h5 {
          margin: 0 0 var(--ui-spacing-sm) 0;
          color: var(--ui-text);
          font-weight: 600 !important;
        }
        .sanzar-contacts-block-spacer {
          margin-bottom: var(--ui-spacing-md);
        }

        /* Streamlit buttons — cohesive primary / secondary */
        .stButton > button[kind="primary"],
        div[data-testid="stSidebar"] button[kind="primary"] {
          background-color: var(--ui-accent) !important;
          color: var(--ui-accent-contrast) !important;
          border: 1px solid var(--ui-accent) !important;
          border-radius: var(--ui-radius-md) !important;
          font-weight: 550 !important;
        }
        .stButton > button[kind="primary"]:hover {
          background-color: var(--ui-accent-hover) !important;
          border-color: var(--ui-accent-hover) !important;
        }
        .stButton > button.crm-btn-strong,
        div[data-testid="stSidebar"] button.crm-btn-strong {
          background-color: var(--ui-primary-strong) !important;
          color: var(--ui-primary-strong-contrast) !important;
          border: 1px solid var(--ui-primary-strong) !important;
        }
        .stButton > button.crm-btn-strong:hover,
        div[data-testid="stSidebar"] button.crm-btn-strong:hover {
          background-color: var(--ui-primary-strong-active) !important;
          border-color: var(--ui-primary-strong-active) !important;
        }
        .stButton > button[kind="secondary"],
        .stButton > button[kind="tertiary"] {
          background: var(--ui-bg-elevated) !important;
          color: var(--ui-text) !important;
          border: 1px solid var(--ui-border) !important;
          border-radius: 8px !important;
          font-weight: 500 !important;
        }
        .stButton > button[kind="secondary"]:hover,
        .stButton > button[kind="tertiary"]:hover {
          background: #f4f4f5 !important;
          border-color: var(--ui-border-strong) !important;
        }

        /* ── Sidebar shell (Linear-style) ─────────────────────────────────── */
        div[data-testid="stSidebar"] .block-container,
        div[data-testid="stSidebar"] > div:first-child {
          padding-top: 1.1rem;
        }
        .sanzar-brand {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 2px 4px 10px;
        }
        .sanzar-brand-mark {
          width: 28px;
          height: 28px;
          border-radius: 8px;
          background: var(--ui-accent);
          color: var(--ui-accent-contrast);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.9375rem;
          letter-spacing: -0.02em;
          flex-shrink: 0;
        }
        .sanzar-brand-name {
          font-size: 1rem;
          font-weight: 650;
          letter-spacing: -0.02em;
          color: var(--ui-text);
          line-height: 1.1;
        }
        .sanzar-brand-sub {
          font-size: 0.6875rem;
          color: var(--ui-text-muted);
          margin-top: 1px;
        }
        div[data-testid="stSidebar"] img { border-radius: 6px; }

        /* User chip */
        .sanzar-user-chip {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 10px;
          margin: 2px 0 10px;
          border: 1px solid var(--ui-border);
          border-radius: 10px;
          background: var(--ui-bg-elevated);
        }
        .sanzar-user-avatar {
          width: 28px;
          height: 28px;
          border-radius: 999px;
          background: var(--sanzar-green-soft);
          color: var(--ui-accent-hover);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.75rem;
          font-weight: 700;
          flex-shrink: 0;
        }
        .sanzar-user-name {
          font-size: 0.8438rem;
          font-weight: 600;
          color: var(--ui-text);
          line-height: 1.2;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sanzar-user-role {
          font-size: 0.6875rem;
          color: var(--ui-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        /* Nav sections + items (buttons restyled as nav rows) */
        .sanzar-nav-section {
          margin: 10px 0 2px;
          padding: 0 4px;
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--ui-text-muted);
        }
        [class*="st-key-sanzar_nav"] div[data-testid="stVerticalBlock"] {
          gap: 0.14rem;
        }
        [class*="st-key-nav_btn_"] button {
          width: 100%;
          justify-content: flex-start !important;
          text-align: left !important;
          background: transparent !important;
          border: none !important;
          box-shadow: none !important;
          border-radius: 8px !important;
          padding: 0.3rem 0.55rem !important;
          min-height: 2.05rem !important;
          font-weight: 500 !important;
          font-size: 0.875rem !important;
          color: var(--ui-text-body) !important;
        }
        [class*="st-key-nav_btn_"] button:hover {
          background: var(--ui-hairline-soft) !important;
          color: var(--ui-text) !important;
        }
        [class*="st-key-nav_btn_"] button [data-testid="stIconMaterial"] {
          font-size: 1.05rem;
          color: var(--ui-text-muted);
        }
        [class*="st-key-nav_btn_"] button[kind="primary"] {
          background: var(--sanzar-green-soft) !important;
          color: var(--ui-accent-hover) !important;
          font-weight: 600 !important;
        }
        [class*="st-key-nav_btn_"] button[kind="primary"] [data-testid="stIconMaterial"] {
          color: var(--ui-accent) !important;
        }
        [class*="st-key-nav_btn_"] button[kind="primary"]:hover {
          background: var(--ui-accent-hover) !important;
          border-color: var(--ui-accent-hover) !important;
          color: var(--ui-accent-contrast) !important;
        }
        [class*="st-key-nav_btn_"] button[kind="primary"]:hover [data-testid="stIconMaterial"] {
          color: var(--ui-accent-contrast) !important;
        }
        [class*="st-key-nav_btn_"] button:focus:not(:focus-visible) {
          box-shadow: none !important;
        }

        /* Sidebar utilities (reload / reset / logout) */
        [class*="st-key-nav_util_"] button {
          background: transparent !important;
          border: 1px solid var(--ui-border) !important;
          border-radius: 8px !important;
          color: var(--ui-text-muted) !important;
          font-size: 0.8125rem !important;
          font-weight: 500 !important;
          min-height: 1.9rem !important;
          padding: 0.2rem 0.5rem !important;
        }
        [class*="st-key-nav_util_"] button:hover {
          background: var(--ui-hairline-soft) !important;
          color: var(--ui-text) !important;
          border-color: var(--ui-border-strong) !important;
        }
        .sanzar-sidebar-divider {
          border: none;
          border-top: 1px solid var(--ui-border);
          margin: 10px 0 8px;
        }

        /* Login card */
        .sanzar-login-title {
          margin: 4px 0 0 !important;
          font-size: 1.05rem !important;
          font-weight: 650 !important;
          color: var(--ui-text) !important;
        }
        .sanzar-login-sub {
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
          margin: 2px 0 8px;
        }

        /* ── Page header (todas las páginas) ──────────────────────────────── */
        .sanzar-page-header {
          margin: 0 0 1.1rem;
          padding-bottom: 0.85rem;
          border-bottom: 1px solid var(--ui-border);
        }
        .sanzar-page-title {
          margin: 0 !important;
          padding: 0 !important;
          font-size: 1.55rem !important;
          font-weight: 650 !important;
          letter-spacing: -0.025em !important;
          line-height: 1.2 !important;
          color: var(--ui-text) !important;
        }
        .sanzar-page-desc {
          margin: 4px 0 0 !important;
          padding: 0 !important;
          font-size: 0.875rem;
          color: var(--ui-text-muted);
          line-height: 1.45;
        }

        /* Contact list rows (buttons) — table-like, quiet */
        [class*="st-key-contact_row_"] button {
          width: 100%;
          justify-content: flex-start !important;
          text-align: left !important;
          background: transparent !important;
          border: none !important;
          border-bottom: 1px solid var(--ui-hairline-soft) !important;
          border-radius: 6px !important;
          padding: 0.34rem 0.6rem !important;
          min-height: 2rem !important;
          font-size: 0.8438rem !important;
          font-weight: 450 !important;
          color: var(--ui-text-body) !important;
          box-shadow: none !important;
        }
        [class*="st-key-contact_row_"] button:hover {
          background: var(--ui-hairline-soft) !important;
          color: var(--ui-text) !important;
        }

        /* Sidebar — blocked/unavailable pages */
        .sanzar-nav-blocked-label {
          margin: 6px 0 4px;
          color: var(--ui-text-muted);
          font-size: 0.78rem;
          font-weight: 500;
        }
        .sanzar-nav-blocked-item {
          padding: 4px 10px;
          margin-bottom: 4px;
          border: 1px solid var(--ui-border);
          border-radius: 8px;
          color: var(--ui-text-muted);
          background: var(--ui-bg-page);
          font-size: 0.85rem;
        }

        /* ── Global input/control refinements (Linear-style) ─────────────── */
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div {
          border-radius: 8px !important;
          border-color: var(--ui-border) !important;
          background: var(--ui-bg-elevated) !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within {
          border-color: var(--ui-accent) !important;
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--ui-accent) 14%, transparent) !important;
        }
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        .stSelectbox div[data-baseweb="select"] {
          font-size: 0.875rem !important;
        }
        div[data-testid="stWidgetLabel"] p {
          font-size: 0.8125rem !important;
          font-weight: 500;
          color: var(--ui-text-body);
        }
        details[data-testid="stExpander"] {
          border: 1px solid var(--ui-border) !important;
          border-radius: 10px !important;
          background: var(--ui-bg-elevated);
        }
        details[data-testid="stExpander"] summary {
          font-size: 0.875rem;
          font-weight: 550;
        }
        div[data-testid="stDialog"] > div:first-child {
          border-radius: 14px !important;
        }
        div[data-testid="stForm"] {
          border: 1px solid var(--ui-border) !important;
          border-radius: 12px !important;
        }
        button[data-baseweb="tab"] {
          font-size: 0.875rem !important;
          font-weight: 500 !important;
        }
        /* Cards & chips */
        .sanzar-card {
          border: 1px solid var(--ui-border);
          border-radius: 12px;
          padding: 16px;
          background: var(--ui-bg-elevated);
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
          margin-bottom: 12px;
        }
        .sanzar-card h3 { margin-top: 0; margin-bottom: 8px; font-weight: 600 !important; font-size: 1.05rem !important; }
        .sanzar-chip {
          display: inline-block;
          padding: 5px 11px;
          border-radius: 6px;
          font-size: 0.8125rem;
          font-weight: 500;
          line-height: 1.25;
          margin-right: 6px;
          margin-bottom: 6px;
        }
        .sanzar-kv { color: var(--ui-text-muted); font-size: 0.875rem; }
        .sanzar-muted { color: var(--ui-text-muted); font-size: 0.875rem; }
        .sanzar-table-note { color: var(--ui-text-muted); font-size: 0.85rem; margin-top: -8px; }

        /* Shared KPI cards (Dashboard + Acciones) */
        .sanzar-kpi,
        .sanzar-acciones-kpi {
          border: 1px solid var(--ui-border);
          border-radius: 14px;
          padding: 16px 18px;
          background: var(--ui-kpi-neutral-bg);
          margin-bottom: 8px;
        }
        .sanzar-kpi--success,
        .sanzar-acciones-kpi--success {
          background: var(--ui-kpi-success-bg);
          border-color: var(--ui-kpi-success-border);
        }
        .sanzar-kpi--danger,
        .sanzar-acciones-kpi--danger {
          background: var(--ui-kpi-danger-bg);
          border-color: var(--ui-kpi-danger-border);
        }
        .sanzar-kpi--info {
          background: var(--ui-kpi-info-bg);
          border-color: var(--ui-kpi-info-border);
        }
        .sanzar-kpi--warning {
          background: var(--ui-kpi-warning-bg);
          border-color: var(--ui-kpi-warning-border);
        }
        .sanzar-kpi-label,
        .sanzar-acciones-kpi-label {
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
          margin-bottom: 6px;
        }
        .sanzar-kpi-value,
        .sanzar-acciones-kpi-value {
          font-size: 2rem;
          font-weight: 650;
          letter-spacing: -0.03em;
          color: var(--ui-text);
          line-height: 1.1;
        }
        .sanzar-kpi-help {
          margin-top: 6px;
          font-size: 0.75rem;
          color: var(--ui-text-muted);
        }
        /* Dashboard ranked lists + funnel */
        .sanzar-dash-section {
          margin-bottom: 8px;
        }
        .sanzar-dash-rank-card,
        .sanzar-dash-funnel-card {
          border: 1px solid var(--ui-border);
          border-radius: 12px;
          padding: 12px 14px;
          background: var(--ui-bg-elevated);
          margin-bottom: 10px;
        }
        .sanzar-dash-rank-head,
        .sanzar-dash-funnel-head {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 8px;
        }
        .sanzar-dash-rank-title,
        .sanzar-dash-funnel-title {
          font-size: 0.9375rem;
          font-weight: 650;
          color: var(--ui-text);
        }
        .sanzar-dash-rank-value,
        .sanzar-dash-funnel-value {
          font-size: 0.875rem;
          font-weight: 600;
          color: var(--ui-text-muted);
        }
        .sanzar-dash-rank-track,
        .sanzar-dash-funnel-track {
          height: 10px;
          border-radius: 999px;
          background: #f4f4f5;
          overflow: hidden;
          margin-bottom: 4px;
        }
        .sanzar-dash-rank-fill,
        .sanzar-dash-funnel-fill {
          height: 100%;
          border-radius: 999px;
          background: #cbd5e1;
        }
        .sanzar-dash-funnel-meta {
          font-size: 0.75rem;
          color: var(--ui-text-muted);
        }
        .sanzar-acciones-week-caption {
          text-align: center;
          margin: 0.35rem 0 0.75rem;
          font-size: 0.9375rem;
          color: var(--ui-text);
        }
        .sanzar-acciones-person-card,
        .sanzar-acciones-week-snapshot,
        .sanzar-acciones-canal-rate-card {
          border: 1px solid var(--ui-border);
          border-radius: 14px;
          padding: 14px 16px;
          background: var(--ui-bg-elevated);
          margin-bottom: 12px;
        }
        .sanzar-acciones-person-head,
        .sanzar-acciones-week-snapshot-head,
        .sanzar-acciones-canal-rate-head {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 8px;
        }
        .sanzar-acciones-person-name,
        .sanzar-acciones-week-snapshot-when,
        .sanzar-acciones-canal-rate-title {
          font-size: 1rem;
          font-weight: 650;
          color: var(--ui-text);
        }
        .sanzar-acciones-person-total,
        .sanzar-acciones-week-snapshot-total,
        .sanzar-acciones-canal-rate-pct {
          font-size: 0.875rem;
          font-weight: 600;
          color: var(--ui-text-muted);
        }
        .sanzar-acciones-person-summary,
        .sanzar-acciones-week-snapshot-summary {
          margin-bottom: 10px;
        }
        .sanzar-acciones-canal-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 8px;
        }
        .sanzar-acciones-canal-item {
          border: 1px dashed var(--ui-border);
          border-radius: 10px;
          padding: 8px 10px;
          background: rgba(255, 255, 255, 0.55);
        }
        .sanzar-acciones-canal-item-label {
          font-size: 0.75rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--ui-text-muted);
          margin-bottom: 4px;
        }
        .sanzar-acciones-canal-item-stats {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          font-size: 0.8125rem;
          color: var(--ui-text);
        }
        .sanzar-acciones-stat-ok { color: var(--ui-semantic-success); font-weight: 600; }
        .sanzar-acciones-stat-ko { color: var(--ui-semantic-error); font-weight: 600; }
        .sanzar-acciones-person-btn-spacer { height: 18px; }
        .sanzar-acciones-canal-rate-track {
          height: 10px;
          border-radius: 999px;
          background: #f4f4f5;
          overflow: hidden;
          margin-bottom: 8px;
        }
        .sanzar-acciones-canal-rate-fill {
          height: 100%;
          border-radius: 999px;
        }
        .sanzar-acciones-canal-rate-fill--high { background: #86efac; }
        .sanzar-acciones-canal-rate-fill--mid { background: #fde68a; }
        .sanzar-acciones-canal-rate-fill--low { background: #fca5a5; }
        .sanzar-acciones-canal-rate-meta {
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
        }

        /* Inventario cards */
        .sanzar-inv-card,
        .sanzar-inv-assoc-card,
        .sanzar-inv-conflict-card {
          border: 1px solid var(--ui-border);
          border-radius: 12px;
          padding: 14px 16px;
          background: var(--ui-bg-elevated);
          margin-bottom: 10px;
          transition: border-color 120ms ease, box-shadow 120ms ease;
        }
        .sanzar-inv-card:hover {
          border-color: var(--ui-border-strong);
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
        }
        .sanzar-inv-chip {
          display: inline-block;
          padding: 2px 9px;
          border-radius: 999px;
          font-size: 0.6875rem;
          font-weight: 650;
          letter-spacing: 0.05em;
          border: 1px solid transparent;
        }
        .sanzar-inv-chip--em500     { background: #eaf4ee; color: #1e4d38; border-color: #cde5d7; }
        .sanzar-inv-chip--uc501     { background: #eff6ff; color: #1e40af; border-color: #d4e4fb; }
        .sanzar-inv-chip--ug67      { background: #f5f3ff; color: #5b21b6; border-color: #e4defc; }
        .sanzar-inv-chip--sim       { background: #fffbeb; color: #92400e; border-color: #fdeec2; }
        .sanzar-inv-chip--solenoide { background: #ecfeff; color: #155e75; border-color: #cbf3fa; }
        .sanzar-inv-chip--probe     { background: #f0fdfa; color: #115e59; border-color: #ccf1e9; }
        .sanzar-inv-chip--ecowitt   { background: #fef3c7; color: #92400e; border-color: #fde68a; }
        .sanzar-inv-chip--ecowitt-gw { background: #ffedd5; color: #9a3412; border-color: #fed7aa; }
        .sanzar-inv-chip--default   { background: #f4f4f5; color: #52525b; border-color: #e4e4e7; }
        .sanzar-inv-card-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin: 2px 0 10px;
        }
        .sanzar-inv-pill {
          display: inline-block;
          padding: 2px 9px;
          border-radius: 999px;
          font-size: 0.75rem;
          font-weight: 550;
          background: #fafafa;
          border: 1px solid var(--ui-border);
          color: var(--ui-text-body);
        }
        .sanzar-inv-pill--loc {
          background: var(--sanzar-green-soft);
          border-color: color-mix(in srgb, var(--ui-accent) 25%, #ffffff);
          color: var(--ui-accent-hover);
        }
        .sanzar-inv-pill--ok {
          background: var(--ui-kpi-success-bg);
          border-color: var(--ui-kpi-success-border);
          color: #166534;
        }
        .sanzar-inv-card-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
          gap: 4px 20px;
        }
        .sanzar-inv-kv {
          display: flex;
          align-items: baseline;
          gap: 8px;
          min-width: 0;
          font-size: 0.8125rem;
        }
        .sanzar-inv-kv-label {
          flex-shrink: 0;
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--ui-text-muted);
        }
        .sanzar-inv-kv-value {
          color: var(--ui-text);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sanzar-inv-kv-value--mono {
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 0.78rem;
          letter-spacing: 0.01em;
        }
        .sanzar-inv-card-head {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .sanzar-inv-card-sn {
          font-size: 0.95rem;
          font-weight: 650;
          color: var(--ui-text);
        }
        .sanzar-inv-card-model {
          font-size: 0.8125rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--ui-text-muted);
        }
        .sanzar-inv-card-meta {
          margin-bottom: 6px;
          font-size: 0.75rem;
          color: var(--ui-text-muted);
        }
        .sanzar-inv-card-line {
          font-size: 0.8125rem;
          color: var(--ui-text);
          line-height: 1.4;
          margin-bottom: 2px;
        }
        .sanzar-inv-card-label {
          color: var(--ui-text-muted);
          font-weight: 600;
        }
        .sanzar-inv-card-edit-spacer { height: 16px; }
        .sanzar-inv-state--en-uso,
        .sanzar-inv-state--disponible {
          display: inline-block;
          border-radius: 999px;
          padding: 3px 10px;
          font-size: 0.75rem;
          font-weight: 600;
        }
        .sanzar-inv-state--en-uso {
          color: #166534;
          background: #dcfce7;
          border: 1px solid #86efac;
        }
        .sanzar-inv-state--disponible {
          color: #991b1b;
          background: #fee2e2;
          border: 1px solid #fca5a5;
        }
        .sanzar-inv-pagination-caption {
          text-align: center;
          margin: 0.4rem 0 0.7rem;
          font-size: 0.875rem;
          color: var(--ui-text-muted);
        }

        .sanzar-alarm-card {
          border-radius: 12px;
          padding: 12px;
          margin-bottom: 10px;
          background: var(--ui-bg-elevated);
          border: 1px solid var(--ui-border);
        }

        /* Alarms — work inbox row */
        .sanzar-inbox-spacer { height: 6px; }
        .sanzar-inbox-card {
          border: 1px solid var(--ui-border);
          border-left-width: 4px;
          border-radius: 12px;
          padding: 14px 16px;
          background: var(--ui-bg-elevated);
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
          text-align: left;
        }
        .sanzar-inbox-eyebrow {
          display: flex;
          flex-wrap: wrap;
          align-items: baseline;
          gap: 8px 12px;
          margin-bottom: 10px;
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
        }
        .sanzar-inbox-badge {
          display: inline-block;
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          padding: 3px 8px;
          border-radius: 6px;
          background: #f4f4f5;
          border: 1px solid var(--ui-border);
          color: var(--ui-text-muted);
        }
        .sanzar-inbox-prio { color: var(--ui-text-muted); }
        .sanzar-inbox-prio strong { color: var(--ui-text); font-weight: 600; }
        .sanzar-inbox-sep {
          flex: 1 1 8px;
          min-width: 0;
          height: 0;
        }
        .sanzar-inbox-when-label {
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .sanzar-inbox-when { color: var(--ui-text); font-weight: 500; }
        .sanzar-inbox-title {
          margin: 0 0 8px 0 !important;
          padding: 0 !important;
          font-size: 1.0625rem !important;
          font-weight: 600 !important;
          letter-spacing: -0.015em !important;
          color: var(--ui-text) !important;
          line-height: 1.3 !important;
        }
        .sanzar-inbox-context {
          margin: 0 0 8px 0 !important;
          padding: 0 !important;
          font-size: 0.8125rem;
          font-weight: 500;
          color: #737373;
        }
        .sanzar-inbox-detail {
          margin: 0 0 10px 0 !important;
          padding: 0 !important;
          font-size: 0.875rem;
          color: var(--ui-text-muted);
          line-height: 1.45;
        }
        .sanzar-inbox-owner {
          font-size: 0.875rem;
          color: var(--ui-text);
          margin-bottom: 12px;
        }
        .sanzar-inbox-next {
          padding: 10px 12px;
          background: #fafafa;
          border: 1px solid var(--ui-border);
          border-radius: 8px;
        }
        .sanzar-inbox-next-label {
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--ui-text-muted);
          margin-bottom: 6px;
        }
        .sanzar-inbox-next-text {
          font-size: 0.875rem;
          color: var(--ui-text);
          line-height: 1.45;
          font-weight: 500;
        }

        /* Ficha cliente — línea de tiempo unificada */
        .sanzar-timeline-shell {
          margin: 0 0 0.75rem;
          padding: 0;
        }
        .sanzar-timeline-legends {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 14px;
        }
        .san-tl-chip {
          display: inline-block;
          padding: 3px 9px;
          border-radius: 6px;
          font-size: 0.6875rem;
          font-weight: 600;
          letter-spacing: 0.03em;
          border: 1px solid var(--ui-border);
        }
        .san-tl-sensor { background: #ecfdf5; color: #14532d; border-color: #bbf7d0; }
        .san-tl-campana { background: #eef2ff; color: #312e81; border-color: #c7d2fe; }
        .san-tl-pago { background: #faf5ff; color: #6b21a8; border-color: #e9d5ff; }
        .san-tl-incidencia { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
        .sanzar-timeline-month {
          margin-bottom: 1rem;
          padding-bottom: 0.5rem;
        }
        .sanzar-timeline-month-title {
          margin: 0 0 10px !important;
          padding-bottom: 6px;
          font-size: 0.9375rem !important;
          font-weight: 650 !important;
          letter-spacing: -0.01em !important;
          color: var(--ui-text-muted) !important;
          border-bottom: 1px solid var(--ui-border);
        }
        .sanzar-timeline-list {
          position: relative;
          margin-left: 6px;
          padding-left: 18px;
          border-left: 2px solid #e5e5e5;
        }
        .sanzar-timeline-item {
          position: relative;
          padding: 12px 0 12px 4px;
          margin-left: -2px;
        }
        .sanzar-timeline-item:last-child {
          padding-bottom: 4px;
        }
        .sanzar-timeline-dot {
          position: absolute;
          left: -22px;
          top: 18px;
          width: 10px;
          height: 10px;
          border-radius: 999px;
          background: var(--ui-text-muted);
          border: 2px solid var(--ui-bg-elevated);
        }
        .sanzar-timeline-item[data-kind^="sensor-"] .sanzar-timeline-dot { background: var(--ui-accent); }
        .sanzar-timeline-item[data-kind^="campana-"] .sanzar-timeline-dot { background: #4f46e5; }
        .sanzar-timeline-item[data-kind^="pago"] .sanzar-timeline-dot,
        .sanzar-timeline-item[data-kind^="pago-"] .sanzar-timeline-dot { background: #7c3aed; }
        .sanzar-timeline-item[data-kind^="incidencia-"] .sanzar-timeline-dot { background: #dc2626; }
        .sanzar-timeline-head time {
          display: block;
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--ui-text-muted);
          margin-bottom: 4px;
        }
        .sanzar-timeline-title {
          margin: 0 !important;
          padding: 0 !important;
          font-size: 0.9375rem !important;
          font-weight: 600 !important;
          color: var(--ui-text) !important;
          line-height: 1.35 !important;
        }
        .sanzar-timeline-ul {
          margin: 8px 0 0 !important;
          padding-left: 1rem !important;
          font-size: 0.8125rem !important;
          color: var(--ui-text-muted) !important;
          line-height: 1.45;
        }

        /* Botón destructivo: confirmación de borrado en rojo, no verde corporativo.
           Selectores con button[kind] para superar la regla global de primarios. */
        .st-key-btn_confirm_delete_contact button[kind="primary"] {
          background: #dc2626 !important;
          border-color: #dc2626 !important;
          color: #ffffff !important;
        }
        .st-key-btn_confirm_delete_contact button[kind="primary"]:hover {
          background: #b91c1c !important;
          border-color: #b91c1c !important;
        }
        .st-key-btn_destruct_contact_ficha button[kind="secondary"] {
          color: #b91c1c !important;
          border-color: #fecaca !important;
        }
        .st-key-btn_destruct_contact_ficha button[kind="secondary"]:hover {
          background: #fef2f2 !important;
          border-color: #fca5a5 !important;
        }

        /* Panel de detalle de históricos (tabla + fila seleccionada) */
        .sanzar-detail-field {
          margin-bottom: 10px;
        }
        .sanzar-detail-label {
          color: var(--ui-text-muted);
          font-size: 0.72rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .sanzar-detail-value {
          font-size: 0.875rem;
          color: var(--ui-text);
          word-break: break-word;
        }

        /* Contact list */
        .sanzar-contact-table {
          border: 1px solid var(--ui-border);
          border-radius: 12px;
          overflow: hidden;
          background: var(--ui-bg-elevated);
          margin-bottom: 12px;
        }
        .sanzar-contact-row {
          display: grid;
          grid-template-columns: 1.55fr .95fr .95fr .95fr;
          gap: 8px;
          padding: 9px 11px;
          border-bottom: 1px solid #f4f4f5;
          color: var(--ui-text) !important;
          text-decoration: none !important;
          align-items: center;
        }
        .sanzar-contact-row:hover { background: #fafafa; }
        .sanzar-contact-row.selected {
          background: rgba(37, 99, 235, 0.06);
          outline: 2px solid #2563eb;
          outline-offset: -2px;
          border-radius: 8px;
          border-bottom-color: transparent;
          font-weight: 600;
        }
        .sanzar-contact-row-lost {
          background: #fef2f2;
          color: #991b1b !important;
          outline-color: #dc2626 !important;
        }
        .sanzar-contact-header {
          background: #fafafa;
          color: var(--ui-text-muted) !important;
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .sanzar-contact-cell {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 0.875rem;
        }
        .sanzar-overview-table .sanzar-overview-header,
        .sanzar-overview-table .sanzar-overview-row {
          grid-template-columns: 1.2fr 1.4fr 1fr 1.2fr 0.7fr;
        }
        .sanzar-overview-row--verde {
          background: var(--ui-kpi-success-bg);
        }
        .sanzar-overview-row--amarillo {
          background: var(--ui-kpi-warning-bg);
        }
        .sanzar-overview-row--neutral {
          background: var(--ui-kpi-neutral-bg);
        }
        .sanzar-overview-table--expanded .sanzar-contact-cell {
          white-space: normal;
          overflow: visible;
          text-overflow: unset;
          word-break: break-word;
          line-height: 1.35;
        }
        .sanzar-overview-table--expanded .sanzar-overview-row {
          align-items: start;
        }
        .sanzar-overview-table--expanded .sanzar-overview-header,
        .sanzar-overview-table--expanded .sanzar-overview-row {
          grid-template-columns: 1.4fr 2fr 1.2fr 1.4fr 0.8fr;
        }

        /* Clientes — daily board cards */
        .sanzar-cliente-card {
          padding: 4px 2px 8px;
          margin-bottom: 4px;
        }
        .sanzar-cliente-card.visto .sanzar-cliente-card__title {
          color: var(--ui-text);
        }
        .sanzar-cliente-card--cliente.visto,
        .sanzar-cliente-card--potencial.visto {
          border-radius: 10px;
          padding: 10px 12px 8px;
          background: var(--ui-kpi-success-bg);
          border: 1px solid color-mix(in srgb, var(--ui-kpi-success-bg) 70%, #16a34a);
          margin-bottom: 8px;
        }
        .sanzar-cliente-card__top {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .sanzar-cliente-badge {
          display: inline-block;
          font-size: 0.7rem;
          font-weight: 650;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          padding: 3px 8px;
          border-radius: 6px;
          border: 1px solid var(--ui-border);
          color: var(--ui-text-muted);
          background: #fafafa;
        }
        .sanzar-cliente-badge--cliente {
          color: #166534;
          border-color: #bbf7d0;
          background: #f0fdf4;
        }
        .sanzar-cliente-badge--potencial {
          color: #1e40af;
          border-color: #bfdbfe;
          background: #eff6ff;
        }
        .sanzar-cliente-card__title {
          margin: 0 0 10px 0 !important;
          padding: 0 !important;
          font-size: 1.05rem !important;
          font-weight: 650 !important;
          color: var(--ui-text) !important;
          line-height: 1.3 !important;
        }
        .sanzar-cliente-card__meta {
          margin: 0;
          display: grid;
          gap: 8px;
        }
        .sanzar-cliente-card__meta > div {
          display: grid;
          gap: 2px;
        }
        .sanzar-cliente-card__meta dt {
          margin: 0;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--ui-text-muted);
        }
        .sanzar-cliente-card__meta dd {
          margin: 0;
          font-size: 0.875rem;
          color: var(--ui-text);
          line-height: 1.35;
          word-break: break-word;
        }
        @media (max-width: 768px) {
          .sanzar-cliente-card__title {
            font-size: 1rem !important;
          }
        }

        /* Contact detail — operational header */
        .sanzar-detail-header {
          position: sticky;
          top: 0.25rem;
          z-index: 30;
          margin-bottom: 1rem;
          padding: 14px 18px 16px;
          background: var(--ui-bg-elevated);
          border: 1px solid var(--ui-border);
          border-radius: 12px;
          box-shadow: 0 2px 12px rgba(15, 23, 42, 0.07);
        }
        .sanzar-detail-header--with-flags {
          margin-bottom: 0;
          border-bottom-left-radius: 0;
          border-bottom-right-radius: 0;
          border-bottom: none;
          box-shadow: none;
        }
        /* Franja de flags: el row de columnas que contiene el marcador, pegado al header */
        div[data-testid="stHorizontalBlock"]:has(.sanzar-flags-marker) {
          margin: 0 0 1rem 0 !important;
          padding: 10px 18px 14px !important;
          background: var(--ui-bg-elevated);
          border: 1px solid var(--ui-border);
          border-top: 1px dashed var(--ui-border);
          border-radius: 0 0 12px 12px;
          box-shadow: 0 2px 12px rgba(15, 23, 42, 0.07);
        }
        .sanzar-detail-header-top {
          display: flex;
          flex-wrap: wrap;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px 16px;
          margin-bottom: 12px;
        }
        .sanzar-detail-title-block { min-width: 0; flex: 1 1 220px; }
        .sanzar-detail-title {
          margin: 0 !important;
          padding: 0 !important;
          font-size: 1.375rem !important;
          font-weight: 650 !important;
          letter-spacing: -0.02em !important;
          line-height: 1.2 !important;
          color: var(--ui-text) !important;
        }
        .sanzar-detail-subline {
          margin: 6px 0 0 !important;
          padding: 0 !important;
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
          line-height: 1.45;
        }
        .sanzar-detail-id {
          font-size: 0.75rem;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          background: #f4f4f5;
          padding: 2px 6px;
          border-radius: 4px;
          border: 1px solid var(--ui-border);
          word-break: break-all;
        }
        .sanzar-detail-chips-primary,
        .sanzar-detail-chips-secondary {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
        }
        .sanzar-detail-chips-primary { justify-content: flex-end; flex: 1 1 140px; }
        .sanzar-detail-last-contact {
          padding: 8px 12px;
          margin-bottom: 10px;
          background: #f8fafc;
          border: 1px solid var(--ui-border);
          border-radius: 8px;
        }
        .sanzar-detail-last-contact-label {
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--ui-text-muted);
          margin-bottom: 4px;
        }
        .sanzar-detail-last-contact-row {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
        }
        .sanzar-detail-last-contact-when {
          font-size: 0.8125rem;
          font-weight: 550;
          color: var(--ui-text);
        }
        .sanzar-detail-last-contact-sub {
          margin: 4px 0 0 !important;
          padding: 0 !important;
          font-size: 0.75rem;
          color: var(--ui-text-muted);
          line-height: 1.4;
        }
        .sanzar-detail-last-contact-line {
          margin: 0 !important;
          font-size: 0.75rem;
        }
        .sanzar-detail-next {
          padding: 10px 12px;
          margin-bottom: 12px;
          background: #fafafa;
          border: 1px solid var(--ui-border);
          border-radius: 8px;
        }
        .sanzar-detail-next-label {
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--ui-text-muted);
          margin-bottom: 6px;
        }
        .sanzar-detail-next-row {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 10px;
        }
        .sanzar-detail-persona {
          font-size: 0.875rem;
          color: var(--ui-text);
          font-weight: 550;
        }
        .sanzar-detail-next-detail {
          margin: 8px 0 0 !important;
          padding: 0 !important;
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
          line-height: 1.45;
        }
        .sanzar-detail-task-more {
          margin: 6px 0 0 !important;
          padding: 0 !important;
          font-size: 0.75rem;
          line-height: 1.35;
        }
        .sanzar-detail-footer-row {
          display: flex;
          flex-wrap: wrap;
          align-items: flex-end;
          justify-content: space-between;
          gap: 10px 16px;
        }
        .sanzar-detail-contact-line {
          font-size: 0.8125rem;
          color: var(--ui-text);
          line-height: 1.5;
        }

        /* Seguimiento comercial + históricos operativos — cards in contact ficha */
        .sanzar-seg-card,
        .sanzar-hist-card {
          margin: 0 0 4px 0;
          padding: 12px 14px;
          border-radius: 10px;
          border: 1px solid var(--ui-border);
          background: var(--ui-bg-elevated);
        }
        .sanzar-seg-card--exitoso,
        .sanzar-hist-card--exitoso {
          border-left: 4px solid var(--ui-accent);
          background: var(--ui-kpi-success-bg);
        }
        .sanzar-seg-card--fallido,
        .sanzar-hist-card--fallido {
          border-left: 4px solid var(--ui-semantic-error);
          background: var(--ui-kpi-danger-bg);
        }
        .sanzar-seg-card--neutral,
        .sanzar-hist-card--neutral {
          border-left: 4px solid var(--ui-border-strong);
        }
        .sanzar-hist-card--warning {
          border-left: 4px solid var(--ui-semantic-warning);
          background: var(--ui-kpi-warning-bg);
        }
        .sanzar-seg-card-head,
        .sanzar-hist-card-head {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 4px;
        }
        .sanzar-seg-card-when,
        .sanzar-hist-card-when {
          font-size: 0.9375rem;
          font-weight: 600;
          color: var(--ui-text);
        }
        .sanzar-seg-card-sub,
        .sanzar-hist-card-sub {
          font-size: 0.8125rem;
          color: var(--ui-text-muted);
          margin-bottom: 6px;
        }
        .sanzar-hist-card-body {
          font-size: 0.8125rem;
          color: var(--ui-text);
          margin-bottom: 6px;
          line-height: 1.45;
        }
        .sanzar-seg-card-notes,
        .sanzar-hist-card-notes {
          margin: 0 0 8px 0 !important;
          font-size: 0.8125rem;
          color: var(--ui-text);
          line-height: 1.45;
        }
        .sanzar-hist-card-extra {
          padding: 8px 10px;
          margin: 4px 0 8px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.65);
          border: 1px dashed var(--ui-border);
          font-size: 0.8125rem;
        }
        .sanzar-seg-card-proxima {
          padding: 8px 10px;
          margin-top: 4px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.65);
          border: 1px dashed var(--ui-border);
          font-size: 0.8125rem;
        }
        .sanzar-seg-card-proxima-detail {
          margin: 4px 0 0 !important;
          font-size: 0.75rem;
          color: var(--ui-text-muted);
        }
        .sanzar-seg-card-meta-label,
        .sanzar-hist-card-meta-label {
          font-size: 0.6875rem;
          font-weight: 650;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--ui-text-muted);
          margin-right: 4px;
        }
        .sanzar-seg-card-meta,
        .sanzar-hist-card-meta {
          margin-top: 6px;
          font-size: 0.6875rem;
          color: var(--ui-text-muted);
        }
        .sanzar-seg-card-edit-spacer,
        .sanzar-hist-card-edit-spacer {
          height: 12px;
        }

        /* Pricing — mode badge */
        .sanzar-badge-proveedor {
          display: inline-block;
          padding-top: 1.4rem;
          text-align: right;
          color: #d97706;
          font-weight: 700;
          font-size: 0.85rem;
        }
        .sanzar-badge-cliente {
          display: inline-block;
          padding-top: 1.4rem;
          text-align: right;
          color: #6b7280;
          font-weight: 700;
          font-size: 0.85rem;
        }

        /* Vacaciones — calendar legend */
        .sanzar-legend-row {
          font-size: 0.9rem;
          margin-bottom: 8px;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px 14px;
        }
        .sanzar-legend-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .sanzar-legend-item::before {
          content: '';
          display: inline-block;
          width: 12px;
          height: 12px;
          border-radius: 2px;
          flex-shrink: 0;
        }
        .sanzar-legend-ausencia::before  { background: #fecaca; border: 1px solid #fca5a5; }
        .sanzar-legend-teletrabajo::before { background: #fef08a; border: 1px solid #fde047; }
        .sanzar-legend-festivo::before   { background: #dbeafe; border: 1px solid #93c5fd; }

        /* Form section titles — override inline pastel blocks for one neutral look */
        .sanzar-form-section-title {
          border-radius: 8px !important;
          padding: 9px 12px !important;
          font-size: 0.875rem !important;
          font-weight: 600 !important;
          color: var(--ui-text) !important;
          border: 1px solid var(--ui-border) !important;
          background: #fafafa !important;
          margin: 10px 0 8px 0 !important;
        }

        /* ── Dashboard próximas acciones bucket buttons ────────────────────────
         * Idle state: white bg, grey border, no accent stripe.
         * Active state is driven by a left border; the Python side passes the
         * active_bucket value but we keep the colour rules here — static, no
         * per-rerun <style> injection.
         */
        .st-key-dash_bucket_past button,
        .st-key-dash_bucket_today button,
        .st-key-dash_bucket_tomorrow button,
        .st-key-dash_bucket_future button {
          background: var(--ui-bg-elevated) !important;
          border: 1px solid var(--ui-border) !important;
          border-left: 3px solid transparent !important;
          color: var(--ui-text-body) !important;
          border-radius: var(--ui-radius-md) !important;
          font-weight: 500 !important;
        }
        .st-key-dash_bucket_past button[kind="primary"]     { border-left: 3px solid var(--ui-bucket-past) !important; background: var(--ui-surface-soft) !important; border-color: var(--ui-border-strong) !important; color: var(--ui-text) !important; }
        .st-key-dash_bucket_today button[kind="primary"]    { border-left: 3px solid var(--ui-bucket-today) !important; background: var(--ui-surface-soft) !important; border-color: var(--ui-border-strong) !important; color: var(--ui-text) !important; }
        .st-key-dash_bucket_tomorrow button[kind="primary"],
        .st-key-dash_bucket_future button[kind="primary"] { border-left: 3px solid var(--ui-bucket-future) !important; background: var(--ui-surface-soft) !important; border-color: var(--ui-border-strong) !important; color: var(--ui-text) !important; }
        .st-key-dash_bucket_past button[kind="primary"]:hover     { background: var(--ui-hairline-soft) !important; border-left-color: var(--ui-bucket-past) !important; }
        .st-key-dash_bucket_today button[kind="primary"]:hover    { background: var(--ui-hairline-soft) !important; border-left-color: var(--ui-bucket-today) !important; }
        .st-key-dash_bucket_tomorrow button[kind="primary"]:hover,
        .st-key-dash_bucket_future button[kind="primary"]:hover { background: var(--ui-hairline-soft) !important; border-left-color: var(--ui-bucket-future) !important; }

        /* ── Semantic button tiers (key-prefix based, generic and stable) ──────
         * Save / confirm: any button or form-submit whose widget key starts with
         * btn_save_  e.g. key="btn_save_contact", key="btn_save_vac_add"
         */
        [class*="st-key-btn_save_"] button {
          background: var(--ui-btn-save-bg) !important;
          color: var(--ui-btn-save-fg) !important;
          border: 1px solid var(--ui-accent-hover) !important;
          border-radius: 8px !important;
          font-weight: 600 !important;
        }
        [class*="st-key-btn_save_"] button:hover {
          background: var(--ui-btn-save-hover) !important;
          border-color: var(--ui-accent-hover) !important;
        }

        /* Destructive: key starts with btn_destruct_ */
        [class*="st-key-btn_destruct_"] button {
          background: var(--ui-btn-destruct-bg) !important;
          color: var(--ui-btn-destruct-fg) !important;
          border: 1px solid var(--ui-btn-destruct-border) !important;
          border-radius: 8px !important;
          font-weight: 600 !important;
        }
        [class*="st-key-btn_destruct_"] button:hover {
          background: var(--ui-btn-destruct-hover) !important;
        }

        /* Neutral / cancel: key starts with btn_neutral_ */
        [class*="st-key-btn_neutral_"] button {
          background: var(--ui-btn-neutral-bg) !important;
          color: var(--ui-btn-neutral-fg) !important;
          border: 1px solid var(--ui-btn-neutral-border) !important;
          border-radius: 8px !important;
          font-weight: 500 !important;
        }
        [class*="st-key-btn_neutral_"] button:hover {
          background: var(--ui-btn-neutral-hover) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# Injected from streamlit_app when the Tareas inbox has pending items.
NAV_ALARMS_PENDING_TAREAS_CSS = """
[class*="st-key-nav_btn_centro_de_alarmas"] button[kind="tertiary"] {
  color: var(--ui-semantic-error) !important;
  background: var(--ui-kpi-danger-bg) !important;
  font-weight: 600 !important;
}
[class*="st-key-nav_btn_centro_de_alarmas"] button[kind="tertiary"] [data-testid="stIconMaterial"] {
  color: var(--ui-semantic-error) !important;
}
[class*="st-key-nav_btn_centro_de_alarmas"] button[kind="primary"] {
  box-shadow: inset 3px 0 0 var(--ui-semantic-error) !important;
}
"""
