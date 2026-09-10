# Actualizador de dólar (Bolivia)

Revisa la cotización del dólar en dos fuentes independientes —
[dolarbluebolivia.click](https://www.dolarbluebolivia.click/) (paralelo/blue)
y el [Banco Central de Bolivia](https://www.bcb.gob.bo/) (oficial) — y avisa
por Telegram y correo cuando cambia alguna. También genera una imagen
(`wallpaper/current.png`) con el precio actual para usar como fondo de
pantalla en Windows.

## Cómo funciona

- `check_dolar.py` lee `https://www.dolarbluebolivia.click/tasas.json` (el
  endpoint propio del sitio, permitido por su `robots.txt`) y además lee el
  tipo de cambio oficial directamente de la portada de `bcb.gob.bo` (el BCB
  no tiene un endpoint JSON público, así que se extrae del HTML). Compara
  ambas fuentes contra el último valor guardado en `data/last_rates.json` y,
  si algo cambió, manda los avisos. Si el BCB falla o cambia su HTML, esa
  fuente se salta sin romper la corrida (sigue funcionando solo con
  dolarbluebolivia.click).
- `.github/workflows/check-dolar.yml` ejecuta ese script en GitHub Actions
  (gratis) y guarda el resultado en el repo. La cadencia real (cada 15 min)
  la maneja un **cron externo** (ver sección más abajo) porque el cron
  interno de GitHub (`schedule`) no es puntual para intervalos cortos en
  repos con poco tráfico — se observó en la práctica que llegaba a
  espaciarse más de 4 horas en vez de cada 20 min. El `schedule` interno
  queda solo como respaldo.
- `scripts/set_wallpaper.ps1` (en tu PC) descarga la última imagen generada
  y la pone de fondo de pantalla, cada 15 minutos.

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
powershell -File scripts\install_wallpaper_task.ps1 -Repo "TU_USUARIO/TU_REPO"
```

Esto registra una tarea programada de Windows (`ActualizadorDolarWallpaper`)
que cada 15 minutos descarga la última imagen y la pone de fondo de
pantalla (guardada en `Imágenes\ActualizadorDolarBolivia`). Para quitarla:

```powershell
Unregister-ScheduledTask -TaskName ActualizadorDolarWallpaper
```

### 5. Cron externo (para que la actualización sea puntual)

El `schedule` interno de GitHub Actions no es confiable para intervalos
cortos (ver nota más arriba), así que la cadencia real la maneja un cron
externo gratuito, [cron-job.org](https://cron-job.org), que llama a la API
de GitHub cada 15 minutos para forzar la corrida:

1. **Token de GitHub** (Settings → Developer settings → Fine-grained
   tokens → Generate new token): acceso solo a este repositorio, permiso
   **Actions: Read and write** (es el único permiso necesario).
2. **Cronjob en cron-job.org**, cada 15 minutos, con:
   - URL: `https://api.github.com/repos/TU_USUARIO/TU_REPO/actions/workflows/check-dolar.yml/dispatches`
   - Método: `POST`
   - Headers: `Authorization: Bearer TU_TOKEN`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"ref":"main"}`

Si alguna vez cambian el token o quieren migrar a otro servicio de cron,
esta es toda la configuración necesaria — no depende de nada más en el
repo.

## Poner el fondo de pantalla en OTRA computadora (sin repetir todo lo demás)

El aviso y la generación de la imagen ya corren centralizados en GitHub
Actions (una sola vez para todas tus PCs). Para que una segunda
computadora con Windows también muestre el fondo actualizado, solo hace
falta el paso 4 de arriba en esa máquina — no hace falta Python, ni git,
ni repetir la configuración de Telegram/correo.

**En la otra laptop, en PowerShell** (no requiere permisos de administrador):

```powershell
# 1. Crea una carpeta para los scripts y descarga los dos que hacen falta
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\ActualizadorDolarBolivia" | Out-Null
cd "$env:USERPROFILE\ActualizadorDolarBolivia"
Invoke-WebRequest "https://raw.githubusercontent.com/guevarakruz-code/actualizador-de-dolar-bolivia/main/scripts/set_wallpaper.ps1" -OutFile "set_wallpaper.ps1"
Invoke-WebRequest "https://raw.githubusercontent.com/guevarakruz-code/actualizador-de-dolar-bolivia/main/scripts/install_wallpaper_task.ps1" -OutFile "install_wallpaper_task.ps1"

# 2. Instala la tarea programada (queda actualizando el fondo cada 15 min)
powershell -ExecutionPolicy Bypass -File install_wallpaper_task.ps1 -Repo "guevarakruz-code/actualizador-de-dolar-bolivia"
```

Con eso queda. Esa laptop va a mostrar el mismo precio del dólar que esta,
actualizado cada 15 minutos, sin depender de que esta PC esté prendida (el
que realmente consulta los precios corre en la nube, en GitHub Actions).

## Probar en tu propia PC (sin GitHub Actions)

```powershell
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="..."
python check_dolar.py
```
