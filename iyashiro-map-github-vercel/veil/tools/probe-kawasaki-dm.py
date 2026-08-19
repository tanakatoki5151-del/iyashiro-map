#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import re
import urllib.request
import zipfile

OUT = pathlib.Path(os.environ.get('VEIL_DM_PROBE_OUT', 'veil-kawasaki-dm-probe'))
OUT.mkdir(parents=True, exist_ok=True)
USER_AGENT = 'PROJECT-VEIL-research-runner/1.0 (+GitHub Actions; evidence acquisition)'
TARGETS = [
    ('KAWASAKI_DM1_2024', 'DM1.zip', 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/DM1.zip'),
    ('KAWASAKI_DM2_2024', 'DM2.zip', 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/DM2.zip'),
]

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def decode_sample(data):
    out = {}
    for enc in ('ascii', 'cp932', 'shift_jis', 'utf-8'):
        try:
            text = data.decode(enc)
            out[enc] = text.replace('\r', '\\r').replace('\n', '\\n')
        except Exception as e:
            out[enc] = None
    return out

def is_textish(name, data):
    suffix = pathlib.Path(name).suffix.lower()
    if suffix in {'.dm', '.txt', '.dat', '.csv', '.idx', '.dmi', '.dmt', '.map'}:
        return True
    sample = data[:256]
    if not sample:
        return False
    printable = sum((32 <= b <= 126) or b in (9,10,13) for b in sample)
    return printable / len(sample) > 0.75

def index_record_probe(data):
    # Public Survey Standard Map Symbol appendix defines fixed 84-byte records.
    # Do not promote this parser result as authoritative by itself. It reports
    # candidate fields for comparison with the official format specification.
    if len(data) < 84:
        return None
    record = data[:84]
    ascii_text = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in record)
    # Spec diagram: record type A2 followed by plane rectangular coordinate
    # system number I2. Preserve raw slice and integer candidate, fail closed.
    coord_slice = record[2:4].decode('ascii', errors='replace')
    coord_candidate = int(coord_slice) if re.fullmatch(r'\d{1,2}', coord_slice.strip() or 'x') else None
    return {
        'record84_hex': record.hex(),
        'record84_ascii': ascii_text,
        'record_type_slice_0_2': record[0:2].decode('ascii', errors='replace'),
        'coordinate_system_slice_2_4': coord_slice,
        'coordinate_system_candidate': coord_candidate,
    }

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read(), getattr(r, 'status', 200), r.headers.get('Content-Type'), r.geturl()

def main():
    reports = []
    for key, filename, url in TARGETS:
        entry = {'resourceKey': key, 'fileName': filename, 'url': url}
        try:
            raw, status, ctype, final_url = fetch(url)
            entry.update({
                'status': 'ACQUIRED', 'httpStatus': status, 'contentType': ctype,
                'finalUrl': final_url, 'bytes': len(raw), 'sha256': sha256(raw),
            })
            zpath = OUT / filename
            zpath.write_bytes(raw)
            files = []
            coord_candidates = []
            with zipfile.ZipFile(zpath) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    row = {'name': info.filename, 'bytes': info.file_size, 'crc': f'{info.CRC:08x}'}
                    with zf.open(info) as fh:
                        sample = fh.read(min(info.file_size, 4096))
                    if is_textish(info.filename, sample):
                        row['sampleHex'] = sample[:336].hex()
                        row['decoded'] = decode_sample(sample[:336])
                        probe = index_record_probe(sample)
                        row['indexRecordProbe'] = probe
                        if probe and probe['coordinate_system_candidate'] is not None:
                            coord_candidates.append({
                                'name': info.filename,
                                'candidate': probe['coordinate_system_candidate'],
                                'recordType': probe['record_type_slice_0_2'],
                                'rawSlice': probe['coordinate_system_slice_2_4'],
                            })
                    files.append(row)
            entry['zipMemberCount'] = len(files)
            entry['members'] = files
            entry['coordinateSystemCandidates'] = coord_candidates
            entry['uniqueCoordinateSystemCandidates'] = sorted({x['candidate'] for x in coord_candidates})
        except Exception as e:
            entry.update({'status': 'ERROR', 'error': repr(e)})
        reports.append(entry)

    summary = {
        'project': 'PROJECT_VEIL',
        'purpose': 'Kawasaki 2024 DM primary-file CRS/code-system probe; research only; no public derivative',
        'officialFormatEvidence': {
            'authority': 'Geospatial Information Authority of Japan, Public Survey Standard Map Symbol, Appendix 7',
            'rule': 'DM index record contains plane rectangular coordinate system number and classification-code mapping; parser candidates require raw-record/spec agreement before promotion',
        },
        'targets': reports,
    }
    (OUT / 'kawasaki-dm-probe.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'statuses': {x['resourceKey']: x['status'] for x in reports},
        'coordinateSystemCandidates': {x['resourceKey']: x.get('uniqueCoordinateSystemCandidates') for x in reports},
        'memberCounts': {x['resourceKey']: x.get('zipMemberCount') for x in reports},
    }, ensure_ascii=False))
    if any(x['status'] != 'ACQUIRED' for x in reports):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
