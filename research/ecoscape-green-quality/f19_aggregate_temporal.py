#!/usr/bin/env python3
"""Aggregate 32 F19 spatial shards into one 120,662-cell temporal delta."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter

PERIODS=["SPRING","EARLY_SUMMER","PEAK_SUMMER","AUTUMN_RECOVERY","WINTER_DIAGNOSTIC"]
FULL_YEARS=list(range(2019,2026))

def slope(values,years):
    v=np.asarray(values,dtype=float); y=np.asarray(years,dtype=float)
    m=np.isfinite(v)&np.isfinite(y)
    return float(np.polyfit(y[m],v[m],1)[0]) if m.sum()>=4 else np.nan

def mad(values):
    v=np.asarray(values,dtype=float); v=v[np.isfinite(v)]
    if not len(v): return np.nan
    med=np.median(v); return float(np.median(np.abs(v-med)))

def neighborhood(df,value_col,size):
    rows=sorted(df.gridRow.unique()); cols=sorted(df.gridCol.unique())
    rmap={v:i for i,v in enumerate(rows)}; cmap={v:i for i,v in enumerate(cols)}
    arr=np.full((len(rows),len(cols)),np.nan,dtype=float)
    for row in df[["gridRow","gridCol",value_col]].itertuples(index=False):
        arr[rmap[row.gridRow],cmap[row.gridCol]]=row[2]
    valid=np.isfinite(arr).astype(float); vals=np.nan_to_num(arr)
    sums=uniform_filter(vals,size=size,mode="constant",cval=0)*size*size
    counts=uniform_filter(valid,size=size,mode="constant",cval=0)*size*size
    mean=np.divide(sums,counts,out=np.full_like(sums,np.nan),where=counts>0)
    return np.array([mean[rmap[r.gridRow],cmap[r.gridCol]] for r in df[["gridRow","gridCol"]].itertuples(index=False)])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--grid',required=True); ap.add_argument('--output',required=True); args=ap.parse_args()
    root=Path(args.input); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    sfiles=sorted(root.rglob('F19_SENTINEL_PERIOD_SHARD_*.csv.gz')); lfiles=sorted(root.rglob('F19_LANDSAT_SUMMER_SHARD_*.csv.gz'))
    if len(sfiles)!=32 or len(lfiles)!=32: raise RuntimeError(f'shard files sentinel={len(sfiles)} landsat={len(lfiles)}')
    s=pd.concat([pd.read_csv(p) for p in sfiles],ignore_index=True); l=pd.concat([pd.read_csv(p) for p in lfiles],ignore_index=True)
    grid=pd.read_csv(args.grid,compression='gzip')
    records=[]
    for cell,g in s.groupby('canonicalCellId'):
        rec={'canonicalCellId':cell}
        for period in PERIODS:
            pg=g[(g.period==period)&g.year.isin(FULL_YEARS)].sort_values('year')
            rec[f'{period.lower()}Years']=int(pg.ndviMedian.notna().sum())
            for metric in ['ndviMedian','eviMedian','ndmiMedian','ndreMedian']:
                rec[f'{period.lower()}_{metric}']=float(pg[metric].median()) if pg[metric].notna().any() else np.nan
                rec[f'{period.lower()}_{metric}_trend']=slope(pg[metric],pg.year)
                rec[f'{period.lower()}_{metric}_mad']=mad(pg[metric])
        es=rec.get('early_summer_ndviMedian',np.nan); ps=rec.get('peak_summer_ndviMedian',np.nan); ar=rec.get('autumn_recovery_ndviMedian',np.nan)
        rec['summerStressDrop']=es-ps if np.isfinite(es) and np.isfinite(ps) else np.nan
        rec['autumnRecovery']=ar-ps if np.isfinite(ar) and np.isfinite(ps) else np.nan
        records.append(rec)
    t=pd.DataFrame(records)
    heat=[]
    for cell,g in l.groupby('canonicalCellId'):
        g=g[g.year.isin(FULL_YEARS)].sort_values('year')
        heat.append({'canonicalCellId':cell,'heatYears':int(g.lstMedianC.notna().sum()),'multiSummerLSTMedianC':float(g.lstMedianC.median()) if g.lstMedianC.notna().any() else np.nan,'multiSummerLSTP90C':float(g.lstP90C.median()) if g.lstP90C.notna().any() else np.nan,'multiSummerLSTTrendCPerYear':slope(g.lstMedianC,g.year),'multiSummerLSTMAD':mad(g.lstMedianC)})
    t=t.merge(pd.DataFrame(heat),on='canonicalCellId',how='outer').merge(grid[['canonicalCellId','gridRow','gridCol']],on='canonicalCellId',how='right')
    for metric,prefix in [('peak_summer_ndviMedian','vitality'),('peak_summer_ndmiMedian','moisture'),('multiSummerLSTMedianC','heat')]:
        t[f'{prefix}300m']=neighborhood(t,metric,3); t[f'{prefix}500m']=neighborhood(t,metric,5)
    core_years=t[['springYears','peak_summerYears','autumn_recoveryYears']].min(axis=1)
    t['temporalConfidence']=np.select([(core_years>=5)&(t.heatYears>=5),(core_years>=4)&(t.heatYears>=3)],['HIGH','MEDIUM'],default='LOW')
    t['temporalStatus']=np.where(core_years>=4,'MULTI_YEAR_MEASURED','INSUFFICIENT_OBSERVATIONS')
    t.to_csv(out/'ECOSCAPE_F19_TEMPORAL_DELTA_120662.csv.gz',index=False,compression='gzip')
    audit={'buildId':'ecoscape-f19-full-domain-temporal-v1','rows':len(t),'uniqueCells':int(t.canonicalCellId.nunique()),'sentinelRows':len(s),'landsatRows':len(l),'measuredCells':int((t.temporalStatus=='MULTI_YEAR_MEASURED').sum()),'confidenceCounts':t.temporalConfidence.value_counts().to_dict(),'rankingEffect':'none','scoringEffect':'none','candidateOverride':0}
    (out/'ECOSCAPE_F19_TEMPORAL_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
