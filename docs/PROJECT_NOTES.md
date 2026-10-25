# Project Notes

Point Maps began as an attempt to turn public hydrant layers into usable offline ArcGIS Earth overlays.

The manual discovery path established the important behavior first:

- public ArcGIS REST point data could be exported with attributes
- GeoJSON preserved attributes but did not provide the desired ArcGIS Earth presentation
- KML/KMZ gave control over icons and LOD
- a single dense point set with one appearance threshold worked better than multi-tier duplicate-symbol experiments
- Nassau's accepted threshold was 12,000
- Duval's accepted threshold was 30,000
- hidden labels kept dense layers readable while preserving click popups

PointLayer then generalized the workflow so a user can paste a public ArcGIS service, select fields, and build the complete point overlay directly.

The project intentionally avoids expanding the program without discussion. New functional changes should be versioned and added one at a time.
