from __future__ import annotations

import pandas as pd
import streamlit as st

from app.cache import load_users_cached
from app.navigation import page_menu_title


def render(_: pd.DataFrame) -> None:
    st.title(page_menu_title("Usuarios"))
    st.caption("Roles y acceso por pestañas.")
    users = load_users_cached(st.session_state.get("users_cache_version", 0))
    df = pd.DataFrame(
        [
            {
                "employee_id": user.employee_id,
                "nombre": user.nombre,
                "role": user.role,
                "password": user.password,
            }
            for user in users
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True, height=420)
    st.info("Los usuarios se cargan desde la hoja `Usuarios CRM`.")
