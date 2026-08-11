# MLIT L03-b acquisition runbook

## Scope

Acquire the eight official historical 100 m land-use ZIP files required by the V10 fixed grid:

- 1976: 5239, 5339
- 1987: 5239, 5339
- 1991: 5239, 5339
- 1997: 5239, 5339

Official filenames use the pattern `L03-b-YY_MMMM_GML.zip`.

## Quality gates

1. Preserve the official catalogue HTML and relevant JavaScript.
2. Record every attempted URL and HTTP result.
3. Count a file as downloaded only when Python `zipfile.is_zipfile` succeeds.
4. Save SHA-256 and member names for every valid ZIP.
5. The files use Tokyo Datum for these vintages; transform explicitly before joining to WGS84 V10 cell centres.
6. Historical land-use coverage is not negative evidence for major incidents, burial sites, execution grounds, or other major-history themes.

## Automation

`research/mlit_l03b_probe.py` runs in `.github/workflows/mlit-l03b-probe.yml` and uploads all evidence as the `mlit-l03b-probe` artifact.

## V10 fixed-grid invariant

- Total valid cells: 120,662
- Primary mesh 5339: 120,007
- Primary mesh 5239: 655
- Primary mesh 5340: 0 valid V10 cell centres

After all eight ZIPs are acquired, the next stage is extraction, CRS verification/transformation, spatial join, unmatched/duplicate audit, and site-delivery JSON generation.
