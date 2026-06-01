# Migración: seguimiento comercial en hoja Acciones

## Antes del despliegue

1. Exportar CSV de la pestaña **Acciones** actual (log antiguo de 6 columnas) si queréis conservar histórico.
2. Exportar CSV de **Contactos** / **Contacts**.
3. Si tenéis datos en columnas de seguimiento en Contactos que queréis conservar, copiadlos manualmente a filas nuevas en Acciones (una fila por touchpoint) o aceptad la pérdida.

## Hoja Acciones

Al arrancar la app nueva, si la fila 1 no coincide con `ACCIONES_HEADERS` en `config/settings.py`, la hoja se **vacía** y se reescribe la cabecera. Planificad el cambio en una ventana de mantenimiento.

## Contactos: columnas a eliminar en Google Sheets

Eliminar de la fila 1 (y datos asociados) estas 6 columnas:

- `fecha_ultimo_contacto`
- `persona_ultimo_contacto`
- `proxima_accion_fecha`
- `persona_proxima_accion`
- `proxima_accion_detalle`
- `fecha_veces_sin_respuesta`

**Conservar** el bloque Lead: `fuente_lead`, `lead_detalle`, `fecha_primer_contacto`, `persona_primer_contacto`, más el resto de `CANONICAL_COLUMNS`.

## Después del despliegue

- Ficha **Datos**: solo bloque **Lead**.
- Ficha **Históricos** → **Histórico de seguimiento comercial**: cada contacto realizado es una fila en Acciones.
- Filtros **Próxima acción** en la lista de contactos leen la próxima acción de la fila de Acciones más reciente con `proxima_accion_fecha` definida.
- Email masivo con «Registrar seguimiento» crea filas en Acciones (`origen_registro=email_batch`), sin parchear columnas de seguimiento en Contactos.

## Verificación rápida

1. Crear contacto y guardar Lead.
2. Añadir seguimiento en Históricos; comprobar fila en Acciones.
3. Filtrar lista por **Hoy** + persona según próxima acción del histórico.
4. Eliminar contacto y comprobar que desaparecen filas Acciones con ese `contact_id`.
