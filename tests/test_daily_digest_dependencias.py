"""El cron del resumen diario corre con muy pocas dependencias instaladas.

``scripts/send_daily_digest.py`` se ejecuta en GitHub Actions con solo
pandas, gspread, google-auth y python-dotenv. Si alguien añade en la cadena
de imports un módulo pesado de la app (Streamlit, geopy, folium, plotly,
matplotlib, reportlab…) a nivel de módulo, el cron reventaría a las 6:00 y
nadie se enteraría hasta que faltara el correo.

Estos tests simulan que esos paquetes NO están instalados, aunque en local
sí lo estén, y comprueban que el script sigue importándose.
"""
from __future__ import annotations

import builtins
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Paquetes que la app usa pero que el cron no instala.
PAQUETES_FUERA_DEL_CRON = (
    "streamlit",
    "geopy",
    "folium",
    "streamlit_folium",
    "plotly",
    "matplotlib",
    "reportlab",
    "openpyxl",
    "PIL",
    "jinja2",
    "yaml",
)

_SUBPROCESO = textwrap.dedent(
    """
    import builtins, sys
    bloqueados = {bloqueados!r}
    real = builtins.__import__

    def fake(name, *args, **kwargs):
        raiz = name.split(".")[0]
        if raiz in bloqueados:
            raise ModuleNotFoundError(f"No module named {{raiz!r}}")
        return real(name, *args, **kwargs)

    builtins.__import__ = fake
    for nombre in list(sys.modules):
        if nombre.split(".")[0] in bloqueados:
            del sys.modules[nombre]

    import {modulo}
    print("OK")
    """
)


def _importa_sin(modulo: str, bloqueados: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _SUBPROCESO.format(modulo=modulo, bloqueados=bloqueados)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )


@pytest.mark.parametrize(
    "modulo",
    [
        "scripts.send_daily_digest",
        "services.daily_digest",
        "services.history_service",
        "services.sheets_service",
        "services.email_service",
        "app.smtp_profiles",
    ],
)
def test_el_cron_importa_sin_las_dependencias_pesadas(modulo: str) -> None:
    resultado = _importa_sin(modulo, PAQUETES_FUERA_DEL_CRON)
    assert resultado.returncode == 0, (
        f"«{modulo}» no se puede importar sin las dependencias pesadas de la app. "
        f"El cron de las 6:00 fallaría.\n{resultado.stderr[-2000:]}"
    )
    assert "OK" in resultado.stdout


def test_el_truco_de_bloqueo_funciona_de_verdad() -> None:
    # Guarda de cordura: si el bloqueo no bloqueara nada, los tests de arriba
    # pasarían siempre y no protegerían de nada.
    resultado = _importa_sin("app.telemetry_no_existe", PAQUETES_FUERA_DEL_CRON)
    assert resultado.returncode != 0

    codigo = _SUBPROCESO.format(modulo="geopy.geocoders", bloqueados=("geopy",))
    directo = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert directo.returncode != 0
    assert "No module named" in directo.stderr


def test_telemetria_funciona_sin_streamlit() -> None:
    # ``timed`` lo usa sheets_service en cada lectura: no debe romper sin Streamlit.
    codigo = textwrap.dedent(
        """
        import builtins
        real = builtins.__import__
        def fake(name, *a, **k):
            if name.split(".")[0] == "streamlit":
                raise ModuleNotFoundError("No module named 'streamlit'")
            return real(name, *a, **k)
        builtins.__import__ = fake
        import sys
        for n in list(sys.modules):
            if n.split(".")[0] == "streamlit":
                del sys.modules[n]
        from app.telemetry import timed
        with timed("prueba", origen="test"):
            pass
        print("OK")
        """
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    assert resultado.returncode == 0, resultado.stderr[-1500:]
    assert "OK" in resultado.stdout
