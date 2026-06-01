from ui.components.history_cards import (
    build_campana_card_html,
    build_history_card_html,
    build_incidencia_card_html,
    build_sensor_card_html,
    build_suscripcion_card_html,
)
from ui.palette import (
    STATUS_DANGER,
    STATUS_NEUTRAL,
    STATUS_SUCCESS,
    STATUS_WARNING,
    history_incident_modifier,
    history_incident_style,
    history_open_closed_modifier,
    history_open_closed_style,
    history_subscription_modifier,
    history_subscription_style,
)


def test_history_open_closed_palette() -> None:
    assert history_open_closed_modifier("estado_cierre_sensor", "abierto") == "exitoso"
    assert history_open_closed_modifier("estado_cierre_sensor", "cerrado") == "fallido"
    assert history_open_closed_modifier("estado_cierre_campana", "") == "neutral"
    assert history_open_closed_style("abierto") == STATUS_SUCCESS
    assert history_open_closed_style("cerrado") == STATUS_DANGER


def test_history_subscription_palette() -> None:
    assert history_subscription_modifier("activa") == "exitoso"
    assert history_subscription_modifier("caduca pronto") == "warning"
    assert history_subscription_modifier("inactiva") == "fallido"
    assert history_subscription_style("caduca pronto") == STATUS_WARNING
    assert history_subscription_style("inactiva") == STATUS_DANGER


def test_history_incident_palette() -> None:
    assert history_incident_modifier("abierta") == "exitoso"
    assert history_incident_modifier("en curso") == "exitoso"
    assert history_incident_modifier("bloqueada") == "exitoso"
    assert history_incident_modifier("cerrada") == "fallido"
    assert history_incident_modifier("resuelta") == "fallido"
    assert history_incident_modifier("") == "neutral"
    assert history_incident_style("abierta") == STATUS_SUCCESS
    assert history_incident_style("cerrada") == STATUS_DANGER
    assert history_incident_style("") == STATUS_NEUTRAL


def test_sensor_card_html_open_closed_modifiers() -> None:
    open_html = build_sensor_card_html({"estado_cierre_sensor": "abierto"})
    closed_html = build_sensor_card_html({"estado_cierre_sensor": "cerrado"})
    assert "sanzar-hist-card--exitoso" in open_html
    assert "sanzar-hist-card--fallido" in closed_html


def test_campana_card_html() -> None:
    html = build_campana_card_html(
        {
            "nombre_campana": "Tomate 2025",
            "estado_cierre_campana": "abierto",
            "fecha_campana_inicio": "01/01/2025",
            "fecha_campana_fin": "30/06/2025",
        }
    )
    assert "Tomate 2025" in html
    assert "sanzar-hist-card--exitoso" in html


def test_suscripcion_card_html_warning() -> None:
    html = build_suscripcion_card_html({"estado_suscripcion": "caduca pronto"})
    assert "sanzar-hist-card--warning" in html


def test_incidencia_card_html() -> None:
    open_html = build_incidencia_card_html({"estado": "abierta", "detalle": "Fallo sensor"})
    closed_html = build_incidencia_card_html(
        {"estado": "cerrada", "detalle": "Ok", "resolucion": "Reemplazado"}
    )
    assert "sanzar-hist-card--exitoso" in open_html
    assert "sanzar-hist-card--fallido" in closed_html
    assert "Resolución" in closed_html


def test_history_card_dispatch() -> None:
    row = {"estado_cierre_sensor": "abierto"}
    assert build_history_card_html("sensores", row) == build_sensor_card_html(row)
