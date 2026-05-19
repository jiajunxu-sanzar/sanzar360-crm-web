from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.secrets import get_bool_secret, get_int_secret, get_secret

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def normalize_google_sheet_id(raw: str) -> str:
    value = (raw or "").strip().strip('"').strip("'")
    if "docs.google.com" in value and "/d/" in value:
        start = value.index("/d/") + 3
        tail = value[start:]
        return tail.split("/")[0].split("?")[0].strip()
    return value


SEGUIMIENTO_COMERCIAL_FIELDS: frozenset[str] = frozenset({
    "fuente_lead",
    "lead_detalle",
    "fecha_primer_contacto",
    "persona_primer_contacto",
    "fecha_ultimo_contacto",
    "persona_ultimo_contacto",
    "proxima_accion_fecha",
    "persona_proxima_accion",
    "proxima_accion_detalle",
    "fecha_veces_sin_respuesta",
})

CANONICAL_COLUMNS = [
    "contact_id",
    "nombre",
    "tipo_entidad",
    "detalle",
    "país",
    "provincia",
    "municipio",
    "coordenadas",
    "direccion",
    "telefono",
    "correo",
    "cuenta_usuario",
    "digital_maps",
    "iot_module",
    "sowing_module",
    "otros_contactos",
    "cultivos",
    "superficie_ha",
    "tipo_riego",
    "fuente_lead",
    "lead_detalle",
    "fecha_primer_contacto",
    "persona_primer_contacto",
    "fecha_ultimo_contacto",
    "persona_ultimo_contacto",
    "proxima_accion_fecha",
    "persona_proxima_accion",
    "proxima_accion_detalle",
    "fecha_veces_sin_respuesta",
    "estado",
    "fecha_estado",
    "razon_perdida",
    "valor",
]

CONTACT_ESTADO_OPCIONES: tuple[str, ...] = (
    "Nuevo Contacto",
    "En Contacto",
    "En Negociación",
    "Cliente",
    "Perdido",
)
CONTACT_ESTADO_SET = frozenset(CONTACT_ESTADO_OPCIONES)

FUENTE_LEAD_OPCIONES: tuple[str, ...] = (
    "Referencia",
    "Evento",
    "Cold Call",
    "Email",
    "Puerta Fría",
    "Página Web/SEO",
)

VALOR_OPCIONES: tuple[str, ...] = ("Bajo", "Medio", "Alto")

PERSONA_ULTIMO_CONTACTO_OPCIONES: tuple[str, ...] = (
    "Jiajun Xu",
    "Kabir Caravotta",
    "Marco Ruano",
    "David Ortiz",
    "Viviana Castañeda",
    "Carla Moreno",
)
PERSONA_ULTIMO_CONTACTO_SET = frozenset(PERSONA_ULTIMO_CONTACTO_OPCIONES)
PERSONA_COMERCIAL_OPCIONES: tuple[str, ...] = PERSONA_ULTIMO_CONTACTO_OPCIONES
PERSONA_COMERCIAL_SET = PERSONA_ULTIMO_CONTACTO_SET

_TEMPLATE_LABEL_ALIASES_EXTRA: dict[str, str] = {
    "Contact Id": "contact_id",
    "Nombre": "nombre",
    "Tipo Entidad": "tipo_entidad",
    "Detalle": "detalle",
    "País": "país",
    "Pais": "país",
    "Provincia": "provincia",
    "Municipio": "municipio",
    "Coordenadas": "coordenadas",
    "Dirección": "direccion",
    "Direccion": "direccion",
    "Teléfono": "telefono",
    "Telefono": "telefono",
    "Correo": "correo",
    "Cuenta usuario": "cuenta_usuario",
    "Digital maps": "digital_maps",
    "Iot module": "iot_module",
    "Sowing module": "sowing_module",
    "email": "correo",
    "Email": "correo",
    "Otros contactos": "otros_contactos",
    "Cultivos": "cultivos",
    "Superficie Ha": "superficie_ha",
    "Superficie": "superficie_ha",
    "Tipo Riego": "tipo_riego",
    "Riego": "tipo_riego",
    "Fuente Lead": "fuente_lead",
    "Lead detalle": "lead_detalle",
    "Persona último contacto": "persona_ultimo_contacto",
    "Valor": "valor",
    "Próxima acción detalle": "proxima_accion_detalle",
    "Estado": "estado",
    "Fecha estado": "fecha_estado",
    "Razón pérdida": "razon_perdida",
}
TEMPLATE_LABEL_ALIASES: dict[str, str] = {
    c: c for c in CANONICAL_COLUMNS
} | _TEMPLATE_LABEL_ALIASES_EXTRA

INVENTORY_WORKSHEET_NAME = "Inventario"
INVENTORY_MODEL_FIELDS_WORKSHEET_NAME = "InventarioCamposModelo"
INVENTORY_HEADERS: tuple[str, ...] = (
    "inventory_id",
    "asset_type",
    "model",
    "brand",
    "supplier",
    "acquisition_type",
    "acquisition_date",
    "loan_end_date",
    "logistics_status",
    "location_type",
    "location_contact_id",
    "location_detail",
    "serial_number",
    "sim_eid_number",
    "eui",
    "configured",
    "gateway_config_name",
    "ui_password",
    "proforma_invoice_url",
    "payment_receipt_url",
    "parent_asset_id",
    "associated_sim_inventory_id",
    "associated_probe_inventory_id",
    "associated_gateway_inventory_id",
    "notes",
    "created_at",
    "updated_at",
)
INVENTORY_MODEL_FIELD_HEADERS: tuple[str, ...] = (
    "model",
    "field_key",
    "field_label",
    "field_type",
    "required",
    "options_csv",
    "help_text",
    "order_index",
    "active",
    "created_at",
    "updated_at",
)

COMPRAS_WORKSHEET_NAME = "Compras"
COMPRAS_ESTADOS: tuple[str, ...] = (
    "comparando",
    "pendiente",
    "en_transito",
    "recibida",
    "cancelada",
)
COMPRAS_ESTADOS_PENDIENTES: frozenset[str] = frozenset({"comparando", "pendiente", "en_transito"})
COMPRAS_HEADERS: tuple[str, ...] = (
    "compra_id",
    "referencia",
    "descripcion",
    "proveedor",
    "proveedor_contacto",
    "proveedor_direccion",
    "proveedor_telefono",
    "proveedor_email",
    "estado",
    "fecha_solicitud",
    "fecha_pedido",
    "fecha_recepcion",
    "importe_total",
    "moneda",
    "proforma_invoice_url",
    "pis_comparativas_carpeta_url",
    "payment_receipt_url",
    "po_lineas_json",
    "ship_to",
    "po_notas",
    "responsable",
    "notas",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class AppConfig:
    google_sheet_id: str = normalize_google_sheet_id(get_secret("GOOGLE_SHEET_ID", ""))
    google_worksheet_name: str = get_secret("GOOGLE_WORKSHEET_NAME", "Contacts")
    google_activity_log_worksheet_name: str = get_secret(
        "GOOGLE_ACTIVITY_LOG_WORKSHEET_NAME", "Acciones"
    )
    google_activity_kpi_worksheet_name: str = get_secret(
        "GOOGLE_ACTIVITY_KPI_WORKSHEET_NAME", "ResumenSemanal"
    )
    google_service_account_path: str = get_secret(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        get_secret("GOOGLE_SERVICE_ACCOUNT_PATH", "config/credentials/service_account.json"),
    )
    smtp_host: str = get_secret("SMTP_HOST", "")
    smtp_port: int = get_int_secret("SMTP_PORT", 587)
    smtp_user: str = get_secret("SMTP_USER", "")
    smtp_password: str = get_secret("SMTP_PASSWORD", "")
    smtp_use_tls: bool = get_bool_secret("SMTP_USE_TLS", True)
    app_password: str = get_secret("APP_PASSWORD", "")


CONFIG = AppConfig()
