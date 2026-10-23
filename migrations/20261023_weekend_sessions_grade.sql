-- 베티모의고사 회차를 분원별·학년별로 관리 (2026-10-23)
-- weekend_sessions 에 grade 컬럼 추가. 값: '1' | '2' | '3' | 'pre'(예비고) | NULL(전학년 공통)
-- 고유 제약을 (program, 날짜, 분원, 학년) 으로 바꾼다. 기존 행은 전부 grade NULL(전학년) 이라 데이터 이전 없음.

alter table public.weekend_sessions
  add column if not exists grade text
  check (grade is null or grade in ('1','2','3','pre'));

-- 기존 고유 인덱스(이름이 환경마다 달라 전부 찾아 지움: weekend_sessions 의 unique 인덱스 중 PK 제외)
do $$
declare r record;
begin
  for r in
    select i.indexname
    from pg_indexes i
    join pg_class c on c.relname = i.indexname
    join pg_index x on x.indexrelid = c.oid
    where i.schemaname = 'public' and i.tablename = 'weekend_sessions'
      and x.indisunique and not x.indisprimary
  loop
    execute format('drop index if exists public.%I', r.indexname);
  end loop;
end $$;

create unique index weekend_sessions_program_date_branch_grade_uq
  on public.weekend_sessions (
    program,
    session_date,
    coalesce(branch_id, '00000000-0000-0000-0000-000000000000'::uuid),
    coalesce(grade, '')
  );

-- 확인
select program, session_date, round_no, is_closed, branch_id, grade
from public.weekend_sessions
where program = 'bety'
order by session_date desc
limit 5;
