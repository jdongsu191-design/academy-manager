# -*- coding: utf-8 -*-
"""검산 실행 단위 — vg_double 에서 판 흐름만 떼어 왔다.

원판(vg_double.py)은 한 문항의 두 온도를 스레드로 같이 돌렸다.
서버에서는 함수 하나가 60초 제한이라, **브라우저가 온도별로 따로 부르고**
(run) 결과를 모아 다시 서버에서 합친다(combine). 합치는 규칙은 원판 그대로:
값이 둘 이상 서로 맞을 때만 '확인함'. 기준은 끝까지 둘이다.
"""
from vg_spec import ask_spec, figure_only, num_of
from verify_geo import check

TEMPS = (0.15, 0.55)
TEMP3 = 0.35
REL = 2e-3


def run_once(statement, png=None, temp=0.15, trials=10):
    """온도 하나로 명세를 받아 푼다. (vg_double._once 그대로)"""
    sym = figure_only(statement)
    if sym:
        return {'verdict': '검산 못 함', 'value': None,
                'why': "묻는 대상 '%s' 가 그림에만 표시됨 — 추측하면 오탐이 난다" % sym,
                'gated': True}
    try:
        spec, sec = ask_spec(statement, png, temp=temp)
    except Exception as e:
        return {'verdict': '명세 실패', 'why': str(e)[:70], 'sec': 0, 'spec': None}
    if not spec.get('points'):
        return {'verdict': '검산 못 함', 'why': (spec.get('why') or '')[:70],
                'sec': sec, 'spec': spec}
    r = check(spec, trials=trials)
    r['sec'] = sec
    r['spec'] = spec
    return r


def _agree(x, y, rel=REL):
    return abs(x - y) <= rel * max(1.0, abs(x), abs(y))


def combine(rs, answer_script=None, rel=REL):
    """값이 **둘 이상 서로 맞을 때만** 확인함. (vg_double._combine 그대로)
    돌려주는 것에 need_third 를 얹는다 — 값이 하나뿐이면 셋째(0.35)를 부르라는 뜻."""
    idx = [i for i, r in enumerate(rs) if r.get('value') is not None]
    why = ' / '.join((r.get('why') or r.get('verdict') or '')[:48] for r in rs)

    out = None
    for i in range(len(idx)):
        for j in range(i + 1, len(idx)):
            a, b = rs[idx[i]]['value'], rs[idx[j]]['value']
            if not _agree(a, b, rel):
                continue
            va, vb = (rs[idx[i]].get('vars') or {}), (rs[idx[j]].get('vars') or {})
            vars_ = {k: (va[k] + vb[k]) / 2 for k in va
                     if k in vb and _agree(va[k], vb[k], rel)}
            out = {'verdict': '확인함', 'value': (a + b) / 2,
                   'vars': vars_, 'agreed': 2, 'why': ''}
            break
        if out:
            break

    if out is None:
        if len(idx) >= 2:
            out = {'verdict': '흔들림', 'value': None,
                   'why': '값이 서로 다름 (%s)' % ' · '.join('%g' % rs[i]['value'] for i in idx)}
        elif all(r.get('verdict') == '조건 모순' for r in rs):
            out = {'verdict': '조건 모순', 'value': None, 'why': why}
        elif idx:
            out = {'verdict': '판정 보류', 'value': None,
                   'why': '%d번 물어 값이 한 번만 나옴 (%g) — %s'
                          % (len(rs), rs[idx[0]]['value'], why)}
        else:
            out = {'verdict': '검산 못 함', 'value': None, 'why': why}

    out['need_third'] = (len(rs) == 2 and len(idx) == 1)
    out['agree'] = agrees(out, answer_script) if answer_script else ''
    return out


def agrees(verdict, claimed_script, rel=REL):
    """'일치' / '어긋남' / '' (견줄 수 없음)."""
    got = verdict.get('value')
    if got is None:
        return ''
    want = num_of(claimed_script)
    if want is None:
        want = num_of(claimed_script, verdict.get('vars') or {})
    if want is None:
        return ''
    return '일치' if abs(got - want) <= rel * max(1.0, abs(want)) else '어긋남'
