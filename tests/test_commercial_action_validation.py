from services.commercial_action_validation import validate_commercial_action_values


def _base() -> dict[str, str]:
    return {
        "resultado_contacto": "exitoso",
        "fecha_contacto": "01/06/2026",
        "hora_contacto": "",
        "canal_contacto": "llamada",
        "email_url": "",
        "email_clasificacion": "",
        "proxima_accion_fecha": "",
        "proxima_accion_persona": "",
        "proxima_accion_canal": "",
        "proxima_accion_detalle": "",
    }


def test_email_requires_clasificacion() -> None:
    v = _base()
    v["canal_contacto"] = "email"
    assert validate_commercial_action_values(v) is not None
    v["email_clasificacion"] = "seguimiento"
    assert validate_commercial_action_values(v) is None


def test_non_email_cannot_have_email_fields() -> None:
    v = _base()
    v["email_url"] = "https://example.com"
    assert validate_commercial_action_values(v) is not None


def test_proxima_partial_requires_core_fields() -> None:
    v = _base()
    v["proxima_accion_detalle"] = "Seguir"
    assert validate_commercial_action_values(v) is not None
    v["proxima_accion_fecha"] = "10/06/2026"
    v["proxima_accion_persona"] = "David Ortiz"
    v["proxima_accion_canal"] = "email"
    assert validate_commercial_action_values(v) is None


def test_whatsapp_is_valid_for_contact_and_next_action() -> None:
    v = _base()
    v["canal_contacto"] = "whatsapp"
    assert validate_commercial_action_values(v) is None

    v["proxima_accion_fecha"] = "10/06/2026"
    v["proxima_accion_persona"] = "David Ortiz"
    v["proxima_accion_canal"] = "whatsapp"
    v["proxima_accion_detalle"] = "Escribir por WhatsApp"
    assert validate_commercial_action_values(v) is None
