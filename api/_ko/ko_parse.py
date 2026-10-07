# -*- coding: utf-8 -*-
"""국어 시험지 PDF → 구조(JSON).  브라우저(pdf.js)에서 하던 일을 서버(pymupdf)로 옮긴 것.

왜 옮겼나 (실측, 2026 수능 국어)
 · pdf.js 는 줄 끝 공백을 45줄 중 2줄만 준다 → 띄어쓰기 971곳이 추정이었다. pymupdf 는 63% 를 준다.
 · pdf.js 는 글꼴 이름을 안 준다. pymupdf 는 신명-중명조(본문)·신명-태고딕(제목)·견명조(강조)를 준다.
 · pdf.js 는 이 PDF 를 그릴 수 없다(한 쪽 75초+). pymupdf 는 1초 → 표·활동지형 문항을 이미지로 넣는다.
 · '머리글은 쪽 높이의 12.5% 위' 같은 문턱값이 다른 시험지에서 바로 깨졌다('국어 영역' 띠가 본문에 박힘).
   여기서는 문턱값 대신 **쪽마다 반복되는 것 = 장식** 으로 가른다.

판정 규칙은 전부 pymupdf 로 먼저 실측한 것을 그대로 옮겼다 (들여쓰기 층 · 꽉 참 · 밑줄 조각 · 묶음 꺾쇠).
"""
import re, base64
from collections import Counter
import pymupdf

CH = '①②③④⑤'
RE_SET   = re.compile(r'^\s*[\[［\]］]{0,2}\s*(\d+)\s*[～~〜⁓]\s*(\d+)\s*[\]］]')
RE_QNO   = re.compile(r'^\s*(\d{1,2})\s*\.\s*')
RE_ELECT = re.compile(r'^\d{0,2}[(（](화법과작문|언어와매체)[)）]\d{0,2}$')
RE_SRC   = re.compile(r'^[-–—−]\s*[^,，]{1,40}[,，]\s*.{1,40}$')
RE_CUE   = re.compile(r'^\s*[\[［][가-힣]{1,6}[\]］]')
RE_CAP   = re.compile(r'\s*[<＜]\s*그\s*림\s*\d*\s*[>＞]\s*')
RE_HEAD  = re.compile(r'^[(（]\s*[가-힣]\s*[)）]$')
RE_NOTE  = re.compile(r'^[*✻※]')
RE_MARK  = re.compile(r'^[\[［]\s*[A-Z]\s*[\]］]$')
RE_LAB   = re.compile(r'[\[［]\s*([A-Z])\s*[\]］]')
RE_BOX   = re.compile(r'^[<＜]\s*보\s*기\s*[>＞]$')
RE_PTS3  = re.compile(r'\s*\[\s*3\s*점\s*\]\s*')
# 쪽 머리글·꼬리글 — 글 자체가 말해 주는 것들
RE_FURN  = re.compile(r'^(홀수형|짝수형|제\d교시|\d{1,3})$|대학수학능력시험|모의평가|학력평가|저작권')
RE_CIRC  = re.compile(r'([ⓐ-ⓩ㉠-㉾])(\s+)(?=[가-힣])')
RE_JOSA  = re.compile(r'\s(에서|에게|에|을|를|은|는|의)(?=[\s,.?!;:)\]}”’…·]|$)')


# ─────────────────────────────────────────────── 글자 덜어 내며 표시 자리 당기기
def _cut(t, marks, guess, at, ln):
    t = t[:at] + t[at + ln:]
    m2 = []
    for m in marks:
        s_ = m['s'] - ln if m['s'] > at else m['s']
        e_ = m['e'] - ln if m['e'] > at else m['e']
        s_, e_ = max(s_, min(at, m['s'])), max(e_, at if m['e'] > at else m['e'])
        if e_ > s_:
            m2.append({'s': s_, 'e': e_})
    g2 = [g - ln if g > at else g for g in guess if not (at <= g < at + ln)]
    return t, m2, g2


# ─────────────────────────────────────────────── 선·그림 상자 모으기
def _segs(page):
    hor, ver, arms, boxes = [], [], [], []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                x0, x1 = sorted((a.x, b.x)); y0, y1 = sorted((a.y, b.y))
            elif it[0] == 're':
                r = it[1]
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
                if r.width >= 3 and r.height >= 3:
                    boxes.append(r); continue
            else:
                continue
            w, h = x1 - x0, y1 - y0
            # 꺾쇠는 6.3~8.9pt(실측 두 시험지). 한 글자 밑줄(10.3pt~)과 섞이지 않게 9.5 에서 끊는다.
            if h < 1.5 and 3 <= w <= 9.5: arms.append((x0, x1, y0))
            if h < 1.5 and 8 <= w <= 95:  hor.append((x0, x1, y0))
            # ⚠ 25pt 로 두면 두 줄짜리 묶음 괄호(세로선 20pt, 실측 두 번째 시험지)를 놓친다.
            #    꺾쇠가 양끝에 있어야 묶음으로 치므로 낮춰도 표 테두리가 끌려오지 않는다.
            if w < 1.5 and h > 12:        ver.append((x0, y0, y1))
    return hor, ver, arms, boxes


def _label_spans(rows):
    """[A] 같은 묶음 라벨 — 제 줄에 홀로 있든(두 번째 시험지) 본문 줄에 붙어 있든(2026) span 으로 찾는다."""
    out = []
    for L in rows:
        for sp in L['sp']:
            m = RE_MARK.match(sp['s'].strip())
            if m:
                out.append({'x0': sp['x0'], 'yc': (sp['y0'] + sp['y1']) / 2,
                            'label': RE_LAB.search(sp['s']).group(1)})
    return out


def _marks_from_segs(page, hor, ver, arms, labels=()):
    """밑줄 자리와 묶음 괄호.
    ⚠ 「네모 강조」는 가로선이 위·아래 둘이다(실측 13.1pt 간격). 윗선은 윗줄 글자에
       밑줄을 그어 버리므로, 짝이 바로 아래 있는 선은 버린다.
    ⚠ [A] 괄호는 세로선 두 토막이다(가운데가 라벨 자리). 이어 붙인 뒤 위·아래 꺾쇠가 있고
       오른쪽에 짝이 되는 세로선이 없어야 묶음 괄호다. 표 테두리·단 구분선은 이 잣대로 걸러진다."""
    under = [h for h in hor if not any(
        abs(o[0] - h[0]) < 2 and abs(o[1] - h[1]) < 2 and 6 < (o[2] - h[2]) < 22 for o in hor)]
    ver = sorted(ver)
    merged = []
    for x, y0, y1 in ver:
        if merged and abs(merged[-1][0] - x) < 2 and (y0 - merged[-1][2]) < 30:
            merged[-1][2] = max(merged[-1][2], y1); continue
        merged.append([x, y0, y1])
    H = page.rect.height
    # ⚠ 묶음은 세로선이 아니라 **꺾쇠 한 쌍**으로 잡는다. 2026 수능은 긴 세로선이 있었지만
    #    두 번째 시험지는 세로 중간선을 아예 안 그리고 꺾쇠 + 3pt 토막만 그린다(실측).
    #    같은 x 에 위아래로 선 꺾쇠를 차례로 짝지으면 두 시험지 다 맞는다.
    groups = []
    uniq = sorted({(round(a[0], 1), round(a[2], 1)) for a in arms})          # (x0, y)
    # ① 라벨([A])이 있으면 그것이 기준이다 — 라벨 바로 위·아래의 꺾쇠가 괄호의 양끝이다.
    #    ⚠ 꺾쇠를 차례로 짝지으면 같은 x 에 짧은 선이 하나 더 있을 때 짝이 어긋난다(실측 [B]).
    for lb in labels:
        cand = [(y, x0) for x0, y in uniq if lb['x0'] - 6 <= x0 <= lb['x0'] + 16]
        above = [y for y, _ in cand if y < lb['yc']]
        below = [y for y, _ in cand if y > lb['yc']]
        if not above or not below:
            continue
        y0, y1 = max(above), min(below)
        x0 = next(x for y, x in cand if y == y0)
        if 12 <= y1 - y0 <= H * 0.6:
            groups.append({'x': x0, 'y0': y0, 'y1': y1, 'label': lb['label']})
    if groups:
        return under, groups
    # ② 라벨을 못 찾았을 때만 꺾쇠끼리 차례로 짝짓는다
    by_x = {}
    for x0, y in uniq:
        by_x.setdefault(round(x0 / 2.5), []).append((y, x0))
    for lst in by_x.values():
        lst.sort(); i = 0
        while i + 1 < len(lst):
            (y0, x0), (y1, _) = lst[i], lst[i + 1]
            span = y1 - y0
            pair = any(o[0] > x0 + 8 and abs(o[1] - y0) < 6 and abs(o[2] - y1) < 6 for o in merged)
            if 12 <= span <= H * 0.6 and not pair:
                groups.append({'x': x0, 'y0': y0, 'y1': y1, 'label': None}); i += 2
            else:
                i += 1
    return under, groups


# ─────────────────────────────────────────────── 줄 모으기
def _lines(page, mid):
    """spans 를 같은 단·같은 높이끼리 한 줄로. 줄 끝 공백은 pymupdf 가 보존해 준다."""
    rows = []
    for b in page.get_text('dict')['blocks']:
        if b.get('type', 0) != 0:
            continue
        for ln in b['lines']:
            for sp in ln['spans']:
                if not sp['text']:
                    continue
                x0, y0, x1, y1 = sp['bbox']
                base = sp['origin'][1]
                c = 0 if (x0 + x1) / 2 < mid else 1
                L = None
                # ⚠ span 의 윗변(y0)으로 묶으면 ①·ⓐ 처럼 크기가 다른 글자가 줄을 쪼갠다(실측:
                #    문항 번호가 따로 떨어져 [10~13] 이 문항 2개로 줄었다). pdf.js 처럼 기준선으로 묶는다.
                for r in rows:
                    if r['c'] == c and abs(r['base'] - base) < 3:
                        L = r; break
                if L is None:
                    L = {'c': c, 'base': base, 'y0': y0, 'y1': y1, 'x0': x0, 'x1': x1, 'sp': []}
                    rows.append(L)
                L['x0'] = min(L['x0'], x0); L['x1'] = max(L['x1'], x1)
                L['y0'] = min(L['y0'], y0); L['y1'] = max(L['y1'], y1)
                L['sp'].append({'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 's': sp['text'],
                                'font': sp['font'], 'size': round(sp['size'], 1)})
    for L in rows:
        L['sp'].sort(key=lambda s: s['x0'])
        L['raw'] = ''.join(s['s'] for s in L['sp'])
    rows.sort(key=lambda r: (r['c'], r['y0']))
    return rows


def _column_mid(page):
    """단 구분선(쪽을 거의 다 내려오는 세로선)이 있으면 그것, 없으면 가운데."""
    W, H = page.rect.width, page.rect.height
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if abs(a.x - b.x) < 1.5 and abs(a.y - b.y) > H * 0.5 and W * 0.4 < a.x < W * 0.6:
                    return a.x
    return W / 2


# ─────────────────────────────────────────────── 문서 읽기
def read_doc(doc):
    N = doc.page_count
    # ① 쪽마다 반복되는 그림 = 장식 (문턱값 없음)
    img_pages = Counter()
    for p in doc:
        for im in p.get_images(full=True):
            img_pages[im[0]] += 1
    furn_xrefs = {x for x, n in img_pages.items() if n >= max(3, N * 0.3)}

    pages = []
    for pno, page in enumerate(doc, 1):
        mid = _column_mid(page)
        rows = _lines(page, mid)
        hor, ver, arms, boxes = _segs(page)
        under, groups = _marks_from_segs(page, hor, ver, arms, _label_spans(rows))
        # 글을 담은 상자(초고·보기 테두리) — 상자 안 줄은 상자 폭이 곧 경계다. 쪽 전체 틀은 뺀다.
        boxes = [b for b in boxes if b.width < page.rect.width * 0.48 and b.height > 20]

        # ② 머리글: 글 자체가 말해 주는 줄들. 그 아래 끝선보다 위에 있는 것은 전부 장식.
        elect, hdr_bottom = None, 0.0
        # ⚠ 끝선은 쪽 맨 위 글줄에서 60pt 안의 머리글로만 잡는다. 윗부분 아무 데나 있는
        #    숫자 한 줄(선지 번호 조각 등)이 끌어올리면 [38~42] 머리줄까지 통째로 날아간다(실측).
        top = min((L['y0'] for L in rows if L['raw'].strip()), default=0.0)
        for L in rows:
            t = re.sub(r'\s', '', L['raw'])
            if not t:
                continue
            # ⚠ 기준선으로 묶으면 '4 (언어와 매체) 홀수형' 처럼 쪽번호·형과 한 줄이 된다.
            #    통째로 맞추지 말고, 머리글 띠(쪽 위 1/5) 안의 짧은 줄에서 라벨을 찾는다.
            m = RE_ELECT.match(t) or (re.search(r'(화법과작문|언어와매체)', t)
                                      if L['y0'] < page.rect.height * 0.2 and len(t) < 24 else None)
            if m:
                elect = '화법과 작문' if m.group(1) == '화법과작문' else '언어와 매체'
            if m or RE_FURN.search(t):
                L['furn'] = True
                # ⚠ 꼬리글('저작권…', 쪽번호)도 장식이지만 끝선에 넣으면 쪽 전체가 날아간다.
                #    끝선은 쪽 윗부분(절반 위)의 머리글로만 잡는다.
                if L['y0'] < top + 60:
                    hdr_bottom = max(hdr_bottom, L['y1'])
        body = []
        for L in rows:
            if L.get('furn') or not L['raw'].strip():
                continue
            if L['y1'] <= hdr_bottom + 1:
                continue
            body.append(L)

        # ③ 그림 상자 (장식 제외) — 글이 그림을 감싸는지, 어디에 꽂을지에 쓴다
        #    ⚠ 쪽 첫 글줄보다 위에 있는 그림은 머리 띠다('국어 영역'). 1쪽에만 있어
        #       반복 횟수로는 못 거르고, 머리글 끝선과는 1~2pt 차이로 엇갈린다(실측).
        first_y = min((L['y0'] for L in body), default=0.0)
        figs = []
        for im in page.get_images(full=True):
            xref = im[0]
            if xref in furn_xrefs:
                continue
            for r in page.get_image_rects(xref):
                if r.y1 <= hdr_bottom + 2 or r.width < 18 or r.height < 18:
                    continue
                if r.y0 < first_y - 1:
                    continue
                figs.append({'xref': xref, 'x0': r.x0, 'y0': r.y0, 'x1': r.x1, 'y1': r.y1,
                             'c': 0 if r.x0 < mid else 1})

        # ④ 단마다 들여쓰기 층 · 꽉 참
        for c in (0, 1):
            col = [L for L in body if L['c'] == c]
            if not col:
                continue
            gaps = sorted(col[i]['x0'] - col[i + 1]['x0'] for i in range(len(col) - 1)
                          if 4 <= col[i]['x0'] - col[i + 1]['x0'] <= 11)
            unit = gaps[len(gaps) // 2] if gaps else 7
            # ⚠ 오른쪽 끝(x1)은 같은 단 안에서도 396·401·405·409 로 흔들린다(실측) —
            #    pymupdf 의 span 끝이 꼬리 공백·문장부호에 따라 몇 pt 씩 다르다.
            #    최빈값(2pt 칸)으로 잡으면 비율이 25% 밑으로 흩어져 산문이 운문으로 오인된다.
            #    → 상위 분위수를 경계로 삼고 12pt 안이면 '꽉 참' 으로 본다. 운문은 행 길이가
            #      제각각이라 경계 가까이 모이는 줄이 드물다.
            # ⚠ 선지(①…) 줄은 본문보다 8~13pt 더 넓다(실측 409.6 vs 396.9). 선지까지 넣고 분위수를
            #    잡으면 경계가 선지 쪽으로 밀려 본문 줄이 전부 '덜 참' 이 되고 운문으로 오인된다.
            #    경계는 문항·선지가 아닌 줄로만 잰다.
            meas = [L for L in col if not RE_QNO.match(L['raw']) and L['raw'].lstrip()[:1] not in CH]
            xs = sorted(L['x1'] for L in (meas or col))
            edge = xs[max(0, int(len(xs) * 0.9) - 1)] if len(xs) > 2 else xs[-1]
            near = sum(1 for x in xs if edge - x < 12)
            justified = (near / len(xs)) >= 0.35
            for i, L in enumerate(col):
                nx = col[i + 1] if i + 1 < len(col) else None
                pv = col[i - 1] if i > 0 else None
                d = (L['x0'] - nx['x0']) if nx else 0
                same = pv is not None and abs(L['x0'] - pv['x0']) < 2
                L['indent'] = abs(d - unit) < 2.5 and not same
                # 상자(초고·보기 테두리) 안의 줄은 상자 오른쪽 변이 경계다
                inbox = [b for b in boxes if b.x0 - 2 <= L['x0'] and L['x1'] <= b.x1 + 2
                         and b.y0 - 2 <= L['y0'] and L['y1'] <= b.y1 + 2]
                e = (min(b.x1 for b in inbox) - 4) if inbox else edge
                L['full'] = (justified or bool(inbox)) and (e - L['x1']) < 12
                # 글이 그림을 감싸 흐르면 그 줄은 그림 때문에 짧다
                if any(f['x0'] > L['x1'] - 2 and f['y0'] <= L['y1'] + 2 and f['y1'] >= L['y0'] - 2
                       for f in figs):
                    L['full'] = True; L['wrap'] = True

        # ⑤ 줄마다: 밑줄 조각 · 묶음 · 공백 손질 · 표시 자리
        for L in body:
            t, marks = '', []
            for sp in L['sp']:
                on = bool(sp['s'].strip()) and any(
                    abs(h[0] - sp['x0']) < 2.5 and sp['y0'] < h[2] < sp['y1'] + 12 for h in under)
                if on:
                    marks.append({'s': len(t), 'e': len(t) + len(sp['s'])})
                t += sp['s']
            guess = []
            while True:
                m = RE_CIRC.search(t)
                if not m: break
                t, marks, guess = _cut(t, marks, guess, m.start() + len(m.group(1)), len(m.group(2)))
            while True:
                m = RE_JOSA.search(t)
                if not m: break
                t, marks, guess = _cut(t, marks, guess, m.start(), 1)
            L['sp_end'] = t.endswith(' ')
            L['s'] = t.rstrip()
            L['marks'] = [{'s': m['s'], 'e': min(m['e'], len(L['s']))} for m in marks
                          if min(m['e'], len(L['s'])) > m['s']]
            L['g'] = None
            # ⚠ 줄의 위아래 변으로 재면 두 줄짜리 괄호(20pt)에서 글자 상자가 꺾쇠를 몇 pt 넘어
            #    빈 묶음(G0)이 생긴다(실측). 줄의 가운데가 꺾쇠 사이에 들면 그 묶음이다.
            cy = (L['y0'] + L['y1']) / 2
            L['gl'] = None
            for gi, G in enumerate(groups):
                gc = 0 if G['x'] < mid else 1
                if L['c'] == gc and G['y0'] - 3 <= cy <= G['y1'] + 3:
                    L['g'] = '%d-%d' % (pno, gi); L['gl'] = G.get('label')
            L['p'] = pno
            L['font'] = Counter(s['font'] for s in L['sp']).most_common(1)[0][0]
            L['size'] = Counter(s['size'] for s in L['sp']).most_common(1)[0][0]

        pages.append({'no': pno, 'elect': elect, 'lines': body, 'figs': figs, 'mid': mid})
    return pages


# ─────────────────────────────────────────────── 줄 잇기
def _join(lines):
    txt, guess, marks = '', [], []
    for i, L in enumerate(lines):
        t = L['s']
        if i == 0:
            base = 0; txt = t
        else:
            if not lines[i - 1]['sp_end']:
                guess.append(len(txt))
            txt += ' '
            base = len(txt)
            txt += t
        for m in L['marks']:
            a, b = base + m['s'], base + min(m['e'], len(t))
            if b > a:
                marks.append({'s': a, 'e': b})
    return txt, guess, marks


def _item_p(buf):
    txt, guess, marks = _join(buf)
    while True:
        m = RE_CAP.search(txt)
        if not m: break
        txt, marks, guess = _cut(txt, marks, guess, m.start(), len(m.group(0)))
    return {'t': 'p', 'text': txt, 'guess': guess, 'marks': marks, 'n': len(buf),
            'ind': bool(buf[0].get('indent')), 'font': buf[0]['font'],
            'p': buf[0]['p'], 'c': buf[0]['c'], 'y': buf[0]['y0'], 'y1': buf[-1]['y1']}


def _body_plain(ls):
    out, buf = [], []
    def flush():
        if buf:
            out.append(_item_p(list(buf))); buf.clear()
    for L in ls:
        t = L['s'].strip()
        if not t:
            continue
        kind = ('head' if RE_HEAD.match(t) else 'note' if RE_NOTE.match(t)
                else 'mark' if RE_MARK.match(t) else 'fig' if RE_CAP.fullmatch(t) else None)
        if kind:
            flush(); out.append({'t': kind, 'text': t, 'p': L['p'], 'c': L['c'], 'y': L['y0']}); continue
        prev = buf[-1] if buf else None
        # ⚠ 앞 줄이 꽉 차지 않았으면 그 줄에서 글이 끝난 것이다. 이어 붙이면 시가 뭉개진다.
        if L.get('indent') or RE_CUE.match(t) or (prev is not None and not prev.get('full')):
            flush()
        buf.append(L)
    flush()
    return _verse(out)


def _verse(items):
    """한 줄짜리 덩이가 잇따르면 운문 — 행을 그대로 살린다. 행 사이가 벌어지면 연이 바뀐 것."""
    res, run = [], []
    def flush():
        if len(run) >= 2:
            gaps = sorted(run[i]['y'] - run[i - 1]['y'] for i in range(1, len(run)))
            step = gaps[len(gaps) // 2] if gaps else 0
            rows, cur = [], []
            for i, it in enumerate(run):
                if i and step and (it['y'] - run[i - 1]['y']) > step * 1.6 and cur:
                    rows.append(cur); cur = []
                cur.append(it)
            if cur: rows.append(cur)
            res.append({'t': 'verse', 'rows': rows, 'p': run[0]['p'], 'c': run[0]['c'],
                        'y': run[0]['y'], 'y1': run[-1]['y1']})
        elif run:
            res.append(run[0])
        run.clear()
    for it in items:
        if it['t'] == 'p' and it['n'] == 1 and not it['ind']:
            run.append(it)
        else:
            flush(); res.append(it)
    flush()
    return res


def _body(ls):
    """묶음 괄호([A]) 안의 줄들을 통째로 싸고, 글 가운데 박힌 라벨을 떼어 낸다."""
    out, run, cur = [], [], None
    def flush():
        nonlocal run
        if not run: return
        items = _body_plain(run)
        # 괄호를 라벨로 찾았으면 그 이름이 가장 확실하다
        lab = next((L['gl'] for L in run if L.get('gl')), None)
        run = []
        if cur is None:
            out.extend(items); return
        # ⚠ 라벨([A])은 두 모습이다 — 2026 수능처럼 본문 줄에 붙어 있거나(기준선이 같음),
        #    두 번째 시험지처럼 괄호 가운데 홀로 떠 있거나(제 줄). 둘 다 묶음 이름으로 삼는다.
        for it in list(items):
            if it['t'] == 'mark' and RE_MARK.match(it['text']):
                lab = lab or RE_LAB.search(it['text']).group(1)
                items.remove(it)
        # ⚠ 이름을 이미 알아도 글에 박힌 라벨은 떼어 내야 한다('…가라앉을 것이다[A]' 가 남았다).
        #    운문 행 안에 있을 수도 있으니 잎(p) 전부를 훑는다. 한 묶음에 라벨은 하나다.
        leaves = [x for it in items for x in
                  ((l for row in it['rows'] for l in row) if it['t'] == 'verse' else [it])
                  if x['t'] == 'p']
        for x in leaves:
            m = RE_LAB.search(x['text'])
            if m and (lab is None or m.group(1) == lab):
                lab = lab or m.group(1)
                x['text'], x['marks'], x['guess'] = _cut(x['text'], x['marks'], x['guess'],
                                                          m.start(), len(m.group(0)))
                x['text'] = x['text'].strip()
                break
        out.append({'t': 'group', 'label': lab, 'items': items,
                    'p': items[0]['p'] if items else None, 'c': items[0]['c'] if items else None})
    for L in ls:
        g = L.get('g')
        if g != cur:
            flush(); cur = g
        run.append(L)
    flush()
    return out


# ─────────────────────────────────────────────── 문항
def _one_q(seg, no):
    q = {'no': no, 'pts': 2, 'stem': '', 'stemGuess': [], 'stemMarks': [], 'box': None,
         'choices': [], 'p': seg[0]['p'], 'c': seg[0]['c'], 'y': seg[0]['y0'], 'y1': seg[-1]['y1']}
    cAt = next((i for i, L in enumerate(seg) if CH[0] in L['s']), -1)
    bEnd = len(seg) if cAt < 0 else cAt
    bAt = next((i for i in range(bEnd) if RE_BOX.match(seg[i]['s'].strip())), -1)
    head = seg[:bAt if bAt >= 0 else bEnd]
    if head:
        txt, guess, marks = _join(head)
        m = RE_QNO.match(txt); off = m.end() if m else 0
        txt = txt[off:]
        q['stemGuess'] = [g - off for g in guess if g >= off]
        q['stemMarks'] = [{'s': m2['s'] - off, 'e': m2['e'] - off} for m2 in marks if m2['e'] > off]
        if RE_PTS3.search(txt):
            q['pts'] = 3
            m3 = RE_PTS3.search(txt)
            txt, q['stemMarks'], q['stemGuess'] = _cut(txt, q['stemMarks'], q['stemGuess'], m3.start(), len(m3.group(0)))
            txt = txt.rstrip()
        q['stem'] = txt.strip()
    if bAt >= 0:
        bl = seg[bAt + 1:bEnd]
        txt, guess, marks = _join(bl) if bl else ('', [], [])
        q['box'] = {'text': txt, 'guess': guess, 'marks': marks,
                    'p': bl[0]['p'] if bl else q['p'], 'c': bl[0]['c'] if bl else q['c'],
                    'y': bl[0]['y0'] if bl else q['y'], 'y1': bl[-1]['y1'] if bl else q['y']}
    if cAt >= 0:
        cur = None
        for L in seg[cAt:]:
            t = L['s']
            starts = sorted((t.index(ch), j + 1) for j, ch in enumerate(CH) if ch in t)
            if starts and starts[0][0] <= 2:
                if cur: q['choices'].append(cur)
                for j, (at, n) in enumerate(starts):
                    to = starts[j + 1][0] if j + 1 < len(starts) else len(t)
                    one = {'n': n, 'p': L['p'], 'c': L['c'], 'y': L['y0'], 'y1': L['y1'],
                           'lines': [{'s': t[at + 1:to], 'sp_end': L['sp_end'] if j + 1 == len(starts) else False,
                                      'marks': [{'s': m['s'] - at - 1, 'e': min(m['e'], to) - at - 1}
                                                for m in L['marks'] if m['e'] > at + 1 and m['s'] < to]}]}
                    if j + 1 < len(starts): q['choices'].append(one)
                    else: cur = one
            elif cur:
                cur['lines'].append({'s': t, 'sp_end': L['sp_end'], 'marks': L['marks']})
                cur['y1'] = L['y1']
        if cur: q['choices'].append(cur)
        for ch in q['choices']:
            txt, guess, marks = _join(ch['lines'])
            lead = len(txt) - len(txt.lstrip())
            ch['text'] = txt.strip()
            ch['guess'] = [g - lead for g in guess if g >= lead]
            ch['marks'] = [{'s': max(0, m['s'] - lead), 'e': m['e'] - lead} for m in marks if m['e'] > lead]
            del ch['lines']
    return q


def _questions(ls, lo, hi):
    # ⚠ 경계는 범위 안 번호로만 자르면 안 된다. 범위 밖 단독 문항(언매 37)이 경계가 못 되어
    #    앞 문항(36)이 세트 끝까지 늘어나 선지가 20개가 된다(실측). 모든 번호로 자르고
    #    범위 안 것만 돌려준다.
    at = [(i, int(m.group(1))) for i, L in enumerate(ls) for m in [RE_QNO.match(L['s'])] if m]
    out = []
    for k, (i, no) in enumerate(at):
        if not (lo <= no <= hi):
            continue
        end = at[k + 1][0] if k + 1 < len(at) else len(ls)
        out.append(_one_q(ls[i:end], no))
    return out


# ─────────────────────────────────────────────── 세트
def parse_sets(pages):
    lines = [L for pg in pages for L in pg['lines']]
    elect = {pg['no']: pg['elect'] for pg in pages if pg['elect']}
    heads = [(i, int(m.group(1)), int(m.group(2))) for i, L in enumerate(lines)
             for m in [RE_SET.match(L['s'])] if m]
    sets = []
    for k, (i, a, b) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        seg = lines[i:end]
        # ⚠ 머리줄은 2~3줄일 수 있다(38~42 · 43~45 · 44~45). '물음에 답하시오' 까지가 머리줄.
        hEnd = next((j + 1 for j in range(min(len(seg), 4)) if re.search(r'물음에\s*답하시오', seg[j]['s'])), 1)
        qAt = next((j for j in range(hEnd, len(seg)) for m in [RE_QNO.match(seg[j]['s'])]
                    if m and int(m.group(1)) == a), len(seg))
        lead = RE_SET.sub('', ' '.join(L['s'].strip() for L in seg[:hEnd])).strip()
        body_lines = seg[hEnd:qAt]
        pgs = sorted({L['p'] for L in seg})
        area = next((elect[p] for p in pgs if p in elect), None)
        if not area:
            area = '문학' if any(RE_SRC.match(L['s'].strip()) for L in body_lines) else '독서'
        sets.append({'from': a, 'to': b, 'range': '%d~%d' % (a, b), 'area': area, 'lead': lead,
                     'body': _body(body_lines), 'qs': _questions(seg[qAt:], a, b),
                     'pages': pgs})
        # ⚠ 묶음에 안 든 단독 문항이 있다 — 언어와 매체 37·38·39(문법). 머리줄 사이 구간에 끼어
        #    있어 앞 묶음(35~36)에 딸려 들어가면 36번 선지가 20개가 된다(실측). 따로 세운다.
        tail = seg[qAt:]
        starts = [(j, int(m.group(1))) for j, L in enumerate(tail)
                  for m in [RE_QNO.match(L['s'])] if m]
        for k2, (j, no) in enumerate(starts):
            if a <= no <= b:
                continue
            end2 = starts[k2 + 1][0] if k2 + 1 < len(starts) else len(tail)
            qs = _questions(tail[j:end2], no, no)
            if not qs:
                continue
            pg2 = sorted({L['p'] for L in tail[j:end2]})
            area2 = next((elect[p] for p in pg2 if p in elect), area)
            sets.append({'from': no, 'to': no, 'range': str(no), 'area': area2, 'lead': '',
                         'body': [], 'qs': qs, 'pages': pg2})
    # 홀수형·짝수형이 한 파일에 있어 같은 지문이 두 번 잡힌다 → 본문이 같으면 하나로
    seen, out = set(), []
    for S in sets:
        key = (S['area'], S['range'], re.sub(r'\s', '', ''.join(
            it['text'] for it in S['body'] if it['t'] == 'p'))[:400])
        if key in seen: continue
        seen.add(key); out.append(S)
    return out


def _flatten(items):
    for it in items:
        if it['t'] == 'group': yield from _flatten(it['items'])
        elif it['t'] == 'verse':
            for row in it['rows']: yield from row
        else: yield it


def _b64(data): return base64.b64encode(data).decode('ascii')


def parse(pdf_bytes, lo=1, hi=99, max_fig=150_000):
    """⚠ Vercel 함수의 응답 한도는 4.5MB 다. 그림을 다 실으면 4.2MB 까지 갔다(실측).
       작은 그림만 싣고, 큰 것은 브라우저가 pdf.js 로 꺼낸다(자리 정보는 여기서 준다)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype='pdf')
    pages = read_doc(doc)
    all_sets = parse_sets(pages)
    sets = [S for S in all_sets if S['from'] >= lo and S['to'] <= hi]
    skipped = len(all_sets) - len(sets)
    used = {p for S in sets for p in S['pages']}

    # 그림: 고른 지문이 놓인 쪽에서만. 원본 비트맵을 그대로 꺼낸다(다시 그리지 않는다).
    figs = []
    for pg in pages:
        if pg['no'] not in used: continue
        for f in pg['figs']:
            try:
                info = doc.extract_image(f['xref'])
                data, ext = info['image'], info['ext']
                if ext not in ('png', 'jpeg', 'jpg', 'jpx', 'gif', 'bmp'):
                    pix = pymupdf.Pixmap(doc, f['xref'])
                    if pix.n - pix.alpha >= 4: pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    data, ext = pix.tobytes('png'), 'png'
            except Exception:
                data, ext = None, None
            figs.append({'p': pg['no'], 'c': f['c'], 'y': f['y0'], 'y1': f['y1'], 'x0': f['x0'], 'x1': f['x1'],
                         'w': f['x1'] - f['x0'], 'h': f['y1'] - f['y0'], 'ext': ext,
                         'b64': _b64(data) if data and len(data) <= max_fig else None,
                         'bytes': len(data) if data else 0})

    # 표·활동지형 문항(선지가 5개가 아님) — 글자로 못 푸니 그 영역을 그대로 그려 넣는다
    tables = []
    for S in sets:
        for q in S['qs']:
            if len(q['choices']) == 5: continue
            page = doc[q['p'] - 1]
            mid = pages[q['p'] - 1]['mid']
            x0, x1 = (page.rect.x0 + 20, mid - 6) if q['c'] == 0 else (mid + 6, page.rect.x1 - 20)
            clip = pymupdf.Rect(x0, q['y'] - 4, x1, q['y1'] + 6) & page.rect
            # ⚠ 문항이 단을 넘어가면 y 가 뒤집혀 빈 사각형이 된다 → 렌더러가 터진다(실측)
            if clip.is_empty or clip.width < 20 or clip.height < 10:
                q['table_png'] = None
                continue
            pix = page.get_pixmap(clip=clip, dpi=150)
            q['table_png'] = _b64(pix.tobytes('png'))
            tables.append({'no': q['no'], 'p': q['p'], 'w': pix.width, 'h': pix.height})

    body_items = [it for S in sets for it in _flatten(S['body'])]
    stats = {
        'pages': doc.page_count, 'sets': len(sets), 'qs': sum(len(S['qs']) for S in sets),
        'choices': sum(len(q['choices']) for S in sets for q in S['qs']),
        'paras': sum(1 for it in body_items if it['t'] == 'p'),
        'verse': sum(1 for S in sets for it in S['body'] if it['t'] == 'verse'),
        'groups': sum(1 for S in sets for it in S['body'] if it['t'] == 'group'),
        'under': sum(len(it.get('marks', [])) for it in body_items)
                 + sum(len(q['stemMarks']) + sum(len(c['marks']) for c in q['choices'])
                       + (len(q['box']['marks']) if q['box'] else 0) for S in sets for q in S['qs']),
        'guess': sum(len(it.get('guess', [])) for it in body_items)
                 + sum(len(q['stemGuess']) + sum(len(c['guess']) for c in q['choices'])
                       + (len(q['box']['guess']) if q['box'] else 0) for S in sets for q in S['qs']),
        'figs': len(figs), 'figs_inline': sum(1 for f in figs if f['b64']), 'tables': len(tables),
        'areas': dict(Counter(S['area'] for S in sets)), 'skipped': skipped,
    }
    for S in sets: S.pop('pages', None)
    return {'sets': sets, 'figs': figs, 'tables': tables, 'stats': stats}
