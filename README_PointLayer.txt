PointLayer 1.3
==============

PURPOSE
-------
Download an entire public/queryable ArcGIS point layer, keep only the fields you want,
and build one offline file for ArcGIS Earth. No QGIS, ArcGIS Pro, GDAL, requests,
GeoPandas, or ArcPy is required.

The program uses Python 3 standard-library modules plus Tkinter.

SUPPORTED INPUT
---------------
Paste either the ArcGIS service root OR a specific point-layer URL:

  /FeatureServer
  /FeatureServer/<layer number>
  /MapServer
  /MapServer/<layer number>

If a service root contains one queryable point layer, PointLayer selects it automatically.
If it contains several point layers, PointLayer shows a small chooser. You do not need to
look up or guess the layer ID yourself.

Examples used during development:

Nassau County hydrants (service root; actual point layer is ID 458):
https://services5.arcgis.com/F73IhFZbCCYUexxB/arcgis/rest/services/Water_Hydrant/FeatureServer

Duval / JFRD-JEA hydrants (specific layer URL also remains supported):
https://maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/3

DISPLAY / WINDOW
----------------
Version 1.2 keeps the progress/status/BUILD bar fixed at the bottom of the window.
The service, fields, output, and style sections scroll above it, so Windows display
scaling or a short laptop screen cannot hide the BUILD button.

WORKFLOW
--------
1. Run PointLayer.bat.
2. Paste the FeatureServer/MapServer service root or a specific layer URL.
3. Click Read Service. If several point layers are available, choose one from the list.
4. Choose the fields to keep.
5. Choose an output folder and base filename.
6. Choose KMZ, GeoJSON, or both.
7. For KMZ choose a built-in marker or your own PNG, icon scale, and LOD cutoff.
8. Click BUILD.

The program requests the complete Object ID list first, then retrieves the points in
safe batches using outSR=4326. It does not crop to the current screen or require a
manual bounding box. The final KML Region is calculated from the downloaded points.

ARC GIS EARTH / LOD
-------------------
LOD is intentionally adjustable because point density varies dramatically.

Field-tested starting references:
  Nassau hydrants: 3,250 points -> LOD 12,000
  Duval hydrants: 30,688 points -> LOD 30,000

PointLayer proposes a starting LOD from feature count. Treat it as a starting value,
not a universal law. Raise the value if dense symbols appear too early; lower it if
the layer appears too late.

The KMZ contains its icon locally, so the marker does not depend on an Internet-hosted
icon after creation.

OUTPUT BEHAVIOR
---------------
KMZ:
- One complete point layer.
- User-selected attributes remain attached to each point.
- Built-in Red dot, Blue dot, Yellow dot, and Red H (hydrant) icons.
- Custom PNG supported.
- Labels hidden by default.
- LOD controls when the layer becomes visible while the layer itself remains checked.

GeoJSON:
- One FeatureCollection containing the same selected fields and point geometry.
- Styling is not embedded; viewers choose their own point symbol.

IMPORTANT
---------
PointLayer downloads what the source service publishes. Public accessibility does not
mean every publisher grants identical redistribution rights. Users remain responsible
for source licensing, attribution, data freshness, accuracy, and permitted reuse.

A source service can also change fields, URLs, limits, or availability without notice.
