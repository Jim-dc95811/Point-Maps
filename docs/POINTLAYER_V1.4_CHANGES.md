# PointLayer 1.4 - change document

**Released:** 2026-11-01
**Type:** hardening release. Completeness, file safety and data robustness.
**Download:** [`releases/PointLayer_v1.4.zip`](../releases/PointLayer_v1.4.zip)

**For normal services the output is unchanged.** Service discovery, the layer chooser, field selection, batching and batch splitting, the LOD suggestion, icons, `outSR=4326` geometry, and the KMZ and GeoJSON layout are identical to 1.3. For an ordinary layer, 1.4 writes the same KMZ contents and the same GeoJSON as 1.3.

## What changed

### 1. Every published point is accounted for

PointLayer's purpose is to download the *complete* published layer.

**1.3** never checked that the service actually returned every object ID it listed. If a server quietly returned fewer features (hidden limits, records changing mid-download), the layer was written short. The only message, e.g. "3,238 point records written", looked like success.

**1.4:**
- Checks every listed ID off as features arrive. To do that it always requests the object-ID field, but only the fields you chose are written.
- Asks the service once more for any that are missing.
- If some are still missing, writes the layer and warns, e.g.:

```text
WARNING: 3 of 3,250 published features were not returned by the service, even after
asking again. The layer was written without them.
Missing object IDs: 3248, 3249, 3250
```

For a service that publishes no object-ID field, the totals are compared instead.

### 2. One bad record can no longer spoil the whole KMZ

Older agency records sometimes contain invisible control characters, typically in notes fields. XML forbids them.

**1.3** copied them into the KMZ's KML, making the whole document invalid XML. ArcGIS Earth would likely refuse the entire layer.

**1.4** removes those characters from KML text; the rest of the value is kept. GeoJSON already handled them correctly and is unchanged.

### 3. Single-point and straight-line layers can appear

The KMZ's visibility Region is the box around the points, and the LOD cutoff is measured against that box's size on screen.

**1.3:** with one point, or points that all share one latitude or one longitude, the box had zero area, so it could never reach the LOD threshold and the layer would never draw.

**1.4:** in that case only, the box is given a real extent: the size of the other direction, or about 1 km (0.01 degrees) for a single point. Layers with a normal spread are unchanged. Very small layers may still need a lower LOD cutoff, which remains adjustable.

### 4. Points without a location are reported

**1.3** skipped records that the service published without geometry, silently. **1.4** reports them, e.g. `65 records had no location in the service and were skipped.`

The completion message now reads `N of M published points written`.

### 5. Existing files are protected

- **Replace prompt:** if the KMZ or GeoJSON already exists, 1.4 asks before replacing it, with No as the default. 1.3 replaced it silently.
- **Safe writing:** files are written as `.partial` first and renamed only when complete, so a failure part-way leaves the previous file untouched.

### 6. Custom icon must be a PNG

**1.3** accepted any file chosen as a "Custom PNG", for example a renamed JPEG. **1.4** checks the file is a real PNG and says so if it is not.

The window title and package README show 1.4. The built-in `--self-test` gained checks for control characters, the zero-area Region, the PNG check and safe writing.

## Verification

- **Live acceptance:** Jim Gaddy tested 1.4 on Windows with ArcGIS Earth on 2026-11-01 and reported everything working.
- **Regression against 1.3:** run against a stand-in ArcGIS FeatureServer, so not a live service. KMZ contents and GeoJSON were byte-identical to 1.3 for:
  - a 3,250-point layer with maxRecordCount 1000;
  - a 30,688-point layer with maxRecordCount 2000;
  - values with accents, quotes, `&` and `<`;
  - a single selected field.
- **Hardening tests (17 checks, all passed):**
  - features dropped once were recovered by the second request;
  - features never returned were reported by ID, and by count for a service without an ID field;
  - a control character produced valid KML with the rest of the note intact;
  - one-point and single-latitude layers got a Region containing every point;
  - 65 location-less records were counted;
  - a disk-full failure kept the previous file;
  - a renamed JPEG was rejected;
  - `--self-test` passes, including when run from the extracted release zip.

## Checksums

| File | SHA-256 |
|---|---|
| `PointLayer.py` 1.4 | `d09a4fae215a2fdd2e8a19faaac99140966e782a6ea93e69c8679e3b57ed3c67` |
| `PointLayer_v1.4.zip` | `1987c1ef7e00b7a4ecb1ada41b46a17d29c78c05a5dcd621916aa77af4dce3f6` |
| `PointLayer.py` 1.3 (previous) | `7ad56e5083e170096eff7151d2c5802ea58509b69f46b62f8fa94055ae4039b4` |

`PointLayer.bat` is unchanged. `releases/PointLayer_v1.3.zip` stays in the repository so existing links keep working.
