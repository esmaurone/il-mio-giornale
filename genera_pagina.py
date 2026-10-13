#!/usr/bin/env python3
"""Genera sito/index.html: meteo (Rimini, Viserbella) + notizie (Sole 24 Ore, Sky TG24).
Solo librerie standard di Python."""

import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

# ------------------------------ IMPOSTAZIONI ------------------------------
LUOGHI = {
    "Rimini": (44.0678, 12.5695),
    "Viserbella": (44.0930, 12.5750),  # coordinate approssimate
}

# Per ogni testata puoi mettere più indirizzi RSS: lo script usa quelli che funzionano.
# DA VERIFICARE: se una testata non compare, cerca la pagina "RSS" sul suo sito
# e sostituisci qui gli indirizzi.
FEED = {
    "Il Sole 24 Ore": [
        "https://www.ilsole24ore.com/rss/italia.xml",
        "https://www.ilsole24ore.com/rss/economia.xml",
    ],
    "Sky TG24": [
        "https://tg24.sky.it/rss/tg24.xml",
        "https://tg24.sky.it/rss/tg24_ultimora.xml",
    ],
}
NOTIZIE_PER_TESTATA = 10

# Orari lezioni UniBo (2° anno, Economia dell'impresa, Rimini)
ORARI_URL = "https://corsi.unibo.it/laurea/clei/orario-lezioni/@@orario_reale_json?anno=2&curricula=B69-000"
# ---------------------------------------------------------------------------

CODICI = {
    0: ("Sereno", "☀️"), 1: ("Quasi sereno", "🌤️"), 2: ("Parz. nuvoloso", "⛅"),
    3: ("Coperto", "☁️"), 45: ("Nebbia", "🌫️"), 48: ("Nebbia", "🌫️"),
    51: ("Pioviggine", "🌦️"), 53: ("Pioviggine", "🌦️"), 55: ("Pioviggine", "🌦️"),
    61: ("Pioggia debole", "🌧️"), 63: ("Pioggia", "🌧️"), 65: ("Pioggia forte", "🌧️"),
    71: ("Neve debole", "🌨️"), 73: ("Neve", "🌨️"), 75: ("Neve forte", "❄️"),
    80: ("Rovesci", "🌦️"), 81: ("Rovesci", "🌧️"), 82: ("Rovesci violenti", "⛈️"),
    95: ("Temporale", "⛈️"), 96: ("Temporale e grandine", "⛈️"), 99: ("Temporale e grandine", "⛈️"),
}
GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
UTC = timezone.utc


def scarica(url):
    richiesta = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(richiesta, timeout=30) as r:
        return r.read()


def punto(gradi):
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][round(gradi / 45) % 8]


def scheda_meteo(nome, lat, lon):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
            "weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset"
            "&timezone=Europe%2FRome&forecast_days=4"
        )
        d = json.loads(scarica(url))
        c, g = d["current"], d["daily"]
        descr, ico = CODICI.get(c["weather_code"], ("", "🌡️"))
        righe = ""
        for i in range(4):
            _, ico_g = CODICI.get(g["weather_code"][i], ("", "🌡️"))
            giorno = "Oggi" if i == 0 else GIORNI[datetime.fromisoformat(g["time"][i]).weekday()]
            righe += (
                f"<tr><td>{giorno}</td><td>{ico_g}</td>"
                f"<td>{g['temperature_2m_min'][i]:.0f}° / {g['temperature_2m_max'][i]:.0f}°</td>"
                f"<td>☔ {g['precipitation_probability_max'][i] or 0}% · {g['precipitation_sum'][i]} mm</td>"
                f"<td>💨 {g['wind_speed_10m_max'][i]:.0f}</td></tr>"
            )
        return f"""<section class="card"><h2>{html.escape(nome)}</h2>
<div class="big">{ico} {c['temperature_2m']:.0f}°</div>
<p>{descr} · percepita {c['apparent_temperature']:.0f}°</p>
<p>💨 {c['wind_speed_10m']:.0f} km/h da {punto(c['wind_direction_10m'])} (raffiche {c['wind_gusts_10m']:.0f})</p>
<p>💧 umidità {c['relative_humidity_2m']}% · pioggia ora {c['precipitation']} mm</p>
<p>🌅 {g['sunrise'][0][11:]} · 🌇 {g['sunset'][0][11:]}</p>
<table>{righe}</table></section>"""
    except Exception as errore:
        print(f"Meteo {nome} non disponibile: {errore}")
        return f'<section class="card"><h2>{html.escape(nome)}</h2><p>⚠️ Meteo non disponibile.</p></section>'


MEDIA = "{http://search.yahoo.com/mrss/}"


def immagine(it):
    """Cerca l'indirizzo dell'immagine nella voce del feed (se c'è)."""
    for e in it.iter():
        u = e.get("url") or ""
        if not u.startswith("http") or e.tag not in (MEDIA + "content", MEDIA + "thumbnail", "enclosure"):
            continue
        tipo = (e.get("type") or "") + (e.get("medium") or "")
        if e.tag == MEDIA + "thumbnail" or "image" in tipo or u.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            return u
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', it.findtext("description") or "")
    return m.group(1) if m else ""


def lezioni_domani(ora):
    domani = (ora + timedelta(days=1)).date()
    dopo = domani + timedelta(days=1)
    try:
        dati = json.loads(scarica(f"{ORARI_URL}&start={domani}&end={dopo}"))
        if isinstance(dati, dict):
            dati = dati.get("events") or dati.get("data") or []
        eventi = sorted((e for e in dati if str(e.get("start", ""))[:10] == str(domani)),
                        key=lambda e: str(e.get("start")))
    except Exception as errore:
        print(f"Orari non disponibili: {errore}")
        return "<p>⚠️ Orari non disponibili.</p>"
    if not eventi:
        return f"<p>Nessuna lezione domani ({GIORNI[domani.weekday()]} {domani:%d/%m}).</p>"
    righe = ""
    for e in eventi:
        aule = e.get("aule") or []
        if isinstance(aule, list):
            aula = ", ".join(str(a.get("des_risorsa", a)) if isinstance(a, dict) else str(a) for a in aule)
        else:
            aula = str(aule)
        orario = f"{str(e.get('start'))[11:16]}–{str(e.get('end', ''))[11:16]}"
        righe += (f"<li><div><b>{orario}</b> {html.escape(str(e.get('title', '?')))}"
                  f"{' · ' + html.escape(aula) if aula else ''}</div></li>")
    return f"<p class=\"sub\">{GIORNI[domani.weekday()]} {domani:%d/%m}</p><ul>{righe}</ul>"


def notizie():
    tutte, avvisi = [], []
    for fonte, indirizzi in FEED.items():
        voci = {}
        for url in indirizzi:
            try:
                radice = ET.fromstring(scarica(url))
                for it in radice.iter("item"):
                    titolo = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    try:
                        data = parsedate_to_datetime(it.findtext("pubDate"))
                        if data.tzinfo is None:
                            data = data.replace(tzinfo=UTC)
                    except Exception:
                        data = datetime.min.replace(tzinfo=UTC)
                    if titolo and link:
                        voci[link] = (data, fonte, titolo, link, immagine(it))
            except Exception as errore:
                print(f"Feed non disponibile ({fonte}) {url}: {errore}")
        if not voci:
            avvisi.append(f"⚠️ {fonte}: nessun feed funzionante, controlla gli indirizzi nello script.")
        migliori = sorted(voci.values(), key=lambda v: v[0], reverse=True)[:NOTIZIE_PER_TESTATA]
        tutte += migliori
    tutte.sort(key=lambda v: v[0], reverse=True)
    elenco = "".join(
        (f'<li><img src="{html.escape(im)}" alt="" loading="lazy" referrerpolicy="no-referrer">' if im else "<li>")
        + f'<div><span class="fonte">{html.escape(f)}</span> '
        f'<a href="{html.escape(l)}" target="_blank" rel="noopener">{html.escape(t)}</a></div></li>'
        for _, f, t, l, im in tutte
    )
    note = "".join(f"<p>{a}</p>" for a in avvisi)
    return f"{note}<ul>{elenco}</ul>"


MODELLO = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Il mio giornale</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--tx:#1d1d1f;--sub:#666;--ac:#0a5fb4}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--card:#232323;--tx:#eee;--sub:#aaa;--ac:#6cb2ff}}
body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--tx);line-height:1.45}
main{max-width:900px;margin:auto;padding:16px}
h1{margin:.2em 0}.sub{color:var(--sub)}
.griglia{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.card{background:var(--card);border-radius:12px;padding:14px}
.card h2{margin:0 0 4px}.card p{margin:3px 0}.big{font-size:2.4rem;font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:.9rem}
td{padding:4px 2px;border-top:1px solid #8884}
ul{list-style:none;padding:0}li{background:var(--card);margin:8px 0;padding:10px 12px;border-radius:10px;display:flex;gap:12px;align-items:center}
li img{width:104px;height:70px;object-fit:cover;border-radius:8px;flex:none}
a{color:var(--ac);text-decoration:none}
.fonte{display:inline-block;font-size:.72rem;font-weight:700;color:var(--sub);text-transform:uppercase;margin-right:6px}
.link{font-size:.9rem}
</style></head><body><main>
<h1>Il mio giornale</h1>
<p class="sub">Aggiornato: __DATA__</p>
<h2>Meteo</h2>
<div class="griglia">__METEO__</div>
<p class="link">Confronta anche: <a href="https://www.google.com/search?q=meteo+Rimini" target="_blank" rel="noopener">Google Rimini</a> ·
<a href="https://www.google.com/search?q=meteo+Viserbella" target="_blank" rel="noopener">Google Viserbella</a> ·
<a href="https://www.ilmeteo.it/meteo/Rimini" target="_blank" rel="noopener">ilmeteo.it Rimini</a> ·
<a href="https://www.google.com/search?q=ilmeteo.it+meteo+Viserbella" target="_blank" rel="noopener">ilmeteo.it Viserbella</a></p>
<h2>Lezioni di domani</h2>
__LEZIONI__
<h2>Notizie</h2>
__NOTIZIE__
<p class="sub">Dati meteo: Open-Meteo.com. Notizie: titoli e link dei feed RSS delle testate.</p>
</main></body></html>"""


def main():
    ora = datetime.now(ZoneInfo("Europe/Rome"))
    data = f"{GIORNI[ora.weekday()]} {ora:%d/%m/%Y %H:%M}"
    meteo = "".join(scheda_meteo(n, la, lo) for n, (la, lo) in LUOGHI.items())
    pagina = MODELLO.replace("__DATA__", data).replace("__METEO__", meteo).replace("__LEZIONI__", lezioni_domani(ora)).replace("__NOTIZIE__", notizie())
    os.makedirs("sito", exist_ok=True)
    with open("sito/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)
    print("Pagina generata.")


if __name__ == "__main__":
    main()
