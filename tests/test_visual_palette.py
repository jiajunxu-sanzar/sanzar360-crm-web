from ui.palette import (
    STATUS_DANGER,
    STATUS_SUCCESS,
    STATUS_WARNING,
    alarm_category_style,
    contact_status_style,
    incident_status_style,
    subscription_status_style,
)


def test_contact_and_subscription_styles() -> None:
    assert contact_status_style("Cliente") == STATUS_SUCCESS
    assert subscription_status_style("caduca pronto") == STATUS_WARNING
    assert subscription_status_style("inactiva") == STATUS_DANGER


def test_incident_and_alarm_styles() -> None:
    assert incident_status_style("abierta") == STATUS_DANGER
    assert incident_status_style("cerrada") == STATUS_SUCCESS
    style, width = alarm_category_style(True, True)
    assert style == STATUS_DANGER
    assert width == 3
