# -*- coding: utf-8 -*-
# 한/글 수식 상자 크기 계산기.
# 상수는 추측이 아니라 학원 파일 속 수식 1,699개의 실측값(한/글이 계산해 저장한 <hp:sz>)에 맞춘 것이다.
# 판정 기준은 하나 — **모자라게 잡으면 글자가 겹친다.** 넘치는 건 여백일 뿐이다.
import re, math

BASE = 1300                # 원본 일일N제와 같은 수식 크기(13pt)

W_DIGIT  = 675
W_LETTER = 675             # 소문자 (ab = 1350)
W_UPPER  = 1025            # 대문자 (ABD = 3075)
W_WIDE   = 1200            # m, w 처럼 넓은 소문자
W_CJK    = 1300            # 수식 안에 섞인 한글
W_ADD    = 1390            # + -
W_EQ     = 1520            # = < >
W_PAREN  = 520
W_BAR    = 620             # | (집합 표기)
W_COMMA  = 380
W_TICK   = 300             # ` 는 가는 공백
W_TILDE  = 600             # ~ 는 그보다 넓다 (4,~5,~6,~7 = 6048)
W_CONST  = 75
SUP      = 0.67
FRAC_PAD = 650
FRAC_BAR = 340
SQRT_W   = 1496
SAFETY   = 1.18
HSAFE    = 1.22

GREEK = set('alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi '
            'omicron pi rho sigma tau upsilon phi chi psi omega Gamma Delta Theta Lambda '
            'Xi Pi Sigma Upsilon Phi Psi Omega inf infty partial nabla'.split())
FUNCS = set('log ln lg sin cos tan sec csc cot sinh cosh tanh lim max min exp deg mod'.split())
BIGOP = set('sum prod int oint lim'.split())
ACCENT = set('bar vec hat tilde dot ddot box under overline underline'.split())
ACCENT |= {x.upper() for x in ACCENT}
RELS = {'LEQ': 1900, 'GEQ': 1900, 'NEQ': 1900, 'TIMES': 1420, 'DIV': 1420,
        'CDOT': 700, 'PLUSMINUS': 1500, 'MINUSPLUS': 1500,
        'RIGHTARROW': 1900, 'LEFTARROW': 1900, 'LEFTRIGHTARROW': 2200,
        'therefore': 1400, 'because': 1400, 'IDENTICAL': 1900,
        'IN': 1600, 'NOTIN': 1600, 'SUBSET': 1600, 'CAP': 1400, 'CUP': 1400,
        'APPROX': 1900, 'SIM': 1500, 'PROP': 1600, 'ANGLE': 900, 'PERP': 900,
        'cdots': 1600, 'dotaxis': 1600, 'ldots': 1600, 'dots': 1600,
        # 대문자 기호 낱말 — 표에 없으면 글자 수대로 재서 3배씩 넓어진다 (실측 중2·중3)
        'THEREFORE': 1400, 'BECAUSE': 1400, 'TRIANGLE': 1500, 'SQUARE': 1500,
        'DIVIDE': 1420, 'prime': 500, 'PRIME': 500}

# 소문자·중괄호로 쓰인 관계 기호를 한 가지로 모은다
_ALIAS = {'le': 'LEQ', 'leq': 'LEQ', 'ge': 'GEQ', 'geq': 'GEQ', 'ne': 'NEQ', 'neq': 'NEQ',
          'times': 'TIMES', 'div': 'DIV', 'cdot': 'CDOT', 'in': 'IN', 'cap': 'CAP',
          'cup': 'CUP', 'subset': 'SUBSET', 'approx': 'APPROX', 'sim': 'SIM',
          'rightarrow': 'RIGHTARROW', 'leftarrow': 'LEFTARROW', 'pm': 'PLUSMINUS',
          'mp': 'MINUSPLUS', 'equiv': 'IDENTICAL', 'perp': 'PERP', 'angle': 'ANGLE',
          'triangle': 'TRIANGLE', 'square': 'SQUARE', 'divide': 'DIVIDE'}

LBRACE, RBRACE, NULLDELIM = '\x01', '\x02', '\x03'
MULTI = ('cases', 'matrix', 'pmatrix', 'bmatrix', 'dmatrix', 'pile', 'lpile', 'rpile', 'eqalign')


def normalize(s):
    s = str(s)
    # LEFT{ ... RIGHT} 의 중괄호는 '묶음'이 아니라 '괄호 기호'다. 먼저 떼어낸다.
    s = re.sub(r'\b(?:LEFT|left)\s*\{', LBRACE, s)
    s = re.sub(r'\b(?:RIGHT|right)\s*\}', RBRACE, s)
    s = re.sub(r'\b(?:LEFT|left|RIGHT|right)\s*\.', NULLDELIM, s)
    s = s.replace('vert', '|').replace('Vert', '|')
    # 붙여 쓴 명령어를 떼어낸다 — 1over2 · cases{ · 31right 처럼 글자에 붙어 나온다
    s = re.sub(r'(?<![A-Za-z])over(?!line|brace|set|arrow)', ' over ', s)
    s = re.sub(r'(?<![A-Za-z])cdot(?!s)', ' cdot ', s)
    for kw in ('sqrt', 'root', 'cases', 'matrix', 'pile', 'eqalign',
               'LEFT', 'RIGHT', 'left', 'right', 'times', 'overline', 'underline',
               'box', 'BOX', 'bar', 'BAR', 'vec', 'VEC', 'hat', 'HAT', 'tilde', 'TILDE'):
        s = re.sub(r'(?<![A-Za-z])' + kw + r'(?![A-Za-z])', ' ' + kw + ' ', s)
    # ANGLErm BDE 처럼 대문자 낱말 뒤에 붙은 지시어 — 앞이 대문자라 위 규칙이 못 뗀다
    s = re.sub(r'(?<=[A-Z])(?:rm|it|bf)(?![a-z])', ' ', s)
    # ⚠ 대문자 지시어(RMA)도 온다 — 안 떼면 글자 수대로 재서 3~4배 넓어진다 (실측 중1 3월3회)
    s = re.sub(r'(?<![A-Za-z])(ITA|ita|BOLD|bold|RM|rm|IT|it|BF|bf)(?=[A-Za-z])', ' ', s)
    s = re.sub(r'(?<![A-Za-z])(ITA|ita|BOLD|bold|RM|rm|IT|it|BF|bf)(?![A-Za-z])', ' ', s)
    s = re.sub(r'[ ]{2,}', ' ', s)
    # {leq} 처럼 중괄호로 감싼 관계 기호를 편다
    s = re.sub(r'\{\s*([A-Za-z]+)\s*\}',
               lambda m: (' %s ' % _ALIAS[m.group(1).lower()]) if m.group(1).lower() in _ALIAS
               else m.group(0), s)
    s = re.sub(r'(?<![A-Za-z])([A-Za-z]+)(?![A-Za-z])',
               lambda m: _ALIAS.get(m.group(1).lower(), m.group(1))
               if m.group(1).lower() in _ALIAS else m.group(1), s)
    return s


def _depth0(s, ch):
    """중괄호 밖에 그 글자가 있는가"""
    d = 0
    for c in s:
        if c == '{': d += 1
        elif c == '}': d = max(0, d - 1)
        elif c == ch and d == 0: return True
    return False


def _split_top(s):
    """중괄호 깊이 0 에서 토큰을 끊는다. (LEFT{ 는 이미 치환돼 여기 안 걸린다)"""
    toks, buf, depth = [], '', 0
    for c in s:
        if c == '{':
            if depth == 0 and buf: toks.append(buf); buf = ''
            depth += 1; buf += c
        elif c == '}':
            depth -= 1; buf += c
            if depth <= 0:
                toks.append(buf); buf = ''; depth = 0
        elif depth == 0 and c == ' ':
            if buf: toks.append(buf); buf = ''
            toks.append(' ')
        else:
            buf += c
    if buf: toks.append(buf)
    return toks


def _unwrap(t):
    return t[1:-1] if t.startswith('{') and t.endswith('}') else t


def measure(script):
    """(폭, 높이). 모자라면 글자가 겹치므로 넉넉한 쪽으로 잡는다."""
    try:
        # 끝에 붙은 가는 공백(` ~)은 한/글이 폭에 세지 않는다 (실측 'a`' 750 = 'a')
        w, h = _measure(normalize(script).rstrip('`~ '), 1.0)
    except Exception:
        n = len(re.sub(r'\s+', '', str(script)))
        return int(max(1300, n * 900)), int(BASE * 2.6)
    return int(math.ceil((w + W_CONST) * SAFETY)), int(math.ceil(max(h, BASE) * HSAFE))


def _multi(inner, scale):
    """cases·matrix·pile — 여러 줄로 쌓인다. # 가 줄, & 가 칸."""
    rows = re.split(r'#+', inner)
    W, H = 0.0, 0.0
    for r in rows:
        rw = 0.0; rh = BASE * scale
        for cell in re.split(r'&+', r):
            cw, ch = _measure(cell, scale)
            rw += cw + 400 * scale
            rh = max(rh, ch)
        W = max(W, rw); H += rh
    return W + 900 * scale, H + 200 * scale


def _measure(s, scale):
    """토큰을 '덩이(atom)' 단위로 재고, over 는 앞뒤 덩이 하나씩만 묶는다."""
    # cases·matrix 로 감싸지 않고 # 로만 줄을 나눈 식도 있다 (해설의 정렬 블록)
    if '#' in s and _depth0(s, '#'):
        return _multi(s, scale)
    toks = _split_top(s)
    atoms = []                       # [(폭, 높이)]
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == ' ':
            i += 1; continue

        if t == 'over':              # 분수 — 바로 앞 덩이와 바로 뒤 덩이를 묶는다
            nw, nh = atoms.pop() if atoms else (0.0, BASE * scale)
            j = i + 1
            while j < len(toks) and toks[j] == ' ': j += 1
            if j < len(toks):
                dw, dh = _atom(toks, j, scale)[0:2]
                j = _atom(toks, j, scale)[2]
            else:
                dw, dh, j = 0.0, BASE * scale, j
            atoms.append((max(nw, dw) + FRAC_PAD * scale, nh + dh + FRAC_BAR * scale))
            i = j; continue

        if t in ('LEFT', 'left', 'RIGHT', 'right'):
            j = i + 1
            while j < len(toks) and toks[j] == ' ': j += 1
            if j < len(toks) and toks[j]:
                d = toks[j][0]
                atoms.append((0.0 if d == NULLDELIM else W_PAREN * scale, BASE * scale))
                rest = toks[j][1:]
                toks = toks[:j] + ([rest] if rest else []) + toks[j + 1:]
                i = j
            else:
                i = j
            continue

        k = i - 1
        while k >= 0 and toks[k] == ' ': k -= 1
        sup = k >= 0 and toks[k].endswith(('^', '_'))
        aw, ah, ni = _atom(toks, i, scale * (SUP if sup else 1.0))
        if sup:
            # ⚠ 기준을 '지금까지 최대 높이'로 잡으면 첨자마다 누적돼 4.8배까지 부푼다.
            #   첨자의 기준은 **바로 앞 덩이**다 (분수^2 처럼 큰 밑은 그 높이를 따른다)
            base_h = atoms[-1][1] if atoms else BASE * scale
            ah = base_h + ah * 0.55
        atoms.append((aw, ah))
        i = ni

    if not atoms:
        return 0.0, BASE * scale
    return sum(a[0] for a in atoms), max(a[1] for a in atoms)


def _atom(toks, i, scale):
    """toks[i] 에서 시작하는 덩이 하나 → (폭, 높이, 다음 위치)"""
    t = toks[i]
    if t in MULTI:
        j = i + 1
        while j < len(toks) and toks[j] == ' ': j += 1
        mw, mh = _multi(_unwrap(toks[j]) if j < len(toks) else '', scale)
        return mw, mh, j + 1
    if t == 'sqrt':
        j = i + 1
        while j < len(toks) and toks[j] == ' ': j += 1
        iw, ih = _measure(_unwrap(toks[j]) if j < len(toks) else '', scale)
        return SQRT_W * scale + iw, ih + 300 * scale, j + 1
    if t == 'root':
        j = i + 1
        while j < len(toks) and toks[j] == ' ': j += 1
        nw, _n = _measure(_unwrap(toks[j]) if j < len(toks) else '', scale * SUP)[0:2]
        k = j + 1
        while k < len(toks) and toks[k] in (' ', 'of'): k += 1
        iw, ih = _measure(_unwrap(toks[k]) if k < len(toks) else '', scale)
        return SQRT_W * scale + nw + iw, ih + 400 * scale, k + 1
    if t in ACCENT or t.lower() in ACCENT:
        j = i + 1
        while j < len(toks) and toks[j] == ' ': j += 1
        iw, ih = _measure(_unwrap(toks[j]) if j < len(toks) else '', scale)
        # 윗줄류(bar·vec·overline)는 폭을 거의 안 늘린다 — +800 은 실측 대비 1.7배였다
        pad = 800 if t.lower() in ('box',) else 150
        return iw + pad * scale, ih + 250 * scale, j + 1
    # 'alpha`' 처럼 가는 공백이 붙은 채 오면 기호 표를 못 찾고 글자 수대로 잰다 — 떼고 본다
    base = t.rstrip('`~')
    if base != t and base and (base in RELS or base in GREEK
                               or base in FUNCS or base in BIGOP):
        extra = sum((W_TICK if c == '`' else W_TILDE) for c in t[len(base):]) * scale
        if base in RELS:
            return RELS[base] * scale + extra, BASE * scale, i + 1
        if base in GREEK:
            return 760 * scale + extra, BASE * scale, i + 1
        return len(base) * W_LETTER * 0.98 * scale + extra, BASE * scale, i + 1
    if t in RELS:
        return RELS[t] * scale, BASE * scale, i + 1
    if t in GREEK:
        return 760 * scale, BASE * scale, i + 1
    if t in FUNCS or t in BIGOP:
        return len(t) * W_LETTER * 0.98 * scale, BASE * scale, i + 1
    if t.startswith('{'):
        iw, ih = _measure(_unwrap(t), scale)
        return iw, ih, i + 1
    w, h = _chars(t, scale)
    return w, h, i + 1


def _word_w(run, scale):
    """글자 연쇄 하나의 폭 — '+beta' 처럼 기호에 붙어 온 낱말도 표로 잰다."""
    if run in GREEK:
        return 760 * scale
    low = run.lower()
    if low in _ALIAS and _ALIAS[low] in RELS:
        return RELS[_ALIAS[low]] * scale
    if run in RELS:
        return RELS[run] * scale
    if run in FUNCS:
        return len(run) * W_LETTER * 0.98 * scale
    w = 0.0
    for c in run:
        if c in 'mw':
            w += W_WIDE
        elif c.isupper():
            w += W_UPPER
        else:
            w += W_LETTER
    return w * scale


def _chars(t, scale):
    w, h, j = 0.0, BASE * scale, 0
    while j < len(t):
        c = t[j]
        if c in '^_':
            j += 1
            if j < len(t) and t[j] == '{':
                d, k = 0, j
                while k < len(t):
                    if t[k] == '{': d += 1
                    elif t[k] == '}':
                        d -= 1
                        if d == 0: break
                    k += 1
                iw, ih = _measure(t[j + 1:k], scale * SUP)
                # ⚠ h + ih*0.55 로 누적하면 첨자 8개짜리 식이 4.8배 높이가 된다 —
                #   첨자는 겹치지 않는 한 키를 더 키우지 않는다 (실측 '공중부양' 신고)
                w += iw; h = max(h, BASE * scale + ih * 0.55)
                j = k + 1
            elif j < len(t):
                iw, ih = _measure(t[j], scale * SUP)
                w += iw; h = max(h, BASE * scale + ih * 0.55)
                j += 1
            continue
        if   c in '=<>':        w += W_EQ * scale
        elif c in '+-':         w += W_ADD * scale
        elif c in '()[]':       w += W_PAREN * scale
        elif c in (LBRACE, RBRACE): w += W_PAREN * scale
        elif c == NULLDELIM:    pass
        elif c == '|':          w += W_BAR * scale
        elif c == '~':          w += W_TILDE * scale
        elif c == '`':          w += W_TICK * scale
        elif c == ',':          w += W_COMMA * scale
        elif c in '.':          w += W_COMMA * scale
        elif c.isdigit():       w += W_DIGIT * scale
        elif c in '{}':         pass
        elif c == '!':          w += W_ADD * scale
        elif 0xE000 <= ord(c) <= 0xF8FF:
            w += W_BAR * scale                           # 한/글 PUA 기호 (절댓값 막대 등)
        elif ord(c) > 0x2000:   w += W_CJK * scale       # 한글·전각기호
        elif c.isalpha() and c.isascii():
            k2 = j
            while k2 < len(t) and t[k2].isalpha() and t[k2].isascii():
                k2 += 1
            w += _word_w(t[j:k2], scale)
            j = k2
            continue
        else:                   w += W_LETTER * scale
        j += 1
    return w, h
