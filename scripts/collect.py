#!/usr/bin/env python3
"""Recolhe notícias RSS e evita atribuir automaticamente notícias estrangeiras ao país da pesquisa."""
import json, re, time, hashlib
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "RadarIndustrial/1.1 (public RSS reader)"}

SECTORS = [
    ("Plásticos e injeção", ["plasturgie", "plastique", "plástico", "plásticos", "inyección", "injection plastique", "injeção", "extrusion", "extrusão"]),
    ("Automóvel", ["automobile", "automotive", "automoción", "automóvel", "voiture", "car parts", "auto parts"]),
    ("Moldes e ferramentas", ["moule", "moldes", "molde", "mould", "tooling", "ferramentaria", "ferramentas"]),
    ("Metalomecânica", ["métallurgie", "metalomecânica", "metalworking", "usinage", "mecanizado", "mecânica"]),
    ("Aeronáutica", ["aéronautique", "aeronautique", "aeronáutica", "aerospace", "aviation"]),
    ("Embalagem", ["emballage", "packaging", "embalagem"]),
    ("Energia e logística", ["énergie", "energia", "logistique", "logística", "logistics", "renewable"]),
]

# Indícios explícitos de localização. Não se usa apenas o país do feed para
# classificar uma notícia que mencione claramente outro mercado.
COUNTRY_MARKERS = {
    "Portugal": ["portugal", "lisboa", "porto", "braga", "guimarães", "aveiro", "leiria", "setúbal", "sines", "viseu", "coimbra", "faro", "viana do castelo", "vila nova de gaia", "palmela", "o nosso país"],
    "França": ["france", "frança", "paris", "lyon", "marseille", "toulouse", "bordeaux", "lille", "nantes", "strasbourg", "rennes", "grenoble", "dunkerque", "clermont-ferrand"],
    "Espanha": ["españa", "spain", "espanha", "madrid", "barcelona", "valencia", "zaragoza", "bilbao", "vigo", "valladolid", "castellón", "castellon", "andalucía", "cataluña", "navarra"],
    "Marrocos": ["maroc", "morocco", "marrocos", "tanger", "tangier", "casablanca", "rabat", "kenitra", "kénitra", "agadir", "marrakech", "fès", "fez", "nouaceur"],
    "Tunísia": ["tunisie", "tunisia", "tunísia", "tunis", "sfax", "sousse", "monastir", "bizerte", "gabès", "gabes"],
}
FOREIGN_MARKERS = [
    "brasil", "brazil", "brasileira", "brasileiro", "são paulo", "sao paulo", "minas gerais",
    "united states", "états-unis", "estados unidos", "usa", "china", "chinese", "deutschland",
    "germany", "alemania", "italia", "italy", "romania", "poland", "polónia", "polonia",
    "turkey", "turquía", "turquia", "india", "japan", "mexico", "méxico", "argentina",
]

def classify(text, feed_country):
    low = text.casefold()
    hits = [country for country, markers in COUNTRY_MARKERS.items() if any(m in low for m in markers)]
    if len(hits) == 1:
        country = hits[0]
    elif len(hits) > 1:
        country = feed_country if feed_country in hits else "Por confirmar"
    elif any(m in low for m in FOREIGN_MARKERS):
        country = "Internacional"
    else:
        country = feed_country
    sector = "Indústria geral"
    for label, terms in SECTORS:
        if any(term in low for term in terms):
            sector = label
            break
    return country, sector

def parse_date(value):
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat() if value else None
    except Exception:
        return None

def resolve_url(url):
    # Evita pedidos adicionais em massa; o link RSS original continua funcional.
    return url

def main():
    config = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    output = ROOT / "data/news.json"
    seen, items = set(), []
    for query in config["queries"]:
        url = "https://news.google.com/rss/search?q=" + quote(query["q"]) + "&hl=" + query["hl"] + "&gl=" + query["gl"] + "&ceid=" + query["ceid"]
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=20) as response:
                xml = response.read()
            root = ET.fromstring(xml)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = item.findtext("description") or ""
                summary = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", desc)).strip()
                source = item.find("source")
                publisher = (source.text or "").strip() if source is not None else "Google News RSS"
                published = parse_date(item.findtext("pubDate"))
                if not title or not link:
                    continue
                country, sector = classify(" ".join([title, summary, publisher]), query["country"])
                clean_title = re.sub(r"\s[-–|]\s" + re.escape(publisher) + r"\s*$", "", title, flags=re.I).strip()
                key = link.split("&")[0]
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "id": hashlib.sha1((clean_title + link).encode()).hexdigest()[:14],
                    "title": clean_title, "url": link, "published": published,
                    "publisher": publisher, "country": country, "sector": sector,
                    "summary": summary[:650], "verification": "A validar"
                })
        except (URLError, HTTPError, ET.ParseError, TimeoutError) as exc:
            print(f"Feed falhou ({query['country']}): {exc}")
        except Exception as exc:
            print(f"Erro inesperado ({query['country']}): {exc}")
        time.sleep(1)
    items.sort(key=lambda item: item.get("published") or "", reverse=True)
    items = items[:1000]
    output.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Concluído: {len(items)} registos guardados.")

if __name__ == "__main__":
    main()
