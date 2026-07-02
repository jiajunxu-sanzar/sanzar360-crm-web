from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.contact_sensor_overview import (
    OVERVIEW_COLUMNS,
    build_contact_sensor_overview,
    format_sensor_pack_associations,
)


def _contact(contact_id: str = "c1", nombre: str = "Cliente Test") -> pd.DataFrame:
    return pd.DataFrame([{"contact_id": contact_id, "nombre": nombre}])


def _sensor_row(
    contact_id: str = "c1",
    sensor_serial_number: str = "uc501-UC001-T10-SIM001",
    estado_cierre_sensor: str = "",
) -> dict[str, str]:
    return {
        "contact_id": contact_id,
        "sensor_serial_number": sensor_serial_number,
        "estado_cierre_sensor": estado_cierre_sensor,
    }


def _incidencia_row(
    contact_id: str = "c1",
    estado: str = "abierta",
    fecha_cierre: str = "",
    detalle: str = "Sin conexión",
    resolucion: str = "",
    tipo_incidencia: str = "conectividad",
    prioridad: str = "alta",
) -> dict[str, str]:
    return {
        "contact_id": contact_id,
        "estado": estado,
        "fecha_cierre": fecha_cierre,
        "detalle": detalle,
        "resolucion": resolucion,
        "tipo_incidencia": tipo_incidencia,
        "prioridad": prioridad,
    }


def test_empty_contacts() -> None:
    out = build_contact_sensor_overview(
        pd.DataFrame(),
        [],
        [],
        pd.DataFrame(),
    )
    assert list(out.columns) == OVERVIEW_COLUMNS
    assert out.empty


def test_sin_historicos() -> None:
    out = build_contact_sensor_overview(_contact(), [], [], pd.DataFrame())
    row = out.iloc[0]
    assert row["semaforo"] == "sin_sensores"
    assert row["num_sensores"] == 0
    assert row["sensor_sns"] == ""
    assert row["ultimo_contacto"] == ""
    assert row["incidencias_abiertas"] == 0


def test_verde_sensor_abierto() -> None:
    out = build_contact_sensor_overview(
        _contact(),
        [_sensor_row()],
        [],
        pd.DataFrame(),
    )
    row = out.iloc[0]
    assert row["semaforo"] == "verde"
    assert row["num_sensores"] == 3
    assert "uc501-UC001" in str(row["sensor_sns"])
    assert "→" in str(row["sensor_sns"])
    assert row["incidencias_abiertas"] == 0


def test_amarillo_con_incidencia() -> None:
    out = build_contact_sensor_overview(
        _contact(),
        [_sensor_row()],
        [_incidencia_row()],
        pd.DataFrame(),
    )
    row = out.iloc[0]
    assert row["semaforo"] == "amarillo"
    assert row["incidencias_abiertas"] == 1


def test_incidencia_cerrada_no_cuenta() -> None:
    out = build_contact_sensor_overview(
        _contact(),
        [_sensor_row()],
        [
            _incidencia_row(estado="cerrada"),
            _incidencia_row(estado="abierta", fecha_cierre="01/06/2025"),
        ],
        pd.DataFrame(),
    )
    row = out.iloc[0]
    assert row["incidencias_abiertas"] == 0
    assert row["semaforo"] == "verde"


def test_sensor_cerrado_no_suma() -> None:
    out = build_contact_sensor_overview(
        _contact(),
        [_sensor_row(estado_cierre_sensor="cerrado")],
        [],
        pd.DataFrame(),
    )
    row = out.iloc[0]
    assert row["num_sensores"] == 0
    assert row["semaforo"] == "sin_sensores"


def test_ultimo_contacto_mas_reciente() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": yesterday.strftime("%d/%m/%Y"),
                "hora_contacto": "15:00",
                "canal_contacto": "email",
            },
            {
                "contact_id": "c1",
                "fecha_contacto": today.strftime("%d/%m/%Y"),
                "hora_contacto": "09:00",
                "canal_contacto": "llamada",
            },
        ]
    )
    out = build_contact_sensor_overview(_contact(), [], [], acciones)
    row = out.iloc[0]
    assert row["ultimo_contacto"] == today.strftime("%d/%m/%Y")
    assert row["ultimo_contacto_canal"] == "llamada"


def test_format_sensor_pack_associations_uc501_bundle() -> None:
    text = format_sensor_pack_associations("uc501-UC001-TE001-SIM001")
    assert "uc501-UC001" in text
    assert "→" in text
    assert "teros10-TE001" in text
    assert "sim-SIM001" in text


def test_ultimo_contacto_incluye_detalle() -> None:
    acciones = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "fecha_contacto": "01/06/2025",
                "hora_contacto": "10:30",
                "canal_contacto": "llamada",
                "persona_contacto": "Ana",
                "resultado_contacto": "exitoso",
                "notas_contacto": "Quiere demo la semana que viene",
            }
        ]
    )
    out = build_contact_sensor_overview(_contact(), [], [], acciones)
    row = out.iloc[0]
    assert "Quiere demo" in str(row["ultimo_contacto_detalle"])
    assert "Ana" in str(row["ultimo_contacto_detalle"])
    assert "exitoso" in str(row["ultimo_contacto_detalle"])


def test_incidencias_incluyen_detalle_y_resolucion() -> None:
    out = build_contact_sensor_overview(
        _contact(),
        [_sensor_row()],
        [_incidencia_row(detalle="Corte de red", resolucion="Pendiente revisión remota")],
        pd.DataFrame(),
    )
    row = out.iloc[0]
    assert "Corte de red" in str(row["incidencias_detalle"])
    assert "Resolución: Pendiente revisión remota" in str(row["incidencias_detalle"])
    assert "conectividad" in str(row["incidencias_detalle"])
