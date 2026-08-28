# -*- coding: utf-8 -*-
"""문항 본문 → 검산 명세. **출제자와 다른 호출**로 받는다.

같은 응답에서 문제와 검산을 같이 받으면, 모델이 잘못 이해한 게 양쪽에 똑같이 반영되어
검산이 통과해 버린다(실측: 부채꼴에서 AB 조건이 빠졌는데 검산은 통과할 뻔했다).
그래서 여기서는 **완성된 본문만** 주고, 답이 무엇인지도 알려주지 않는다.
"""
import sys, os, json, base64, re, time, urllib.request

# Vercel 함수 안에서 돈다 — 프록시를 거치지 않고 키로 직접 부른다.
# ⚠ 함수 시간 제한(60초) 안에 들어야 하므로 호출당 timeout 을 짧게 잡는다.
API = ('https://generativelanguage.googleapis.com/v1beta/models/'
       'gemini-2.5-flash:generateContent?key=%s')


def _gemini(body, timeout=25):
    key = os.environ.get('GEMINI_API_KEY') or ''
    if not key:
        raise RuntimeError('GEMINI_API_KEY 미설정')
    req = urllib.request.Request(API % key, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as rr:
        return json.loads(rr.read().decode())

PROMPT = """아래 수학 문제를 **좌표 조건으로 옮겨라.** 문제를 풀지 마라. 답을 쓰지 마라.
프로그램이 이 조건을 좌표로 풀어 답을 스스로 구한다.

문제
─────────────────────────
@STMT@
─────────────────────────
(그림이 있으면 이미지로 함께 준다. 그림에만 적힌 값도 조건에 넣어라.)

쓸 수 있는 것
  값        len(P,Q)   angle(P,Q,R)   area(P,Q,R)   x(P)   y(P)
  삼각비    sin(<각을 나타내는 식>)   cos(…)   tan(…)
  술어      parallel(A,B, C,D)   perp(A,B, C,D)   midpoint(M, A,B)
            collinear(A,B,C)     eqlen(A,B, C,D)  oncircle(P, O, r)
  등식      <식> = <식>        예) area(A,B,M) = 23     angle(D,F,C) = 30
                                  len(A,B) = len(A,C)   len(O,Q) = 10 - r
  부등식    <식> > <식>  (>= < <= 도 된다)   예) k > 0     len(A,H) > len(H,B)
  각은 도(°). 넓이·길이는 문제에 적힌 수 그대로. 사칙연산과 sqrt( ) 를 쓸 수 있다.

삼각비 문제에서 (이 단원이 그렇다)
  · **각은 반드시 세 점으로 적어라.**  cos(C) 는 안 된다 → cos(angle(A,C,B))
  · ∠B 처럼 꼭짓점 하나로 부르는 각은 그 삼각형의 두 이웃 꼭짓점을 찾아 세 점으로 편다.
  · 'tan x = 2/3 일 때' 처럼 삼각비가 주어지면 그것도 조건이다 → tan(angle(A,B,C)) = 2/3
  · 비를 묻거나 비만 주어졌으면 **크기를 마음대로 정하지 마라.**
    AH:HB = 3:2 는 scalars 에 k 를 두고  len(A,H) = 3*k ,  len(H,B) = 2*k 로 적어라.
    (수를 박아 넣으면 길이를 묻는 문제에서 없는 조건을 준 셈이 된다)
  · ask 가 비면 그대로 나눗셈으로 적어라. 예) len(A,B) / len(A,C)

대수 문제에서 (도형이 없어도 포기하지 마라)
  · 점이 없으면 points 를 빈 배열로 두고 **모든 미지수를 scalars 에** 넣어라.
  · 식·연립방정식·부등식을 constraints 에 **그대로** 적어라.
      예) "2*x + y = 7" , "x - y = 1" , "abs(a - 2) = 5" , "a > 0"
  · 곱셈 기호를 생략하지 마라: 2x → 2*x , xy → x*y. 거듭제곱은 x^2,
    절댓값은 abs( ), 분수는 / , 근호는 sqrt( ).
  · ask 에는 구하는 식을 적어라: "x" , "x + y" , "a*b"
  · ask 는 **한 식**이어야 한다. 순서쌍 "(x, y)" 를 적지 마라.
    문제가 여러 값을 각각 물으면(a 와 b 의 값) ask 에는 **첫 번째 것 하나만** 적어라.
  · 해가 여러 개일 수 있는 방정식은 문제가 준 범위·부등식 조건까지 **다** 적어야
    답이 하나로 정해진다.
  · 순서쌍 나열·개수 세기·순환소수 표기·자릿수·증명 문제는 이 언어로 못 옮긴다
    → points·scalars 를 비우고 why 에 이유를 적어라.

규칙
1. **문제에 적힌(또는 그림에 적힌) 조건을 하나도 빠뜨리지 마라.** 빠지면 답이 안 정해진다.
2. **문제에 없는 조건을 지어내지 마라.** 특히 답을 알고 넣는 조건은 절대 안 된다.
3. 정삼각형은 eqlen 두 줄, 정사각형은 eqlen 세 줄 + perp 한 줄로 적는다.
4. 교점은 점으로 두고 collinear 두 줄로 묶는다.
     예) AD 와 BE 의 교점 P  →  collinear(A,P,D) · collinear(B,P,E)
5. 접선·수선의 발은 collinear + perp 로 적는다.
6. 반지름처럼 점이 아닌 미지수는 scalars 에 이름을 두고 조건에서 쓴다.
7. ask 에는 **문제가 구하라는 것**을 식으로 적는다. 예) angle(A,P,B)
     여러 개의 합이면 area(A,D,M) + area(B,C,M) 처럼 쓴다.
8. start 에는 **그림과 같은 배치**의 대략적인 좌표를 모든 점에 대해 적어라.
   조건이 같아도 점을 어느 쪽에 두느냐로 답이 달라지므로 이게 있어야 한다.
   정확할 필요는 없다 — 배치(위아래·좌우·안팎)만 그림과 같으면 된다.
9. **'a 에 대한 식으로 나타내시오' 같은 문제도 반드시 옮겨라.** 포기하지 마라.
   그 문자를 scalars 에 두고, 본문이 정의한 대로 조건에 묶는다.
     예) '∠A=35°, AB=1, BC=a 일 때 tan70° 를 a 로 나타내시오'
         scalars     : ["a"]
         constraints : ["angle(A,B,C) = 90", "angle(B,A,C) = 35",
                        "len(A,B) = 1", "len(B,C) = a"]
         ask         : "tan(70)"          ← 구하라는 값 **그 자체**를 적는다
   프로그램이 배치를 풀며 a 값을 알아내고, 답으로 적힌 식에 넣어 맞는지 본다.
   ask 에 문자를 쓰지 마라. 구하라는 것이 무엇인지만 적으면 된다.
10. 좌표로 옮길 수 없는 문제면 points 를 빈 배열로 두고 why 에 이유를 적어라.
11. **그림이 보여 주는 배치도 조건이다.** '그림과 같이' 문제에서 어떤 점이 어떤 변 위에
    있으면 그것을 반드시 적어라 — 빠지면 그 점이 아무 데나 갈 수 있어 답이 안 정해진다.
      예) D 가 변 BC 위  →  collinear(B,D,C) · len(B,D) < len(B,C)
    어느 변 위인지 헷갈리면 지어내지 말고 why 에 적어라. 엉뚱한 변에 놓으면 틀린 답이 나온다.
12. **좌표를 자로 대듯 고정하면 풀이가 안정된다.** 한 점을 원점에, 그와 이웃한 한 점을
    x축 위에 두어라. 예) x(C) = 0 · y(C) = 0 · y(B) = 0 · x(B) > 0
    (길이·각은 안 바뀐다) **딱 그만큼만** 고정하라 — 더 고정하면 없는 조건을 준 셈이 된다.
    이때 x축에 얹은 변 위의 점은 y(D) = 0 처럼 쓰면 collinear 보다 낫다."""

SCHEMA = {'type': 'object', 'properties': {
    'points': {'type': 'array', 'items': {'type': 'string'}},
    'scalars': {'type': 'array', 'items': {'type': 'string'}},
    'constraints': {'type': 'array', 'items': {'type': 'string'}},
    'start': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'p': {'type': 'string'}, 'x': {'type': 'number'}, 'y': {'type': 'number'}},
        'required': ['p', 'x', 'y']}},
    'ask': {'type': 'string'}, 'why': {'type': 'string'}},
    'required': ['points', 'scalars', 'constraints', 'start', 'ask', 'why']}


def ask_spec(statement, fig_png=None, budget=8192, tries=3, temp=0.1):
    parts = []
    if fig_png:
        parts.append({'inlineData': {'mimeType': 'image/png',
                                     'data': base64.b64encode(fig_png).decode()}})
    # ⟦⟧ 는 조건 상자 표시 — 모델에겐 줄바꿈으로 풀어 보낸다
    txt = PROMPT.replace('@STMT@',
                         re.sub(r'[$⟪⟫]', '', re.sub(r'[⟦⟧]', '\n', statement or '')))
    parts.append({'text': txt})
    last = ''
    for b in (budget, 0):        # 60초 제한 안: 두 번만, 호출당 25초
        try:
            body = {'contents': [{'parts': parts}],
                    'generationConfig': {'temperature': temp, 'maxOutputTokens': 8192,
                                         'responseMimeType': 'application/json',
                                         'responseSchema': SCHEMA,
                                         'thinkingConfig': {'thinkingBudget': b}}}
            t0 = time.time()
            d = _gemini(body)
            c = (d.get('candidates') or [{}])[0]
            t = (((c.get('content') or {}).get('parts') or [{}])[0]).get('text')
            if not t:
                raise RuntimeError('빈 응답 (%s)' % c.get('finishReason'))
            r = json.loads(t)
            return {'points': r['points'], 'scalars': r['scalars'],
                    'constraints': r['constraints'], 'ask': r['ask'], 'why': r.get('why', ''),
                    'start': {s['p']: [s['x'], s['y']] for s in r['start']}}, time.time() - t0
        except Exception as e:
            last = str(e)
    raise RuntimeError(last)


# ── 한글 수식 정답을 숫자로 ──────────────────────────────
def num_of(script, vars=None):
    """'23`cm ^{2}' → 23.0 ,  '{14} over {9} pi' → 4.887…  (못 읽으면 None)

    vars 를 주면 문자식도 읽는다. 검산이 배치를 풀면서 구한 미지수 값을 넣으면
    '{2a} over {1-a^{2}}' 같은 답도 숫자가 되어 견줄 수 있다.
    """
    s = str(script or '')
    s = re.sub(r'[$⟪⟫`]', ' ', s)
    s = re.sub(r'[가-힣]+', ' ', s)      # '4개'·'3명' 같은 단위 낱말 (실측: 개 때문에 못 읽음)
    # 'a=11, b=11' 처럼 쌍으로 적힌 답 — 첫 쌍의 우변만 읽는다 (ask 도 첫 값 하나만 묻는다)
    if '=' in s:
        s = s.split(',')[0].split('=')[-1]
    s = re.sub(r'(?<![A-Za-z])(rm|it|ita|RM)(?![a-z])', ' ', s)
    # 한글 수식의 '크기 맞춘 괄호' — 낱말만 떼면 괄호 자체는 남는다
    #   '15 LEFT (2- sqrt {3} RIGHT )'  →  '15  (2- sqrt {3}  )'
    s = re.sub(r'(?<![A-Za-z])(LEFT|RIGHT|left|right)(?![A-Za-z])', ' ', s)
    s = re.sub(r'\bcm\s*\^\s*\{?\s*2\s*\}?', ' ', s)
    s = re.sub(r'\b(cm|mm|km|m)\b', ' ', s)
    # 도(°) 표기는 대소문자가 섞여 온다 — 실측: 'DEG' 도 있고 '60Deg' 도 있었다
    s = re.sub(r'(?<![A-Za-z])[Dd][Ee][Gg](?![A-Za-z])', ' ', s)
    s = s.replace('°', ' ').replace('^{circ}', ' ').replace('circ', ' ')
    s = re.sub(r'\s*over\s*', ' over ', s)                 # over 앞뒤 공백을 맞춘다
    # ⚠ sqrt 를 분수보다 **먼저** 푼다. '5sqrt{61}over{61}' 처럼 밀착해 오면
    #   분수 규칙이 sqrt 의 인자 중괄호를 분자로 오인해 sqrt(61/61) 이 된다 (실측 오판)
    s = re.sub(r'(?<![A-Za-z])(root|sqrt)\s*\{([^{}]*)\}', r'sqrt(\2)', s)
    s = re.sub(r'(?<![A-Za-z])(root|sqrt)\s*(\d+(?:\.\d+)?)', r'sqrt(\2)', s)
    s = re.sub(r'\{([^{}]*)\} over \{([^{}]*)\}', r'((\1)/(\2))', s)
    # 한/글은 여는 중괄호가 없어도 읽는다 (9root5 }over4 = 9√5/4). 남은 중괄호는 턴다.
    s = s.replace('{', ' ').replace('}', ' ')
    if ' over ' in s:                                       # 마지막 over 를 분수로
        L, R = s.rsplit(' over ', 1)
        s = '((%s)/(%s))' % (L, R)
    s = re.sub(r'\^\s*\{?\s*(\d+)\s*\}?', r'**\1', s)
    s = re.sub(r'(\d)\s*(sqrt|pi)', r'\1*\2', s)      # 9sqrt(5) → 9*sqrt(5)
    s = re.sub(r'(\))\s*(sqrt|pi)', r'\1*\2', s)
    s = re.sub(r'(\d)\s*pi', r'\1*pi', s)
    s = re.sub(r'(\))\s*pi', r'\1*pi', s)
    # 검산이 배치를 풀며 구한 미지수를 값으로 바꾼다 (긴 이름부터 — 'ab' 가 'a' 로 잘리면 안 된다)
    #  ⚠ '2a' 처럼 숫자에 붙어 오는 것을 놓치면 안 된다. 곱셈 기호가 생략된 표기다
    #    (실측: '{2a} over {a^2-1}' 이 통째로 안 읽혔다)
    for nm in sorted((vars or {}), key=len, reverse=True):
        val = '(%.12g)' % float(vars[nm])
        s = re.sub(r'(?<![A-Za-z_])(\d)\s*%s(?![A-Za-z_0-9])' % re.escape(nm),
                   lambda m, v=val: m.group(1) + '*' + v, s)
        s = re.sub(r'(?<![A-Za-z_0-9])%s(?![A-Za-z_0-9])' % re.escape(nm), val, s)
    s = re.sub(r'(\d)\s*\(', r'\1*(', s)
    s = re.sub(r'(\))\s*(\d)', r'\1*\2', s)
    s = re.sub(r'(\))\s*\(', r')*(', s)
    s = re.sub(r'(\))\s*(sqrt|pi)', r'\1*\2', s)
    s = s.strip()
    if not s or re.search(r'[A-Za-z]', s.replace('sqrt', '').replace('pi', '')):
        return None
    try:
        import math
        return float(eval(s, {'__builtins__': {}}, {'sqrt': math.sqrt, 'pi': math.pi}))
    except Exception:
        return None

# ── 그림에만 있는 기호를 묻는 문제는 검산하지 않는다 ──────
#  실측: "∠x 의 크기를 구하시오" 에서 x 가 그림에만 표시돼 있었고,
#  모델이 ∠ABE 라고 추측해 90° 를 내놓아 **오탐**이 났다(정답 85°).
#  오탐 하나가 검산 전체의 신뢰를 무너뜨리므로, 애매하면 검산하지 않는다.
#
#  ⚠ 다만 '∠BAD = ∠x 일 때 sin x' 처럼 **본문이 스스로 정의한** 기호까지 막으면
#     멀쩡한 문항을 통째로 버린다(삼각비 단원은 거의 다 이렇게 쓴다).
#     그래서 "묻는 기호가 본문에서 = 로 정의됐는가" 를 따로 본다.

# 무엇을 묻는가 — '… 의 값을/크기를/길이를' 바로 앞의 **홀로 선** 소문자
ASKED = re.compile(r'(?<![A-Za-z])([a-z])(?![A-Za-z])[^가-힣A-Za-z]{0,6}의\s*(?:값|크기|길이)')


def _defined(t, s):
    """'= s' 또는 's =' 꼴로 본문이 그 기호를 정의했는가.
    등호와 기호 사이에 한글이 끼면 다른 문장이므로 정의로 안 본다."""
    for m in re.finditer(r'(?<![A-Za-z])%s(?![A-Za-z])' % re.escape(s), t):
        left = t[max(0, m.start() - 40):m.start()]
        i = left.rfind('=')
        if i >= 0 and not re.search(r'[가-힣]', left[i:]) and re.search(r'[A-Z]{2,}', left[:i]):
            return True
        right = t[m.end():m.end() + 40]
        j = right.find('=')
        if j >= 0 and not re.search(r'[가-힣]', right[:j]) and re.search(r'[A-Z]{2,}', right[j:]):
            return True
    return False


def figure_only(statement):
    """묻는 대상이 그림 표시에만 있는 기호이면 그 기호를 돌려준다.
    ⚠ 본문에 '그림' 이 없는 문항엔 걸지 않는다 — 대수 문제의 'x 의 값' 을
      '그림에만 표시됨' 이라고 오도했다(실측: 중2 대수 파일 6문항)."""
    t = re.sub(r'[$⟪⟫⟦⟧`]', ' ', statement or '')
    if '그림' not in t:
        return None
    for m in ASKED.finditer(t):
        s = m.group(1)
        if not _defined(t, s):
            return s
    return None
