-- 고등 N제 요일 과제 — 기한 전 잠금 해제 (2026-11-20, 사용자 결정)
-- 전: 그 요일(due_date)이 돼야 열림.  후: 부여된 과제는 날짜와 무관하게 언제든 풀 수 있다.
-- 바꾸는 것은 자격 판정 함수 하나뿐(시작·임시저장·제출·열기가 모두 이 함수를 쓴다). 표·데이터는 건드리지 않는다.
-- 되돌리려면 where 끝에 "and d.due_date <= naje_kst_today()" 를 다시 붙여 실행.
create or replace function public.naje_day_eligible(p_student_id uuid, p_day_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(
    select 1 from public.naje_daily d
    join public.users u on u.id = d.student_id and u.role = 'student' and u.status = 'active'
    where d.id = p_day_id and d.student_id = p_student_id);
$$;
