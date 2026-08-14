#!/usr/bin/env python3
import hashlib, json, os, pathlib, re, urllib.request, urllib.error
from pypdf import PdfReader

URL='https://www.city.sumida.lg.jp/kenko_fukushi/tiikihukusi_sonota/tiiki_hukusi/kouryo.files/20251125_ko464_s.pdf'
OUT=pathlib.Path(os.environ.get('VEIL_UMEWAKA_INCIDENT_OUT','veil-umewaka-incident-probe')); OUT.mkdir(parents=True,exist_ok=True)
RAW=OUT/'20251125_ko464_s.pdf'
report={'project':'PROJECT_VEIL','resourceKey':'SUMIDA_NOTICE_464_2025_UMEWAKA_PARK_DECEASED','sourceUrl':URL,'rawArtifactAcquired':False,'sourceGateStatus':'SOURCE_ACCESS_PENDING','rawTextStoredInReport':False,'privacyRule':'Do not expose person description, exact body position, belongings, or raw notice payload in public API.'}
try:
    req=urllib.request.Request(URL,headers={'User-Agent':'PROJECT-VEIL-research-runner/1.0 (+GitHub Actions; evidence acquisition)','Accept':'application/pdf,*/*'})
    with urllib.request.urlopen(req,timeout=120) as r:
        data=r.read(); status=getattr(r,'status',200); ctype=r.headers.get('Content-Type'); final=r.geturl()
    RAW.write_bytes(data)
    reader=PdfReader(str(RAW)); text='\n'.join((p.extract_text() or '') for p in reader.pages); norm=re.sub(r'\s+','',text)
    facility='梅若公園' in norm; notice=('第464号' in norm) or ('464号' in norm)
    report.update({'httpStatus':status,'contentType':ctype,'finalUrl':final,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'pageCount':len(reader.pages),'facilityConfirmed':facility,'notice464Confirmed':notice,'rawArtifactAcquired':True,'sourceGateStatus':'ACQUIRED_PRIMARY_CONFIRMED' if facility and notice else 'ACQUIRED_CONTENT_MISMATCH','publicEventPeriod':'2025-08' if facility else None,'publicLocationPrecision':'facility_site' if facility else None,'publicFacilityName':'梅若公園' if facility else None,'publicEventType':'unidentified_deceased_found' if facility else None,'dateTokensObserved':sorted(set(re.findall(r'令和\s*7\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日',text)))})
except urllib.error.HTTPError as e:
    report.update({'httpStatus':e.code,'contentType':e.headers.get('Content-Type') if e.headers else None,'sourceGateStatus':f'SOURCE_ACCESS_PENDING_HTTP_{e.code}','errorClass':'HTTPError'})
except Exception as e:
    report.update({'sourceGateStatus':'SOURCE_ACCESS_PENDING_ERROR','errorClass':type(e).__name__})

(OUT/'sumida-umewaka-incident-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report.get(k) for k in ['httpStatus','sourceGateStatus','rawArtifactAcquired','facilityConfirmed','notice464Confirmed']},ensure_ascii=False))
# A completed probe is successful even when source access is pending. Evidence
# promotion is controlled by sourceGateStatus, never by workflow color.
