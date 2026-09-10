# Registra una tarea programada en Windows que actualiza el fondo de
# pantalla cada 15 minutos, descargando la ultima imagen generada por el
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

# El cron externo (cron-job.org) dispara la corrida en la nube justo en
# los cuartos de hora (:00 :15 :30 :45). Para no bajar una imagen vieja
# (que pasaria si el primer disparo local cae, por ejemplo, en :53 y el
# siguiente en :08 -- desfasado de la nube), el disparo local se alinea al
# proximo cuarto de hora + 2 minutos de margen (tiempo de sobra para que
# la corrida en GitHub Actions termine y commitee).
$ahora = Get-Date
$cuartoActual = Get-Date -Year $ahora.Year -Month $ahora.Month -Day $ahora.Day -Hour $ahora.Hour `
    -Minute ([Math]::Floor($ahora.Minute / 15) * 15) -Second 0 -Millisecond 0
$inicio = $cuartoActual.AddMinutes(2)
while ($inicio -le $ahora) { $inicio = $inicio.AddMinutes(15) }

# Duracion larga (10 anos) en vez de TimeSpan.MaxValue: el Programador de
# tareas de Windows rechaza duraciones de repeticion que no caben en su
# esquema XML (P99999999D...).
$disparador = New-ScheduledTaskTrigger -Once -At $inicio -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)

# StartWhenAvailable=true: sin esto, si el instante exacto de "-At (Get-Date)"
# ya paso para cuando el Programador de tareas lo registra (una carrera de
# tiempos que pasa casi siempre), Windows NO dispara esa primera corrida y
# se queda esperando el proximo intervalo de 15 minutos.
#
# AllowStartIfOnBatteries / DontStopIfGoingOnBatteries: por defecto Windows
# no corre (o corta) tareas programadas cuando la laptop esta en bateria;
# esto es una laptop, asi que sin estas opciones se saltea corridas.
#
# MultipleInstances Parallel: por defecto, si una corrida anterior quedo
# marcada como "en ejecucion" (por ejemplo, tras una prueba manual
# interrumpida), el Programador de tareas SALTEA en silencio la siguiente
# corrida programada -- reporta exito (LastTaskResult 0) sin ejecutar nada
# en realidad. Esto se observo en la practica. Con Parallel, cada corrida
# programada se ejecuta si o si.
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances Parallel

Register-ScheduledTask -TaskName "ActualizadorDolarWallpaper" `
    -Action $accion -Trigger $disparador -Settings $config `
    -Description "Actualiza el fondo de pantalla con el precio del dolar en Bolivia" `
    -Force

Write-Output "Tarea 'ActualizadorDolarWallpaper' creada. Se ejecuta cada 15 minutos."
Write-Output "Para quitarla despues: Unregister-ScheduledTask -TaskName ActualizadorDolarWallpaper"

# La corre una vez de una, para no tener que esperar hasta 15 minutos para
# ver el primer resultado.
Start-ScheduledTask -TaskName "ActualizadorDolarWallpaper"
Write-Output "Primera corrida lanzada ahora mismo (puede tardar unos segundos)."
