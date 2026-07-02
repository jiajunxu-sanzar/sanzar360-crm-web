# Plan de mejora de usabilidad — Página de Contactos

Fecha: 02/07/2026 · Estado: propuesta pendiente de aprobación

---

## 1. Cómo será el resultado final (tras completar todas las fases)

### 1.1 Estructura visual de la página

Todo queda organizado en bloques con borde (mismo estilo `st.container(border=True)` + design tokens que ya usa la ficha), en dos columnas como ahora (38% / 62%):

```
┌─ CONTACTOS ─────────────────────────────────────────────────────────────┐
│ ┌─ Columna izquierda ──────────────┐ ┌─ Columna derecha ──────────────┐ │
│ │ ┌─ BLOQUE: Próximas acciones ──┐ │ │ ┌─ BLOQUE: Ficha / Vista ────┐ │ │
│ │ │ Persona | Estado | Responsab.│ │ │ │                            │ │ │
│ │ │ [Anterior][Hoy][Mañana][Fut] │ │ │ │  · Si modo "Ver ficha":    │ │ │
│ │ └──────────────────────────────┘ │ │ │    ficha actual (datos +   │ │ │
│ │ ┌─ BLOQUE: Buscar ─────────────┐ │ │ │    históricos), sin cambios│ │ │
│ │ │ 🔍 texto | ⏬ filtros        │ │ │ │                            │ │ │
│ │ │ [Con sensores] [Mostrar      │ │ │ │  · Si modo "Ver" (tabla):  │ │ │
│ │ │  perdidos]                   │ │ │ │    tabla resumen de        │ │ │
│ │ └──────────────────────────────┘ │ │ │    sensores (ver 1.3)      │ │ │
│ │ ┌─ BLOQUE: Lista de contactos ─┐ │ │ └────────────────────────────┘ │ │
│ │ │ [Nuevo contacto]  [Ver][Ver  │ │ └────────────────────────────────┘ │
│ │ │  ficha] [Exportar ▾]         │ │                                    │
│ │ │ ● verde/amarillo + filas     │ │                                    │
│ │ └──────────────────────────────┘ │                                    │
│ └──────────────────────────────────┘                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Filtro y semáforo de sensores (en la lista)

- Botón **"Con sensores"** en el bloque Buscar: al activarlo, la lista solo muestra contactos con al menos un histórico de sensor abierto (`estado_cierre_sensor != "cerrado"`).
- Cada fila de la lista lleva indicador de color:
  - 🟢 **Verde**: sensores activos y **sin** incidencias abiertas.
  - 🟡 **Amarillo**: sensores activos **con** alguna incidencia abierta (`HistoricoIncidencias` con estado ≠ cerrada / sin `fecha_cierre`).
  - Sin indicador: contacto sin sensores activos.
  - 🔴 se mantiene para "Perdido" (comportamiento actual).

### 1.3 Vista "Ver" (tabla resumen)

Junto al selector de contacto habrá dos modos: **Ver** y **Ver ficha**.

- **Ver ficha**: abre la ficha completa actual (sin cambios funcionales).
- **Ver**: muestra en la columna derecha una tabla resumen de los contactos filtrados, con estas columnas:

| Contacto | Cantidad de sensores (+ SNs) | Último contacto | Próxima acción | Incidencias |
|---|---|---|---|---|
| Finca X | 3 — UC001, UC002, EM500-A1 | 15/06/2026 (llamada) | 05/07/2026 · Visita | 1 abierta |

- Fila **verde** si todo bien, **amarilla** si tiene incidencia abierta.
- Cada fila con botón "Ver ficha" que salta directo a la ficha de ese contacto.

### 1.4 Exportar

Botón **"Exportar ▾"** sobre la tabla resumen, con dos opciones:

- **Excel (.xlsx)**: la tabla de 1.3, con relleno condicional verde/amarillo por fila, cabecera con estilo Sanzar, columnas autoajustadas.
- **PDF**: misma tabla apaisada con ReportLab (mismo patrón que el export de inventario existente), filas coloreadas verde/amarillo.

El export respeta los filtros activos (lo que ves es lo que exportas). Nombre de archivo: `contactos_sensores_YYYYMMDD.xlsx|pdf`.

### 1.5 Datos: cómo se calcula cada columna

| Dato | Fuente |
|---|---|
| Sensores activos y SNs | `HistoricoSensores` abiertos → `parse_sensor_assets` / `sensor_asset_tokens` (history_service) |
| Cantidad de sensores | `count_sensor_assets(sensor_serial_number)` sumado por contacto |
| Último contacto | `latest_commercial_contact_row` (seguimiento comercial: fecha + canal) |
| Próxima acción | `enrich_contacts_with_proxima` (ya existe) |
| Incidencias | `HistoricoIncidencias` filtrado por `contact_id`, abiertas = sin cierre |

Todo se centraliza en un nuevo servicio `services/contact_sensor_overview.py` que devuelve un DataFrame único (una fila por contacto con semáforo), cacheado con la misma versión de caché de históricos ya existente. Un solo cálculo alimenta: filtro, colores, tabla "Ver" y exports.

---

## 2. Fases de implementación

### Fase 1 — Servicio de datos (base de todo)
- Crear `services/contact_sensor_overview.py`: `build_contact_sensor_overview(contacts_df, history, acciones_df) -> DataFrame` con columnas: `contact_id, nombre, num_sensores, sensor_sns, ultimo_contacto, ultimo_contacto_canal, proxima_accion_fecha, proxima_accion_detalle, incidencias_abiertas, semaforo (verde|amarillo|sin_sensores)`.
- Tests: `tests/test_contact_sensor_overview.py` (contacto sin sensores, con sensores sin incidencia, con incidencia abierta, incidencia cerrada no cuenta, sensores cerrados no cuentan).
- **Entregable**: servicio probado, aún sin cambios visibles.

### Fase 2 — Filtro "Con sensores" + semáforo en la lista
- Toggle "Con sensores" en el bloque Buscar (`pages/contacts.py`, `_render_contact_list`).
- Punto de color 🟢/🟡 por fila en `_render_contact_table` usando el semáforo de Fase 1 (colores de `semantic-success` / `semantic-warning` de design tokens).
- **Entregable**: ya puedes ver de un vistazo quién tiene sensores y su estado.

### Fase 3 — Vista "Ver" + botón "Ver ficha"
- Modo de vista en `session_state` (`contacts_view_mode: ficha|tabla`), botones "Ver" / "Ver ficha".
- Nueva tabla resumen en la columna derecha (componente `ui/components/contact_overview_table.py`) con filas coloreadas y botón "Ver ficha" por fila que fija `selected_contact_id` y cambia a modo ficha.
- **Entregable**: vista rápida operativa completa.

### Fase 4 — Exportar Excel y PDF
- Añadir `openpyxl` a `requirements.txt`.
- `services/contacts_export.py`: `build_overview_xlsx_bytes(...)` (openpyxl, relleno condicional) y `build_overview_pdf_bytes(...)` (ReportLab, patrón de `inventory_export.py`).
- Botones de descarga (`st.download_button`) sobre la tabla "Ver". Tests de export.
- **Entregable**: exportación con formato desde la vista filtrada.

### Fase 5 — Armonización en bloques
- Envolver en `st.container(border=True)` con títulos consistentes: Próximas acciones, Buscar, Lista de contactos, y el bloque derecho (ficha/tabla).
- Unificar espaciados y jerarquía tipográfica con los design tokens existentes; misma altura de panel en ambas columnas.
- **Entregable**: página visualmente coherente por bloques.

### Fase 6 — Mejoras propuestas (mi aportación, priorizadas)
1. **Rendimiento de la lista**: hoy se pinta un `st.button` por contacto (lento con cientos de filas). Paginación o `st.dataframe` con selección de fila → carga mucho más rápida. *Impacto alto.*
2. **Chips KPI en cabecera**: "X contactos · Y con sensores · Z con incidencia" clicables como filtros rápidos.
3. **Acción rápida desde la tabla "Ver"**: botón "Registrar acción" que abre el modal de seguimiento comercial sin entrar a la ficha (ahorra 3 clics por llamada).
4. **Orden por próxima acción**: ordenar la tabla por fecha de próxima acción vencida primero — convierte contactos en lista de trabajo diaria.
5. **Alertas de estancamiento integradas**: icono ⏰ en la fila cuando el contacto supera el umbral de días en su estado (servicio `estado_stagnation_alarms` ya existe, solo se ve en Alarmas).
6. **Enlace directo (deep-link)**: `?contact=<id>` en la URL para compartir fichas entre el equipo.
7. **Estado de suscripción en el semáforo**: aviso "caduca pronto" (`subscription_status_for_contact` ya existe) como tercer color/badge opcional.
8. **Búsqueda siempre visible**: eliminar el toggle 🔍 y dejar el campo fijo — un clic menos en la operación más frecuente.

---

## 3. Orden y dependencias

Fase 1 → bloquea 2, 3 y 4. Fase 5 es independiente (puede hacerse en paralelo). Fase 6 se prioriza tras validar 2–5 en uso real; recomiendo empezar por 6.1 y 6.4.

## 4. Criterios de aceptación globales

- Sin regresiones: los tests actuales de contactos siguen pasando; se añaden tests por fase.
- El semáforo, la tabla "Ver" y los exports muestran siempre los mismos números (una sola fuente de datos).
- Sin escrituras nuevas a Google Sheets: todo es lectura/presentación (cero riesgo sobre datos).
