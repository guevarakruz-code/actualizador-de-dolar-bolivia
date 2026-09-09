# Descarga la imagen mas reciente del repositorio de GitHub (publico) y la
# pone como fondo de pantalla de Windows. Pensado para correr cada cierto
# tiempo desde el Programador de tareas de Windows (ver
# install_wallpaper_task.ps1). No necesita git ni la CLI de GitHub
# instalados: solo PowerShell (viene con Windows).
#
# NOTAS de depuracion (por si esto vuelve a fallar):
#   - La API moderna de Windows para el fondo de pantalla (IDesktopWallpaper,
#     la misma que usa la app Configuracion) devuelve "archivo no encontrado"
#     (HRESULT 0x80070002) para CUALQUIER archivo dentro de
#     %LOCALAPPDATA% (AppData\Local), aunque el archivo exista y sea valido.
#     Por eso la imagen se guarda dentro de la carpeta de Imagenes del
#     usuario (Pictures), no en AppData\Local.
#   - Ademas, tanto la API vieja (SystemParametersInfo) como la nueva a veces
#     NO repintan el escritorio si se les pasa la MISMA ruta de archivo que
#     ya estaba configurada, aunque el contenido cambio. Por eso cada corrida
#     escribe a un nombre de archivo distinto (con timestamp) y borra los
#     anteriores.
#
# Uso:
#   powershell -File set_wallpaper.ps1 -Repo "usuario/repo" -Path "wallpaper/current.png"

param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [string]$Path = "wallpaper/current.png"
)

$ErrorActionPreference = "Stop"

$carpetaImagenes = [Environment]::GetFolderPath("MyPictures")
$carpetaDestino = Join-Path $carpetaImagenes "ActualizadorDolarBolivia"
New-Item -ItemType Directory -Path $carpetaDestino -Force | Out-Null

$stamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$destino = Join-Path $carpetaDestino "dolar-bolivia-$stamp.png"

try {
    # Nota: en Windows PowerShell 5.1, "$var?..." dentro de una cadena se
    # interpola vacio (bug de parsing); por eso se usa ${Repo}/${Path}.
    $url = "https://raw.githubusercontent.com/${Repo}/main/${Path}?t=$stamp"
    Invoke-WebRequest -Uri $url -OutFile $destino -UseBasicParsing
} catch {
    Write-Warning "No se pudo descargar la imagen ($_). Se mantiene el fondo de pantalla actual."
    exit 1
}

Add-Type @"
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("B92B56A9-8B55-4E14-9A89-0199BBB6F93B"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IDesktopWallpaper
{
    void SetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID, [MarshalAs(UnmanagedType.LPWStr)] string wallpaper);
    [return: MarshalAs(UnmanagedType.LPWStr)]
    string GetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID);
    [return: MarshalAs(UnmanagedType.LPWStr)]
    string GetMonitorDevicePathAt(uint monitorIndex);
    uint GetMonitorDevicePathCount();
}

[ComImport, Guid("C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD")]
public class DesktopWallpaperClass { }

public static class WallpaperSetter
{
    // Pone la misma imagen en todos los monitores usando la API moderna
    // (IDesktopWallpaper). Si eso falla por completo, cae de vuelta a la
    // API vieja (SystemParametersInfo) como red de seguridad.
    public static void Set(string path)
    {
        try
        {
            var dw = (IDesktopWallpaper)new DesktopWallpaperClass();
            uint count = dw.GetMonitorDevicePathCount();
            if (count == 0)
            {
                dw.SetWallpaper(null, path);
            }
            else
            {
                for (uint i = 0; i < count; i++)
                {
                    dw.SetWallpaper(dw.GetMonitorDevicePathAt(i), path);
                }
            }
        }
        catch
        {
            SystemParametersInfo(0x0014, 0, path, 0x01 | 0x02);
        }
    }

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern int SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);
}
"@

[WallpaperSetter]::Set($destino)
Write-Output "Fondo de pantalla actualizado: $destino"

# Limpieza: borra versiones anteriores en esa carpeta (deja la actual).
Get-ChildItem -Path $carpetaDestino -Filter "dolar-bolivia-*.png" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -ne $destino } |
    Remove-Item -Force -ErrorAction SilentlyContinue
