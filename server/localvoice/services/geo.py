"""Plain geometry helpers (no LLM): distance, bearing, geohash, relative direction."""
import math

EARTH_R = 6371008.8
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def angle_diff(a, b):
    """Signed difference b - a in (-180, 180]."""
    d = (b - a + 180) % 360 - 180
    return 180.0 if d == -180 else d


def destination(lat, lon, bearing, distance_m):
    br = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    dr = distance_m / EARTH_R
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(p1), math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def relative_direction(course_deg, target_bearing):
    """ahead / right / left / behind relative to the direction of travel."""
    d = angle_diff(course_deg, target_bearing)
    if abs(d) <= 45:
        return "ahead"
    if abs(d) >= 135:
        return "behind"
    return "right" if d > 0 else "left"


def geohash_encode(lat, lon, precision=6):
    lat_r, lon_r = [-90.0, 90.0], [-180.0, 180.0]
    bits, bit, ch, even = [], 0, 0, True
    out = []
    while len(out) < precision:
        rng, val = (lon_r, lon) if even else (lat_r, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            ch |= 1 << (4 - bit)
            rng[0] = mid
        else:
            rng[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_BASE32[ch])
            bit, ch = 0, 0
    del bits
    return "".join(out)


def geohash_bbox(gh):
    lat_r, lon_r = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for c in gh:
        cd = _BASE32.index(c)
        for mask in (16, 8, 4, 2, 1):
            rng = lon_r if even else lat_r
            mid = (rng[0] + rng[1]) / 2
            if cd & mask:
                rng[0] = mid
            else:
                rng[1] = mid
            even = not even
    return lat_r[0], lon_r[0], lat_r[1], lon_r[1]


def geohash_center(gh):
    s, w, n, e = geohash_bbox(gh)
    return (s + n) / 2, (w + e) / 2


# Transport classes (mvp-technical-design §9) and PoC search radii (§5)
MANUAL_TO_CLASS = {
    "walk": "walking",
    "bicycle": "cycling",
    "car": "motorized",
    "train": "motorized",
    "shinkansen": "high_speed",
    "ship": "motorized",
    "other": "walking",
}
SEARCH_RADIUS_M = {
    "stationary": 500,
    "walking": 700,
    "cycling": 1500,
    "motorized": 5000,
    "high_speed": 12000,
}
LOOKAHEAD_M = {"stationary": 0, "walking": 600, "cycling": 1500, "motorized": 5000, "high_speed": 15000}


def transport_class(client_mode, manual_mode=None, speed_mps=None):
    if manual_mode and manual_mode != "auto":
        return MANUAL_TO_CLASS.get(manual_mode, "walking")
    if client_mode in SEARCH_RADIUS_M:
        return client_mode
    if speed_mps is None:
        return "walking"
    if speed_mps < 0.5:
        return "stationary"
    if speed_mps < 2.5:
        return "walking"
    if speed_mps < 7:
        return "cycling"
    if speed_mps < 45:
        return "motorized"
    return "high_speed"
