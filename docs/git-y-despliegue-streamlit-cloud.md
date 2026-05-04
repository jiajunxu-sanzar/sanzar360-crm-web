# Git: push habitual y despliegue en Streamlit Community Cloud

Guía rápida para subir cambios a GitHub y publicar la app en [Streamlit Community Cloud](https://streamlit.io/cloud).

---

## Parte 1 — Cada vez que quieras hacer push

Trabaja siempre desde la raíz del repo (donde está `streamlit_app.py`).

### 1. Ver qué ha cambiado

```bash
git status
```

Comprueba que **no** aparezcan archivos sensibles (`.env`, JSON de credenciales, `secrets.toml`, `.venv`). Si aparecen, no los añadas; revisa `.gitignore`.

### 2. Añadir cambios

Solo lo que quieras incluir en el commit:

```bash
git add .
```

O archivos concretos:

```bash
git add ruta/al/archivo.py
```

### 3. Crear el commit

Mensaje claro (qué cambió y por qué):

```bash
git commit -m "Descripción breve del cambio"
```

Si Git dice que no hay nada que commitear, no hace falta push.

### 4. Bajar posibles cambios remotos (recomendado si trabajas en varios sitios)

```bash
git pull --rebase origin main
```

Si tu rama principal se llama `master`, sustituye `main` por `master`.

### 5. Subir a GitHub

```bash
git push origin main
```

La primera vez en un ordenador puede pedirte login (token HTTPS o SSH).

### Resumen en una línea (cuando ya estás seguro)

```bash
git status && git add . && git commit -m "Tu mensaje" && git pull --rebase origin main && git push origin main
```

---

## Parte 2 — Próximos pasos: despliegue en Streamlit Community Cloud

### Paso A — Cuenta y acceso

1. Cuenta en [streamlit.io](https://streamlit.io) (puede enlazarse con GitHub).
2. Entra en el [dashboard de apps](https://share.streamlit.io/).

### Paso B — Crear la app enlazada al repo

1. **New app** (o **Create app**).
2. **Repository**: elige tu repo de GitHub y la **rama** (normalmente `main`).
3. **Main file path**: `streamlit_app.py` (está en la raíz del proyecto).
4. **App URL** (subdominio): elige un nombre único si te lo pide.
5. **Deploy**.

La primera compilación puede tardar unos minutos.

### Paso C — Secretos (obligatorio para Sheets / Google)

En la app → **Settings** (⚙️) → **Secrets**.

Pega un TOML con al menos:

- `GOOGLE_SHEET_ID`
- `GOOGLE_WORKSHEET_NAME` (si no usas el valor por defecto `Contacts`)
- Bloque **`[gcp_service_account]`** con los mismos campos que tu JSON de cuenta de servicio (copia del fichero que **no** subes a GitHub).

La app ya prioriza `st.secrets` sobre el `.env` local (`app/secrets.py`). Con eso no necesitas subir `config/credentials/` al repo.

Guarda y **Reboot app** si cambias los secretos.

### Paso D — Comprobar que el build es correcto

1. Abre la **URL pública** de la app.
2. Si falla, en el dashboard mira **Manage app** → **Logs** para ver el error (dependencias, secretos faltantes, etc.).

### Paso E — Flujo de trabajo día a día

1. Cambias código en local → `commit` → `push` a GitHub.
2. En Streamlit Cloud, la app **suele redeployarse sola** al detectar push en la rama conectada (según configuración del proyecto).
3. Si no se actualiza: **Manage app** → **Reboot** o **Deploy** de nuevo.

### Referencia oficial

- [Deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

---

## Recordatorio de seguridad

- No subas `.env`, JSON de service account ni `.streamlit/secrets.toml` al repo.
- Rota credenciales si alguna vez se exponen.
