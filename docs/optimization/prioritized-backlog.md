# Backlog Priorizado (Impacto/Esfuerzo)

## Alta prioridad
- **Incremental writes en históricos**
  - Estado: implementado.
  - Cambio: evitar `clear + update` full sheet para `add/update`.
  - Archivos: `services/history_service.py`, `services/sheets_service.py`.

- **Separación de caché por dominio**
  - Estado: implementado.
  - Cambio: `contacts_cache_version` separado de `history_cache_version`.
  - Archivos: `app/state.py`, `streamlit_app.py`, `pages/contacts.py`.

- **Cache de filas de históricos para búsquedas/alarms**
  - Estado: implementado.
  - Cambio: `load_history_rows_cached`.
  - Archivos: `app/cache.py`, `pages/asset_search.py`, `pages/alarms.py`.

## Prioridad media
- **Refactor de `pages/contacts.py` por módulos**
  - Estado: iniciado.
  - Cambio: extraído `services/contact_use_cases.py`.
  - Pendiente: extraer filtros/form/históricos a módulos dedicados.

- **Estandarizar parse/fechas**
  - Estado: parcial.
  - Cambio: bucket de fechas vectorizado en contactos.
  - Pendiente: unificar utilidades de fecha entre páginas/servicios.

## Prioridad baja
- **Observabilidad persistente**
  - Estado: parcial.
  - Cambio: telemetría en `session_state` y logger.
  - Pendiente: exportar eventos a hoja de métricas o archivo.
