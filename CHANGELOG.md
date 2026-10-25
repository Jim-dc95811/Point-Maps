# Changelog

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
