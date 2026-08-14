#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import tempfile
import urllib.request
import zipfile

import shapefile

URL = 'https://www.city.sumida.lg.jp/wkg/opendata/opendata_ichiran/matizukuri_map/kuritukouen_20251001.zip'
OUT = pathlib.Path(os.environ.get('VEIL_SUMIDA_PARK_OUT', 'veil-sumida-park-probe'))
OUT.mkdir(parents=True, exist_ok=True)
RAW = OUT / 'kuritukouen_20251001.zip'

req = urllib.request.Request(URL, headers={
    'User-Agent': 'PROJECT-VEIL-research-runner/1.0 (+GitHub Actions; evidence acquisition)',
    'Accept': '*/*',
})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
    status = getattr(r, 'status', 200)
    ctype = r.headers.get('Content-Type')
    final_url = r.geturl()
RAW.write_bytes(data)
sha = hashlib.sha256(data).hexdigest()

members = []
shp_profiles = []
with zipfile.ZipFile(RAW) as zf:
    members = [x.filename for x in zf.infolist() if not x.is_dir()]
    shp_names = [n for n in members if n.lower().endswith('.shp')]
    for shp_name in shp_names:
        base = shp_name[:-4]
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            for ext in ('.shp','.shx','.dbf','.prj','.cpg'):
                candidate = base + ext
                if candidate in members:
                    (td / pathlib.Path(candidate).name).write_bytes(zf.read(candidate))
            shp_path = td / pathlib.Path(shp_name).name
            reader = shapefile.Reader(str(shp_path), encoding='cp932', encodingErrors='replace')
            fields = [f[0] for f in reader.fields[1:]]
            matching = []
            for idx, rec in enumerate(reader.iterRecords()):
                values = [v for v in rec]
                text = ' | '.join('' if v is None else str(v) for v in values)
                if '梅若' in text:
                    shape = reader.shape(idx)
                    matching.append({
                        'recordIndex': idx,
                        'attributes': dict(zip(fields, values)),
                        'shapeType': shape.shapeTypeName,
                        'bbox': list(shape.bbox) if hasattr(shape, 'bbox') else None,
                        'points': len(shape.points),
                        'parts': list(shape.parts),
                    })
            prj = None
            prj_path = td / (pathlib.Path(base).name + '.prj')
            if prj_path.exists():
                prj = prj_path.read_text(encoding='utf-8', errors='replace')
            shp_profiles.append({
                'shpName': shp_name,
                'shapeType': reader.shapeTypeName,
                'recordCount': len(reader),
                'fields': fields,
                'bbox': list(reader.bbox),
                'prj': prj,
                'umewakaMatches': matching,
            })

report = {
    'project': 'PROJECT_VEIL',
    'resourceKey': 'TOKYO_SUMIDA_PARKS_20251001',
    'sourceUrl': URL,
    'httpStatus': status,
    'contentType': ctype,
    'finalUrl': final_url,
    'bytes': len(data),
    'sha256': sha,
    'license': 'CC BY 2.1 JP per Sumida Open Data Portal; attribution/modified-data notice required',
    'memberCount': len(members),
    'members': members,
    'shapefiles': shp_profiles,
    'safeInterpretation': 'Official current ward-park geometry. A park polygon is not an exact event point; use only as facility-site/area context for park-level incident precision.',
}
(OUT / 'sumida-park-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({
    'status': 'ACQUIRED',
    'bytes': len(data),
    'sha256': sha,
    'shapefiles': len(shp_profiles),
    'umewakaMatches': sum(len(x['umewakaMatches']) for x in shp_profiles),
}, ensure_ascii=False))
if not shp_profiles:
    raise SystemExit('no shapefile in official park ZIP')
if sum(len(x['umewakaMatches']) for x in shp_profiles) < 1:
    raise SystemExit('梅若 record not found; fail closed')
