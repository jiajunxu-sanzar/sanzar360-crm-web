"""Resolve SMTP settings per authenticated user from Streamlit secrets (or .toml fallback).

Layouts in `.streamlit/secrets.toml`:
--------------------------------------

  [smtp_profiles.jiajun]
  host = "smtp.gmail.com"
  port = "587"
  user = "jiajun@..."
  password = "..."
  use_tls = "true"

  [smtp_profiles.kabir]
  host = "..."
  ...

  # Opción A: por employee_id de la pestaña «Usuarios CRM»
  [smtp_route_by_employee]
  EMP001 = "jiajun"
  EMP002 = "kabir"

  # Opción B: por nombre exacto igual que columna nombre en usuarios (si no hay ruta por id)
  [smtp_route_by_nombre]
  "Jiajun Xu" = "jiajun"
  "Kabir Caravotta" = "kabir"

Sin ruta SMTP por usuario se usa SMTP_HOST / SMTP_USER / … (CONFIG).
Usuarios con rol **sales** no pueden usar ese fallback: debe existir una entrada
`smtp_route_by_*` que los apunte y un perfil `smtp_profiles.*` usable, para no
enviar desde el buzón global de otro.

Variables de entorno (sin ``st.secrets`` anidado):

- ``SMTP_PROFILE_jiajun_HOST``, ``SMTP_PROFILE_jiajun_USER``, … (slug en minúsculas)
- ``SMTP_ROUTE_BY_EMPLOYEE_EMP001=jiajun``, etc.

Los valores de ``secrets.toml`` / Cloud **sustituyen** a los de entorno si hay clave repetida.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.navigation import ROLE_SALES, normalize_role
from app.secrets import streamlit_secrets
from config.settings import CONFIG

_ENV_PROFILE_PREFIX = "SMTP_PROFILE_"
_ENV_ROUTE_EMP_PREFIX = "SMTP_ROUTE_BY_EMPLOYEE_"


@dataclass(frozen=True)
class SmtpDeliveryConfig:
    host: str
    port: int
    user: str
    password: str
    use_tls: bool


@dataclass(frozen=True)
class SmtpResolved:
    """Resultado de enrutar SMTP por usuario."""

    delivery: SmtpDeliveryConfig
    routed_profile_slug: str | None
    profile_complete: bool


def default_smtp_from_config() -> SmtpDeliveryConfig:
    return SmtpDeliveryConfig(
        host=CONFIG.smtp_host,
        port=CONFIG.smtp_port,
        user=CONFIG.smtp_user,
        password=CONFIG.smtp_password,
        use_tls=CONFIG.smtp_use_tls,
    )


def _plain_dict(fragment: Any) -> dict[str, Any]:
    if fragment is None:
        return {}
    if isinstance(fragment, dict):
        return dict(fragment)
    try:
        return dict(fragment)
    except Exception:
        return {}


def _smtp_profiles_from_env() -> dict[str, dict[str, Any]]:
    suffix_field = (
        ("_HOST", "host"),
        ("_PORT", "port"),
        ("_USER", "user"),
        ("_PASSWORD", "password"),
        ("_USE_TLS", "use_tls"),
    )
    raw: dict[str, dict[str, Any]] = {}
    for key, val in os.environ.items():
        if not key.upper().startswith(_ENV_PROFILE_PREFIX.upper()):
            continue
        rest = key[len(_ENV_PROFILE_PREFIX) :]
        matched = False
        for suf, field in suffix_field:
            upper_rest = rest.upper()
            if upper_rest.endswith(suf):
                slug = rest[: -len(suf)].strip("_").lower()
                if slug:
                    raw.setdefault(slug, {})[field] = val
                matched = True
                break
        if not matched:
            continue
    return {k: v for k, v in raw.items() if v}


def _smtp_profiles_from_secrets_only() -> dict[str, dict[str, Any]]:
    secrets = streamlit_secrets()
    if secrets is None:
        return {}
    try:
        block = secrets.get("smtp_profiles")
    except Exception:
        return {}
    if not block:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw_key, vals in _plain_dict(block).items():
        key = str(raw_key).strip().lower()
        if key:
            out[key] = _plain_dict(vals)
    return out


def _smtp_profiles_dict() -> dict[str, dict[str, Any]]:
    merged = {**_smtp_profiles_from_env(), **_smtp_profiles_from_secrets_only()}
    return merged


def _routes_table(key: str) -> dict[str, str]:
    secrets = streamlit_secrets()
    if secrets is None:
        return {}
    try:
        block = secrets.get(key)
    except Exception:
        return {}
    if not block:
        return {}
    return {
        str(k).strip(): str(v).strip()
        for k, v in _plain_dict(block).items()
        if str(k).strip() and str(v).strip()
    }


def _smtp_route_by_employee_from_env() -> dict[str, str]:
    out: dict[str, str] = {}
    pfx = _ENV_ROUTE_EMP_PREFIX.upper()
    for key, val in os.environ.items():
        ku = key.upper()
        if not ku.startswith(pfx):
            continue
        emp = key[len(_ENV_ROUTE_EMP_PREFIX) :].strip()
        v = val.strip()
        if emp and v:
            out[emp] = v.lower()
    return out


def smtp_route_by_employee() -> dict[str, str]:
    merged = {**_smtp_route_by_employee_from_env()}
    merged.update(_routes_table("smtp_route_by_employee"))
    return merged


def smtp_route_by_nombre() -> dict[str, str]:
    return _routes_table("smtp_route_by_nombre")


def _profile_as_config(profile: dict[str, Any]) -> SmtpDeliveryConfig | None:
    host = str(profile.get("host", "")).strip()
    user = str(profile.get("user", "")).strip()
    password = str(profile.get("password", "")).strip()
    if not host or not user:
        return None
    raw_port = profile.get("port", CONFIG.smtp_port)
    try:
        port = int(str(raw_port).strip())
    except ValueError:
        port = CONFIG.smtp_port
    tls_raw = str(profile.get("use_tls", "true")).strip().lower()
    use_tls = tls_raw in {"", "1", "true", "yes", "y", "si", "sí"}
    return SmtpDeliveryConfig(host=host, port=port, user=user, password=password, use_tls=use_tls)


def resolve_smtp_detail(
    *,
    employee_id: str = "",
    nombre: str = "",
    app_role: str = "",
) -> SmtpResolved:
    profiles = _smtp_profiles_dict()
    fallback = default_smtp_from_config()
    fallback_usable = bool(fallback.host and fallback.user)

    slug_role = normalize_role(app_role)

    emp = employee_id.strip()
    nome = nombre.strip()
    profile_key = ""
    if emp:
        profile_key = smtp_route_by_employee().get(emp, "").strip().lower()
    if not profile_key and nome:
        profile_key = smtp_route_by_nombre().get(nome, "").strip().lower()

    if not profile_key:
        if slug_role == ROLE_SALES:
            return SmtpResolved(fallback, None, False)
        return SmtpResolved(fallback, None, fallback_usable)

    if profile_key not in profiles:
        return SmtpResolved(fallback, profile_key, False)

    cfg = _profile_as_config(profiles[profile_key])
    if cfg is None:
        return SmtpResolved(fallback, profile_key, False)
    return SmtpResolved(cfg, profile_key, True)


def resolve_smtp_for_user(
    *,
    employee_id: str = "",
    nombre: str = "",
    app_role: str = "",
) -> SmtpDeliveryConfig:
    return resolve_smtp_detail(
        employee_id=employee_id, nombre=nombre, app_role=app_role
    ).delivery
