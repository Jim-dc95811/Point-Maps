# Changelog


## PointLayer 2.1 - 2026-11-08

- Re-hardening: "NaN" and blank locations no longer break the layer or the build; dates and code-list values readable in the popup; browser URLs (`?f=pjson`, `/query`) accepted; real (OneDrive) Desktop; plain message for a login page; wheel over the field list; thousands commas. New (Jim's live test): Scale 1.0 default, ground marker disc (4 m, grows as you zoom in), **Show below (ft)** replaces LOD cutoff. Live-tested by Jim. See [docs/POINTLAYER_V2.1_CHANGES.md](docs/POINTLAYER_V2.1_CHANGES.md). Zip `releases/PointLayer_v2.1.zip`; the 2.0 zip moved to `archive/`.

## PointLayer 2.0 - the 2.0 Reference (2026-11-08)

- The whole ArcGIS Earth Unlocked family moved to 2.0 as one reference point (Jim). Program = 1.4 with only the version text changed (diff-checked). Zip `releases/PointLayer_v2.0.zip`; older zips moved to `archive/`.

## PointLayer 1.4.2 (2026-11-08)
- Ready to Fly: `PointLayer.bat` - the launcher now gets the PC ready first: it finds Python or installs it for you (just for you, no admin - answer **Y**), then starts the tool. New file `System Files\Ready_To_Fly.ps1` (log: `System Files\Ready_To_Fly_log.txt`). Program byte-identical to the previous release. Live-tested by Jim 2026-11-08.

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
