# -*- coding: utf-8 -*-
"""원본과 변형을 나란히 놓은 hwpx 를 만든다 (검수용).

· 템플릿은 포텐셜 원본(pt_src.hwpx) — 쪽 설정·글자 모양을 그대로 물려받는다.
· 수식은 진짜 한글 수식 객체로 넣는다 (크기는 eq_metrics 로 잰다 — 모자라면 글자를 덮는다).
· 그림은 원본 BMP 를 PNG 로 바꿔 넣는다.
⚠ 원본 파일은 읽기만 한다.
"""
import zipfile, re, os, io, sys, html, json
import xml.etree.ElementTree as ET
from eq_metrics import measure as eq_measure
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def _zf(t):
    """경로도 bytes 도 받는다 — 서버에서는 파일을 안 만들고 bytes 로 돈다."""
    if isinstance(t, (bytes, bytearray)):
        return zipfile.ZipFile(io.BytesIO(t))
    return zipfile.ZipFile(t)

CP = 0            # 본문 글자모양 (원본에서 가장 많이 쓰인 것)
PP = 0            # 문단 모양


def esc(t):
    return html.escape(str(t), quote=False).replace('\r', '')


def balanced(s, tag, start=0):
    m = re.compile(r'<%s\b' % tag).search(s, start)
    if not m:
        return None
    i, depth = m.start(), 0
    for t in re.finditer(r'<%s\b[^>]*?(/?)>|</%s>' % (tag, tag), s[i:]):
        if t.group(0).startswith('</'):
            depth -= 1
        elif t.group(1) == '/':
            continue
        else:
            depth += 1
        if depth == 0:
            return s[i:i + t.end()]
    return None


class Doc:
    def __init__(self, template):
        self.z = _zf(template)
        s0 = self.z.read('Contents/section0.xml').decode('utf-8')
        self.NS = re.search(r'<hs:sec\s[^>]*>', s0).group(0)
        # 첫 문단의 제어 run(secPr) 만 챙긴다. 머리말·꼬리말은 표·도형이 얽혀 있어 뺀다.
        first = balanced(s0, 'hp:p')
        run = None
        pos = 0
        while True:
            r = balanced(first, 'hp:run', pos)
            if not r:
                break
            pos = first.index(r, pos) + len(r)
            if '<hp:secPr' in r:
                run = r
                break
        assert run, 'secPr 를 못 찾음'
        for tag in ('hp:header', 'hp:footer'):
            while True:
                b = balanced(run, tag)
                if not b:
                    break
                run = run.replace(b, '', 1)
        self.head = run
        self._id = 1800000000
        self._pid = -1
        self.paras = []
        self.bins = {}
        # 글자모양·문단모양을 더 얹고 싶으면 여기에 채워 넣는다 (없으면 원본 그대로)
        self.hdr_xml = None

    # ── 조각 ──
    #  수식 크기·기준선. 원본 포텐셜 실측: baseUnit=본문 pt, baseLine 은 내용에 따라
    #  일반 85 · 첨자 71 · 분수 65 · 복합분수 61. 고정 68 로 두면 분수가 아래로 처져
    #  윗줄(번호 밑줄)에 닿는다.
    EQ_SCALE = 1.0          # eq_measure(13pt 기준)를 본문 크기로 줄이는 비율
    EQ_BASE = 1000

    def eq(self, script):
        self._id += 1
        w, h = eq_measure(script)
        r = h / 1300.0                       # eq_metrics.BASE 대비 높이 비율
        bl = 85 if r <= 1.3 else (71 if r <= 1.75 else (65 if r <= 2.9 else 61))
        w = int(w * self.EQ_SCALE)
        h = int(h * self.EQ_SCALE)
        return ('<hp:equation id="%d" zOrder="0" numberingType="EQUATION" textWrap="TOP_AND_BOTTOM"'
                ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" version="Equation Version 60"'
                ' baseLine="%d" textColor="#000000" baseUnit="%d" lineMode="CHAR" font="HYhwpEQ">'
                '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
                '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"'
                ' holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP"'
                ' horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                '<hp:outMargin left="56" right="56" top="0" bottom="0"/>'
                '<hp:shapeComment>수식입니다.</hp:shapeComment>'
                '<hp:script>%s</hp:script></hp:equation>'
                % (self._id, bl, self.EQ_BASE, w, h, esc(script)))

    def img(self, png, wmm, hmm):
        self._id += 2
        name = 'vfig%d' % (len(self.bins) + 1)
        self.bins[name] = png
        W, H = int(wmm / 25.4 * 7200), int(hmm / 25.4 * 7200)
        return ('<hp:pic id="%d" zOrder="0" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM"'
                ' textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0"'
                ' instid="%d" reverse="0">'
                '<hp:offset x="0" y="0"/><hp:orgSz width="%d" height="%d"/>'
                '<hp:curSz width="%d" height="%d"/><hp:flip horizontal="0" vertical="0"/>'
                '<hp:rotationInfo angle="0" centerX="%d" centerY="%d" rotateimage="1"/>'
                '<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                '<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
                '<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>'
                '<hc:img binaryItemIDRef="%s" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
                '<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="%d" y="0"/>'
                '<hc:pt2 x="%d" y="%d"/><hc:pt3 x="0" y="%d"/></hp:imgRect>'
                '<hp:imgClip left="0" right="%d" top="0" bottom="%d"/>'
                '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
                '<hp:imgDim dimwidth="%d" dimheight="%d"/><hp:effects/>'
                '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
                '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"'
                ' holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP"'
                ' horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
                '<hp:shapeComment>그림입니다.</hp:shapeComment></hp:pic>'
                % (self._id, self._id + 1, W, H, W, H, W // 2, H // 2,
                   name, W, W, H, H, W, H, W, H, W, H))

    def para(self, segs, head=''):
        self._pid += 1
        body = ''.join(segs) or '<hp:t/>'
        return ('<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0"'
                ' merged="0">%s<hp:run charPrIDRef="%d">%s</hp:run></hp:p>'
                % (self._pid, PP, head, CP, body))

    def line(self, segs, head=''):
        self.paras.append(self.para(segs, head))

    def text(self, t):
        self.line(['<hp:t>%s</hp:t>' % esc(t)] if t else [])

    # $ … $ 로 감싼 곳만 수식 객체로 만든다
    def rich(self, s):
        segs = []
        for i, part in enumerate(re.split(r'\$', s or '')):
            if not part:
                continue
            if i % 2:
                segs.append(self.eq(part))
            else:
                segs.append('<hp:t>%s</hp:t>' % esc(part.replace('`', '')))
        self.line(segs)

    # ⟪ … ⟫ 로 표시된 원본용
    def rich_src(self, s):
        segs = []
        for i, part in enumerate(re.split(r'⟪|⟫', s or '')):
            if not part:
                continue
            segs.append(self.eq(part) if i % 2 else '<hp:t>%s</hp:t>' % esc(part))
        self.line(segs)

    def picture(self, png, w, h, maxmm=55.0):
        mm = min(maxmm, w / 96 * 25.4)
        self.line([self.img(png, mm, mm * h / w)])

    # ── 저장 ──
    def save(self, out, title='변형문제 시안'):
        z = self.z
        # ⚠ 쪽 설정(secPr)·단 설정(colPr)은 **첫 문단 안**에 있어야 한다.
        #   빠뜨리면 한/글이 조용히 기본값으로 열어 1단 A4 가 된다 (실제로 그랬다).
        paras = list(self.paras)
        assert paras, '문단이 없다'
        m = re.match(r'(<hp:p\b[^>]*>)', paras[0])
        assert m, '첫 문단 모양이 이상하다'
        paras[0] = m.group(1) + self.head + paras[0][m.end():]
        sec = ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>' + self.NS
               + ''.join(paras) + '</hs:sec>')
        hdr = self.hdr_xml or z.read('Contents/header.xml').decode('utf-8')
        hdr = re.sub(r'secCnt="\d+"', 'secCnt="1"', hdr, 1)
        hpf = z.read('Contents/content.hpf').decode('utf-8')
        for m in re.findall(r'<opf:item[^>]*href="(BinData/[^"]*)"[^>]*/>', hpf):
            hpf = re.sub(r'<opf:item[^>]*href="%s"[^>]*/>' % re.escape(m), '', hpf)
        hpf = hpf.replace('</opf:manifest>', ''.join(
            '<opf:item id="%s" href="BinData/%s.png" media-type="image/png" isEmbeded="1"/>' % (k, k)
            for k in self.bins) + '</opf:manifest>', 1)
        for n in range(1, 9):
            hpf = re.sub(r'<opf:item[^>]*href="Contents/section%d\.xml"[^>]*/>' % n, '', hpf)
            hpf = re.sub(r'<opf:itemref[^>]*idref="section%d"[^>]*/>' % n, '', hpf)
        hpf = re.sub(r'<opf:title>.*?</opf:title>', '<opf:title>%s</opf:title>' % esc(title), hpf, 1)

        rdf = z.read('META-INF/container.rdf').decode('utf-8')
        for b in re.findall(r'<rdf:Description\b.*?</rdf:Description>', rdf, re.S):
            if re.search(r'section[1-9]\.xml', b):
                rdf = rdf.replace(b, '')
        st = re.sub(r'(<ha:CaretPosition[^>]*paraIDRef=")\d+(")',
                    lambda m: m.group(1) + '0' + m.group(2),
                    z.read('settings.xml').decode('utf-8'))
        prv = '\r\n'.join(re.sub(r'<[^>]+>', '', p) for p in self.paras)[:1800]

        files = [(n, z.read(n)) for n in ('version.xml', 'META-INF/container.xml',
                                          'META-INF/manifest.xml', 'Scripts/headerScripts.js')
                 if n in z.namelist()]
        files += [('BinData/%s.png' % k, v) for k, v in self.bins.items()]
        files += [('Contents/header.xml', hdr.encode()), ('settings.xml', st.encode()),
                  ('META-INF/container.rdf', rdf.encode()), ('Contents/content.hpf', hpf.encode()),
                  ('Contents/section0.xml', sec.encode()),
                  ('Preview/PrvText.txt', prv.encode())]
        if isinstance(out, str) and os.path.exists(out):
            os.remove(out)
        zz = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
        zz.writestr(zipfile.ZipInfo('mimetype'), 'application/hwp+zip', zipfile.ZIP_STORED)
        for k, v in files:
            zz.writestr(k, v)
        zz.close()
        return out


def _png_size(b):
    """PNG IHDR 에서 (w, h)."""
    import struct
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        return 0, 0
    return struct.unpack('>II', b[16:24])


def _jpg_size(b):
    """JPEG SOF 마커에서 (w, h)."""
    import struct
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack('>HH', b[i + 5:i + 9])
            return w, h
        i += 2 + (struct.unpack('>H', b[i + 2:i + 4])[0] if i + 4 <= len(b) else 0)
    return 0, 0


def to_png(hwpx, name):
    """BinData 그림을 PNG 로 (PIL 없이 — BMP 는 hwpx_parse.bmp_to_png, JPG 는 그대로).
    JPG 는 hwpx 에 그대로 넣어도 되지만 확장자를 맞추려 png 만 promises 하는
    호출부와의 계약상, JPG 는 (bytes, w, h, 'jpg') 로 구분해 돌려준다."""
    from hwpx_parse import bmp_to_png
    z = _zf(hwpx)
    for n in z.namelist():
        if n.startswith('BinData/') and n.split('/')[-1].split('.')[0] == name:
            ext = n.rsplit('.', 1)[-1].lower()
            b = z.read(n)
            if ext == 'bmp':
                p = bmp_to_png(b)
                if p is None:
                    return None, 0, 0
                w, h = _png_size(p)
                return p, w, h
            if ext == 'png':
                w, h = _png_size(b)
                return b, w, h
            if ext in ('jpg', 'jpeg'):
                # ⚠ Doc.img 는 png 로 등록한다 — JPG 도 한/글이 png 확장자로 읽지만
                #   깔끔하게 가려면 그림이 jpg 뿐인 문서에서 확인할 것 (실측: 포텐셜은 거의 BMP)
                w, h = _jpg_size(b)
                return b, w, h
    return None, 0, 0


if __name__ == '__main__':
    made = json.load(open('made.json', encoding='utf-8'))
    d = Doc('pt_src.hwpx')
    d.text('변형문제 시안 — 포텐셜  (2026-08-24, gemini-2.5-flash)')
    d.text('각 문항마다 [원본] 다음에 V0·V1·V2 를 붙였습니다. 답은 모델이 낸 값입니다.')
    d.text('')
    SRC = {'m1': 'pt_src.hwpx', 'm3': 'pt3_src.hwpx'}
    NAME = {'m1': '중1 8월 3회', 'm3': '중3 8월 3회'}
    for item in made:
        o = item['origin']
        d.text('━' * 46)
        d.text('%s  %d번   [%s]  %s점   출처) %s'
               % (NAME[item['tag']], o['number'], o['type'], o['points'], o['source']))
        d.text('')
        d.text('【원본】')
        d.rich_src(o['statement'])
        for f in (o.get('figures') or []):
            png, w, h = to_png(SRC[item['tag']], f[0])
            if png:
                d.picture(png, w, h)
        d.rich_src('정답  ⟪%s⟫' % o['answer_script'])
        d.text('')
        for v in item['variants']:
            if not (v.get('statement') or '').strip():
                d.text('【%s】 만들지 못함 — %s' % (v['level'], v['changed']))
                d.text('')
                continue
            d.text('【%s】' % v['level'])
            d.rich(v['statement'])
            d.rich('정답  %s' % v['answer'])
            d.text('바꾼 것 : %s' % re.sub(r'\$', '', v['changed']))
            d.text('그림    : %s' % re.sub(r'\$', '', v['figure_change']))
            for ln in (v['solution'] or '').split('\n'):
                if ln.strip():
                    d.rich('   ' + ln.strip())
            d.text('')
    out = d.save('변형문제_시안.hwpx')
    print('저장: %s (%.0f KB) · 문단 %d · 그림 %d'
          % (out, os.path.getsize(out) / 1024, len(d.paras), len(d.bins)))
