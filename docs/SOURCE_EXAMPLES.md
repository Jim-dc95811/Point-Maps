# Public Source Examples

These URLs were used while developing and testing the Point Maps workflow.

Public availability can change. Each publisher controls its own data, terms, schema, service availability, and update schedule.

## Nassau County

`https://services5.arcgis.com/F73IhFZbCCYUexxB/arcgis/rest/services/Water_Hydrant/FeatureServer`

PointLayer discovers the `Water Hydrant` point layer at ID **458**.

## Duval County / Jacksonville

`https://maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/3`

## St. Johns County

`https://www.gis.sjcfl.us/portal_sjcgis/rest/services/Fire_Hydrants/FeatureServer`

The service advertises `Fire Hydrants` at layer ID **0**.

## Clay County

`https://maps.claycountygov.com/server/rest/services/Hydrants/FeatureServer`

Clay County also publishes other hydrant-related point services. Inspect the service description and fields before assuming two similarly named layers mean the same thing.

## Palm Coast / Flagler-area utility hydrants

`https://gis.palmcoast.gov/hosting/rest/services/External/Collaboration_EOC_wHydrant1/FeatureServer`

The corresponding service describes `wHydrant` data from the Palm Coast water utility GIS database.

Do not assume that a municipal utility service is identical to complete countywide coverage. Treat the publisher's description as the authority on scope.

## General rule

PointLayer does not need a hydrant-specific source.

Look for a public ArcGIS service whose desired layer reports:

- `Type: Feature Layer`
- `Geometry Type: esriGeometryPoint`
- Query capability

Then paste the service root or specific layer URL into PointLayer.
