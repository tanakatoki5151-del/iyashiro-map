#!/usr/bin/env python3
"""Extract address/xAL attributes for the high-value PLATEAU building candidates.

Uses the exact 2025 CityGML source files and candidate gml:ids fixed by
v10-b41-plateau-crosssource-v1 (artifact 9232731261). Diagnostic only.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import requests
from lxml import etree

OUT=Path('out-b41-plateau-candidate-address-v1')
TARGETS=[
 {'propertyId':'BLDG-6583382c8322','name':'レ・サン・サーンス','expectedAddress':'東京都目黒区目黒本町5丁目29-12','gmlId':'bldg_7b54ce02-37b0-4c5d-99e3-24f184f5d7fe','buildingID':'13110-bldg-1504','sourceCityCode':'13109','sourceCityName':'品川区','url':'https://assets.cms.plateau.reearth.io/assets/4b/90d7b7-679a-46d4-a842-7706fec36d40/13109_shinagawa-ku_pref_2025_citygml_1_op/udx/bldg/53393545_bldg_6697_op.gml','sourceSha256':'baa900ffcbfafb213cd74b5f1d2416e5bb1bb50bb8adb4d841b88eb57e5d33a9'},
 {'propertyId':'BLDG-edf6c2448f9e','name':'エスティメゾン代沢','expectedAddress':'東京都世田谷区代沢2丁目39-13','gmlId':'bldg_31b5fd98-da35-4c9e-9b0e-20a47c2f51c8','buildingID':'13112-bldg-118096','sourceCityCode':'13112','sourceCityName':'世田谷区','url':'https://assets.cms.plateau.reearth.io/assets/b4/38c131-2e1e-4226-95f7-44f2b12debd7/13112_setagaya-ku_pref_2025_citygml_1_op/udx/bldg/53393593_bldg_6697_op.gml','sourceSha256':'0031349149f89a35d117fe36cdcd770948654d4acba95c823e04457579b16dfe'},
 {'propertyId':'BLDG-4e6c9a14c783','name':'レオパレス駒場東大前','expectedAddress':'東京都目黒区駒場4丁目3-21','gmlId':'bldg_eea5678b-c018-44ba-bc6c-56b241eee276','buildingID':'13110-bldg-45829','sourceCityCode':'13110','sourceCityName':'目黒区','url':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/bldg/53393594_bldg_6697_op.gml','sourceSha256':'17c1ad44f0cc932cf537d2547e8c12caf8a25352ce0327c987130a2bbf8d6c56'},
 {'propertyId':'BLDG-c404c81c08a5','name':'プリュメゾン駒沢','expectedAddress':'東京都目黒区東が丘1丁目16-26','gmlId':'bldg_958e8009-cbab-4089-b09f-06e45eba935d','buildingID':'13110-bldg-50639','sourceCityCode':'13110','sourceCityName':'目黒区','url':'https://assets.cms.plateau.reearth.io/assets/c1/5af712-42ee-403a-bad5-f5d82f8b2492/13110_meguro-ku_pref_2025_citygml_1_op/udx/bldg/53393553_bldg_6697_op.gml','sourceSha256':'1c76b1e9e695a6c0dfd3afe678373d0543f1e328f753bef87fbf9a44ec5e3199'},
]
GML_ID='{http://www.opengis.net/gml}id'

def lname(tag): return tag.split('}')[-1] if '}' in tag else tag

def clean_text(x): return ' '.join((x or '').split())

def extract_address(building):
 addresses=[]
 for node in building.iter():
  if lname(node.tag)!='address': continue
  vals=[]
  structured={}
  for d in node.iter():
   txt=clean_text(d.text)
   if not txt: continue
   n=lname(d.tag)
   vals.append({'element':n,'text':txt})
   structured.setdefault(n,[])
   if txt not in structured[n]: structured[n].append(txt)
  addresses.append({'texts':vals,'structured':structured})
 return addresses

def extract_generic(building):
 out=[]
 for n in building.iter():
  if lname(n.tag) not in {'stringAttribute','intAttribute','doubleAttribute'}: continue
  name=n.get('name')
  value=None
  for c in n:
   if lname(c.tag)=='value' and c.text: value=clean_text(c.text)
  if name and value: out.append({'name':name,'value':value})
 return out

def normalize(s):
 repl={'東京都':'','丁目':'','番':'-','号':'','－':'-','−':'-','ー':'-','‐':'-',' ':''}
 for a,b in repl.items(): s=s.replace(a,b)
 return s.lower()

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sess=requests.Session(); sess.headers['User-Agent']='iyashiro-v10-research/1.0'
 items=[]
 for t in TARGETS:
  r=sess.get(t['url'],timeout=90); r.raise_for_status(); blob=r.content
  sha=hashlib.sha256(blob).hexdigest()
  source_integrity=(sha==t['sourceSha256'])
  root=etree.fromstring(blob)
  b=None
  for x in root.iter():
   if lname(x.tag)=='Building' and x.get(GML_ID)==t['gmlId']:
    b=x; break
  if b is None: raise RuntimeError(f"candidate not found {t['gmlId']}")
  addresses=extract_address(b); generic=extract_generic(b)
  flattened=' | '.join(v['text'] for a in addresses for v in a['texts'])
  expected_norm=normalize(t['expectedAddress'])
  flat_norm=normalize(flattened)
  exact_or_contains=bool(expected_norm and (expected_norm in flat_norm or flat_norm in expected_norm)) if flat_norm else False
  items.append({**t,'downloadedBytes':len(blob),'actualSha256':sha,'sourceIntegrityMatchesPriorArtifact':source_integrity,'addresses':addresses,'genericAttributes':generic,'flattenedAddressText':flattened,'normalizedExpectedAddress':expected_norm,'normalizedCandidateAddress':flat_norm,'expectedAddressTextMatch':exact_or_contains,'formalPromotion':False,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'})
 summary={'schemaVersion':'v10-b41-plateau-candidate-address-v1','generatedAt':datetime.now(timezone.utc).isoformat(),'sourceArtifact':{'artifactId':9232731261,'digest':'sha256:17ec70a1db7a0348556b340e97a89124d65066a5ad9dc2c2e4e08767837e0057'},'items':items,'policy':{'formalPromotion':0,'scoringEffect':'none','rankingEffect':'none','automaticExclusionEffect':'none'}}
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 md=['# V10 B41 PLATEAU candidate address audit v1','']
 for x in items:
  md += [f"## {x['name']}",f"Expected: `{x['expectedAddress']}`",f"PLATEAU address text: `{x['flattenedAddressText'] or '(none)'}`",f"Text match: `{x['expectedAddressTextMatch']}`",f"Source city: `{x['sourceCityCode']} {x['sourceCityName']}`; buildingID `{x['buildingID']}`",f"Source digest unchanged: `{x['sourceIntegrityMatchesPriorArtifact']}`",'']
 md += ['## Policy','- This audit does not promote a footprint.','- Candidate address absence is not evidence of mismatch because bldg:address is optional.','- An explicit contradictory address is a rejection signal.']
 (OUT/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 sums=[]
 for p in sorted(OUT.iterdir()):
  if p.name=='SHA256SUMS.txt' or not p.is_file(): continue
  sums.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
 (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 print(json.dumps({x['propertyId']:{'address':x['flattenedAddressText'],'match':x['expectedAddressTextMatch'],'city':x['sourceCityName'],'integrity':x['sourceIntegrityMatchesPriorArtifact']} for x in items},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
