# Point Maps - Continuity

Last consolidated: October 24, 2026

## Project purpose

Point Maps is the home for the **PointLayer** project: a small Windows/Python GUI that converts public/queryable ArcGIS point Feature Layers into complete offline overlays for ArcGIS Earth.

The project started with fire hydrants, but PointLayer is intentionally **not hydrant-specific**. The proven pattern applies to suitable public point layers such as hydrants, fire stations, shelters, sirens, AEDs, towers, utility assets, gates, wells, boat ramps, traffic signals, mile markers, schools, hospitals, helipads, and similar point datasets.

Core workflow:

`Public ArcGIS FeatureServer/MapServer -> select point layer -> select fields -> download complete published layer -> KMZ / GeoJSON -> ArcGIS Earth`

## Current release

**PointLayer 1.3**

Current release package:

`releases/PointLayer_v1.3.zip`

Root source files:

- `PointLayer.py`
- `PointLayer.bat`
- `README_PointLayer.txt`
- `TEST_SOURCES.txt`

## Strict modification rule

This project uses a deliberate change-control rule:

1. Discuss a proposed functional modification first.
2. Make **one functional modification at a time**.
3. Do not add unrequested improvements, cleanup, refactors, or extra behavior while making that change.
4. **Every code modification gets a new version number.**
5. Preserve known-good behavior unless the agreed change specifically requires altering it.

This rule exists because unrequested improvements created serious problems in earlier projects.

## Version history

### 1.0

Initial generalized point-layer downloader:

- public ArcGIS point Feature Layer input
- selected-field export
- complete Object ID retrieval
- safe batched feature downloads
- EPSG:4326 output geometry
- KMZ and GeoJSON output
- embedded offline KMZ icon
- adjustable icon scale
- KML Region/LOD
- Hide labels option

### 1.1

Fixed the incorrect assumption that the desired layer must be `/0`.

PointLayer now accepts service roots and:

- discovers advertised point layers
- auto-selects the only point layer
- presents a chooser when multiple point layers are present

This was required because Nassau's Water Hydrant layer is **ID 458**, not 0.

### 1.2

Fixed GUI sizing on smaller laptop displays / Windows scaling:

- scrollable upper work area
- BUILD/status/progress remains fixed at the bottom
- reduced startup/minimum dimensions

### 1.3

Removed the automatically injected visible `Source` row from KMZ popups.

The KMZ popup now contains only the fields the user selected.

No other functional change was made.

## Proven operational behavior

### Hide labels

With **Hide labels** checked:

- point symbols remain visible
- text is not drawn beside every point
- the user clicks a point to see the popup
- selected attributes remain intact

This is the preferred behavior for dense operational overlays.

### LOD

KML Region/LOD allows a layer to remain checked in ArcGIS Earth while rendering nothing at low zoom. Symbols appear only when the view reaches a useful scale.

Two manually tuned reference datasets established the current empirical starting points:

| Layer | Published point features | Accepted LOD |
| --- | ---: | ---: |
| Nassau County hydrants | 3,250 | 12,000 |
| Duval / JFRD-JEA hydrants | 30,688 | 30,000 |

These are **empirical starting points**, not universal mathematical rules. Geographic extent and density matter.

The successful hydrant presentation uses:

- one point set
- one appearance threshold
- red H icon
- icon scale 0.50
- labels hidden

Multi-tier duplicate-symbol experiments were tested manually and were worse because they created excessive visual clutter. Do not reintroduce that approach without a new discussion/testing cycle.

## File-format result

A same-run Nassau comparison proved that the smaller KMZ was not losing point data.

Both outputs contained:

- 3,250 point features
- matching selected attributes
- matching coordinates

Observed sizes:

- GeoJSON: **695,722 bytes**
- KMZ: **96,350 bytes**
- uncompressed `doc.kml` inside KMZ: roughly **2.0 MB**

The size reduction is ZIP compression of repetitive KML/XML, not removal of hydrants.

## Important data wording

Do not equate a published feature count with a guaranteed real-world asset total unless the source agency explicitly makes that completeness claim.

Correct wording:

> 3,250 features were published and downloaded from the Nassau hydrant layer.

Do not automatically claim:

> Nassau County has exactly 3,250 hydrants.

## Public test sources

### Nassau County

Service root:

`https://services5.arcgis.com/F73IhFZbCCYUexxB/arcgis/rest/services/Water_Hydrant/FeatureServer`

Important facts:

- desired point layer: `Water Hydrant`
- layer ID: **458**
- published test count: **3,250**
- accepted LOD: **12,000**

### Duval / Jacksonville

Layer used:

`https://maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/3`

Important facts:

- published test count: **30,688**
- accepted LOD: **30,000**
- service includes rich hydrant/JFRD/JEA attributes

### St. Johns County

`https://www.gis.sjcfl.us/portal_sjcgis/rest/services/Fire_Hydrants/FeatureServer`

### Clay County

`https://maps.claycountygov.com/server/rest/services/Hydrants/FeatureServer`

### Palm Coast / Flagler-area utility source

`https://gis.palmcoast.gov/hosting/rest/services/External/Collaboration_EOC_wHydrant1/FeatureServer`

Do not automatically describe a municipal utility source as complete countywide coverage. Preserve the publisher's stated scope.

## Five-source proof

By the end of the initial project session, five neighboring hydrant sources had been converted and displayed together in ArcGIS Earth.

The project screenshot is stored as:

`assets/five_counties.jpg`

This established that the generalized PointLayer workflow can be repeated across multiple independent public ArcGIS point services.

## Geometry and attribute handling

PointLayer requests feature geometry with:

`outSR=4326`

This is intentional.

Do not trust attribute fields named `Latitude`, `Longitude`, `X`, or `Y` merely because of their names. Nassau demonstrated that coordinate-like attribute fields can contain projected or otherwise non-decimal values while the service geometry itself is correctly located.

Point placement should come from the service geometry transformed to EPSG:4326.

## Complete-layer retrieval design

The tool avoids relying on one normal feature query's record-return limit.

General sequence:

1. `where=1=1`
2. request `returnIdsOnly=true`
3. obtain the complete Object ID list
4. download features in batches
5. recursively split transiently failing batches when necessary
6. keep selected fields only
7. write one complete output layer

Unlike Parcel100, PointLayer does **not** divide the source into 100 geographic cells. It downloads the whole published point layer.

## KMZ design

KMZ contains:

- `doc.kml`
- `icons/point.png`

The icon is embedded so the overlay remains self-contained/offline.

PointLayer supports:

- Red dot
- Blue dot
- Yellow dot
- Red H
- custom PNG

The first non-empty selected field is used as the Placemark name/popup title.

## Repository intent

The repository distributes:

- PointLayer software
- release ZIP
- user documentation
- technical documentation
- field-test notes
- public source examples
- project screenshots

It should **not** become a redistributed archive of agency hydrant datasets.

Public accessibility does not guarantee identical licensing, redistribution, attribution, completeness, or operational terms. Users are responsible for reviewing source-agency requirements.

## Repository documentation

- `README.md` - public project front page
- `docs/PointLayer_User_Guide.pdf` - user manual
- `docs/USER_GUIDE.md` - text user guide
- `docs/TECHNICAL_NOTES.md` - implementation/design notes
- `docs/FIELD_TESTS.md` - Nassau/Duval/five-source validation
- `docs/SOURCE_EXAMPLES.md` - public service examples
- `docs/PROJECT_NOTES.md` - project origin and lessons
- `CHANGELOG.md` - version history
- `CONTINUITY.md` - this file

## Relationship to larger ArcGIS Earth work

Point Maps is a focused side project within a broader ArcGIS Earth/offline mapping effort that also includes:

- TPKX/offline imagery production
- MBTiles -> TPKX conversion
- Master 4 geographic grids
- Parcel100 property overlays
- PRAVE / ME tracking
- planned joystick-based ArcGIS Earth navigation

PointLayer should remain a focused point-layer utility rather than absorbing unrelated functions.

## Next sensible work - only after discussion

Possible future directions exist, but none are approved merely by appearing here:

- test PointLayer on non-hydrant public point layers
- additional built-in symbols
- better LOD recommendation logic based on density/extent
- additional documentation/video
- inclusion in a future ArcGIS Earth Tools umbrella repository

Any functional change still follows the strict one-change/new-version rule above.
