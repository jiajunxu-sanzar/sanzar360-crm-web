from __future__ import annotations

from services.newsletter_service import (
    NewsletterContent,
    SANZAR_LINKEDIN_URL,
    SANZAR_WEB_URL,
    TEST_CONTACT_ID,
    TEST_NEWSLETTER_ID,
    allows_crm_email,
    build_unsubscribe_url,
    data_uri,
    image_mime_subtype,
    is_newsletter_subscribed,
    load_linkedin_icon_bytes,
    load_logo_bytes,
    load_web_icon_bytes,
    newsletter_content_from_historial_row,
    render_newsletter_html,
    row_had_newsletter_image,
    verify_unsubscribe_token,
    _paragraph_to_html,
    _sign,
)


def _render(content: NewsletterContent, **kwargs) -> str:
    defaults = dict(
        logo_src="cid:logo",
        hero_src=None,
        unsubscribe_url=None,
        icon_web_src="cid:icon_web",
        icon_linkedin_src="cid:icon_linkedin",
    )
    defaults.update(kwargs)
    return render_newsletter_html(content, **defaults)


def test_is_newsletter_subscribed_default_true_for_empty_or_missing() -> None:
    assert is_newsletter_subscribed({}) is True
    assert is_newsletter_subscribed({"newsletter_suscrito": ""}) is True
    assert is_newsletter_subscribed({"newsletter_suscrito": "sí"}) is True
    assert is_newsletter_subscribed({"newsletter_suscrito": "SI"}) is True


def test_is_newsletter_subscribed_false_only_for_no() -> None:
    assert is_newsletter_subscribed({"newsletter_suscrito": "no"}) is False
    assert is_newsletter_subscribed({"newsletter_suscrito": " No "}) is False
    assert is_newsletter_subscribed({"newsletter_suscrito": "NO"}) is False


def test_allows_crm_email_default_true() -> None:
    assert allows_crm_email({}) is True
    assert allows_crm_email({"no_recibir_emails": ""}) is True
    assert allows_crm_email({"no_recibir_emails": "no"}) is True
    assert allows_crm_email({"no_recibir_emails": "NO"}) is True


def test_allows_crm_email_false_when_si() -> None:
    assert allows_crm_email({"no_recibir_emails": "sí"}) is False
    assert allows_crm_email({"no_recibir_emails": "si"}) is False
    assert allows_crm_email({"no_recibir_emails": " Sí "}) is False


def test_token_roundtrip_and_tamper_detection() -> None:
    token = _sign("contact-1", "newsletter-1")
    assert verify_unsubscribe_token("contact-1", "newsletter-1", token) is True
    # Distinto contacto o distinta newsletter -> token no válido.
    assert verify_unsubscribe_token("contact-2", "newsletter-1", token) is False
    assert verify_unsubscribe_token("contact-1", "newsletter-2", token) is False
    # Token corrupto/adivinado -> no válido.
    assert verify_unsubscribe_token("contact-1", "newsletter-1", token[:-1] + "0") is False


def test_build_unsubscribe_url_none_without_public_base_url(monkeypatch) -> None:
    import services.newsletter_service as ns

    monkeypatch.setattr(ns, "NEWSLETTER_PUBLIC_BASE_URL", "")
    assert build_unsubscribe_url("c1", "n1") is None


def test_build_unsubscribe_url_contains_signed_token(monkeypatch) -> None:
    import services.newsletter_service as ns

    monkeypatch.setattr(ns, "NEWSLETTER_PUBLIC_BASE_URL", "https://sanzar-crm.streamlit.app")
    url = build_unsubscribe_url("c1", "n1")
    assert url is not None
    assert url.startswith("https://sanzar-crm.streamlit.app/?")
    assert "newsletter_unsub=1" in url
    assert "cid=c1" in url
    assert "nid=n1" in url
    assert "t=" in url


def test_paragraph_to_html_markdown_safe() -> None:
    assert "<strong>negrita</strong>" in _paragraph_to_html("**negrita**")
    assert "<u>sub</u>" in _paragraph_to_html("++sub++")
    html = _paragraph_to_html("[ver](https://example.com/path)")
    assert 'href="https://example.com/path"' in html
    assert ">ver</a>" in html
    # HTML libre escapado; javascript: no se convierte en enlace.
    assert "&lt;script&gt;" in _paragraph_to_html("<script>x</script>")
    assert "<script>" not in _paragraph_to_html("<script>x</script>")
    assert 'href="' not in _paragraph_to_html("[bad](javascript:alert(1))")
    assert "a<br>b" in _paragraph_to_html("a\nb")


def test_render_newsletter_html_escapes_user_content_and_includes_images() -> None:
    content = NewsletterContent(
        asunto="Asunto SMTP distinto",
        titulo="<script>alert(1)</script>",
        parrafo="línea 1\nlínea 2",
        cta_texto="Ver más",
        cta_url="https://sanzar-group.com",
    )
    html = _render(
        content,
        hero_src="cid:hero",
        unsubscribe_url="https://sanzar-crm.streamlit.app/?newsletter_unsub=1",
    )
    assert "<script>alert(1)</script>" not in html  # escapado
    assert "&lt;script&gt;" in html
    assert "línea 1<br>línea 2" in html
    assert 'src="cid:logo"' in html
    assert 'src="cid:hero"' in html
    assert 'src="cid:icon_web"' in html
    assert 'src="cid:icon_linkedin"' in html
    assert "Ver más" in html
    assert "https://sanzar-group.com" in html
    assert "Darse de baja" in html
    # El asunto SMTP no va al cuerpo HTML; solo el título H1.
    assert "Asunto SMTP distinto" not in html


def test_render_newsletter_html_header_centered_and_footer_links() -> None:
    content = NewsletterContent(
        asunto="Asunto",
        titulo="Título",
        parrafo="**hola**",
        cta_texto="",
        cta_url="",
    )
    html = _render(content)
    assert "text-align:center" in html
    assert 'height="50"' in html
    assert 'max-width:400px' in html
    assert SANZAR_WEB_URL in html
    assert SANZAR_LINKEDIN_URL in html
    assert "viewAsMember" not in html
    assert "<strong>hola</strong>" in html


def test_render_newsletter_html_without_hero_or_cta_or_unsubscribe() -> None:
    content = NewsletterContent(
        asunto="Asunto",
        titulo="Título",
        parrafo="Texto",
        cta_texto="",
        cta_url="",
    )
    html = _render(content)
    assert 'src="cid:hero"' not in html
    assert "info@sanzar-group.com" in html  # fallback de contacto sin URL de baja
    assert "Título" in html
    assert "Asunto" not in html  # asunto no se renderiza en el HTML


def test_test_send_uses_dedicated_ids_that_never_match_real_contacts() -> None:
    # Los ids de prueba nunca deben poder colisionar con un contact_id o
    # newsletter_id real (ambos son uuid4), así que un clic accidental en el
    # botón de baja de un correo de prueba no afecta a nadie real.
    assert TEST_CONTACT_ID == "__test__"
    assert TEST_NEWSLETTER_ID == "__test__"


def test_image_mime_subtype() -> None:
    assert image_mime_subtype("foto.JPG") == "jpeg"
    assert image_mime_subtype("foto.jpeg") == "jpeg"
    assert image_mime_subtype("foto.png") == "png"
    assert image_mime_subtype("foto.webp") == "webp"
    assert image_mime_subtype("sin_extension") == "png"


def test_data_uri_format() -> None:
    uri = data_uri(b"hello", "png")
    assert uri.startswith("data:image/png;base64,")


def test_load_logo_bytes_reads_real_asset() -> None:
    data = load_logo_bytes()
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_load_footer_icon_bytes() -> None:
    assert len(load_web_icon_bytes()) > 0
    assert len(load_linkedin_icon_bytes()) > 0


def test_newsletter_content_from_historial_row_and_preview() -> None:
    row = {
        "newsletter_asunto": "Asunto bandeja",
        "titulo": "Titulo H1",
        "newsletter_texto": "Hola **mundo**",
        "boton_newsletter": "sí",
        "newsletter_cta_texto": "Ver más",
        "link_boton_newsletter": "https://example.com/x",
        "imagen": "sí",
    }
    content = newsletter_content_from_historial_row(row)
    assert content.asunto == "Asunto bandeja"
    assert content.titulo == "Titulo H1"
    assert content.cta_texto == "Ver más"
    assert content.cta_url == "https://example.com/x"
    assert row_had_newsletter_image(row) is True
    html = _render(content)
    assert "Titulo H1" in html
    assert "Asunto bandeja" not in html
    assert "Ver más" in html
    assert "https://example.com/x" in html
    assert "<strong>mundo</strong>" in html
