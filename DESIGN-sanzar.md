---
extends: DESIGN-cal.md
colors:
  brand-accent: "#2D6A4F"
  brand-accent-hover: "#1E4D38"
  brand-accent-soft: "#EAF4EE"
  brand-accent-contrast: "#FFFFFF"
  semantic-success: "#4CAF78"
  semantic-warning: "#F5A623"
  semantic-error: "#E05252"
  semantic-info: "#4A90D9"
  semantic-purple: "#7C5CBF"
  bucket-past: "#B0B8C1"
  bucket-today: "#2D6A4F"
  bucket-future: "#6EB5E0"
components:
  button-primary:
    backgroundColor: "{colors.brand-accent}"
    textColor: "{colors.brand-accent-contrast}"
  button-primary-active:
    backgroundColor: "{colors.brand-accent-hover}"
    textColor: "{colors.brand-accent-contrast}"
  button-primary-strong:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
  button-primary-strong-active:
    backgroundColor: "{colors.primary-active}"
    textColor: "{colors.on-primary}"
---

## Sanzar CRM — capa de marca

Extiende [DESIGN-cal.md](DESIGN-cal.md) con la paleta Sanzar. Neutros, tipografía, espaciado y radios se heredan de Cal.com.

### Tipografía

Cal Sans no está disponible públicamente. En el CRM se usa **Inter** (400–700) con `letter-spacing: -0.02em` en títulos display, como sustituto documentado en DESIGN-cal.

### CTA dual

| Contexto | Componente | Color |
|---|---|---|
| CRM diario | `button-primary` | `brand-accent` (#2D6A4F) |
| Alta acción | `button-primary-strong` | Cal `primary` (#111111) |

Los modales de confirmación destructiva o acciones irreversibles usan la clase CSS `.crm-btn-strong` (negro Cal).

### Buckets — Próximas acciones

| Filtro | Token | Hex |
|---|---|---|
| Fecha anterior | `bucket-past` | #B0B8C1 |
| Hoy | `bucket-today` | #2D6A4F |
| Mañana / Fecha futura | `bucket-future` | #6EB5E0 |

### Semántica CRM

Los chips de estado derivan fondo/borde/texto desde un color base (`semantic-*`) mediante mezcla con blanco en `ui/design_tokens.py`.
