#!/usr/bin/env python3
"""Envía el resumen diario del CRM por correo (pensado para el cron de las 6:00).

Lee Google Sheets con la cuenta de servicio y manda un solo correo HTML con:

- Próximas acciones y tareas con fecha de hoy.
- Seguimiento comercial y tareas atrasados que siguen pendientes.

Configuración por variables de entorno (además de las que ya usa la app):

    GOOGLE_SHEET_ID
    GOOGLE_WORKSHEET_NAME              (por defecto Contacts)
    GOOGLE_ACTIVITY_LOG_WORKSHEET_NAME
    GOOGLE_SERVICE_ACCOUNT_PATH        ruta al JSON de la cuenta de servicio
    SMTP_PROFILE_JIAJUN_HOST / _PORT / _USER / _PASSWORD / _USE_TLS

    DAILY_DIGEST_SMTP_PROFILE   perfil SMTP remitente (por defecto ``jiajun``)
    DAILY_DIGEST_RECIPIENTS     destinatarios separados por coma
    DAILY_DIGEST_SEND_IF_EMPTY  "true" para enviar también los días sin nada
    DAILY_DIGEST_DRY_RUN        "true" para imprimir el HTML sin enviar

Uso:

    python3 -m scripts.send_daily_digest
    python3 -m scripts.send_daily_digest --dry-run
    python3 -m scripts.send_daily_digest --fecha 02/09/2026
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.smtp_profiles import resolve_smtp_profile  # noqa: E402
from config.settings import ACCIONES_HEADERS, CONFIG  # noqa: E402
from services.daily_digest import (  # noqa: E402
    build_daily_digest,
    digest_subject,
    render_digest_html,
    render_digest_text,
)
from services.email_service import (  # noqa: E402
    send_html_email,
    smtp_connection,
    smtp_exception_user_message,
)
from services.history_service import HISTORY_SPECS  # noqa: E402
from services.sheets_service import SheetsService  # noqa: E402

DEFAULT_RECIPIENTS = (
    "carla.moreno@sanzar-group.com",
    "david.ortiz@sanzar-group.com",
    "info@sanzar-group.com",
    "jiajun.xu@sanzar-group.com",
)
DEFAULT_PROFILE = "jiajun"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "y", "si", "sí"}


def recipients() -> list[str]:
    raw = os.getenv("DAILY_DIGEST_RECIPIENTS", "").strip()
    if not raw:
        return list(DEFAULT_RECIPIENTS)
    seen: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        addr = chunk.strip()
        if addr and addr not in seen:
            seen.append(addr)
    return seen or list(DEFAULT_RECIPIENTS)


def _parse_fecha(raw: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise SystemExit(f"Fecha no válida: {raw!r}. Usa DD/MM/AAAA.")


def load_data(sheets: SheetsService) -> tuple[list[dict[str, str]], list[dict[str, str]], object]:
    tareas_spec = HISTORY_SPECS["tareas"]
    acciones_ws = CONFIG.google_activity_log_worksheet_name

    contacts_df = sheets.load_contacts_df()
    acciones_df = sheets.read_worksheet_df(acciones_ws, list(ACCIONES_HEADERS))
    tareas_df = sheets.read_worksheet_df(tareas_spec.worksheet_name, list(tareas_spec.headers))

    acciones_rows = acciones_df.fillna("").astype(str).to_dict("records") if not acciones_df.empty else []
    tareas_rows = tareas_df.fillna("").astype(str).to_dict("records") if not tareas_df.empty else []
    return acciones_rows, tareas_rows, contacts_df


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumen diario del CRM por correo.")
    parser.add_argument("--dry-run", action="store_true", help="No envía: imprime el asunto y el HTML.")
    parser.add_argument("--fecha", default="", help="Fecha de referencia DD/MM/AAAA (por defecto, hoy).")
    parser.add_argument("--to", default="", help="Destinatarios separados por coma (sobrescribe el entorno).")
    args = parser.parse_args()

    today = _parse_fecha(args.fecha) if args.fecha else date.today()
    dry_run = args.dry_run or _env_bool("DAILY_DIGEST_DRY_RUN")

    if not CONFIG.google_sheet_id:
        print("ERROR: falta GOOGLE_SHEET_ID.", file=sys.stderr)
        return 2

    try:
        acciones_rows, tareas_rows, contacts_df = load_data(SheetsService())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR leyendo Google Sheets: {exc}", file=sys.stderr)
        return 3

    digest = build_daily_digest(
        acciones_rows=acciones_rows,
        tareas_rows=tareas_rows,
        contacts_df=contacts_df,
        today=today,
    )
    subject = digest_subject(digest)
    print(
        f"[{today.isoformat()}] hoy={digest.total_hoy} atrasado={digest.total_atrasado} "
        f"(acciones {len(digest.acciones_hoy)}/{len(digest.acciones_atrasadas)}, "
        f"tareas {len(digest.tareas_hoy)}/{len(digest.tareas_atrasadas)})"
    )

    if digest.vacio and not _env_bool("DAILY_DIGEST_SEND_IF_EMPTY", True):
        print("Sin acciones ni tareas: no se envía (DAILY_DIGEST_SEND_IF_EMPTY=false).")
        return 0

    html = render_digest_html(digest)
    texto = render_digest_text(digest)

    if dry_run:
        print(f"\nAsunto: {subject}\n")
        print(texto)
        out = PROJECT_ROOT / "daily_digest_preview.html"
        out.write_text(html, encoding="utf-8")
        print(f"\nHTML de prueba escrito en {out}")
        return 0

    destinatarios = (
        [a.strip() for a in args.to.replace(";", ",").split(",") if a.strip()]
        if args.to
        else recipients()
    )
    if not destinatarios:
        print("ERROR: no hay destinatarios.", file=sys.stderr)
        return 2

    slug = os.getenv("DAILY_DIGEST_SMTP_PROFILE", DEFAULT_PROFILE).strip().lower() or DEFAULT_PROFILE
    resolved = resolve_smtp_profile(slug)
    if not resolved.profile_complete:
        print(
            f"ERROR: el perfil SMTP «{slug}» no está configurado "
            f"(faltan SMTP_PROFILE_{slug.upper()}_HOST / _USER / _PASSWORD).",
            file=sys.stderr,
        )
        return 4

    fallos = 0
    try:
        with smtp_connection(resolved.delivery) as connection:
            for addr in destinatarios:
                try:
                    send_html_email(
                        addr,
                        subject,
                        html,
                        plain_fallback=texto,
                        connection=connection,
                    )
                    print(f"  enviado → {addr}")
                except Exception as exc:  # noqa: BLE001
                    fallos += 1
                    print(
                        f"  ERROR → {addr}: "
                        f"{smtp_exception_user_message(exc, routed_profile_slug=slug)}",
                        file=sys.stderr,
                    )
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR de conexión SMTP: {smtp_exception_user_message(exc, routed_profile_slug=slug)}",
            file=sys.stderr,
        )
        return 5

    print(f"Resumen enviado desde {resolved.delivery.user} a {len(destinatarios) - fallos} destinatario(s).")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
