from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.smtp_profiles import SmtpDeliveryConfig
from services.email_service import send_email, send_html_email, smtp_connection


class _FakeSMTP:
    """Stand-in for ``smtplib.SMTP`` that records what would have been sent."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_args: tuple[str, str] | None = None
        self.sent_message = None
        self.sent_messages: list[object] = []
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def send_message(self, msg) -> None:
        self.sent_message = msg
        self.sent_messages.append(msg)

    def quit(self) -> None:
        self.quit_called = True


def _cfg(**overrides: object) -> SmtpDeliveryConfig:
    base = dict(host="smtp.example.com", port=587, user="a@sanzar-group.com", password="secret", use_tls=True)
    base.update(overrides)
    return SmtpDeliveryConfig(**base)  # type: ignore[arg-type]


def test_send_html_email_builds_multipart_with_inline_image() -> None:
    _FakeSMTP.instances.clear()
    html = '<html><body><img src="cid:logo"><p>Hola</p></body></html>'
    with patch("smtplib.SMTP", _FakeSMTP):
        send_html_email(
            "dest@example.com",
            "Asunto de prueba",
            html,
            inline_images={"logo": (b"fake-png-bytes", "png")},
            delivery=_cfg(),
        )

    assert len(_FakeSMTP.instances) == 1
    fake = _FakeSMTP.instances[0]
    assert fake.starttls_called is True
    assert fake.login_args == ("a@sanzar-group.com", "secret")

    msg = fake.sent_message
    assert msg["Subject"] == "Asunto de prueba"
    assert msg["To"] == "dest@example.com"

    content_types = [part.get_content_type() for part in msg.walk()]
    assert "multipart/alternative" in content_types
    assert "multipart/related" in content_types
    assert "text/plain" in content_types  # fallback para clientes sin HTML
    assert "text/html" in content_types
    assert "image/png" in content_types

    image_parts = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    assert len(image_parts) == 1
    assert image_parts[0].get("Content-ID") == "<logo>"
    assert image_parts[0].get_payload(decode=True) == b"fake-png-bytes"


def test_send_html_email_without_inline_images() -> None:
    _FakeSMTP.instances.clear()
    with patch("smtplib.SMTP", _FakeSMTP):
        send_html_email("dest@example.com", "Asunto", "<html><body>Hola</body></html>", delivery=_cfg())
    fake = _FakeSMTP.instances[0]
    content_types = [part.get_content_type() for part in fake.sent_message.walk()]
    assert "multipart/related" not in content_types
    assert "text/html" in content_types


def test_send_html_email_raises_without_smtp_config() -> None:
    try:
        send_html_email("dest@example.com", "Asunto", "<html></html>", delivery=_cfg(host="", user=""))
        assert False, "debería haber lanzado RuntimeError"
    except RuntimeError:
        pass


def test_smtp_connection_reused_across_several_sends() -> None:
    """Envío masivo: una sola conexión (un solo handshake+login) para N correos."""
    _FakeSMTP.instances.clear()
    with patch("smtplib.SMTP", _FakeSMTP):
        with smtp_connection(_cfg()) as conn:
            for i in range(5):
                send_html_email(f"dest{i}@example.com", "Asunto", "<html></html>", connection=conn)

    # Una única conexión abierta y autenticada, no una por destinatario.
    assert len(_FakeSMTP.instances) == 1
    fake = _FakeSMTP.instances[0]
    assert fake.starttls_called is True
    assert fake.login_args == ("a@sanzar-group.com", "secret")
    assert len(fake.sent_messages) == 5
    assert [m["To"] for m in fake.sent_messages] == [f"dest{i}@example.com" for i in range(5)]
    assert all(m["From"] == "a@sanzar-group.com" for m in fake.sent_messages)
    # La conexión se cierra sola al salir del context manager.
    assert fake.quit_called is True


def test_smtp_connection_closes_even_if_send_raises() -> None:
    _FakeSMTP.instances.clear()
    with patch("smtplib.SMTP", _FakeSMTP):
        try:
            with smtp_connection(_cfg()) as conn:
                conn.send_message  # noqa: B018 - solo para referenciarlo, no lo llamamos
                raise ValueError("fallo simulado a mitad del envío masivo")
        except ValueError:
            pass
    assert _FakeSMTP.instances[0].quit_called is True


def test_send_email_reuses_connection_too() -> None:
    _FakeSMTP.instances.clear()
    with patch("smtplib.SMTP", _FakeSMTP):
        with smtp_connection(_cfg()) as conn:
            send_email("dest@example.com", "Asunto texto", "Cuerpo", connection=conn)
    fake = _FakeSMTP.instances[0]
    assert fake.sent_message["To"] == "dest@example.com"
    assert fake.sent_message["From"] == "a@sanzar-group.com"


def test_send_html_email_without_connection_still_opens_and_closes_one_connection() -> None:
    """Comportamiento sin cambios para quien no pase `connection` (envío individual)."""
    _FakeSMTP.instances.clear()
    with patch("smtplib.SMTP", _FakeSMTP):
        send_html_email("dest@example.com", "Asunto", "<html></html>", delivery=_cfg())
    assert len(_FakeSMTP.instances) == 1
