"""Polyfills y fixtures compartidos para la suite de tests.

En algunas versiones de Streamlit instaladas en CI/local no existe
``st.dialog`` (es API moderna). Como varias páginas del CRM lo usan a nivel
de módulo (``@st.dialog(...)``), importarlas en cualquier test fallaba con
``AttributeError``. Añadimos un decorador no-op antes de cualquier import
para mantener compatibilidad sin tocar el código de producción.
"""
from __future__ import annotations

import streamlit as st


if not hasattr(st, "dialog"):
    def _dialog_polyfill(*_args: object, **_kwargs: object):
        def _decorator(fn):
            return fn

        return _decorator

    st.dialog = _dialog_polyfill  # type: ignore[attr-defined]
