"""Detección automática de cambios remotos en el spreadsheet.

Cada sesión Streamlit consulta cada ``POLL_INTERVAL_S`` segundos el
``modifiedTime`` del fichero de Google Drive que respalda el CRM. Si el
timestamp ha cambiado respecto al último visto, se vacían las cachés de datos
(`st.cache_data`) y se incrementan las versiones gestionadas en
:mod:`app.state`, de forma que la siguiente lectura por página recupere los
datos frescos.

Diseño:
- *Throttled*: ``POLL_INTERVAL_S`` evita pegar a Drive en cada rerun de
  Streamlit (típicamente varios por interacción).
- *Resiliente*: cualquier excepción al consultar Drive se traga y se devuelve
  ``False``; la app sigue funcionando con la caché actual.
- *Una sola llamada por usuario activo*: Drive API es independiente de la cuota
  de Sheets, y 1 req cada 30 s por sesión es despreciable.
- *Sin acoplamiento con la UI*: la función no llama a ``st.toast`` ni a
  ``st.rerun``; el llamador decide cómo reflejar la invalidación.
"""

from __future__ import annotations

import time
from typing import Final

import streamlit as st

from app.cache import sheets_service
from app.state import bump_all_data_caches

POLL_INTERVAL_S: Final[float] = 30.0

_LAST_CHECK_KEY: Final[str] = "_remote_sync_last_check_ts"
_LAST_MTIME_KEY: Final[str] = "_remote_sync_last_mtime"


def _now() -> float:
    """Indirección para tests (parchear fácilmente la fuente de tiempo)."""
    return time.time()


def _read_modified_time() -> str:
    """Wrapper testeable alrededor de ``SheetsService.get_modified_time``."""
    return sheets_service().get_modified_time()


def check_remote_changes(*, force: bool = False) -> bool:
    """Sondea Drive y devuelve ``True`` si invalidó cachés en esta llamada.

    Args:
        force: omite el throttle (útil tras una escritura propia que ya bumpeó
            las cachés y queremos resincronizar el baseline de ``modifiedTime``
            para evitar un segundo bump espurio).

    Returns:
        ``True`` sólo cuando el ``modifiedTime`` cambió respecto al último
        visto en esta sesión *y* se invalidaron las cachés. El primer sondeo
        de la sesión nunca invalida (solo registra el baseline).
    """
    now = _now()
    last_check = float(st.session_state.get(_LAST_CHECK_KEY, 0.0))
    if not force and (now - last_check) < POLL_INTERVAL_S:
        return False

    try:
        mtime = _read_modified_time()
    except Exception:
        return False

    st.session_state[_LAST_CHECK_KEY] = now

    if not mtime:
        return False

    previous = st.session_state.get(_LAST_MTIME_KEY)
    if previous is None:
        st.session_state[_LAST_MTIME_KEY] = mtime
        return False

    if mtime == previous:
        return False

    st.session_state[_LAST_MTIME_KEY] = mtime
    st.cache_data.clear()
    bump_all_data_caches()
    return True


def reset_remote_sync_state() -> None:
    """Olvida el baseline de ``modifiedTime`` y la marca de tiempo del poll.

    Se invoca tras un reinicio duro de sesión para que el siguiente poll
    registre un nuevo baseline en vez de invalidar a ciegas.
    """
    st.session_state.pop(_LAST_CHECK_KEY, None)
    st.session_state.pop(_LAST_MTIME_KEY, None)
