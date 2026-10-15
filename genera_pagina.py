#!/usr/bin/env python3
"""Genera sito/index.html: meteo (Rimini, Viserbella) + notizie (Sole 24 Ore, Sky TG24).
Solo librerie standard di Python."""

import html
import json
import os
import re
import urllib.request
from urllib.parse import quote, quote_plus
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

# ------------------------------ IMPOSTAZIONI ------------------------------
LUOGHI = {
    "Rimini": (44.0678, 12.5695),
    "Viserbella": (44.0930, 12.5750),  # coordinate approssimate
}

# Titoli seguiti: (nome, ricerca per le notizie, simbolo Yahoo Finance, id CoinGecko come piano B)
# Per aggiungerne o toglierne basta copiare o cancellare una riga.
TITOLI = [
    ("AMD", "AMD azioni", "AMD", ""),
    ("Tesla", "Tesla TSLA azioni", "TSLA", ""),
    ("ASML", "ASML azioni", "ASML", ""),
    ("Ferrari", "Ferrari titolo borsa", "RACE.MI", ""),
    ("Nvidia", "Nvidia azioni", "NVDA", ""),
    ("Amazon", "Amazon AMZN azioni", "AMZN", ""),
    ("Nasdaq", "Nasdaq Inc NDAQ azioni", "NDAQ", ""),  # Nasdaq Inc. (per l'indice usa "^IXIC")
    ("IBM", "IBM azioni", "IBM", ""),
    ("D-Wave Quantum", "D-Wave Quantum", "QBTS", ""),
    ("IonQ", "IonQ", "IONQ", ""),
    ("Intesa Sanpaolo", "Intesa Sanpaolo", "ISP.MI", ""),
    ("BPER Banca", "BPER Banca", "BPE.MI", ""),
    ("Bitcoin", "Bitcoin", "BTC-USD", "bitcoin"),
    ("USDT", "USDT Tether", "USDT-USD", "tether"),
]
NOTIZIE_PER_TITOLO = 2       # quante notizie mostrare per ogni titolo
NOTIZIE_ULTIMI_GIORNI = 2    # solo notizie degli ultimi N giorni

# Schede ufficiali di Borsa Italiana (per controllare i prezzi dei titoli italiani)
BORSA_ITALIANA = {
    "RACE.MI": "https://www.borsaitaliana.it/borsa/azioni/scheda/NL0011585146.html",
    "ISP.MI": "https://www.borsaitaliana.it/borsa/azioni/scheda/IT0000072618.html",
    "BPE.MI": "https://www.borsaitaliana.it/borsa/azioni/scheda/IT0000066123.html",
}

# "Accadde oggi": solo eventi degli ultimi N anni
ACCADDE_ULTIMI_ANNI = 115

# Esami: ogni esame compare nella pagina da quando mancano ESAMI_PREAVVISO_GIORNI giorni
# fino al giorno stesso. Per aggiungerne uno, copia una riga: (anno, mese, giorno, "nome")
ESAMI_PREAVVISO_GIORNI = 40
ESAMI = [
    (2026, 11, 2, "1° parziale di Matematica finanziaria"),
    (2026, 11, 4, "1° parziale di Rendicontazione"),
    (2026, 12, 21, "2° parziale di Rendicontazione"),
    (2027, 1, 7, "1° parziale di Diritto commerciale"),
    (2027, 1, 8, "2° parziale di Matematica finanziaria"),
    (2027, 1, 13, "1° appello di Strategie di impresa"),
    (2027, 2, 4, "Appello di Matematica finanziaria"),
    (2027, 3, 31, "1° parziale di Controllo di gestione"),
    (2027, 4, 1, "1° parziale di Statistica"),
    (2027, 4, 7, "2° parziale di Diritto commerciale"),
    (2027, 5, 25, "2° parziale di Statistica"),
    (2027, 5, 31, "1° appello di Macroeconomia"),
    (2027, 6, 7, "2° parziale di Controllo di gestione"),
]

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


def esami(ora):
    oggi = ora.date()
    righe = ""
    for a, m, g, nome in sorted(ESAMI):
        giorno = date(a, m, g)
        mancano = (giorno - oggi).days
        if not 0 <= mancano <= ESAMI_PREAVVISO_GIORNI:
            continue
        quando = "OGGI!" if mancano == 0 else "domani" if mancano == 1 else f"tra {mancano} giorni"
        stile = ' class="urgente"' if mancano <= 7 else ""
        righe += (f"<li{stile}><div><b>{html.escape(nome)}</b><br>"
                  f"{GIORNI[giorno.weekday()]} {giorno:%d/%m/%Y} · {quando}</div></li>")
    if not righe:
        return f"<p>Nessun esame nei prossimi {ESAMI_PREAVVISO_GIORNI} giorni.</p>"
    return f"<ul>{righe}</ul>"


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
    voci, senza = {}, []
    for nome, ricerca, _, _ in TITOLI:
        try:
            q = quote_plus(f"{ricerca} when:{NOTIZIE_ULTIMI_GIORNI}d")
            radice = ET.fromstring(scarica(f"https://news.google.com/rss/search?q={q}&hl=it&gl=IT&ceid=IT:it"))
            trovate = []
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
                    trovate.append((data, nome, titolo, link))
            trovate.sort(key=lambda v: v[0], reverse=True)
            if not trovate:
                senza.append(nome)
            for v in trovate[:NOTIZIE_PER_TITOLO]:
                voci.setdefault(v[3], v)
        except Exception as errore:
            print(f"Notizie {nome} non disponibili: {errore}")
            senza.append(nome)
    elenco = ""
    for _, nome, titolo, link in sorted(voci.values(), key=lambda v: v[0], reverse=True):
        testo, _, giornale = titolo.rpartition(" - ")  # Google News scrive "Titolo - Testata"
        if not testo:
            testo, giornale = titolo, ""
        elenco += (f'<li><div><span class="fonte">{html.escape(nome)}</span> '
                   f'<a href="{html.escape(link)}" target="_blank" rel="noopener">{html.escape(testo)}</a> '
                   f'<span class="giornale">{html.escape(giornale)}</span></div></li>')
    nota = f'<p class="sub">Nessuna notizia recente per: {html.escape(", ".join(senza))}.</p>' if senza else ""
    return f'<ul class="notizie">{elenco}</ul>{nota}'


def num(x, dec=None):
    if x is None:
        return "–"
    dec = (4 if abs(x) < 10 else 2) if dec is None else dec
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def intervallo(a, b):
    return "–" if a is None or b is None else f"{num(a)} – {num(b)}"


def scarica_titolo(simbolo):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(simbolo, safe='')}?range=5d&interval=1d"
    r = json.loads(scarica(url))["chart"]["result"][0]
    meta = r["meta"]
    chiusure = [c for c in r["indicators"]["quote"][0].get("close", []) if c is not None]
    prezzo = meta["regularMarketPrice"]
    prec = chiusure[-2] if len(chiusure) >= 2 else None
    return {
        "prezzo": prezzo, "var": (prezzo / prec - 1) * 100 if prec else None,
        "valuta": meta.get("currency", ""), "ora": meta.get("regularMarketTime"),
        "min_g": meta.get("regularMarketDayLow"), "max_g": meta.get("regularMarketDayHigh"),
        "min_52": meta.get("fiftyTwoWeekLow"), "max_52": meta.get("fiftyTwoWeekHigh"),
    }


def borsa():
    righe, cg = "", None
    for nome, _, simbolo, id_cg in TITOLI:
        try:
            d = scarica_titolo(simbolo)
        except Exception as errore:
            print(f"Borsa {nome} ({simbolo}) non disponibile: {errore}")
            d = None
            if id_cg:  # piano B per le criptovalute
                try:
                    if cg is None:
                        cg = json.loads(scarica("https://api.coingecko.com/api/v3/simple/price"
                                                "?ids=bitcoin,tether&vs_currencies=usd&include_24hr_change=true"))
                    d = {"prezzo": cg[id_cg]["usd"], "var": cg[id_cg].get("usd_24h_change"), "valuta": "USD",
                         "min_g": None, "max_g": None, "min_52": None, "max_52": None}
                except Exception as errore2:
                    print(f"Piano B {nome} non disponibile: {errore2}")
        if d is None:
            righe += f'<tr><td><b>{html.escape(nome)}</b></td><td colspan="5">dato non disponibile</td></tr>'
            continue
        v = d["var"]
        classe = "" if v is None else ("su" if v >= 0 else "giu")
        var = "–" if v is None else f"{'+' if v >= 0 else ''}{num(v, 2)}%"
        val = {"USD": "$", "EUR": "€"}.get(d["valuta"], d["valuta"])
        link_bi = BORSA_ITALIANA.get(simbolo)
        extra = f' · <a href="{link_bi}" target="_blank" rel="noopener">Borsa Italiana</a>' if link_bi else ""
        try:
            ultimo = datetime.fromtimestamp(d["ora"], ZoneInfo("Europe/Rome")).strftime("%d/%m %H:%M")
        except Exception:
            ultimo = "–"
        righe += (f"<tr><td><b>{html.escape(nome)}</b><br><small>{html.escape(simbolo)}{extra}</small></td>"
                  f"<td>{num(d['prezzo'])} {val}</td>"
                  f'<td class="{classe}">{var}</td>'
                  f"<td>{intervallo(d['min_g'], d['max_g'])}</td><td>{intervallo(d['min_52'], d['max_52'])}</td>"
                  f"<td>{ultimo}</td></tr>")
    return ('<div class="scorri"><table class="borsa"><tr><th>Titolo</th><th>Prezzo</th><th>Var. giorno</th>'
            f'<th>Min–Max giorno</th><th>Min–Max 52 sett.</th><th>Ultimo dato</th></tr>{righe}</table></div>')


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
li.urgente{border-left:5px solid #d33}
.notizie li a{font-size:1.4rem;font-weight:700;line-height:1.25}.notizie .fonte{font-size:1.05rem}
.giornale{color:var(--sub);font-size:.85rem}
.su{color:#1a8f3c;font-weight:700}.giu{color:#d33;font-weight:700}
th{text-align:left;font-size:.8rem;color:var(--sub)}.borsa td{white-space:nowrap;vertical-align:top}
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
<h2>Prossimi esami</h2>
__ESAMI__
<h2>Accadde oggi</h2>
__ACCADDE__
<h2>Notizie di economia</h2>
__NOTIZIE__
<h2>Dati di borsa</h2>
__BORSA__
<p class="sub">Meteo: Open-Meteo.com. Notizie: Google News (titoli e link). Borsa: Yahoo Finance (per i titoli italiani prezzi di Borsa Italiana, in genere con circa 15 minuti di ritardo); dati indicativi, non sono consigli di investimento. Per i dati ufficiali usa i link Borsa Italiana.</p>
</main></body></html>"""


def main():
    ora = datetime.now(ZoneInfo("Europe/Rome"))
    data = f"{GIORNI[ora.weekday()]} {ora:%d/%m/%Y %H:%M}"
    meteo = "".join(scheda_meteo(n, la, lo, ora) for n, (la, lo) in LUOGHI.items())
    pagina = MODELLO.replace("__DATA__", data).replace("__METEO__", meteo).replace("__LEZIONI__", lezioni(ora)).replace("__ESAMI__", esami(ora)).replace("__ACCADDE__", accadde_oggi(ora)).replace("__NOTIZIE__", notizie()).replace("__BORSA__", borsa())
    os.makedirs("sito", exist_ok=True)
    with open("sito/index.html", "w", encoding="utf-8") as f:
        f.write(pagina)
    print("Pagina generata.")


if __name__ == "__main__":
    main()
