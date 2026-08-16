#!/usr/bin/env python3
import json,struct,requests,urllib.parse
from pathlib import Path
import DracoPy,numpy as np
URL='https://assets.cms.plateau.reearth.io/assets/ad/5fd83a-161b-4a01-a666-a3e8c1c23759/14100_yokohama-shi_city_2024_citygml_2_op_bldg_3dtiles_14103_nishi-ku_lod1/data/data0.b3dm'
b=requests.get(URL,timeout=(20,120)).content
version,bl,ftj,ftb,btj,btb=struct.unpack_from('<6I',b,4);off=28+ftj+ftb+btj+btb;glb=b[off:]
_,gv,glen=struct.unpack_from('<4sII',glb,0);clen,ctype=struct.unpack_from('<II',glb,12);gj=json.loads(glb[20:20+clen].decode().rstrip('\x00 '));bin_off=20+clen
if bin_off%4:bin_off+=4-bin_off%4
blen,btype=struct.unpack_from('<II',glb,bin_off);binary=glb[bin_off+8:bin_off+8+blen]
prim=gj['meshes'][0]['primitives'][0];ext=prim['extensions']['KHR_draco_mesh_compression'];bv=gj['bufferViews'][ext['bufferView']];d=binary[int(bv.get('byteOffset',0)):int(bv.get('byteOffset',0))+int(bv['byteLength'])]
mesh=DracoPy.decode(d)
res={'dracoBytes':len(d),'dir':[x for x in dir(mesh) if not x.startswith('__')],'pointsShape':list(np.asarray(mesh.points).shape),'facesShape':list(np.asarray(mesh.faces).shape),'pointsDtype':str(np.asarray(mesh.points).dtype),'facesDtype':str(np.asarray(mesh.faces).dtype),'primitiveDracoAttributeMap':ext['attributes']}
for n in res['dir']:
 try:
  v=getattr(mesh,n)
  if isinstance(v,(str,int,float,bool,type(None))):res['attr_'+n]=v
  elif hasattr(v,'shape'):res['attr_'+n]={'shape':list(v.shape),'dtype':str(v.dtype),'sample':np.asarray(v).reshape(-1)[:20].tolist()}
  elif isinstance(v,dict):res['attr_'+n]={'type':'dict','keys':list(v.keys())[:30],'repr':repr(v)[:2000]}
  elif isinstance(v,(list,tuple)):res['attr_'+n]={'type':type(v).__name__,'len':len(v),'repr':repr(v[:3])[:1000]}
  else:res['attr_'+n]={'type':type(v).__name__,'repr':repr(v)[:1000]}
 except Exception as e:res['attr_'+n]={'error':str(e)}
Path('output').mkdir(exist_ok=True);Path('output/PLATEAU_DRACOPY_PROBE.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(res,ensure_ascii=False,indent=2)[:12000])
