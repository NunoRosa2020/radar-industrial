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

def classify(title, summary, feed_country):
    # O país indicado pela pesquisa RSS é apenas o mercado de pesquisa,
    # nunca prova a localização da notícia. O título tem prioridade.
    def matches(text, marker_map):
        low = text.casefold()
        return [country for country, markers in marker_map.items()
                if any(re.search(r"(?<![\\w])" + re.escape(m) + r"(?![\\w])", low) for m in markers)]

    title_hits = matches(title, COUNTRY_MARKERS)
    summary_hits = matches(summary, COUNTRY_MARKERS)
    title_foreign = any(m in title.casefold() for m in FOREIGN_MARKERS)

    if len(title_hits) == 1:
        country = title_hits[0]
    elif len(title_hits) > 1:
        country = "Por confirmar"
    elif title_foreign:
        country = "Internacional"
    elif len(summary_hits) == 1:
        country = summary_hits[0]
    elif len(summary_hits) > 1:
        country = "Por confirmar"
    else:
        # Não herdar cegamente o país do feed: é precisamente a origem
        # de falsos destaques nacionais em notícias internacionais.
        country = "Por confirmar"

    combined = (title + " " + summary).casefold()
    sector = "Indústria geral"
    for label, terms in SECTORS:
        if any(term in combined for term in terms):
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
                country, sector = classify(title, summary, query["country"])
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
