# Estrategia mínima de tests y smoke checks

## Unit tests críticos
- `services/history_service.py`
  - alta/edición incremental.
  - conflictos de sensores.
  - estado de suscripción.
- `services/sheet_date_format.py`
  - fechas DD/MM/AAAA.
  - seriales de sensores.
- `services/contact_use_cases.py`
  - crear contacto y guardar cambios por `contact_id`.

## Integration smoke (manual y automático ligero)
- Cargar contactos.
- Seleccionar contacto y guardar ficha.
- Crear histórico y verificar persistencia.
- Cambiar entre páginas (navegación 1 click).
- Buscar activo y abrir ficha.

## Comandos
```bash
python3 -m pytest
python3 -m compileall app config models services ui pages streamlit_app.py
```
