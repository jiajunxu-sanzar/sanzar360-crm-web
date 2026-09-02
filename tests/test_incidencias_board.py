from __future__ import annotations

from datetime import date

import pandas as pd

from services.incidencias_board import (
    BUCKET_ABIERTAS,
    BUCKET_CERRADAS,
    BUCKET_PENDIENTES,
    VER_TODOS,
    build_incidencia_payloads,
    bucket_counts,
    bucket_payloads,
    cliente_options,
    filter_payloads,
    incidencia_bucket,
    values_for_aprobar,
    values_for_cerrar,
    values_for_marcar_pendiente,
    values_for_reabrir,
)

TODAY = date(2026, 9, 2)

CONTACTS = pd.DataFrame(
    [
        {"contact_id": "c1", "nombre": "Finca Olivar"},
        {"contact_id": "c2", "nombre": "Agro Norte"},
    ]
)

ROWS = [
    {
        "historial_incidencia_id": "I1",
        "contact_id": "c1",
        "nombre_cliente": "",
        "fecha_apertura": "28/08/2026",
        "fecha_cierre": "",
        "tipo_incidencia": "sensor",
        "estado": "abierta",
        "prioridad": "alta",
        "detalle": "Sensor sin datos",
        "resolucion": "",
        "sensor_serial_number": "em500-1",
        "nombre_campana": "",
    },
    {
        "historial_incidencia_id": "I2",
        "contact_id": "c2",
        "nombre_cliente": "Agro Norte",
        "fecha_apertura": "01/09/2026",
        "fecha_cierre": "",
        "tipo_incidencia": "riego",
        "estado": "pendiente de aprobar",
        "prioridad": "media",
        "detalle": "Revisión de umbrales",
        "resolucion": "",
        "sensor_serial_number": "",
        "nombre_campana": "Campaña 26",
    },
    {
        "historial_incidencia_id": "I3",
        "contact_id": "c1",
        "nombre_cliente": "Finca Olivar",
        "fecha_apertura": "10/08/2026",
        "fecha_cierre": "15/08/2026",
        "tipo_incidencia": "conectividad",
        "estado": "cerrada",
        "prioridad": "baja",
        "detalle": "Gateway caído",
        "resolucion": "Reinicio del gateway",
        "sensor_serial_number": "",
        "nombre_campana": "",
    },
    {
        "historial_incidencia_id": "I4",
        "contact_id": "c2",
        "nombre_cliente": "Agro Norte",
        "fecha_apertura": "20/08/2026",
        "fecha_cierre": "",
        "tipo_incidencia": "sensor",
        "estado": "en curso",
        "prioridad": "media",
        "detalle": "Batería baja",
        "resolucion": "",
        "sensor_serial_number": "em500-9",
        "nombre_campana": "",
    },
]


def payloads():
    return build_incidencia_payloads(ROWS, contacts_df=CONTACTS, today=TODAY)


def test_bucket_por_estado() -> None:
    assert incidencia_bucket({"estado": "abierta"}) == BUCKET_ABIERTAS
    assert incidencia_bucket({"estado": "en curso"}) == BUCKET_ABIERTAS
    assert incidencia_bucket({"estado": "bloqueada"}) == BUCKET_ABIERTAS
    assert incidencia_bucket({"estado": ""}) == BUCKET_ABIERTAS
    assert incidencia_bucket({"estado": "pendiente de aprobar"}) == BUCKET_PENDIENTES
    assert incidencia_bucket({"estado": "Pendiente de Aprobar"}) == BUCKET_PENDIENTES
    assert incidencia_bucket({"estado": "cerrada"}) == BUCKET_CERRADAS
    assert incidencia_bucket({"estado": "resuelto"}) == BUCKET_CERRADAS


def test_fecha_cierre_manda_sobre_el_estado() -> None:
    assert incidencia_bucket({"estado": "abierta", "fecha_cierre": "01/09/2026"}) == BUCKET_CERRADAS


def test_conteo_por_cubo() -> None:
    counts = bucket_counts(payloads())
    assert counts == {BUCKET_ABIERTAS: 2, BUCKET_PENDIENTES: 1, BUCKET_CERRADAS: 1}


def test_cliente_se_completa_desde_contactos() -> None:
    p = next(p for p in payloads() if p.incidencia_id == "I1")
    assert p.cliente == "Finca Olivar"


def test_dias_abierta_y_etiqueta() -> None:
    abierta = next(p for p in payloads() if p.incidencia_id == "I1")
    assert abierta.dias_abierta == 5
    assert abierta.antiguedad_label == "5 días abierta"
    cerrada = next(p for p in payloads() if p.incidencia_id == "I3")
    assert cerrada.dias_abierta == 5
    assert cerrada.antiguedad_label == "Resuelta en 5 días"


def test_orden_abiertas_prioridad_y_antiguedad() -> None:
    abiertas = bucket_payloads(payloads(), BUCKET_ABIERTAS)
    assert [p.incidencia_id for p in abiertas] == ["I1", "I4"]


def test_filtros() -> None:
    todos = payloads()
    assert len(filter_payloads(todos, cliente=VER_TODOS)) == 4
    assert len(filter_payloads(todos, cliente="Agro Norte")) == 2
    assert len(filter_payloads(todos, tipo="sensor")) == 2
    assert len(filter_payloads(todos, prioridad="alta")) == 1
    assert len(filter_payloads(todos, query="gateway")) == 1
    assert len(filter_payloads(todos, query="GATEWAY")) == 1
    assert len(filter_payloads(todos, query="campana")) == 1


def test_opciones_de_cliente_incluyen_ver_todos() -> None:
    opts = cliente_options(payloads())
    assert opts[0] == VER_TODOS
    assert set(opts[1:]) == {"Finca Olivar", "Agro Norte"}


def test_valores_de_transicion() -> None:
    assert values_for_aprobar() == {"estado": "abierta"}
    assert values_for_marcar_pendiente() == {"estado": "pendiente de aprobar"}
    cerrar = values_for_cerrar(resolucion="Cambiada la pila", today=TODAY)
    assert cerrar == {
        "estado": "cerrada",
        "fecha_cierre": "02/09/2026",
        "resolucion": "Cambiada la pila",
    }
    assert "resolucion" not in values_for_cerrar(today=TODAY)
    assert values_for_reabrir() == {"estado": "abierta", "fecha_cierre": ""}


def test_estado_pendiente_sigue_contando_como_no_resuelta() -> None:
    from services.contact_sensor_overview import is_incidencia_abierta

    assert is_incidencia_abierta({"estado": "pendiente de aprobar", "fecha_cierre": ""}) is True
