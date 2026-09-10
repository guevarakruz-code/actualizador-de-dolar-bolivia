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
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

TASAS_URL = "https://www.dolarbluebolivia.click/tasas.json"
BCB_URL = "https://www.bcb.gob.bo/"
STATE_FILE = Path(__file__).parent / "data" / "last_rates.json"
HISTORY_FILE = Path(__file__).parent / "data" / "history.json"
WALLPAPER_FILE = Path(__file__).parent / "wallpaper" / "current.png"

HEADERS = {"User-Agent": "actualizador-de-dolar-personal/1.0 (uso personal, no comercial)"}

# Bolivia no usa horario de verano: UTC-4 todo el ano. Se usa esto (en vez
# de datetime.now(), que en GitHub Actions corre en UTC) para que las horas
# mostradas en el wallpaper ("Actualizado", "Proxima actualizacion") sean
# la hora real de Bolivia.
BOLIVIA_TZ = timezone(timedelta(hours=-4))

HISTORIAL_HORAS = 4          # ventana que se muestra en el grafico
HISTORIAL_MAX_ENTRADAS = 300  # limite de seguridad para que el archivo no crezca sin fin
MINUTOS_ENTRE_CORRIDAS = 15   # cadencia real: el cron externo (cron-job.org) dispara cada 15 min


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


def cargar_historial():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def guardar_historial(historial):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(historial, indent=2, ensure_ascii=False), encoding="utf-8")


def agregar_al_historial(historial, actual):
    """
    Agrega la lectura actual al historial y lo recorta (por tiempo y por
    cantidad) para que no crezca sin fin. Si el BCB fallo esta corrida
    (bcb_oficial=None), se arrastra el ultimo valor conocido para que el
    grafico no quede con huecos.
    """
    bcb_oficial = actual.get("bcb_oficial")
    if bcb_oficial is None and historial:
        bcb_oficial = historial[-1].get("bcb_oficial")

    historial = historial + [{
        "t": actual["consultado_en"],
        "blue_venta": actual["blue_venta"],
        "bcb_oficial": bcb_oficial,
    }]

    limite = datetime.now(timezone.utc) - timedelta(hours=HISTORIAL_HORAS * 3)
    historial = [h for h in historial if datetime.fromisoformat(h["t"]) >= limite]
    return historial[-HISTORIAL_MAX_ENTRADAS:]


def historial_reciente(historial, horas=HISTORIAL_HORAS):
    """Los puntos del historial dentro de las ultimas N horas (al menos 1)."""
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    ventana = [h for h in historial if datetime.fromisoformat(h["t"]) >= limite]
    return ventana or historial[-1:]


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


def generar_wallpaper(actual, anterior, historial):
    from PIL import Image, ImageDraw, ImageFont

    ancho, alto = 1920, 1080
    fondo = (13, 17, 23)
    verde = (56, 189, 148)      # usado para: precio grande (marca) y "baja"
    rojo = (239, 68, 68)        # usado para: "sube"
    azul_bcb = (96, 165, 250)   # color fijo de la serie BCB en el grafico
    texto_secundario = (148, 163, 184)
    texto_claro = (226, 232, 240)
    linea_sutil = (30, 41, 54)

    img = Image.new("RGB", (ancho, alto), fondo)
    draw = ImageDraw.Draw(img)

    def fuente(tam):
        try:
            return ImageFont.load_default(size=tam)
        except TypeError:
            return ImageFont.load_default()

    f_titulo = fuente(44)
    f_precio = fuente(140)
    f_label = fuente(34)
    f_metrica = fuente(28)
    f_hist_label = fuente(24)
    f_pie = fuente(26)
    f_esquina = fuente(24)
    f_valor_punto = fuente(19)

    def centrar_x(texto, f, cx=None):
        bbox = draw.textbbox((0, 0), texto, font=f)
        w = bbox[2] - bbox[0]
        centro = cx if cx is not None else ancho // 2
        return centro - w // 2

    def color_variacion(sube):
        # Pedido del usuario: invertido respecto a la convencion habitual.
        return rojo if sube else verde

    # --- titulo ---
    titulo = "DOLAR PARALELO EN BOLIVIA"
    draw.text((centrar_x(titulo, f_titulo), 70), titulo, font=f_titulo, fill=texto_secundario)

    # --- precio grande (Blue - venta) ---
    precio_txt = f"Bs {actual['blue_venta']:.2f}"
    y_precio = 250
    bbox_precio = draw.textbbox((centrar_x(precio_txt, f_precio), y_precio), precio_txt, font=f_precio)
    draw.text((bbox_precio[0], y_precio), precio_txt, font=f_precio, fill=verde)

    def badge_variacion(x, y_centro, etiqueta, valor_delta):
        """[triangulo] ETIQUETA  0.02 Bs -- o 'sin cambio' / '(primera lectura)'."""
        if valor_delta is None:
            texto = f"{etiqueta}  (primera lectura)"
            color = texto_secundario
            tiene_flecha = False
            sube = False
        elif valor_delta == 0:
            texto = f"{etiqueta}  sin cambio"
            color = texto_secundario
            tiene_flecha = False
            sube = False
        else:
            sube = valor_delta > 0
            color = color_variacion(sube)
            texto = f"{etiqueta}  {abs(valor_delta):.2f} Bs"
            tiene_flecha = True

        bbox_txt = draw.textbbox((0, 0), texto, font=f_metrica)
        w_txt = bbox_txt[2] - bbox_txt[0]
        h_txt = bbox_txt[3] - bbox_txt[1]

        tri_w, tri_h = 16, 16
        pad_x, pad_y = 16, 10
        espacio = 10
        contenido_w = (tri_w + espacio if tiene_flecha else 0) + w_txt
        contenido_h = max(tri_h, h_txt)

        x0, y0 = x, y_centro - contenido_h // 2 - pad_y
        x1, y1 = x + contenido_w + pad_x * 2, y_centro + contenido_h // 2 + pad_y
        draw.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=(20, 26, 34), outline=color, width=2)

        cursor_x = x + pad_x
        if tiene_flecha:
            # La fuente por defecto de PIL no tiene el glifo de flecha
            # (arriba/abajo), asi que se dibuja como triangulo.
            tri_cx = cursor_x + tri_w // 2
            tri_cy = y_centro
            if sube:
                tri = [(tri_cx - tri_w // 2, tri_cy + tri_h // 2), (tri_cx + tri_w // 2, tri_cy + tri_h // 2), (tri_cx, tri_cy - tri_h // 2)]
            else:
                tri = [(tri_cx - tri_w // 2, tri_cy - tri_h // 2), (tri_cx + tri_w // 2, tri_cy - tri_h // 2), (tri_cx, tri_cy + tri_h // 2)]
            draw.polygon(tri, fill=color)
            cursor_x += tri_w + espacio

        y_texto = y_centro - h_txt // 2 - bbox_txt[1]
        draw.text((cursor_x, y_texto), texto, font=f_metrica, fill=color)

    delta_blue = cambio(anterior, actual, "blue_venta") if anterior else None
    delta_blue = round(delta_blue[1] - delta_blue[0], 2) if delta_blue else (0.0 if anterior else None)
    delta_bcb = cambio(anterior, actual, "bcb_oficial") if anterior else None
    delta_bcb = round(delta_bcb[1] - delta_bcb[0], 2) if delta_bcb else (0.0 if anterior and actual.get("bcb_oficial") is not None else None)

    x_badges = bbox_precio[2] + 30
    badge_variacion(x_badges, y_precio + 35, "BLUE", delta_blue)
    badge_variacion(x_badges, y_precio + 90, "BCB", delta_bcb)

    # --- subinfo (compra / oficial) ---
    sub = f"Compra Bs {actual['blue_compra']:.2f}   |   Oficial (dolarbluebolivia) Bs {actual['oficial_venta']:.2f}"
    draw.text((centrar_x(sub, f_label), 470), sub, font=f_label, fill=texto_claro)

    bcb_oficial = actual.get("bcb_oficial")
    bcb_ufv = actual.get("bcb_ufv")
    if bcb_oficial is not None:
        bcb_txt = f"Oficial BCB: Bs {bcb_oficial:.2f}"
        if bcb_ufv is not None:
            bcb_txt += f"   |   UFV: {bcb_ufv:.5f}"
        draw.text((centrar_x(bcb_txt, f_label), 525), bcb_txt, font=f_label, fill=texto_secundario)

    # --- historial: grafico con las dos series ---
    hist_top = 610
    label_margin = 34
    plot_top = hist_top + label_margin
    hist_bottom = 860
    hist_left = 460
    hist_right = 1460
    hist_titulo = f"HISTORIAL - ULTIMAS {HISTORIAL_HORAS} HORAS"
    draw.text((centrar_x(hist_titulo, f_hist_label), hist_top - 36), hist_titulo, font=f_hist_label, fill=texto_secundario)

    historial_blue = [h["blue_venta"] for h in historial]
    historial_bcb = [h.get("bcb_oficial") for h in historial if h.get("bcb_oficial") is not None]
    n = len(historial_blue)

    if n < 2:
        msg = "Aun no hay suficiente historial (vuelve a mirar en un rato)"
        draw.text((centrar_x(msg, f_hist_label), (hist_top + hist_bottom) // 2), msg, font=f_hist_label, fill=texto_secundario)
    else:
        todos_los_valores = historial_blue + (historial_bcb or [])
        vmin, vmax = min(todos_los_valores), max(todos_los_valores)
        margen = (vmax - vmin) * 0.1 or 0.05
        vmin -= margen
        vmax += margen
        rango = vmax - vmin
        paso_x = (hist_right - hist_left) / (n - 1)

        def puntos_de(serie):
            return [
                (hist_left + i * paso_x, hist_bottom - ((v - vmin) / rango) * (hist_bottom - plot_top))
                for i, v in enumerate(serie)
            ]

        def etiqueta_valor(x, y, valor, color):
            texto = f"{valor:.2f}"
            bbox = draw.textbbox((0, 0), texto, font=f_valor_punto)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            draw.text((x - w / 2, y - h - 12 - bbox[1]), texto, font=f_valor_punto, fill=color)

        draw.line([(hist_left, hist_bottom), (hist_right, hist_bottom)], fill=linea_sutil, width=1)

        hay_bcb = len(historial_bcb) == n
        if hay_bcb:
            pts_bcb = puntos_de(historial_bcb)
            for i in range(len(pts_bcb) - 1):
                x0, y0 = pts_bcb[i]
                x1, y1 = pts_bcb[i + 1]
                segmentos = 6
                for s in range(segmentos):
                    t0, t1 = s / segmentos, min((s + 0.6) / segmentos, 1)
                    draw.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)], fill=azul_bcb, width=3)
            for i, (x, y) in enumerate(pts_bcb):
                es_ultimo = i == len(pts_bcb) - 1
                r = 7 if es_ultimo else 3
                draw.ellipse([x - r, y - r, x + r, y + r], fill=azul_bcb)
                etiqueta_valor(x, y, historial_bcb[i], azul_bcb)

        pts_blue = puntos_de(historial_blue)
        for i in range(len(pts_blue) - 1):
            seg_color = color_variacion(historial_blue[i + 1] >= historial_blue[i])
            draw.line([pts_blue[i], pts_blue[i + 1]], fill=seg_color, width=4)
        for i, (x, y) in enumerate(pts_blue):
            es_ultimo = i == len(pts_blue) - 1
            r = 8 if es_ultimo else 4
            draw.ellipse([x - r, y - r, x + r, y + r], fill=texto_claro if es_ultimo else texto_secundario)
            etiqueta_valor(x, y, historial_blue[i], texto_claro if es_ultimo else texto_claro)

        # leyenda
        leyenda_y = hist_top - 36
        lx = hist_right - (260 if hay_bcb else 110)
        draw.line([(lx, leyenda_y + 12), (lx + 30, leyenda_y + 12)], fill=texto_claro, width=4)
        draw.text((lx + 40, leyenda_y), "Blue", font=f_hist_label, fill=texto_claro)
        if hay_bcb:
            lx2 = lx + 110
            for s in range(4):
                draw.line([(lx2 + s * 9, leyenda_y + 12), (lx2 + s * 9 + 5, leyenda_y + 12)], fill=azul_bcb, width=3)
            draw.text((lx2 + 45, leyenda_y), "BCB", font=f_hist_label, fill=texto_claro)

        # ejes de tiempo (aproximado, segun la cadencia esperada)
        try:
            t_ini = datetime.fromisoformat(historial[0]["t"])
            t_fin = datetime.fromisoformat(historial[-1]["t"])
            horas_reales = (t_fin - t_ini).total_seconds() / 3600
            hace_txt = f"hace {horas_reales:.1f}h" if horas_reales < 10 else f"hace {round(horas_reales)}h"
        except Exception:
            hace_txt = f"hace ~{HISTORIAL_HORAS}h"
        draw.text((hist_left, hist_bottom + 14), hace_txt, font=f_hist_label, fill=texto_secundario)
        ahora_txt = "ahora"
        bbox_ahora = draw.textbbox((0, 0), ahora_txt, font=f_hist_label)
        draw.text((hist_right - (bbox_ahora[2] - bbox_ahora[0]), hist_bottom + 14), ahora_txt, font=f_hist_label, fill=texto_claro)

    # --- esquina: hora de la proxima actualizacion ---
    ahora_bo = datetime.now(BOLIVIA_TZ)
    proxima = ahora_bo + timedelta(minutes=MINUTOS_ENTRE_CORRIDAS)
    # Margen grande respecto al borde inferior: en Windows, el estilo de
    # fondo "Rellenar" (Fill) recorta la imagen para cubrir toda la
    # pantalla si la proporcion del monitor no es exactamente 16:9, y
    # ademas la barra de tareas puede tapar una franja del borde inferior.
    # Con poco margen, este texto quedaba cortado/tapado en otras PCs.
    margen_inferior = 140
    esquina_txt = f"Proxima actualizacion: ~{proxima.strftime('%H:%M')}"
    draw.text((60, alto - margen_inferior), esquina_txt, font=f_esquina, fill=texto_secundario)

    # --- pie (centrado) ---
    fuentes = "dolarbluebolivia.click"
    if bcb_oficial is not None:
        fuentes += "  +  bcb.gob.bo"
    pie = f"Actualizado: {ahora_bo.strftime('%d/%m/%Y %H:%M')} (hora Bolivia)  -  {fuentes}"
    draw.text((centrar_x(pie, f_pie), alto - margen_inferior), pie, font=f_pie, fill=texto_secundario)

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

    historial = agregar_al_historial(cargar_historial(), actual)
    guardar_historial(historial)

    generar_wallpaper(actual, anterior, historial_reciente(historial))
    guardar_estado(actual)


if __name__ == "__main__":
    main()
