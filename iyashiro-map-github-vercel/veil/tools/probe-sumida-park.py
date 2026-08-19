#!/usr/bin/env python3
import hashlib
import io
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

outer_members = []
shp_profiles = []

def profile_zip(zf, package_label):
    names = [x.filename for x in zf.infolist() if not x.is_dir()]
    for shp_name in [n for n in names if n.lower().endswith('.shp')]:
        base = shp_name[:-4]
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            for ext in ('.shp','.shx','.dbf','.prj','.cpg'):
                candidate = base + ext
                if candidate in names:
                    (td / pathlib.Path(candidate).name).write_bytes(zf.read(candidate))
            shp_path = td / pathlib.Path(shp_name).name
            reader = shapefile.Reader(str(shp_path), encoding='cp932', encodingErrors='replace')
            fields = [f[0] for f in reader.fields[1:]]
            matching = []
            for idx, rec in enumerate(reader.iterRecords()):
                values = [v for v in rec]
                text = ' | '.join('' if v is None else str(v) for v in values)
                if '梅若' in text:
                    shp = reader.shape(idx)
                    matching.append({
                        'recordIndex': idx,
                        'attributes': dict(zip(fields, values)),
                        'shapeType': shp.shapeTypeName,
                        'bbox': list(getattr(shp, 'bbox', [])) or None,
                        'points': len(shp.points),
                        'parts': list(shp.parts),
                    })
            prj = None
            prj_path = td / (pathlib.Path(base).name + '.prj')
            if prj_path.exists():
                prj = prj_path.read_text(encoding='utf-8', errors='replace')
            shp_profiles.append({
                'package': package_label,
                'shpName': shp_name,
                'shapeType': reader.shapeTypeName,
                'recordCount': len(reader),
                'fields': fields,
                'bbox': list(reader.bbox),
                'prj': prj,
                'umewakaMatches': matching,
            })

with zipfile.ZipFile(RAW) as outer:
    outer_members = [x.filename for x in outer.infolist() if not x.is_dir()]
    profile_zip(outer, 'outer')
    for name in outer_members:
        if not name.lower().endswith('.zip'):
            continue
        nested_bytes = outer.read(name)
        try:
            with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                profile_zip(nested, name)
        except zipfile.BadZipFile:
            pass

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
    'outerMemberCount': len(outer_members),
    'outerMembers': outer_members,
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
    raise SystemExit('no shapefile after recursive ZIP inspection')
if sum(len(x['umewakaMatches']) for x in shp_profiles) < 1:
    raise SystemExit('梅若 record not found; fail closed')
