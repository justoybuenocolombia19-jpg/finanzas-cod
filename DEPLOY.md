# Publicar la app gratis, con cuentas por invitación

Esta guía tiene los pasos que **solo tú puedes hacer** (crear cuentas externas — nadie más
puede hacerlo por ti, ni siquiera un asistente). Todo lo demás ya está listo en el código.

Tiempo estimado: 20-30 minutos, una sola vez.

---

## 1 · Conectar tu terminal con GitHub

Ya tienes cuenta de GitHub y ya está instalado `gh` (la herramienta de línea de comandos).
Falta autorizarlo — es como iniciar sesión, así que lo haces tú, aprobando en el navegador:

```bash
gh auth login
```

Elige: **GitHub.com** → **HTTPS** → **Login with a web browser**. Te va a dar un código de
un solo uso y abrir el navegador — pégalo ahí y aprueba. Cuando termine, dime "listo" y
sigo yo con el repositorio y el primer `push`.

## 2 · Crear la base de datos en la nube (Turso, gratis)

1. Entra a **[turso.tech](https://turso.tech)** → *Sign up* (puedes usar tu cuenta de GitHub).
2. Crea una base de datos nueva (el plan gratis alcanza de sobra para este uso). Ponle un
   nombre, por ejemplo `finanzas-central`.
3. En el panel de esa base, copia dos cosas:
   - La **URL** (empieza con `libsql://...`).
   - Un **Auth Token** (créalo si no hay uno — botón *Create Token*).
4. Pégame los dos valores aquí en el chat (o dime que ya los tienes y los vamos a poner
   directo en Streamlit Cloud en el paso 4, sin pasar por el chat si prefieres más
   privacidad — cualquiera de las dos formas funciona).

## 3 · Publicar en Streamlit Community Cloud (gratis)

1. Entra a **[share.streamlit.io](https://share.streamlit.io)** → *Sign in* → **Continue with GitHub**
   (autoriza con tu cuenta de GitHub, ya creada en el paso 1).
2. **Create app** → **From an existing repo**.
3. Elige el repositorio (te aviso el nombre exacto cuando lo suba en el paso siguiente),
   rama `main`, archivo principal `app.py`.
4. Antes de darle *Deploy*, abre **Advanced settings → Secrets** y pega esto (con tus
   valores reales del paso 2):
   ```toml
   TURSO_DATABASE_URL = "libsql://tu-base.turso.io"
   TURSO_AUTH_TOKEN = "tu-token"
   ```
5. **Deploy**. En 1-2 minutos tienes tu link público (algo como
   `https://tu-app.streamlit.app`).

## 4 · Primer ingreso (quedas como administrador)

1. Abre el link de tu app. Verás la pantalla de **Crear cuenta**.
2. Regístrate con tu correo y una contraseña — como eres la primera persona, **no
   necesitas código de invitación** y quedas automáticamente como administrador.
3. Crea tu primer panel (Rayzen, Dropshipping, o el que quieras).
4. Para invitar a alguien más: menú **Paneles → Invitaciones → Generar código**, y
   compártele el código junto con el link de la app. Sin ese código, nadie más puede
   crear una cuenta.

---

## Qué hago yo mientras tanto

En cuanto me confirmes que hiciste el paso 1 (`gh auth login`), yo:
- Creo el repositorio en GitHub y subo el código (sin ningún dato tuyo, ya lo dejé fuera).
- Te doy el link exacto para el paso 3.
- Si me pasas la URL y el token de Turso, los reviso y confirmo que todo esté bien armado.

## Notas de seguridad

- Las contraseñas nunca se guardan en texto plano (se guardan con hash **bcrypt**).
- Después de 6 intentos fallidos de entrar, esa cuenta queda bloqueada 15 minutos.
- Cada quien ve **solo** sus propios paneles — están separados por completo, no por un
  simple filtro que se pueda olvidar: es una base de datos distinta por panel.
- Nadie puede crear una cuenta sin un código de invitación tuyo (excepto la primera vez).
- El archivo `.streamlit/secrets.toml` (si lo usas localmente) nunca se sube a GitHub.

## Actualizar la app después de un cambio

Cuando yo (o tú) hagamos cambios al código:
```bash
git add -A && git commit -m "lo que cambió" && git push
```
Streamlit Cloud redeploya solo en 1-2 minutos.
