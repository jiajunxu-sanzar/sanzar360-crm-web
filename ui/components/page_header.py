"""Cabecera de página consistente (título + descripción) para todas las pestañas.

Sustituye a ``st.title(page_menu_title(...))`` con un patrón único estilo
Linear/Attio: título limpio sin emoji, subtítulo muted y separación regular.
El icono/emoji sigue viviendo solo en la navegación lateral.
"""

from __future__ import annotations

import html

import streamlit as st

from app.navigation import PAGE_DESCRIPTIONS


def render_page_header(page: str, *, description: str | None = None) -> None:
    """Pinta la cabecera estándar de una página del CRM.

    Args:
        page: clave canónica de ``app.navigation.PAGES`` (p. ej. ``"Contactos"``).
        description: subtítulo alternativo; por defecto ``PAGE_DESCRIPTIONS[page]``.
    """
    desc = description if description is not None else PAGE_DESCRIPTIONS.get(page, "")
    desc_html = (
        f"<p class='sanzar-page-desc'>{html.escape(desc)}</p>" if desc else ""
    )
    st.markdown(
        "<div class='sanzar-page-header'>"
        f"<h1 class='sanzar-page-title'>{html.escape(page)}</h1>"
        f"{desc_html}"
        "</div>",
        unsafe_allow_html=True,
    )
