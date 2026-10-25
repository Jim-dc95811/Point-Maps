# Field Tests

## Nassau County - Water Hydrant

Service root:

`https://services5.arcgis.com/F73IhFZbCCYUexxB/arcgis/rest/services/Water_Hydrant/FeatureServer`

Important findings:

- desired layer is **458**, not 0
- published comparison layer contained **3,250 point features**
- manually accepted ArcGIS Earth LOD: **12,000**
- red H symbol at scale **0.50** worked well
- hidden labels + click popup gave the desired operational display

The manual KML/KMZ work was used as the reference for validating PointLayer.

## Duval / Jacksonville - JFRD/JEA Hydrants

Layer URL:

`https://maps.coj.net/coj/rest/services/HydrantsInspections/JFRD_JEA_Hydrants_2026_Mobile/FeatureServer/3`

Important findings:

- manual comparison contained **30,688 point features**
- accepted ArcGIS Earth LOD: **30,000**
- the denser layer required a later appearance threshold than Nassau

## Five-source result

After PointLayer was generalized, the workflow was used to build five neighboring hydrant overlays and display them together in ArcGIS Earth.

The practical conclusion is that the tool is not hydrant-specific. Hydrants were simply a strong first test because they are dense, operationally meaningful point data with useful popup attributes.

## Acceptance standard

The generated layer had to match the manually proven operational behavior:

- complete point count from the published layer
- correct geographic placement
- clean symbol
- manageable LOD behavior
- selected popup fields
- no unwanted visible Source row
- labels suppressed until click
