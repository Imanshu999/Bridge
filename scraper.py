#!/usr/bin/env python3
"""Build CineNova's real metadata catalog from TMDB, AniList and iptv-org."""
from __future__ import annotations
import json, logging, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests

LOG = logging.getLogger("bridge")
OUT = Path("public/catalog.json")
TMDB = "https://api.themoviedb.org/3"
ANILIST = "https://graphql.anilist.co"
IPTV = "https://iptv-org.github.io/api"
IMG = "https://image.tmdb.org/t/p"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CineNovaBridge/1.0 (+https://github.com/Imanshu999/Bridge)", "Accept": "application/json"})
TIMEOUT = 25

def get_json(url, *, params=None, headers=None):
    r = SESSION.get(url, params=params, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def post_graphql(query, variables=None):
    r = SESSION.post(ANILIST, json={"query": query, "variables": variables or {}},
                     headers={"Content-Type":"application/json","Accept":"application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError("AniList GraphQL returned errors")
    return payload["data"]

def tmdb_get(path, token, params=None):
    headers = {"Authorization": "Bearer " + token, "accept": "application/json"}
    return get_json(TMDB + path, params=params, headers=headers)

def tmdb_image(path, size="w500"):
    return IMG + "/" + size + path if path else None

def clean_text(value):
    if value is None: return None
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value or None

def tmdb_item(x, kind, token):
    is_movie = kind == "movie"
    title = x.get("title") if is_movie else x.get("name")
    date = x.get("release_date") if is_movie else x.get("first_air_date")
    item = {
        "id": f"tmdb:{kind}:{x['id']}", "source": "TMDB", "source_id": x["id"],
        "type": "movie" if is_movie else "series", "title": title,
        "original_title": x.get("original_title") if is_movie else x.get("original_name"),
        "overview": clean_text(x.get("overview")), "release_date": date,
        "year": date[:4] if date else None, "rating": x.get("vote_average"),
        "vote_count": x.get("vote_count"), "genres": [],
        "poster_url": tmdb_image(x.get("poster_path")),
        "backdrop_url": tmdb_image(x.get("backdrop_path"), "w1280"),
        "banner_url": tmdb_image(x.get("backdrop_path"), "w1280"),
        "logo_url": None, "detail_url": f"https://www.themoviedb.org/{kind}/{x['id']}",
        "reviews": [], "review_count": 0, "cast": [], "crew": [],
        "seasons": [], "episodes": [],
        "playback": {"available": False, "provider": None}
    }
    return item

def enrich_tmdb(item, token):
    kind = "movie" if item["type"] == "movie" else "tv"
    ident = item["source_id"]
    try:
        details = tmdb_get(f"/{kind}/{ident}", token, {"append_to_response":"credits"})
        item["genres"] = [g["name"] for g in details.get("genres", [])]
        item["runtime"] = details.get("runtime") or (details.get("episode_run_time") or [None])[0]
        item["status"] = details.get("status")
        item["original_language"] = details.get("original_language")
        item["production_countries"] = [c.get("name") for c in details.get("production_countries", [])]
        credits = details.get("credits", {})
        item["cast"] = [{"name":c.get("name"),"character":c.get("character"),"profile_url":tmdb_image(c.get("profile_path"),"w185")} for c in credits.get("cast", [])[:12]]
        item["crew"] = [{"name":c.get("name"),"job":c.get("job")} for c in credits.get("crew", []) if c.get("job") in ("Director","Writer","Screenplay")][:8]
        if kind == "tv":
            item["seasons"] = []
            for season in details.get("seasons", []):
                sn = season.get("season_number")
                season_item = {"id":season.get("id"),"season_number":sn,"name":season.get("name"),
                               "episode_count":season.get("episode_count"),"overview":clean_text(season.get("overview")),
                               "poster_url":tmdb_image(season.get("poster_path")),"episodes":[]}
                if sn is not None and sn >= 0:
                    try:
                        season_data = tmdb_get(f"/tv/{ident}/season/{sn}", token, {"language":"en-US"})
                        season_item["episodes"] = [{"id":ep.get("id"),"episode_number":ep.get("episode_number"),
                            "name":ep.get("name"),"overview":clean_text(ep.get("overview")),
                            "air_date":ep.get("air_date"),"runtime":ep.get("runtime"),
                            "still_url":tmdb_image(ep.get("still_path"),"w500")} for ep in season_data.get("episodes", [])]
                    except Exception as exc:
                        LOG.warning("Season episode import failed for %s season %s: %s", ident, sn, exc)
                item["seasons"].append(season_item)
        # Real user-submitted reviews returned by TMDB; never fabricate them.
        review_data = tmdb_get(f"/{kind}/{ident}/reviews", token, {"language":"en-US","page":1})
        item["reviews"] = [{
            "id":rv.get("id"), "author":rv.get("author"),
            "author_details": {"name":rv.get("author_details",{}).get("name"),"rating":rv.get("author_details",{}).get("rating")},
            "created_at":rv.get("created_at"), "text":clean_text(rv.get("content")),
            "url":rv.get("url"), "source":"TMDB"
        } for rv in review_data.get("results", [])[:10]]
        item["review_count"] = review_data.get("total_results", 0)
    except Exception as exc:
        LOG.warning("TMDB detail/review enrichment failed for %s: %s", item["id"], exc)
    return item

def build_tmdb(token):
    items=[]
    if not token:
        LOG.warning("TMDB_API_READ_ACCESS_TOKEN is missing; movie/series and TMDB reviews are skipped.")
        return items
    for kind in ("movie","tv"):
        for category in ("trending","popular","top_rated"):
            try:
                data=tmdb_get(f"/{category}/{kind}/week" if category=="trending" else f"/{kind}/{category}",
                              token, {"language":"en-US","page":1})
                for row in data.get("results",[])[:24]:
                    if row.get("id") and (row.get("title") or row.get("name")):
                        items.append(tmdb_item(row,kind,token))
            except Exception as exc:
                LOG.error("TMDB %s %s fetch failed: %s",kind,category,exc)
    # Deduplicate before costly detail/review calls; enrich up to 60 entries per type.
    unique={}
    for item in items: unique.setdefault(item["id"],item)
    enriched=[]
    per_type={"movie":0,"series":0}
    for item in unique.values():
        if per_type[item["type"]] < 60:
            enriched.append(enrich_tmdb(item,token))
            per_type[item["type"]]+=1
            time.sleep(0.12)
        else: enriched.append(item)
    return enriched

ANILIST_QUERY = """
query {
  Page(page: 1, perPage: 50) {
    media(type: ANIME, sort: TRENDING_DESC, isAdult: false) {
      id
      title { romaji english native }
      description(asHtml: false)
      type
      format
      status
      startDate { year month day }
      season
      seasonYear
      episodes
      duration
      averageScore
      meanScore
      popularity
      genres
      coverImage { extraLarge large }
      bannerImage
      siteUrl
    }
  }
}
"""

def build_anime():
    data=post_graphql(ANILIST_QUERY)
    items=[]
    for a in data.get("Page",{}).get("media",[]):
        title=a.get("title") or {}
        start=a.get("startDate") or {}
        year=start.get("year")
        items.append({
            "id":f"anilist:anime:{a['id']}","source":"AniList","source_id":a["id"],
            "type":"anime","title":title.get("english") or title.get("romaji") or title.get("native"),
            "original_title":title.get("native"),"romaji_title":title.get("romaji"),
            "overview":clean_text(a.get("description")),"release_date":None,"year":year,
            "rating":(a.get("averageScore") or 0)/10 if a.get("averageScore") else None,
            "vote_count":None,"genres":a.get("genres") or [],
            "poster_url":(a.get("coverImage") or {}).get("extraLarge") or (a.get("coverImage") or {}).get("large"),
            "backdrop_url":a.get("bannerImage"),"banner_url":a.get("bannerImage"),
            "logo_url":None,"detail_url":a.get("siteUrl"),
            "format":a.get("format"),"status":a.get("status"),"season":a.get("season"),
            "season_year":a.get("seasonYear"),"episodes_count":a.get("episodes"),
            "episode_duration_minutes":a.get("duration"),
            "reviews":[],"review_count":None,"cast":[],"crew":[],"seasons":[],"episodes":[],
            "playback":{"available":False,"provider":None}
        })
    return items

def build_channels():
    channels=get_json(IPTV+"/channels.json")
    logos=get_json(IPTV+"/logos.json")
    guides=get_json(IPTV+"/guides.json")
    logo_map={}
    for logo in logos if isinstance(logos,list) else []:
        if logo.get("channel") and logo.get("url") and logo["channel"] not in logo_map:
            logo_map[logo["channel"]]=logo["url"]
    guide_map={}
    for guide in guides if isinstance(guides,list) else []:
        if guide.get("channel"):
            guide_map.setdefault(guide["channel"],[]).append({
                "site":guide.get("site"),"site_name":guide.get("site_name"),
                "language":guide.get("lang"),"sources":guide.get("sources",[])
            })
    out=[]
    for c in channels if isinstance(channels,list) else []:
        if c.get("closed") or c.get("is_nsfw"): continue
        out.append({
            "id":"iptv-org:"+str(c.get("id")),"source":"iptv-org","source_id":c.get("id"),
            "type":"channel","title":c.get("name"),"alternative_names":c.get("alt_names",[]),
            "network":c.get("network"),"owners":c.get("owners",[]),
            "country":c.get("country"),"categories":c.get("categories",[]),
            "launched":c.get("launched"),"website":c.get("website"),
            "logo_url":logo_map.get(c.get("id")),"poster_url":logo_map.get(c.get("id")),
            "backdrop_url":None,"banner_url":None,"language_codes":[],
            "epg_sources":guide_map.get(c.get("id"),[]),
            "playback":{"available":False,"provider":None}
        })
    return out

def main():
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    token=os.getenv("TMDB_API_READ_ACCESS_TOKEN","").strip()
    sources=[]; items=[]
    jobs=[("anime",build_anime),("tv_channels",build_channels)]
    for name,fn in jobs:
        try:
            batch=fn(); items.extend(batch); sources.append({"name":name,"status":"ok","count":len(batch)})
            LOG.info("%s: %d records",name,len(batch))
        except Exception as exc:
            sources.append({"name":name,"status":"error","count":0,"error":str(exc)})
            LOG.exception("%s source failed",name)
    try:
        batch=build_tmdb(token); items.extend(batch)
        sources.append({"name":"tmdb_movies_tv_reviews","status":"ok" if token else "needs_secret","count":len(batch)})
        LOG.info("TMDB: %d records",len(batch))
    except Exception as exc:
        sources.append({"name":"tmdb_movies_tv_reviews","status":"error","count":0,"error":str(exc)})
        LOG.exception("TMDB source failed")
    # Stable IDs and source-provided records only.
    unique={}
    for item in items:
        if item.get("id") and item.get("title"):
            unique.setdefault(item["id"],item)
    result={
        "schema_version":2,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "source_count":len(sources),
        "item_count":len(unique),
        "counts":{kind:sum(1 for x in unique.values() if x.get("type")==kind)
                  for kind in ("movie","series","anime","channel")},
        "sources":sources,
        "items":list(unique.values()),
        "attribution":{
            "TMDB":"This product uses the TMDB API but is not endorsed or certified by TMDB.",
            "AniList":"Anime metadata supplied by AniList.",
            "iptv-org":"Channel metadata supplied by iptv-org."
        }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    LOG.info("Wrote %d real metadata records to %s",len(unique),OUT)
    # Fail only if every configured upstream failed; missing TMDB secret is surfaced clearly.
    if all(s["status"]=="error" for s in sources): return 1
    return 0

if __name__=="__main__":
    sys.exit(main())
