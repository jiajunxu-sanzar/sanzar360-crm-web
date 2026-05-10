# Inventory Roadmap

## Objetivo
Priorizar mejoras del modulo de Inventario para hacerlo mas robusto, operable y escalable en flujos diarios.

## Funciones recomendadas
- Historial de cambios por activo (auditoria de quien, que y cuando).
- Estados de ciclo de vida del activo (`stock`, `asignado`, `mantenimiento`, `retirado`).
- Reglas de integridad para asociaciones UC501-SIM-Probe con validacion server-side.
- Importacion y exportacion CSV con prevalidacion y reporte de errores.
- Deteccion de duplicados por serial/modelo con asistente de consolidacion.
- Filtros avanzados y vistas guardadas por usuario.
- Alertas de mantenimiento, calibracion y garantia por fechas.
- Soft-delete y archivado de activos en lugar de borrado duro.
- Paginacion/virtualizacion para crecer a volumen alto sin degradacion de UX.

## Prioridad sugerida
1. Integridad de datos y auditoria.
2. Import/export y calidad de datos.
3. Productividad de busqueda y filtros.
4. Escalabilidad de tabla y rendimiento.
