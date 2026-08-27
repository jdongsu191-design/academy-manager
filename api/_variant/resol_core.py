# -*- coding: utf-8 -*-
"""해설 재작성 — pt_resol(헤맨 해설) · pt_resol2(범위 밖 도구) 의 서버판.

⚠ 답이 검산으로 확인된 것만 다시 쓴다. 답이 미덥지 않은데 해설만 매끄럽게 만들면
  '그럴듯하지만 틀린 해설' 이 되어 검산 이전보다 나빠진다. (호출부가 지킨다)
⚠ 다시 써도 헤매면 원래 것을 둔다 — 바꿔서 나빠지면 안 된다. (여기서 지킨다)
"""
import json, re
from vg_spec import _gemini
from pt_grade import block as grade_block, TOOLS, BANNED, OVER_PAT, grade_of
from clean_core import sol_flag
from gen_core import tidy_field, stmt_parts

PROMPT_RESOL = """아래 수학 문제의 **답은 이미 확인되었다.**
프로그램이 조건을 좌표로 풀어 같은 답에 이르렀으므로 답은 맞다.

문제
─────────────────────────
@STMT@
─────────────────────────
확인된 답 : @ANS@
@CURR@
할 일: **이 답에 이르는 풀이를 처음부터 다시, 깔끔하게 써라.**

지켜야 할 것
1. **답을 찾으려 하지 마라.** 답은 위에 있다. 거기까지 가는 길만 보여라.
2. 막혔다는 말, 다시 해 보겠다는 말, 스스로 고치는 말을 **쓰지 마라.**
   ('이대로는', '너무 복잡하니', '정정:', '다시 계산하면' 같은 말은 학생용 해설에 있으면 안 된다)
3. **번호를 붙여 단계로** 쓰되 한 단계는 한 줄로 짧게. 6~10단계면 넉넉하다.
   마지막 단계는 반드시 '따라서 …이다.' 로 답을 적으며 끝낸다.
4. **수식은 한글(HWP) 수식 스크립트로 쓰고 반드시 $ … $ 로 감싼다.**
   LaTeX(\\frac, \\triangle, \\sqrt)를 쓰지 마라. $ 밖에 rm·bar{ }·over·sqrt·DEG·ANGLE 이
   하나도 남으면 안 된다.
   보기) $ overline{{rm{AB}} it } = 3 $ , $ tan 60 DEG = root3 $ , $ {3} over {5} $
5. insight 는 이 문제를 푸는 실마리 두세 줄. 풀이를 되풀이하지 말고 **어디를 봐야 하는지**를 적어라."""

SCHEMA_RESOL = {'type': 'object', 'properties': {
    'insight': {'type': 'string'}, 'solution': {'type': 'string'}},
    'required': ['insight', 'solution']}

PROMPT_CURR = """아래 수학 문제의 **답은 이미 확인되었다.** 프로그램이 조건을 좌표로 풀어 같은 답에 이르렀다.

문제
─────────────────────────
@STMT@
─────────────────────────
확인된 답 : @ANS@

지금 있는 해설은 답은 맞지만 **@OVER@ 을(를) 써서** 이 학년 학생이 읽을 수 없다.

할 일: **@GRADE@ 학생이 이미 배운 것만으로 같은 답에 이르는 풀이를 다시 써라.**

@GRADE@ 이(가) 쓸 수 있는 것
@TOOLS@

쓰면 안 되는 것
  @BANNED@

지켜야 할 것
1. **답을 찾으려 하지 마라.** 답은 위에 있다. 거기까지 가는 길만 보여라.
2. 막혔다는 말, 다시 해 보겠다는 말, 스스로 고치는 말을 **쓰지 마라.**
3. **번호를 붙여 단계로** 쓰되 한 단계는 한 줄로 짧게. 마지막은 '따라서 …이다.' 로 끝낸다.
4. **수식은 한글(HWP) 수식 스크립트로 쓰고 반드시 $ … $ 로 감싼다.**
   LaTeX 를 쓰지 마라. $ 밖에 rm·bar{ }·over·sqrt·DEG·ANGLE 이 남으면 안 된다.
5. insight 는 실마리 두세 줄 — **길을 여는 한 수**를 적어라.

⚠ **정말로 위 도구만으로는 풀 수 없는 문제라면** possible 을 false 로 두고
   why_not 에 이유를 한 줄로 적어라. 억지로 지어내지 마라 — 틀린 해설이 제일 나쁘다."""

SCHEMA_CURR = {'type': 'object', 'properties': {
    'possible': {'type': 'boolean'}, 'why_not': {'type': 'string'},
    'insight': {'type': 'string'}, 'solution': {'type': 'string'}},
    'required': ['possible', 'why_not', 'insight', 'solution']}


def _call(txt, schema, temp, max_out=12000, think=3072):
    d = _gemini({'contents': [{'parts': [{'text': txt}]}],
                 'generationConfig': {'temperature': temp, 'maxOutputTokens': max_out,
                                      'responseMimeType': 'application/json',
                                      'responseSchema': schema,
                                      'thinkingConfig': {'thinkingBudget': think}}},
                timeout=48)
    c = (d.get('candidates') or [{}])[0]
    t = (((c.get('content') or {}).get('parts') or [{}])[0]).get('text')
    if not t:
        raise RuntimeError('빈 응답 (%s)' % c.get('finishReason'))
    return json.loads(t)


def _over(txt, grade):
    return [n for n, p in OVER_PAT[grade].items() if re.search(p, txt)]


def rewrite(statement, answer, grade_label, temp=0.2):
    """헤맨 해설 다시 쓰기. 다시 써도 헤매면 kept."""
    txt = (PROMPT_RESOL.replace('@STMT@', statement).replace('@ANS@', answer)
           .replace('@CURR@', grade_block(grade_label)))
    r = _call(txt, SCHEMA_RESOL, temp)
    new_sol = tidy_field(r.get('solution'))
    fl = sol_flag(new_sol)
    if fl:
        return {'kept': True, 'why': '다시 써도 ' + fl}
    return {'kept': False, 'insight': tidy_field(r.get('insight')),
            'solution': new_sol, 'sol_flag': ''}


def rewrite_curr(statement, answer, over, grade_label, temp=0.25):
    """범위 밖 도구를 그 학년 도구로. 못 하면 kept + why."""
    g = grade_of(grade_label) or '중3'
    txt = PROMPT_CURR
    for k, v in (('@STMT@', statement), ('@ANS@', answer),
                 ('@OVER@', ' · '.join(over)), ('@GRADE@', g),
                 ('@TOOLS@', TOOLS[g]), ('@BANNED@', BANNED[g])):
        txt = txt.replace(k, v)
    r = _call(txt, SCHEMA_CURR, temp, max_out=16000, think=4096)
    if not r.get('possible'):
        return {'kept': True, 'why': '이 학년 도구로 못 씀: ' + (r.get('why_not') or '')[:120]}
    new_sol = tidy_field(r.get('solution'))
    new_ins = tidy_field(r.get('insight'))
    still = _over(new_sol + ' ' + new_ins, g)
    fl = sol_flag(new_sol)
    if still or fl:
        return {'kept': True, 'why': '다시 써도 ' + (' · '.join(still) or fl)}
    return {'kept': False, 'insight': new_ins, 'solution': new_sol,
            'sol_flag': '', 'over': []}
