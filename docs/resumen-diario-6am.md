# Resumen diario del CRM a las 6:00

Cada día a las 6:00 (hora de Madrid) sale un correo desde
`jiajun.xu@sanzar-group.com` a:

- carla.moreno@sanzar-group.com
- david.ortiz@sanzar-group.com
- info@sanzar-group.com
- jiajun.xu@sanzar-group.com

## Qué lleva el correo

Cuatro bloques, en este orden:

1. **Próxima acción · hoy** — próximas acciones del seguimiento comercial con
   fecha de hoy. Por cada una: cliente, detalle, encargado, canal y la fecha
   del último contacto.
2. **Tareas · hoy** — tareas del histórico con fecha límite hoy y estado
   distinto de «Terminado». Cliente, título y notas, encargado y tipo.
3. **Seguimiento comercial atrasado** — próximas acciones con fecha anterior a
   hoy que siguen pendientes, con los días de retraso.
4. **Tareas atrasadas** — tareas vencidas y sin terminar.

Una próxima acción se considera pendiente mientras la **última** fila de
seguimiento comercial de ese contacto siga apuntando a una fecha pasada. En
cuanto alguien registra un contacto nuevo, esa fila deja de ser la última y el
pendiente desaparece solo; no hay que marcar nada a mano.

Los días sin nada también se envía el correo, con los bloques vacíos. Para no
enviarlo esos días, poner `DAILY_DIGEST_SEND_IF_EMPTY=false`.

## Cómo se ejecuta

Streamlit Cloud no ejecuta tareas programadas, así que el envío lo dispara
GitHub Actions desde este mismo repositorio:

- Workflow: `.github/workflows/daily-digest.yml`
- Script: `scripts/send_daily_digest.py`
- Lógica y maquetación del correo: `services/daily_digest.py`
- Dependencias del cron: `requirements-cron.txt`

El cron corre con cuatro paquetes (pandas, gspread, google-auth,
python-dotenv), no con todos los de la app. Si alguien añade a esa cadena
de imports algo pesado (Streamlit, geopy, folium…) el envío reventaría a
las 6:00 sin que nadie se entere, así que `tests/test_daily_digest_dependencias.py`
lo vigila y el workflow comprueba los imports antes de intentar enviar.
Cuando haga falta una dependencia nueva, mira primero si el import se
puede hacer perezoso (dentro de la función) antes de engordar el cron.

GitHub Actions solo entiende UTC, así que el workflow se dispara a las **04:00
y 05:00 UTC** y el primer paso corta la ejecución que no toque: en horario de
verano vale la de 04:00 y en invierno la de 05:00. El correo sale siempre a
las 6:00 de Madrid sin tocar nada en los cambios de hora.

## Configuración en GitHub (una sola vez)

En `https://github.com/jiajunxu-sanzar/sanzar360-crm-web` →
**Settings → Secrets and variables → Actions**.

### Pestaña «Secrets» → New repository secret

| Nombre | Valor |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Contenido completo del JSON de la cuenta de servicio (`config/credentials/service_account.json`), pegado tal cual |
| `GOOGLE_SHEET_ID` | El mismo valor que `GOOGLE_SHEET_ID` del `.env` |
| `SMTP_PROFILE_JIAJUN_HOST` | El mismo valor que en el `.env` |
| `SMTP_PROFILE_JIAJUN_PORT` | El mismo valor que en el `.env` (normalmente `587`) |
| `SMTP_PROFILE_JIAJUN_USER` | `jiajun.xu@sanzar-group.com` |
| `SMTP_PROFILE_JIAJUN_PASSWORD` | Contraseña de aplicación de esa cuenta (no la contraseña normal) |

### Pestaña «Variables» → New repository variable (opcional)

Solo si algún día hay que cambiarlos sin tocar el código:

| Nombre | Valor por defecto si no se crea |
|---|---|
| `DAILY_DIGEST_RECIPIENTS` | Las cuatro direcciones de arriba, separadas por coma |
| `GOOGLE_WORKSHEET_NAME` | `contacts` |
| `GOOGLE_ACTIVITY_LOG_WORKSHEET_NAME` | `Acciones` |

La cuenta de servicio necesita permiso de lectura sobre el Google Sheet; es la
misma que ya usa la app, así que si el CRM lee, esto también.

## Probarlo sin esperar a mañana

En GitHub → pestaña **Actions** → workflow «Resumen diario CRM» → **Run
workflow**. Ahí se puede marcar `dry_run` para generarlo sin enviar nada, o
poner una fecha concreta en `fecha` (formato `DD/MM/AAAA`) para ver qué habría
salido ese día.

En local, con el `.env` del proyecto:

```bash
python3 -m scripts.send_daily_digest --dry-run
python3 -m scripts.send_daily_digest --dry-run --fecha 15/09/2026
python3 -m scripts.send_daily_digest --to marco.ruano@sanzar-group.com
```

El `--dry-run` deja el correo maquetado en `daily_digest_preview.html` para
abrirlo en el navegador.

## Si un día no llega el correo

1. GitHub → **Actions** → «Resumen diario CRM»: mirar la última ejecución. Las
   ejecuciones que se cortan por hora son normales, salen en verde y sin pasos.
2. Errores típicos:
   - `falta GOOGLE_SHEET_ID` → el secret no está creado.
   - `ERROR leyendo Google Sheets` → la cuenta de servicio perdió acceso al
     Sheet, o el JSON del secret está mal pegado.
   - `el perfil SMTP «jiajun» no está configurado` → faltan los secrets
     `SMTP_PROFILE_JIAJUN_*`.
   - `no pudo autenticarse` → la contraseña de aplicación de Gmail caducó o se
     revocó; hay que generar otra y actualizar el secret.
