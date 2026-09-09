# Descarga la imagen mas reciente del repositorio de GitHub y la pone como
# fondo de pantalla de Windows. Pensado para correr cada cierto tiempo desde
# el Programador de tareas de Windows (ver install_wallpaper_task.ps1).
#
# El repositorio es privado, asi que la URL publica de raw.githubusercontent.com
# da 404 sin autenticacion. Se resuelve pidiendole el token a la sesion de
# GitHub CLI ya autenticada en este equipo ("gh auth token") y usandolo como
# cabecera Authorization contra raw.githubusercontent.com. No se crea ni se
# guarda ningun token nuevo en disco.
#
# Uso:
#   powershell -File set_wallpaper.ps1 -Repo "usuario/repo" -Path "wallpaper/current.png"

param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$Path = "wallpaper/current.png"
)

$ErrorActionPreference = "Stop"

$destino = Join-Path $env:LOCALAPPDATA "actualizador-dolar-wallpaper.png"

try {
    $token = (& gh auth token).Trim()
    if (-not $token) { throw "gh auth token no devolvio nada (revisa 'gh auth status')" }

    # Nota: en Windows PowerShell 5.1, "$var?..." dentro de una cadena se
    # interpola vacio (bug de parsing); por eso se usa ${Repo}/${Path}.
    $url = "https://raw.githubusercontent.com/${Repo}/main/${Path}?t=$(Get-Date -UFormat %s)"
    Invoke-WebRequest -Uri $url -Headers @{ Authorization = "token $token" } -OutFile $destino -UseBasicParsing
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
