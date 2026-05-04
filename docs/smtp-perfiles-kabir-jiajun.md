# Cómo obtener y configurar un perfil SMTP (ejemplo: Kabir)

En **Sanzar CRM Web**, el envío masivo desde la pestaña **Email** puede ir **por usuario**: cada comercial usa su propio buzón (`jiajun`, `kabir`, etc.) mediante **perfiles SMTP** y **rutas** enlazadas al `employee_id` o al nombre en la hoja **«Usuarios CRM»**.

Este documento resume **cómo conseguir** host, usuario y contraseña para un perfil tipo **Kabir** usando un correo **Google (Gmail o Google Workspace)**. Para **Jiajun** el procedimiento es el mismo: otra cuenta Google, otro bloque `SMTP_PROFILE_JIAJUN_*` o `[smtp_profiles.jiajun]`, y su ruta (`EMP…` o nombre). Otros proveedores (Microsoft 365, etc.) siguen la misma idea: servidor SMTP del proveedor + credenciales que permitan envío.

---

## 1. Qué vas a rellenar en la app

Para el perfil **`kabir`** (nombre interno; puede ser cualquier clave coherente):

| Campo       | Ejemplo típico (Gmail) |
|------------|-------------------------|
| **host**   | `smtp.gmail.com`        |
| **port**   | `587`                   |
| **user**   | Dirección completa del correo de Kabir (`kabir@tu-dominio.com` o `@gmail.com`) |
| **password** | Ver sección 2 (no es la contraseña normal de login) |
| **use_tls**| `true` (STARTTLS en el puerto 587) |

Equivale en **`.env`** a:

```bash
SMTP_PROFILE_KABIR_HOST=smtp.gmail.com
SMTP_PROFILE_KABIR_PORT=587
SMTP_PROFILE_KABIR_USER=kabir.correo@sanzar-group.com
SMTP_PROFILE_KABIR_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_PROFILE_KABIR_USE_TLS=true
```

O en **`.streamlit/secrets.toml` / Streamlit Cloud → Secrets**:

```toml
[smtp_profiles.kabir]
host = "smtp.gmail.com"
port = "587"
user = "kabir.correo@sanzar-group.com"
password = "xxxx xxxx xxxx xxxx"
use_tls = "true"
```

La app **no** envía con el perfil hasta que **rutas** ese usuario al slug `kabir`:

- Por `employee_id` (recomendado): el sufijo debe coincidir **exactamente** con la columna de «Usuarios CRM».

```toml
[smtp_route_by_employee]
EMP017 = "kabir"
```

(o en `.env`: `SMTP_ROUTE_BY_EMPLOYEE_EMP017=kabir`)

- O por nombre exacto:

```toml
[smtp_route_by_nombre]
"Kabir Caravotta" = "kabir"
```

Usuarios con rol **`sales`** no usan el SMTP “global” como sustituto si falta ruta o el perfil está incompleto. El comportamiento está en `app/smtp_profiles.py`; ver también `.env.example` y `.streamlit/secrets.example.toml`.

---

## 2. Gmail / Google Workspace: contraseña de aplicación

Google **no** permite usar la contraseña normal de la cuenta para SMTP de forma fiable; hay que usar una **contraseña de aplicación** (16 caracteres), salvo que tu organización use otro método (SSO estricto sin app passwords, SMTP relay interno, etc.).

### Pasos (cuenta personal `@gmail.com` o Workspace si el admin lo permite)

1. Inicia sesión en Google con la cuenta **de Kabir** (la misma que pondrás en **`user`**).
2. Activa la **verificación en dos pasos** (2FA) en la cuenta si aún no está activa.  
   - Resumen: [Verificación en dos pasos](https://support.google.com/accounts/answer/185839)
3. Crea una **contraseña de aplicación**:
   - Ve a la cuenta de Google → **Seguridad** → **Contraseñas de aplicaciones** (a veces aparece solo con 2FA activo).  
   - Enlace directo habitual: [Contraseñas de aplicaciones](https://myaccount.google.com/apppasswords)
   - Genera una contraseña para “Correo” / “Otro (personalizado)” → p. ej. nombre `Sanzar CRM`.
4. Google muestra **16 caracteres** (a menudo agrupados como `xxxx xxxx xxxx xxxx`). Eso es lo que copias en **`password`** del perfil (`SMTP_PROFILE_KABIR_PASSWORD` o TOML).

### Google Workspace (empresa)

Si el administrador del dominio ha **deshabilitado** las contraseñas de aplicación o exige otro flujo, Kabir no podrá usar SMTP con usuario/contraseña clásicos hasta que TI configure:

- relay SMTP autorizado por IP, o  
- OAuth/Gmail API por usuario (no está implementado así en esta app; aquí se usa **SMTP + app password**),

o un buzón SMTP del proveedor que sí dé credenciales SMTP.

---

## 3. Comprobar que el correo es el “From”

En el código, el remitente es el **`user`** del perfil seleccionado (`email_service.send_email` → cabecera **From**).

Tras configurar, abre **Email** en la app (contraseña CRM + desbloqueo de la pestaña si aplica): debería aparecer un texto del tipo *Enviando como **kabir@…** (perfil «kabir»)*.

---

## 4. Seguridad

- No subas `.env` ni `secrets.toml` con contraseñas al repositorio.
- En **Streamlit Cloud**, pega los secretos solo en el panel **Secrets** del dashboard.
- Si una contraseña de aplicación se filtra, **revócala** en Google y genera otra.

---

## 5. Referencias útiles

- [Gmail: configurar el cliente de correo SMTP](https://support.google.com/mail/answer/7126229) (host, puerto, TLS).
- Documentación del proyecto: `.env.example`, `.streamlit/secrets.example.toml`.
