#!/usr/bin/env python3
import hashlib,json,time
from pathlib import Path
OUT=Path('output')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read(name):
 p=OUT/name
 try:return json.loads(p.read_text(encoding='utf-8'))
 except Exception as e:return {'status':'MISSING_OR_INVALID','error':str(e)}
summary={'schema':'IYASHIRO_OFFICIAL_CLOSURE_ARTIFACT_v1','generated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_project_writes':0,'ranking_effect':0,'site_code_changes':0,'source_status':read('SOURCE_STATUS.json'),'portal_status':read('PORTAL_STATUS.json')}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
files=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and p.name!='FILE_INVENTORY.json':files.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
(OUT/'FILE_INVENTORY.json').write_text(json.dumps({'generated_utc':summary['generated_utc'],'files':files},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':len(files),'summary':str(OUT/'SUMMARY.json')},ensure_ascii=False))
