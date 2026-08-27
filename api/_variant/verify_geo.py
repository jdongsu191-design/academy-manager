# -*- coding: utf-8 -*-
"""평면기하 검산기 — 조건을 좌표로 풀어 답을 **코드가 다시 구한다**.

원리는 하나다.
    조건을 잔차로 바꾸고, 무작위 초기값에서 여러 번 수치로 푼다.
      · 해가 없다              → 조건 모순
      · 매번 같은 답            → 답이 결정된다. 그 값이 답이다
      · 매번 다른 답            → 본문만으로 답이 안 정해진다 (조건 부족)
      · 준 값을 갈아도 답 그대로 → 그 값은 갈아도 쌍둥이 (변형 불가)

⚠ AI 가 쓴 풀이는 읽지 않는다. 조건만 받아서 처음부터 다시 세운다.
   출제자와 채점자가 같으면 검산이 아니다.

의존성 없음 (numpy·scipy 를 안 쓴다 — 이 PC 에 없다).
"""
import math, random, re

TOL = 1e-9
MAXIT = 220


# ══════════════════════════════════════════════════════════
#  아주 작은 최소제곱 풀이기 (Levenberg–Marquardt)
# ══════════════════════════════════════════════════════════
def _solve_lin(A, b):
    """가우스 소거. A 는 n×n 리스트, 실패하면 None."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-14:
            return None
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        for j in range(c, n + 1):
            M[c][j] /= pv
        for r in range(n):
            if r == c:
                continue
            f = M[r][c]
            if f:
                for j in range(c, n + 1):
                    M[r][j] -= f * M[c][j]
    return [M[i][n] for i in range(n)]


def least_squares(res, x0, maxit=MAXIT):
    """res(x) -> 잔차 리스트. (해, 잔차제곱합) 을 돌려준다."""
    x = list(x0)
    n = len(x)
    lam = 1e-3
    r = res(x)
    f = sum(v * v for v in r)
    for _ in range(maxit):
        if f < TOL:
            break
        # 수치 야코비
        J = []
        for i in range(n):
            h = 1e-7 * max(1.0, abs(x[i]))
            xp = x[:]; xp[i] += h
            rp = res(xp)
            J.append([(rp[k] - r[k]) / h for k in range(len(r))])
        # (JᵀJ + λI) δ = -Jᵀr
        JtJ = [[sum(J[i][k] * J[j][k] for k in range(len(r))) for j in range(n)]
               for i in range(n)]
        Jtr = [sum(J[i][k] * r[k] for k in range(len(r))) for i in range(n)]
        ok = False
        for _try in range(12):
            A = [[JtJ[i][j] + (lam * (JtJ[i][i] + 1e-9) if i == j else 0.0)
                  for j in range(n)] for i in range(n)]
            d = _solve_lin(A, [-v for v in Jtr])
            if d is None:
                lam *= 10; continue
            xn = [x[i] + d[i] for i in range(n)]
            rn = res(xn)
            fn = sum(v * v for v in rn)
            if fn < f:
                x, r, f = xn, rn, fn
                lam = max(lam * 0.3, 1e-12)
                ok = True
                break
            lam *= 10
        if not ok:
            break
    return x, f


# ══════════════════════════════════════════════════════════
#  조건 언어
# ══════════════════════════════════════════════════════════
#  한 줄은 둘 중 하나다.
#     술어      parallel(A,D, B,C)   midpoint(M, C,D)   collinear(A,B,C)
#     등식      area(A,B,M) = 28     angle(D,F,C) = 30     len(A,B) = len(A,C)
#  점 이름은 공백·쉼표·괄호가 아닌 아무 글자나 된다 (O' 도 된다).
FUNCS_DOC = """
쓸 수 있는 것
  값을 주는 함수   len(P,Q)  angle(P,Q,R)  area(P,Q,R)  x(P)  y(P)
  술어             parallel(A,B, C,D)   perp(A,B, C,D)   midpoint(M, A,B)
                   collinear(A,B,C)     oncircle(P, O, r)   eqlen(A,B, C,D)
  등식             <식> = <식>       (양쪽에 위 함수와 + - * / ( ) 숫자 사용)
  각은 도(°) 단위.  r 은 반지름 변수 이름(점이 아닌 스칼라).
"""


class Model:
    def __init__(self, points, scalars=()):
        self.pts = list(points)
        self.scl = list(scalars)
        self.idx = {}
        k = 0
        for p in self.pts:
            self.idx[p] = k; k += 2
        self.sidx = {}
        for s in self.scl:
            self.sidx[s] = k; k += 1
        self.n = k

    def P(self, x, name):
        i = self.idx[name]
        return (x[i], x[i + 1])

    def S(self, x, name):
        return x[self.sidx[name]]


def _args(s):
    """괄호 안을 쉼표로 나눈다 (중첩 괄호 고려)."""
    out, d, cur = [], 0, ''
    for c in s:
        if c == ',' and d == 0:
            out.append(cur.strip()); cur = ''
        else:
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
            cur += c
    if cur.strip():
        out.append(cur.strip())
    return out


_CALL_RE = re.compile(r'^([A-Za-z_][A-Za-z_0-9]*)\((.*)\)$')


class _M:
    def __init__(self, a, b):
        self._a, self._b = a, b

    def group(self, i):
        return self._a if i == 1 else self._b


def CALL_match(e):
    """'area(A,B,C)' 는 호출, 'area(A,B,C) + area(D,E,F)' 는 아니다.
    맨 끝 ')' 가 첫 '(' 의 짝일 때만 호출로 본다."""
    m = _CALL_RE.match(e)
    if not m:
        return None
    d = 0
    body = e[len(m.group(1)):]
    for i, c in enumerate(body):
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d == 0:
                return _M(m.group(1), m.group(2)) if i == len(body) - 1 else None
    return None


class CALL:
    match = staticmethod(CALL_match)


# 좌표에서 곧바로 값이 나오는 것들. sqrt·pi 는 여기 없다 — eval 에 맡긴다.
GEO = ('len', 'angle', 'area', 'x', 'y')
# 삼각비. 각은 **도(°)** 로 받는다 — 조건도 답도 학생이 쓰는 단위 그대로여야 한다.
TRIG = {'sin': math.sin, 'cos': math.cos, 'tan': math.tan}
PRIM = set(GEO) | set(TRIG)
_ONECALL = re.compile(r'([A-Za-z_][A-Za-z_0-9]*)\(([^()]*)\)')
SAFE = {'sqrt': math.sqrt, 'pi': math.pi, 'abs': abs}


def make_eval(model):
    """식 문자열 → (x -> 값) 함수."""
    def prim(f, a, x, depth):
        if f == 'len':
            (ax, ay), (bx, by) = model.P(x, a[0]), model.P(x, a[1])
            return math.hypot(bx - ax, by - ay)
        if f == 'angle':
            (px, py), (qx, qy), (rx, ry) = (model.P(x, a[0]), model.P(x, a[1]),
                                            model.P(x, a[2]))
            u, v = (px - qx, py - qy), (rx - qx, ry - qy)
            nu, nv = math.hypot(*u) or 1e-12, math.hypot(*v) or 1e-12
            c = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
            return math.degrees(math.acos(c))
        if f == 'area':
            (ax, ay), (bx, by), (cx, cy) = (model.P(x, a[0]), model.P(x, a[1]),
                                            model.P(x, a[2]))
            return abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2.0
        if f in ('x', 'y'):
            p = model.P(x, a[0])
            return p[0] if f == 'x' else p[1]
        # 삼각비의 속은 각도를 나타내는 **식**이다 — 다시 풀어서 값을 낸다
        return TRIG[f](math.radians(ev(','.join(a), x, depth + 1)))

    def ev(expr, x, depth=0):
        e = str(expr).strip()
        if depth > 12:
            raise RecursionError('식이 너무 깊다: %s' % e[:40])
        m = CALL.match(e)
        if m and m.group(1) in PRIM:
            return prim(m.group(1), _args(m.group(2)), x, depth)
        if e in model.sidx:                       # 반지름처럼 점이 아닌 미지수
            return model.S(x, e)
        # 안쪽 괄호부터 값으로 바꿔 나간다.
        #  ⚠ sin(angle(A,B,C)) 처럼 겹쳐 있으면 '[^()]*' 한 번으로는 안 잡힌다.
        #    sqrt(3) 같은 것은 건드리지 말고 넘겨 eval 이 계산하게 둔다.
        e2, pos = e, 0
        for _ in range(60):
            m2 = _ONECALL.search(e2, pos)
            if not m2:
                break
            if m2.group(1) not in PRIM:
                pos = m2.start() + 1
                continue
            v = prim(m2.group(1), _args(m2.group(2)), x, depth)
            e2 = e2[:m2.start()] + repr(v) + e2[m2.end():]
            pos = 0
        for s in model.sidx:
            e2 = re.sub(r'(?<![A-Za-z_0-9])%s(?![A-Za-z_0-9])' % re.escape(s),
                        repr(model.S(x, s)), e2)
        return float(eval(e2, {'__builtins__': {}}, dict(SAFE)))
    return ev


def residuals_of(model, lines):
    """조건 목록 → (x -> 잔차 리스트)."""
    ev = make_eval(model)
    plan = []
    for raw in lines:
        s = str(raw).strip()
        if not s or s.startswith('#'):
            continue
        # ⚠ 부등식(k > 0 처럼 '값의 범위')을 모르는 조건으로 버리면 문항 전체가 검산 못 함이 된다.
        #   등식이 아니라 **한쪽으로만 미는 벌점**으로 받는다 — 만족하면 0, 어기면 어긴 만큼.
        m_ineq = re.match(r'^(.*?)(>=|<=|=>|=<|>|<)(.*)$', s)
        if m_ineq and '=' not in m_ineq.group(1) and '=' not in m_ineq.group(3):
            L, op, R = m_ineq.group(1), m_ineq.group(2), m_ineq.group(3)
            plan.append(('ge' if op[0] == '>' else 'le', L, R))
            continue
        if '=' in s and not CALL.match(s):
            L, R = s.split('=', 1)
            plan.append(('eq', L, R))
            continue
        m = CALL.match(s)
        if m and m.group(1) in ('parallel', 'perp', 'midpoint', 'collinear',
                                'oncircle', 'eqlen'):
            plan.append((m.group(1), _args(m.group(2)), None))
        elif '=' in s:
            L, R = s.split('=', 1)
            plan.append(('eq', L, R))
        else:
            plan.append(('bad', s, None))

    def res(x):
        out = []
        for kind, a, b in plan:
            if kind == 'eq':
                out.append(ev(a, x) - ev(b, x))
            elif kind == 'ge':                       # a >= b : 어긴 만큼만 벌점
                out.append(min(0.0, ev(a, x) - ev(b, x)))
            elif kind == 'le':
                out.append(max(0.0, ev(a, x) - ev(b, x)))
            elif kind == 'parallel':
                (ax, ay), (bx, by) = model.P(x, a[0]), model.P(x, a[1])
                (cx, cy), (dx, dy) = model.P(x, a[2]), model.P(x, a[3])
                out.append((bx - ax) * (dy - cy) - (by - ay) * (dx - cx))
            elif kind == 'perp':
                (ax, ay), (bx, by) = model.P(x, a[0]), model.P(x, a[1])
                (cx, cy), (dx, dy) = model.P(x, a[2]), model.P(x, a[3])
                out.append((bx - ax) * (dx - cx) + (by - ay) * (dy - cy))
            elif kind == 'midpoint':
                (mx, my) = model.P(x, a[0])
                (ax, ay), (bx, by) = model.P(x, a[1]), model.P(x, a[2])
                out += [mx - (ax + bx) / 2, my - (ay + by) / 2]
            elif kind == 'collinear':
                (ax, ay), (bx, by), (cx, cy) = (model.P(x, a[0]), model.P(x, a[1]),
                                                model.P(x, a[2]))
                out.append((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
            elif kind == 'eqlen':
                (ax, ay), (bx, by) = model.P(x, a[0]), model.P(x, a[1])
                (cx, cy), (dx, dy) = model.P(x, a[2]), model.P(x, a[3])
                out.append(math.hypot(bx - ax, by - ay) - math.hypot(dx - cx, dy - cy))
            elif kind == 'oncircle':
                (px, py) = model.P(x, a[0])
                (ox, oy) = model.P(x, a[1])
                out.append(math.hypot(px - ox, py - oy) - ev(a[2], x))
        return out
    bad = [a for k, a, _ in plan if k == 'bad']
    return res, len(plan), bad


# ══════════════════════════════════════════════════════════
#  검산
# ══════════════════════════════════════════════════════════
ARITY = {'len': 2, 'angle': 3, 'area': 3, 'x': 1, 'y': 1, 'parallel': 4, 'perp': 4,
         'midpoint': 3, 'collinear': 3, 'eqlen': 4, 'oncircle': 3,
         'sin': 1, 'cos': 1, 'tan': 1}
_ANYCALL = re.compile(r'([A-Za-z_][A-Za-z_0-9]*)\(([^()]*)\)')


def normalize(spec):
    """AI 가 쓴 명세를 너그럽게 받아들인다.
    실측: angle(DBC) 처럼 쉼표 없이 쓰거나, 점 이름을 붙여 쓰는 일이 잦다."""
    pts = set(spec.get('points') or [])

    def fix(m):
        f, inner = m.group(1), m.group(2)
        need = ARITY.get(f)
        if not need:
            return m.group(0)
        args = [a.strip() for a in inner.split(',') if a.strip()]
        if len(args) == need:
            return '%s(%s)' % (f, ','.join(args))
        exp = []
        for a in args:
            if a in pts or not a:
                exp.append(a)
            elif all(ch in pts for ch in a):          # 'DBC' → D,B,C
                exp += list(a)
            else:
                exp.append(a)
        if len(exp) == need:
            return '%s(%s)' % (f, ','.join(exp))
        return m.group(0)

    out = dict(spec)
    out['constraints'] = [_ANYCALL.sub(fix, str(c)) for c in (spec.get('constraints') or [])]
    out['ask'] = _ANYCALL.sub(fix, str(spec.get('ask') or ''))
    return _autodeclare(out)


# 이름을 쓰면서 scalars 에 넣는 것을 잊는 일이 잦다 (실측: "NameError: name 'x' is not defined").
# 홀로 선 소문자 이름은 미지수로 받아 준다 — 점 이름은 대문자라 헷갈리지 않는다.
_RESERVED = set(ARITY) | {'sqrt', 'pi', 'abs'}
_IDENT = re.compile(r'(?<![A-Za-z_0-9])([A-Za-z_][A-Za-z_0-9]*)\s*(\()?')


def _autodeclare(spec):
    pts = set(spec.get('points') or [])
    scl = list(spec.get('scalars') or [])
    seen = set(scl)
    add = []
    for txt in list(spec.get('constraints') or []) + [spec.get('ask') or '']:
        for m in _IDENT.finditer(str(txt)):
            nm = m.group(1)
            if m.group(2) or nm in _RESERVED or nm in pts or nm in seen:
                continue          # 함수 이름·점 이름·이미 선언된 것은 넘어간다
            if len(nm) > 3 or not nm.islower():
                continue          # 소문자 짧은 이름만 (a·k·r·x·ab …)
            seen.add(nm)
            add.append(nm)
    if add:
        spec = dict(spec)
        spec['scalars'] = scl + add
        spec['_autodeclared'] = add
    return spec


def check(spec, trials=10, seed=12345, rel=2e-3):
    try:
        return _check(spec, trials, seed, rel)
    except Exception as e:
        # 어떤 경우에도 죽지 않는다 — 모르면 '검산 못 함' 이라고 말한다
        return {'verdict': '검산 못 함', 'why': '%s: %s' % (type(e).__name__, e)}


def _check(spec, trials=10, seed=12345, rel=2e-3):
    """spec = {points, scalars, constraints, ask}
    돌려주는 것: verdict · value · detail"""
    spec = normalize(spec)
    pts = spec.get('points') or []
    scl = spec.get('scalars') or []
    cons = spec.get('constraints') or []
    ask = (spec.get('ask') or '').strip()
    if not pts or not ask:
        return {'verdict': '검산 못 함', 'why': '점 목록이나 구할 것이 없음'}

    model = Model(pts, scl)
    res, ncons, bad = residuals_of(model, cons)
    if bad:
        return {'verdict': '검산 못 함', 'why': '모르는 조건: %s' % '; '.join(bad[:3])}
    ev = make_eval(model)

    rng = random.Random(seed)
    # 출발점: 도형 명세의 좌표가 있으면 그 언저리에서 시작한다.
    # 같은 조건이라도 점을 어느 쪽에 두느냐로 답이 달라지므로(배치 분기),
    # 무작위로만 뽑으면 서로 다른 배치의 답이 섞여 '안 정해짐' 이 된다.
    start = spec.get('start') or {}
    base, sc = [], 1.0
    if start:
        xs = [float(v[0]) for v in start.values() if v]
        ys = [float(v[1]) for v in start.values() if v]
        if xs:
            sc = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    vals, svals, solved, fails = [], [], 0, 0
    for t in range(trials):
        x0 = []
        for p in pts:
            if p in start:
                j = 0.0 if t == 0 else 0.12 * sc
                x0 += [float(start[p][0]) + rng.uniform(-j, j),
                       float(start[p][1]) + rng.uniform(-j, j)]
            else:
                x0 += [rng.uniform(-sc, sc), rng.uniform(-sc, sc)]
        for _ in scl:
            x0.append(rng.uniform(0.05 * sc, 0.6 * sc))
        x, f = least_squares(res, x0)
        # ⚠ 크기에 견주어 본다. 도형이 쪼그라들면 잔차도 같이 작아져 거짓 통과가 난다
        #   (실측: 정삼각형+50° 라는 모순이 '확인함' 으로 통과했다)
        span = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                span = max(span, math.dist(model.P(x, pts[i]), model.P(x, pts[j])))
        if span < 1e-2:
            fails += 1
            continue
        # ⚠ 1e-6 은 잉여 조건(좌표 고정 넷)이 있으면 수렴이 문턱 바로 위(1e-10)에서
        #   멈춰 멀쩡한 배치를 다 버렸다. 모순 잔차는 1e-2 이상이라 1e-5 도 여유가 크다.
        if f > (1e-5 * max(1.0, span)) ** 2 * max(1, ncons):
            fails += 1
            continue
        degen = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if math.dist(model.P(x, pts[i]), model.P(x, pts[j])) < 1e-3 * span:
                    degen = True
        if degen:
            fails += 1
            continue
        try:
            vals.append(ev(ask, x))
            # 답이 '{2a} over {1-a^2}' 처럼 문자식이면 그 문자의 값도 있어야 견줄 수 있다
            svals.append({nm: model.S(x, nm) for nm in scl})
            solved += 1
        except Exception as e:
            return {'verdict': '검산 못 함', 'why': '구할 것을 계산 못 함: %s' % e}

    if solved == 0:
        return {'verdict': '조건 모순', 'why': '조건을 만족하는 배치를 %d번 다 못 찾음' % trials,
                'tries': trials}
    lo, hi = min(vals), max(vals)
    spread = (hi - lo) / max(1e-9, abs(sum(vals) / len(vals)))
    if spread > rel:
        return {'verdict': '답이 안 정해짐', 'value': None, 'solved': solved,
                'why': '배치마다 답이 다름 (%.6g ~ %.6g)' % (lo, hi),
                'range': [lo, hi]}
    v = sum(vals) / len(vals)
    # 배치마다 값이 같은 미지수만 내보낸다 — 자유롭게 움직이는 것(비례상수 k 등)은 대입해 봐야 뜻이 없다
    fixed = {}
    for nm in scl:
        xs = [d[nm] for d in svals]
        if max(xs) - min(xs) <= rel * max(1e-9, abs(sum(xs) / len(xs))):
            fixed[nm] = sum(xs) / len(xs)
    return {'verdict': '확인함', 'value': v, 'solved': solved, 'tries': trials,
            'spread': spread, 'vars': fixed}


def sensitivity(spec, given, trials=6):
    """준 값을 흔들어 답이 따라 움직이는지 본다.
    given = {'조건줄 안의 숫자 위치': ...} 대신, 조건 문자열을 통째로 갈아 끼운다.
    돌려주는 것: [(바꾼값, 답)] — 답이 안 변하면 그 값은 갈아도 쌍둥이."""
    out = []
    for gv in given:
        sp = dict(spec)
        sp['constraints'] = [c.replace(gv['from'], gv['to']) for c in spec['constraints']]
        r = check(sp, trials=trials)
        out.append({'to': gv['to'], 'verdict': r['verdict'], 'value': r.get('value')})
    return out
