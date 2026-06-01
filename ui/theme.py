from __future__ import annotations

import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        :root {
          /* Typography */
          --ui-font: 'Inter', ui-sans-serif, system-ui, sans-serif;
          /* Core — minimalist neutral + single accent */
          --ui-bg-page: #fafafa;
          --ui-bg-elevated: #ffffff;
          --ui-sidebar: #f4f4f5;
          --ui-border: #e5e5e5;
          --ui-border-strong: #d4d4d8;
          --ui-text: #18181b;
          --ui-text-muted: #737373;
          /* Brand accent — single green */
          --ui-accent: #15803d;
          --ui-accent-hover: #166534;
          --ui-accent-contrast: #ffffff;
          /* Legacy aliases (contacts / alarms) */
          --sanzar-green: #15803d;
          --sanzar-green-soft: #ecfdf5;
          --sanzar-border: var(--ui-border);
          --sanzar-text: var(--ui-text);
          /* Semantic button tokens */
          --ui-btn-save-bg: #15803d;
          --ui-btn-save-hover: #166534;
          --ui-btn-save-fg: #ffffff;
          --ui-btn-destruct-bg: #fef2f2;
          --ui-btn-destruct-border: #fecaca;
          --ui-btn-destruct-hover: #ffe4e6;
          --ui-btn-destruct-fg: #991b1b;
          --ui-btn-neutral-bg: #fafafa;
          --ui-btn-neutral-border: #e5e5e5;
          --ui-btn-neutral-hover: #f4f4f5;
          --ui-btn-neutral-fg: #404040;
          /* Kept for any legacy reference */
          --ui-btn-affirm-bg: #fafafa;
          --ui-btn-affirm-border: #e5e5e5;
          --ui-btn-affirm-hover: #f4f4f5;
          --ui-btn-affirm-fg: #18181b;
        }
        body, .stApp { font-family: var(--ui-font) !important; }
        /* Page */
        .block-container {
          padding-top: 1.5rem;
          padding-bottom: 2rem;
          max-width: 1200px;
        }
        .main .block-container { background: var(--ui-bg-page); }
        div[data-testid="stSidebar"] {
          background: var(--ui-sidebar);
          border-right: 1px solid var(--ui-border);
        }
        /* Typography rhythm */
        h1 { font-weight: 600 !important; letter-spacing: -0.02em; color: var(--ui-text) !important; }
        h2, h3 { font-weight: 600 !important; color: var(--ui-text) !important; }

        /* Streamlit buttons — cohesive primary / secondary */
        .stButton > button[kind="primary"],
        div[data-testid="stSidebar"] button[kind="primary"] {
          background-color: var(--ui-accent) !important;
          color: var(--ui-accent-contrast) !important;
          border: 1px solid var(--ui-accent) !important;
          border-radius: 8px !important;
          font-weight: 550 !important;
        }
        .stButton > button[kind="primary"]:hover {
          background-color: var(--ui-accent-hover) !important;
          border-color: var(--ui-accent-hover) !important;
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
          background: #fafafa;
          margin-bottom: 8px;
        }
        .sanzar-kpi--success,
        .sanzar-acciones-kpi--success {
          background: #f0fdf4;
          border-color: #bbf7d0;
        }
        .sanzar-kpi--danger,
        .sanzar-acciones-kpi--danger {
          background: #fef2f2;
          border-color: #fecaca;
        }
        .sanzar-kpi--info {
          background: #f0f9ff;
          border-color: #bae6fd;
        }
        .sanzar-kpi--warning {
          background: #fffbeb;
          border-color: #fde68a;
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
        .sanzar-acciones-stat-ok { color: #15803d; font-weight: 600; }
        .sanzar-acciones-stat-ko { color: #b91c1c; font-weight: 600; }
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
        .sanzar-timeline-item[data-kind^="sensor-"] .sanzar-timeline-dot { background: #15803d; }
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
          border-left: 4px solid #15803d;
          background: #f0fdf4;
        }
        .sanzar-seg-card--fallido,
        .sanzar-hist-card--fallido {
          border-left: 4px solid #b91c1c;
          background: #fef2f2;
        }
        .sanzar-seg-card--neutral,
        .sanzar-hist-card--neutral {
          border-left: 4px solid var(--ui-border-strong);
        }
        .sanzar-hist-card--warning {
          border-left: 4px solid #b45309;
          background: #fffbeb;
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
        .st-key-dash_bucket_tomorrow button {
          background: #ffffff !important;
          border: 1px solid #e5e5e5 !important;
          border-left: 3px solid transparent !important;
          color: #525252 !important;
          border-radius: 8px !important;
          font-weight: 500 !important;
        }
        /* Selected variants — Python sets type="primary" when active */
        .st-key-dash_bucket_past button[kind="primary"]     { border-left: 3px solid #e11d48 !important; background: #f4f4f5 !important; border-color: #d4d4d8 !important; color: #18181b !important; }
        .st-key-dash_bucket_today button[kind="primary"]    { border-left: 3px solid #ca8a04 !important; background: #f4f4f5 !important; border-color: #d4d4d8 !important; color: #18181b !important; }
        .st-key-dash_bucket_tomorrow button[kind="primary"] { border-left: 3px solid #16a34a !important; background: #f4f4f5 !important; border-color: #d4d4d8 !important; color: #18181b !important; }
        /* Hover must also stay grey — otherwise the global primary:hover turns them green */
        .st-key-dash_bucket_past button[kind="primary"]:hover     { background: #ececec !important; border-left-color: #e11d48 !important; border-color: #c4c4c8 !important; }
        .st-key-dash_bucket_today button[kind="primary"]:hover    { background: #ececec !important; border-left-color: #ca8a04 !important; border-color: #c4c4c8 !important; }
        .st-key-dash_bucket_tomorrow button[kind="primary"]:hover { background: #ececec !important; border-left-color: #16a34a !important; border-color: #c4c4c8 !important; }

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
