from __future__ import annotations

from app.smtp_profiles import NEWSLETTER_SMTP_PROFILE_SLUG, resolve_smtp_profile


def test_newsletter_smtp_profile_slug_is_info() -> None:
    assert NEWSLETTER_SMTP_PROFILE_SLUG == "info"


def test_resolve_smtp_profile_missing_is_incomplete(monkeypatch) -> None:
    import app.smtp_profiles as sp

    monkeypatch.setattr(sp, "_smtp_profiles_dict", lambda: {})
    resolved = resolve_smtp_profile("info")
    assert resolved.routed_profile_slug == "info"
    assert resolved.profile_complete is False


def test_resolve_smtp_profile_info_complete(monkeypatch) -> None:
    import app.smtp_profiles as sp

    monkeypatch.setattr(
        sp,
        "_smtp_profiles_dict",
        lambda: {
            "info": {
                "host": "smtp.gmail.com",
                "port": "587",
                "user": "info@sanzar-group.com",
                "password": "app-pass",
                "use_tls": "true",
            }
        },
    )
    resolved = resolve_smtp_profile("info")
    assert resolved.profile_complete is True
    assert resolved.routed_profile_slug == "info"
    assert resolved.delivery.user == "info@sanzar-group.com"
    assert resolved.delivery.host == "smtp.gmail.com"


def test_resolve_smtp_profile_incomplete_without_user(monkeypatch) -> None:
    import app.smtp_profiles as sp

    monkeypatch.setattr(
        sp,
        "_smtp_profiles_dict",
        lambda: {"info": {"host": "smtp.gmail.com", "user": "", "password": "x"}},
    )
    resolved = resolve_smtp_profile("info")
    assert resolved.profile_complete is False
    assert resolved.routed_profile_slug == "info"
