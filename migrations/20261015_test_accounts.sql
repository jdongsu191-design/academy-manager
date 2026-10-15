-- 테스트 계정 (2026-10-15)
-- · users.is_test : 집계(월별 수강인원·계정 현황·포텐셜 순위·입퇴원 통계)에서 빼는 표시
-- · test_account_purge : 테스트 계정과 그 계정이 남긴 기록을 한 번에 지운다 (비활성·퇴원이 아니라 완전 삭제)
--   - public 스키마의 uuid 컬럼 중 student_id / teacher_id / user_id / desk_id / from_teacher_id / to_teacher_id 가
--     그 계정을 가리키는 행은 지우고, created_by / sent_by / voided_by / linked_student_id 는 null 로 비운다
--   - is_test 가 아닌 계정은 절대 지우지 않는다 · 호출자는 마스터 관리자여야 한다
-- Supabase SQL Editor 에서 전체 선택(Ctrl+A) 후 한 번 실행.

alter table public.users add column if not exists is_test boolean not null default false;

create or replace function public.test_account_purge(p_actor_id uuid, p_user_id uuid) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  actor public.users;
  target public.users;
  r record;
  n bigint;
  total bigint := 0;
  detail jsonb := '{}'::jsonb;
  errors jsonb := '[]'::jsonb;
  del_cols text[] := array['student_id','teacher_id','user_id','desk_id','from_teacher_id','to_teacher_id'];
  null_cols text[] := array['created_by','sent_by','voided_by','linked_student_id','approved_by','updated_by'];
begin
  select * into actor from public.users where id = p_actor_id;
  if actor.id is null or actor.role <> 'admin' or coalesce(actor.is_master, false) = false then
    return jsonb_build_object('ok', false, 'reason', 'not_master');
  end if;
  select * into target from public.users where id = p_user_id;
  if target.id is null then return jsonb_build_object('ok', false, 'reason', 'not_found'); end if;
  if coalesce(target.is_test, false) = false then return jsonb_build_object('ok', false, 'reason', 'not_test'); end if;

  -- 1) 그 계정을 가리키는 행 삭제
  for r in
    select c.table_name, c.column_name
    from information_schema.columns c
    where c.table_schema = 'public' and c.data_type = 'uuid'
      and c.table_name <> 'users' and c.column_name = any(del_cols)
      and exists (select 1 from information_schema.tables t where t.table_schema = 'public' and t.table_name = c.table_name and t.table_type = 'BASE TABLE')
  loop
    begin
      execute format('delete from public.%I where %I = $1', r.table_name, r.column_name) using p_user_id;
      get diagnostics n = row_count;
      if n > 0 then
        detail := detail || jsonb_build_object(r.table_name || '.' || r.column_name, n);
        total := total + n;
      end if;
    exception when others then
      errors := errors || jsonb_build_array(r.table_name || '.' || r.column_name || ': ' || sqlerrm);
    end;
  end loop;

  -- 2) 참조만 끊는 컬럼은 null 로
  for r in
    select c.table_name, c.column_name
    from information_schema.columns c
    where c.table_schema = 'public' and c.data_type = 'uuid'
      and c.column_name = any(null_cols)
      and exists (select 1 from information_schema.tables t where t.table_schema = 'public' and t.table_name = c.table_name and t.table_type = 'BASE TABLE')
  loop
    begin
      execute format('update public.%I set %I = null where %I = $1', r.table_name, r.column_name, r.column_name) using p_user_id;
    exception when others then
      errors := errors || jsonb_build_array(r.table_name || '.' || r.column_name || ': ' || sqlerrm);
    end;
  end loop;

  -- 3) users 안의 자기참조 (테스트 선생님을 담당으로 둔 학생 등)
  update public.users set teacher_id = null where teacher_id = p_user_id;

  -- 4) 계정 삭제
  delete from public.users where id = p_user_id;
  return jsonb_build_object('ok', true, 'name', target.name, 'role', target.role, 'deleted_rows', total, 'detail', detail, 'errors', errors);
end $$;

grant execute on function public.test_account_purge(uuid, uuid) to anon, authenticated;
