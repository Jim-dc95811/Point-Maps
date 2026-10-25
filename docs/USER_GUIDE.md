# PointLayer 1.3 User Guide

## Purpose

PointLayer converts a public/queryable ArcGIS point Feature Layer into one complete offline point overlay for ArcGIS Earth.

The program is intentionally narrow: it handles **point geometry**. It does not attempt to turn every GIS format or geometry type into one universal converter.

## Requirements

- Windows
- Python 3 with Tkinter
- Internet access while reading/downloading the public service
- ArcGIS Earth for the intended KMZ viewing workflow

No QGIS, ArcGIS Pro, ArcPy, GDAL, GeoPandas, or Python `requests` package is required.

## Start the program

Run `PointLayer.bat`.

## Step 1 - Paste a public ArcGIS service

PointLayer accepts either:

- `/FeatureServer`
- `/FeatureServer/<layer id>`
- `/MapServer`
- `/MapServer/<layer id>`

Click **Read Service**.

If the root has one queryable point layer, it is selected automatically. If several point layers are available, PointLayer presents a chooser.

## Step 2 - Choose fields

The field table shows the service fields, aliases, and field types.

Controls:

- **Recommended** - selects fields whose names/aliases look operationally useful.
- **All** - selects all fields.
- **None** - clears the selection.
- Click an individual row to toggle it.

The finished KMZ popup contains only the fields you select.

OID fields are normally unnecessary.

Do not assume a field named Latitude or Longitude is actually decimal geographic coordinates. Some public layers store projected X/Y values or legacy values in fields with misleading names. PointLayer uses the service geometry and requests output geometry in EPSG:4326.

## Step 3 - Choose output

Choose the output folder and base name.

Output choices:

- **KMZ**
- **GeoJSON**
- both

### KMZ

Use KMZ when the primary goal is ArcGIS Earth.

KMZ provides:

- embedded icon
- icon scale
- hidden labels
- KML Region/LOD
- clickable popup attributes

### GeoJSON

GeoJSON preserves the selected attributes and point geometry but does not carry the same Earth-specific presentation.

## Step 4 - Choose KMZ style

Built-in symbols:

- Red dot
- Blue dot
- Yellow dot
- Red H (hydrant)

A custom PNG can also be supplied.

### Scale

`0.50` was used successfully for the hydrant H symbol.

### Hide labels

Checked means the symbol is visible but text is not drawn beside every point.

Click the point to see its popup information.

This is normally the useful setting for dense operational layers.

### LOD cutoff

LOD controls when ArcGIS Earth starts drawing the layer.

A high-density layer should not necessarily appear while the user is looking at an entire county. Keeping the layer enabled but invisible until a useful zoom level prevents a wall of overlapping symbols.

Proven starting references:

- Nassau County hydrants: 3,250 published point features -> LOD 12,000
- Duval / JFRD-JEA hydrants: 30,688 published point features -> LOD 30,000

Raise LOD if the symbols appear too early. Lower it if they appear too late.

## Step 5 - BUILD

Click **BUILD**.

PointLayer:

1. requests the complete Object ID list
2. downloads feature records in safe batches
3. automatically splits a failing batch into smaller batches when appropriate
4. requests geometry in EPSG:4326
5. keeps only selected attributes
6. calculates the downloaded point extent
7. writes the selected output format(s)

## Open in ArcGIS Earth

Double-click the KMZ or add it through ArcGIS Earth.

With labels hidden:

- symbols remain clean
- the layer can stay checked
- LOD delays drawing until useful zoom
- click a symbol to see selected information

## File-size behavior

In one Nassau test, the same 3,250 features and selected fields produced:

- GeoJSON: 695,722 bytes
- KMZ: 96,350 bytes

The KMZ's internal uncompressed KML was roughly 2.0 MB. ZIP compression reduced it dramatically because XML repeats the same tags and field names thousands of times.

No hydrants were removed to achieve the smaller file.

## Troubleshooting

### "Requested layer 0 was not found"

Do not add `/0` just because many ArcGIS examples use layer zero.

Paste the service root and let PointLayer discover the actual point layer.

Nassau's hydrant layer, for example, is layer **458**.

### BUILD button is off-screen

PointLayer 1.2 and later use a scrollable main area with BUILD/status/progress fixed at the bottom.

### Too many symbols appear at once

Increase the LOD cutoff.

### Symbols appear too late

Decrease the LOD cutoff.

### Popup is cluttered

Rebuild and select fewer fields.

PointLayer 1.3 does not inject a visible Source row into KMZ popups.

### A "Latitude" or "Longitude" field looks wrong

The public service may be storing projected coordinates or another convention in those attributes. PointLayer places points using the layer geometry requested in EPSG:4326, not by trusting attribute names.

## Data responsibility

The tool downloads the records that the source service publishes. A published feature count is not automatically proof of the real-world total number of assets.

For example, "3,250 features downloaded from Nassau's hydrant layer" is precise. "Nassau County has exactly 3,250 hydrants" would require a separate completeness claim from the data owner.

Always check source-agency terms, currency, completeness, and operational suitability.
