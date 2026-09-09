# Registra una tarea programada en Windows que actualiza el fondo de
# pantalla cada 20 minutos, descargando la ultima imagen generada por el
# workflow de GitHub Actions.
#
# Ejecutar UNA VEZ, en una terminal PowerShell normal (no hace falta admin):
#   powershell -File install_wallpaper_task.ps1 -ImageUrl "https://raw.githubusercontent.com/USUARIO/REPO/main/wallpaper/current.png"

param(
    [Parameter(Mandatory = $true)]
    [string]$ImageUrl
)

$scriptPath = Join-Path $PSScriptRoot "set_wallpaper.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -ImageUrl `"$ImageUrl`""

$disparador = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration ([TimeSpan]::MaxValue)

Register-ScheduledTask -TaskName "ActualizadorDolarWallpaper" `
    -Action $accion -Trigger $disparador -Description "Actualiza el fondo de pantalla con el precio del dolar en Bolivia" `
    -Force

Write-Output "Tarea 'ActualizadorDolarWallpaper' creada. Se ejecuta cada 20 minutos."
Write-Output "Para quitarla despues: Unregister-ScheduledTask -TaskName ActualizadorDolarWallpaper"
