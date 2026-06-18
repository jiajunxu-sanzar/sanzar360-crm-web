from ui.palette import (
    STATUS_DANGER,
    STATUS_INFO,
    STATUS_NEUTRAL,
    STATUS_PURPLE,
    STATUS_SUCCESS,
    STATUS_WARNING,
    alarm_category_style,
    commercial_result_style,
    commercial_seg_card_modifier,
    contact_status_style,
    incident_status_style,
    subscription_status_style,
)


def test_contact_and_subscription_styles() -> None:
    assert contact_status_style("Cliente") == STATUS_SUCCESS
    assert contact_status_style("Nuevo contacto") == STATUS_WARNING
    assert contact_status_style("Contacto inicial") == STATUS_INFO
    assert contact_status_style("Piloto activo") == STATUS_PURPLE
    assert contact_status_style("Perdido") == STATUS_DANGER
    assert subscription_status_style("caduca pronto") == STATUS_WARNING
    assert subscription_status_style("inactiva") == STATUS_DANGER


def test_incident_and_alarm_styles() -> None:
    assert incident_status_style("abierta") == STATUS_DANGER
    assert incident_status_style("cerrada") == STATUS_SUCCESS
    style, width = alarm_category_style(True, True)
    assert style == STATUS_DANGER
    assert width == 3


def test_commercial_result_and_card_modifier() -> None:
    assert commercial_result_style("exitoso") == STATUS_SUCCESS
    assert commercial_result_style("fallido") == STATUS_DANGER
    assert commercial_result_style("") == STATUS_NEUTRAL
    assert commercial_seg_card_modifier("exitoso") == "exitoso"
    assert commercial_seg_card_modifier("Fallido") == "fallido"
    assert commercial_seg_card_modifier("") == "neutral"
