# Roadmap de ejecución (fases)

## Sprint 1 (quick wins)
- Instrumentación baseline completa.
- Caché por dominio (`contacts`/`history`).
- Escrituras incrementales de históricos.
- Corrección de estados UI con `session_state`.

## Sprint 2 (rendimiento)
- Índices cacheados para búsqueda de activos.
- Optimizaciones de filtros/fechas vectorizadas.
- Reducción de reruns no necesarios.

## Sprint 3 (mantenibilidad)
- Dividir `pages/contacts.py` en submódulos.
- Estandarizar manejo de errores y logs.
- Aumentar cobertura de tests.

## KPIs objetivo
- Reducir latencia p95 de guardado de histórico.
- Reducir tiempo p95 de render de contactos.
- Reducir llamadas a Sheets por operación.
- Reducir regresiones en navegación/modales.
