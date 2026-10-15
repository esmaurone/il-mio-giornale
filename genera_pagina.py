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

# "Accadde oggi": solo eventi degli ultimi N anni
ACCADDE_ULTIMI_ANNI = 115

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


def scheda_meteo(nome, lat, lon, ora):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
            "weather_code,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
            "&hourly=temperature_2m,precipitation_probability,weather_code,wind_speed_10m"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset"
            "&timezone=Europe%2FRome&forecast_days=7"
        )
        d = json.loads(scarica(url))
        c, g, h = d["current"], d["daily"], d["hourly"]
        descr, ico = CODICI.get(c["weather_code"], ("", "🌡️"))
        oggi = f"{ora:%Y-%m-%d}"
        domani = f"{ora + timedelta(days=1):%Y-%m-%d}"

        def fascia(giorno, da_ora):
            out = ""
            for i, t in enumerate(h["time"]):
                if t[:10] != giorno or int(t[11:13]) < da_ora:
                    continue
                _, ic = CODICI.get(h["weather_code"][i], ("", "🌡️"))
                out += (
                    f'<div class="ora"><small>{t[11:16]}</small><span>{ic}</span>'
                    f'<b>{h["temperature_2m"][i]:.0f}°</b>'
                    f'<small>☔{h["precipitation_probability"][i] or 0}%</small>'
                    f'<small>💨{h["wind_speed_10m"][i]:.0f}</small></div>'
                )
            return out

        righe = ""
        for i in range(7):
            dsc, ic = CODICI.get(g["weather_code"][i], ("", "🌡️"))
            data_g = datetime.fromisoformat(g["time"][i])
            giorno = "Oggi" if i == 0 else f"{GIORNI[data_g.weekday()]} {data_g:%d/%m}"
            righe += (
                f"<tr><td>{giorno}</td><td>{ic}</td><td>{dsc}</td>"
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
<h3>Oggi, prossime ore</h3><div class="fascia">{fascia(oggi, ora.hour)}</div>
<h3>Domani, ora per ora</h3><div class="fascia">{fascia(domani, 0)}</div>
<h3>Prossimi 7 giorni</h3><div class="scorri"><table>{righe}</table></div></section>"""
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


def lezioni(ora):
    oggi = ora.date()
    domani = oggi + timedelta(days=1)
    try:
        dati = json.loads(scarica(f"{ORARI_URL}&start={oggi}&end={domani + timedelta(days=1)}"))
        if isinstance(dati, dict):
            dati = dati.get("events") or dati.get("data") or []
    except Exception as errore:
        print(f"Orari non disponibili: {errore}")
        return "<p>⚠️ Orari non disponibili.</p>"
    out = ""
    for giorno, etichetta in ((oggi, "Oggi"), (domani, "Domani")):
        eventi = sorted((e for e in dati if str(e.get("start", ""))[:10] == str(giorno)),
                        key=lambda e: str(e.get("start")))
        out += f"<h3>{etichetta} · {GIORNI[giorno.weekday()]} {giorno:%d/%m}</h3>"
        if not eventi:
            out += "<p>Nessuna lezione.</p>"
            continue
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
        out += f"<ul>{righe}</ul>"
    return out


def accadde_oggi(ora):
    """Sceglie l'evento più 'importante' (stima: quello con più voci Wikipedia collegate)."""
    for lingua in ("it", "en"):
        for tipo in ("selected", "events"):
            try:
                url = f"https://{lingua}.wikipedia.org/api/rest_v1/feed/onthisday/{tipo}/{ora:%m}/{ora:%d}"
                eventi = json.loads(scarica(url)).get(tipo) or []
            except Exception as errore:
                print(f"Accadde oggi ({lingua}/{tipo}) non disponibile: {errore}")
                continue
            eventi = [e for e in eventi
                      if isinstance(e.get("year"), int) and e["year"] >= ora.year - ACCADDE_ULTIMI_ANNI]
            if not eventi:
                continue
            eventi.sort(key=lambda e: len(e.get("pages", [])), reverse=True)
            scelti = eventi[:1]
            if len(eventi) > 1 and len(eventi[1].get("pages", [])) >= len(eventi[0].get("pages", [])) >= 3:
                scelti = eventi[:2]
            return "".join(
                f'<section class="card"><p><b>{html.escape(str(e.get("year", "")))}</b> — '
                f'{html.escape(e.get("text", ""))}</p></section>'
                for e in scelti
            )
    return "<p>⚠️ Non disponibile.</p>"


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
.griglia{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.card{background:var(--card);border-radius:12px;padding:14px;min-width:0}
.card h2{margin:0 0 4px}.card p{margin:3px 0}.big{font-size:2.4rem;font-weight:700}
table{width:100%;border-collapse:collapse;margin-top:8px;font-size:.9rem}
td{padding:4px 2px;border-top:1px solid #8884}
ul{list-style:none;padding:0}li{background:var(--card);margin:8px 0;padding:10px 12px;border-radius:10px;display:flex;gap:12px;align-items:center}
li img{width:104px;height:70px;object-fit:cover;border-radius:8px;flex:none}
a{color:var(--ac);text-decoration:none}
.fonte{display:inline-block;font-size:.95rem;font-weight:800;color:var(--ac);text-transform:uppercase;letter-spacing:.03em;margin-right:8px}
li a{font-size:1.12rem;font-weight:600}
.fascia{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px}
.ora{flex:none;display:flex;flex-direction:column;align-items:center;gap:2px;min-width:54px;padding:6px 4px;border-radius:10px;background:#8881}
.ora small{color:var(--sub);font-size:.72rem}.scorri{overflow-x:auto}
.card h3{margin:12px 0 4px;font-size:.95rem;color:var(--sub)}main>h3{margin:14px 0 2px}
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
<h2>Lezioni</h2>
__LEZIONI__
<h2>Accadde oggi</h2>
__ACCADDE__
<h2>Notizie</h2>
__NOTIZIE__
<p class="sub">Dati meteo: Open-Meteo.com. Notizie: titoli e link dei feed RSS delle testate.</p>
</main></body></html>"""


def main():
    ora = datetime.now(ZoneInfo("Europe/Rome"))
    data = f"{GIORNI[ora.weekday()]} {ora:%d/%m/%Y %H:%M}"
    meteo = "".join(scheda_meteo(n, la, lo, ora) for n, (la, lo) in LUOGHI.items())
    pagina = MODELLO.replace("__DATA__", data).replace("__METEO__", meteo).replace("__LEZIONI__", lezioni(ora)).replace("__ACCADDE__", accadde_oggi(ora)).replace("__NOTIZIE__", notizie())
    os.makedirs("sito", exist_ok=True)
    with open("sito/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)
    print("Pagina generata.")


if __name__ == "__main__":
    main()
