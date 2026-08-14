import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const OUT = process.env.VEIL_NETWORK_OUT || 'veil-network-out';
const RAW = path.join(OUT, 'raw');
const REPORTS = path.join(OUT, 'reports');
const USER_AGENT = 'PROJECT-VEIL-research-runner/1.0 (+GitHub Actions; evidence acquisition)';

const downloadTargets = [
  {
    resourceKey: 'TOKYO_NAKANO_ARCH_0052',
    fileName: 'nakano_opendata_6000780.csv',
    url: 'https://www2.wagmap.jp/nakanodatamap/nakanodatamap/opendatafile/map_33/CSV/opendata_6000780.csv',
    kind: 'csv',
  },
  {
    resourceKey: 'TOKYO_SUMIDA_ARCH_SHP_0190',
    fileName: 'maizoubunkazai_20260330.zip',
    url: 'https://www.city.sumida.lg.jp/wkg/opendata/opendata_ichiran/matizukuri_map/maizoubunkazai_20260330.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14131_SHP2500_2024',
    fileName: '1kawasakiSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/1kawasakiSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14132_SHP2500_2024',
    fileName: '2saiwaiSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/2saiwaiSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14133_SHP2500_2024',
    fileName: '3nakaharaSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/3nakaharaSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14134_SHP2500_2024',
    fileName: '4takatuSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/4takatuSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14135_SHP2500_2024',
    fileName: '6tamaSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/6tamaSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14136_SHP2500_2024',
    fileName: '5miyamaeSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/5miyamaeSHP2500.zip',
    kind: 'zip',
  },
  {
    resourceKey: 'KAWASAKI_14137_SHP2500_2024',
    fileName: '7asaoSHP2500.zip',
    url: 'https://www.city.kawasaki.jp/500/cmsfiles/contents/0000138/138658/7asaoSHP2500.zip',
    kind: 'zip',
  },
];

const yokohamaWards = [
  '鶴見区','神奈川区','西区','中区','南区','港南区','保土ケ谷区','旭区','磯子区',
  '金沢区','港北区','緑区','青葉区','都筑区','戸塚区','栄区','泉区','瀬谷区',
];
const yokohamaBaseTerms = [
  '文化財','埋蔵文化財','遺跡','史跡','名所','石碑','記念碑','墓地','塚','神社','寺院','民俗','伝承','旧跡',
];
const yokohamaQueries = [...new Set([
  ...yokohamaBaseTerms,
  ...yokohamaWards.flatMap((ward) => [`${ward} 文化財`, `${ward} 史跡`, `${ward} 名所`]),
])];

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function nowIso() {
  return new Date().toISOString();
}

async function fetchWithTimeout(url, { timeoutMs = 45_000, headers = {} } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      redirect: 'follow',
      signal: controller.signal,
      headers: { 'user-agent': USER_AGENT, accept: '*/*', ...headers },
    });
  } finally {
    clearTimeout(timer);
  }
}

async function downloadOne(target) {
  const startedAt = nowIso();
  try {
    const response = await fetchWithTimeout(target.url, { timeoutMs: 120_000 });
    const finalUrl = response.url;
    const contentType = response.headers.get('content-type');
    const contentLength = response.headers.get('content-length');
    if (!response.ok) {
      return { ...target, status: 'HTTP_ERROR', httpStatus: response.status, contentType, contentLength, finalUrl, startedAt, finishedAt: nowIso() };
    }
    const buffer = Buffer.from(await response.arrayBuffer());
    const filePath = path.join(RAW, target.fileName);
    await writeFile(filePath, buffer);
    return {
      ...target,
      status: 'ACQUIRED',
      httpStatus: response.status,
      finalUrl,
      contentType,
      advertisedContentLength: contentLength ? Number(contentLength) : null,
      bytes: buffer.length,
      sha256: sha256(buffer),
      localPath: filePath,
      startedAt,
      finishedAt: nowIso(),
    };
  } catch (error) {
    return { ...target, status: 'FETCH_ERROR', error: String(error?.stack || error), startedAt, finishedAt: nowIso() };
  }
}

async function fetchJson(url, timeoutMs = 45_000) {
  const response = await fetchWithTimeout(url, { timeoutMs, headers: { accept: 'application/json' } });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  const json = await response.json();
  if (json?.success !== true) throw new Error(`CKAN success=false for ${url}`);
  return json.result;
}

async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  async function worker() {
    while (true) {
      const index = next++;
      if (index >= items.length) return;
      out[index] = await fn(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return out;
}

function wardMatches(text) {
  const source = String(text || '');
  return yokohamaWards.filter((ward) => source.includes(ward));
}

const nativeGeometryFormats = new Set(['GEOJSON','KML','KMZ','SHP','GPKG','GML','GEOPACKAGE']);
function normalizeFormat(format, url = '') {
  const f = String(format || '').trim().toUpperCase();
  if (f) return f;
  const clean = String(url).split('?')[0].toLowerCase();
  if (clean.endsWith('.geojson')) return 'GEOJSON';
  if (clean.endsWith('.csv')) return 'CSV';
  if (clean.endsWith('.tsv')) return 'TSV';
  if (clean.endsWith('.json')) return 'JSON';
  if (clean.endsWith('.kml')) return 'KML';
  if (clean.endsWith('.kmz')) return 'KMZ';
  if (clean.endsWith('.zip')) return 'ZIP';
  return 'UNKNOWN';
}

function parseHeaderLine(text) {
  const first = String(text || '').replace(/^\uFEFF/, '').split(/\r?\n/, 1)[0] || '';
  // Header profiling only. We do not claim full CSV parsing here.
  return first.split(/,|\t/).map((x) => x.trim().replace(/^"|"$/g, '')).filter(Boolean);
}

function headerLocationProfile(headers) {
  const joined = headers.join('|').toLowerCase();
  const hasLat = /(緯度|latitude|(^|\W)lat($|\W))/.test(joined);
  const hasLon = /(経度|longitude|(^|\W)(lon|lng)($|\W))/.test(joined);
  const hasAddress = /(住所|所在地|所在|address|location|町丁目|町丁|地番)/.test(joined);
  const hasXY = /(^|\W)(x|ｘ)($|\W)/.test(joined) && /(^|\W)(y|ｙ)($|\W)/.test(joined);
  return { hasLat, hasLon, hasAddress, hasXY, locatable: (hasLat && hasLon) || hasAddress || hasXY };
}

async function fetchTextPrefix(url, maxBytes = 65_536) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(url, {
      redirect: 'follow',
      signal: controller.signal,
      headers: { 'user-agent': USER_AGENT, accept: 'text/csv,text/plain,*/*', range: `bytes=0-${maxBytes - 1}` },
    });
    if (!response.ok) return { status: `HTTP_${response.status}`, text: '', contentType: response.headers.get('content-type') };
    const reader = response.body?.getReader();
    if (!reader) return { status: 'NO_BODY', text: '', contentType: response.headers.get('content-type') };
    const chunks = [];
    let size = 0;
    while (size < maxBytes) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) {
        const remaining = maxBytes - size;
        const take = value.byteLength > remaining ? value.slice(0, remaining) : value;
        chunks.push(Buffer.from(take));
        size += take.byteLength;
        if (size >= maxBytes) break;
      }
    }
    try { await reader.cancel(); } catch {}
    const buf = Buffer.concat(chunks);
    let text = new TextDecoder('utf-8', { fatal: false }).decode(buf);
    const replacementRatio = (text.match(/�/g)?.length || 0) / Math.max(1, text.length);
    if (replacementRatio > 0.01) {
      try { text = new TextDecoder('shift_jis', { fatal: false }).decode(buf); } catch {}
    }
    return { status: 'OK', text, bytesRead: buf.length, contentType: response.headers.get('content-type'), finalUrl: response.url };
  } catch (error) {
    return { status: 'FETCH_ERROR', text: '', error: String(error) };
  } finally {
    clearTimeout(timer);
  }
}

async function runYokohamaDiscovery() {
  const api = 'https://data.city.yokohama.lg.jp/api/3/action';
  const queryRuns = [];
  const packages = new Map();

  for (const q of yokohamaQueries) {
    const url = `${api}/package_search?rows=1000&q=${encodeURIComponent(q)}`;
    try {
      const result = await fetchJson(url);
      const ids = [];
      for (const pkg of result.results || []) {
        ids.push(pkg.id);
        const existing = packages.get(pkg.id) || { pkg, matchedQueries: new Set() };
        existing.pkg = pkg;
        existing.matchedQueries.add(q);
        packages.set(pkg.id, existing);
      }
      queryRuns.push({ query: q, status: 'OK', count: result.count ?? ids.length, returned: ids.length, packageIds: ids });
    } catch (error) {
      queryRuns.push({ query: q, status: 'ERROR', error: String(error) });
    }
  }

  const packageRows = [...packages.values()].map(({ pkg, matchedQueries }) => ({
    packageId: pkg.id,
    packageName: pkg.name,
    title: pkg.title,
    notes: pkg.notes || '',
    organization: pkg.organization?.title || pkg.organization?.name || null,
    licenseId: pkg.license_id || null,
    licenseTitle: pkg.license_title || null,
    metadataModified: pkg.metadata_modified || null,
    matchedQueries: [...matchedQueries].sort(),
    wardMatches: wardMatches(`${pkg.title || ''}\n${pkg.notes || ''}`),
    resourceIds: (pkg.resources || []).map((r) => r.id),
  }));

  const resourceSeeds = [];
  for (const { pkg, matchedQueries } of packages.values()) {
    for (const r of pkg.resources || []) {
      resourceSeeds.push({ pkg, matchedQueries: [...matchedQueries], seed: r });
    }
  }
  const uniqueSeeds = [...new Map(resourceSeeds.map((x) => [x.seed.id, x])).values()];

  const resourceRows = await mapLimit(uniqueSeeds, 6, async ({ pkg, matchedQueries, seed }) => {
    let resource = seed;
    let resourceShowStatus = 'SEED_ONLY';
    try {
      resource = await fetchJson(`${api}/resource_show?id=${encodeURIComponent(seed.id)}`);
      resourceShowStatus = 'OK';
    } catch (error) {
      resourceShowStatus = `ERROR:${String(error)}`;
    }
    const format = normalizeFormat(resource.format || seed.format, resource.url || seed.url);
    let locationUsability = nativeGeometryFormats.has(format) ? 'NATIVE_GEOMETRY_CANDIDATE' : 'NOT_PROFILED';
    let sampleStatus = 'NOT_ATTEMPTED';
    let headers = [];
    let headerProfile = { hasLat: false, hasLon: false, hasAddress: false, hasXY: false, locatable: false };
    if (format === 'CSV' || format === 'TSV') {
      const sample = await fetchTextPrefix(resource.url || seed.url);
      sampleStatus = sample.status;
      if (sample.status === 'OK') {
        headers = parseHeaderLine(sample.text);
        headerProfile = headerLocationProfile(headers);
        locationUsability = headerProfile.locatable ? 'LOCATABLE_TABLE_HEADER' : 'TABLE_HEADER_NO_LOCATION_FIELD';
      } else {
        locationUsability = 'TABLE_SAMPLE_PENDING';
      }
    } else if (format === 'ZIP') {
      const nameText = `${resource.name || ''} ${resource.description || ''} ${resource.url || ''}`;
      locationUsability = /(shape|shp|geojson|kml|gis|地理|位置|座標|マップ|map)/i.test(nameText)
        ? 'ARCHIVE_GEOMETRY_CANDIDATE'
        : 'ARCHIVE_CONTENT_UNKNOWN';
    }

    const packageLicense = pkg.license_id || null;
    const licenseEligible = packageLicense === 'cc-by' || /creative commons attribution|クリエイティブ・コモンズ.*表示/i.test(pkg.license_title || '');
    const locatable = ['NATIVE_GEOMETRY_CANDIDATE','LOCATABLE_TABLE_HEADER','ARCHIVE_GEOMETRY_CANDIDATE'].includes(locationUsability);
    return {
      packageId: pkg.id,
      packageName: pkg.name,
      packageTitle: pkg.title,
      organization: pkg.organization?.title || pkg.organization?.name || null,
      packageLicenseId: packageLicense,
      packageLicenseTitle: pkg.license_title || null,
      packageMetadataModified: pkg.metadata_modified || null,
      matchedQueries: [...new Set(matchedQueries)].sort(),
      wardMatches: wardMatches(`${pkg.title || ''}\n${pkg.notes || ''}\n${resource.name || ''}\n${resource.description || ''}`),
      resourceId: resource.id || seed.id,
      resourceName: resource.name || seed.name || null,
      format,
      url: resource.url || seed.url || null,
      mimetype: resource.mimetype || null,
      datastoreActive: Boolean(resource.datastore_active),
      resourceLastModified: resource.last_modified || resource.created || null,
      resourceShowStatus,
      sampleStatus,
      headerFields: headers,
      ...headerProfile,
      locationUsability,
      licenseEligible,
      locatable,
      publicShadowCandidate: licenseEligible && locatable,
    };
  });

  const publicCandidates = resourceRows.filter((r) => r.publicShadowCandidate);
  const wardCoverage = yokohamaWards.map((ward) => {
    const rows = resourceRows.filter((r) => r.wardMatches.includes(ward));
    return {
      ward,
      matchedResources: rows.length,
      publicShadowCandidates: rows.filter((r) => r.publicShadowCandidate).length,
      locatableResources: rows.filter((r) => r.locatable).length,
    };
  });

  const result = {
    generatedAt: nowIso(),
    api,
    queries: yokohamaQueries,
    queryRuns,
    packageCount: packageRows.length,
    resourceCount: resourceRows.length,
    publicShadowCandidateCount: publicCandidates.length,
    packages: packageRows,
    resources: resourceRows,
    publicCandidates,
    wardCoverage,
  };
  await writeFile(path.join(REPORTS, 'yokohama-ckan-discovery.json'), JSON.stringify(result, null, 2));

  const cols = [
    'packageId','packageTitle','organization','packageLicenseId','resourceId','resourceName','format','locationUsability',
    'licenseEligible','locatable','publicShadowCandidate','wardMatches','matchedQueries','sampleStatus','headerFields','url',
  ];
  const escape = (v) => `"${String(v ?? '').replaceAll('"','""')}"`;
  const lines = [cols.join(',')];
  for (const row of resourceRows) {
    lines.push(cols.map((c) => escape(Array.isArray(row[c]) ? row[c].join('|') : row[c])).join(','));
  }
  await writeFile(path.join(REPORTS, 'yokohama-ckan-resources.csv'), lines.join('\n'));
  return {
    queryCount: yokohamaQueries.length,
    queryErrors: queryRuns.filter((x) => x.status !== 'OK').length,
    packageCount: packageRows.length,
    resourceCount: resourceRows.length,
    publicShadowCandidateCount: publicCandidates.length,
    wardCoverage,
  };
}

await mkdir(RAW, { recursive: true });
await mkdir(REPORTS, { recursive: true });

console.log(`PROJECT VEIL network runner start ${nowIso()}`);
const downloads = [];
for (const target of downloadTargets) {
  console.log(`download ${target.resourceKey} ${target.url}`);
  const result = await downloadOne(target);
  downloads.push(result);
  console.log(JSON.stringify({ resourceKey: result.resourceKey, status: result.status, bytes: result.bytes, sha256: result.sha256, httpStatus: result.httpStatus }));
}
await writeFile(path.join(REPORTS, 'download-manifest.json'), JSON.stringify({ generatedAt: nowIso(), downloads }, null, 2));

console.log(`Yokohama CKAN discovery ${yokohamaQueries.length} pre-registered queries`);
const yokohama = await runYokohamaDiscovery();
console.log(JSON.stringify({ yokohama }, null, 2));

const summary = {
  generatedAt: nowIso(),
  acquired: downloads.filter((x) => x.status === 'ACQUIRED').length,
  failed: downloads.filter((x) => x.status !== 'ACQUIRED').length,
  downloads: downloads.map(({ resourceKey, status, bytes, sha256, httpStatus, contentType, finalUrl }) => ({ resourceKey, status, bytes, sha256, httpStatus, contentType, finalUrl })),
  yokohama,
};
await writeFile(path.join(REPORTS, 'run-summary.json'), JSON.stringify(summary, null, 2));
console.log('VEIL_NETWORK_RUN_SUMMARY=' + JSON.stringify(summary));
