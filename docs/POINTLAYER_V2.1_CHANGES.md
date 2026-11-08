# PointLayer 2.1 - what changed (2026-11-08)

> 🤖 **Using AI assistance?** Have the agent read the [CLAUDE.md](https://github.com/Jim-dc95811/ArcGIS-Earth-Unlocked/blob/main/CLAUDE.md) file first.

A re-hardening release plus three things Jim asked for while testing it. Live-tested by Jim on 2026-11-08 against a stand-in county server with bad records ([`pointlayer_test_server.py`](https://github.com/Jim-dc95811/ArcGIS-Earth-Unlocked/blob/main/tools/test-rigs/pointlayer_test_server.py)).

## Fixes

| # | Before (2.0) | Now (2.1) |
|---|---|---|
| 1 | A point the server sent with location "NaN" (an ArcGIS habit for empty points) broke the layer's visibility box - ArcGIS Earth drew **none** of the points, with no message. | Counted as "no location" and skipped; every other point draws. |
| 2 | A point with a blank location stopped the build (`float() argument must be ...`). | Same as 1. |
| 3 | Date fields showed as `1625097600000`. | Shown as `2021-07-01` (a time is kept when there is one). |
| 4 | URLs copied from the browser (`.../FeatureServer/0?f=pjson`, `.../0/query`) were refused. | Accepted. |
| 5 | Default folder `C:\Users\<you>\Desktop`, which may not exist where OneDrive moved the Desktop ("Output folder does not exist"). | The Desktop Windows really shows. |
| 6 | A login page gave `Expecting value: line 1 column 1 (char 0)`. | "The server did not send map data. It may need a login, or this is not an ArcGIS REST service URL." |
| 7 | Code-list fields showed the code (`1`). | Show the meaning the service lists ("Nassau County"). The GeoJSON keeps the raw values. |
| 8 | The mouse wheel over the field list scrolled the whole page; `12,000` was refused. | The list scrolls; thousands commas work; messages name the box. |

## New (Jim's live test: "markers are way too small and don't trigger until you are almost on top of them")

- **Bigger markers:** Scale starts at **1.0** (was 0.5). ArcGIS Earth draws a KMZ icon at a fixed size on the screen, so it never grows as you zoom in.
- **Ground marker:** "Disc on the ground", on by default, **4 m** across, in the symbol's colour. It sits on the imagery and grows as you zoom in - like a QGIS symbol sized in map units. Click it for the same popup.
- **Show below (ft)** replaces **LOD cutoff**: the eye alt in feet below which the points show (0 = always). PointLayer works out the pixel LOD from it and the size of the layer (the Object Factory calibration: about 5,967 ft x pixels per metre of box). The suggestion keeps the old one for big county layers and is at least **10,000 ft**, so a small layer no longer needs you right on top of it. Jim's test layer: visible to about 8,800 ft in a tilted view with 10,000 set.

With the ground marker off and a layer with no dates, code lists or empty points, the KMZ is the same as 2.0's for the same pixel LOD. Test rigs: [`pointlayer_test_v21.py`](https://github.com/Jim-dc95811/ArcGIS-Earth-Unlocked/blob/main/tools/test-rigs/pointlayer_test_v21.py) (ALL PASS) and the 1.4 rig's 9 cases (same as 2.0).
