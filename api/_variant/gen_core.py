# -*- coding: utf-8 -*-
"""변형 생성 — pt_full3 의 프롬프트를 **등급 하나씩** 받도록 바꾼 것.

원판은 한 호출로 V1·V2·V3 을 다 받았다(호출당 1~4분). 서버는 60초 제한이라
등급 하나씩 받는다. 등급 정의·규칙·본보기·학년 범위는 원판 그대로다.
받은 뒤 손질(clean_core)과 표 달기(sol_flag)·범위 검사(pt_grade)까지 여기서 한다.
"""
import json, re, time
from vg_spec import _gemini
from pt_grade import block as grade_block, OVER_PAT, grade_of
from clean_core import balance, wrap_math, sol_flag
from eq_fix import fix_text
from hwpx_parse import eq_to_latex
from shots import SHOTS

RULES = """너는 학원 수학 교재를 만드는 사람이다. 아래 **원문**에서 변형문제 **하나**를 만든다.

등급 (이 정의를 그대로 따른다) — 이번에 만들 것은 **@LEVEL@** 하나뿐이다.
  V1  푸는 길은 원문과 같고 **계산이 무거워진다**
  V2  조건은 원문의 것을 쓰되 **묻는 대상이 달라진다**
  V3  직접 준 조건을 **간접 조건으로 바꾼다** — 조건을 푸는 단계가 하나 붙는다

@SHOTS@
@CURR@
원문
─────────────────────────
학년·단원 : @GRADE@
유형      : @TYPE@   배점 : @POINTS@
본문      : @STMT@
정답      : @ANSWER@
(그림이 있으면 이미지로 함께 준다)
─────────────────────────
@RETRY@
지켜야 할 것
1. **수식은 한글(HWP) 수식 스크립트로 쓰고 반드시 $ … $ 로 감싼다.**
   본보기의 표기를 그대로 흉내 내라. LaTeX(\\frac, \\triangle)를 쓰지 마라.
   $ 밖에는 수식 기호가 하나도 남으면 안 된다.
2. **답을 반드시 직접 풀어 확인하라.** 조건이 모순이거나 답이 결정되지 않으면 만들지 마라.
   ⚠ 만든 문제는 프로그램이 조건을 좌표로 풀어 **답을 다시 구해 대조한다.**
   본문에 적힌 조건만으로 답이 하나로 정해져야 한다.
3. **숫자는 계산이 지저분해지지 않게 고른다.** 답은 정수가 가장 좋고,
   분수면 분모가 작게, 무리수면 $root2$·$root3$ 정도로 끝나게 하라.
4. **그림을 글로 대신하지 마라. 그림이 보여 주던 것은 본문에 글로 적어라.**
   그림에만 적혀 있던 값(길이·각·기호)과 **배치**(어떤 점이 어떤 변 위에 있는지,
   직각이 어느 꼭짓점인지, 교점의 이름)는 반드시 **본문 문장 안에** 다시 적어라.
   ⚠ 원문이 '∠x' 처럼 그림에만 표시된 기호를 묻는다면,
     변형에서는 그 각을 **세 꼭짓점 이름으로** 바꿔 부르거나 본문에서 정의하라.
5. **바꿀 수 있는 수치가 없으면** 억지로 만들지 말고 statement 를 빈 문자열로 두고
   idea 에 '만들 수 없음 — 이유' 를 적어라. 원문을 그대로 베끼는 것은 실패로 친다.
6. solution 은 번호 붙인 단계별 풀이(마지막은 '따라서 …이다.'), insight 는 실마리 두세 줄,
   idea 는 원문 대비 무엇을 갈았고 손이 어디서 늘었는지.
7. think(발상) 1~5, calc(계산) 1~6 으로 난이도를 매기고,
   base_think·base_calc 에는 **원문**의 난이도를 매겨라.
8. 그림은 네가 그리지 않는다. 사람이 그린다. 대신 다음 둘만 적어라.
   figure_need : 'none'(그림이 필요 없다) / 'edit'(원문 그림의 수치만 고치면 된다)
                 / 'new'(새로 그려야 한다)
   figure_note : 'edit' 이면 무엇을 무엇으로 고칠지, 'new' 면 무엇을 어떻게 그릴지를
                 **한두 줄로** 적어라. 점 이름·길이·각도를 빠짐없이 넣어라.
                 ⚠ **반드시 한국어로** 써라. 선생님이 읽고 그린다.
9. **수식은 빠짐없이 $ … $ 안에 넣어라.** $ 밖에 rm·bar{ }·over·sqrt·DEG·ANGLE 같은
   한글 수식 낱말이 하나라도 남으면 한/글에 그 글자가 그대로 찍힌다(실제로 찍혔다)."""

SCHEMA = {'type': 'object', 'properties': {
    'base_think': {'type': 'integer'}, 'base_calc': {'type': 'integer'},
    'statement': {'type': 'string'}, 'answer': {'type': 'string'},
    'solution': {'type': 'string'}, 'insight': {'type': 'string'},
    'idea': {'type': 'string'},
    'figure_need': {'type': 'string', 'enum': ['none', 'edit', 'new']},
    'figure_note': {'type': 'string'},
    'think': {'type': 'integer'}, 'calc': {'type': 'integer'}},
    'required': ['base_think', 'base_calc', 'statement', 'answer', 'solution',
                 'insight', 'idea', 'figure_need', 'figure_note', 'think', 'calc']}

RETRY_HEAD = """
⚠ 먼저 만든 변형이 검산에서 걸렸다. 같은 잘못을 되풀이하지 마라.
%s
검산은 **본문에 적힌 조건만** 좌표로 옮겨 답을 다시 구한다.
따라서 답이 어긋났다면 (가) 네 계산이 틀렸거나 (나) 조건을 본문에 덜 적은 것이다.
처음부터 다시 만들되, 걸린 곳을 특히 손보아라.
"""


def tidy_field(s):
    s, _ = balance(s or '')
    s, _, _ = fix_text(s)
    s, _ = wrap_math(s)
    return s


def stmt_parts(s):
    """$ … $ 본문을 화면용 조각으로 — 파싱 화면과 같은 모양."""
    parts = []
    for i, tok in enumerate(re.split(r'\$', s or '')):
        if not tok:
            continue
        if i % 2:
            try:
                parts.append({'eq': tok, 'latex': eq_to_latex(tok)})
            except Exception:
                parts.append({'t': tok})
        else:
            parts.append({'t': tok.replace('`', '')})
    return parts


def make_one(prob, grade_label, level, png_b64=None, retry_note='', temp=0.35):
    """등급 하나를 만들어 손질까지 마친 변형 dict 를 돌려준다."""
    pts = prob.get('points')
    txt = RULES
    for k, v in (('@SHOTS@', SHOTS), ('@LEVEL@', level),
                 ('@GRADE@', grade_label), ('@TYPE@', prob.get('type') or ''),
                 ('@POINTS@', ('A %s / B %s' % (pts.get('A'), pts.get('B')))
                  if isinstance(pts, dict) else str(pts or '')),
                 ('@STMT@', (prob.get('statement') or '').replace('⟪', '$').replace('⟫', '$')),
                 ('@ANSWER@', '$%s$' % (prob.get('answer_script') or '')),
                 ('@CURR@', grade_block(grade_label)),
                 ('@RETRY@', (RETRY_HEAD % retry_note) if retry_note else '')):
        txt = txt.replace(k, v)
    parts = []
    if png_b64:
        parts.append({'inlineData': {'mimeType': 'image/png', 'data': png_b64}})
    parts.append({'text': txt})
    t0 = time.time()
    d = _gemini({'contents': [{'parts': parts}],
                 'generationConfig': {'temperature': temp, 'maxOutputTokens': 16000,
                                      'responseMimeType': 'application/json',
                                      'responseSchema': SCHEMA,
                                      'thinkingConfig': {'thinkingBudget': 4096}}},
                timeout=48)
    c = (d.get('candidates') or [{}])[0]
    t = (((c.get('content') or {}).get('parts') or [{}])[0]).get('text')
    if not t:
        raise RuntimeError('빈 응답 (%s)' % c.get('finishReason'))
    r = json.loads(t)

    v = {'level': level, 'sec': round(time.time() - t0, 1),
         'base_think': r.get('base_think'), 'base_calc': r.get('base_calc'),
         'think': r.get('think'), 'calc': r.get('calc'),
         'figure_need': r.get('figure_need') or 'none',
         'figure_note': tidy_field(r.get('figure_note'))}
    for f in ('statement', 'answer', 'solution', 'insight', 'idea'):
        v[f] = tidy_field(r.get(f))
    if not (v['statement'] or '').strip():
        v['impossible'] = (v.get('idea') or '')[:200]
        return v
    v['sol_flag'] = sol_flag(v['solution'])
    g = grade_of(grade_label)
    if g:
        txt_all = ' '.join(str(v.get(f) or '') for f in ('solution', 'insight'))
        v['over'] = [n for n, p in OVER_PAT[g].items() if re.search(p, txt_all)]
    else:
        v['over'] = []
    v['parts'] = stmt_parts(v['statement'])
    return v
