# Technical Notes

## Design goal

PointLayer is the point-geometry counterpart to the larger Parcel100 idea, but the problem is simpler: instead of dividing a polygon dataset into 100 spatial cells, PointLayer downloads the entire published point layer and writes one finished overlay.

## Service discovery

PointLayer accepts FeatureServer/MapServer roots or specific layer URLs.

For a service root it reads the advertised layers, inspects them, keeps queryable `esriGeometryPoint` layers, and either auto-selects the only candidate or asks the user to choose.

This was added after the Nassau hydrant service demonstrated why `/0` cannot be assumed. Nassau's point layer is ID 458.

## Complete-layer retrieval

PointLayer does not rely on the service's normal record-return limit for one feature query.

It queries `where=1=1`, requests `returnIdsOnly=true`, then downloads the returned Object IDs in batches.

When a transient batch request fails, the program can split the batch recursively into smaller requests.

## Coordinate handling

Feature requests specify `outSR=4326`.

PointLayer therefore writes WGS84 longitude/latitude geometry even when the source service uses Web Mercator, State Plane, or another service spatial reference.

This is more reliable than trusting attribute fields named Latitude, Longitude, X, or Y.

## KMZ construction

The program creates KML directly and packages it as KMZ.

Each KMZ contains:

- `doc.kml`
- `icons/point.png`

Each point becomes a KML `Placemark` with a shared style, user-selected `ExtendedData`, point coordinates, and clamp-to-ground altitude mode.

The first non-empty selected field becomes the placemark name/popup title. Labels can still be hidden independently with `LabelStyle`.

## KML Region / LOD

A folder-level KML `Region` is calculated from the downloaded feature bounds.

`minLodPixels` is user-adjustable and `maxLodPixels` remains `-1`.

The LOD suggestion is empirical, anchored to two manually tuned tests:

- 3,250 features -> 12,000
- 30,688 features -> about 30,000

It is a starting value, not a universal mathematical rule.

## GeoJSON

GeoJSON output is a standard `FeatureCollection` containing point geometry, selected properties, source URL metadata, and layer name.

The v1.3 "remove Source" change refers specifically to the **visible KMZ popup row**. It did not remove source metadata from GeoJSON.

## Compression finding

For the Nassau comparison:

- 3,250 features in both outputs
- same selected fields
- same point coordinates
- GeoJSON ~696 KB
- finished KMZ ~96 KB
- uncompressed `doc.kml` inside the KMZ ~2.0 MB

KML/XML is highly repetitive and compresses extremely well in the KMZ ZIP container.

## Scope

PointLayer 1.3 intentionally supports **point layers only**.

It does not currently handle polygons, polylines, multipoints, rasters, local geodatabases, or authenticated services. Those would be separate design decisions rather than silent expansion of PointLayer.
