import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const municipalities = [
  ['13101','千代田区','TOKYO23','東京都',''],['13102','中央区','TOKYO23','東京都',''],['13103','港区','TOKYO23','東京都',''],['13104','新宿区','TOKYO23','東京都',''],['13105','文京区','TOKYO23','東京都',''],['13106','台東区','TOKYO23','東京都',''],['13107','墨田区','TOKYO23','東京都',''],['13108','江東区','TOKYO23','東京都',''],['13109','品川区','TOKYO23','東京都',''],['13110','目黒区','TOKYO23','東京都',''],['13111','大田区','TOKYO23','東京都',''],['13112','世田谷区','TOKYO23','東京都',''],['13113','渋谷区','TOKYO23','東京都',''],['13114','中野区','TOKYO23','東京都',''],['13115','杉並区','TOKYO23','東京都',''],['13116','豊島区','TOKYO23','東京都',''],['13117','北区','TOKYO23','東京都',''],['13118','荒川区','TOKYO23','東京都',''],['13119','板橋区','TOKYO23','東京都',''],['13120','練馬区','TOKYO23','東京都',''],['13121','足立区','TOKYO23','東京都',''],['13122','葛飾区','TOKYO23','東京都',''],['13123','江戸川区','TOKYO23','東京都',''],
  ['14101','横浜市鶴見区','YOKOHAMA','神奈川県','横浜市'],['14102','横浜市神奈川区','YOKOHAMA','神奈川県','横浜市'],['14103','横浜市西区','YOKOHAMA','神奈川県','横浜市'],['14104','横浜市中区','YOKOHAMA','神奈川県','横浜市'],['14105','横浜市南区','YOKOHAMA','神奈川県','横浜市'],['14106','横浜市保土ケ谷区','YOKOHAMA','神奈川県','横浜市'],['14107','横浜市磯子区','YOKOHAMA','神奈川県','横浜市'],['14108','横浜市金沢区','YOKOHAMA','神奈川県','横浜市'],['14109','横浜市港北区','YOKOHAMA','神奈川県','横浜市'],['14110','横浜市戸塚区','YOKOHAMA','神奈川県','横浜市'],['14111','横浜市港南区','YOKOHAMA','神奈川県','横浜市'],['14112','横浜市旭区','YOKOHAMA','神奈川県','横浜市'],['14113','横浜市緑区','YOKOHAMA','神奈川県','横浜市'],['14114','横浜市瀬谷区','YOKOHAMA','神奈川県','横浜市'],['14115','横浜市栄区','YOKOHAMA','神奈川県','横浜市'],['14116','横浜市泉区','YOKOHAMA','神奈川県','横浜市'],['14117','横浜市青葉区','YOKOHAMA','神奈川県','横浜市'],['14118','横浜市都筑区','YOKOHAMA','神奈川県','横浜市'],
  ['14131','川崎市川崎区','KAWASAKI','神奈川県','川崎市'],['14132','川崎市幸区','KAWASAKI','神奈川県','川崎市'],['14133','川崎市中原区','KAWASAKI','神奈川県','川崎市'],['14134','川崎市高津区','KAWASAKI','神奈川県','川崎市'],['14135','川崎市多摩区','KAWASAKI','神奈川県','川崎市'],['14136','川崎市宮前区','KAWASAKI','神奈川県','川崎市'],['14137','川崎市麻生区','KAWASAKI','神奈川県','川崎市'],
];

const outRoot = process.env.VEIL_NICHIBUNKEN_OUT || 'veil-nichibunken-out';
const rawDir = path.join(outRoot, 'raw');
const reportDir = path.join(outRoot, 'reports');
fs.mkdirSync(rawDir, { recursive: true });
fs.mkdirSync(reportDir, { recursive: true });

const endpoint = 'https://sekiei.nichibun.ac.jp/cgi-bin/YoukaiDB3/msearch/msearch.cgi';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sha256 = b => crypto.createHash('sha256').update(b).digest('hex');

async function fetchWithRetry(url, attempts = 3) {
  let last;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(url, { headers: { 'user-agent': 'PROJECT-VEIL-research/1.0 (+noncommercial evidence QA)' } });
      const ab = await res.arrayBuffer();
      const bytes = Buffer.from(ab);
      if (res.ok) return { res, bytes };
      last = new Error(`HTTP ${res.status}`);
      if (![429,500,502,503,504].includes(res.status)) return { res, bytes };
    } catch (e) { last = e; }
    await sleep(1000 * (i + 1));
  }
  throw last || new Error('fetch failed');
}

function parseHitCount(html) {
  const normalized = html.replace(/,/g, '');
  const m = normalized.match(/([0-9]+)件ヒットしました/);
  return m ? Number(m[1]) : null;
}

const rows = [];
for (let i = 0; i < municipalities.length; i++) {
  const [code, municipalityName, region, prefecture, parentCity] = municipalities[i];
  const u = new URL(endpoint);
  u.searchParams.set('config', '');
  u.searchParams.set('hint', 'ひらがな');
  u.searchParams.set('index', '');
  u.searchParams.set('num', '100');
  u.searchParams.set('query', municipalityName);
  u.searchParams.set('set', '1');
  const row = { code, municipalityName, region, prefecture, parentCity, queryType: 'F1_FULLTEXT_CURRENT_MUNICIPALITY_RECALL_ONLY', query: municipalityName, sourceURL: u.toString(), scoringEffect: 'none', directCellClaim: false, convergenceEligible: false };
  try {
    const { res, bytes } = await fetchWithRetry(u);
    const html = bytes.toString('utf8');
    const rawPath = path.join(rawDir, `${code}.html`);
    fs.writeFileSync(rawPath, bytes);
    Object.assign(row, { httpStatus: res.status, finalURL: res.url, bytes: bytes.length, sha256: sha256(bytes), hitCount: parseHitCount(html), rawPath, status: res.ok ? 'ACQUIRED_RECALL_PAGE' : 'HTTP_ERROR' });
  } catch (e) {
    Object.assign(row, { status: 'FETCH_ERROR', error: String(e?.message || e), hitCount: null });
  }
  rows.push(row);
  console.log(`VEIL_NICHIBUNKEN ${code} ${municipalityName} status=${row.status} hits=${row.hitCount ?? 'NA'}`);
  if (i < municipalities.length - 1) await sleep(250);
}

const byRegion = {};
for (const r of rows) {
  byRegion[r.region] ||= { municipalities: 0, acquired: 0, queryErrors: 0, rawHitCountSumRecallOnly: 0, unknownHitCounts: 0 };
  const s = byRegion[r.region];
  s.municipalities++;
  if (r.status === 'ACQUIRED_RECALL_PAGE') s.acquired++; else s.queryErrors++;
  if (Number.isInteger(r.hitCount)) s.rawHitCountSumRecallOnly += r.hitCount; else s.unknownHitCounts++;
}
const summary = {
  buildId: 'VEIL-B17-NICHIBUNKEN-48-BROAD-RUN-v1',
  generatedAt: new Date().toISOString(),
  source: { authority: '国際日本文化研究センター 怪異・妖怪伝承データベース', endpoint, mode: 'full-text recall-only', requestedPerQueryMaxDisplay: 100 },
  contract: { municipalityCount: municipalities.length, directCellClaim: false, scoringEffect: 'none', convergenceEligible: false, note: 'Full-text municipality-name hits are discovery recall only. A hit is not location proof, not a 100m assignment, and may include current-name crosswalk text or false positives.' },
  results: { acquired: rows.filter(r => r.status === 'ACQUIRED_RECALL_PAGE').length, queryErrors: rows.filter(r => r.status !== 'ACQUIRED_RECALL_PAGE').length, municipalitiesWithParsedHitCount: rows.filter(r => Number.isInteger(r.hitCount)).length, municipalitiesWithAtLeastOneRecallHit: rows.filter(r => Number.isInteger(r.hitCount) && r.hitCount > 0).length, rawHitCountSumRecallOnly: rows.reduce((a,r)=>a+(Number.isInteger(r.hitCount)?r.hitCount:0),0), byRegion },
  nextGate: ['Parse/deduplicate record identities from result pages.', 'Validate prefecture/city-county fields using advanced search before geographic promotion.', 'Expand historical toponyms and place-name seeds only after F1 QA.', 'Do not assign canonical cells without independent location evidence.']
};
fs.writeFileSync(path.join(reportDir, 'nichibunken-48-summary.json'), JSON.stringify(summary, null, 2));
fs.writeFileSync(path.join(reportDir, 'nichibunken-48-results.jsonl'), rows.map(r => JSON.stringify(r)).join('\n') + '\n');
console.log('VEIL_NICHIBUNKEN_SUMMARY=' + JSON.stringify(summary));
if (summary.results.queryErrors > 0) process.exitCode = 1;
