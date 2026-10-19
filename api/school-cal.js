// 학교 홈페이지 학사일정 중계 — 나이스에 없는 일정을 학교 홈페이지에서 보충한다
// 플랫폼 3종: 경기(○○.goegm.kr 등 경기도교육청 통합 홈페이지) · 서울(○○.sen.hs.kr / sen.ms.kr) · 인천(○○.icehs.kr / icems.kr)
// GET /api/school-cal?hp=https://soha-h.goegm.kr&from=2026-10-01&to=2026-12-31
//  → { ok, platform, platformLabel, page, events:[{ id, title, start, end }], note }
export const config = { maxDuration: 60 };
// 서울 홈페이지는 페이지마다 1.6MB·응답이 느려(Vercel 에서 건당 5~7초) 메뉴 탐색 결과를 인스턴스 안에 캐시하고 달별 조회는 병렬로 한다
const _menuCache = {};

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const PLATFORMS = [
  { key: 'gyeonggi', label: '경기도교육청 학교 홈페이지', test: h => /\.goe[a-z]*\.kr$|\.goe\.go\.kr$/.test(h) },
  { key: 'seoul', label: '서울특별시교육청 학교 홈페이지', test: h => /\.sen\.(hs|ms|es|sc|go)\.kr$/.test(h) },
  { key: 'incheon', label: '인천광역시교육청 학교 홈페이지', test: h => /\.ice(hs|ms|es|sc)\.kr$|\.ice\.go\.kr$/.test(h) },
];

function decodeEntities(s) {
  return String(s || '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#0*39;|&apos;/g, "'").replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
}
function pad2(n) { return String(n).padStart(2, '0'); }
function ymdFromSlash(s) { const m = String(s).match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})/); return m ? m[1] + '-' + pad2(m[2]) + '-' + pad2(m[3]) : null; }
function overlaps(a, b, from, to) { return a <= to && b >= from; }
function monthsBetween(from, to) {
  const out = []; let y = +from.slice(0, 4), m = +from.slice(5, 7); const ey = +to.slice(0, 4), em = +to.slice(5, 7);
  while (y < ey || (y === ey && m <= em)) { out.push([y, m]); m++; if (m > 12) { m = 1; y++; } if (out.length > 14) break; }
  return out;
}

async function fetchText(url, opt) {
  opt = opt || {};
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), opt.timeout || 25000);
  try {
    const headers = Object.assign({ 'User-Agent': UA, 'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8', 'Accept-Language': 'ko-KR,ko;q=0.9' }, opt.headers || {});
    const r = await fetch(url, { method: opt.method || 'GET', headers, body: opt.body, redirect: 'follow', signal: ctl.signal });
    const text = await r.text();
    if (!r.ok) throw new Error('HTTP ' + r.status + ' (' + url.replace(/^https?:\/\//, '').slice(0, 60) + ')');
    return { text, url: r.url || url };
  } finally { clearTimeout(t); }
}
function postForm(url, data, ajax) {
  const headers = { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' }; if (ajax) headers['X-Requested-With'] = 'XMLHttpRequest';
  return fetchText(url, { method: 'POST', body: new URLSearchParams(data).toString(), headers });
}
function normalizeHp(hp) {
  let s = String(hp || '').trim(); if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = 'https://' + s;
  s = s.replace(/^http:/i, 'https:');
  try { return new URL(s); } catch (e) { return null; }
}

/* ── 경기: /{sysId}/main.do 에서 sysId·메뉴번호(mi) → /{sysId}/ps/schdul/selectSchdulList.do 연간(Y) 조회 ── */
async function gyeonggi(u, from, to) {
  const origin = u.protocol + '//' + u.host;
  let sysId = (u.pathname.match(/^\/([\w-]+)\/main\.do/) || [])[1] || null;
  let main;
  if (sysId) main = await fetchText(origin + '/' + sysId + '/main.do');
  else {
    const root = await fetchText(origin + '/');
    const m = root.text.match(/location\.href\s*=\s*["']([^"']+main\.do)["']/);
    const mainUrl = m ? (m[1].startsWith('http') ? m[1] : origin + m[1]) : root.url;
    main = /main\.do/.test(mainUrl) && mainUrl !== root.url ? await fetchText(mainUrl) : root;
    sysId = (new URL(main.url).pathname.match(/^\/([\w-]+)\/main\.do/) || [])[1] || (mainUrl.match(/\/([\w-]+)\/main\.do/) || [])[1];
  }
  if (!sysId) throw new Error('경기 홈페이지에서 학교 식별자(sysId)를 찾지 못했습니다');
  const mi = (main.text.match(/selectSchdulMainList\.do\?mi=(\d+)/) || main.text.match(/var\s+mi\s*=\s*["'](\d+)["']/) || [])[1];
  if (!mi) throw new Error('경기 홈페이지에서 학사일정 메뉴를 찾지 못했습니다');
  const years = []; for (let y = +from.slice(0, 4); y <= +to.slice(0, 4); y++) years.push(y);
  const seen = {}, events = [];
  const yearPages = await Promise.all(years.map(y => postForm(origin + '/' + sysId + '/ps/schdul/selectSchdulList.do?mi=' + mi, { schdulSeq: '', schdulLevel: 'Y', fromDate: '', toDate: '', date: '', weekNum: '', chkNP: '', srchDate: String(y), schType: '', schColor: '', menuId: mi }, true).then(r => r.text)));
  for (const page of yearPages) {
    let html = page; try { const j = JSON.parse(html); if (typeof j === 'string') html = j; } catch (e) { /* 그대로 HTML */ }
    const re = /viewSchdulInfo\('(\w+)',\s*'([\d/]+)',\s*'([\d/]+)',\s*'[^']*'\);"[^>]*>([^<]*)/g; let m;
    while ((m = re.exec(html))) {
      if (seen[m[1]]) continue; seen[m[1]] = 1;
      const s = ymdFromSlash(m[2]), e = ymdFromSlash(m[3]) || s; if (!s) continue;
      events.push({ id: m[1], title: decodeEntities(m[4]), start: s, end: e < s ? s : e });
    }
  }
  return { page: origin + '/' + sysId + '/ps/schdul/selectSchdulMainList.do?mi=' + mi, events };
}

/* ── 서울: 메인에서 '학교일정' 메뉴(/NNNNN/subMenu.do) → siteId → 달마다 캘린더형 POST, 같은 일정번호(fnDetail)를 날짜로 이어 붙임 ── */
async function seoul(u, from, to) {
  const origin = u.protocol + '//' + u.host;
  let page = null, siteId = null;
  const cached = _menuCache[origin];
  if (cached && Date.now() - cached.t < 6 * 3600 * 1000) { page = cached.page; siteId = cached.siteId; }
  else {
    const root = await fetchText(origin + '/');
    const cands = [];
    const re = /<a[^>]+href=["'](\/\d+\/subMenu\.do)["'][^>]*>\s*(?:<[^>]+>\s*)*([^<]*일정[^<]*)/g; let m;
    while ((m = re.exec(root.text))) { const t = decodeEntities(m[2]); if (/급식|식단/.test(t)) continue; if (cands.some(c => c.path === m[1])) continue; cands.push({ path: m[1], text: t, rank: /^학교\s*일정$/.test(t) ? 0 : /학사\s*일정/.test(t) ? 1 : 2 }); }
    cands.sort((a, b) => a.rank - b.rank);
    const probed = await Promise.all(cands.slice(0, 4).map(async c => {
      try { const p = await fetchText(origin + c.path); const sid = (p.text.match(/name="siteId"\s+value="([^"]+)"/) || [])[1]; return (sid && /srhSchdulYear/.test(p.text)) ? { path: c.path, sid } : null; } catch (e) { return null; }
    }));
    const hit = probed.find(Boolean);
    if (!hit) throw new Error(cands.length ? '이 학교의 일정 메뉴는 표준 일정 모듈이 아니어서 읽을 수 없습니다(붙여넣기 등록을 이용하세요)' : '서울 홈페이지에서 학교일정 메뉴를 찾지 못했습니다');
    page = origin + hit.path; siteId = hit.sid; _menuCache[origin] = { page, siteId, t: Date.now() };
  }
  const byId = {};
  const pages = await Promise.all(monthsBetween(from, to).map(([y, mo]) => postForm(page, { siteId, viewType: 'calendar', arrSchdulId: '0', srhSchdulYear: String(y), srhSchdulMonth: pad2(mo) }).then(r => [y, mo, r.text])));
  for (const [y, mo, text] of pages) {
    const i = text.indexOf('캘린더형 목록'); if (i < 0) continue;
    let seg = text.slice(i); seg = seg.slice(0, seg.indexOf('</table>'));
    const tdRe = /<td[^>]*>([\s\S]*?)<\/td>/gi; let td;
    while ((td = tdRe.exec(seg))) {
      const day = (td[1].match(/^\s*(\d{1,2})\b/) || [])[1]; if (!day) continue;
      const date = y + '-' + pad2(mo) + '-' + pad2(day);
      const evRe = /fnDetail\('(\d+)'[^>]*>\s*([^<]+)/g; let ev;
      while ((ev = evRe.exec(td[1]))) {
        const id = ev[1], title = decodeEntities(ev[2]);
        if (!byId[id]) byId[id] = { id, title, start: date, end: date };
        else { if (date < byId[id].start) byId[id].start = date; if (date > byId[id].end) byId[id].end = date; }
      }
    }
  }
  return { page, events: Object.values(byId) };
}

/* ── 인천: /main.do 에서 /schdList.do?m=..&s=.. → 연도·학기(section 1/2)별 POST, <li id='dateYYYY/MM_sSEQ'>DD일~DD일 : 제목</li> ── */
async function incheon(u, from, to) {
  const origin = u.protocol + '//' + u.host;
  const main = await fetchText(origin + '/main.do');
  const m = main.text.match(/href=["']([^"']*\/schdList\.do\?[^"']*)["']/);
  if (!m) throw new Error('인천 홈페이지에서 학사일정 메뉴를 찾지 못했습니다');
  const href = decodeEntities(m[1]); const page = href.startsWith('http') ? href.replace(/^http:/, 'https:') : origin + href;
  const pu = new URL(page); const menu = pu.searchParams.get('m') || '', slug = pu.searchParams.get('s') || '';
  const base = origin + '/schdList.do?m=' + encodeURIComponent(menu) + '&s=' + encodeURIComponent(slug);
  const fy = +from.slice(0, 4), ty = +to.slice(0, 4), sems = [];
  for (let y = fy - 1; y <= ty; y++) {
    if (overlaps(y + '-03-01', y + '-08-31', from, to)) sems.push([y, 1]);
    if (overlaps(y + '-08-01', (y + 1) + '-02-29', from, to)) sems.push([y, 2]);
  }
  const seen = {}, events = [];
  const semPages = await Promise.all(sems.map(([y, sec]) => postForm(base, { section: String(sec), year: String(y), workType: 'H' }).then(r => r.text)));
  for (const text of semPages) {
    const re = /<li id=['"]date(\d{4})\/(\d{2})_s(\d+)['"]>([^<]*)<\/li>/g; let li;
    while ((li = re.exec(text))) {
      const yy = +li[1], mm = +li[2], id = li[3], text = decodeEntities(li[4]);
      if (seen[id]) continue; seen[id] = 1;
      const t = text.match(/^(\d{1,2})\s*일(?:\s*[~∼-]\s*(?:(\d{1,2})\s*월)?\s*(\d{1,2})\s*일)?\s*:\s*(.*)$/);
      if (!t) { events.push({ id, title: text, start: yy + '-' + pad2(mm) + '-01', end: yy + '-' + pad2(mm) + '-01', vague: true }); continue; }
      const d1 = +t[1], em = t[2] ? +t[2] : mm, d2 = t[3] ? +t[3] : d1;
      let ey = yy, eM = em; if (!t[2] && d2 < d1) { eM = mm + 1; } if (eM > 12) { eM = 1; ey = yy + 1; } if (t[2] && em < mm) ey = yy + 1;
      const start = yy + '-' + pad2(mm) + '-' + pad2(d1); let end = ey + '-' + pad2(eM) + '-' + pad2(d2); if (end < start) end = start;
      events.push({ id, title: t[4].trim(), start, end });
    }
  }
  return { page: base, events };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (req.method !== 'GET') { res.status(405).json({ error: 'Method Not Allowed' }); return; }
  const q = req.query || {};
  const u = normalizeHp(q.hp);
  const from = String(q.from || ''), to = String(q.to || '');
  if (!u) { res.status(400).json({ ok: false, error: '홈페이지 주소가 없습니다' }); return; }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to) || from > to) { res.status(400).json({ ok: false, error: '기간 형식 오류' }); return; }
  const host = u.hostname.toLowerCase();
  const pf = PLATFORMS.find(p => p.test(host));
  if (!pf) { res.status(200).json({ ok: false, platform: null, error: '지원하지 않는 홈페이지 플랫폼(' + host + ') — 경기·서울·인천 교육청 통합 홈페이지만 읽습니다' }); return; }
  const t0 = Date.now();
  try {
    const r = await (pf.key === 'gyeonggi' ? gyeonggi(u, from, to) : pf.key === 'seoul' ? seoul(u, from, to) : incheon(u, from, to));
    const events = r.events.filter(e => overlaps(e.start, e.end, from, to)).sort((a, b) => a.start.localeCompare(b.start) || a.title.localeCompare(b.title));
    res.status(200).json({ ok: true, platform: pf.key, platformLabel: pf.label, page: r.page, total: r.events.length, events, ms: Date.now() - t0 });
  } catch (e) {
    res.status(200).json({ ok: false, platform: pf.key, platformLabel: pf.label, error: (e && e.name === 'AbortError') ? '학교 홈페이지 응답이 없습니다(시간 초과)' : String(e && e.message || e) });
  }
}
