# Instalador de una sola linea para poner el fondo de pantalla del dolar
# (Bolivia) en una PC nueva con Windows. No requiere git ni la CLI de
# GitHub, solo PowerShell (viene con Windows).
#
# Uso (pegar en PowerShell, sin permisos de administrador):
#   irm https://raw.githubusercontent.com/guevarakruz-code/actualizador-de-dolar-bolivia/main/scripts/install_on_new_pc.ps1 | iex

$ErrorActionPreference = "Stop"
$Repo = "guevarakruz-code/actualizador-de-dolar-bolivia"

$carpeta = Join-Path $env:USERPROFILE "ActualizadorDolarBolivia"
New-Item -ItemType Directory -Force -Path $carpeta | Out-Null

foreach ($archivo in @("set_wallpaper.ps1", "install_wallpaper_task.ps1")) {
    $url = "https://raw.githubusercontent.com/$Repo/main/scripts/$archivo"
    Invoke-WebRequest -Uri $url -OutFile (Join-Path $carpeta $archivo) -UseBasicParsing
}

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $carpeta "install_wallpaper_task.ps1") -Repo $Repo

Write-Output ""
Write-Output "Listo. El fondo de pantalla se va a actualizar solo cada 20 minutos."
