# Sanzar CRM Web

Aplicacion Streamlit que replica la funcionalidad principal del CRM desktop PySide:
contactos, historicos, buscador de sensores/SIM, centro de alarmas, mapa, email,
facturas y pricing.

## Ejecutar En Local

```bash
cd "/Users/davidxu/Documents/sanzar/2 - operaciones/sanzar-crm-web"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

La app lee secretos desde `.env` y desde
`config/credentials/service_account.json`. Ambos archivos estan en `.gitignore`.

## Variables Locales

Copia `.env.example` a `.env` y completa:

```bash
GOOGLE_SHEET_ID=...
GOOGLE_WORKSHEET_NAME=Contacts
GOOGLE_SERVICE_ACCOUNT_JSON=config/credentials/service_account.json
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_USE_TLS=true
```

## Streamlit Cloud

No subas `.env`, `.streamlit/secrets.toml` ni el JSON de Google a Git.
En Streamlit Cloud usa `App settings -> Secrets` con el formato de
`.streamlit/secrets.example.toml`.

La cuenta de servicio debe tener permiso sobre el Google Sheet y, si se usan
facturas o Drive, sobre las carpetas concretas necesarias.

## Tests

```bash
python3 -m pytest
python3 -m compileall app config models services ui pages streamlit_app.py
```

## Funcionalidades

- Dashboard con KPIs, embudo y graficos.
- Contactos con filtros, ficha y guardado parcial por `contact_id`.
- Historicos de sensores, campanas, suscripciones e incidencias.
- Validacion de fechas `DD/MM/AAAA` y formato de sensores.
- Comprobacion de solapes temporales de sensores entre clientes.
- Buscador operativo de sensores/SIM con disponibilidad y apertura de ficha.
- Centro de alarmas como bandeja de trabajo.
- Pestaña Incidencias: tablero visual de abiertas, pendientes de aprobar y cerradas.
- Resumen diario por correo a las 6:00 (ver `docs/resumen-diario-6am.md`).
- Mapa con coordenadas directas.
- Email con placeholders y preview.
- Facturas PDF descargables con `reportlab`.
- Pricing basico.
