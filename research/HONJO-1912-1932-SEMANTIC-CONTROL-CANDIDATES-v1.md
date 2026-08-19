# Honjo clothing depot — 1912↔1932 semantic control candidates v1

Date: 2026-08-13
Status: research control-point candidate inventory only
Scoring effect: none
Polygon promotion: prohibited from this inventory alone

## Purpose

The 1912 NDL cadastral map (Honjo map 4 / Yokozuna-cho 1-chome, scan 152/153) now gives an independent primary-map view of the active Army Clothing Depot. The 1932 Tokyo Memorial Association source gives the post-earthquake former-depot division diagram. This note defines which features may and may not be used as cross-time control candidates before any georeference is optimized.

The purpose is to prevent a circular fit in which the 1932 A-park outline or the modern Yokozuna-cho Park polygon is used both as the target and as the evidence for the fit.

## Source chain

1. 1912 `東京市及接続郡部地籍地図 下卷`, NDL PID 966080, official IIIF, PDM.
   - scan 152/153 visually verified as Honjo map 4 / Yokozuna-cho 1-chome.
   - large parcel explicitly labelled `陸軍被服廠`.
2. 1932 `被服廠跡`, p83 `元陸軍被服廠分割図` and official museum object 15-00013.
3. Tokyo Archives `本所区復興図`, independent post-reconstruction street/parcel context.
4. Pending: 1934 `東京市本所区地籍図` Honjo maps 18/19 and 1933–35 fire-insurance special maps.

## Candidate classes

### CP-HONJO-01 — southern outer boundary line
Use the long southern site-edge / street-line segment visible in both the 1912 active-site cadastral map and the 1932 pre-division outline.

Gate:
- identify at least two independent junctions on this line, not merely the line orientation;
- confirm the street/parcel line in the 1934 cadastral or 1933–35 fire map before it becomes a numeric control.

Confidence now: medium-high as a line constraint, not yet a point.

### CP-HONJO-02 — southeast outer corner
Candidate point where the long curved eastern outer boundary meets the southern straight boundary.

Why useful:
- outer-site geometry, not a post-division internal road;
- visually distinctive transition from curve to south line.

Gate:
- confirm the same corner in the 1934 cadastral/fire map;
- reject if later road widening moved the corner by an unquantified amount.

Confidence now: medium.

### CP-HONJO-03 — eastern curved boundary trajectory
Use as a polyline/shape constraint rather than a single point. The long curving eastern perimeter appears in the active-site map and the 1932 former-depot outline.

Gate:
- sample only vertices corresponding to independent road/parcel junctions after 1934 map confirmation;
- do not create multiple pseudo-independent points from the same uninterrupted curve.

Confidence now: medium-high as a shape constraint.

### CP-HONJO-04 — southwest outer corner / southern-line junction
Candidate point where the western/diagonal site edge reaches the southern street line.

Gate:
- identify the exact road/rail/parcel function in 1912 and 1932;
- confirm in the 1934 cadastral/fire map before numeric use.

Confidence now: medium.

### CP-HONJO-05 — northwest outer-boundary junction
Candidate only if the corresponding outer boundary and adjacent road/parcel junction can be independently identified on the 1934 cadastral/fire map.

Current caution:
- the 1912 sheet has dense transport/parcel features in this sector;
- do not infer correspondence from angle alone.

Confidence now: low-medium.

### CP-HONJO-06 — north/east road junction near the outer curve
Candidate only if the junction exists before and after the 1923 earthquake and is not part of the later division-road construction.

Confidence now: low-medium pending 1934/fire map.

## Explicitly rejected as controls at this stage

### REJECT-HONJO-A — 1932 division road C
Road C is part of the former-depot division plan. It is not presumed to be an unchanged 1912 feature.

### REJECT-HONJO-B — park interior / design features
The park design, paths, planting, oval field and post-division interior geometry are later features and cannot anchor the active 1912 depot boundary.

### REJECT-HONJO-C — modern Yokozuna-cho Park outline
Modern park geometry is an analysis/check target, not an independent historical control for reconstructing the entire former depot.

### REJECT-HONJO-D — depot building corners
Buildings may have been destroyed/rebuilt by earthquake, fire, reconstruction or site division. Do not use a building corner unless the exact building is independently shown to persist in another dated source.

### REJECT-HONJO-E — repeated samples along one continuous boundary
Multiple points sampled from one curve/straight edge are not independent controls. A transform with many correlated points can look precise while having weak source independence.

## Required georeference QC after 1934/fire map acquisition

1. At least 6 **independent semantic controls**, distributed around the site perimeter.
2. At least 3 source epochs/systems in the chain, preferably 1912 cadastral + 1932 source + 1934 cadastral/fire map, before modern geometry is used as a check.
3. Compare affine and projective transforms.
4. Save per-control residuals in ground metres.
5. Save RMS, median, 95th percentile and maximum error.
6. Leave-one-out residual test for every control.
7. Report spatial spread / quadrant coverage of controls.
8. Use modern park area and 1928 exchange area as **validation**, not transform objective.
9. Do not optimize the transform to make the historical area equal a known area.
10. Independent vertex review before any `source_backed_review_polygon` promotion.

## Promotion gate

The 1912 map substantially strengthens provenance because it directly labels the active Army Clothing Depot, but it does not by itself turn `research_shape_alignment_candidate_v0` into a source-backed review polygon. Promotion is considered only after the pending 1934 cadastral / 1933–35 fire-map source independently fixes the perimeter controls and residuals pass QC.
