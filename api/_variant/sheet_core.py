# -*- coding: utf-8 -*-
"""문제집 조립 — pt_sheet3 의 서버판. 입출력만 bytes/dict 로 바꿨고 판형은 그대로다.

입력
  src      : 원본 포텐셜 hwpx (bytes) — 쪽 설정·서식·원문 그림·해설 그림을 물려받는다
  probs    : 파서가 만든 원문 목록 (statement 는 ⟪…⟫)
  gen      : {번호(str): {'base_think','base_calc','variants':[…]}}
  title    : 표지·문서 제목
출력: hwpx bytes
"""
import io, re
from pt_layout import Styled, mm
from pt_build import esc, to_png

LVDOT = {'V1': 1, 'V2': 2, 'V3': 3}
NEED = {'edit': '도형 필요 — 원문 그림을 고쳐 쓰세요',
        'new': '도형 필요 — 새로 그려야 합니다'}


def dots(n, total):
    n = max(0, min(int(n or 0), total))
    return '●' * n + '○' * (total - n)


def sol_lines(s):
    """해설을 줄로 나눈다. 번호 앞에서 끊되 $ … $ 안에서는 절대 끊지 않는다."""
    ENDS = re.compile(r'(?<!\d)\.$|[다요)]$')
    NUM = re.compile(r'\s*(\d{1,2}\.)(?!\d)')
    s = str(s or '')
    out, cur, inmath, i = [], [], False, 0
    while i < len(s):
        c = s[i]
        if c == '$':
            inmath = not inmath
        if not inmath:
            if c == '\n':
                out.append(''.join(cur)); cur = []; i += 1; continue
            m = NUM.match(s, i)
            if m and ENDS.search(''.join(cur).rstrip()):
                out.append(''.join(cur)); cur = []
                i = m.start(1)
                continue
        cur.append(c); i += 1
    out.append(''.join(cur))
    return [x.strip() for x in out if x.strip()]


class Book(Styled):
    def __init__(self, template, cols=2):
        super().__init__(template)
        self.head = re.sub(
            r'<hp:colPr[^>]*?/>|<hp:colPr[^>]*?>.*?</hp:colPr>',
            '<hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="%d" sameSz="1"'
            ' sameGap="2551"><hp:colLine type="SOLID" width="0.12 mm" color="#CCCCCC"/>'
            '</hp:colPr>' % cols, self.head, count=1, flags=re.S)
        assert 'colCount="%d"' % cols in self.head, '단 설정 실패'
        self._note = 0

    def note(self, blocks):
        self._note += 1
        self._id += 1
        ps = []
        for i, (c, segs, pp) in enumerate(blocks):
            self._pid += 1
            head = ('<hp:ctrl><hp:autoNum num="%d" numType="ENDNOTE">'
                    '<hp:autoNumFormat type="DIGIT" userChar="" prefixChar=""'
                    ' suffixChar=")" supscript="0"/></hp:autoNum></hp:ctrl>'
                    % self._note) if i == 0 else ''
            ps.append('<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0"'
                      ' columnBreak="0" merged="0">'
                      '<hp:run charPrIDRef="%d">%s%s</hp:run>'
                      '<hp:linesegarray/></hp:p>'
                      % (self._pid, self.P[pp], self.C[c], head,
                         ''.join(segs) or '<hp:t/>'))
        return ('<hp:ctrl><hp:endNote number="%d" suffixChar="41" instId="%d">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK"'
                ' vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" textWidth="0"'
                ' textHeight="0" hasTextRef="0" hasNumRef="0">%s</hp:subList>'
                '</hp:endNote></hp:ctrl>' % (self._note, self._id, ''.join(ps)))

    def T(self, s, c='sol', pp='sol'):
        return (c, ['<hp:t>%s</hp:t>' % esc(s)] if s else [], pp)

    def R(self, s, c='sol', pp='sol'):
        return (c, self.segs(s), pp)

    def head_line(self, no, badge, bc, meta, note=''):
        # ⚠ 미주 <hp:ctrl> 은 반드시 <hp:run> 안 — 밖이면 한/글이 조용히 삼킨다 (실측)
        self.add([('num', ['<hp:t>%s.</hp:t>' % no]),
                  ('body', ['<hp:t>  </hp:t>']),
                  (bc, ['<hp:t>%s</hp:t>' % esc(badge)]),
                  ('meta', ['<hp:t>%s</hp:t>' % esc('   ' + meta), '<hp:t>  </hp:t>']),
                  ('dim', [note])], 'head')

    # 변형(모델 출력)의 조건 줄 — "(가) …" "ㄱ. …" 로 시작하는 줄
    COND = re.compile(r'^(?:\([가나다라마]\)|[ㄱㄴㄷㄹㅁ]\.)')

    def stmt(self, text, src=True):
        """본문을 문단·조건 상자 단위로 넣는다.
        원문: 파서가 남긴 ⟦…⟧ 가 상자, \n 이 문단.
        변형: 모델 출력이라 표시가 없다 — (가)(나)(다)·ㄱ.ㄴ.ㄷ. 줄을 상자로 승격."""
        segs = self.segs_src if src else self.segs
        t = (text or '').replace('⟦', '\n⟦\n').replace('⟧', '\n⟧\n')
        if not src:
            # 모델이 줄바꿈 없이 이어 쓴 조건도 줄로 편다 — "…구하시오.(가) …(나) …"
            t = re.sub(r'\s*(?=\([가나다라마]\)\s)', '\n', t)
            t = re.sub(r'\s*(?=[ㄱㄴㄷㄹㅁ]\.\s)', '\n', t)
        lines = [ln.strip() for ln in t.split('\n') if ln.strip()]
        inbox = False
        for ln in lines:
            if ln == '⟦':
                inbox = True
                continue
            if ln == '⟧':
                inbox = False
                continue
            box = inbox or (not src and bool(self.COND.match(ln)))
            self.add([('body', segs(ln))], 'cbox' if box else 'body')

    def memo_box(self, need, note):
        if need not in NEED:
            return
        self.add([('memoh', ['<hp:t>%s</hp:t>' % esc('▣ ' + NEED[need])])], 'memo')
        lines = [x.strip() for x in re.split(r'\n+', (note or '').strip()) if x.strip()]
        for ln in lines or ['(내용 없음 — 원문 그림을 참고하세요)']:
            self.add([('memo', self.segs(ln))], 'memol')

    def fig(self, png, w, h, wmm=58.0):
        self.paras.append(self.p([('body', [self.img(png, wmm, wmm * h / w)])], 'fig'))


def check_line(c):
    """검산 결과 한 줄 — '통과' 는 코드 값과 출제 답이 맞았을 때만."""
    c = c or {}
    if c.get('agree') == '일치':
        return True, '검산 통과   코드가 구한 값 %g  ·  출제 답과 일치' % c['value']
    if c.get('agree') == '어긋남':
        return False, '검산 ✗ 어긋남   코드는 %g 가 나왔습니다  ·  사람이 확인' % c['value']
    if c.get('value') is not None:
        return False, ('검산 값만 확인   코드가 구한 값 %g'
                       '  ·  출제 답이 문자식이라 대조 못 함' % c['value'])
    return False, '검산 △ 사람이 확인   ' + {
        '조건 모순': '조건을 만족하는 도형이 없음',
        '흔들림': '두 번 돌려 값이 달랐음',
        '판정 보류': '한 번만 값이 나왔음',
        '검산 못 함': '좌표로 옮기지 못함',
    }.get(c.get('verdict'), c.get('verdict') or '검산 전')


def build_book(src, probs, gen, title):
    s = Book(src)
    by_no = {str(p['number']): p for p in probs}

    n_var = sum(len(g.get('variants') or []) for g in gen.values())
    s.txt(title, 'title', 'ctr')
    s.txt('원문 %d문항과 그 변형 %d문항' % (len(gen), n_var), 'sub', 'ctr')
    s.txt('', 'sub', 'gap')
    s.add([('body', [])], 'rule')
    for ln in (
        '· 문항마다 [원문] 다음에 변형(V1·V2·V3)이 옵니다. 해설은 문서 끝에 미주로 붙습니다.',
        '· V1 계산이 무거워짐 · V2 묻는 대상이 달라짐 · V3 조건이 간접적으로 바뀜',
        '· 그림은 넣지 않았습니다. 필요한 곳에 점선 상자로 무엇을 그려야 하는지 적어 두었습니다.',
        '· 해설 첫 줄의 “검산”은 프로그램이 본문의 조건만 좌표로 풀어 답을 다시 구한 결과입니다.',
        '   검산 통과 = 코드가 같은 답에 이르렀음.  △ 표시 = 사람이 확인해야 함.',
        '· ⚑ 표시가 붙은 해설은 모델이 풀이를 끝맺지 못한 것입니다.',
    ):
        s.txt(ln, 'sub', 'sol')
    s.add([('body', [])], 'rule')

    seq = 0
    for no in sorted(gen, key=lambda x: int(x)):
        g = gen[no]
        p = by_no.get(str(no))
        if not p:
            continue
        vs = [v for v in (g.get('variants') or []) if (v.get('statement') or '').strip()]
        pts = p.get('points')
        ptxt = ('A %s / B %s점' % (pts.get('A'), pts.get('B'))) if isinstance(pts, dict) \
            else ('%s점' % pts)

        # ── 원문 ── (원문마다 새 단에서 시작)
        seq += 1
        s.newcol()
        nb = [('ans', s.segs_src('[정답]  ⟪%s⟫' % p['answer_script']), 'note'),
              s.T('난이도   발상 %s / 계산 %s'
                  % (dots(g.get('base_think'), 5), dots(g.get('base_calc'), 6)), 'dim', 'note'),
              s.T('출처)  ' + (p.get('source') or ''), 'dim', 'note')]
        for np_ in (p.get('note_pics') or [])[:1]:
            png, w, h = to_png(src, np_[0])
            if png and w:
                nb.append(('body', [s.img(png, 56.0, 56.0 * h / w)], 'ctr'))
        s.head_line(seq, '원문', 'otag', '%s · %s' % (p.get('type') or '', ptxt),
                    note=s.note(nb))
        s.stmt(p['statement'], src=True)
        for f in (p.get('figures') or [])[:1]:
            png, w, h = to_png(src, f[0])
            if png and w:
                s.fig(png, w, h)
        s.end_item()

        # ── 변형 ──
        for v in vs:
            seq += 1
            ok, cline = check_line(v.get('check'))
            nb = [('ans', s.segs('[정답]  %s' % v['answer']), 'note'),
                  (('ok' if ok else 'warn'), ['<hp:t>%s</hp:t>' % esc(cline)], 'note'),
                  s.T('변형   %s' % dots(LVDOT.get(v.get('level'), 1), 5), 'dim', 'note'),
                  s.T('난이도  발상 %s / 계산 %s'
                      % (dots(v.get('think'), 5), dots(v.get('calc'), 6)), 'dim', 'note'),
                  s.T('기준    발상 %s / 계산 %s'
                      % (dots(g.get('base_think'), 5), dots(g.get('base_calc'), 6)),
                      'dim', 'note')]
            for tag, body in (('[발상]', v.get('insight')), ('[풀이]', v.get('solution')),
                              ('[변형 아이디어]', v.get('idea'))):
                nb.append(s.T(tag, 'solh', 'solh'))
                nb += [s.R(x) for x in sol_lines(body)]
            if v.get('sol_flag'):
                nb.append(s.T('⚑ %s — 답은 검산 결과를 보세요.' % v['sol_flag'],
                              'warn', 'note'))

            s.head_line(seq, v.get('level') or 'V?', 'vtag',
                        '%s · %s' % (p.get('type') or '', ptxt), note=s.note(nb))
            s.stmt(v['statement'], src=False)
            s.memo_box(v.get('figure_need'), v.get('figure_note'))
            s.end_item()

    bio = io.BytesIO()
    s.save(bio, title)
    return bio.getvalue(), {'items': seq, 'notes': s._note,
                            'paras': len(s.paras), 'pics': len(s.bins)}
