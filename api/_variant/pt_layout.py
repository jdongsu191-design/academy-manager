# -*- coding: utf-8 -*-
"""한/글 레이아웃 도구 — 글자모양·문단모양을 새로 만들어 header.xml 에 얹는다.

지난 시안은 모든 문단이 paraPrIDRef=0 · charPrIDRef=0 이라 **글자가 다 똑같았다**.
번호도 본문도 해설도 12pt 한 덩어리라 "텍스트만 나열된 느낌" 이 났다.
여기서는 쓰임새마다 모양을 따로 만들어 원본이 이미 쓰던 폰트(함초롬바탕·돋움)에 맞춘다.

⚠ 원본 파일은 읽기만 한다. header.xml 은 **복사본 문자열**에만 손댄다.
"""
import re, zipfile
from pt_build import Doc, esc, balanced, _zf
from eq_metrics import measure as eq_measure

MM = 7200.0 / 25.4          # 1mm 가 몇 HWPUNIT 인가


def mm(v):
    return int(round(v * MM))


# ── 글자모양 ─────────────────────────────────────────────
def charpr(i, h=1000, f=6, color='#000000', bold=False, ratio=100, sp=0):
    """f: 0 나눔고딕ExtraBold · 3 한컴윤고딕760 · 5 함초롬돋움 · 6 함초롬바탕"""
    seven = lambda k, v: ('<hh:%s hangul="%s" latin="%s" hanja="%s" japanese="%s"'
                          ' other="%s" symbol="%s" user="%s"/>' % ((k,) + (v,) * 7))
    return ('<hh:charPr id="%d" height="%d" textColor="%s" shadeColor="none"'
            ' useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="3">'
            % (i, h, color)
            + seven('fontRef', f) + seven('ratio', ratio) + seven('spacing', sp)
            + seven('relSz', 100) + seven('offset', 0)
            + ('<hh:bold/>' if bold else '')
            + '<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
              '<hh:strikeout shape="NONE" color="#000000"/><hh:outline type="NONE"/>'
              '<hh:shadow type="NONE" color="#B2B2B2" offsetX="10" offsetY="10"/>'
              '</hh:charPr>')


# ── 문단모양 ─────────────────────────────────────────────
def parapr(i, align='JUSTIFY', line=160, intent=0, left=0, right=0,
           prev=0, next=0, border=3, pad=0, keep=0, tab=1, hold=0, connect=0):
    marg = ('<hh:margin><hc:intent value="%d" unit="HWPUNIT"/>'
            '<hc:left value="%d" unit="HWPUNIT"/><hc:right value="%d" unit="HWPUNIT"/>'
            '<hc:prev value="%d" unit="HWPUNIT"/><hc:next value="%d" unit="HWPUNIT"/>'
            '</hh:margin><hh:lineSpacing type="PERCENT" value="%d" unit="HWPUNIT"/>'
            % (intent, left, right, prev, next, line))
    return ('<hh:paraPr id="%d" tabPrIDRef="%d" condense="0" fontLineHeight="0"'
            ' snapToGrid="1" suppressLineNumbers="0" checked="0">'
            '<hh:align horizontal="%s" vertical="BASELINE"/>'
            '<hh:heading type="NONE" idRef="0" level="0"/>'
            '<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD"'
            ' widowOrphan="0" keepWithNext="%d" keepLines="%d" pageBreakBefore="0"'
            ' lineWrap="BREAK"/><hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
            '<hp:switch><hp:case hp:required-namespace='
            '"http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">%s</hp:case>'
            '<hp:default>%s</hp:default></hp:switch>'
            # ⚠ ignoreMargin=0 이면 테두리가 문단 **여백까지 포함**해 그려져
            #   밑줄이 다음 문단 첫 줄 위에 얹힌다 (실측) — 글상자에만 붙인다
            '<hh:border borderFillIDRef="%d" offsetLeft="%d" offsetRight="%d"'
            ' offsetTop="%d" offsetBottom="%d" connect="%d" ignoreMargin="1"/>'
            '</hh:paraPr>' % (i, tab, align, keep, hold, marg, marg, border,
                              pad, pad, pad, pad, connect))


# ── 테두리·채우기 ────────────────────────────────────────
def borderfill(i, left='NONE', right='NONE', top='NONE', bottom='NONE',
               width='0.12 mm', color='#000000', face='none'):
    b = lambda k, t: ('<hh:%sBorder type="%s" width="%s" color="%s"/>' % (k, t, width, color))
    return ('<hh:borderFill id="%d" threeD="0" shadow="0" centerLine="NONE"'
            ' breakCellSeparateLine="0">'
            '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
            '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
            % i + b('left', left) + b('right', right) + b('top', top) + b('bottom', bottom)
            + '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
              '<hc:fillBrush><hc:winBrush faceColor="%s" hatchColor="#FF000000" alpha="0"/>'
              '</hc:fillBrush></hh:borderFill>' % face)


def _bump(h, tag, add, xml):
    """<hh:xxxProperties itemCnt="N"> … </hh:xxxProperties> 에 끼워 넣고 개수를 올린다."""
    blk = balanced(h, tag)
    assert blk, tag + ' 없음'
    n = int(re.search(r'itemCnt="(\d+)"', blk).group(1))
    new = (re.sub(r'itemCnt="\d+"', 'itemCnt="%d"' % (n + add), blk, 1)
           .replace('</%s>' % tag, xml + '</%s>' % tag, 1))
    assert new != blk
    return h.replace(blk, new, 1)


class Styled(Doc):
    """원본 서식을 물려받되, 쓰임새별 모양을 새로 얹은 문서."""

    # 수식을 본문(10.5pt)에 맞춘다 — eq_metrics 는 13pt 기준이라 그대로 쓰면
    # 수식이 글자보다 커서 줄 높이가 널뛰고 번호 밑줄에 닿는다 (실측).
    EQ_SCALE = 1050.0 / 1300.0
    EQ_BASE = 1050

    def __init__(self, template):
        super().__init__(template)
        h = _zf(template).read('Contents/header.xml').decode('utf-8')
        # 새 id 는 기존 최대값 다음부터 — 겹치면 한/글이 조용히 엉뚱한 모양을 쓴다
        nc = max(int(x) for x in re.findall(r'<hh:charPr id="(\d+)"', h)) + 1
        np_ = max(int(x) for x in re.findall(r'<hh:paraPr id="(\d+)"', h)) + 1
        nb = max(int(x) for x in re.findall(r'<hh:borderFill id="(\d+)"', h)) + 1

        # 테두리 세 가지
        BF_RULE, BF_BOX, BF_TAB = nb, nb + 1, nb + 2
        bfs = (borderfill(BF_RULE, bottom='SOLID', width='0.4 mm', color='#333333')
               + borderfill(BF_BOX, 'DASH', 'DASH', 'DASH', 'DASH',
                            width='0.12 mm', color='#9AA0A6', face='#F5F5F5')
               + borderfill(BF_TAB, top='SOLID', width='0.12 mm', color='#BBBBBB'))

        # 글자모양 — 쓰임새마다 하나씩
        cspec = [
            ('num',   dict(h=1250, f=0, bold=True, color='#111111')),       # 3.
            ('vtag',  dict(h=1000, f=5, bold=True, color='#B4231E')),       # V2
            ('otag',  dict(h=1000, f=5, bold=True, color='#17458F')),       # 원문
            ('meta',  dict(h=850,  f=5, color='#6E7377')),                  # 개념응용·11.6점
            ('body',  dict(h=1050, f=6, ratio=97, sp=-3)),                  # 본문
            ('memo',  dict(h=880,  f=5, color='#6E7377')),                  # 도형 메모
            ('memoh', dict(h=880,  f=5, bold=True, color='#4A4F53')),       # ▣ 도형 필요
            ('ans',   dict(h=930,  f=5, bold=True, color='#111111')),       # 정답
            ('ok',    dict(h=850,  f=5, color='#1B6B3A')),                  # 검산 통과
            ('warn',  dict(h=850,  f=5, color='#A8620B')),                  # 검산 보류
            ('solh',  dict(h=900,  f=5, bold=True, color='#17458F')),       # [발상]
            ('sol',   dict(h=900,  f=6, ratio=97, sp=-3)),                  # 해설 본문
            ('dim',   dict(h=830,  f=5, color='#8A8F94')),                  # 난이도 점
            ('title', dict(h=1600, f=0, bold=True, color='#111111')),
            ('sub',   dict(h=950,  f=5, color='#6E7377')),
        ]
        C = {}
        for k, _ in cspec:
            C[k] = nc
            nc += 1
        cps = ''.join(charpr(C[k], **kw) for k, kw in cspec)

        # 문단모양
        #  ⚠ keep(=다음 문단과 함께) 를 문항의 모든 문단에 걸면 문서 전체가 한 줄로 묶여
        #     단이 안 나뉜다. 그래서 **문항의 마지막 문단만** keep 을 뗀 짝(…end)을 쓴다.
        BOX = dict(left=mm(3.0), right=mm(3.0), border=BF_BOX, pad=mm(1.5), connect=1)
        P = {}
        specs = [
            # 번호 줄 — 위로 넉넉히 띄우고 아래에 굵은 밑줄, 본문과 떼지 않는다
            #  ⚠ next 를 좁게 잡으면 밑줄이 본문 첫 줄(특히 분수 수식)에 닿는다 (실측)
            ('head', dict(prev=mm(4.2), next=mm(2.6), border=BF_RULE,
                          pad=mm(0.9), keep=1, line=140)),
            # 본문 — 줄을 넉넉히, 왼쪽을 조금 들여 번호와 층을 만든다
            #  ⚠ 양쪽 정렬(JUSTIFY)은 쓰지 않는다. 수식이 글자처럼 끼어 있어
            #     줄이 일찍 끊기고, 한/글이 남은 자리를 낱말 사이 공백으로 벌린다
            #     ('직각삼각형    ABC에서    피타고라스    정리에' 처럼 됐다).
            #  178% 는 13pt 수식 시절의 값 — 수식을 본문 크기로 줄인 뒤엔 원본(160)에 맞춘다
            ('body',    dict(align='LEFT', line=165, left=mm(1.2), next=mm(1.0),
                             keep=1, hold=1)),
            ('bodyend', dict(align='LEFT', line=165, left=mm(1.2), next=mm(1.0), hold=1)),
            # 도형 자리 — 점선 상자 (connect=1 이라야 위아래 문단이 한 상자로 이어진다)
            ('memo',     dict(align='CENTER', line=150, prev=mm(2.0), keep=1, **BOX)),
            ('memol',    dict(align='LEFT', line=150, next=mm(2.0), keep=1, **BOX)),
            ('memolend', dict(align='LEFT', line=150, next=mm(2.0), **BOX)),
            ('fig',  dict(align='CENTER', line=130, prev=mm(1.6), next=mm(1.6))),
            ('gap',  dict(line=100)),
            # 해설(미주) — 좁게, 왼쪽을 들여 본문과 구분
            ('sol',  dict(align='LEFT', line=155, left=mm(2.0), next=mm(0.6))),
            ('solh', dict(align='LEFT', line=150, prev=mm(1.4), next=mm(0.4))),
            ('note', dict(align='LEFT', line=150, next=mm(0.4))),
            ('ctr',  dict(align='CENTER', line=150)),
            ('rule', dict(line=100, prev=mm(1.2), next=mm(1.2), border=BF_TAB)),
        ]
        for k, _ in specs:
            P[k] = np_
            np_ += 1
        pps = ''.join(parapr(P[k], **kw) for k, kw in specs)

        h = _bump(h, 'hh:borderFills', 3, bfs)
        h = _bump(h, 'hh:charProperties', len(C), cps)
        h = _bump(h, 'hh:paraProperties', len(P), pps)
        self.hdr_xml = h
        self.C, self.P = C, P
        self.colw = self._colwidth(template, cols=2)

    @staticmethod
    def _colwidth(template, cols=2, gap=2551):
        """단 하나의 실제 폭(HWPUNIT). 수식이 이보다 넓으면 옆 단으로 삐져나간다.
        ⚠ 제본 여백(gutter)까지 빼야 한다 — 빠뜨리면 폭을 넉넉히 잡아 넘침을 놓친다."""
        s = _zf(template).read('Contents/section0.xml').decode('utf-8')
        sec = balanced(s, 'hp:secPr') or ''
        w = int(re.search(r'<hp:pagePr[^>]*\swidth="(\d+)"', sec).group(1))
        m = re.search(r'<hp:margin\b[^>]*/>', sec).group(0)

        def g(k):
            hit = re.search(r'\s%s="(\d+)"' % k, m)
            return int(hit.group(1)) if hit else 0

        body = w - g('left') - g('right') - g('gutter')
        return (body - gap * (cols - 1)) // cols

    # ── 문단 짓기 ────────────────────────────────────────
    def p(self, runs, pp='body', brk='0', head=''):
        """runs = [(글자모양 이름, [조각…]), …]  — 한 문단 안에서 모양을 바꿀 수 있다."""
        self._pid += 1
        body = ''.join('<hp:run charPrIDRef="%d">%s</hp:run>'
                       % (self.C[c], ''.join(segs) or '<hp:t/>') for c, segs in runs)
        return ('<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0"'
                ' columnBreak="%s" merged="0">%s%s</hp:p>'
                % (self._pid, self.P[pp], brk, head,
                   body or '<hp:run charPrIDRef="%d"><hp:t/></hp:run>' % self.C['body']))

    def add(self, runs, pp='body', brk='0', head=''):
        self.paras.append(self.p(runs, pp, brk, head))

    def txt(self, s, c='body', pp='body'):
        self.add([(c, ['<hp:t>%s</hp:t>' % esc(s)] if s else [])], pp)

    def newcol(self):
        self.paras.append(self.p([('body', [])], 'gap', brk='1'))

    # 문항의 마지막 문단은 '다음과 함께' 를 뗀다 — 안 그러면 문서 전체가 한 덩어리로 묶인다
    END = {'body': 'bodyend', 'memol': 'memolend'}

    def end_item(self):
        inv = {self.P[k]: self.P[v] for k, v in self.END.items()}
        m = re.search(r'paraPrIDRef="(\d+)"', self.paras[-1])
        if m and int(m.group(1)) in inv:
            self.paras[-1] = self.paras[-1].replace(
                'paraPrIDRef="%s"' % m.group(1),
                'paraPrIDRef="%d"' % inv[int(m.group(1))], 1)

    # ── 긴 수식 나누기 ───────────────────────────────────
    #  수식은 **글자 하나짜리 개체**다. 한/글은 그 안에서 줄을 못 바꾼다.
    #  단 폭보다 넓으면 그대로 옆 단으로 삐져나가 구분선에 걸친다(실측 65개, 최대 268%).
    #  그래서 맨 바깥 '=' 에서 끊어 **여러 개체로 나눈다** — 교과서가 줄을 넘기는 방식 그대로다.
    OPS = ('=', '≤', '≥', '≠', '<', '>')

    @staticmethod
    def _top(s, chars):
        """중괄호·괄호 밖(맨 바깥)에 있는 기호의 자리."""
        d, out = 0, []
        for i, c in enumerate(s):
            if c in '{([':
                d += 1
            elif c in '})]':
                d -= 1
            elif d == 0 and c in chars:
                out.append(i)
        return out

    def _cut(self, script, depth=0):
        """단 폭에 맞을 때까지 쪼갠다. 더 못 쪼개면 그대로 돌려준다."""
        if eq_measure(script)[0] * self.EQ_SCALE <= self.colw or depth > 2:
            return [script]
        for chars in (self.OPS, '+-'):
            at = [i for i in self._top(script, chars) if i > 0]
            if not at:
                continue
            parts, prev = [], 0
            for i in at:
                parts.append(script[prev:i])
                prev = i                       # 이어지는 조각은 연산자로 시작한다
            parts.append(script[prev:])
            parts = [p for p in parts if p.strip()]
            if len(parts) > 1:
                out = []
                for p in parts:
                    out += self._cut(p, depth + 1)
                return out
        return [script]

    # 수식 안에 한글이 4자 넘게 있으면 그건 수식이 아니다 —
    # $ 짝이 어긋나 본문이 통째로 수식이 된 것이다(실측: "원문의 그림과 조건에 오류가…").
    HANGUL = re.compile(r'[가-힣]')

    def _math(self, part):
        if len(self.HANGUL.findall(part)) >= 4:
            return ['<hp:t>%s</hp:t>' % esc(part.replace('`', ''))]
        cuts = self._cut(part)
        if len(cuts) == 1:
            return [self.eq(part)]
        out = []
        for j, c in enumerate(cuts):
            if j:
                out.append('<hp:t> </hp:t>')    # 여기서 줄이 바뀔 수 있다
            out.append(self.eq(c))
        return out

    # ── 수식 섞인 글 ─────────────────────────────────────
    def segs(self, s, mark='$'):
        out = []
        for i, part in enumerate(re.split(re.escape(mark), s or '')):
            if not part:
                continue
            out += (self._math(part) if i % 2
                    else ['<hp:t>%s</hp:t>' % esc(part.replace('`', ''))])
        return out

    def segs_src(self, s):
        out = []
        for i, part in enumerate(re.split('⟪|⟫', s or '')):
            if not part:
                continue
            out += self._math(part) if i % 2 else ['<hp:t>%s</hp:t>' % esc(part)]
        return out
