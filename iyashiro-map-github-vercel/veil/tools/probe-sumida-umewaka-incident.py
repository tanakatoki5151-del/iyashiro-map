#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import re
import urllib.request

from pypdf import PdfReader

URL = 'https://www.city.sumida.lg.jp/kenko_fukushi/tiikihukusi_sonota/tiiki_hukusi/kouryo.files/20251125_ko464_s.pdf'
OUT = pathlib.Path(os.environ.get('VEIL_UMEWAKA_INCIDENT_OUT', 'veil-umewaka-incident-probe'))
OUT.mkdir(parents=True, exist_ok=True)
RAW = OUT / '20251125_ko464_s.pdf'

req = urllib.request.Request(URL, headers={
    'User-Agent': 'PROJECT-VEIL-research-runner/1.0 (+GitHub Actions; evidence acquisition)',
    'Accept': 'application/pdf,*/*',
})
with urllib.request.urlopen(req, timeout=120) as r:
    data = r.read()
    status = getattr(r, 'status', 200)
    ctype = r.headers.get('Content-Type')
    final_url = r.geturl()
RAW.write_bytes(data)
sha = hashlib.sha256(data).hexdigest()

reader = PdfReader(str(RAW))
text = '\n'.join((p.extract_text() or '') for p in reader.pages)
normalized = re.sub(r'\s+', '', text)

# Public-safe extraction only. Never emit names, body descriptors, unit numbers,
# or the raw extracted payload in the machine report.
facility_confirmed = '梅若公園' in normalized
notice_number_confirmed = ('第464号' in normalized) or ('464号' in normalized)
# Keep event-date metadata coarse/public. Exact occurrence details remain internal.
dates = sorted(set(re.findall(r'令和\s*7\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', text)))
report = {
    'project': 'PROJECT_VEIL',
    'resourceKey': 'SUMIDA_NOTICE_464_2025_UMEWAKA_PARK_DECEASED',
    'sourceUrl': URL,
    'httpStatus': status,
    'contentType': ctype,
    'finalUrl': final_url,
    'bytes': len(data),
    'sha256': sha,
    'pageCount': len(reader.pages),
    'facilityConfirmed': facility_confirmed,
    'notice464Confirmed': notice_number_confirmed,
    'publicEventPeriod': '2025-08' if facility_confirmed else None,
    'publicLocationPrecision': 'facility_site' if facility_confirmed else None,
    'publicFacilityName': '梅若公園' if facility_confirmed else None,
    'publicEventType': 'unidentified_deceased_found' if facility_confirmed else None,
    'rawTextStoredInReport': False,
    'privacyRule': 'Do not expose person description, exact body position, or other identifying/raw notice fields in public API.',
    'convergenceRule': 'Independent modern event may count only at facility-site precision after source/geometry linkage; never as exact death point.',
    'dateTokensObserved': dates,
}
(OUT / 'sumida-umewaka-incident-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: report[k] for k in ['httpStatus','bytes','sha256','pageCount','facilityConfirmed','notice464Confirmed','publicLocationPrecision']}, ensure_ascii=False))
if status != 200 or not facility_confirmed or not notice_number_confirmed:
    raise SystemExit('official incident source gate not closed')
