#!/usr/bin/env python3
"""Build a static normalized catalog from permitted public metadata sources."""
from __future__ import annotations
import argparse, ipaddress, json, logging, socket, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

LOG=logging.getLogger("cinenova-bridge")
TIMEOUT=20
MAX_BYTES=8*1024*1024
UA="CineNovaCatalogBridge/1.0 metadata-importer"

def validate_url(url):
    p=urlparse(url)
    if p.scheme not in ("http","https") or not p.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are accepted")
    host=p.hostname.lower()
    if host=="localhost" or host.endswith((".localhost",".local")):
        raise ValueError("Local destinations are blocked")
    for item in socket.getaddrinfo(host,None):
        ip=ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private/reserved network destinations are blocked")

def fetch(url):
    validate_url(url)
    # Redirects are intentionally disabled to avoid silently following unvalidated destinations.
    r=requests.get(url,headers={"User-Agent":UA,"Accept":"application/json,text/html;q=0.9"},
                   timeout=TIMEOUT,stream=True,allow_redirects=False)
    try:
        if 300<=r.status_code<400:
            raise ValueError("Redirect blocked; configure the final source URL explicitly")
        r.raise_for_status()
        chunks=[]; size=0
        for chunk in r.iter_content(65536):
            size+=len(chunk)
            if size>MAX_BYTES: raise ValueError("Response exceeds 8 MiB limit")
            chunks.append(chunk)
        return b"".join(chunks).decode(r.encoding or "utf-8",errors="replace")
    finally: r.close()

def path_get(obj,path):
    cur=obj
    if not path: return cur
    for part in path.split("."):
        if isinstance(cur,dict): cur=cur.get(part)
        elif isinstance(cur,list) and part.isdigit():
            i=int(part); cur=cur[i] if i<len(cur) else None
        else: return None
    return cur

def textval(v):
    if v is None or isinstance(v,(dict,list)): return None
    s=" ".join(str(v).split()).strip()
    return s or None

def urlval(v,base):
    s=textval(v)
    if not s: return None
    u=urljoin(base,s)
    try: validate_url(u); return u
    except Exception: return None

def normalize(raw,source,base):
    title=textval(raw.get("title"))
    if not title: return None
    kind=(textval(raw.get("type")) or "movie").lower()
    if kind in ("tv","tv_channel","channel","live"): kind="channel"
    if kind not in ("movie","series","anime","channel"): kind="movie"
    genres=raw.get("genres") or []
    if isinstance(genres,str): genres=[x.strip() for x in genres.split(",")]
    if not isinstance(genres,list): genres=[]
    reviews=raw.get("reviews")
    if not isinstance(reviews,list): reviews=[]
    # Keep only actual source-supplied review text and author/date/rating fields.
    clean_reviews=[]
    for rev in reviews:
        if isinstance(rev,dict) and textval(rev.get("text")):
            clean_reviews.append({k:rev.get(k) for k in ("author","rating","date","text") if rev.get(k) is not None})
    seasons=raw.get("seasons") if isinstance(raw.get("seasons"),list) else []
    episodes=raw.get("episodes") if isinstance(raw.get("episodes"),list) else []
    rid=textval(raw.get("id")) or title.casefold().replace(" ","-")
    item={
      "id":f"{source}:{rid}","source":source,"type":kind,"title":title,
      "year":textval(raw.get("year")),"release_date":textval(raw.get("release_date")),
      "overview":textval(raw.get("overview")),
      "poster_url":urlval(raw.get("poster"),base),
      "backdrop_url":urlval(raw.get("backdrop"),base),
      "banner_url":urlval(raw.get("banner"),base),
      "logo_url":urlval(raw.get("logo"),base),
      "genres":[textval(x) for x in genres if textval(x)],
      "rating":textval(raw.get("rating")),
      "review_count":textval(raw.get("review_count")),
      "reviews":clean_reviews,
      "detail_url":urlval(raw.get("detail_url"),base),
      "seasons":seasons,"episodes":episodes,
      "channel_number":textval(raw.get("channel_number")),
      "language":textval(raw.get("language")),
      "country":textval(raw.get("country")),
      # Never infer that metadata artwork is a playable video.
      "playback":{"available":False,"provider":None}
    }
    return item

def html_value(node,selector):
    if not selector: return None
    if "@" in selector:
        css,attr=selector.rsplit("@",1)
        found=node.select_one(css)
        return found.get(attr) if found else None
    found=node.select_one(selector)
    return found.get_text(" ",strip=True) if found else None

def scrape(source):
    body=fetch(source["url"])
    name=source["name"]
    if source["kind"]=="json":
        payload=json.loads(body)
        rows=path_get(payload,source.get("items_path"))
        if not isinstance(rows,list): raise ValueError("items_path must resolve to a JSON array")
        mapping=source.get("fields",{})
        raw_items=[{key:path_get(row,path) for key,path in mapping.items()}
                   for row in rows if isinstance(row,dict)]
    elif source["kind"]=="html":
        soup=BeautifulSoup(body,"html.parser")
        selectors=source.get("selectors",{})
        if not selectors.get("item"): raise ValueError("HTML source needs selectors.item")
        raw_items=[]
        for node in soup.select(selectors["item"]):
            raw_items.append({k:html_value(node,v) for k,v in selectors.items() if k!="item"})
    else: raise ValueError("kind must be json or html")
    out=[]
    for raw in raw_items:
        item=normalize(raw,name,source["url"])
        if item: out.append(item)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default="sources.json")
    ap.add_argument("--output",default="public/catalog.json")
    args=ap.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
    all_items=[]; statuses=[]
    for src in cfg.get("sources",[]):
        name=src.get("name","unnamed")
        try:
            items=scrape(src); all_items.extend(items)
            statuses.append({"source":name,"status":"ok","items":len(items)})
            LOG.info("%s: %d records",name,len(items))
        except Exception as e:
            statuses.append({"source":name,"status":"error","items":0,"message":str(e)})
            LOG.error("%s: %s",name,e)
    unique={}
    for item in all_items:
        key=(item["type"],item["title"].casefold(),item.get("year") or "")
        unique.setdefault(key,item)
    catalog={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
             "source_count":len(cfg.get("sources",[])),"item_count":len(unique),
             "sources":statuses,"items":list(unique.values())}
    dest=Path(args.output); dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    LOG.info("Wrote %d records to %s",len(unique),dest)
    return 1 if any(s["status"]=="error" for s in statuses) else 0
if __name__=="__main__": sys.exit(main())
