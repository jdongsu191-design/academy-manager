/* 베티 OMR 사진 인식 엔진 (의존성 없음, 브라우저 canvas 만 사용)
   흐름: 사진 → 회색조 축소 → 기준 마크(검정-흰-검정 정사각형) 4개 찾기 → 방향 판정(오른쪽 위만 중심점 없음)
        → 호모그래피(mm→px) → 칸마다 채움률 측정(종이 흰색·마크 검정으로 정규화) → 문항별 판정
   양식 정의는 assets/omr-forms.json (칸 중심 mm 좌표). 결과는 window.OmrEngine.analyze(img, form, opts) */
(function(){
  'use strict';

  /* ── 기본 영상 처리 ─────────────────────────────────────── */
  function toGray(src, maxSide){
    var w = src.naturalWidth || src.videoWidth || src.width, h = src.naturalHeight || src.videoHeight || src.height;
    var k = Math.min(1, maxSide / Math.max(w, h)), W = Math.round(w * k), Hh = Math.round(h * k);
    var c = document.createElement('canvas'); c.width = W; c.height = Hh;
    var ctx = c.getContext('2d', { willReadFrequently: true }); ctx.drawImage(src, 0, 0, W, Hh);
    var d = ctx.getImageData(0, 0, W, Hh).data, g = new Uint8ClampedArray(W * Hh);
    for(var i = 0, j = 0; i < d.length; i += 4, j++) g[j] = (d[i] * 299 + d[i+1] * 587 + d[i+2] * 114) / 1000;
    return { g: g, w: W, h: Hh, scale: k, canvas: c };
  }
  function integral(g, w, h){
    var S = new Float64Array((w + 1) * (h + 1));
    for(var y = 1; y <= h; y++){ var row = 0; for(var x = 1; x <= w; x++){ row += g[(y-1)*w + (x-1)]; S[y*(w+1) + x] = S[(y-1)*(w+1) + x] + row; } }
    return S;
  }
  function boxMean(S, w, x0, y0, x1, y1){   /* [x0,x1) × [y0,y1) 평균 */
    var W = w + 1; return (S[y1*W + x1] - S[y0*W + x1] - S[y1*W + x0] + S[y0*W + x0]) / ((x1 - x0) * (y1 - y0));
  }
  /* 국소 적응 이진화: 주변 평균보다 t 만큼 어두우면 1 */
  function adaptiveBinary(g, w, h, block, t){
    var S = integral(g, w, h), b = new Uint8Array(w * h), r = block >> 1;
    for(var y = 0; y < h; y++){
      var y0 = Math.max(0, y - r), y1 = Math.min(h, y + r + 1);
      for(var x = 0; x < w; x++){
        var x0 = Math.max(0, x - r), x1 = Math.min(w, x + r + 1);
        if(g[y*w + x] < boxMean(S, w, x0, y0, x1, y1) - t) b[y*w + x] = 1;
      }
    }
    return b;
  }
  /* 연결 성분(4방향) — 상자·면적·중심 */
  function components(b, w, h, minA, maxA){
    var lab = new Int32Array(w * h), out = [], stack = new Int32Array(w * h), n = 0;
    for(var i = 0; i < w * h; i++){
      if(!b[i] || lab[i]) continue;
      n++; var sp = 0; stack[sp++] = i; lab[i] = n;
      var area = 0, sx = 0, sy = 0, x0 = w, x1 = 0, y0 = h, y1 = 0;
      while(sp){
        var p = stack[--sp], px = p % w, py = (p - px) / w;
        area++; sx += px; sy += py; if(px < x0) x0 = px; if(px > x1) x1 = px; if(py < y0) y0 = py; if(py > y1) y1 = py;
        if(px > 0 && b[p-1] && !lab[p-1]){ lab[p-1] = n; stack[sp++] = p-1; }
        if(px < w-1 && b[p+1] && !lab[p+1]){ lab[p+1] = n; stack[sp++] = p+1; }
        if(py > 0 && b[p-w] && !lab[p-w]){ lab[p-w] = n; stack[sp++] = p-w; }
        if(py < h-1 && b[p+w] && !lab[p+w]){ lab[p+w] = n; stack[sp++] = p+w; }
        if(area > maxA) break;
      }
      if(area >= minA && area <= maxA) out.push({ area: area, cx: sx / area, cy: sy / area, x0: x0, y0: y0, x1: x1, y1: y1, w: x1 - x0 + 1, h: y1 - y0 + 1 });
    }
    return out;
  }

  /* ── 기준 마크 찾기 ────────────────────────────────────────
     바깥 검정 테두리(두께 25%) 안에 흰 정사각형(50%), 그 안에 검정 점(20%, 오른쪽 위만 없음) */
  function findFiducials(gray){
    var g = gray.g, w = gray.w, h = gray.h, S = integral(g, w, h);
    var est = Math.max(w, h) * (7 / 297);                     /* 마크 한 변(px) 어림 — 종이가 화면을 거의 채울 때 */
    /* 패턴 점수: 바깥 테두리(검정) 대비 안쪽 사각형(흰) — 적분영상 상자 평균만 써서 끊긴 테두리·흐림에도 강하다 */
    function box(cx, cy, half){ var x0 = Math.max(0, Math.round(cx - half)), y0 = Math.max(0, Math.round(cy - half)), x1 = Math.min(w, Math.round(cx + half)), y1 = Math.min(h, Math.round(cy + half)); if(x1 - x0 < 1 || y1 - y0 < 1) return null; return { m: boxMean(S, w, x0, y0, x1, y1), a: (x1 - x0) * (y1 - y0) }; }
    function score(cx, cy, sz){
      var O = box(cx, cy, sz * 0.5), I = box(cx, cy, sz * 0.25), D = box(cx, cy, sz * 0.09), A = box(cx, cy, sz * 0.8); if(!O || !I || !D || !A) return null;
      var outer = (O.m * O.a - I.m * I.a) / Math.max(1, O.a - I.a);        /* 테두리 띠 */
      var inner = (I.m * I.a - D.m * D.a) / Math.max(1, I.a - D.a);        /* 흰 띠 */
      var paper = (A.m * A.a - O.m * O.a) / Math.max(1, A.a - O.a);        /* 둘레 종이 */
      /* 흰 띠가 테두리보다 밝고, 테두리가 둘레 종이보다 어두울수록 높은 점수 */
      var c1 = (inner - outer) / Math.max(1, inner), c2 = (paper - outer) / Math.max(1, paper);
      return { outer: outer, inner: inner, dot: D.m, paper: paper, s: 100 * (c1 + 0.5 * c2) - 30 * Math.abs(inner - paper) / Math.max(1, paper) };
    }
    /* 귀퉁이 영역마다 자리·크기를 훑어 마크다운 후보를 여럿(국소 최대) 모은 뒤, 넷의 기하(크기·비율·볼록)가 맞는 조합을 고른다 */
    var regions = [[0, 0, w * 0.45, h * 0.45], [w * 0.55, 0, w, h * 0.45], [0, h * 0.55, w * 0.45, h], [w * 0.55, h * 0.55, w, h]];
    var scales = [0.5, 0.65, 0.8, 1.0, 1.2, 1.45, 1.75].map(function(f){ return est * f; });
    function refine(c, step){
      var b2 = c, sz0 = c.size;
      [0.85, 0.92, 1, 1.08, 1.16].forEach(function(f){ var sz = sz0 * f;
        for(var y = c.cy - step; y <= c.cy + step; y++) for(var x = c.cx - step; x <= c.cx + step; x++){ var sc = score(x, y, sz); if(sc && sc.s > b2.s){ b2 = sc; b2.cx = x; b2.cy = y; b2.size = sz; } } });
      b2.hasDot = b2.dot < (b2.inner + b2.outer) / 2;
      b2.valid = (b2.inner - b2.outer > Math.max(35, b2.inner * 0.3)) && (b2.paper - b2.outer > Math.max(25, b2.paper * 0.25));
      return b2;
    }
    var lists = regions.map(function(R){
      var step = Math.max(2, Math.round(est / 6)), grid = [];
      for(var y = R[1] + est * 0.3; y < R[3] - est * 0.3; y += step) for(var x = R[0] + est * 0.3; x < R[2] - est * 0.3; x += step){
        var best = null;
        for(var si = 0; si < scales.length; si++){ var sc = score(x, y, scales[si]); if(sc && (!best || sc.s > best.s)){ best = sc; best.cx = x; best.cy = y; best.size = scales[si]; } }
        if(best && best.s > 45) grid.push(best);
      }
      grid.sort(function(p, q){ return q.s - p.s; });
      var top = [];
      for(var i = 0; i < grid.length && top.length < 6; i++){ var c = grid[i]; if(top.some(function(t){ return Math.hypot(t.cx - c.cx, t.cy - c.cy) < Math.max(t.size, c.size) * 1.5; })) continue; top.push(refine(c, step)); }
      return top.filter(function(t){ return t.valid; });
    });
    if(lists.some(function(l){ return !l.length; })) return { ok: false, reason: 'fiducials', found: lists.filter(function(l){ return l.length; }).length, cands: lists };
    /* 조합 고르기: 크기 비슷, 볼록, 가로/세로 비율이 답안지(≈1.45)에 가깝고, 마주보는 변 길이 비슷 */
    var bestQ = null;
    function quadScore(tl, tr, bl, br){
      var sz = [tl.size, tr.size, bl.size, br.size], smin = Math.min.apply(null, sz), smax = Math.max.apply(null, sz); if(smax > smin * 1.3) return null;
      var top = Math.hypot(tr.cx - tl.cx, tr.cy - tl.cy), bot = Math.hypot(br.cx - bl.cx, br.cy - bl.cy), lef = Math.hypot(bl.cx - tl.cx, bl.cy - tl.cy), rig = Math.hypot(br.cx - tr.cx, br.cy - tr.cy);
      if(top / bot > 1.35 || bot / top > 1.35 || lef / rig > 1.35 || rig / lef > 1.35) return null;
      var aspect = (top + bot) / (lef + rig); if(aspect < 1.1 || aspect > 1.9) return null;
      /* 볼록성: 시계 방향 외적 부호 일치 */
      var pts = [tl, tr, br, bl], sgn = 0;
      for(var i = 0; i < 4; i++){ var p = pts[i], q2 = pts[(i+1)%4], r = pts[(i+2)%4]; var cr = (q2.cx - p.cx) * (r.cy - q2.cy) - (q2.cy - p.cy) * (r.cx - q2.cx); if(!sgn) sgn = cr > 0 ? 1 : -1; else if((cr > 0 ? 1 : -1) !== sgn) return null; }
      /* 마크 크기와 변 길이의 비(7mm : 282mm)도 맞아야 */
      var expTop = ((tl.size + tr.size) / 2) * (282 / 7); if(top / expTop > 1.3 || expTop / top > 1.3) return null;
      return tl.s + tr.s + bl.s + br.s - (smax / smin - 1) * 80 - Math.abs(top / expTop - 1) * 40;
    }
    lists[0].forEach(function(tl){ lists[1].forEach(function(tr){ lists[2].forEach(function(bl){ lists[3].forEach(function(br){
      var qs = quadScore(tl, tr, bl, br); if(qs != null && (!bestQ || qs > bestQ.q)) bestQ = { q: qs, p: [tl, tr, bl, br] };
    }); }); }); });
    if(!bestQ) return { ok: false, reason: 'fiducials_geom', found: 4, cands: lists };
    var pick = bestQ.p.slice();
    /* 방향: 점이 없는 마크가 '오른쪽 위'. 중심 기준 각도로 시계 방향 정렬 */
    var mx = pick.reduce(function(a, c){ return a + c.cx; }, 0) / 4, my = pick.reduce(function(a, c){ return a + c.cy; }, 0) / 4;
    pick.sort(function(a, b){ return Math.atan2(a.cy - my, a.cx - mx) - Math.atan2(b.cy - my, b.cx - mx); });
    var noDot = pick.map(function(c, i){ return { i: i, c: (c.dot - c.outer) / Math.max(1, c.inner - c.outer) }; }).sort(function(a, b){ return b.c - a.c; })[0].i;
    var TR = pick[noDot], BR = pick[(noDot + 1) % 4], BL = pick[(noDot + 2) % 4], TL = pick[(noDot + 3) % 4];
    [TL, TR, BR, BL].forEach(function(c){ c.ring = c.inner; });
    return { ok: true, TL: TL, TR: TR, BR: BR, BL: BL, cands: pick, rotated: !(TL.cx < TR.cx && TL.cy < BL.cy) };
  }

  /* ── 호모그래피 (4점 DLT) ─────────────────────────────────── */
  function solve(A, b){   /* 가우스 소거 */
    var n = b.length, M = A.map(function(r, i){ return r.concat([b[i]]); });
    for(var c = 0; c < n; c++){
      var p = c; for(var r = c + 1; r < n; r++) if(Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      var t = M[c]; M[c] = M[p]; M[p] = t;
      if(Math.abs(M[c][c]) < 1e-12) return null;
      for(var r2 = 0; r2 < n; r2++){ if(r2 === c) continue; var f = M[r2][c] / M[c][c]; for(var k = c; k <= n; k++) M[r2][k] -= f * M[c][k]; }
    }
    return M.map(function(r, i){ return r[n] / r[i]; });
  }
  function homography(src, dst){   /* src[i]=[x,y](mm) → dst[i]=[u,v](px) */
    var A = [], b = [];
    for(var i = 0; i < 4; i++){
      var x = src[i][0], y = src[i][1], u = dst[i][0], v = dst[i][1];
      A.push([x, y, 1, 0, 0, 0, -u*x, -u*y]); b.push(u);
      A.push([0, 0, 0, x, y, 1, -v*x, -v*y]); b.push(v);
    }
    var hv = solve(A, b); if(!hv) return null;
    return [hv[0], hv[1], hv[2], hv[3], hv[4], hv[5], hv[6], hv[7], 1];
  }
  function apply(H, x, y){ var d = H[6]*x + H[7]*y + H[8]; return [(H[0]*x + H[1]*y + H[2]) / d, (H[3]*x + H[4]*y + H[5]) / d]; }
  function invert3(H){
    var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7],i=H[8];
    var A=e*i-f*h, B=-(d*i-f*g), C=d*h-e*g, det=a*A+b*B+c*C; if(Math.abs(det)<1e-12) return null;
    return [A/det, -(b*i-c*h)/det, (b*f-c*e)/det, B/det, (a*i-c*g)/det, -(a*f-c*d)/det, C/det, -(a*h-b*g)/det, (a*e-b*d)/det];
  }

  /* ── 보조 측정 ─────────────────────────────────────────── */
  function sampleDisc(g, w, h, cx, cy, r){   /* 원 안 평균 밝기 */
    var s = 0, n = 0, r2 = r * r;
    for(var y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++){ if(y < 0 || y >= h) continue;
      for(var x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++){ if(x < 0 || x >= w) continue;
        if((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2){ s += g[y*w + x]; n++; } } }
    return n ? s / n : 255;
  }
  function sampleRing(g, w, h, cx, cy, r0, r1, pick){   /* 고리 안 밝기 — pick='median'|'mean' */
    var vals = [], a = r0 * r0, b = r1 * r1;
    for(var y = Math.floor(cy - r1); y <= Math.ceil(cy + r1); y++){ if(y < 0 || y >= h) continue;
      for(var x = Math.floor(cx - r1); x <= Math.ceil(cx + r1); x++){ if(x < 0 || x >= w) continue;
        var d = (x - cx) * (x - cx) + (y - cy) * (y - cy); if(d >= a && d <= b) vals.push(g[y*w + x]); } }
    if(!vals.length) return 255;
    if(pick === 'mean') return vals.reduce(function(s, v){ return s + v; }, 0) / vals.length;
    vals.sort(function(p, q){ return p - q; }); return vals[Math.floor(vals.length * 0.6)];   /* 상위 쪽 중앙값: 종이 흰색 */
  }
  function blurScore(g, w, h, x0, y0, x1, y1){   /* 라플라시안 분산(큰 값 = 선명) */
    var s = 0, s2 = 0, n = 0;
    x0 = Math.floor(x0); y0 = Math.floor(y0); x1 = Math.ceil(x1); y1 = Math.ceil(y1);
    for(var y = Math.max(1, y0); y < Math.min(h - 1, y1); y += 2) for(var x = Math.max(1, x0); x < Math.min(w - 1, x1); x += 2){
      var v = 4 * g[y*w + x] - g[y*w + x - 1] - g[y*w + x + 1] - g[(y-1)*w + x] - g[(y+1)*w + x]; s += v; s2 += v * v; n++; }
    return n ? (s2 / n - (s / n) * (s / n)) : 0;
  }

  /* ── 보정 이미지(펼친 답안지) 그리기 ─────────────────────── */
  function warp(gray, H, pxPerMm, form){
    var W = Math.round(form.page_mm[0] * pxPerMm), Hh = Math.round(form.page_mm[1] * pxPerMm);
    var c = document.createElement('canvas'); c.width = W; c.height = Hh; var ctx = c.getContext('2d');
    var out = ctx.createImageData(W, Hh), o = out.data, g = gray.g, gw = gray.w, gh = gray.h;
    for(var y = 0; y < Hh; y++){ var my = y / pxPerMm;
      for(var x = 0; x < W; x++){
        var p = apply(H, x / pxPerMm, my), sx = p[0], sy = p[1], v = 255;
        if(sx >= 0 && sy >= 0 && sx < gw - 1 && sy < gh - 1){
          var ix = sx | 0, iy = sy | 0, fx = sx - ix, fy = sy - iy, i0 = iy * gw + ix;
          v = g[i0] * (1-fx) * (1-fy) + g[i0+1] * fx * (1-fy) + g[i0+gw] * (1-fx) * fy + g[i0+gw+1] * fx * fy;
        }
        var k = (y * W + x) * 4; o[k] = o[k+1] = o[k+2] = v; o[k+3] = 255;
      }
    }
    ctx.putImageData(out, 0, 0); return c;
  }

  /* ── 본 처리 ─────────────────────────────────────────── */
  function analyze(src, form, opts){
    opts = opts || {};
    var t0 = performance.now();
    var full = toGray(src, 2400);                                   /* 측정용(세밀) */
    var small = toGray(src, 1400);                                  /* 마크 찾기용 */
    var q = { longSide: Math.max(src.naturalWidth || src.width, src.naturalHeight || src.height), warnings: [] };
    var fd = findFiducials(small);
    if(!fd.ok) return { ok: false, reason: fd.reason, message: fd.reason === 'fiducials_geom' ? '네 모서리 표식의 배치가 답안지 모양과 맞지 않아요. 답안지 전체가 평평하게 보이도록 다시 찍어 주세요.' : '네 모서리의 검은 표식이 모두 보이게 찍어 주세요 (' + (fd.found || 0) + '개만 보임).', quality: q, debug: fd };
    var k = full.w / small.w;                                      /* small → full 배율 */
    var F = form.fiducials, src4 = [[F.TL.cx, F.TL.cy], [F.TR.cx, F.TR.cy], [F.BR.cx, F.BR.cy], [F.BL.cx, F.BL.cy]];
    var dst4 = [fd.TL, fd.TR, fd.BR, fd.BL].map(function(c){ return [c.cx * k, c.cy * k]; });
    var H = homography(src4, dst4); if(!H) return { ok: false, reason: 'homography', message: '답안지 모양을 계산하지 못했어요. 다시 찍어 주세요.', quality: q };
    /* 품질: 답안지 폭(px) · 기울기 · 선명도 · 대비 */
    var pxPerMmX = Math.hypot(dst4[1][0] - dst4[0][0], dst4[1][1] - dst4[0][1]) / (F.TR.cx - F.TL.cx);
    var pxPerMmY = Math.hypot(dst4[3][0] - dst4[0][0], dst4[3][1] - dst4[0][1]) / (F.BL.cy - F.TL.cy);
    q.sheetWidthPx = Math.round(pxPerMmX * form.page_mm[0] / (full.scale || 1));
    q.aspectSkew = Math.abs(1 - (pxPerMmX / pxPerMmY));
    var g = full.g, w = full.w, h = full.h;
    var ptsX = dst4.map(function(p){ return p[0]; }), ptsY = dst4.map(function(p){ return p[1]; });
    q.blur = Math.round(blurScore(g, w, h, Math.min.apply(null, ptsX), Math.min.apply(null, ptsY), Math.max.apply(null, ptsX), Math.max.apply(null, ptsY)));
    /* 검정 기준: 마크 테두리 / 흰 기준: 마크 안쪽 흰 띠와 종이 */
    var black = 0, white = 0;
    [fd.TL, fd.TR, fd.BR, fd.BL].forEach(function(c){ black += (c.outer); white += c.ring; });
    black /= 4; white /= 4; q.contrast = Math.round(white - black);
    if(q.sheetWidthPx < 1300) q.warnings.push({ code: 'far', text: '답안지가 작게 찍혔어요. 조금 더 가까이에서 찍으면 더 정확해요.' });
    if(q.aspectSkew > 0.18) q.warnings.push({ code: 'skew', text: '많이 기울어져 찍혔어요. 정면에서 찍어 주세요.' });
    if(q.contrast < 70) q.warnings.push({ code: 'dark', text: '너무 어둡거나 빛이 반사됐어요. 더 밝은 곳에서 찍어 주세요.' });
    if(q.blur < (opts.blurMin || 120)) q.warnings.push({ code: 'blur', text: '초점이 흐려요. 잠시 멈춘 뒤 다시 찍어 주세요.' });
    if(q.sheetWidthPx < 900 || q.contrast < 45) return { ok: false, reason: 'quality', message: q.warnings.map(function(x){ return x.text; }).join(' '), quality: q, debug: fd };

    /* 칸 측정: 안쪽 원(반지름 r_mm) 평균 밝기, 바깥 고리(2.6~3.4mm) 종이 밝기 → 채움률 */
    var rIn = form.r_mm * pxPerMmX, cells = [];
    function measure(x, y){
      var p = apply(H, x, y), inner = sampleDisc(g, w, h, p[0], p[1], rIn), paper = sampleRing(g, w, h, p[0], p[1], 2.6 * pxPerMmX, 3.4 * pxPerMmX, 'median');
      var fill = (paper - inner) / Math.max(1, paper - black);
      return { px: p[0], py: p[1], inner: inner, paper: paper, fill: Math.max(0, Math.min(1.2, fill)) };
    }
    var answers = {};
    var FILL = opts.fillMin || 0.42, AMB = opts.ambMin || 0.16;
    /* 한 묶음(객관식 5칸 / 숫자열 10칸)의 상대 채움률 배열 → 판정. 연필처럼 연해도 혼자 뚜렷하면 '확실' */
    function judge(rel){
      var srt = rel.slice().sort(function(a, b){ return b.f - a.f; }), top = srt[0], second = srt[1] || { f: 0 };
      if(!top || top.f < AMB) return { st: 'blank', pick: null, on: [] };
      if(second.f >= FILL) return { st: 'multi', pick: top, on: srt.filter(function(r){ return r.f >= FILL; }) };
      if(second.f >= Math.max(AMB, top.f * 0.55)) return { st: 'ambiguous', pick: top, on: [top] };
      if(top.f < FILL * 0.7) return { st: 'ambiguous', pick: top, on: [top] };
      return { st: 'ok', pick: top, on: [top] };
    }      /* 연필 허용 → 채움 임계를 낮게, 모호 구간을 넓게 */
    Object.keys(form.choice).forEach(function(qn){
      var opts5 = form.choice[qn].map(function(o){ var m = measure(o.x, o.y); m.v = o.v; m.q = +qn; m.key = 'q' + qn + ':' + o.v; cells.push(m); return m; });
      /* 기준선: 이 문항의 가장 밝은 3칸 중앙값(빈 칸에도 글자 잉크가 있으므로 상대 비교) */
      var base = opts5.map(function(m){ return m.fill; }).sort(function(a, b){ return a - b; });
      var floor = base[1];
      var rel = opts5.map(function(m){ return { v: m.v, f: m.fill - floor, raw: m.fill }; });
      var J = judge(rel);
      answers[qn] = { kind: 'choice', value: J.pick ? String(J.pick.v) : null, status: J.st, marks: J.on.map(function(r){ return r.v; }), scores: rel.map(function(r){ return +r.f.toFixed(2); }) };
      opts5.forEach(function(m){ var r = rel.find(function(x){ return x.v === m.v; }); m.rel = r.f; m.on = J.on.indexOf(r) >= 0; m.amb = !m.on && r.f >= AMB; });
    });
    Object.keys(form.short).forEach(function(qn){
      var digits = [], st = 'ok', anyAmb = false, anyMulti = false, anyBlank = false, places = ['백', '십', '일'];
      places.forEach(function(pl){
        var col = (form.short[qn][pl] || []).map(function(o){ var m = measure(o.x, o.y); m.v = o.v; m.q = +qn; m.key = 'q' + qn + ':' + pl + ':' + o.v; cells.push(m); return m; });
        var base = col.map(function(m){ return m.fill; }).sort(function(a, b){ return a - b; }); var floor = base[2];
        col.forEach(function(m){ m.rel = m.fill - floor; });
        var J = judge(col.map(function(m){ return { v: m.v, f: m.rel, m: m }; }));
        col.forEach(function(m){ m.on = J.on.some(function(r){ return r.m === m; }); m.amb = !m.on && m.rel >= AMB; });
        if(J.st === 'blank'){ anyBlank = true; digits.push(null); }
        else { digits.push(J.pick.v); if(J.st === 'multi') anyMulti = true; else if(J.st === 'ambiguous') anyAmb = true; }
      });
      var blanks = digits.filter(function(d){ return d == null; }).length;
      if(blanks === 3) st = 'blank'; else if(anyMulti) st = 'multi'; else if(blanks || anyAmb) st = 'ambiguous';
      var value = (blanks === 3) ? null : String(parseInt(digits.map(function(d){ return d == null ? '0' : String(d); }).join(''), 10));
      answers[qn] = { kind: 'short', value: value, status: st, digits: digits };
    });
    var warped = opts.warp === false ? null : warp(full, H, opts.pxPerMm || 5, form);
    q.ms = Math.round(performance.now() - t0);
    var counts = { ok: 0, ambiguous: 0, multi: 0, blank: 0 };
    Object.keys(answers).forEach(function(k2){ counts[answers[k2].status]++; });
    return { ok: true, H: H, Hinv: invert3(H), pxPerMm: pxPerMmX, fiducials: fd, cells: cells, answers: answers, counts: counts, quality: q, warped: warped, gray: full, black: black, white: white };
  }

  window.OmrEngine = { analyze: analyze, _internal: { toGray: toGray, findFiducials: findFiducials, homography: homography, apply: apply } };
})();
