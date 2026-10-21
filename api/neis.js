// 나이스(NEIS) 교육정보 개방포털 중계 — 학교 찾기 · 학사일정
// 키는 Vercel 환경변수 NEIS_API_KEY (없으면 키 없이 호출: 샘플 5건 한도)
// GET /api/neis?op=school&name=신송고
// GET /api/neis?op=schedule&atpt=E10&code=7310250&from=20260901&to=20261231
export const config = { maxDuration: 20 };

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (req.method !== 'GET') { res.status(405).json({ error: 'Method Not Allowed' }); return; }
  const q = req.query || {};
  const key = process.env.NEIS_API_KEY || '';
  const base = 'https://open.neis.go.kr/hub/';
  let url;
  if (q.op === 'school') {
    const name = String(q.name || '').trim();
    if (!name) { res.status(400).json({ error: 'name 필요' }); return; }
    url = base + 'schoolInfo?' + new URLSearchParams({ Type: 'json', pIndex: '1', pSize: '20', SCHUL_NM: name, ...(key ? { KEY: key } : {}) });
  } else if (q.op === 'schedule') {
    const atpt = String(q.atpt || ''), code = String(q.code || ''), from = String(q.from || ''), to = String(q.to || '');
    if (!/^[A-Z]\d{2}$/.test(atpt) || !/^\d{7}$/.test(code) || !/^\d{8}$/.test(from) || !/^\d{8}$/.test(to)) { res.status(400).json({ error: '학교 코드/기간 형식 오류' }); return; }
    url = base + 'SchoolSchedule?' + new URLSearchParams({ Type: 'json', pIndex: '1', pSize: '1000', ATPT_OFCDC_SC_CODE: atpt, SD_SCHUL_CODE: code, AA_FROM_YMD: from, AA_TO_YMD: to, ...(key ? { KEY: key } : {}) });
  } else { res.status(400).json({ error: 'op 는 school 또는 schedule' }); return; }
  try {
    const r = await fetch(url, { headers: { 'User-Agent': 'BMAPS/1.0' } });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch (e) { res.status(502).json({ error: 'NEIS 응답을 읽지 못했습니다', raw: text.slice(0, 200) }); return; }
    res.status(200).json({ ok: true, hasKey: !!key, data });
  } catch (e) {
    res.status(502).json({ error: 'NEIS 연결 실패: ' + (e.message || e) });
  }
}
// 2026-10-16 NEIS_API_KEY 적용을 위한 재배포
