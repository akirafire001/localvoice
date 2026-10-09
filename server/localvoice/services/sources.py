"""Material collection for runtime knowledge generation (realtime-llm-design §3.2).

Programmatic fetches from Wikipedia (ja/en), Wikidata and OpenStreetMap (Overpass, Nominatim) come before the LLM.
Fetched text is data; it is passed to the LLM as material, never as instructions.
"""
import logging
import re
import time

import requests
from flask import current_app

log = logging.getLogger(__name__)

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
WIKI_LICENSE = "CC BY-SA 4.0 (Wikipedia)"
OSM_LICENSE = "ODbL (OpenStreetMap contributors)"
WIKIDATA_LICENSE = "CC0 (Wikidata)"
# Nominatim address keys that hold a town (町・大字) name in Japan, most specific first
TOWN_KEYS = ("neighbourhood", "quarter", "village", "hamlet")
# Elsewhere a district of a city is usually a suburb or city_district; a small place is the town itself
TOWN_KEYS_ABROAD = ("neighbourhood", "quarter", "suburb", "city_district", "village", "hamlet", "town", "city")
# Wikipedia in the local language, besides ja and en, for towns abroad (ISO 3166 country code → wiki language)
LOCAL_WIKI = {
    "kr": "ko", "cn": "zh", "tw": "zh", "hk": "zh", "mo": "zh", "th": "th", "vn": "vi", "id": "id", "my": "ms",
    "ph": "tl", "in": "hi", "fr": "fr", "be": "fr", "lu": "fr", "mc": "fr", "de": "de", "at": "de", "ch": "de",
    "it": "it", "sm": "it", "va": "it", "es": "es", "mx": "es", "ar": "es", "cl": "es", "co": "es", "pe": "es",
    "pt": "pt", "br": "pt", "nl": "nl", "se": "sv", "no": "no", "dk": "da", "fi": "fi", "is": "is", "pl": "pl",
    "cz": "cs", "sk": "sk", "hu": "hu", "ro": "ro", "bg": "bg", "gr": "el", "hr": "hr", "si": "sl", "rs": "sr",
    "ru": "ru", "ua": "uk", "tr": "tr", "il": "he", "eg": "ar", "ae": "ar", "sa": "ar", "ma": "ar", "jo": "ar",
}
CHOME_RE = re.compile(r"[0-9０-９一二三四五六七八九十]+丁目$")


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


def _town_of(address):
    """(town, municipality) from a Nominatim address, e.g. 尻手二丁目 → ("尻手", "神奈川県横浜市鶴見区").
    Abroad, e.g. マレ地区 in パリ → ("マレ地区", "パリ、イル＝ド＝フランス")."""
    if (address.get("country_code") or "jp") != "jp":
        name = next((address[k] for k in TOWN_KEYS_ABROAD if address.get(k)), None)
        if not name:
            return None
        parts = [address.get(k) for k in ("city", "town", "county", "state")]
        municipality = "、".join(dict.fromkeys(p for p in parts if p and p != name))
        return (name.strip(), municipality or (address.get("country") or ""))
    name = next((address[k] for k in TOWN_KEYS if address.get(k)), None)
    if not name:
        return None
    town = CHOME_RE.sub("", name.strip()).strip()
    parts = [address.get(k) for k in ("province", "state", "city", "county", "town", "suburb")]
    municipality = "".join(dict.fromkeys(p for p in parts if p and p != name))
    return (town, municipality) if town else None


def town_materials(lat, lon, bbox):
    """Towns (町・大字) in the cell via Nominatim reverse geocoding, one material per town.

    Samples the center and four inner points of the cell, one request per second (Nominatim usage policy).
    Each material also carries `town`, `municipality`, `country_code` (ISO 3166, lower case) and `country` (its
    name in Japanese) for the local-history web search and the country-wide manners.
    """
    cfg = current_app.config["LV"]
    if not cfg.SOURCE_FETCH_ENABLED:
        return []
    s = _session()
    south, west, north, east = bbox
    dlat, dlon = (north - south) / 4, (east - west) / 4
    points = [(lat, lon), (lat + dlat, lon - dlon), (lat + dlat, lon + dlon), (lat - dlat, lon - dlon), (lat - dlat, lon + dlon)]
    towns = {}
    for i, (plat, plon) in enumerate(points):
        if i:
            time.sleep(1.0)
        try:
            r = s.get(
                f"{cfg.NOMINATIM_URL}/reverse",
                params={"lat": plat, "lon": plon, "format": "jsonv2", "zoom": 16, "accept-language": "ja"},
                timeout=10,
            )
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("nominatim reverse failed: %s", e)
            continue
        address = data.get("address") or {}
        found = _town_of(address)
        if not found or found in towns:
            continue
        town, municipality = found
        url = (f"https://www.openstreetmap.org/{data['osm_type']}/{data['osm_id']}"
               if data.get("osm_type") and data.get("osm_id")
               else f"https://www.openstreetmap.org/?mlat={plat:.5f}&mlon={plon:.5f}")
        towns[found] = {
            "kind": "osm", "title": f"{town}（{municipality}）", "url": url, "publisher": "OpenStreetMap",
            "lat": float(data.get("lat") or plat), "lon": float(data.get("lon") or plon),
            "text": f"町名: {town} / 所在地: {municipality}{town}", "license": OSM_LICENSE,
            "town": town, "municipality": municipality,
            "country_code": (address.get("country_code") or "jp").lower(), "country": address.get("country") or None,
        }
    return list(towns.values())


def collect_materials(lat, lon, bbox, country_code=None):
    """Returns a list of material dicts with stable ids m1..mN. Abroad, Wikipedia in the local language too."""
    cfg = current_app.config["LV"]
    if not cfg.SOURCE_FETCH_ENABLED:
        return []
    s = _session()
    mats = []
    mats += wikipedia_materials(s, "ja", lat, lon)
    mats += wikipedia_materials(s, "en", lat, lon, limit=5)
    local = LOCAL_WIKI.get((country_code or "").lower())
    if local:
        mats += wikipedia_materials(s, local, lat, lon, limit=5)
    mats += wikidata_materials(s, [m.get("wikidata") for m in mats])
    mats += osm_materials(s, bbox)
    for i, m in enumerate(mats, 1):
        m["id"] = f"m{i}"
        m.pop("wikidata", None)
    return mats
