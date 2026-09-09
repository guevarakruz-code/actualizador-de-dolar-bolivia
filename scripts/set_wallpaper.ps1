# Descarga la imagen mas reciente del repositorio de GitHub y la pone como
# fondo de pantalla de Windows. Pensado para correr cada cierto tiempo desde
# el Programador de tareas de Windows (ver install_wallpaper_task.ps1).
#
# Uso:
#   powershell -File set_wallpaper.ps1 -ImageUrl "https://raw.githubusercontent.com/USUARIO/REPO/main/wallpaper/current.png"

param(
    [Parameter(Mandatory = $true)]
    [string]$ImageUrl
)

$ErrorActionPreference = "Stop"

$destino = Join-Path $env:LOCALAPPDATA "actualizador-dolar-wallpaper.png"

try {
    Invoke-WebRequest -Uri "$ImageUrl?t=$(Get-Date -UFormat %s)" -OutFile $destino -UseBasicParsing
} catch {
    Write-Warning "No se pudo descargar la imagen ($_). Se mantiene el fondo de pantalla actual."
    exit 1
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Wallpaper {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);
}
"@

$SPI_SETDESKWALLPAPER = 0x0014
$SPIF_UPDATEINIFILE = 0x01
$SPIF_SENDWININICHANGE = 0x02

[Wallpaper]::SystemParametersInfo($SPI_SETDESKWALLPAPER, 0, $destino, $SPIF_UPDATEINIFILE -bor $SPIF_SENDWININICHANGE) | Out-Null

Write-Output "Fondo de pantalla actualizado desde $ImageUrl"
