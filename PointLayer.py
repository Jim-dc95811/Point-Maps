import json
import math
import re
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from xml.sax.saxutils import escape

APP_NAME = "PointLayer"
VERSION = "1.3"
TIMEOUT = 90
RETRIES = 3
DEFAULT_PRECISION = 7
MAX_BATCH = 2000

RECOMMENDED_KEYWORDS = (
    "address", "addr", "owner", "type", "description", "desc", "name",
    "id", "latitude", "longitude", "lat", "lon", "long", "status",
    "flow", "pressure", "size", "zone", "agency", "facility", "source",
)


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
            result = json.loads(raw.decode("utf-8"))
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
    url = url.strip().rstrip("/")
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


def xml_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


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
    geom = feature.get("geometry") or {}
    if "x" not in geom or "y" not in geom:
        return None
    return float(geom["x"]), float(geom["y"])


def calculate_bounds(features):
    points = [extract_point(f) for f in features]
    points = [p for p in points if p is not None]
    if not points:
        raise ValueError("No valid point geometries were returned.")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


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
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def write_kmz(path, features, fields, aliases, source_url, layer_name,
              lod_pixels, icon_scale, icon_bytes, hide_labels=True):
    west, east, south, north = calculate_bounds(features)
    label_scale = "0" if hide_labels else "1"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'<name>{escape(layer_name)}</name>',
        '<Style id="point-style">',
        '<IconStyle>',
        f'<scale>{icon_scale:g}</scale>',
        '<Icon><href>icons/point.png</href></Icon>',
        '<hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>',
        '</IconStyle>',
        f'<LabelStyle><scale>{label_scale}</scale></LabelStyle>',
        '</Style>',
        '<Folder>',
        f'<name>{escape(layer_name)}</name>',
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
            value = attrs.get(field)
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
            value = xml_text(attrs.get(field))
            lines.extend([
                f'<Data name="{escape(field)}">',
                f'<displayName>{escape(alias)}</displayName>',
                f'<value>{escape(value)}</value>',
                '</Data>',
            ])
        lines.extend([
            '</ExtendedData>',
            '<Point><altitudeMode>clampToGround</altitudeMode>',
            f'<coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>',
            '</Placemark>',
        ])

    lines.extend(['</Folder>', '</Document>', '</kml>'])
    kml = "\n".join(lines).encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        z.writestr("icons/point.png", icon_bytes)


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
        self.output_dir_var = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.output_name_var = tk.StringVar(value="PointLayer")
        self.kmz_var = tk.BooleanVar(value=True)
        self.geojson_var = tk.BooleanVar(value=False)
        self.symbol_var = tk.StringVar(value="Red dot")
        self.custom_icon_var = tk.StringVar()
        self.icon_scale_var = tk.StringVar(value="0.50")
        self.lod_var = tk.StringVar(value="12000")
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
        ttk.Label(sr1, text="LOD cutoff").pack(side="left", padx=(18, 4))
        ttk.Entry(sr1, textvariable=self.lod_var, width=9).pack(side="left")
        ttk.Checkbutton(sr1, text="Hide labels", variable=self.hide_labels_var).pack(side="left", padx=10)
        sr2 = ttk.Frame(style); sr2.pack(fill="x", padx=8, pady=(3, 7))
        ttk.Label(sr2, text="Custom icon", width=12).pack(side="left")
        self.custom_entry = ttk.Entry(sr2, textvariable=self.custom_icon_var, state="disabled")
        self.custom_entry.pack(side="left", fill="x", expand=True)
        self.custom_btn = ttk.Button(sr2, text="Browse PNG", command=self.choose_custom_icon, state="disabled")
        self.custom_btn.pack(side="left", padx=(6, 0))
        ttk.Label(sr2, text="Suggested LOD is empirical and remains user-adjustable.").pack(side="left", padx=10)

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
            self.root.after(0, self._apply_service, layer_url, meta, count)
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

    def _apply_service(self, layer_url, meta, count):
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
        self.lod_var.set(str(suggest_lod(count)))

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
            f"Ready. Suggested LOD {self.lod_var.get()} from {count:,} points; adjust if desired."
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
            scale = float(self.icon_scale_var.get())
            lod = int(float(self.lod_var.get()))
            if scale <= 0:
                raise ValueError
            if lod < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Icon scale must be > 0 and LOD cutoff must be 0 or greater.")
            return
        output_dir = Path(self.output_dir_var.get()).expanduser()
        base = sanitize_filename(self.output_name_var.get())
        if not output_dir.exists():
            messagebox.showerror(APP_NAME, "Output folder does not exist.")
            return
        if self.symbol_var.get() == "Custom PNG":
            custom = Path(self.custom_icon_var.get())
            if not custom.is_file():
                messagebox.showerror(APP_NAME, "Choose a custom PNG icon first.")
                return
        self.build_btn.configure(state="disabled")
        self.read_btn.configure(state="disabled")
        self.progress.configure(value=0)
        args = (fields, self.aliases(), output_dir, base, scale, lod)
        threading.Thread(target=self._build_worker, args=args, daemon=True).start()

    def _build_worker(self, fields, aliases, output_dir, base, scale, lod):
        try:
            self.set_status("Requesting all object IDs...")
            ids, oid_field = query_object_ids(self.layer_url, self.retry_status)
            if not ids:
                raise ValueError("The service returned zero point IDs.")
            count = len(ids)
            max_record = int(self.meta.get("maxRecordCount") or 1000)
            batch_size = max(1, min(max_record, MAX_BATCH))
            features = []

            def retry_cb(next_attempt, total, exc):
                self.set_status(f"Feature request failed ({exc}) — retry {next_attempt} of {total}...")

            for start in range(0, count, batch_size):
                batch = ids[start:start + batch_size]
                done_before = len(features)
                self.set_status(
                    f"Downloading points {start+1:,}-{min(start+len(batch), count):,} of {count:,}..."
                )
                got = query_feature_batch_resilient(
                    self.layer_url, batch, fields, DEFAULT_PRECISION,
                    status_callback=self.set_status,
                    retry_callback=retry_cb,
                )
                features.extend(got)
                pct = 85.0 * min(1.0, (start + len(batch)) / count)
                self.set_progress(pct)

            valid = sum(1 for f in features if extract_point(f) is not None)
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
                write_kmz(
                    kmz_path, features, fields, aliases, self.layer_url, layer_name,
                    lod, scale, icon_bytes, self.hide_labels_var.get()
                )
                written.append(kmz_path)

            if self.geojson_var.get():
                self.set_status("Writing GeoJSON...")
                geo_path = output_dir / f"{base}.geojson"
                write_geojson(geo_path, features, fields, self.layer_url, layer_name)
                written.append(geo_path)

            self.set_progress(100)
            msg = (
                f"{valid:,} point records written.\n\n" +
                "\n".join(str(p) for p in written)
            )
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
