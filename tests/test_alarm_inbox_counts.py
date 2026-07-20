from __future__ import annotations

from datetime import date

import pandas as pd

from services.alarm_inbox_counts import pending_tareas_inbox_count


def test_pending_tareas_inbox_count_empty() -> None:
    assert pending_tareas_inbox_count([], [], today=date(2026, 7, 20)) == 1


def test_pending_tareas_inbox_count_includes_due_tarea_and_blog() -> None:
    today = date(2026, 7, 20)
    tareas = [
        {
            "contact_id": "c1",
            "titulo": "Llamar",
            "estado_tarea": "Sin iniciar",
            "fecha_limite": "19/07/2026",
            "tipo_tarea": "Seguimiento",
            "notas": "x",
            "persona_gestiona": "Ana",
            "nombre_cliente": "Cliente",
        }
    ]
    blogs = [
        {
            "tipo_registro": "blog",
            "titulo": "Post",
            "estado_blog": "Borrador",
            "fecha_publicacion_prevista": "20/07/2026",
            "historial_blog_id": "b1",
        }
    ]
    # 1 tarea + 1 blog due + 0 gap (blog scheduled this week)
    assert pending_tareas_inbox_count(tareas, blogs, today=today) == 2


def test_pending_tareas_inbox_count_includes_visto_hoy() -> None:
    today = date(2026, 7, 16)
    contacts = pd.DataFrame(
        [
            {
                "contact_id": "c1",
                "nombre": "A",
                "tipo_relacion": "Cliente",
                "visto_cliente_fecha": "",
            }
        ]
    )
    # weekly blog gap (1) + visto hoy pending (1)
    assert pending_tareas_inbox_count([], [], contacts_df=contacts, today=today) == 2
