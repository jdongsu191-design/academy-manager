# -*- coding: utf-8 -*-
"""포텐셜 hwpx 파서 (2차) — 미주(endNote) 를 문항 경계로 삼는다.

발견
  · 해설은 미주로 달려 있다. 한/글이 문서 끝(18~19쪽)에 모아 찍는다.
  · 미주 번호가 곧 문항 번호다 (자동 번호라 본문 글자엔 없다).
  · 그래서 문항 경계 추측이 필요 없다 — 미주 하나 = 문항 하나.

정본은 **한글 수식 스크립트**를 그대로 둔다. LaTeX 는 화면 표시용 파생일 뿐이다.
⚠ 읽기만 한다. 원본을 고치지 않는다.
"""
import zipfile, sys, re, json, base64, io
import xml.etree.ElementTree as ET
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

NS = lambda t: t.split('}')[-1]


# ── 한글 수식 → LaTeX (표시용) ─────────────────────────────────
# 정본은 스크립트 원문이다. 여기서 틀려도 저장된 내용은 안 망가진다.
EQ_WORD = [
    ('TRIANGLE', r'\triangle '), ('ANGLE', r'\angle '), ('DEG', r'^\circ '),
    ('triangle', r'\triangle '), ('angle', r'\angle '), ('square', r'\square '),
    ('SIGMA', r'\sum '), ('PI', r'\pi '), ('SQRT', r'\sqrt'),
    ('sqrt', r'\sqrt'), ('root', r'\sqrt'),
    ('overline', r'\overline'), ('bar', r'\overline'), ('vec', r'\vec'), ('hat', r'\hat'),
    ('times', r'\times '), ('cdot', r'\cdot '), ('div', r'\div '),
    ('pm', r'\pm '), ('mp', r'\mp '), ('infty', r'\infty '),
    ('sin', r'\sin '), ('cos', r'\cos '), ('tan', r'\tan '),
    ('log', r'\log '), ('lim', r'\lim '),
    ('theta', r'\theta '), ('alpha', r'\alpha '), ('beta', r'\beta '),
    ('pi', r'\pi '),
    ('LEQ', r'\le '), ('GEQ', r'\ge '), ('NEQ', r'\ne '),
    ('leq', r'\le '), ('geq', r'\ge '), ('neq', r'\ne '),
    ('PERP', r'\perp '), ('perp', r'\perp '),
]

# ⚠ 서체 지시어는 뒤 낱말에 **붙어서** 온다: rmTRIANGLE · rmcm · rm{bar{AD}}
#   그래서 뒤에 무엇이 오든 먼저 떼어내야 한다.
#   나중에 떼면 rmTRIANGLE 의 TRIANGLE 이 낱말 경계에 안 걸려 안 바뀐다 (실제로 12개 남았다).
#   뒤에 오는 것이 글자일 수도, 숫자일 수도, □ 같은 기호일 수도 있다 (rm□ABCD · rm8`cm).
#   그래서 뒤를 따지지 않는다. 앞이 영문자가 아니기만 하면 지시어다.
#   대문자로도 쓴다 (실측: RM ABCD · RM ANGLE APB).
#   ⚠ 뒤를 따지면 안 된다. rmcm(=cm) 처럼 소문자가 바로 붙어 오는 경우를 놓친다.
#     긴 것(ita)을 짧은 것(it)보다 먼저 적어 둔다.
FONT = re.compile(r'(?<![A-Za-z])(?:BOLD|bold|ITA|ita|RM|rm|IT|it)')


def strip_font(s):
    return FONT.sub('', s)


# ── over(분수) 는 중위 연산자다 ────────────────────────────────
# 한/글은 여는 중괄호가 없어도 읽는다: 9root5 }over4  →  9√5/4 (PDF 로 확인함)
# 그래서 왼쪽 항을 이렇게 잡는다: '}' 로 끝나면 짝 맞는 '{' 까지, 없으면 처음까지.
#                                아니면 공백 없는 마지막 토막.
OVER = re.compile(r'(?<![A-Za-z])over(?![a-z])')


def _left(t):
    t2 = t.rstrip()
    if t2.endswith('}'):
        depth = 0
        for i in range(len(t2) - 1, -1, -1):
            if t2[i] == '}':
                depth += 1
            elif t2[i] == '{':
                depth -= 1
                if depth == 0:
                    return t2[:i], t2[i + 1:-1]
        return '', t2[:-1]                    # 짝이 없으면 통째로 분자
    m = re.search(r'(\S+)$', t2)
    return (t2[:m.start()], m.group(1)) if m else (t2, '')


def _right(t):
    t2 = t.lstrip()
    if t2.startswith('{'):
        depth = 0
        for i, c in enumerate(t2):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return t2[1:i], t2[i + 1:]
        return t2[1:], ''
    m = re.match(r'\S+', t2)
    return (m.group(0), t2[m.end():]) if m else ('', t2)


def fix_over(s, depth=0):
    m = OVER.search(s)
    if not m or depth > 20:
        return s
    head, num = _left(s[:m.start()])
    den, tail = _right(s[m.end():])
    return fix_over('%s\\frac{%s}{%s}%s' % (head, num, den, tail), depth + 1)
EQ_CHAR = {'`': ' ', '~': ' ', '⫽': r'\parallel ', '∥': r'\parallel ',
           '□': r'\square ', '△': r'\triangle ', '∠': r'\angle ',
           '≡': r'\equiv ', '×': r'\times ', '÷': r'\div ', '°': r'^\circ '}


def eq_to_latex(s):
    """대충이라도 읽히게만 바꾼다. 정확도가 필요하면 정본(script)을 본다."""
    out = fix_over(strip_font(s))          # ← 서체 지시어를 떼고, 분수를 먼저 세운다
    for ch, rep in EQ_CHAR.items():
        out = out.replace(ch, rep)
    # 낱말 치환 — 긴 것부터, 낱말 경계를 지켜서
    # ⚠ 치환 문자열에 역슬래시가 들어가므로 람다로 넘긴다 (\s 를 이스케이프로 읽는다)
    for w, rep in sorted(EQ_WORD, key=lambda x: -len(x[0])):
        out = re.sub(r'(?<![A-Za-z\\])' + w + r'(?![a-z])', lambda m, r=rep: r, out)
    # \sqrt10 은 KaTeX 가 √1·0 으로 그린다 — 두 글자 이상이면 묶어 준다
    out = re.sub(r'\\(sqrt|overline|vec|hat)\s*([A-Za-z0-9]{2,})',
                 lambda m: '\\%s{%s}' % (m.group(1), m.group(2)), out)
    return re.sub(r'[ \t]+', ' ', out).strip()


# ── hwpx 훑기 ──────────────────────────────────────────────────
def items_of(el, skip_endnote=True):
    """문단 하나를 (종류, 값) 목록으로 편다."""
    out = []

    def go(e):
        tag = NS(e.tag)
        if tag == 'endNote' and skip_endnote:
            return
        if tag == 't':
            out.append(('t', e.text or ''))
            for ch in e:
                go(ch)
                if ch.tail:
                    out.append(('t', ch.tail))
            return
        if tag == 'equation':
            out.append(('eq', ''.join(x.text or '' for x in e.iter()
                                      if NS(x.tag) == 'script')))
            return
        if tag == 'pic':
            img, cmt = '', ''
            for x in e.iter():
                for k, v in x.attrib.items():
                    if NS(k) == 'binaryItemIDRef':
                        img = v
                if NS(x.tag) == 'shapeComment':
                    cmt = x.text or ''
            m = re.search(r'가로\s*(\d+)pixel,\s*세로\s*(\d+)pixel', cmt)
            out.append(('pic', (img, int(m.group(1)) if m else 0,
                                int(m.group(2)) if m else 0)))
            return
        for ch in e:
            go(ch)

    go(el)
    return out


def text_of(items):
    s = ''
    for k, v in items:
        if k == 't':
            s += v
        elif k == 'eq':
            s += '⟪%s⟫' % v
    return s


def parse(path):
    z = zipfile.ZipFile(path)
    probs, order = [], 0
    for si in range(9):
        try:
            root = ET.fromstring(z.read('Contents/section%d.xml' % si))
        except KeyError:
            break

        # 문서 순서대로 최상위 문단만 (미주 안 문단은 따로 본다)
        def top_paras(node, inside=False):
            for ch in node:
                t = NS(ch.tag)
                if t == 'endNote':
                    continue
                if t == 'p' and not inside:
                    yield ch
                    yield from top_paras(ch, inside=True)   # 표 안 문단
                else:
                    yield from top_paras(ch, inside)

        cur = None
        for p in top_paras(root):
            note = None
            for e in p.iter():
                if NS(e.tag) == 'endNote':
                    note = e
                    break
            if note is not None:
                order += 1
                cur = {'no': order, 'note': note, 'items': [], 'sec': si}
                probs.append(cur)
            if cur is not None:
                cur['items'] += items_of(p)
    return probs


# ── 문항 하나를 정리해 담기 ────────────────────────────────────
def _clean_ans(s):
    """미주·빠른답지의 정답 토막을 정본으로.
    ⟪⟫ 를 벗기고, 수식 안 개행을 공백으로, '4 개' 처럼 단위 앞 공백을 붙인다.
    (실측: 12번 미주가 ⟪4↵⟫개 — 개행이 정규식을 막아 정답이 빈값이 됐다)"""
    s = re.sub(r'[⟪⟫]', ' ', str(s or ''))
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'\s+(?=[가-힣]+$)', '', s)


HEAD = re.compile(r'\[Potential\s*([^\]]+?)\]\s*\[\s*(?:A\s*([\d.]+)점\s*/\s*B\s*([\d.]+)점|([\d.]+)점)\s*\]')
NOTE = re.compile(r'\[정답\]\s*(.*?)\s*\[Potential\s*([^\]]+?)\]\s*\[([^\]]+?)\]')
SRC = re.compile(r'출처\)\s*(.+)')
DROP = re.compile(r'^\s*(?:[123]단계|출처\)|\[\s*Potent!?al)')


def tidy(p):
    # ── 미주(해설) ──
    npar = [items_of(x, skip_endnote=False) for x in p['note'].iter()
            if NS(x.tag) == 'p']
    ntxt = [text_of(i).strip() for i in npar]
    npics = [v for i in npar for k, v in i if k == 'pic']
    head = next((t for t in ntxt if '[정답]' in t), '')
    head = re.sub(r'\s+', ' ', head)     # 수식 안 개행이 정규식을 막는다 (실측 12번)
    m = NOTE.search(head)
    src = next((SRC.search(t).group(1).strip() for t in ntxt if SRC.search(t)), '')

    # ── 본문 ──
    lines, pics, eqs = [], [], []
    for k, v in p['items']:
        if k == 'pic':
            pics.append(v)
        elif k == 'eq':
            eqs.append(v)
    body = text_of(p['items'])
    body = HEAD.sub('', body)
    body = re.sub(r'\[\s*Potent!?al[^\]]*\]', '', body)
    body = re.sub(r'(?:\d단계[^\n]*?하세요\.[^\n]*)', '', body)
    body = re.sub(r'출처\)[^⟪]*?번', '', body)
    body = re.sub(r'\s+', ' ', body).strip()

    hm = HEAD.search(text_of(p['items']))
    return {
        'number': p['no'],
        'level': (m.group(2).strip() if m else (hm.group(1).strip() if hm else '')),
        'type': m.group(3).strip() if m else '',
        'answer_script': _clean_ans(m.group(1) if m else ''),
        'points': ({'A': hm.group(2), 'B': hm.group(3)} if hm and hm.group(2)
                   else (hm.group(4) if hm else None)),
        'source': src,
        'statement': body,
        'eqs': eqs,
        'pics': pics,
        'note_pics': npics,
    }


def add_figures(probs, path):
    """장식(로고·오답노트 아이콘)을 걸러 문제그림·QR·해설그림을 나눠 담는다.
    장식 = 여러 문항에 되풀이되거나, 문항 밖에도 나오는 그림."""
    from collections import Counter
    z = zipfile.ZipFile(path)
    inside = Counter(x[0] for p in probs for x in p['pics'])
    total = Counter()
    for n in z.namelist():
        if not n.startswith('Contents/section'):
            continue
        for e in ET.fromstring(z.read(n)).iter():
            for k, v in e.attrib.items():
                if NS(k) == 'binaryItemIDRef':
                    total[v] += 1
    deco = {k for k in inside if inside[k] > 1 or total[k] > inside[k]}
    for p in probs:
        p['figures'] = [x for x in p['pics'] if x[0] not in deco and x[1] != 450]
        p['qr'] = [x for x in p['pics'] if x[1] == 450]
    return probs


# ══════════════════════════════════════════════════════════════
#  서버용 한 방 함수 — bytes 를 받아 문항 12개 + 정답 교차검증까지
#  (pt_verify.py 의 빠른답지 대조를 그대로 옮겼다)
# ══════════════════════════════════════════════════════════════
def _quick_answers(z):
    """맨 뒤 '빠른답지' 표에서 번호→정답을 읽는다."""
    quick = {}
    for si in range(9):
        try:
            root = ET.fromstring(z.read('Contents/section%d.xml' % si))
        except KeyError:
            break
        for tbl in root.iter():
            if NS(tbl.tag) != 'tbl':
                continue
            cells = []
            for tc in tbl.iter():
                if NS(tc.tag) == 'tc':
                    s = ''
                    for p in tc.iter():
                        if NS(p.tag) == 'p':
                            for k, v in items_of(p, skip_endnote=False):
                                s += v if k == 't' else ('⟪%s⟫' % v if k == 'eq' else '')
                    cells.append(s.strip())
            if not any('빠른답지' in c for c in cells):
                continue
            for i, c in enumerate(cells):
                if re.fullmatch(r'\d{1,2}', c) and i + 1 < len(cells):
                    nxt = cells[i + 1]
                    if nxt.startswith('⟪'):
                        quick[int(c)] = _clean_ans(nxt)
    return quick


def _norm_ans(s):
    """비교용 — 빠른답지는 23`(rmcm ^{2}) 처럼 괄호를 치기도 한다."""
    return re.sub(r'[`~\s(){}]', '', strip_font(s or ''))


_MIME = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
         'bmp': 'image/bmp', 'gif': 'image/gif', 'webp': 'image/webp'}


def bmp_to_png(b):
    """무압축 24비트 BMP → PNG (PIL 없이). 한/글 문서의 BMP 는 실측 135/135 이 형식.
    594KB BMP 가 수십 KB PNG 로 준다 — 응답 4.5MB 제한과 Gemini 형식 제한을 같이 푼다.
    다른 형식이면 None (원본 그대로 내보낸다)."""
    import struct, zlib
    try:
        if b[:2] != b'BM':
            return None
        off, = struct.unpack('<I', b[10:14])
        hs, = struct.unpack('<I', b[14:18])
        w, h = struct.unpack('<ii', b[18:26])
        bpp, = struct.unpack('<H', b[28:30])
        comp, = struct.unpack('<I', b[30:34])
        if hs < 40 or bpp != 24 or comp != 0 or w <= 0 or h == 0:
            return None
        flip = h > 0
        h = abs(h)
        stride = (w * 3 + 3) & ~3
        raw = bytearray()
        for y in range(h):
            row = b[off + (h - 1 - y if flip else y) * stride:][:w * 3]
            if len(row) < w * 3:
                return None
            raw.append(0)                       # PNG 필터 0
            for x in range(0, w * 3, 3):        # BGR → RGB
                raw += bytes((row[x + 2], row[x + 1], row[x]))
        def chunk(tag, data):
            c = struct.pack('>I', len(data)) + tag + data
            return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))
    except Exception:
        return None


def _bin_datauri(z, name):
    for n in z.namelist():
        if n.startswith('BinData/') and n.split('/')[-1].split('.')[0] == name:
            ext = n.rsplit('.', 1)[-1].lower()
            data = z.read(n)
            if ext == 'bmp':
                png = bmp_to_png(data)
                if png is not None:
                    ext, data = 'png', png
            if len(data) > 1200 * 1024:          # 응답 한도 보호 — 너무 큰 그림은 뺀다
                return None
            return 'data:%s;base64,%s' % (_MIME.get(ext, 'image/png'),
                                          base64.b64encode(data).decode())
    return None


def parse_potential(data):
    """hwpx 바이트 → 문항 목록(그림은 data URI) + 빠른답지 교차검증."""
    bio = io.BytesIO(data)
    probs = add_figures([tidy(p) for p in parse(bio)], io.BytesIO(data))
    z = zipfile.ZipFile(io.BytesIO(data))
    quick = _quick_answers(z)
    out = []
    for p in probs:
        figs = []
        for name, w, h in p['figures'][:2]:
            uri = _bin_datauri(z, name)
            if uri:
                figs.append({'name': name, 'w': w, 'h': h, 'data': uri})
        q = quick.get(p['number'])
        # 화면 표시용 — 본문을 글/수식 조각으로 나눠 수식엔 LaTeX 를 딸려 보낸다.
        # 정본은 어디까지나 statement(한글 수식 스크립트)다.
        parts = []
        for tok in re.split(r'(⟪[^⟫]*⟫)', p['statement']):
            if tok.startswith('⟪'):
                sc = tok.strip('⟪⟫')
                try:
                    parts.append({'eq': sc, 'latex': eq_to_latex(sc)})
                except Exception:
                    parts.append({'t': sc})
            elif tok:
                parts.append({'t': tok})
        out.append({
            'parts': parts,
            'number': p['number'], 'level': p['level'], 'type': p['type'],
            'points': p['points'], 'source': p['source'],
            'statement': p['statement'],
            'answer_script': p['answer_script'],
            'answer_latex': eq_to_latex(p['answer_script']),
            'answer_cross': ('일치' if q is not None and
                             _norm_ans(p['answer_script']) == _norm_ans(q)
                             else ('다름' if q is not None else '없음')),
            'quick_answer': q,
            'figures': figs,
        })
    return {'count': len(out), 'quick_count': len(quick), 'probs': out}


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'pt_src.hwpx'
    raw = parse(src)
    print('미주(=문항) %d개\n' % len(raw) + '=' * 78)
    out = []
    for p in raw:
        t = tidy(p)
        out.append(t)
        big = [x for x in t['pics'] if x[1] * x[2] > 60000 and x[1] != 450]
        fig = [x for x in t['pics'] if 0 < x[1] * x[2] <= 60000 or (x[1] < 300 and x[2] < 300)]
        qr = [x for x in t['pics'] if x[1] == 450]
        print('\n[%2d] %-4s %-6s %s점   출처) %s'
              % (t['number'], t['level'], t['type'], t['points'], t['source']))
        print('     정답 : %s   →  %s' % (t['answer_script'], eq_to_latex(t['answer_script'])))
        print('     본문 : %s' % t['statement'][:150])
        print('     수식 %d개 · 문제그림 %d · QR %d · 해설그림 %d'
              % (len(t['eqs']), len(fig), len(qr), len(t['note_pics'])))
    json.dump(out, open('pt_parsed.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n저장: pt_parsed.json')
