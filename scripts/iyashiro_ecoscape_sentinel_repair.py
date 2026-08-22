#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json
from pathlib import Path
import requests

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pilot',HERE/'iyashiro_ecoscape_temporal_pilot.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
mod.OUT=Path('output/ecoscape_temporal_v2');mod.OUT.mkdir(parents=True,exist_ok=True)

def search_stac(url,collection,dt,cloud=35):
    body={'collections':[collection],'bbox':mod.BBOX,'datetime':dt,'limit':100}
    r=mod.SESSION.post(url.rstrip('/')+'/search',json=body,timeout=(30,180))
    if r.status_code>=400:
        raise RuntimeError(f'STAC {r.status_code}: {r.text[:1500]}')
    feats=r.json().get('features',[])
    return [x for x in feats if float(x.get('properties',{}).get('eo:cloud_cover',100))<cloud] or feats

mod.search_stac=search_stac
mod.main()
