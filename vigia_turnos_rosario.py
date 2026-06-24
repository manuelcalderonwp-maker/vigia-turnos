#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==================================================================
  VIGÍA DE TURNOS - Licencia de conducir Rosario (psicofísico)
  Login automático (CUIT + contraseña) + modo diagnóstico.
==================================================================

Lee el desplegable "Lugar de atención" de "Modificar turno", saca la fecha
de cada distrito que te interese y, si alguna es MÁS TEMPRANA que tu turno
actual, manda un mail:  TURNO TURNO TURNO (dd/mm/aaaa)

Credenciales por variables de entorno: MR_CUIT, MR_PASS, MR_MAIL_PASS
Si algo falla, guarda debug.png y debug.html para ver qué pasó.
==================================================================
"""

import os
import re
import time
import random
import smtplib
import datetime as dt
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

# ========================= CONFIG =========================

FECHA_OBJETIVO = dt.date(2026, 8, 10)

DISTRITOS_ACEPTADOS = {
    "CMD Sudoeste",
    "CMD Oeste",
    "CMD Centro",
    "CMD Sur",
}

INTERVALO_MIN = 5
HEADLESS = True
RUN_ONCE = bool(os.environ.get("RUN_ONCE"))

CUIT     = os.environ.get("MR_CUIT", "")
PASSWORD = os.environ.get("MR_PASS", "")
EMAIL_APP_PASSWORD = os.environ.get("MR_MAIL_PASS", "")

EMAIL_FROM = "manuelcalderonwp@gmail.com"
EMAIL_TO   = "manuelcalderonwp@gmail.com"

URL_AGENDA = "https://www.rosario.gob.ar/inicio/perfildigital/licenciaconducir/preparar-agenda"
USER_DATA_DIR = "perfil_chrome"
RE_FECHA = re.compile(r"(\d{2}/\d{2}/\d{4})")

# ========================= LÓGICA =========================

def enviar_mail(fecha, distrito):
    asunto = f"TURNO TURNO TURNO ({fecha:%d/%m/%Y})"
    cuerpo = (
        f"Se liberó un turno de psicofísico más temprano que el tuyo "
        f"({FECHA_OBJETIVO:%d/%m/%Y}).\n\n"
        f"Lugar: {distrito}\n"
        f"Turnos a partir del: {fecha:%d/%m/%Y}\n\n"
        f"Entrá YA a reservarlo:\n{URL_AGENDA}\n"
    )
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.set_content(cuerpo)
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        s.send_message(msg)


def volcar_debug(page, etiqueta="debug"):
    try:
        page.screenshot(path=f"{etiqueta}.png", full_page=True)
        with open(f"{etiqueta}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"Guardé {etiqueta}.png y {etiqueta}.html (URL: {page.url})")
    except Exception as e:
        print("No pude guardar el diagnóstico:", e)


def hay_pantalla_turnos(page):
    try:
        page.get_by_label("Lugar de atención").wait_for(timeout=6000)
        return True
    except Exception:
        return False


def campo_login_visible(page):
    try:
        return page.locator("#username").first.is_visible()
    except Exception:
        return False


def intentar_revelar_login(page):
    """Si el formulario de CUIT está oculto, clickea los botones para mostrarlo."""
    candidatos = ["Municipalidad de Rosario", "Ingresar", "Iniciar sesión", "Acceder"]
    for _ in range(3):
        if campo_login_visible(page):
            return
        clickeo = False
        for texto in candidatos:
            try:
                loc = page.get_by_text(texto, exact=False).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=4000)
                    page.wait_for_load_state("networkidle", timeout=20000)
                    clickeo = True
                    break
            except Exception:
                continue
        if not clickeo:
            return


def login(page):
    intentar_revelar_login(page)
    page.wait_for_selector("#username", state="visible", timeout=20000)
    page.fill("#username", CUIT)
    page.fill("#password", PASSWORD)
    page.click("#kc-login")
    page.wait_for_load_state("networkidle", timeout=60000)


def asegurar_sesion(page):
    page.goto(URL_AGENDA, wait_until="networkidle", timeout=60000)
    if hay_pantalla_turnos(page):
        return
    login(page)
    page.goto(URL_AGENDA, wait_until="networkidle", timeout=60000)
    page.get_by_label("Lugar de atención").wait_for(timeout=20000)


def leer_opciones_lugar(page):
    try:
        select = page.get_by_label("Lugar de atención")
        select.wait_for(timeout=15000)
    except Exception:
        select = page.locator("select").first
        select.wait_for(timeout=15000)
    return select.locator("option").all_inner_texts()


def mejor_fecha(textos):
    candidatos = []
    for t in textos:
        distrito = t.split(" - ", 1)[0].strip()
        if distrito not in DISTRITOS_ACEPTADOS:
            continue
        m = RE_FECHA.search(t)
        if not m:
            continue
        try:
            fecha = dt.datetime.strptime(m.group(1), "%d/%m/%Y").date()
        except ValueError:
            continue
        candidatos.append((fecha, distrito))
    return min(candidatos, key=lambda x: x[0]) if candidatos else None


def chequear_y_avisar(page, ultima_alerta):
    ahora = dt.datetime.now().strftime("%d/%m %H:%M:%S")
    page.goto(URL_AGENDA, wait_until="networkidle", timeout=60000)
    if not hay_pantalla_turnos(page):
        print(f"[{ahora}] sin sesión -> login")
        asegurar_sesion(page)

    resultado = mejor_fecha(leer_opciones_lugar(page))
    if resultado is None:
        print(f"[{ahora}] no encontré fechas para tus distritos.")
        return ultima_alerta

    fecha, distrito = resultado
    if fecha < FECHA_OBJETIVO and fecha != ultima_alerta:
        print(f"[{ahora}] >>> {distrito}: {fecha:%d/%m/%Y} (mejor!) -> mail")
        enviar_mail(fecha, distrito)
        print("        mail enviado.")
        return fecha

    print(f"[{ahora}] más temprano: {distrito} {fecha:%d/%m/%Y} "
          f"(no mejora el {FECHA_OBJETIVO:%d/%m/%Y})")
    return ultima_alerta


def main():
    faltan = [n for n, v in [("MR_CUIT", CUIT), ("MR_PASS", PASSWORD),
                             ("MR_MAIL_PASS", EMAIL_APP_PASSWORD)] if not v]
    if faltan:
        print("Faltan credenciales:", ", ".join(faltan))
        return

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(USER_DATA_DIR, headless=HEADLESS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if RUN_ONCE:
                try:
                    asegurar_sesion(page)
                    chequear_y_avisar(page, None)
                except Exception as e:
                    print("FALLO:", e)
                    volcar_debug(page)
                    raise
            else:
                print(f"Vigía en bucle. Aviso si hay turno antes del "
                      f"{FECHA_OBJETIVO:%d/%m/%Y}. (Ctrl+C para frenar)\n")
                asegurar_sesion(page)
                ultima = None
                while True:
                    try:
                        ultima = chequear_y_avisar(page, ultima)
                    except Exception as e:
                        print("error:", e)
                        volcar_debug(page)
                    time.sleep(max(60, INTERVALO_MIN * 60 + random.randint(-20, 20)))
        except KeyboardInterrupt:
            print("\nFrenado.")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()
