from __future__ import annotations

import streamlit as st

from services.sheet_date_format import validate_contact_date_fields, validate_dd_mm_yyyy_fields


def text_input(label: str, value: str = "", *, key: str, disabled: bool = False) -> str:
    return st.text_input(label, value=value or "", key=key, disabled=disabled)


def text_area(label: str, value: str = "", *, key: str) -> str:
    return st.text_area(label, value=value or "", key=key, height=90)


def selectbox(label: str, options: list[str], value: str = "", *, key: str) -> str:
    options = [""] + [option for option in options if option]
    index = options.index(value) if value in options else 0
    return st.selectbox(label, options, index=index, key=key)


def show_error(message: str | None) -> bool:
    if message:
        st.error(message)
        return True
    return False


def validate_dates(values: dict[str, str], extra: list[tuple[str, str]] | None = None) -> str | None:
    contact_error = validate_contact_date_fields(values)
    if contact_error:
        return contact_error
    if extra:
        return validate_dd_mm_yyyy_fields(extra)
    return None
