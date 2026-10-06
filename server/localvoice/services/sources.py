"""Material collection for runtime knowledge generation (realtime-llm-design §3.2).

Programmatic fetches from Wikipedia (ja/en), Wikidata and OpenStreetMap (Overpass) come before the LLM.
Fetched text is data; it is passed to the LLM as material, never as instructions.
"""
import logging

import requests
from flask import current_app

log = logging.getLogger(__name__)

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
WIKI_LICENSE = "CC BY-SA 4.0 (Wikipedia)"
OSM_LICENSE = "ODbL (OpenStreetMap contributors)"
WIKIDATA_LICENSE = "CC0 (Wikidata)"


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = current_app.config["LV"].HTTP_USER_AGENT
    return s


def wikipedia_materials(s, lang, lat, lon, radius=3000, limit=8):
    try:
        r = s.get(
            WIKI_API.format(lang=lang),
            params={
                "action": "query", "format": "json", "list": "geosearch",
                "gscoord": f"{lat}|{lon}", "gsradius": min(radius, 10000), "gslimit": limit,
            },
            timeout=10,
        )
        pages = r.json().get("query", {}).get("geosearch", [])
        if not pages:
            return []
        ids = "|".join(str(p["pageid"]) for p in pages)
        r = s.get(
            WIKI_API.format(lang=lang),
            params={
                "action": "query", "format": "json", "pageids": ids, "prop": "extracts|pageprops|info",
                "exintro": 0, "explaintext": 1, "exchars": 2500, "inprop": "url",
            },
            timeout=15,
        )
        details = r.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError) as e:
        log.warning("wikipedia fetch failed: %s", e)
        return []
    out = []
    for p in pages:
        d = details.get(str(p["pageid"]), {})
        text = (d.get("extract") or "").strip()
        if len(text) < 80:
            continue
        out.append({
            "kind": f"wikipedia_{lang}",
            "title": p["title"],
            "url": d.get("fullurl") or f"https://{lang}.wikipedia.org/?curid={p['pageid']}",
            "publisher": f"Wikipedia ({lang})",
            "lat": p["lat"], "lon": p["lon"],
            "text": text,
            "license": WIKI_LICENSE,
            "wikidata": (d.get("pageprops") or {}).get("wikibase_item"),
        })
    return out


def wikidata_materials(s, qids):
    qids = [q for q in qids if q][:20]
    if not qids:
        return []
    try:
        r = s.get(
            WIKIDATA_API,
            params={"action": "wbgetentities", "ids": "|".join(qids), "format": "json",
                    "props": "labels|descriptions|claims", "languages": "ja|en"},
            timeout=15,
        )
        ents = r.json().get("entities", {})
    except (requests.RequestException, ValueError) as e:
        log.warning("wikidata fetch failed: %s", e)
        return []
    out = []
    for qid, e in ents.items():
        labels = e.get("labels", {})
        desc = e.get("descriptions", {})
        facts = []
        claims = e.get("claims", {})
        # inception (P571), architect (P84), heritage designation (P1435), named after (P138)
        for pid, name in (("P571", "inception"), ("P1435", "heritage_designation"), ("P138", "named_after"), ("P84", "architect")):
            for c in claims.get(pid, [])[:2]:
                v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(v, dict) and "time" in v:
                    facts.append(f"{name}: {v['time'][1:11]}")
                elif isinstance(v, dict) and "id" in v:
                    facts.append(f"{name}: {v['id']}")
        text = " / ".join(
            x for x in [
                (labels.get("ja") or {}).get("value"), (desc.get("ja") or {}).get("value"),
                (labels.get("en") or {}).get("value"), (desc.get("en") or {}).get("value"), *facts,
            ] if x
        )
        if text:
            out.append({
                "kind": "wikidata", "title": (labels.get("ja") or labels.get("en") or {}).get("value", qid),
                "url": f"https://www.wikidata.org/wiki/{qid}", "publisher": "Wikidata",
                "text": text, "license": WIKIDATA_LICENSE,
            })
    return out


def osm_materials(s, bbox, limit=25):
    south, west, north, east = bbox
    q = f"""[out:json][timeout:20];
(
  nwr["historic"]["name"]({south},{west},{north},{east});
  nwr["amenity"="place_of_worship"]["name"]({south},{west},{north},{east});
  nwr["natural"~"peak|water|bay|cape|spring"]["name"]({south},{west},{north},{east});
  nwr["man_made"="bridge"]["name"]({south},{west},{north},{east});
  nwr["waterway"="river"]["name"]({south},{west},{north},{east});
  nwr["tourism"~"attraction|museum|viewpoint"]["name"]({south},{west},{north},{east});
);
out center tags {limit};"""
    try:
        r = s.post(OVERPASS_API, data={"data": q}, timeout=25)
        elements = r.json().get("elements", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("overpass fetch failed: %s", e)
        return []
    out = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        keep = {k: v for k, v in tags.items() if k in (
            "name", "name:en", "name:ja-Hira", "historic", "amenity", "religion", "denomination", "natural",
            "man_made", "waterway", "tourism", "heritage", "start_date", "description", "wikipedia", "ele")}
        out.append({
            "kind": "osm", "title": tags.get("name"),
            "url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}", "publisher": "OpenStreetMap",
            "lat": lat, "lon": lon, "text": "; ".join(f"{k}={v}" for k, v in keep.items()),
            "license": OSM_LICENSE,
        })
    return out


def collect_materials(lat, lon, bbox):
    """Returns a list of material dicts with stable ids m1..mN."""
    cfg = current_app.config["LV"]
    if not cfg.SOURCE_FETCH_ENABLED:
        return []
    s = _session()
    mats = []
    mats += wikipedia_materials(s, "ja", lat, lon)
    mats += wikipedia_materials(s, "en", lat, lon, limit=5)
    mats += wikidata_materials(s, [m.get("wikidata") for m in mats])
    mats += osm_materials(s, bbox)
    for i, m in enumerate(mats, 1):
        m["id"] = f"m{i}"
        m.pop("wikidata", None)
    return mats
