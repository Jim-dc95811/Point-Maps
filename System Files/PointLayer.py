"""PointLayer 2.1

2.1 re-hardening (2026-11-08) - a layer with no dates, no code lists and no empty points
is written exactly as by 2.0:
  - a point the server sends with no location ("NaN" or blank) is counted as "no location"
    instead of breaking the whole layer (NaN made the layer's Region invalid, so ArcGIS
    Earth drew none of the points; a blank one stopped the build)
  - date fields show as a date (2021-07-01) in the KMZ popup instead of 1625097600000
  - fields with a code list (domain) show the meaning ("Pressure") instead of the code
    (GeoJSON keeps the raw values)
  - URLs copied from the browser with ?f=pjson or /query on the end are accepted
  - the default output folder is the Desktop Windows really shows (OneDrive)
  - a login page or other non-map answer gets a plain message
  - the mouse wheel over the field list scrolls the list; Scale / Show below accept 12,000
    and say which box is wrong
  - bigger markers by default (Scale 1.0, was 0.5)
  - optional ground marker: a disc of N metres on the ground under each point (default on,
    4 m). An icon stays the same size on the screen; the disc grows as you zoom in, like a
    QGIS symbol sized in map units. Click it for the same popup.
  - "Show below (ft)" replaces "LOD cutoff": the eye alt in feet below which the points
    show. The pixel LOD is worked out from it and the size of the layer, so a small layer
    no longer needs you right on top of it. The suggestion keeps the old one for big layers
    (Nassau, Duval) and is at least 10,000 ft. 0 or blank = always show.

2.0 = 1.4 (2.0 Reference, 2026-11-08).

PointLayer 1.4

1.4 hardening (discovery, field selection, batching, LOD suggestion, icons and the
KMZ/GeoJSON layout unchanged from 1.3):
  - every requested object ID is checked; missing features are asked for once more
    and any still missing are reported (the layer is still written)
  - characters that are illegal in XML are removed from KML text, so one bad record
    can no longer make the whole KMZ unreadable
  - the KML Region gets a non-zero size when all points share a latitude or longitude
  - points without a location are counted and reported instead of dropped silently
  - asks before replacing an existing output; files are written as .partial first
  - a custom icon must really be a PNG
"""
import json
import math
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from xml.sax.saxutils import escape

APP_NAME = "PointLayer"
VERSION = "2.1"
TIMEOUT = 90
RETRIES = 3
DEFAULT_PRECISION = 7
MAX_BATCH = 2000

RECOMMENDED_KEYWORDS = (
    "address", "addr", "owner", "type", "description", "desc", "name",
    "id", "latitude", "longitude", "lat", "lon", "long", "status",
    "flow", "pressure", "size", "zone", "agency", "facility", "source",
)


NOT_MAP_DATA = ("The server did not send map data. It may need a login, or this is not an ArcGIS REST "
                "service URL (it should end in /FeatureServer or /MapServer, maybe with a layer number).")


def desktop_dir():
    """The Desktop folder Windows really shows (it may have been moved into OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
            # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                        (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                path = buf.value
                ctypes.windll.ole32.CoTaskMemFree(buf)
                if path and Path(path).is_dir():
                    return Path(path)
        except Exception:
            pass
    return Path.home() / "Desktop"


def _request(url, params, retry_callback=None):
    data = urllib.parse.urlencode(params).encode("utf-8")
    last_error = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "User-Agent": f"{APP_NAME}/{VERSION}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json, */*",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                raw = response.read()
            try:
                result = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise RuntimeError(NOT_MAP_DATA) from None
            if isinstance(result, dict) and "error" in result:
                err = result["error"]
                if isinstance(err, dict):
                    msg = err.get("message", "ArcGIS service error")
                    details = err.get("details") or []
                    if details:
                        msg += " — " + "; ".join(str(x) for x in details)
                else:
                    msg = str(err)
                raise RuntimeError(msg)
            return result
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ConnectionError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < RETRIES:
                if retry_callback:
                    retry_callback(attempt + 2, RETRIES, exc)
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def query_endpoint(layer_url):
    return layer_url.rstrip("/") + "/query"


def normalize_service_url(url):
    """Accept either a service root or a specific ArcGIS layer URL."""
    url = url.strip()
    # 2.1: URLs copied from the browser - drop ?f=pjson / #... and a trailing /query.
    url = re.split(r"[?#]", url, maxsplit=1)[0].rstrip("/")
    url = re.sub(r"/query$", "", url, flags=re.I).rstrip("/")
    match = re.search(r"/(FeatureServer|MapServer)(?:/(\d+))?$", url, re.I)
    if not match:
        raise ValueError(
            "Paste an ArcGIS FeatureServer or MapServer URL.\n\n"
            "Accepted examples:\n"
            "  https://server/.../FeatureServer\n"
            "  https://server/.../FeatureServer/458\n"
            "  https://server/.../MapServer\n"
            "  https://server/.../MapServer/3"
        )
    service_type = match.group(1)
    layer_id = int(match.group(2)) if match.group(2) is not None else None
    root_url = url[:match.start()] + f"/{service_type}"
    return root_url, layer_id


def validate_point_layer_meta(meta):
    if meta.get("geometryType") != "esriGeometryPoint":
        raise ValueError(
            "PointLayer requires a point layer. "
            f"Service reports: {meta.get('geometryType') or 'unknown geometry'}"
        )
    fields = meta.get("fields") or []
    if not fields:
        raise ValueError("The service reported no fields.")
    capabilities = str(meta.get("capabilities") or "")
    if capabilities and "query" not in capabilities.lower():
        raise ValueError("The layer does not advertise Query capability.")
    return meta


def discover_point_layers(url, retry_callback=None):
    """Return queryable point layers from a service root or one explicit layer."""
    root_url, layer_id = normalize_service_url(url)

    if layer_id is not None:
        layer_url = f"{root_url}/{layer_id}"
        meta = _request(layer_url, {"f": "json"}, retry_callback=retry_callback)
        validate_point_layer_meta(meta)
        return [(layer_url, meta)]

    service_meta = _request(root_url, {"f": "json"}, retry_callback=retry_callback)
    advertised = service_meta.get("layers") or []
    if not advertised:
        raise ValueError("The service root reported no layers.")

    candidates = []
    failures = []
    for entry in advertised:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        try:
            lid = int(entry["id"])
            layer_url = f"{root_url}/{lid}"
            meta = _request(layer_url, {"f": "json"}, retry_callback=retry_callback)
            if meta.get("geometryType") != "esriGeometryPoint":
                continue
            fields = meta.get("fields") or []
            capabilities = str(meta.get("capabilities") or "")
            if not fields or (capabilities and "query" not in capabilities.lower()):
                continue
            candidates.append((layer_url, meta))
        except Exception as exc:
            failures.append(f"{entry.get('name', entry.get('id'))}: {exc}")

    if not candidates:
        detail = ""
        if failures:
            detail = "\n\nSome advertised layers could not be inspected:\n" + "\n".join(failures[:5])
        raise ValueError("No queryable point layers were found in this service." + detail)
    return candidates


def read_service(layer_url, retry_callback=None):
    meta = _request(layer_url, {"f": "json"}, retry_callback=retry_callback)
    return validate_point_layer_meta(meta)


def query_count(layer_url, retry_callback=None):
    data = _request(
        query_endpoint(layer_url),
        {"f": "json", "where": "1=1", "returnCountOnly": "true"},
        retry_callback=retry_callback,
    )
    return int(data.get("count") or 0)


def query_object_ids(layer_url, retry_callback=None):
    data = _request(
        query_endpoint(layer_url),
        {
            "f": "json",
            "where": "1=1",
            "returnIdsOnly": "true",
            "returnGeometry": "false",
        },
        retry_callback=retry_callback,
    )
    ids = data.get("objectIds") or []
    return list(ids), data.get("objectIdFieldName")


def _is_transient(exc):
    text = str(exc).lower()
    markers = (
        "500", "502", "503", "504", "gateway", "timeout", "timed out",
        "remote end closed", "connection reset", "temporarily unavailable",
        "request entity too large", "uri too long",
    )
    return any(m in text for m in markers)


def _query_feature_batch(layer_url, ids, fields, precision, retry_callback=None):
    params = {
        "f": "json",
        "objectIds": ",".join(str(x) for x in ids),
        "outFields": ",".join(fields),
        "returnGeometry": "true",
        "outSR": "4326",
        "returnZ": "false",
        "returnM": "false",
        "geometryPrecision": str(precision),
    }
    data = _request(query_endpoint(layer_url), params, retry_callback=retry_callback)
    return data.get("features") or []


def query_feature_batch_resilient(layer_url, ids, fields, precision,
                                  status_callback=None, retry_callback=None):
    try:
        return _query_feature_batch(layer_url, ids, fields, precision, retry_callback)
    except RuntimeError as exc:
        if len(ids) <= 1 or not _is_transient(exc):
            raise
        mid = len(ids) // 2
        if status_callback:
            status_callback(
                f"Batch of {len(ids):,} failed ({exc}). Splitting into "
                f"{mid:,} + {len(ids)-mid:,}..."
            )
        left = query_feature_batch_resilient(
            layer_url, ids[:mid], fields, precision, status_callback, retry_callback
        )
        right = query_feature_batch_resilient(
            layer_url, ids[mid:], fields, precision, status_callback, retry_callback
        )
        return left + right


def download_all_features(layer_url, ids, oid_field, fields, batch_size, precision=DEFAULT_PRECISION,
                          status_callback=None, retry_callback=None, progress_callback=None):
    """Download every published feature and report any the service did not return.

    The object-ID field is always requested (only the chosen fields are written) so each
    returned feature can be matched to its ID. Missing IDs are requested once more.
    Returns (features, missing_ids)."""
    request_fields = list(fields)
    if oid_field and oid_field not in request_fields:
        request_fields.append(oid_field)
    count = len(ids)
    features = []
    for start in range(0, count, batch_size):
        batch = ids[start:start + batch_size]
        if status_callback:
            status_callback(f"Downloading points {start+1:,}-{min(start+len(batch), count):,} of {count:,}...")
        features.extend(query_feature_batch_resilient(
            layer_url, batch, request_fields, precision,
            status_callback=status_callback, retry_callback=retry_callback))
        if progress_callback:
            progress_callback(85.0 * min(1.0, (start + len(batch)) / count))

    if not oid_field:
        # Without an ID field only the totals can be compared.
        return features, [None] * max(0, count - len(features))

    def returned_ids(feats):
        found = set()
        for f in feats:
            value = (f.get("attributes") or {}).get(oid_field)
            if value is not None:
                found.add(str(value))
        return found

    seen = returned_ids(features)
    missing = [i for i in ids if str(i) not in seen]
    if missing:
        if status_callback:
            status_callback(f"{len(missing):,} features were not returned - asking for them once more...")
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            try:
                features.extend(query_feature_batch_resilient(
                    layer_url, batch, request_fields, precision,
                    status_callback=status_callback, retry_callback=retry_callback))
            except RuntimeError:
                pass   # reported below as still missing
        seen = returned_ids(features)
        missing = [i for i in ids if str(i) not in seen]
    return features, missing


# Show below (ft) <-> minLodPixels (2.1). Object Factory 1.2 calibration on Jim's screen
# (looking straight down): a flat 309.6 m box hides at altitude x minLodPixels = 1.85 million
# ft*px, i.e. about 5,967 ft*px per metre of box size (size = square root of its area).
LOD_FT_PX_PER_M = 1_790_000.0 / 300.0
MIN_SUGGEST_FT = 10000


def box_size_m(west, east, south, north):
    """Square root of the area of a lon/lat box, in metres."""
    lat = math.radians((north + south) / 2.0)
    w = abs(east - west) * 111_320.0 * max(math.cos(lat), 0.01)
    h = abs(north - south) * 110_574.0
    return math.sqrt(max(w * h, 1.0))


def lod_pixels_for_feet(feet, bounds):
    """minLodPixels for 'show below <feet> eye alt' on a layer with these Region bounds.
    0 = always show."""
    if not feet or feet <= 0:
        return 0
    return max(1, int(round(LOD_FT_PX_PER_M * box_size_m(*region_bounds(*bounds)) / feet)))


def suggest_show_below_ft(feature_count, bounds):
    """Feet that reproduce the old count-based LOD for this layer's size (so big county
    layers keep the accepted behaviour), never below MIN_SUGGEST_FT, rounded to 500 ft."""
    if not bounds:
        return MIN_SUGGEST_FT
    feet = LOD_FT_PX_PER_M * box_size_m(*region_bounds(*bounds)) / suggest_lod(feature_count)
    return int(max(MIN_SUGGEST_FT, round(feet / 500.0) * 500))


def query_extent(layer_url, retry_callback=None):
    """(west, east, south, north) of all features in WGS84, or None if the server cannot say."""
    try:
        data = _request(query_endpoint(layer_url),
                        {"f": "json", "where": "1=1", "returnExtentOnly": "true", "outSR": "4326"},
                        retry_callback=retry_callback)
        ext = data.get("extent") or {}
        vals = [float(ext[k]) for k in ("xmin", "xmax", "ymin", "ymax")]
        if all(math.isfinite(v) for v in vals) and -180 <= vals[0] <= vals[1] <= 180 and -90 <= vals[2] <= vals[3] <= 90:
            return tuple(vals)
    except Exception:
        pass
    return None


def suggest_lod(feature_count):
    """Empirical starting point anchored to proven Nassau and Duval tests."""
    if feature_count <= 0:
        return 12000
    # 3,250 points -> 12,000; 30,688 points -> about 30,000.
    exponent = 0.409
    value = 12000.0 * ((feature_count / 3250.0) ** exponent)
    value = max(6000.0, min(50000.0, value))
    return int(round(value / 1000.0) * 1000)


def sanitize_filename(text):
    text = re.sub(r'[<>:"/\\|?*]+', "_", str(text or "PointLayer"))
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text or "PointLayer"


# Characters XML 1.0 does not allow (old agency records often contain them).
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def xml_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return _XML_ILLEGAL.sub("", str(value))


def _png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


GROUND_COLORS = {"Red dot": (235, 35, 35), "Blue dot": (30, 105, 235), "Yellow dot": (245, 185, 20),
                 "Red H (hydrant)": (235, 35, 35)}


def kml_color(rgb, alpha=255):
    r, g, b = rgb
    return f"{alpha:02x}{b:02x}{g:02x}{r:02x}"


def ground_disc(lon, lat, diameter_m, sides=20):
    """Closed ring of a disc on the ground (lon,lat pairs) - 2.1 ground marker."""
    r = diameter_m / 2.0
    dlat = r / 110_574.0
    dlon = r / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    pts = []
    for i in range(sides + 1):
        a = 2 * math.pi * (i % sides) / sides
        pts.append(f"{lon + dlon * math.cos(a):.7f},{lat + dlat * math.sin(a):.7f},0")
    return " ".join(pts)


def make_icon_png(kind="red_dot", size=32):
    """Create a simple offline-safe RGBA PNG using only the standard library."""
    palette = {
        "red_dot": (235, 35, 35),
        "blue_dot": (30, 105, 235),
        "yellow_dot": (245, 185, 20),
        "red_h": (235, 35, 35),
    }
    color = palette.get(kind, palette["red_dot"])
    cx = cy = (size - 1) / 2.0
    r_outer = size * 0.44
    r_inner = size * 0.37
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            dist = math.hypot(x - cx, y - cy)
            if dist <= r_outer:
                if dist >= r_inner:
                    rgba = (255, 255, 255, 255)
                else:
                    rgba = (*color, 255)
                    if kind == "red_h":
                        # White block H with generous strokes for visibility at 0.5 scale.
                        left = int(size * 0.31) <= x <= int(size * 0.39)
                        right = int(size * 0.61) <= x <= int(size * 0.69)
                        cross = int(size * 0.46) <= y <= int(size * 0.55) and int(size * 0.31) <= x <= int(size * 0.69)
                        vert_range = int(size * 0.28) <= y <= int(size * 0.72)
                        if (left and vert_range) or (right and vert_range) or cross:
                            rgba = (255, 255, 255, 255)
            else:
                rgba = (0, 0, 0, 0)
            row.extend(rgba)
        rows.append(bytes(row))
    raw = b"".join(rows)
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return header + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")


def built_in_icon_bytes(symbol_name):
    mapping = {
        "Red dot": "red_dot",
        "Blue dot": "blue_dot",
        "Yellow dot": "yellow_dot",
        "Red H (hydrant)": "red_h",
    }
    return make_icon_png(mapping.get(symbol_name, "red_dot"))


def extract_point(feature):
    """(lon, lat), or None when the server sent no usable location - missing, blank, or the
    "NaN" ArcGIS uses for an empty point (2.1: NaN used to break the whole layer)."""
    geom = feature.get("geometry") or {}
    try:
        x, y = float(geom["x"]), float(geom["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return x, y


def display_value(value, field=None):
    """2.1: the text a KMZ popup shows for one value. Code-list (domain) fields show the
    meaning; date fields (milliseconds since 1970, UTC) show the date. Anything else, and
    every value without field information, is unchanged."""
    if field and value is not None:
        domain = field.get("domain") or {}
        if domain.get("type") == "codedValue":
            for cv in domain.get("codedValues") or []:
                if str(cv.get("code")) == str(value):
                    return cv.get("name")
        if field.get("type") == "esriFieldTypeDate" and isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return value
            # A date with no time (UTC midnight, or midnight in the Americas = 00:00-12:00 UTC
            # on the hour) shows as the date only; anything else keeps its time.
            if dt.minute == 0 and dt.second == 0 and dt.microsecond == 0 and dt.hour <= 12:
                return dt.strftime("%Y-%m-%d")
            return dt.strftime("%Y-%m-%d %H:%M UTC")
    return value


def calculate_bounds(features):
    points = [extract_point(f) for f in features]
    points = [p for p in points if p is not None]
    if not points:
        raise ValueError("No valid point geometries were returned.")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


MIN_REGION_DEG = 0.01  # about 1 km; used only when the points have no extent in a direction


def region_bounds(west, east, south, north):
    """Give the KML Region a non-zero size. With one point, or points that all share a
    latitude or longitude, the box would have zero area and could never reach the LOD
    pixel threshold, so the layer would never draw. Normal layers are unchanged."""
    lat_span, lon_span = north - south, east - west
    if lat_span > 0 and lon_span > 0:
        return west, east, south, north
    target = max(lat_span, lon_span, MIN_REGION_DEG)
    if lat_span <= 0:
        mid = (north + south) / 2.0
        south, north = max(-90.0, mid - target / 2.0), min(90.0, mid + target / 2.0)
    if lon_span <= 0:
        mid = (east + west) / 2.0
        west, east = max(-180.0, mid - target / 2.0), min(180.0, mid + target / 2.0)
    return west, east, south, north


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_png(path):
    try:
        with open(path, "rb") as f:
            return f.read(8) == _PNG_SIGNATURE
    except OSError:
        return False


def _partial(path):
    return path.with_name(path.name + ".partial")


def _finish(partial, path, ok):
    """Replace the real file only when writing succeeded; otherwise remove the partial."""
    if ok:
        os.replace(partial, path)
    else:
        try:
            partial.unlink()
        except OSError:
            pass


def write_geojson(path, features, fields, source_url, layer_name):
    out_features = []
    for feature in features:
        point = extract_point(feature)
        if point is None:
            geometry = None
        else:
            geometry = {"type": "Point", "coordinates": [point[0], point[1]]}
        attrs = feature.get("attributes") or {}
        out_features.append({
            "type": "Feature",
            "properties": {name: attrs.get(name) for name in fields},
            "geometry": geometry,
        })
    data = {
        "type": "FeatureCollection",
        "name": path.stem,
        "source": source_url,
        "layer": layer_name,
        "features": out_features,
    }
    partial, ok = _partial(path), False
    try:
        with partial.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        ok = True
    finally:
        _finish(partial, path, ok)


def write_kmz(path, features, fields, aliases, source_url, layer_name,
              lod_pixels, icon_scale, icon_bytes, hide_labels=True, field_meta=None,
              ground_m=None, ground_rgb=(235, 35, 35)):
    field_meta = field_meta or {}
    west, east, south, north = region_bounds(*calculate_bounds(features))
    label_scale = "0" if hide_labels else "1"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'<name>{escape(xml_text(layer_name))}</name>',
        '<Style id="point-style">',
        '<IconStyle>',
        f'<scale>{icon_scale:g}</scale>',
        '<Icon><href>icons/point.png</href></Icon>',
        '<hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>',
        '</IconStyle>',
        f'<LabelStyle><scale>{label_scale}</scale></LabelStyle>',
    ] + ([
        f'<LineStyle><color>ffffffff</color><width>1</width></LineStyle>',
        f'<PolyStyle><color>{kml_color(ground_rgb, 230)}</color><outline>1</outline></PolyStyle>',
    ] if ground_m else []) + [
        '</Style>',
        '<Folder>',
        f'<name>{escape(xml_text(layer_name))}</name>',
        '<Region>',
        '<LatLonAltBox>',
        f'<north>{north:.10f}</north><south>{south:.10f}</south>',
        f'<east>{east:.10f}</east><west>{west:.10f}</west>',
        '</LatLonAltBox>',
        '<Lod>',
        f'<minLodPixels>{int(lod_pixels)}</minLodPixels><maxLodPixels>-1</maxLodPixels>',
        '</Lod>',
        '</Region>',
    ]

    for feature in features:
        point = extract_point(feature)
        if point is None:
            continue
        lon, lat = point
        attrs = feature.get("attributes") or {}
        # Use first non-empty selected field as popup title, without enabling map labels.
        title = "Point"
        for field in fields:
            value = display_value(attrs.get(field), field_meta.get(field))
            if value not in (None, ""):
                title = xml_text(value)
                break
        lines.extend([
            '<Placemark>',
            f'<name>{escape(title)}</name>',
            '<styleUrl>#point-style</styleUrl>',
            '<ExtendedData>',
        ])
        for field in fields:
            alias = aliases.get(field) or field
            value = xml_text(display_value(attrs.get(field), field_meta.get(field)))
            lines.extend([
                f'<Data name="{escape(xml_text(field))}">',
                f'<displayName>{escape(xml_text(alias))}</displayName>',
                f'<value>{escape(value)}</value>',
                '</Data>',
            ])
        point_kml = ['<Point><altitudeMode>clampToGround</altitudeMode>',
                     f'<coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>']
        if ground_m:
            point_kml = (['</ExtendedData>', '<MultiGeometry>'] + point_kml +
                         ['<Polygon><tessellate>1</tessellate><altitudeMode>clampToGround</altitudeMode>'
                          '<outerBoundaryIs><LinearRing><coordinates>' + ground_disc(lon, lat, ground_m) +
                          '</coordinates></LinearRing></outerBoundaryIs></Polygon>', '</MultiGeometry>'])
        else:
            point_kml = ['</ExtendedData>'] + point_kml
        lines.extend(point_kml + ['</Placemark>'])

    lines.extend(['</Folder>', '</Document>', '</kml>'])
    kml = "\n".join(lines).encode("utf-8")
    partial, ok = _partial(path), False
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", kml)
            z.writestr("icons/point.png", icon_bytes)
        ok = True
    finally:
        _finish(partial, path, ok)


class PointLayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {VERSION}")
        # Fit comfortably on smaller/laptop displays and Windows scaling.
        sw = max(640, self.root.winfo_screenwidth())
        sh = max(480, self.root.winfo_screenheight())
        width = min(1000, max(760, sw - 120))
        height = min(680, max(520, sh - 140))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(680, 480)

        self.meta = None
        self.layer_url = None
        self.field_rows = []
        self.feature_count = 0

        self.url_var = tk.StringVar()
        self.service_var = tk.StringVar(value="No service loaded")
        self.count_var = tk.StringVar(value="Features: —")
        self.batch_var = tk.StringVar(value="Batch size: —")
        self.output_dir_var = tk.StringVar(value=str(desktop_dir()))
        self.output_name_var = tk.StringVar(value="PointLayer")
        self.kmz_var = tk.BooleanVar(value=True)
        self.geojson_var = tk.BooleanVar(value=False)
        self.symbol_var = tk.StringVar(value="Red dot")
        self.custom_icon_var = tk.StringVar()
        self.icon_scale_var = tk.StringVar(value="1.0")
        self.lod_var = tk.StringVar(value=str(MIN_SUGGEST_FT))   # 2.1: Show below (ft)
        self.ground_var = tk.BooleanVar(value=True)
        self.ground_m_var = tk.StringVar(value="4")
        self.hide_labels_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Paste a FeatureServer/MapServer service root or layer URL and click Read Service.")

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # Fixed bottom bar: BUILD is always reachable even on short displays.
        bottom = ttk.Frame(self.root)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 5))
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        self.build_btn = ttk.Button(bottom, text="BUILD", command=self.start_build, state="disabled")
        self.build_btn.pack(side="right", padx=(8, 0))

        # Scrollable work area above the fixed bottom bar.
        work = ttk.Frame(self.root)
        work.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(work, highlightthickness=0, borderwidth=0)
        vscroll = ttk.Scrollbar(work, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        main = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=main, anchor="nw")

        def refresh_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        main.bind("<Configure>", refresh_scrollregion)
        canvas.bind("<Configure>", fit_width)

        def mousewheel(event):
            # 2.1: over the field list, the list scrolls (not the whole page).
            tree = getattr(self, "tree", None)
            if tree is not None and str(event.widget).startswith(str(tree)):
                return None
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        canvas.bind_all("<MouseWheel>", mousewheel)

        ttk.Label(main, text=f"{APP_NAME} {VERSION}", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            main,
            text="Public ArcGIS point layer → selected fields → one offline ArcGIS Earth-ready KMZ",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        source = ttk.LabelFrame(main, text="1. ArcGIS point layer")
        source.pack(fill="x", **pad)
        row = ttk.Frame(source)
        row.pack(fill="x", padx=8, pady=8)
        ttk.Entry(row, textvariable=self.url_var).pack(side="left", fill="x", expand=True)
        self.read_btn = ttk.Button(row, text="Read Service", command=self.start_read_service)
        self.read_btn.pack(side="left", padx=(8, 0))
        info = ttk.Frame(source)
        info.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(info, textvariable=self.service_var).grid(row=0, column=0, sticky="w")
        ttk.Label(info, textvariable=self.count_var).grid(row=0, column=1, sticky="w", padx=(24, 0))
        ttk.Label(info, textvariable=self.batch_var).grid(row=0, column=2, sticky="w", padx=(24, 0))

        fields_frame = ttk.LabelFrame(main, text="2. Fields to keep")
        fields_frame.pack(fill="x", **pad)
        toolbar = ttk.Frame(fields_frame)
        toolbar.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Button(toolbar, text="Recommended", command=self.select_recommended).pack(side="left")
        ttk.Button(toolbar, text="All", command=self.select_all).pack(side="left", padx=4)
        ttk.Button(toolbar, text="None", command=self.select_none).pack(side="left")
        ttk.Label(toolbar, text="Click rows to toggle. OID fields are normally unnecessary.").pack(side="left", padx=12)

        tree_holder = ttk.Frame(fields_frame)
        tree_holder.pack(fill="x", padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(tree_holder, columns=("keep", "name", "alias", "type"), show="headings", height=8)
        self.tree.heading("keep", text="Keep")
        self.tree.heading("name", text="Field")
        self.tree.heading("alias", text="Alias")
        self.tree.heading("type", text="Type")
        self.tree.column("keep", width=55, anchor="center", stretch=False)
        self.tree.column("name", width=200)
        self.tree.column("alias", width=280)
        self.tree.column("type", width=160)
        scroll = ttk.Scrollbar(tree_holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.toggle_field)

        out = ttk.LabelFrame(main, text="3. Output")
        out.pack(fill="x", **pad)
        r1 = ttk.Frame(out); r1.pack(fill="x", padx=8, pady=(7, 3))
        ttk.Label(r1, text="Folder", width=12).pack(side="left")
        ttk.Entry(r1, textvariable=self.output_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(r1, text="Browse", command=self.choose_output_dir).pack(side="left", padx=(6, 0))
        r2 = ttk.Frame(out); r2.pack(fill="x", padx=8, pady=3)
        ttk.Label(r2, text="Base name", width=12).pack(side="left")
        ttk.Entry(r2, textvariable=self.output_name_var).pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(r2, text="KMZ", variable=self.kmz_var).pack(side="left", padx=8)
        ttk.Checkbutton(r2, text="GeoJSON", variable=self.geojson_var).pack(side="left")

        style = ttk.LabelFrame(main, text="4. ArcGIS Earth KMZ style")
        style.pack(fill="x", **pad)
        sr1 = ttk.Frame(style); sr1.pack(fill="x", padx=8, pady=(7, 3))
        ttk.Label(sr1, text="Symbol", width=12).pack(side="left")
        symbols = ["Red dot", "Blue dot", "Yellow dot", "Red H (hydrant)", "Custom PNG"]
        cb = ttk.Combobox(sr1, state="readonly", textvariable=self.symbol_var, values=symbols, width=20)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.update_custom_icon_state())
        ttk.Label(sr1, text="Scale").pack(side="left", padx=(18, 4))
        ttk.Entry(sr1, textvariable=self.icon_scale_var, width=8).pack(side="left")
        ttk.Label(sr1, text="Show below (ft)").pack(side="left", padx=(18, 4))
        ttk.Entry(sr1, textvariable=self.lod_var, width=9).pack(side="left")
        ttk.Checkbutton(sr1, text="Hide labels", variable=self.hide_labels_var).pack(side="left", padx=10)
        sr3 = ttk.Frame(style); sr3.pack(fill="x", padx=8, pady=3)
        ttk.Label(sr3, text="Ground marker", width=12).pack(side="left")
        ttk.Checkbutton(sr3, text="Disc on the ground", variable=self.ground_var).pack(side="left")
        ttk.Label(sr3, text="Size (m)").pack(side="left", padx=(18, 4))
        ttk.Entry(sr3, textvariable=self.ground_m_var, width=6).pack(side="left")
        ttk.Label(sr3, text="Grows as you zoom in (the icon stays the same size on the screen).").pack(side="left", padx=10)
        sr2 = ttk.Frame(style); sr2.pack(fill="x", padx=8, pady=(3, 7))
        ttk.Label(sr2, text="Custom icon", width=12).pack(side="left")
        self.custom_entry = ttk.Entry(sr2, textvariable=self.custom_icon_var, state="disabled")
        self.custom_entry.pack(side="left", fill="x", expand=True)
        self.custom_btn = ttk.Button(sr2, text="Browse PNG", command=self.choose_custom_icon, state="disabled")
        self.custom_btn.pack(side="left", padx=(6, 0))
        ttk.Label(sr2, text="Show below = eye alt in feet; suggested from the layer's size, change it freely. 0 = always.").pack(side="left", padx=10)

    def set_status(self, text):
        self.root.after(0, self.status_var.set, text)

    def set_progress(self, value):
        self.root.after(0, self.progress.configure, {"value": value})

    def retry_status(self, next_attempt, total, exc):
        self.set_status(f"Request failed ({exc}) — retry {next_attempt} of {total}...")

    def start_read_service(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror(APP_NAME, "Paste a FeatureServer/MapServer service root or layer URL first.")
            return
        self.read_btn.configure(state="disabled")
        self.build_btn.configure(state="disabled")
        self.set_status("Reading service metadata...")
        threading.Thread(target=self._read_service_worker, args=(url,), daemon=True).start()

    def _read_service_worker(self, url):
        try:
            candidates = discover_point_layers(url, self.retry_status)
            if len(candidates) == 1:
                layer_url, meta = candidates[0]
                self._finish_read_selected_layer(layer_url, meta)
            else:
                self.root.after(0, self._show_layer_chooser, candidates)
        except Exception as exc:
            self.root.after(0, messagebox.showerror, APP_NAME, str(exc))
            self.set_status("Service read failed.")
        finally:
            self.root.after(0, self.read_btn.configure, {"state": "normal"})

    def _finish_read_selected_layer(self, layer_url, meta):
        self.set_status("Counting features...")
        try:
            count = query_count(layer_url, self.retry_status)
            self.set_status("Measuring the layer...")
            extent = query_extent(layer_url, self.retry_status)
            self.root.after(0, self._apply_service, layer_url, meta, count, extent)
        except Exception as exc:
            self.root.after(0, messagebox.showerror, APP_NAME, str(exc))
            self.set_status("Service read failed.")
        finally:
            self.root.after(0, self.read_btn.configure, {"state": "normal"})

    def _show_layer_chooser(self, candidates):
        chooser = tk.Toplevel(self.root)
        chooser.title("Choose point layer")
        chooser.transient(self.root)
        chooser.grab_set()
        chooser.geometry("560x360")
        ttk.Label(chooser, text="This service contains more than one queryable point layer.").pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        ttk.Label(chooser, text="Choose the layer you want PointLayer to download:").pack(
            anchor="w", padx=12, pady=(0, 8)
        )
        frame = ttk.Frame(chooser)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        lb = tk.Listbox(frame, exportselection=False)
        sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for layer_url, meta in candidates:
            lid = layer_url.rstrip("/").split("/")[-1]
            lb.insert("end", f"[{lid}]  {meta.get('name') or 'Unnamed point layer'}")
        lb.selection_set(0)

        buttons = ttk.Frame(chooser)
        buttons.pack(fill="x", padx=12, pady=(0, 12))

        def choose():
            sel = lb.curselection()
            if not sel:
                return
            layer_url, meta = candidates[sel[0]]
            chooser.grab_release()
            chooser.destroy()
            self.read_btn.configure(state="disabled")
            threading.Thread(
                target=self._finish_read_selected_layer, args=(layer_url, meta), daemon=True
            ).start()

        ttk.Button(buttons, text="Cancel", command=chooser.destroy).pack(side="right")
        ttk.Button(buttons, text="Use Selected Layer", command=choose).pack(side="right", padx=(0, 8))
        lb.bind("<Double-Button-1>", lambda e: choose())
        self.set_status(f"Found {len(candidates)} queryable point layers — choose one.")

    def _apply_service(self, layer_url, meta, count, extent=None):
        self.layer_url = layer_url
        self.meta = meta
        self.feature_count = count
        name = meta.get("name") or "Point Layer"
        max_record = int(meta.get("maxRecordCount") or 1000)
        batch = max(1, min(max_record, MAX_BATCH))
        self.service_var.set(f"Layer: {name}")
        self.count_var.set(f"Features: {count:,}")
        self.batch_var.set(f"Batch size: {batch:,}")
        self.output_name_var.set(sanitize_filename(name))
        self.lod_var.set(f"{suggest_show_below_ft(count, extent):,}")

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.field_rows = []
        oid_name = meta.get("objectIdField") or meta.get("objectIdFieldName")
        for field in meta.get("fields") or []:
            name_f = field.get("name") or ""
            alias = field.get("alias") or name_f
            ftype = field.get("type") or ""
            keep = name_f != oid_name and self._field_recommended(name_f, alias, ftype)
            iid = self.tree.insert("", "end", values=("✓" if keep else "", name_f, alias, ftype))
            self.field_rows.append({"iid": iid, "name": name_f, "alias": alias, "type": ftype, "keep": keep})
        self.build_btn.configure(state="normal")
        self.status_var.set(
            f"Ready. Suggested: show below {self.lod_var.get()} ft for {count:,} points; adjust if desired."
        )

    def _field_recommended(self, name, alias, ftype):
        if str(ftype).lower().endswith("oid"):
            return False
        text = f"{name} {alias}".lower()
        return any(k in text for k in RECOMMENDED_KEYWORDS)

    def toggle_field(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        for row in self.field_rows:
            if row["iid"] == iid:
                row["keep"] = not row["keep"]
                vals = list(self.tree.item(iid, "values"))
                vals[0] = "✓" if row["keep"] else ""
                self.tree.item(iid, values=vals)
                return "break"

    def select_recommended(self):
        for row in self.field_rows:
            row["keep"] = self._field_recommended(row["name"], row["alias"], row["type"])
            vals = list(self.tree.item(row["iid"], "values")); vals[0] = "✓" if row["keep"] else ""
            self.tree.item(row["iid"], values=vals)

    def select_all(self):
        for row in self.field_rows:
            row["keep"] = True
            vals = list(self.tree.item(row["iid"], "values")); vals[0] = "✓"
            self.tree.item(row["iid"], values=vals)

    def select_none(self):
        for row in self.field_rows:
            row["keep"] = False
            vals = list(self.tree.item(row["iid"], "values")); vals[0] = ""
            self.tree.item(row["iid"], values=vals)

    def choose_output_dir(self):
        p = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.home()))
        if p:
            self.output_dir_var.set(p)

    def update_custom_icon_state(self):
        state = "normal" if self.symbol_var.get() == "Custom PNG" else "disabled"
        self.custom_entry.configure(state=state)
        self.custom_btn.configure(state=state)

    def choose_custom_icon(self):
        p = filedialog.askopenfilename(filetypes=[("PNG image", "*.png")])
        if p:
            self.custom_icon_var.set(p)

    def selected_fields(self):
        return [row["name"] for row in self.field_rows if row["keep"]]

    def aliases(self):
        return {row["name"]: row["alias"] for row in self.field_rows}

    def start_build(self):
        if not self.meta or not self.layer_url:
            messagebox.showerror(APP_NAME, "Read a service first.")
            return
        fields = self.selected_fields()
        if not fields:
            messagebox.showerror(APP_NAME, "Select at least one field to keep.")
            return
        if not self.kmz_var.get() and not self.geojson_var.get():
            messagebox.showerror(APP_NAME, "Select KMZ, GeoJSON, or both.")
            return
        try:
            scale = float(self.icon_scale_var.get().strip().replace(",", ""))
            if not (math.isfinite(scale) and scale > 0):
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, f"Scale: {self.icon_scale_var.get().strip()!r} - type a number above 0 (for example 0.5).")
            return
        try:
            text = self.lod_var.get().strip().replace(",", "")
            lod_f = float(text) if text else 0.0
            if not (math.isfinite(lod_f) and lod_f >= 0):
                raise ValueError
            lod = lod_f   # 2.1: feet (Show below); turned into pixels once the layer's size is known
        except ValueError:
            messagebox.showerror(APP_NAME, f"Show below (ft): {self.lod_var.get().strip()!r} - type the eye alt in feet, for example 10000 (0 = always show).")
            return
        ground_m = None
        if self.ground_var.get():
            try:
                ground_m = float(self.ground_m_var.get().strip().replace(",", ""))
                if not (math.isfinite(ground_m) and 0 < ground_m <= 1000):
                    raise ValueError
            except ValueError:
                messagebox.showerror(APP_NAME, f"Ground marker size (m): {self.ground_m_var.get().strip()!r} - type metres above 0, for example 4.")
                return
        output_dir = Path(self.output_dir_var.get()).expanduser()
        base = sanitize_filename(self.output_name_var.get())
        if not output_dir.exists():
            messagebox.showerror(APP_NAME, "Output folder does not exist.")
            return
        if self.symbol_var.get() == "Custom PNG" and self.kmz_var.get():
            custom = Path(self.custom_icon_var.get())
            if not custom.is_file():
                messagebox.showerror(APP_NAME, "Choose a custom PNG icon first.")
                return
            if not is_png(custom):
                messagebox.showerror(APP_NAME, f"{custom.name} is not a PNG image. Choose a .png icon.")
                return
        targets = []
        if self.kmz_var.get():
            targets.append(output_dir / f"{base}.kmz")
        if self.geojson_var.get():
            targets.append(output_dir / f"{base}.geojson")
        existing = [t for t in targets if t.exists()]
        if existing and not messagebox.askyesno(
                APP_NAME,
                "Already in " + str(output_dir) + ":\n\n" + "\n".join(t.name for t in existing) +
                "\n\nReplace?", icon="warning", default="no"):
            self.set_status("Not built - existing file kept.")
            return
        self.build_btn.configure(state="disabled")
        self.read_btn.configure(state="disabled")
        self.progress.configure(value=0)
        args = (fields, self.aliases(), output_dir, base, scale, lod, ground_m)
        threading.Thread(target=self._build_worker, args=args, daemon=True).start()

    def _build_worker(self, fields, aliases, output_dir, base, scale, lod, ground_m=None):
        try:
            self.set_status("Requesting all object IDs...")
            ids, oid_field = query_object_ids(self.layer_url, self.retry_status)
            if not ids:
                raise ValueError("The service returned zero point IDs.")
            count = len(ids)
            max_record = int(self.meta.get("maxRecordCount") or 1000)
            batch_size = max(1, min(max_record, MAX_BATCH))
            oid_field = oid_field or self.meta.get("objectIdField") or self.meta.get("objectIdFieldName")

            def retry_cb(next_attempt, total, exc):
                self.set_status(f"Feature request failed ({exc}) — retry {next_attempt} of {total}...")

            features, missing = download_all_features(
                self.layer_url, ids, oid_field, fields, batch_size, DEFAULT_PRECISION,
                status_callback=self.set_status, retry_callback=retry_cb,
                progress_callback=self.set_progress,
            )

            valid = sum(1 for f in features if extract_point(f) is not None)
            no_location = len(features) - valid
            if valid == 0:
                raise ValueError("No valid point geometries were downloaded.")
            layer_name = self.meta.get("name") or base
            written = []

            if self.kmz_var.get():
                self.set_status("Writing ArcGIS Earth KMZ...")
                if self.symbol_var.get() == "Custom PNG":
                    icon_bytes = Path(self.custom_icon_var.get()).read_bytes()
                else:
                    icon_bytes = built_in_icon_bytes(self.symbol_var.get())
                kmz_path = output_dir / f"{base}.kmz"
                lod_px = lod_pixels_for_feet(lod, calculate_bounds(features))
                write_kmz(
                    kmz_path, features, fields, aliases, self.layer_url, layer_name,
                    lod_px, scale, icon_bytes, self.hide_labels_var.get(),
                    field_meta={f.get("name"): f for f in (self.meta.get("fields") or [])},
                    ground_m=ground_m, ground_rgb=GROUND_COLORS.get(self.symbol_var.get(), (235, 35, 35)),
                )
                written.append(kmz_path)

            if self.geojson_var.get():
                self.set_status("Writing GeoJSON...")
                geo_path = output_dir / f"{base}.geojson"
                write_geojson(geo_path, features, fields, self.layer_url, layer_name)
                written.append(geo_path)

            self.set_progress(100)
            notes = []
            if missing:
                shown = ", ".join(str(m) for m in missing[:10] if m is not None)
                notes.append(
                    f"WARNING: {len(missing):,} of {count:,} published features were not returned by "
                    "the service, even after asking again. The layer was written without them." +
                    (f"\nMissing object IDs: {shown}" + (" ..." if len(missing) > 10 else "") if shown else ""))
            if no_location:
                notes.append(f"{no_location:,} records had no location in the service and were skipped.")
            msg = (
                f"{valid:,} of {count:,} published points written.\n\n" +
                ("\n\n".join(notes) + "\n\n" if notes else "") +
                "\n".join(str(p) for p in written)
            )
            if missing:
                self.set_status(f"Complete with warning — {valid:,} of {count:,} points written; {len(missing):,} not returned by the service.")
                self.root.after(0, messagebox.showwarning, APP_NAME, msg)
            else:
                self.set_status(f"Complete — {valid:,} points written.")
                self.root.after(0, messagebox.showinfo, APP_NAME, msg)
        except Exception as exc:
            self.set_status("Build failed.")
            self.root.after(0, messagebox.showerror, APP_NAME, str(exc))
        finally:
            self.root.after(0, self.build_btn.configure, {"state": "normal"})
            self.root.after(0, self.read_btn.configure, {"state": "normal"})


def run_self_test(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Synthetic points patterned after the two accepted hydrant workflows.
    features = [
        {"attributes": {"Type_": "Pressure", "NameofOwner": "Town of Test", "FULLADDRESS": "100 MAIN ST"},
         "geometry": {"x": -81.80, "y": 30.50}},
        {"attributes": {"Type_": "Dry", "NameofOwner": "County", "FULLADDRESS": "200 RIVER RD"},
         "geometry": {"x": -81.70, "y": 30.55}},
    ]
    fields = ["Type_", "NameofOwner", "FULLADDRESS"]
    aliases = {x: x for x in fields}
    kmz = output_dir / "PointLayer_SELF_TEST.kmz"
    geo = output_dir / "PointLayer_SELF_TEST.geojson"
    write_kmz(kmz, features, fields, aliases, "https://example/FeatureServer/0", "Self Test", 12000, 0.5,
              built_in_icon_bytes("Red H (hydrant)"), True)
    write_geojson(geo, features, fields, "https://example/FeatureServer/0", "Self Test")
    with zipfile.ZipFile(kmz, "r") as z:
        names = set(z.namelist())
        assert "doc.kml" in names and "icons/point.png" in names
        kml = z.read("doc.kml").decode("utf-8")
        assert kml.count("<Placemark>") == 2
        assert "<minLodPixels>12000</minLodPixels>" in kml
        assert "Town of Test" in kml
    loaded = json.loads(geo.read_text(encoding="utf-8"))
    assert len(loaded["features"]) == 2
    assert loaded["features"][0]["geometry"]["type"] == "Point"
    assert suggest_lod(3250) == 12000
    assert 29000 <= suggest_lod(30688) <= 31000
    root_url, layer_id = normalize_service_url("https://example.test/arcgis/rest/services/Hydrants/FeatureServer")
    assert root_url.endswith("/FeatureServer") and layer_id is None
    root_url, layer_id = normalize_service_url("https://example.test/arcgis/rest/services/Hydrants/FeatureServer/458")
    assert root_url.endswith("/FeatureServer") and layer_id == 458
    # 1.4: illegal XML characters removed; zero-area regions widened; PNG check.
    bad = [{"attributes": {"Type_": "Notes\x0bwith\x1acontrol", "NameofOwner": "A", "FULLADDRESS": "B"},
            "geometry": {"x": -81.80, "y": 30.50}}]
    kmz2 = output_dir / "PointLayer_SELF_TEST_control.kmz"
    write_kmz(kmz2, bad, fields, aliases, "https://example/FeatureServer/0", "Self Test", 12000, 0.5,
              built_in_icon_bytes("Red dot"), True)
    import xml.dom.minidom
    xml.dom.minidom.parseString(zipfile.ZipFile(kmz2).read("doc.kml"))
    w, e, s_, n = region_bounds(-81.8, -81.8, 30.5, 30.5)
    assert n > s_ and e > w
    assert region_bounds(-81.8, -81.7, 30.5, 30.55) == (-81.8, -81.7, 30.5, 30.55)
    assert is_png(output_dir / "PointLayer_SELF_TEST.kmz") is False
    assert not list(output_dir.glob("*.partial"))
    # 2.1: NaN / blank locations skipped; dates and code lists shown readably; browser URLs.
    odd = [{"attributes": {"Type_": "A", "NameofOwner": 1, "FULLADDRESS": 1625097600000}, "geometry": {"x": "NaN", "y": "NaN"}},
           {"attributes": {"Type_": "B", "NameofOwner": 1, "FULLADDRESS": 1625112000000}, "geometry": {"x": None, "y": None}},
           {"attributes": {"Type_": "C", "NameofOwner": 2, "FULLADDRESS": 1625112000000}, "geometry": {"x": -81.8, "y": 30.5}}]
    meta = {"NameofOwner": {"name": "NameofOwner", "type": "esriFieldTypeSmallInteger",
                            "domain": {"type": "codedValue", "codedValues": [{"name": "County", "code": 1}, {"name": "City", "code": 2}]}},
            "FULLADDRESS": {"name": "FULLADDRESS", "type": "esriFieldTypeDate"}}
    kmz3 = output_dir / "PointLayer_SELF_TEST_odd.kmz"
    write_kmz(kmz3, odd, fields, aliases, "u", "Self Test", 12000, 0.5, built_in_icon_bytes("Red dot"), True, field_meta=meta)
    k3 = zipfile.ZipFile(kmz3).read("doc.kml").decode("utf-8")
    assert k3.count("<Placemark>") == 1 and "nan" not in k3.lower() and "<value>City</value>" in k3 and "<value>2021-07-01</value>" in k3
    assert normalize_service_url("https://e.test/x/FeatureServer/458?f=pjson")[1] == 458
    assert normalize_service_url("https://e.test/x/FeatureServer/458/query?where=1%3D1")[1] == 458
    # 2.1: Show below (ft) and the ground marker.
    nassau_like = (-81.95, -81.25, 30.40, 30.75)
    ft = suggest_show_below_ft(3250, nassau_like)
    assert abs(lod_pixels_for_feet(ft, nassau_like) - 12000) / 12000 < 0.03
    assert suggest_show_below_ft(6, (-81.942, -81.935, 30.393, 30.401)) == MIN_SUGGEST_FT
    assert lod_pixels_for_feet(0, nassau_like) == 0
    kmz4 = output_dir / "PointLayer_SELF_TEST_ground.kmz"
    write_kmz(kmz4, features, fields, aliases, "u", "Self Test", 400, 1.0, built_in_icon_bytes("Red H (hydrant)"), True, ground_m=4)
    k4 = zipfile.ZipFile(kmz4).read("doc.kml").decode("utf-8")
    xml.dom.minidom.parseString(k4.encode("utf-8"))
    assert k4.count("<Polygon>") == 2 and k4.count("<MultiGeometry>") == 2 and "<PolyStyle><color>e62323eb</color>" in k4
    print("SELF TEST PASS")
    print(kmz)
    print(geo)


def main():
    import sys
    if "--self-test" in sys.argv:
        idx = sys.argv.index("--self-test")
        target = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "/mnt/data/pointlayer-self-test"
        run_self_test(target)
        return

    root = tk.Tk()
    app = PointLayerApp(root)
    if "--gui-smoke-test" in sys.argv:
        def check_and_close():
            root.update_idletasks()
            print("GUI_SMOKE_PASS" if root.winfo_ismapped() else "GUI_SMOKE_FAIL")
            root.destroy()
        root.after(500, check_and_close)
    root.mainloop()


if __name__ == "__main__":
    main()
