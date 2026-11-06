# Changelog

## PointLayer 1.4.1 (2026-11-06)
- One obvious file: the zip holds a `PointLayer_v1.4.1` folder with `PointLayer.bat` and `System Files\PointLayer.py` (Jim's packaging rule). `README_PointLayer.txt` and `TEST_SOURCES.txt` are no longer in the download (they stay in the repository). Program unchanged (1.4).

## PointLayer 1.4
- Every object ID the service lists is checked off; missing features are requested once more, and any still missing are reported (count and IDs) while the layer is still written.
- Characters that are illegal in XML are removed from KML text, so one bad record cannot make the KMZ unreadable.
- A one-point layer, or points on a single latitude or longitude, gets a KML Region with a real extent so it can draw.
- Records without a location are counted in the completion message.
- Asks before replacing an existing KMZ/GeoJSON; files are written as `.partial` first.
- A custom icon must be a real PNG.
- Output for normal services is identical to 1.3. Details: [docs/POINTLAYER_V1.4_CHANGES.md](docs/POINTLAYER_V1.4_CHANGES.md).

## PointLayer 1.3
- Removed the automatically injected `Source` row from KMZ popups.
- KMZ popup content now follows the user's selected fields only.
- No other functional change from 1.2.

## PointLayer 1.2
- Reworked the GUI so the BUILD/status/progress area stays fixed at the bottom.
- Added a scrollable work area above the BUILD bar.
- Reduced startup and minimum window dimensions so short laptop displays and Windows scaling do not hide the BUILD button.

## PointLayer 1.1
- Added service-root input support.
- PointLayer can discover queryable point layers inside a FeatureServer or MapServer service root.
- Automatically selects the only point layer when one exists.
- Shows a layer chooser when several point layers exist.
- Fixed the assumption that a desired public layer must be `/0`.

## PointLayer 1.0
- Initial general point-layer downloader.
- Selected-field export.
- Complete Object ID retrieval followed by safe batched feature downloads.
- EPSG:4326 output.
- KMZ and GeoJSON output.
- Embedded offline KMZ icons.
- Adjustable icon scale and KML LOD.
- Hidden-label option.
