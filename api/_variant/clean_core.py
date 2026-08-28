# -*- coding: utf-8 -*-
"""조립 전 손질 — 한/글이 읽을 수 있는 글로 되돌리고, 못 믿을 해설에 표를 단다.

하는 일
  ① LaTeX 잔재를 한글 수식으로 (\\frac → over, \\sqrt → sqrt …). 못 바꾸면 역슬래시만 뗀다
  ② $ 짝을 맞춘다 — 하나가 남으면 그 뒤가 통째로 수식이 되어 본문이 사라진다
  ③ **헤맨 해설**을 찾아낸다.
     실측: 지난 문제집 26쪽에 모델이 풀다 만 혼잣말이 그대로 찍혔다.
     ('이대로는…', '너무 복잡하니', 결론 없이 끊김)
     지우지 않고 **표를 달아** 사람이 보게 한다 — 답 자체는 검산으로 따로 확인된다.
"""
import sys, json, re
from collections import Counter
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from eq_fix import fix_text, dropped

FIELDS = ('statement', 'answer', 'solution', 'insight', 'idea', 'figure_note')

# 모델이 풀다 막혔을 때 흘리는 말투 (실측에서 모은 것)
WANDER = re.compile(
    r'이대로는|너무 복잡|계산이 복잡|다시 계산|다시 풀|잘못|틀렸|아마도|'
    r'음,|잠깐|어렵습니다|불가능|맞지 않|모순이 생기|정확하지 않|'
    r'라고 가정하면.{0,20}맞지|검토가 필요')
# 끝맺음이 있는가
ENDED = re.compile(r'따라서|그러므로|답은|이다\.\s*$|구하는 값|∴')


# $ 밖으로 새어 나온 한글 수식 낱말 — 그대로 두면 한/글에 글자로 찍힌다
#  실측: '$BC$= 5 cm ,rm bar{AC} =8cm' 가 "BC= 5 cm ,rm bar{AC} =8cm" 로 인쇄됐다
MATHTOK = re.compile(r'(?<![A-Za-z])(rm|it|ita|bar|over|sqrt|root|times|cdot|'
                     r'DEG|ANGLE|TRIANGLE|LEFT|RIGHT|PERP|prime|'
                     # 그리스 낱말과 THEREFORE 류도 글자로 찍힌다 (실측 'alpha는', 'beta이므로')
                     r'alpha|beta|gamma|theta|lambda|mu|pi|omega|THEREFORE|BECAUSE'
                     r')(?![A-Za-z])'
                     # 'rmB'·'RMA' 처럼 지시어가 대문자에 붙은 꼴 (실측 '점 RMB가')
                     r'|(?<![A-Za-z])(?:rm|RM|it|IT|bf|BF)(?=[A-Z])'
                     r'|\^\s*\{|_\s*\{')
TRAIL = ' \t,.·;:'


def wrap_math(t):
    """한글이 아닌 토막 가운데 수식 낱말이 든 것을 $ 로 감싼다."""
    out, n = [], 0
    for i, part in enumerate(str(t or '').split('$')):
        if i % 2:                                  # 이미 수식 안 — 건드리지 않는다
            out.append(part)
            continue
        buf, last = [], 0
        for m in re.finditer(r'[^가-힣]+', part):
            seg = m.group(0)
            if not MATHTOK.search(seg):
                continue
            core = seg.strip(TRAIL)
            if not core:
                continue
            j = m.start() + seg.index(core)
            buf.append(part[last:j])
            buf.append('$%s$' % core)
            last = j + len(core)
            n += 1
        buf.append(part[last:])
        out.append(''.join(buf))
    return '$'.join(out), n


def balance(t):
    """$ 가 홀수면 마지막 것을 떼어 낸다 (붙이는 것보다 잃는 글이 적다)."""
    if (t or '').count('$') % 2 == 0:
        return t, False
    i = t.rfind('$')
    return t[:i] + t[i + 1:], True


def sol_flag(sol):
    s = (sol or '').strip()
    if not s:
        return '해설 없음'
    if WANDER.search(s):
        return '풀이가 헤맴'
    if len(s) > 160 and not ENDED.search(s[-120:]):
        return '끝맺지 못함'
    return ''


def to_korean(notes):
    """영어로 온 도형 메모를 한국어로 옮긴다 (선생님이 읽고 그린다).
    실패하면 원문 그대로 둔다 — 여기서 죽을 이유가 없다."""
    import urllib.request
    body = {'model': 'gemini-2.5-flash',
            'contents': [{'parts': [{'text':
                '아래 줄들을 한국어로 옮겨라. $ … $ 안의 수식은 **한 글자도 건드리지 마라.**\n'
                '줄 수와 순서를 그대로 지켜 JSON 배열로만 답하라.\n\n'
                + '\n'.join(notes)}]}],
            'generationConfig': {'temperature': 0, 'maxOutputTokens': 4096,
                                 'responseMimeType': 'application/json',
                                 'responseSchema': {'type': 'array',
                                                    'items': {'type': 'string'}},
                                 'thinkingConfig': {'thinkingBudget': 0}}}
    req = urllib.request.Request(
        'https://academy-manager-eosin.vercel.app/api/gemini-proxy',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    out = json.loads(d['candidates'][0]['content']['parts'][0]['text'])
    return out if len(out) == len(notes) else notes


# (조립 파이프라인 __main__ 은 서버에 싣지 않는다 — full3c 덮어쓰기 사고 방지)
