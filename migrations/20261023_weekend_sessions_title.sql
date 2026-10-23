-- 회차에 숫자 대신 이름(텍스트)도 쓸 수 있게 (2026-10-23)
-- 예: '10월 모의고사', '수능 전 마지막 점검'. title 이 있으면 round_no 는 비워 둔다.
alter table public.weekend_sessions
  add column if not exists title text;

-- 확인
select program, session_date, round_no, title, is_closed, branch_id, grade
from public.weekend_sessions
where program = 'bety'
order by session_date desc
limit 5;
