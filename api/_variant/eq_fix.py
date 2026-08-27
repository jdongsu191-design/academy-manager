# -*- coding: utf-8 -*-
"""AI 가 낸 수식 문자열을 한글 수식 스크립트로 되돌린다.

두 가지를 고친다.
① **삼켜진 역슬래시** — JSON 이스케이프가 \f \t \b \r \v 를 제어문자로 해석한다.
   모델이 "\frac" 이라 쓰면 \x0c 하나만 남아 **XML 이 깨진다**(실제로 깨졌다).
   제어문자 뒤에 영문자가 오면 역슬래시가 삼켜진 것으로 보고 되살린다.
② **LaTeX 잔재** — 한글 수식으로 쓰라고 해도 \frac \triangle 이 샌다.
   기계적으로 바꿀 수 있는 것은 바꾸고, 못 바꾸면 역슬래시만 떼어 낸다.
   (정본이 한글 수식이므로 LaTeX 가 섞이면 한/글이 못 읽는다)
"""
import re

BACK = {'\x08': 'b', '\x09': 't', '\x0a': 'n', '\x0b': 'v', '\x0c': 'f', '\x0d': 'r'}


def unswallow(s):
    """제어문자 뒤에 영문자가 오면 삼켜진 역슬래시를 되살린다."""
    out, n, i = [], 0, 0
    while i < len(s):
        c = s[i]
        if c in BACK and i + 1 < len(s) and s[i + 1].isalpha():
            out.append('\\' + BACK[c]); n += 1
        elif ord(c) < 32 and c not in '\n':
            pass                                  # 되살리지 못한 제어문자는 버린다
        else:
            out.append(c)
        i += 1
    return ''.join(out), n


# LaTeX → 한글 수식
PAIR = [
    (r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', lambda m: '{%s} over {%s}' % (m.group(1), m.group(2))),
    (r'\\dfrac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', lambda m: '{%s} over {%s}' % (m.group(1), m.group(2))),
    (r'\\sqrt\s*\{([^{}]*)\}', lambda m: 'sqrt {%s}' % m.group(1)),
    (r'\\text\s*\{([^{}]*)\}', lambda m: 'rm %s' % m.group(1)),
    (r'\\mathrm\s*\{([^{}]*)\}', lambda m: 'rm %s' % m.group(1)),
    (r'\\overline\s*\{([^{}]*)\}', lambda m: 'bar {%s}' % m.group(1)),
]
WORD = {'triangle': 'TRIANGLE ', 'angle': 'ANGLE ', 'circ': 'DEG ', 'degree': 'DEG ',
        'times': 'times ', 'cdot': 'cdot ', 'div': 'div ', 'pi': 'pi ',
        'sin': 'sin ', 'cos': 'cos ', 'tan': 'tan ', 'log': 'log ',
        'left': '', 'right': '', 'displaystyle': '', 'quad': '` ', 'qquad': '` ',
        'parallel': '⫽ ', 'perp': 'PERP ', 'square': '□ ', 'therefore': '∴ ',
        # ⚠ 화살표는 삼켜진 꼴로 온다. '\runs' 는 실측에서 \Rightarrow 가 뭉개진 결과다
        #   (그대로 두면 '5k^2 runs 20' 처럼 낱말이 인쇄된다).
        'Rightarrow': '⇒ ', 'rightarrow': '→ ', 'Leftarrow': '⇐ ',
        'leftarrow': '← ', 'implies': '⇒ ', 'to': '→ ', 'runs': '⇒ ',
        'leq': '≤ ', 'le': '≤ ', 'geq': '≥ ', 'ge': '≥ ', 'neq': '≠ ', 'ne': '≠ ',
        'approx': '≒ ', 'pm': '± ', 'mp': '∓ ', 'infty': 'inf ',
        'alpha': 'alpha ', 'beta': 'beta ', 'theta': 'theta ',
        # 한글 수식에도 있는 낱말은 이름 그대로 살린다
        'sqrt': 'sqrt ', 'over': 'over ', 'bar': 'bar ', 'rm': 'rm ', 'it': 'it '}

# 위 표에 없는 명령은 **버린다.** 이름을 그대로 남기면 뜻 없는 낱말이 인쇄된다.
_dropped = []


def delatex(s):
    """LaTeX 를 한글 수식으로. 모르는 명령은 버리고 따로 세어 둔다."""
    n = s.count('\\')
    for _ in range(6):                            # 중첩된 \frac 을 안쪽부터 푼다
        before = s
        for pat, rep in PAIR:
            s = re.sub(pat, rep, s)
        if s == before:
            break
    s = re.sub(r'\^\s*\\circ', '^{circ}', s)

    def one(m):
        w = m.group(1)
        if w in WORD:
            return WORD[w]
        _dropped.append(w)
        return '` '
    s = re.sub(r'\\([A-Za-z]+)', one, s)
    s = s.replace('\\', '')
    return s, n


def dropped():
    """버린 명령 목록 (무엇이 사라졌는지 눈으로 봐야 한다)."""
    return _dropped


# 역슬래시 없이 오는 LaTeX 도 있다 (실측: frac{80}{3}). 한글 수식엔 frac 이 없다.
BARE = [
    (r'(?<![A-Za-z])d?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}',
     lambda m: '{%s} over {%s}' % (m.group(1), m.group(2))),
    (r'(?<![A-Za-z])text\s*\{([^{}]*)\}', lambda m: 'rm %s' % m.group(1)),
    (r'(?<![A-Za-z])overline\s*\{([^{}]*)\}', lambda m: 'bar {%s}' % m.group(1)),
    (r'\^\s*\{?\s*circ\s*\}?', ' DEG '),
]


def debare(s):
    k = 0
    for _ in range(6):
        before = s
        for pat, rep in BARE:
            s2 = re.sub(pat, rep, s)
            if s2 != s:
                k += 1
            s = s2
        if s == before:
            break
    return s, k


def fix(script):
    """(고친 스크립트, 되살린 역슬래시 수, LaTeX 명령 수)"""
    s, n = unswallow(str(script or ''))
    s, k = delatex(s)
    s, k2 = debare(s)
    k += k2
    # XML 을 깨뜨릴 수 있는 나머지 제어문자를 마지막으로 턴다
    s = re.sub(r'[\x00-\x08\x0b-\x1f]', '', s)
    return s, n, k


def fix_text(t):
    """본문·풀이처럼 $ … $ 가 섞인 글."""
    parts = re.split(r'(\$)', str(t or ''))
    out, N, K = [], 0, 0
    inmath = False
    for p in parts:
        if p == '$':
            inmath = not inmath
            out.append(p); continue
        if inmath:
            s, n, k = fix(p)
            out.append(s); N += n; K += k
        else:
            out.append(re.sub(r'[\x00-\x08\x0b-\x1f]', '', p))
    return ''.join(out), N, K
