#!/usr/bin/env python3
"""Recolhe notícias de feeds Google News RSS sem API paga."""
import json,re,time,hashlib
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
HEADERS={"User-Agent":"RadarIndustrial/1.0 (public RSS reader)"}
SECTORS=[("Plásticos e injeção",["plasturgie","plastique","plástico","plásticos","inyección","injection plastique","injeção","extrusion","extrusão"]),("Automóvel",["automobile","automotive","automoción","automóvel","voiture","car parts","auto parts"]),("Moldes e ferramentas",["moule","moldes","molde","mould","tooling","ferramentaria","ferramentas"]),("Metalomecânica",["métallurgie","metalomecânica","metalworking","usinage","mecanizado","mecânica"]),("Aeronáutica",["aéronautique","aeronautique","aeronáutica","aerospace","aviation"]),("Embalagem",["emballage","packaging","embalagem"]),("Energia e logística",["énergie","energia","logistique","logística","logistics","renewable"])]
def classify(text,country):
 low=text.lower();sector="Indústria geral"
 for label,terms in SECTORS:
  if any(t in low for t in terms):sector=label;break
 return country,sector
def parse_date(value):
 try:return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat() if value else None
 except Exception:return None
def resolve_url(url):
 try:
  req=Request(url,headers=HEADERS,method="GET")
  with urlopen(req,timeout=12) as r:return r.geturl() if r.geturl().startswith("http") else url
 except Exception:return url
def main():
 config=json.loads((ROOT/"sources.json").read_text(encoding="utf-8"));output=ROOT/"data/news.json"
 try:existing=json.loads(output.read_text(encoding="utf-8")).get("items",[])
 except Exception:existing=[]
 seen=set();items=[]
 for n in existing:
  key=n.get("url") or n.get("title","").lower()
  if key and key not in seen:seen.add(key);items.append(n)
 for query in config["queries"]:
  url="https://news.google.com/rss/search?q="+quote(query["q"])+"&hl="+query["hl"]+"&gl="+query["gl"]+"&ceid="+query["ceid"]
  try:
   req=Request(url,headers=HEADERS)
   with urlopen(req,timeout=20) as response:xml=response.read()
   root=ET.fromstring(xml)
   for item in root.findall(".//item"):
    title=(item.findtext("title") or "").strip();link=(item.findtext("link") or "").strip();desc=item.findtext("description") or ""
    summary=re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",desc)).strip()
    source=item.find("source");publisher=(source.text or "").strip() if source is not None else "Google News RSS";published=parse_date(item.findtext("pubDate"))
    if not title or not link:continue
    final_url=resolve_url(link);key=final_url if "news.google.com" not in final_url else hashlib.sha1(title.lower().encode()).hexdigest()
    if key in seen:continue
    seen.add(key);country,sector=classify(title+" "+summary,query["country"])
    clean_title=re.sub(r"\\s[-–|]\\s"+re.escape(publisher)+r"\\s*$","",title,flags=re.I).strip()
    items.append({"id":hashlib.sha1((clean_title+final_url).encode()).hexdigest()[:14],"title":clean_title,"url":final_url,"published":published,"publisher":publisher,"country":country,"sector":sector,"summary":summary[:650],"verification":"A validar"})
  except (URLError,HTTPError,ET.ParseError,TimeoutError) as e:print(f"Feed falhou ({query['country']}): {e}")
  except Exception as e:print(f"Erro inesperado: {e}")
  time.sleep(1)
 items.sort(key=lambda x:x.get("published") or "",reverse=True);items=items[:1000]
 output.write_text(json.dumps({"updated_at":datetime.now(timezone.utc).isoformat(),"items":items},ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"Concluído: {len(items)} registos guardados.")
if __name__=="__main__":main()