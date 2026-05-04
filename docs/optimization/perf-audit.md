# Auditoría de rendimiento (resumen ejecutado)

## Cuellos de botella detectados y tratados

1. **Full write de históricos por cada cambio**
   - Antes: `clear + update` de hoja completa.
   - Ahora: append/update por fila en históricos.
   - Archivos: `services/history_service.py`, `services/sheets_service.py`.

2. **Invalidación de caché demasiado amplia**
   - Antes: cambios en históricos recargaban contactos.
   - Ahora: versiones separadas (`contacts_cache_version`, `history_cache_version`).
   - Archivos: `app/state.py`, `streamlit_app.py`, `pages/contacts.py`.

3. **Reparseo repetido de históricos en búsquedas/alarms**
   - Ahora: cache de filas históricas y cache interno de ocurrencias de sensores.
   - Archivos: `app/cache.py`, `services/history_service.py`, `pages/asset_search.py`, `pages/alarms.py`.

4. **Filtros de fecha no vectorizados**
   - Ahora: `pd.to_datetime` + máscaras vectoriales para buckets de próxima acción.
   - Archivo: `pages/contacts.py`.

## Instrumentación añadida
- Telemetría de eventos y duración en `app/telemetry.py`.
- Trazas en render de páginas y operaciones de `SheetsService`.
- Visualización rápida en Dashboard (expander de telemetría).

## Pendientes de optimización
- Reducir widgets por fila en lista de contactos para datasets muy grandes.
- Paginación/virtualización en tablas de gran volumen.
- Métricas persistentes (no solo `session_state`).
