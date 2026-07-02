# Prompts de implementación — Mejora de usabilidad de Contactos

5 prompts autocontenidos, uno por fase. Pásalos en orden (cada uno asume completado el anterior). Contexto común: app Streamlit con datos en Google Sheets, repo `sanzar-crm-web`.

---

## PROMPT 1 — Servicio de datos: resumen de sensores por contacto

```
Trabaja en el repo sanzar-crm-web (app Streamlit + Google Sheets). Crea un nuevo servicio de solo lectura que consolide, por contacto, su situación de sensores, incidencias, último contacto y próxima acción. NO modifiques ninguna página todavía y NO escribas nada en Google Sheets.

CONTEXTO DEL CÓDIGO EXISTENTE (úsalo, no lo reimplementes):
- services/history_service.py: HISTORY_SPECS define las hojas "sensores" (HistoricoSensores) e "incidencias" (HistoricoIncidencias). Un histórico de sensor está ABIERTO cuando str(row["estado_cierre_sensor"]).strip().lower() != "cerrado". Funciones útiles ya existentes: parse_sensor_assets(sensor_serial_number), count_sensor_assets(sensor_serial_number), sensor_asset_tokens(sensor_serial_number) (devuelve tokens tipo "uc501-UC001").
- HistoricoIncidencias tiene columnas: contact_id, fecha_apertura, fecha_cierre, tipo_incidencia, estado, prioridad, sensor_serial_number, detalle, resolucion. Una incidencia está ABIERTA cuando fecha_cierre está vacía Y estado (normalizado a lower/strip) no es "cerrada" ni "cerrado" ni "resuelta".
- services/contact_proxima_index.py: enrich_contacts_with_proxima(contacts_df, acciones_df) añade proxima_accion_fecha, persona_proxima_accion, proxima_accion_detalle, proxima_accion_canal; latest_commercial_contact_row(...) da la última acción comercial (usa fecha_contacto y hora_contacto del histórico de seguimiento_comercial; ese df se carga con load_acciones_cached de app/cache.py).
- app/cache.py: load_history_rows_cached(kind, version) devuelve las filas cacheadas de un histórico; el "version" que usa la app es st.session_state["history_cache_version"].
- Los contactos tienen columnas canónicas en config/settings.py (CANONICAL_COLUMNS), clave primaria contact_id, y campo nombre.
- Fechas en las hojas en formato dd/mm/YYYY.

CREA services/contact_sensor_overview.py con:

1. build_contact_sensor_overview(contacts_df, sensor_rows: list[dict], incidencia_rows: list[dict], acciones_df) -> pd.DataFrame
   Una fila por contacto de contacts_df, columnas:
   - contact_id, nombre
   - num_sensores: suma de count_sensor_assets() de todas sus filas de HistoricoSensores ABIERTAS
   - sensor_sns: string con los tokens de sensor_asset_tokens() de esas filas abiertas, únicos, separados por ", "
   - ultimo_contacto: fecha dd/mm/YYYY de la última acción comercial (vacío si no hay)
   - ultimo_contacto_canal: canal de esa acción (vacío si no hay)
   - proxima_accion_fecha, proxima_accion_detalle, persona_proxima_accion (de enrich_contacts_with_proxima)
   - incidencias_abiertas: int, nº de incidencias ABIERTAS del contacto
   - semaforo: "verde" si num_sensores > 0 e incidencias_abiertas == 0; "amarillo" si num_sensores > 0 e incidencias_abiertas > 0; "sin_sensores" si num_sensores == 0

2. Un wrapper cacheado en app/cache.py siguiendo el patrón existente:
   @st.cache_data(ttl=300, show_spinner=False)
   def load_contact_sensor_overview_cached(version: int = 0) -> pd.DataFrame
   que cargue contactos, sensores, incidencias y acciones con los loaders cacheados existentes y llame a build_contact_sensor_overview.

3. Tests en tests/test_contact_sensor_overview.py (pytest, sin tocar red: construye DataFrames/listas en memoria como hacen los tests existentes, mira tests/conftest.py):
   - contacto sin históricos → semaforo "sin_sensores", num_sensores 0
   - contacto con histórico de sensor abierto sin incidencias → "verde", num_sensores y sensor_sns correctos
   - contacto con sensor abierto + incidencia abierta → "amarillo", incidencias_abiertas == 1
   - incidencia con fecha_cierre o estado "cerrada" NO cuenta
   - histórico de sensor con estado_cierre_sensor "cerrado" NO suma sensores
   - ultimo_contacto toma la acción comercial más reciente
   - contacts_df vacío → DataFrame vacío con las columnas correctas

Ejecuta la suite completa de pytest y asegúrate de que todo pasa. Sigue el estilo del código existente (type hints, from __future__ import annotations, funciones puras).
```

---

## PROMPT 2 — Filtro "Con sensores" + semáforo en la lista de contactos

```
Trabaja en el repo sanzar-crm-web. Ya existe services/contact_sensor_overview.py con build_contact_sensor_overview(...) y el loader cacheado load_contact_sensor_overview_cached(version) en app/cache.py, que devuelve por contacto: num_sensores, sensor_sns, incidencias_abiertas y semaforo ("verde" | "amarillo" | "sin_sensores"). Ahora intégralo en la lista de contactos.

ARCHIVO PRINCIPAL: pages/contacts.py
- _render_contact_list(df) (≈ línea 374): renderiza toggle "Mostrar perdidos", búsqueda, filtros y llama a _render_contact_table(filtered, selected_contact_id).
- _render_contact_table(filtered, selected_contact_id) (≈ línea 488): pinta una cabecera HTML con clases sanzar-contact-table / sanzar-contact-row y una fila por contacto; la fila seleccionada se pinta como markdown HTML y el resto como st.button con key f"contact_row_{contact_id}"; los perdidos llevan prefijo "🔴".

CAMBIOS:

1. Filtro "Con sensores":
   - En _render_contact_list, junto al toggle "Mostrar perdidos", añade st.toggle("Con sensores", key="contacts_only_with_sensors") (define la constante CONTACTS_ONLY_WITH_SENSORS_KEY siguiendo el patrón de CONTACTS_SHOW_LOST_KEY).
   - Carga el overview: overview = load_contact_sensor_overview_cached(st.session_state.get("history_cache_version", 0)).
   - Si el toggle está activo, filtra `filtered` dejando solo contact_id cuyo semaforo sea "verde" o "amarillo".
   - Aplícalo junto al resto de filtros, antes de reset_index, de modo que el contador "N contactos encontrados" lo refleje.

2. Semáforo por fila en _render_contact_table:
   - Pasa a la función un dict contact_id -> semaforo (o el overview) desde _render_contact_list.
   - Prefija la etiqueta de cada fila: "🟢 " si semaforo == "verde", "🟡 " si "amarillo", nada si "sin_sensores". Mantén el prefijo "🔴" de perdidos con prioridad (un perdido muestra solo 🔴).
   - Aplica lo mismo a la fila seleccionada (la variante HTML markdown).

3. Tests: añade tests/test_contacts_sensor_filter.py cubriendo la función de filtrado por semáforo (extrae la lógica de filtrado a una función pura, p. ej. filter_by_sensor_overview(filtered, overview) en el propio pages/contacts.py o en el servicio, para poder testearla sin Streamlit).

NO cambies ningún otro comportamiento (búsqueda, filtros, selección, creación de contactos). Ejecuta pytest completo al terminar.
```

---

## PROMPT 3 — Modo "Ver" (tabla resumen) y botón "Ver ficha"

```
Trabaja en el repo sanzar-crm-web. La página pages/contacts.py tiene un layout de dos columnas (render(), ≈ línea 333): izquierda (38%) _render_contact_list(df), derecha (62%) _render_contact_detail(df, selected_id) o un st.info si no hay selección. Existe load_contact_sensor_overview_cached(version) en app/cache.py con columnas por contacto: contact_id, nombre, num_sensores, sensor_sns, ultimo_contacto, ultimo_contacto_canal, proxima_accion_fecha, proxima_accion_detalle, incidencias_abiertas, semaforo.

OBJETIVO: añadir un modo de vista "tabla resumen" en la columna derecha, conmutable con la ficha actual.

CAMBIOS:

1. Estado de modo de vista:
   - Clave de sesión contacts_view_mode con valores "ficha" (default) y "tabla".
   - En _render_contact_list, encima del listado (junto al botón "Nuevo contacto"), añade dos botones en una fila st.columns: "Ver" (pone modo "tabla") y "Ver ficha" (pone modo "ficha"). Marca el activo con type="primary" (mismo patrón que los botones de bucket en _render_next_action_strip, ≈ línea 1307).

2. Componente nuevo ui/components/contact_overview_table.py:
   - render_contact_overview_table(overview_df, on_select_key_prefix="overview_ficha_") que pinta una tabla HTML con las clases CSS del proyecto (mira sanzar-contact-table en el CSS global y ui/design_tokens.py; usa var(--ui-semantic-success) y var(--ui-semantic-warning) o los estilos de ui/palette.py STATUS_SUCCESS/STATUS_WARNING para el fondo de fila).
   - Columnas visibles: "Contacto" (nombre), "Sensores" (num_sensores + salto con los SNs: "3 — uc501-UC001, em500-A1"), "Último contacto" (fecha + canal), "Próxima acción" (fecha + detalle), "Incidencias" ("2 abiertas" o "—").
   - Fondo de fila verde suave si semaforo == "verde", amarillo suave si "amarillo", neutro si "sin_sensores".
   - A la derecha de cada fila, un st.button("Ver ficha", key=f"{prefix}{contact_id}"). Al pulsarlo: st.session_state["selected_contact_id"] = contact_id; st.session_state["contacts_view_mode"] = "ficha"; st.rerun().
   - Escapa todo texto con html.escape (como hace _render_contact_table).

3. Integración en render() de pages/contacts.py:
   - Si contacts_view_mode == "tabla": en la columna derecha renderiza el componente con el overview RESTRINGIDO a los contactos actualmente filtrados en la lista izquierda (haz que _render_contact_list devuelva también los contact_id filtrados, o guarda esa lista en session_state).
   - Si es "ficha": comportamiento actual sin cambios.
   - Ordena la tabla por proxima_accion_fecha ascendente (vencidas primero, vacías al final), parseando dd/mm/YYYY.

4. Tests: tests/test_contact_overview_table.py para la lógica pura (orden por próxima acción, mapeo semáforo → clase CSS, formato de la celda de sensores). Sigue el patrón de los tests existentes de componentes (p. ej. tests/test_history_cards.py).

No rompas la navegación existente (selected_contact_id, _clear_contact_overlay_state). Ejecuta pytest completo al terminar.
```

---

## PROMPT 4 — Exportar la tabla resumen a Excel y PDF

```
Trabaja en el repo sanzar-crm-web. Existe una vista "tabla resumen" de contactos (ui/components/contact_overview_table.py) alimentada por un DataFrame overview con columnas: contact_id, nombre, num_sensores, sensor_sns, ultimo_contacto, ultimo_contacto_canal, proxima_accion_fecha, proxima_accion_detalle, incidencias_abiertas, semaforo ("verde"|"amarillo"|"sin_sensores"). Ya hay un export PDF de referencia en services/inventory_export.py (función build_association_map_pdf_bytes, ReportLab: SimpleDocTemplate + Table + TableStyle, A4 apaisado, import de reportlab dentro de la función). reportlab ya está en requirements.txt.

OBJETIVO: exportar la vista filtrada a .xlsx y .pdf con filas coloreadas.

CAMBIOS:

1. Añade openpyxl a requirements.txt.

2. Crea services/contacts_export.py con dos funciones puras (bytes de entrada/salida, sin Streamlit):
   - build_overview_xlsx_bytes(overview_df, exported_at: datetime | None = None) -> tuple[bytes, str]
     · Hoja "Contactos con sensores". Fila 1: título "Contactos — Sensores e incidencias" + fecha de export dd/mm/YYYY HH:MM. Fila 2 cabeceras: Contacto | Cantidad de sensores | SNs | Último contacto | Próxima acción | Incidencias.
     · "Próxima acción" = fecha + " · " + detalle si hay detalle. "Último contacto" = fecha + " (" + canal + ")" si hay canal.
     · Relleno de TODA la fila: verde claro (p. ej. C6F6D5) si semaforo == "verde", amarillo claro (FEF3C7) si "amarillo", sin relleno si "sin_sensores". Cabecera con fondo verde oscuro Sanzar (#2D6A4F) y letra blanca en negrita. Bordes finos, anchos de columna razonables (ajusta por longitud máxima con tope 60), freeze panes en la fila de datos.
     · Devuelve (bytes, filename) con filename "contactos_sensores_YYYYMMDD.xlsx".
   - build_overview_pdf_bytes(overview_df, exported_at=None) -> tuple[bytes, str]
     · Mismo contenido y colores por fila, siguiendo el patrón exacto de build_association_map_pdf_bytes (A4 landscape, Paragraph para celdas largas, TableStyle con BACKGROUND por fila según semáforo). Filename "contactos_sensores_YYYYMMDD.pdf".

3. UI: en la vista "tabla" de pages/contacts.py, encima de la tabla añade una fila con dos st.download_button: "Exportar Excel" y "Exportar PDF", que generen los bytes A PARTIR DEL MISMO DataFrame filtrado/ordenado que se está mostrando (lo que ves es lo que exportas). mime types: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet y application/pdf.

4. Tests en tests/test_contacts_export.py (mira tests/test_inventory_export.py como referencia):
   - el xlsx se abre con openpyxl y tiene las cabeceras y nº de filas esperado; una fila "verde" tiene el fill C6F6D5 y una "amarillo" FEF3C7
   - el pdf devuelve bytes no vacíos que empiezan por %PDF
   - filenames con la fecha del parámetro exported_at

Ejecuta pytest completo al terminar.
```

---

## PROMPT 5 — Armonización visual en bloques

```
Trabaja en el repo sanzar-crm-web, página pages/contacts.py (Streamlit). La página tiene: cabecera de "Próximas acciones" (_render_next_action_strip, ≈ línea 1307: selectores de persona/estado/responsable + 4 botones bucket), zona de búsqueda/filtros (subheader "Buscar" + toggles + botones 🔍/⏬ en _render_contact_list, ≈ línea 374), lista de contactos (_render_contact_table dentro de st.container(height=..., border=True)), y columna derecha con la ficha (_render_contact_detail) o la tabla resumen (contacts_view_mode == "tabla"). La ficha ya agrupa secciones con st.container(border=True) (ver _render_form_sections ≈ línea 825). El design system está en ui/design_tokens.py (CSS variables --ui-*), ui/palette.py y ui/theme.py.

OBJETIVO: organizar la página en bloques visuales consistentes SIN cambiar ninguna funcionalidad ni ninguna key de session_state.

CAMBIOS:

1. Columna izquierda — tres bloques, cada uno envuelto en st.container(border=True) con un título propio via st.markdown("##### ..."):
   - Bloque "Próximas acciones": todo el contenido actual de _render_next_action_strip.
   - Bloque "Buscar": toggles "Mostrar perdidos" / "Con sensores", botón 🔍, campo de búsqueda y filtros desplegables.
   - Bloque "Contactos": botón "Nuevo contacto", botones "Ver"/"Ver ficha", botones de export si aplica, contador "N contactos encontrados" y la tabla/lista.

2. Columna derecha — un bloque contenedor genérico st.container(border=True) que englobe tanto la ficha como la tabla resumen, con cabecera propia: nombre del contacto seleccionado (modo ficha) o "Vista resumen — N contactos" (modo tabla).

3. Consistencia:
   - Mismos niveles de título en los cuatro bloques (#####), mismo gap ("small") en las filas internas.
   - Elimina st.subheader("Buscar") suelto y cualquier separador redundante que quede duplicado al introducir los contenedores.
   - Si hace falta CSS (padding interno de los contenedores, margen entre bloques), añádelo en ui/design_tokens.py usando las variables --ui-* existentes; no hardcodees colores.
   - Revisa que las alturas CONTACT_LIST_PANEL_HEIGHT_* sigan dejando la lista usable dentro del nuevo contenedor (ajusta las constantes si el doble borde reduce el alto útil).

4. Verificación:
   - Ejecuta pytest completo: los tests de navegación y contactos existentes deben seguir pasando sin modificarlos (si alguno depende de estructura de render, ajusta el test SOLO si el cambio es puramente de layout).
   - Arranca la app (streamlit run streamlit_app.py) y comprueba manualmente: seleccionar contacto, crear contacto, buscar, filtrar, cambiar Ver/Ver ficha, exportar.

Restricción estricta: cero cambios de lógica de datos, cero cambios en keys de session_state, cero escrituras nuevas a Google Sheets.
```
