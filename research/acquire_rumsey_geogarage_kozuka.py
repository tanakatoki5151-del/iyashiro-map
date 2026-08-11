#!/usr/bin/env python3
"""Capture georeferenced Tokyo 1858/1892 map evidence at Kozukappara.

The UC Berkeley/Rumsey GeoGarage pages expose maps already georectified for
interactive viewing. This probe opens the ordinary public pages, moves the map
to the Kozukappara research point when a Google/Leaflet/OpenLayers map object is
available, saves screenshots and public tile responses, and records the map
state. It does not redistribute a full source map or change scoring.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("out-rumsey-geogarage-kozuka")
TARGET = {"lat": 35.73227, "lng": 139.797806}
PAGES = {
    "tokyo1858": "https://rumsey.geogarage.com/maps/g_ea173.html",
    "tokyo1892": "https://rumsey.geogarage.com/maps/geb133.html",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for key, url in PAGES.items():
            d = OUT / key
            d.mkdir(exist_ok=True)
            context = await browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1200})
            page = await context.new_page()
            network = []
            saved = []

            async def on_response(response):
                row = {"url": response.url, "status": response.status, "contentType": response.headers.get("content-type")}
                network.append(row)
                low = response.url.lower()
                ct = (row["contentType"] or "").lower()
                if response.status != 200 or not ("tile" in low or "geogarage" in low or "image" in ct or low.endswith((".png", ".jpg", ".jpeg"))):
                    return
                try:
                    body = await response.body()
                except Exception:
                    return
                if not body or len(body) > 8_000_000:
                    return
                if body[:4] != b"\x89PNG" and body[:3] != b"\xff\xd8\xff":
                    return
                digest = hashlib.sha256(body).hexdigest()
                ext = ".png" if body[:4] == b"\x89PNG" else ".jpg"
                name = f"tile_{len(saved):04d}_{digest[:12]}{ext}"
                path = d / name
                path.write_bytes(body)
                saved.append({**row, "savedAs": name, "bytes": len(body), "sha256": digest})

            page.on("response", lambda r: asyncio.create_task(on_response(r)))
            await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_timeout(12_000)
            await page.screenshot(path=str(d / "01_initial.png"), full_page=True)
            (d / "01_initial.html").write_text(await page.content(), encoding="utf-8")

            globals_hint = await page.evaluate("Object.keys(window).filter(k=>/map|google|leaflet|openlayer|overlay/i.test(k)).slice(0,300)")
            move_result = await page.evaluate(
                """target => {
                  const out={attempts:[]};
                  function tryMap(name,m){
                    if(!m) return false;
                    try{
                      if(typeof m.setCenter==='function'){
                        if(window.google&&google.maps&&google.maps.LatLng) m.setCenter(new google.maps.LatLng(target.lat,target.lng));
                        else m.setCenter([target.lat,target.lng]);
                        if(typeof m.setZoom==='function') m.setZoom(17);
                        out.attempts.push({name,method:'setCenter/setZoom',ok:true}); return true;
                      }
                      if(typeof m.setView==='function'){
                        m.setView([target.lat,target.lng],17);
                        out.attempts.push({name,method:'setView',ok:true}); return true;
                      }
                      if(typeof m.getView==='function'){
                        const v=m.getView();
                        if(v&&typeof v.setCenter==='function'){
                          const c=(window.ol&&ol.proj&&ol.proj.fromLonLat)?ol.proj.fromLonLat([target.lng,target.lat]):[target.lng,target.lat];
                          v.setCenter(c); if(typeof v.setZoom==='function')v.setZoom(17);
                          out.attempts.push({name,method:'OpenLayers view',ok:true}); return true;
                        }
                      }
                    }catch(e){out.attempts.push({name,ok:false,error:String(e)});}
                    return false;
                  }
                  const preferred=['map','gmap','googleMap','mymap','olMap','leafletMap'];
                  for(const k of preferred){if(tryMap(k,window[k])){out.movedBy=k;break;}}
                  if(!out.movedBy){
                    for(const k of Object.keys(window)){
                      if(!/map/i.test(k)) continue;
                      let v; try{v=window[k];}catch(e){continue;}
                      if(tryMap(k,v)){out.movedBy=k;break;}
                    }
                  }
                  out.href=location.href;
                  return out;
                }""",
                TARGET,
            )
            await page.wait_for_timeout(12_000)
            await page.screenshot(path=str(d / "02_kozuka_target.png"), full_page=True)
            (d / "02_after.html").write_text(await page.content(), encoding="utf-8")
            body_text = await page.locator("body").inner_text()
            (d / "body.txt").write_text(body_text, encoding="utf-8")
            resources = await page.evaluate("performance.getEntriesByType('resource').map(e=>e.name)")
            map_state = await page.evaluate(
                """() => {
                  const o={};
                  for(const k of ['map','gmap','googleMap','mymap','olMap','leafletMap']){
                    const m=window[k]; if(!m)continue;
                    try{
                      o[k]={
                        center:typeof m.getCenter==='function'?String(m.getCenter()):null,
                        zoom:typeof m.getZoom==='function'?m.getZoom():null,
                        bounds:typeof m.getBounds==='function'?String(m.getBounds()):null
                      };
                    }catch(e){o[k]={error:String(e)}}
                  }
                  return o;
                }"""
            )
            (d / "network.json").write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "saved-tiles.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "resources.json").write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "globals.json").write_text(json.dumps(globals_hint, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "move-result.json").write_text(json.dumps(move_result, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "map-state.json").write_text(json.dumps(map_state, ensure_ascii=False, indent=2), encoding="utf-8")
            reports.append({"key":key,"url":url,"moveResult":move_result,"mapState":map_state,"networkCount":len(network),"savedTileCount":len(saved)})
            await context.close()
        await browser.close()

    summary = {
        "target": TARGET,
        "reports": reports,
        "qualityRule": "Copyrighted historical map imagery is retained only as a research screenshot/tile evidence package. Derived boundary work must record source URLs and independent control points; no scoring change follows from this acquisition alone.",
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{sha256(p)}  {p.relative_to(OUT)}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
