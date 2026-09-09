"""
Revisa la cotizacion del dolar en dos fuentes independientes y avisa por
Telegram y/o correo cuando cambia. Tambien genera una imagen
(wallpaper/current.png) con el precio actual para usar como fondo de
pantalla.

Fuentes de datos:
  1. https://www.dolarbluebolivia.click/tasas.json
     Endpoint publico de PRIMERA MANO que la propia pagina usa para
     refrescar los precios en el navegador (mismo origen, permitido por su
     robots.txt). NO se llama directamente a su API interna
     (api.dolarbluebolivia.click) porque el propio codigo de la pagina
     explica que hacerlo desde muchos clientes tumbo ese servicio una vez;
     /tasas.json sirve exactamente los mismos datos sin ese riesgo.
  2. https://www.bcb.gob.bo/  (Banco Central de Bolivia)
     Fuente oficial/regulatoria. El BCB no publica un endpoint JSON para
     esto, asi que se lee el numero directamente del HTML de su portada
     (bloque "Tipo de cambio oficial", clase bcb-tco-num), que es texto
     plano generado por su CMS (Drupal), no requiere JavaScript. Tambien
     se aprovecha para leer el UFV del mismo bloque de cotizaciones.

Variables de entorno (todas opcionales; si faltan, ese canal se salta):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   -> aviso por Telegram
  GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO (separados por coma) -> aviso por correo
"""

import json
import os
import re
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

TASAS_URL = "https://www.dolarbluebolivia.click/tasas.json"
BCB_URL = "https://www.bcb.gob.bo/"
STATE_FILE = Path(__file__).parent / "data" / "last_rates.json"
WALLPAPER_FILE = Path(__file__).parent / "wallpaper" / "current.png"

HEADERS = {"User-Agent": "actualizador-de-dolar-personal/1.0 (uso personal, no comercial)"}


def obtener_tasas():
    resp = requests.get(TASAS_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    blue = data["/v1/officialRate"]["data"]["blue"]
    oficial = data["/v1/officialRate"]["data"]["official"]
    return {
        "blue_compra": blue["buy"],
        "blue_venta": blue["sell"],
        "oficial_compra": oficial["buy"],
        "oficial_venta": oficial["sell"],
        "consultado_en": datetime.now(timezone.utc).isoformat(),
    }


def _numero_bcb(texto):
    """Convierte '12,64' o '3.344,40' (formato boliviano) a float."""
    return float(texto.strip().replace(".", "").replace(",", "."))


def _buscar_valor(html, ancla, patron, ventana=2000):
    idx = html.find(ancla)
    if idx == -1:
        return None
    m = re.search(patron, html[idx:idx + ventana])
    return m.group(1) if m else None


def obtener_oficial_bcb():
    """
    Lee el tipo de cambio oficial (y el UFV) directamente de la portada del
    Banco Central de Bolivia. Si el BCB cambia su HTML o no responde, no se
    rompe la corrida completa: se devuelve None y el resto sigue con la
    otra fuente.
    """
    try:
        resp = requests.get(BCB_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text

        # Busqueda directa (no por cercania a una clase CSS): "is-tc-oficial"
        # tambien aparece antes en el <style> del propio HTML, asi que
        # buscar por proximidad a esa clase da falsos negativos. El span
        # bcb-tco-num">...</span> solo existe una vez, en el HTML real.
        m = re.search(r'bcb-tco-num">\s*([\d.,]+)\s*<', html)
        oficial_txt = m.group(1) if m else None
        ufv_txt = _buscar_valor(html, '>UFV<', r'bcb-quote-value">\s*([\d.,]+)\s*<')

        if not oficial_txt:
            print("[bcb] no se encontro el tipo de cambio oficial en el HTML", file=sys.stderr)
            return None

        datos = {"bcb_oficial": _numero_bcb(oficial_txt)}
        if ufv_txt:
            datos["bcb_ufv"] = _numero_bcb(ufv_txt)
        return datos
    except Exception as exc:  # noqa: BLE001 - no queremos tumbar la corrida por esto
        print(f"[bcb] error al consultar {BCB_URL}: {exc}", file=sys.stderr)
        return None


def cargar_estado_anterior():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def guardar_estado(tasas):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(tasas, indent=2, ensure_ascii=False), encoding="utf-8")


CAMPOS_MONITOREADOS = {
    "blue_compra": "Blue - Compra",
    "blue_venta": "Blue - Venta",
    "oficial_compra": "Oficial (dolarbluebolivia) - Compra",
    "oficial_venta": "Oficial (dolarbluebolivia) - Venta",
    "bcb_oficial": "Oficial BCB",
}


def cambio(anterior, actual, campo):
    if anterior is None:
        return None
    antes = anterior.get(campo)
    ahora = actual.get(campo)
    if antes is None or ahora is None or antes == ahora:
        return None
    return antes, ahora


def construir_mensaje(anterior, actual):
    lineas = ["Cambio en la cotizacion del dolar en Bolivia:"]
    for campo, etiqueta in CAMPOS_MONITOREADOS.items():
        diff = cambio(anterior, actual, campo)
        if diff:
            antes, ahora = diff
            flecha = "subio" if ahora > antes else "bajo"
            lineas.append(f"- {etiqueta}: Bs {antes:.2f} -> Bs {ahora:.2f} ({flecha})")
    lineas.append("")
    lineas.append("Fuentes: https://www.dolarbluebolivia.click/  |  https://www.bcb.gob.bo/")
    return "\n".join(lineas)


def enviar_telegram(mensaje):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] omitido: faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=15)
    if r.ok:
        print("[telegram] aviso enviado")
    else:
        print(f"[telegram] error {r.status_code}: {r.text}", file=sys.stderr)


def enviar_correo(mensaje):
    user = os.environ.get("GMAIL_USER")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    destinatarios = os.environ.get("EMAIL_TO", "")
    destinatarios = [d.strip() for d in destinatarios.split(",") if d.strip()]

    if not user or not app_password or not destinatarios:
        print("[correo] omitido: faltan GMAIL_USER / GMAIL_APP_PASSWORD / EMAIL_TO")
        return

    msg = MIMEText(mensaje)
    msg["Subject"] = "Cambio en el precio del dolar (Bolivia)"
    msg["From"] = user
    msg["To"] = ", ".join(destinatarios)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, app_password)
        server.sendmail(user, destinatarios, msg.as_string())
    print(f"[correo] aviso enviado a {destinatarios}")


def generar_wallpaper(actual):
    from PIL import Image, ImageDraw, ImageFont

    ancho, alto = 1920, 1080
    fondo = (13, 17, 23)
    acento = (56, 189, 148)
    texto_secundario = (148, 163, 184)

    img = Image.new("RGB", (ancho, alto), fondo)
    draw = ImageDraw.Draw(img)

    def fuente(tam):
        try:
            return ImageFont.load_default(size=tam)
        except TypeError:
            return ImageFont.load_default()

    f_titulo = fuente(46)
    f_precio = fuente(160)
    f_label = fuente(38)
    f_pie = fuente(30)

    def centrar_x(texto, f):
        bbox = draw.textbbox((0, 0), texto, font=f)
        return (ancho - (bbox[2] - bbox[0])) // 2

    titulo = "DOLAR PARALELO EN BOLIVIA"
    draw.text((centrar_x(titulo, f_titulo), 120), titulo, font=f_titulo, fill=texto_secundario)

    precio_txt = f"Bs {actual['blue_venta']:.2f}"
    draw.text((centrar_x(precio_txt, f_precio), 420), precio_txt, font=f_precio, fill=acento)

    sub = f"Compra Bs {actual['blue_compra']:.2f}   |   Oficial Bs {actual['oficial_venta']:.2f}"
    draw.text((centrar_x(sub, f_label), 640), sub, font=f_label, fill=(226, 232, 240))

    bcb_oficial = actual.get("bcb_oficial")
    if bcb_oficial is not None:
        linea_bcb = f"Oficial BCB: Bs {bcb_oficial:.2f}"
        draw.text((centrar_x(linea_bcb, f_label), 710), linea_bcb, font=f_label, fill=texto_secundario)

    hora_local = datetime.now().strftime("%d/%m/%Y %H:%M")
    fuentes = "dolarbluebolivia.click"
    if bcb_oficial is not None:
        fuentes += "  +  bcb.gob.bo"
    pie = f"Actualizado: {hora_local}  -  {fuentes}"
    draw.text((centrar_x(pie, f_pie), alto - 100), pie, font=f_pie, fill=texto_secundario)

    WALLPAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
    img.save(WALLPAPER_FILE)
    print(f"[wallpaper] generado: {WALLPAPER_FILE}")


def main():
    actual = obtener_tasas()

    datos_bcb = obtener_oficial_bcb()
    if datos_bcb:
        actual.update(datos_bcb)

    anterior = cargar_estado_anterior()

    hubo_cambio = anterior is not None and any(
        cambio(anterior, actual, campo) for campo in CAMPOS_MONITOREADOS
    )

    print(f"Cotizacion actual: {actual}")

    if hubo_cambio:
        mensaje = construir_mensaje(anterior, actual)
        print(mensaje)
        enviar_telegram(mensaje)
        enviar_correo(mensaje)
    elif anterior is None:
        print("Primera ejecucion: se guarda el precio base, sin aviso.")
    else:
        print("Sin cambios respecto a la ultima consulta.")

    generar_wallpaper(actual)
    guardar_estado(actual)


if __name__ == "__main__":
    main()
