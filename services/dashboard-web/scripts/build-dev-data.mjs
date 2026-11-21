// 개발용 화면 데이터 만들기(로컬 전용).
// 옛 중간 프론트(tms-frontend-midterm/public)의 보관 데이터를 새 화면이 읽는 모양으로 바꿔 dev-data/에 쓴다.
// dev-data/에는 실제 사업장명·좌표가 들어 있으므로 저장소에 올리지 않는다(.gitignore) · 운영 빌드에도 넣지 않는다.
// 실행: node scripts/build-dev-data.mjs <옛 public 폴더 경로>
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const src = process.argv[2];
if (!src) {
  console.error("사용법: node scripts/build-dev-data.mjs <tms-frontend-midterm/public 경로>");
  process.exit(1);
}
const out = path.resolve(import.meta.dirname, "..", "dev-data");
fs.mkdirSync(out, { recursive: true });

const readAssign = (file, name) => {
  const ctx = { window: {} };
  ctx.globalThis = ctx.window;
  vm.runInNewContext(fs.readFileSync(file, "utf8"), ctx);
  return ctx.window[name] ?? ctx[name];
};

const local = readAssign(path.join(src, "data/day/latest.js"), "TMS_LOCAL");
const timeline = JSON.parse(fs.readFileSync(path.join(src, "data/day/map-timeline-20261110.json"), "utf8"));
const geography = readAssign(path.join(src, "assets/geography-regional.js"), "TMS_GEOGRAPHY");

const SHORT = {
  서울특별시: "서울", 인천광역시: "인천", 경기도: "경기", 강원도: "강원", 충청북도: "충북", 충청남도: "충남",
  대전광역시: "대전", 세종특별자치시: "세종", 전라북도: "전북", 전라남도: "전남", 광주광역시: "광주",
  경상북도: "경북", 경상남도: "경남", 대구광역시: "대구", 부산광역시: "부산", 울산광역시: "울산",
  제주특별자치도: "제주",
};

function sigunguOf(address) {
  const tokens = String(address ?? "").split(/\s+/);
  const t = tokens[1];
  return t && /[시군구]$/.test(t) ? t : "기타";
}

// 사업장: historical_facility_id → 사업장
const siteByFacility = new Map();
const sites = local.sites.map((s) => {
  const site = {
    id: s.site_id,
    name: s.source_name,
    sido: SHORT[s.boundary_region] ?? s.boundary_region ?? "기타",
    sigungu: sigunguOf(s.address),
    address: s.address ?? "",
    lon: s.longitude,
    lat: s.latitude,
    stacks: [],
  };
  siteByFacility.set(s.historical_facility_id, site);
  return site;
});

// 굴뚝 → 키 "{site_id}:{굴뚝번호}"
const stackInfo = new Map(local.stacks.map((st) => [st.stack_id, st]));
const keyOfIndex = [];
const used = new Set();
for (const stackId of timeline.stackIds) {
  const st = stackInfo.get(stackId);
  const site = st && siteByFacility.get(st.facility_id);
  if (!site) { keyOfIndex.push(null); continue; }
  let key = `${site.id}:${st.stack_code}`;
  for (let n = 2; used.has(key); n++) key = `${site.id}:${st.stack_code}-${n}`;
  used.add(key);
  site.stacks.push({ key, code: key.split(":")[1] });
  keyOfIndex.push(key);
}

// 30분 48시점. 값은 보관된 원문 그대로(숫자 문자열 또는 상태 문구)
const times = timeline.frames.map((f) => f.time);
const stacks = {};
timeline.frames.forEach((frame, slot) => {
  for (const [idx, noxRaw, noxLimit, soxRaw, soxLimit] of frame.rows) {
    const key = keyOfIndex[idx];
    if (!key) continue;
    const e = (stacks[key] ??= {
      nox: new Array(48).fill(null), sox: new Array(48).fill(null), noxLimit: null, soxLimit: null,
    });
    e.nox[slot] = noxRaw ?? null;
    e.sox[slot] = soxRaw ?? null;
    if (noxLimit != null) e.noxLimit = noxLimit;
    if (soxLimit != null) e.soxLimit = soxLimit;
  }
});

const keptSites = sites.filter((s) => s.stacks.length > 0);

// 시도 경계(점 수가 적어 그대로 쓰되 소수 4자리로 줄임). 다단계 단순화는 지도 구현 단계에서 한다
const round = (a) => (typeof a === "number" ? Math.round(a * 1e4) / 1e4 : a.map(round));
// 시도 경계는 옛 지도와 같은 웹 메르카토르 좌표로 쓴다(등고선과 겹쳐야 한다). 경위도 그대로 두고 화면에서 투영한다
const geo = geography.levels.overview.regions.map((r) => ({
  name: SHORT[r.name] ?? r.name,
  type: r.geometry.type,
  coordinates: round(r.geometry.coordinates),
}));

const write = (name, data) => {
  const file = path.join(out, name);
  fs.writeFileSync(file, JSON.stringify(data));
  console.log(name, (fs.statSync(file).size / 1024).toFixed(0) + " KB");
};
// 등고선(Mapzen/USGS/NOAA 지형 타일에서 만든 옛 자료). 웹 메르카토르 세계 좌표(폭 256)로 이미 되어 있어 그대로 쓴다.
// 전국 개요 800m 간격 1개 + 시도별 200m 간격 17개. 점은 평평한 배열 [x0,y0,x1,y1…]로 줄이고 소수 5자리(약 1m)로 맞춘다.
const contourDir = path.join(out, "contours");
fs.mkdirSync(contourDir, { recursive: true });
const manifest = readAssign(path.join(src, "assets/contours/manifest.js"), "TMS_CONTOUR_MANIFEST");
const r5 = (n) => Math.round(n * 1e5) / 1e5;
function convertChunk(entry) {
  const ctx = { window: { TMS_CONTOUR_CHUNKS: {} } };
  vm.runInNewContext(fs.readFileSync(path.join(src, entry.file), "utf8"), ctx);
  const rows = ctx.window.TMS_CONTOUR_CHUNKS[entry.key];
  const seen = new Set();
  const lines = [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const row of rows) {
    const id = row.elevation_m + ":" + JSON.stringify(row.points); // 인접 지역 파일에 겹쳐 있는 같은 선은 한 번만
    if (seen.has(id)) continue;
    seen.add(id);
    const [bx0, by0, bx1, by1] = row.bbox;
    minX = Math.min(minX, bx0); minY = Math.min(minY, by0); maxX = Math.max(maxX, bx1); maxY = Math.max(maxY, by1);
    lines.push({ e: row.elevation_m, b: [r5(bx0), r5(by0), r5(bx1), r5(by1)], p: row.points.flatMap(([x, y]) => [r5(x), r5(y)]) });
  }
  return { lines, bbox: [r5(minX), r5(minY), r5(maxX), r5(maxY)] };
}
const contourIndex = { overview: null, regions: {}, intervalM: { overview: manifest.overview_interval_m, region: manifest.region_interval_m } };
{
  const o = convertChunk(manifest.overview);
  fs.writeFileSync(path.join(contourDir, "overview.json"), JSON.stringify(o.lines));
  contourIndex.overview = { file: "contours/overview.json", bbox: o.bbox };
}
for (const [fullName, entry] of Object.entries(manifest.regions)) {
  const short = SHORT[fullName] ?? fullName;
  const c = convertChunk(entry);
  fs.writeFileSync(path.join(contourDir, `${entry.key}.json`), JSON.stringify(c.lines));
  contourIndex.regions[short] = { file: `contours/${entry.key}.json`, bbox: c.bbox };
}
write("contours/index.json", contourIndex);

write("sites.json", keptSites);
write("day.json", { times, stacks });
write("geo.json", geo);
console.log(`사업장 ${keptSites.length}곳, 굴뚝 ${Object.keys(stacks).length}개, 시점 ${times.length}`);
