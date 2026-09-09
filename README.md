# Actualizador de dólar (Bolivia)

Revisa la cotización del dólar paralelo en [dolarbluebolivia.click](https://www.dolarbluebolivia.click/)
y avisa por Telegram y correo cuando cambia. También genera una imagen
(`wallpaper/current.png`) con el precio actual para usar como fondo de
pantalla en Windows.

## Cómo funciona

- `check_dolar.py` lee `https://www.dolarbluebolivia.click/tasas.json` (el
  endpoint propio del sitio, permitido por su `robots.txt`), compara contra
  el último valor guardado en `data/last_rates.json` y, si cambió, manda los
  avisos.
- `.github/workflows/check-dolar.yml` ejecuta ese script cada 20 minutos en
  GitHub Actions (gratis) y guarda el resultado en el repo.
- `scripts/set_wallpaper.ps1` (en tu PC) descarga la última imagen generada
  y la pone de fondo de pantalla.

## Configuración (una sola vez)

### 1. Telegram

1. Abre Telegram, busca **@BotFather**, envía `/newbot` y sigue los pasos.
   Guarda el **token** que te da.
2. Busca **@userinfobot**, envíale cualquier mensaje y copia tu **Chat ID**.
3. Escríbele al menos un mensaje a tu bot nuevo (si no, no puede escribirte).

### 2. Correo (Gmail)

1. Activa la verificación en dos pasos en tu cuenta de Gmail.
2. Crea una "contraseña de aplicación" en
   https://myaccount.google.com/apppasswords (no uses tu contraseña normal).
3. Anota esa contraseña de 16 caracteres.

### 3. Secretos en GitHub

En el repo, ve a **Settings → Secrets and variables → Actions** y crea:

| Nombre                | Valor                                            |
|------------------------|---------------------------------------------------|
| `TELEGRAM_BOT_TOKEN`  | Token de @BotFather                               |
| `TELEGRAM_CHAT_ID`    | Tu Chat ID de @userinfobot                        |
| `GMAIL_USER`          | Tu correo de Gmail (el que envía el aviso)        |
| `GMAIL_APP_PASSWORD`  | La contraseña de aplicación de 16 caracteres      |
| `EMAIL_TO`            | Destinatarios separados por coma, ej: `lechugaspro21@gmail.com, centrodecomprastja@gmail.com` |

Puedes omitir el grupo de Telegram o el de correo si solo quieres uno de los
dos canales; el script salta el que no tenga sus variables configuradas.

### 4. Fondo de pantalla en Windows (opcional)

Una vez que el repo esté en GitHub y el workflow haya corrido al menos una
vez (para que exista `wallpaper/current.png`), corre en PowerShell:

```powershell
powershell -File scripts\install_wallpaper_task.ps1 -ImageUrl "https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/wallpaper/current.png"
```

Esto registra una tarea programada de Windows que actualiza el fondo de
pantalla cada 20 minutos. Para quitarla:

```powershell
Unregister-ScheduledTask -TaskName ActualizadorDolarWallpaper
```

## Probar en tu propia PC (sin GitHub Actions)

```powershell
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="..."
python check_dolar.py
```
