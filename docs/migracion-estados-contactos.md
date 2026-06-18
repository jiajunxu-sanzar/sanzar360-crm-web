# Migración de estados comerciales (contactos)

Actualización del embudo comercial en la columna `estado` de la hoja de contactos.

## Nuevos estados (orden del embudo)

1. Nuevo contacto
2. Contacto inicial
3. Piloto aceptado
4. Contrato firmado
5. Onboarding
6. Piloto activo
7. Fin de piloto
8. Cliente
9. Perdido

## Mapeo sugerido en Google Sheets

| Valor antiguo en hoja | Nuevo valor |
|---|---|
| Nuevo Contacto | Nuevo contacto |
| En Contacto | Contacto inicial |
| En Negociación | Piloto aceptado |
| Cliente | Cliente |
| Perdido | Perdido |

Hasta completar la migración manual, la app reconoce los valores antiguos al leer y calcular alarmas.

## Campo `fecha_estado`

- Los contactos **nuevos** quedan en `Nuevo contacto` con `fecha_estado` = hoy.
- Al **cambiar** `estado` en la ficha, `fecha_estado` se actualiza automáticamente a hoy.
- Revisa contactos existentes con `fecha_estado` vacía: cambia el estado una vez o rellena la fecha manualmente para que las alarmas de estancamiento funcionen.

## Umbrales de alarma (Centro de alarmas → Embudo comercial)

| Estado | Días sin cambio |
|---|---:|
| Nuevo contacto | 14 |
| Contacto inicial | 21 |
| Piloto aceptado | 10 |
| Contrato firmado | 7 |
| Onboarding | 14 |
| Piloto activo | 60 |
| Fin de piloto | 7 |
| Cliente | (excluido) |
| Perdido | (excluido) |

Además, sigue apareciendo cualquier contacto del embudo con **próxima acción vencida** (`proxima_accion_fecha` hoy o anterior).

## Columna `responsable_cliente`

Al arrancar la app, si falta en la fila 1 de Contacts, se añade la columna **`responsable_cliente`** sin borrar filas existentes. Los contactos actuales quedan con valor vacío hasta que asignes un responsable en la ficha.

El desplegable se rellena con los nombres de la hoja **Usuarios CRM**. También puedes filtrar por responsable en la sección **Próximas acciones** de Contactos.
