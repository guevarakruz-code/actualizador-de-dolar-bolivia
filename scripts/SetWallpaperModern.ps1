# Pone el fondo de pantalla usando la interfaz moderna IDesktopWallpaper
# (la misma que usa la app Configuracion de Windows), en vez de la API
# antigua SystemParametersInfo que en este equipo no estaba disparando el
# repintado real del escritorio (el cache TranscodedWallpaper no se
# actualizaba).

param(
    [Parameter(Mandatory = $true)]
    [string]$ImagePath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ImagePath)) {
    throw "No existe el archivo: $ImagePath"
}
$ImagePath = (Resolve-Path $ImagePath).Path

Add-Type @"
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("B92B56A9-8B55-4E14-9A89-0199BBB6F93B"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IDesktopWallpaper
{
    void SetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID, [MarshalAs(UnmanagedType.LPWStr)] string wallpaper);
    void GetWallpaper([MarshalAs(UnmanagedType.LPWStr)] string monitorID, out IntPtr wallpaper);
    void GetMonitorDevicePathAt(uint monitorIndex, out IntPtr monitorID);
    void GetMonitorDevicePathCount(out uint count);
}

[ComImport, Guid("C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD")]
public class DesktopWallpaperClass { }
"@

$comObj = [Activator]::CreateInstance([Type]::GetTypeFromCLSID([Guid]"C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD"))
if ($null -eq $comObj) { throw "CreateInstance devolvio null (no se pudo instanciar el objeto COM DesktopWallpaper)" }
$dw = [IDesktopWallpaper]$comObj
if ($null -eq $dw) { throw "El cast a IDesktopWallpaper devolvio null" }

# monitorID = $null aplica la misma imagen a todos los monitores
$dw.SetWallpaper($null, $ImagePath)

Write-Output "Fondo de pantalla aplicado via IDesktopWallpaper: $ImagePath"
