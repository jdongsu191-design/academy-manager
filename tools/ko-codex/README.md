# 내신분석표 Codex 처리기

기존 내신분석표에서 Codex 연결 → 파일 선택 → 분석 → 검수 → 총평 생성 → 저장 순서로 사용합니다.
PDF·HWP·HWPX는 50MB/30쪽 이하입니다. SQL 변경은 없습니다.

Windows 처리 PC에서 한컴 한글과 Codex 로그인을 준비합니다. 이 폴더에서 `python -m pip install -r requirements.txt`로 의존성을 설치합니다.
`./start.ps1 -Origin https://academy-manager-eosin.vercel.app -Background`로 실행하고 웹에서 연결을 허용합니다.

한글은 원본 PDF 변환 후 분석합니다. 파일 접근 확인창은 사용자가 허용하고, 변환한 임시 문서의 변경사항은 저장하지 않고 닫습니다. 다른 사용자 문서는 종료하지 않습니다.
문항 번호·배점은 독립 원본 대조표와 비교하고 한 문항 단원도 보존합니다. 난이도 비율을 강제하지 않습니다.
변환 결과·로그·대조표는 로컬 `.bmaps-ko-worker`에 저장됩니다. 저장 버튼 전에는 DB에 쓰지 않습니다.

이 운영 브랜치는 내신분석 모듈만 포함합니다. 처리기는 설치된 모듈만 지원한다고 표시하며 프리뷰의 국어·N제 화면을 활성화하지 않습니다.
검증: `python -m unittest discover -s tools/ko-codex -p 'test_*.py'` (저장소 루트), jsdom 환경에서 `node tools/ko-codex/test_exam_ui.cjs`.
