# Baseline KPIs (CRM Web)

## KPI técnicos
- `load_contacts_df`: tiempo total de lectura de contactos.
- `contacts.render`: tiempo de render de la pantalla de contactos.
- `asset_search.render`: tiempo de render del buscador de activos.
- `alarms.render`: tiempo de render del centro de alarmas.
- Operaciones Sheets instrumentadas:
  - `sheets.load_contacts_df`
  - `sheets.save_contact_rows_by_ids`
  - `sheets.append_worksheet_row`
  - `sheets.update_worksheet_row`
  - `sheets.read_worksheet_df`

## Dónde ver el baseline
- En `Dashboard`, sección **Telemetría (baseline)**.
- También en `st.session_state["telemetry_events"]`.

## Escenarios de medición recomendados
1. Carga inicial app y entrada en Contactos.
2. Seleccionar contacto + guardar ficha.
3. Crear histórico de sensores.
4. Buscar activo por serial/SIM.
5. Abrir centro de alarmas y cambiar categoría.

## Criterio de comparación
- Medir en entorno similar (misma red, mismo Google Sheet).
- Repetir cada escenario 3 veces y usar mediana.
