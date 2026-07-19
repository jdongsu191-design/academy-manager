# BMAPS (베스티안수학학원 포털) — 작업 규칙

## 프로젝트 개요
Supabase 백엔드 기반 학원 관리 포털. 단일 파일 HTML 구조(빌드 과정 없음).
GitHub `jdongsu191-design/academy-manager` → Vercel 자동 배포.

- 운영: `academy-manager-eosin.vercel.app` (main 브랜치)
- 프리뷰: Better-BMAPS 브랜치 (고정 URL)

## 파일 구조와 인코딩 ⚠️ 최우선 주의

| 파일 | 줄 수 | **줄바꿈** | 용도 |
|---|---|---|---|
| `index.html` | ~26,810 | **CRLF** | 메인 포털 (단일 파일 모놀리스) |
| `syllabus.html` | ~3,700 | **LF** | 강의계획서 |
| `studycenter.html` | ~3,290 | **LF** | 독서실 출결 |
| `nje.html` | ~1,470 | **LF** | 서브 페이지 |
| `consult.html` | ~1,433 | **LF** | 서브 페이지 |
| `payroll.html` | ~1,238 | **LF** | 급여 관리 |
| `lobby.html` | ~277 | **LF** | TV 표시용 페이지 |

**`index.html`만 CRLF이고 나머지는 전부 LF다. 편집 전 반드시 확인하고, 원래 방식을 보존할 것.**

```bash
# 편집 전 필수 확인
python3 -c "b=open('index.html','rb').read(); print('CRLF:',b.count(b'\r\n'),'단독LF:',b.count(b'\n')-b.count(b'\r\n'))"
```

## 절대 규칙

### 1. 줄바꿈 보존
- **CRLF 파일**(`index.html`): Python으로 `open(path,'rb')` → `.decode().replace('\r\n','\n')` → 편집 → `.replace('\n','\r\n')` → 바이너리 쓰기
- **LF 파일**(그 외 전부): LF 그대로 유지. CRLF 변환 금지
- **bash 문자열 조작(sed 등)으로 이 파일들을 편집하지 말 것** — 줄바꿈이 깨진다

### 2. 단일 치환 보증
문자열 치환 시 **반드시** 고유성을 검증한다:
```python
assert s.count(old) == 1, f"매칭 {s.count(old)}개"
```
2개 이상 매칭되면 앞뒤 맥락을 더 넣어 고유하게 만든다.

### 3. 수정 후 검증 (매번)
1. **반영 확인** — 의도한 변경이 정확히 들어갔는지 카운트로 확인
2. **문법 검사** — 최대 인라인 `<script>` 블록 추출 후 `node --check`
3. **무회귀 grep** — 최근 작업한 기능들이 그대로 있는지 확인
4. **줄바꿈 확인** — CRLF/LF 개수가 원본과 일치하는지
5. **diff 검증** — 의도한 줄만 바뀌었는지 (`diff` 로 추가/삭제 줄 수 확인)

```bash
# 문법 검사
python3 -c "
import re
s=open('index.html',encoding='utf-8').read()
sc=re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', s, re.S); sc.sort(key=len,reverse=True)
open('/tmp/_chk.js','w',encoding='utf-8').write(sc[0])
" && node --check /tmp/_chk.js
```

## 작업 프로토콜 (수술 원칙)

대형병원 수술처럼 안전과 정확성을 최우선으로 한다.

1. **보고 후 수정** — 코드를 건드리기 전에 문제와 수정 방안을 먼저 설명하고 승인을 받는다
2. **전체 정독** — 수정 부분만이 아니라 관련 함수 전체를 읽고, 부작용 가능성을 독립적으로 점검한다
3. **단계 잠금** — 한 단계를 완전히 검증한 뒤 다음으로 넘어간다. 위험한 기능은 단계를 나눈다
4. **작동하는 코드는 건드리지 않는다** — 요청 범위를 벗어난 리팩터링·정리 금지
5. **영향 범위 사전 조사** — 컬럼/필드 추가 시 DOM 인덱스 의존 코드(`cells[N]`, `nth-child`), 변경감지 로직, 정산 로직에 영향이 없는지 먼저 확인

## 배포 흐름

배포는 **프리뷰 브랜치 먼저** → 실측 검증 → main 순서를 지킨다.
**push가 곧 Vercel 배포 트리거**임을 항상 인지할 것.

### 브랜치별 권한

| 브랜치 | 커밋 | push |
|---|---|---|
| `Better-BMAPS` (프리뷰) | 가능 | **가능** (아래 사전 점검 통과 시) |
| `main` (운영) | 가능 | **반드시 사용자 승인 후** |

### push 전 사전 점검 (필수 3종)

1. **현재 브랜치 확인** — `git branch --show-current`로 의도한 브랜치인지 확인. main이면 즉시 멈추고 승인 요청
2. **변경 내역 보고** — `git status`(변경 파일 목록) + `git diff --stat`(파일별 추가/삭제 줄 수)를 사용자에게 보고한 뒤 push
3. **이상 징후 시 중단** — 예상과 다르면 push하지 말고 보고한다
   - ⚠️ **줄 수가 수만 줄 단위로 잡히면 줄바꿈 사고**다. 무조건 멈춘다
   - 손대지 않은 파일이 변경 목록에 있으면 멈춘다

### 금지 사항

- `git push --force`, `--force-with-lease` — **예외 없이 금지**
- `git reset --hard` 후 push — **금지**
- Supabase **DDL(테이블/컬럼 변경)은 사용자가 직접 실행**한다. Claude는 SQL만 제안

## 실측 검증 (Chrome MCP 사용 시)

- 실제 학생 데이터를 건드리기 전에 **반드시 원본을 백업**하고, 테스트 후 정확히 복원한다
- 전송/저장 등 DB를 바꾸는 함수는 가로채서 차단한 뒤 테스트한다
- 가로챈 함수는 `finally`에서 반드시 원복한다
- 테스트 데이터는 "테스트" 접두어를 붙여 식별 가능하게 만든다

## 도메인 메모

- **Supabase**: anon 클라이언트. `db` 전역으로 노출됨
- **날짜**: `toISOString()`은 UTC라 하루 밀릴 수 있음 → 로컬 포맷터(`_localYMD`) 사용
- **주말 프로그램**: 일일N제(`wn`) / 포텐셜(`pt`) / 베티(`by`) / 내신대비(`ns`) 4종. 페이지네이션 `WK_PAGE_SIZE=100`
- **변경감지**: 주말 출석부는 `[data-sid][data-field]` 속성 기반(`_domValueMap`) — 컬럼 위치와 무관
- **버전 문자열**: `studycenter.html`·`syllabus.html`은 버전을 3곳(`<title>`, 화면 표시 span, `window.*_VERSION`)에 두므로 반드시 함께 수정

## 커뮤니케이션

- **한국어로, 간결하게** 답한다
- 변경 사항은 표나 짧은 목록으로 요약한다
- 불확실하면 추측하지 말고 코드를 읽어 확인한다
