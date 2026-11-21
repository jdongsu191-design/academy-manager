-- 고등 N제 — 부원장도 요일 부여·응시 초기화를 할 수 있게 (2026-11-21)
-- 원인: naje_actor_ok 가 admin·desk·teacher 만 통과시켜, 부원장(vice_director)이 요일 부여를 저장하면 "권한 없음"으로 막혔다.
--       (부원장은 선생님 화면을 그대로 쓰므로 버튼은 보이는데 서버에서 거절)
-- 이 함수를 쓰는 곳: naje_daily_apply(요일 부여) · naje_day_reset · naje_sub_reset(응시 초기화) · naje_sub_list
create or replace function public.naje_actor_ok(p_actor_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(select 1 from public.users where id = p_actor_id and role in ('admin','desk','teacher','vice_director') and status = 'active');
$$;
