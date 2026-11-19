-- 진도계획서 사진 분리 (2026-11-19) — 로딩 멈춤·DB 주기적 충돌의 근본 원인 제거
-- 원인: bmaps_syllabuses.courses(jsonb) 의 강좌마다 선생님 사진 dataURL(0.4~1MB)이 복사되어 한 행이 최대 6.7MB.
--       courses 를 여러 행 읽는 조회(반 카드 📑 contains, 런처, 저장본 목록)가 Postgres 를 쓰러뜨림.
-- 해결: 사진은 행의 photo 칸에 한 번만. 코드는 syllabus.html v2.23(main v2.19.1) 부터 이 모양으로 읽고 쓴다.

-- ── 1. 칸 추가 (실행 완료) ──────────────────────────────────────
alter table public.bmaps_syllabuses add column if not exists photo text;

-- ── 2. 옛 행 정리: 한 번에 10행씩. 아래 블록을 '남은_큰_행' 이 0 이 될 때까지 반복 실행 ──
--    · 강좌 안 첫 사진을 photo 칸으로 옮기고, 강좌 안 photo 는 null 로 (다른 키는 그대로, 강좌 순서 유지)
--    · 대상은 저장 크기로만 고른다 — pg_column_size 는 큰 값을 풀지 않아 가볍다
--      (내용을 검사하는 조건을 쓰면 그 자체가 전 행을 푸는 무거운 조회가 된다)
--    · 기준 20KB: 백업 실측으로 사진 없는 행의 courses 는 최대 6KB, 사진 있는 행은 최소 30KB(압축 후) 라 정확히 갈린다
with t as (
  select id
    from public.bmaps_syllabuses
   where pg_column_size(courses) > 20000
   order by pg_column_size(courses) desc
   limit 10
)
update public.bmaps_syllabuses s
   set photo = coalesce(
         (select e->>'photo'
            from jsonb_array_elements(s.courses) with ordinality x(e, ord)
           where coalesce(e->>'photo', '') <> ''
           order by ord limit 1),
         s.photo),
       courses = (select jsonb_agg(case when e ? 'photo' then jsonb_set(e, '{photo}', 'null'::jsonb) else e end order by ord)
                    from jsonb_array_elements(s.courses) with ordinality x(e, ord))
  from t
 where s.id = t.id;

select count(*) filter (where pg_column_size(courses) > 20000) as 남은_큰_행,
       count(photo) as 사진칸_채워진_행,
       pg_size_pretty(pg_total_relation_size('public.bmaps_syllabuses')) as 표_크기
  from public.bmaps_syllabuses;

-- ── 3. (선택) 다 끝난 뒤 한 번: 빈 공간 정리 ─────────────────────
-- vacuum (analyze) public.bmaps_syllabuses;
