# BBBike OSM GeoPackage inspection — NAGARFLOW AI

> **Note, 2026-11-02:** the finding below that road topology cannot be recovered from this file is superseded. Ways share exact vertices, and a directed graph built from them places 99.29% of 292,338 road nodes in one strongly connected group. See `docs/superpowers/specs/2026-11-02-road-connectivity-design.md`. The rest of this report stands as written, including that this data is not a validated municipal record.

**Inspection status:** Read-only archive review completed. No routing graph or routes were constructed. The archive and requirements/architecture documents were not modified.

## Executive assessment

The expected archive was found at `C:\Users\haris\Downloads\planet_78.163_11.047_55136793.osm.geopackage.zip`. It contains a valid SQLite GeoPackage with OSM feature layers in EPSG:4326. The `lines` table contains 40,124 line features, including 38,142 with a `highway` value, and preserves OSM way IDs plus some routing-relevant OSM tags.

**This file is not a graph-ready routable network and is not approved for routing as-is.** It has no explicit road-node/edge layers or edge `from`/`to` connectivity fields. Direction/access tags are sparse and require vehicle-profile/default interpretation; road classes include paths, steps, footways, construction, and other non-truck candidates. Network connectivity and routing validity have not been tested. Some feature geometries also extend beyond the download rectangle, requiring spatial filtering/clipping against the selected demonstration boundary.

It is a possible source for a later graph-building step, subject to boundary, road-network and topology validation. Graph construction, connectivity testing, and route generation were outside this inspection.

## 1. Archive location and integrity

- Project data location searched: `C:\Users\haris\OneDrive\Documents\VScode\NAGARFLOW_AI\data` — directory does not exist.
- Downloads searched: `C:\Users\haris\Downloads` — archive found.
- Archive size: 15,521,002 bytes.
- ZIP contents: one `.gpkg` file (36,515,840 bytes), `README.txt`, `README.html`, `CHECKSUM.txt`, and `logfile.txt`.
- The extracted GeoPackage MD5 matched the checksum in the archive; SQLite `PRAGMA integrity_check` returned `ok`.
- Inspection used Python standard-library ZIP/SQLite/WKB reads from a temporary extraction. No packages were installed. The original ZIP was not changed.

The archive README identifies the source as BBBike/OpenStreetMap and states the requested extract rectangle as longitude/latitude `78.163, 10.301` to `79.005, 11.385`. The README says the extract was created on 2026-10-30 18:18:51 UTC; the PBF logfile reports an OSM replication timestamp of 2026-10-30 00:00:00 UTC. These are source metadata, not a guarantee of municipal boundary or current road completeness.

## 2. GeoPackage layers

All five feature layers report EPSG:4326 (WGS 84 longitude/latitude coordinates, in degrees). These coordinates are angular, not metres; road lengths must not be calculated as planar Euclidean distances directly in this CRS. A suitable local projected CRS or geodesic measurement method must be selected and validated before producing the MVP's metre-based distance KPI. Bounds below are the GeoPackage layer extents in `(min longitude, min latitude, max longitude, max latitude)` order, read from `gpkg_contents` and checked against geometry coordinates for the line layers.

| Layer | Geometry type | Feature count | CRS | Bounds (EPSG:4326) |
|---|---|---:|---|---|
| `points` | POINT | 14,673 | EPSG:4326 | (77.5338446, 9.9238836, 79.4844176, 13.0424703) |
| `lines` | LINESTRING | 40,124 | EPSG:4326 | (75.4483508, 9.9238836, 79.8688885, 13.2015935) |
| `multilinestrings` | MULTILINESTRING | 82 | EPSG:4326 | (78.0321963, 10.0021401, 79.0605995, 11.4430412) |
| `multipolygons` | MULTIPOLYGON | 106,673 | EPSG:4326 | (78.1560194, 10.1046274, 79.0141820, 11.4087294) |
| `other_relations` | GEOMETRYCOLLECTION | 15 | EPSG:4326 | (77.6973453, 10.5391736, 79.4224019, 11.1042722) |

These are feature layers; the GeoPackage also has standard metadata/tile-index tables but no tile contents were identified. The large counts in `multipolygons` and the non-road relation layers should not be treated as routable network content.

## 3. Geographic extent and Corporation-area comparison

### BBBike rectangle comparison

The BBBike README’s requested rectangle is:

- West/South: `(78.163, 10.301)`
- East/North: `(79.005, 11.385)`

The `lines` table’s actual geometry extent is `(75.4483508, 9.9238836, 79.8688885, 13.2015935)`, substantially wider than the requested rectangle. A geometry-coordinate scan found 40,057 of 40,124 `lines` features wholly within that rectangle; 67 have at least one coordinate outside it. All 40,124 feature envelopes intersect it. In `multilinestrings`, 68 of 82 geometries are wholly within the rectangle and 14 extend outside it. This is consistent with untrimmed OSM ways/relations crossing an extract boundary; it means the rectangle alone has not been applied as a strict clip.

### Tiruchirappalli Corporation comparison

The package contains an OSM multipolygon feature named **“Trichy Corporation Limits”**: `osm_id=1553009`, `boundary=administrative`, `admin_level=8`. Its geometry has 330 vertices and computed bounds `(78.6306621, 10.7273005, 78.7835251, 10.8805108)`. That OSM feature’s bounding box is fully inside the BBBike rectangle, so the requested rectangle’s envelope covers the OSM-mapped Corporation-boundary envelope.

This is **not independent verification** that the OSM boundary matches the legal/current Corporation boundary. The [official Corporation city map](https://www.trichycorporation.gov.in/wh-assets/tccdetails/map/citywardmap.pdf) identifies Corporation, ward, and zone boundaries for 65 wards, but is marked “NOT TO SCALE” and is not a machine-readable boundary. Therefore, no exact geometry overlay or authoritative containment test was possible. The final demonstration boundary remains unresolved and must be supplied/approved separately. Do not use the OSM polygon as a verified municipal boundary without validation.

## 4. Road attributes and OSM tags

The `lines` layer schema includes:

- GeoPackage row key `id` (local row identifier).
- `osm_id` (TEXT; OSM way identifier; 40,124 distinct values in this table).
- `name`, `highway`, `waterway`, `aerialway`, `barrier`, `man_made`, `railway`, `z_order`, and `other_tags`.

The `other_tags` column stores additional OSM key/value tags as text; one-way, access, bridge, tunnel, and junction are not dedicated columns. Counts below are tag values found in `other_tags` on the `lines` layer:

| Tag | Values found |
|---|---|
| `oneway` | `yes`: 1,621; `no`: 46; no `-1` value observed |
| `access` | `private`: 73; `yes`: 33; `no`: 26; `customers`: 12; `permissive`: 10 |
| `motor_vehicle` | `no`: 25; `private`: 1; `yes`: 6 |
| `motorcar` | `no`: 3 |
| `bridge` | `yes`: 1,408; `low_water_crossing`: 3; `aqueduct`: 2 |
| `tunnel` | `culvert`: 210; `yes`: 39; `building_passage`: 9; `yesse`: 1 |
| `junction` | `roundabout`: 36; `circular`: 1 |

There are 38,142 `lines` features with a `highway` value and 1,982 without one. Highway classes include `residential` (25,311), `unclassified` (4,421), `service` (3,002), `tertiary` (2,051), `trunk` (995), `track` (906), `secondary` (601), `primary` (276), `construction` (107), `path` (100), `footway` (73), and `steps` (8), among others. The presence of `highway` does not mean a line is suitable for a waste-collection truck; a vehicle profile and explicit inclusion/exclusion rules are required.

Direction on `oneway=yes` is meaningful relative to the order of coordinates in the OSM way geometry. `oneway` is absent on most ways, and OSM routing defaults/inferred rules (including roundabouts and road classes) are not expanded into directed edges here. Explicit access tags are also sparse; absence of an access tag does not by itself prove truck access. No truck dimensions/weight restrictions or access profile was validated in this review.

## 5. Graph-readiness, topology, and connectivity

### Node/edge layer assessment

- No graph-ready `nodes` or `edges` table exists.
- `points` is a POINT feature layer with OSM IDs and point-feature attributes (such as `highway`, `barrier`, `place`, and `man_made`). It is not an inventory of every road vertex or a road-junction node table.
- `lines` is a collection of OSM way geometries. It has OSM way IDs, but no `source_node`, `target_node`, `from_id`, `to_id`, direction-expanded edge IDs, or adjacency/connectivity fields.
- Road line coordinate sequences do not expose their original OSM node-reference lists in this schema. Consequently, the point table cannot be joined to every road vertex to recover topology from the exported identifiers alone.
- `multilinestrings` mostly describes OSM relations, not graph edges. It must not be added wholesale to the road network.

### Topology/connectivity limitations

Connectivity has **not** been computed or tested; no graph was constructed. The current export does not establish which line endpoints or interior vertices share routable OSM nodes. A 2D geometric intersection is not sufficient to establish a legal at-grade turn: bridges, tunnels, culverts, and `layer` tags indicate grade separation, while junction/turn restrictions and vehicle access may impose further rules. The export provides some of those tags but no complete topology/turn-restriction model in the road-line schema reviewed.

The 67 line geometries and 14 multiline geometries extending beyond BBBike’s requested rectangle also require treatment against an approved boundary. Long ways crossing a clipping edge may need to be clipped while preserving valid network endpoints; simply dropping every feature outside the rectangle can break continuity. That processing has not been performed.

## 6. Suitability decision

**Decision: Not suitable as-is for a directed routable road graph or route generation.**

Evidence supports using the `lines` layer as potential input to a later network preparation step: it contains line geometry, OSM way identifiers, highway classes, and some direction/access/bridge/tunnel tags. It does not contain graph nodes, explicit edge endpoints, adjacency, tested connectivity, validated turn behavior, or a truck-access profile. Spatial overrun beyond the requested rectangle and the unvalidated Corporation boundary are additional blockers.

Before a separate, approved graph-construction task, resolve at minimum:

1. Obtain and approve the exact demonstration-area/Corporation boundary; validate whether the OSM boundary object is acceptable or use a verified machine-readable boundary.
2. Select and document road inclusion rules for the waste-vehicle profile, including private/limited access, non-motor roads, construction, and missing access tags.
3. Define direction handling for explicit and implicit OSM one-way rules, geometry orientation, bridges/tunnels/layers, and turn restrictions.
4. Choose how to derive and validate graph nodes/edges and how to clip/filter boundary-crossing ways without breaking connectivity.
5. Test connected components, depot/storage/facility snapping, reachability, and road-distance calculations on the approved area before treating distances as valid.

These are validation requirements, not implementation performed in this task.

