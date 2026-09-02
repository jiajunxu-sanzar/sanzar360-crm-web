from __future__ import annotations

from datetime import date

import pandas as pd

from services.daily_digest import (
    build_acciones_items,
    build_daily_digest,
    build_tareas_items,
    digest_subject,
    latest_accion_por_contacto,
    render_digest_html,
    render_digest_text,
)

TODAY = date(2026, 9, 2)

CONTACTS = pd.DataFrame(
    [
        {"contact_id": "c1", "nombre": "Finca Olivar"},
        {"contact_id": "c2", "nombre": "Agro Norte"},
        {"contact_id": "c3", "nombre": "Riegos Sur"},
    ]
)

ACCIONES = [
    # c1: fila antigua con próxima acción vencida, pero hay otra más reciente
    {
        "contact_id": "c1",
        "nombre_cliente": "Finca Olivar",
        "fecha_contacto": "10/08/2026",
        "hora_contacto": "09:00",
        "persona_contacto": "Carla Moreno",
        "proxima_accion_persona": "Carla Moreno",
        "proxima_accion_fecha": "15/08/2026",
        "proxima_accion_detalle": "Llamada de seguimiento antigua",
        "proxima_accion_canal": "llamada",
    },
    {
        "contact_id": "c1",
        "nombre_cliente": "Finca Olivar",
        "fecha_contacto": "01/09/2026",
        "hora_contacto": "17:30",
        "persona_contacto": "Carla Moreno",
        "proxima_accion_persona": "Carla Moreno",
        "proxima_accion_fecha": "02/09/2026",
        "proxima_accion_detalle": "Enviar propuesta de piloto",
        "proxima_accion_canal": "email",
    },
    # c2: próxima acción atrasada y sin contacto posterior
    {
        "contact_id": "c2",
        "nombre_cliente": "Agro Norte",
        "fecha_contacto": "20/08/2026",
        "hora_contacto": "11:00",
        "persona_contacto": "David Ortiz",
        "proxima_accion_persona": "David Ortiz",
        "proxima_accion_fecha": "26/08/2026",
        "proxima_accion_detalle": "Confirmar fecha de instalación",
        "proxima_accion_canal": "llamada",
    },
    # c3: próxima acción futura, no debe aparecer
    {
        "contact_id": "c3",
        "nombre_cliente": "Riegos Sur",
        "fecha_contacto": "01/09/2026",
        "hora_contacto": "12:00",
        "persona_contacto": "Jiajun Xu",
        "proxima_accion_persona": "Jiajun Xu",
        "proxima_accion_fecha": "20/09/2026",
        "proxima_accion_detalle": "Revisar campaña",
        "proxima_accion_canal": "email",
    },
]

TAREAS = [
    {
        "historial_tarea_id": "T1",
        "contact_id": "c1",
        "nombre_cliente": "Finca Olivar",
        "titulo": "Preparar oferta",
        "notas": "Con precios 2026",
        "tipo_tarea": "Comercial",
        "estado_tarea": "En proceso",
        "persona_gestiona": "Carla Moreno",
        "fecha_limite": "02/09/2026",
    },
    {
        "historial_tarea_id": "T2",
        "contact_id": "c2",
        "nombre_cliente": "Agro Norte",
        "titulo": "Revisar sensores",
        "notas": "Batería baja",
        "tipo_tarea": "Revisar sensores",
        "estado_tarea": "Sin iniciar",
        "persona_gestiona": "David Ortiz",
        "fecha_limite": "25/08/2026",
    },
    {
        "historial_tarea_id": "T3",
        "contact_id": "c3",
        "nombre_cliente": "Riegos Sur",
        "titulo": "Cerrada ya",
        "notas": "Hecha",
        "tipo_tarea": "Interno",
        "estado_tarea": "Terminado",
        "persona_gestiona": "Jiajun Xu",
        "fecha_limite": "20/08/2026",
    },
    {
        "historial_tarea_id": "T4",
        "contact_id": "c3",
        "nombre_cliente": "Riegos Sur",
        "titulo": "Futura",
        "notas": "Más adelante",
        "tipo_tarea": "Interno",
        "estado_tarea": "Sin iniciar",
        "persona_gestiona": "Jiajun Xu",
        "fecha_limite": "30/09/2026",
    },
]


def test_latest_accion_por_contacto_toma_la_mas_reciente() -> None:
    latest = latest_accion_por_contacto(ACCIONES)
    assert latest["c1"]["proxima_accion_detalle"] == "Enviar propuesta de piloto"


def test_acciones_hoy_y_atrasadas() -> None:
    hoy, atrasadas = build_acciones_items(ACCIONES, contacts_df=CONTACTS, today=TODAY)
    assert [i.detalle for i in hoy] == ["Enviar propuesta de piloto"]
    assert hoy[0].encargado == "Carla Moreno"
    assert hoy[0].cliente == "Finca Olivar"
    assert [i.detalle for i in atrasadas] == ["Confirmar fecha de instalación"]
    assert atrasadas[0].dias_retraso == 7
    assert "Vencida hace 7 días" in atrasadas[0].contexto


def test_accion_antigua_superada_por_un_contacto_nuevo_no_aparece() -> None:
    _, atrasadas = build_acciones_items(ACCIONES, contacts_df=CONTACTS, today=TODAY)
    assert all("antigua" not in i.detalle for i in atrasadas)


def test_tareas_hoy_y_atrasadas() -> None:
    hoy, atrasadas = build_tareas_items(TAREAS, contacts_df=CONTACTS, today=TODAY)
    assert [i.cliente for i in hoy] == ["Finca Olivar"]
    assert hoy[0].detalle == "Preparar oferta — Con precios 2026"
    assert hoy[0].encargado == "Carla Moreno"
    assert [i.cliente for i in atrasadas] == ["Agro Norte"]
    assert atrasadas[0].dias_retraso == 8


def test_tareas_terminadas_y_futuras_quedan_fuera() -> None:
    hoy, atrasadas = build_tareas_items(TAREAS, contacts_df=CONTACTS, today=TODAY)
    titulos = [i.detalle for i in hoy + atrasadas]
    assert not any("Cerrada ya" in t for t in titulos)
    assert not any("Futura" in t for t in titulos)


def test_digest_completo_y_totales() -> None:
    digest = build_daily_digest(
        acciones_rows=ACCIONES, tareas_rows=TAREAS, contacts_df=CONTACTS, today=TODAY
    )
    assert digest.total_hoy == 2
    assert digest.total_atrasado == 2
    assert digest.total == 4
    assert digest.vacio is False


def test_digest_vacio() -> None:
    digest = build_daily_digest(acciones_rows=[], tareas_rows=[], today=TODAY)
    assert digest.vacio is True
    assert "sin acciones ni tareas" in digest_subject(digest)


def test_asunto_resume_los_totales() -> None:
    digest = build_daily_digest(
        acciones_rows=ACCIONES, tareas_rows=TAREAS, contacts_df=CONTACTS, today=TODAY
    )
    assert digest_subject(digest) == "CRM 02/09/2026 · 2 para hoy · 2 atrasados"


def test_html_contiene_los_cuatro_bloques_y_escapa() -> None:
    acciones = ACCIONES + [
        {
            "contact_id": "c9",
            "nombre_cliente": "<script>alerta</script>",
            "fecha_contacto": "01/09/2026",
            "hora_contacto": "10:00",
            "proxima_accion_persona": "Marco Ruano",
            "proxima_accion_fecha": "02/09/2026",
            "proxima_accion_detalle": "Revisar",
            "proxima_accion_canal": "email",
        }
    ]
    digest = build_daily_digest(
        acciones_rows=acciones, tareas_rows=TAREAS, contacts_df=CONTACTS, today=TODAY
    )
    html = render_digest_html(digest)
    assert "Próxima acción · hoy" in html
    assert "Tareas · hoy" in html
    assert "Seguimiento comercial atrasado" in html
    assert "Tareas atrasadas" in html
    assert "Enviar propuesta de piloto" in html
    assert "Carla Moreno" in html
    assert "<script>alerta</script>" not in html
    assert "&lt;script&gt;" in html


def test_texto_plano_incluye_encargado_y_cliente() -> None:
    digest = build_daily_digest(
        acciones_rows=ACCIONES, tareas_rows=TAREAS, contacts_df=CONTACTS, today=TODAY
    )
    texto = render_digest_text(digest)
    assert "Finca Olivar" in texto
    assert "Encargado: Carla Moreno" in texto
    assert "PENDIENTE DE DÍAS ANTERIORES" in texto


def test_sin_atrasados_no_se_pinta_la_seccion() -> None:
    digest = build_daily_digest(
        acciones_rows=[ACCIONES[1]], tareas_rows=[TAREAS[0]], contacts_df=CONTACTS, today=TODAY
    )
    html = render_digest_html(digest)
    assert "Pendiente de días anteriores" not in html
