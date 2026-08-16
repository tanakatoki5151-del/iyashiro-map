#!/usr/bin/env python3
import json,struct,requests,urllib.parse,hashlib
from pathlib import Path
ROOT='https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/14103-bldg-lod1-texture-2024/tileset.json'
s=requests.Session();s.headers['User-Agent']='ECOSCAPE-PLATEAU-3DTILES-PROBE/1.0'
def getj(u):
 r=s.get(u,timeout=(20,120));r.raise_for_status();return r.json(),r.url
def matmul(a,b):
 # column-major 4x4
 c=[0.0]*16
 for col in range(4):
  for row in range(4):c[col*4+row]=sum(a[k*4+row]*b[col*4+k] for k in range(4))
 return c
I=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
leaves=[];visited=set()
def walk(ts_url,parent=I,depth=0):
 if ts_url in visited:return
 visited.add(ts_url);ts,final=getj(ts_url);base=final.rsplit('/',1)[0]+'/'
 def tile(t,pm,d):
  m=matmul(pm,t.get('transform',I));content=t.get('content') or {};uri=content.get('uri') or content.get('url')
  if uri:
   u=urllib.parse.urljoin(base,uri)
   if uri.lower().endswith('.json'):
    walk(u,m,d+1)
   else:leaves.append({'url':u,'depth':d,'transform':m,'boundingVolume':t.get('boundingVolume'),'geometricError':t.get('geometricError')})
  for ch in t.get('children') or []:tile(ch,m,d+1)
 tile(ts['root'],parent,depth)
walk(ROOT)
out={'root':ROOT,'externalTilesetsVisited':len(visited),'contentTiles':len(leaves),'samples':[]}
for leaf in leaves[:3]:
 r=s.get(leaf['url'],timeout=(20,120));r.raise_for_status();b=r.content;magic=b[:4].decode('ascii','replace');rec={**leaf,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'magic':magic,'finalUrl':r.url}
 if magic=='b3dm':
  vals=struct.unpack_from('<7I',b,4);version,byteLength,ftj,ftb,btj,btb=vals;off=28;ft=json.loads(b[off:off+ftj].decode('utf-8').strip() or '{}');off+=ftj+ftb;bt_raw=b[off:off+btj].decode('utf-8','replace').strip();bt=json.loads(bt_raw or '{}');off+=btj+btb;glb=b[off:]
  rec.update({'b3dm':{'version':version,'byteLength':byteLength,'featureTableJSONBytes':ftj,'featureTableBinaryBytes':ftb,'batchTableJSONBytes':btj,'batchTableBinaryBytes':btb,'featureTable':ft,'batchTableKeys':list(bt)[:30],'glbOffset':off,'glbMagic':glb[:4].decode('ascii','replace')}})
  if glb[:4]==b'glTF':
   _,gv,glen=struct.unpack_from('<4sII',glb,0);clen,ctype=struct.unpack_from('<II',glb,12);gj=json.loads(glb[20:20+clen].decode('utf-8').rstrip('\x00 '));rec['gltf']={'version':gv,'length':glen,'asset':gj.get('asset'),'extensionsUsed':gj.get('extensionsUsed'),'extensions':gj.get('extensions'),'nodes':gj.get('nodes',[])[:5],'meshesCount':len(gj.get('meshes',[])),'accessorsCount':len(gj.get('accessors',[])),'bufferViewsCount':len(gj.get('bufferViews',[])),'firstMesh':(gj.get('meshes') or [None])[0]}
 elif magic=='glTF':rec['note']='direct GLB'
 out['samples'].append(rec)
Path('output').mkdir(exist_ok=True);Path('output/PLATEAU_3DTILES_PROBE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'externalTilesetsVisited':len(visited),'contentTiles':len(leaves),'sampleMagics':[x['magic'] for x in out['samples']]},indent=2))
