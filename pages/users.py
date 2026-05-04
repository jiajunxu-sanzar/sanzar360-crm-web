from __future__ import annotations

import pandas as pd
import streamlit as st

from app.cache import load_users_cached


def render(_: pd.DataFrame) -> None:
    st.title("Usuarios")
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
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.info("Los usuarios se cargan desde la hoja `Usuarios CRM`.")
