"""Read text-based KICE answer tables by row and elective heading geometry."""
import pymupdf


def parse_answers(pdf):
    doc=pymupdf.open(stream=pdf,filetype='pdf')
    if doc.is_encrypted or len(doc)>10: raise ValueError('암호 없는 10쪽 이하 정답 PDF를 사용하세요.')
    found={}
    for page in doc:
        labels=[]
        for label in ('화법과 작문','언어와 매체'):
            for rect in page.search_for(label): labels.append((label,(rect.x0+rect.x1)/2,rect.y1))
        rows=[]
        for word in sorted(page.get_text('words'),key=lambda w:(w[1],w[0])):
            if not rows or abs(rows[-1][0]-word[1])>3: rows.append((word[1],[]))
            rows[-1][1].append(word)
        for y,words in rows:
            words.sort(key=lambda w:w[0])
            for i in range(len(words)-2):
                w,a,p=words[i:i+3]; answer=str(a[4]); answer=str('①②③④⑤'.index(answer)+1) if answer in '①②③④⑤' and len(answer)==1 else answer
                if not str(w[4]).isdigit() or answer not in ('1','2','3','4','5') or p[4] not in ('2','3'): continue
                # Require a true number/answer/points triplet rather than an overlapping numeric slice.
                if i%3 or len(words)%3: continue
                no=int(w[4])
                if not 1<=no<=99: continue
                eligible=[label for label in labels if label[2]<y]
                elective=min(eligible,key=lambda l:abs(l[1]-(a[0]+a[2])/2))[0] if no>=35 and eligible else '공통'
                key=(elective,no);item={'no':no,'answer':int(answer),'points':int(p[4]),'elective':elective}
                if key in found and found[key]!=item: raise ValueError('정답표에 충돌하는 문항이 있습니다. 정답표만 포함한 PDF를 사용하세요.')
                found[key]=item
    if not found: raise ValueError('정답표를 읽지 못했습니다. 텍스트형 평가원 정답표를 사용하거나 정답을 직접 입력하세요.')
    return {'rows':list(found.values()),'pages':len(doc)}
