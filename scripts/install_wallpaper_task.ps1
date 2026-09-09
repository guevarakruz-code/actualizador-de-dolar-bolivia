# Registra una tarea programada en Windows que actualiza el fondo de
# pantalla cada 20 minutos, descargando la ultima imagen generada por el
# workflow de GitHub Actions.
#
# Ejecutar UNA VEZ, en una terminal PowerShell normal (no hace falta admin):
#   powershell -File install_wallpaper_task.ps1 -Repo "usuario/repo"

param(
    [Parameter(Mandatory = $true)]
    [string]$Repo
)

$scriptPath = Join-Path $PSScriptRoot "set_wallpaper.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -Repo `"$Repo`""

# Duracion larga (10 anos) en vez de TimeSpan.MaxValue: el Programador de
# tareas de Windows rechaza duraciones de repeticion que no caben en su
# esquema XML (P99999999D...).
$disparador = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration (New-TimeSpan -Days 3650)

# StartWhenAvailable=true: sin esto, si el instante exacto de "-At (Get-Date)"
# ya paso para cuando el Programador de tareas lo registra (una carrera de
# tiempos que pasa casi siempre), Windows NO dispara esa primera corrida y
# se queda esperando el proximo intervalo de 20 minutos.
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName "ActualizadorDolarWallpaper" `
    -Action $accion -Trigger $disparador -Settings $config `
    -Description "Actualiza el fondo de pantalla con el precio del dolar en Bolivia" `
    -Force

Write-Output "Tarea 'ActualizadorDolarWallpaper' creada. Se ejecuta cada 20 minutos."
Write-Output "Para quitarla despues: Unregister-ScheduledTask -TaskName ActualizadorDolarWallpaper"

# La corre una vez de una, para no tener que esperar hasta 20 minutos para
# ver el primer resultado.
Start-ScheduledTask -TaskName "ActualizadorDolarWallpaper"
Write-Output "Primera corrida lanzada ahora mismo (puede tardar unos segundos)."
