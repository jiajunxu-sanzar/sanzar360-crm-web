from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium


def render_folium_map(fmap) -> dict:
    return st_folium(fmap, width=None, height=620)
