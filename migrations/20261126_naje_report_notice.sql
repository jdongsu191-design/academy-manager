-- 고등 N제 — 문항 오류 제보 알림 (2026-11-26, 사용자 요청)
-- Supabase SQL Editor 에서 한 번 실행한다. 여러 번 실행해도 된다. (20261124_naje_error_reports.sql 위에 얹는다)
--
-- ① 학생: 내가 보낸 제보가 처리 완료되면 한 번만 '처리됐어요' 팝업을 본다
--    · naje_error_reports.student_notified_at 칸 하나를 더한다. 팝업으로 내려간 제보는 그 자리에서 시각을 찍어 다시 안 뜬다(기기를 바꿔도 한 번)
--    · 처리 완료를 미처리로 되돌리면 칸을 비운다 → 다시 처리 완료하면 다시 한 번 뜬다
--    · 이 파일을 처음 실행할 때 이미 처리 완료였던 제보는 알림 대상에서 뺀다(옛 제보가 한꺼번에 뜨지 않게)
-- ② 관리자: 새 제보가 들어오면 한 번만 팝업을 본다
--    · 서버는 '이 시각 이후에 들어온 미처리 제보' 만 알려 준다(naje_report_new). 어디까지 봤는지는 화면이 브라우저에 기억한다
begin;

do $$
begin
  if not exists(select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'naje_error_reports' and column_name = 'student_notified_at') then
    alter table public.naje_error_reports add column student_notified_at timestamptz;
    update public.naje_error_reports set student_notified_at = now() where status = 'done';
  end if;
end $$;

-- ── 학생: 처리 완료 알림 받기 (받는 순간 '알렸음' 으로 찍는다) ──
create or replace function public.naje_report_notices(p_student_id uuid) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare v_rows jsonb;
begin
  if not exists(select 1 from users where id = p_student_id and role = 'student' and status = 'active') then
    return jsonb_build_object('ok', false, 'rows', '[]'::jsonb);
  end if;
  with hit as (
    update naje_error_reports r set student_notified_at = now()
     where r.student_id = p_student_id and r.status = 'done' and r.student_notified_at is null
    returning r.set_id, r.problem_number, r.reason, r.handled_at
  )
  select coalesce(jsonb_agg(jsonb_build_object('set_title', s.title, 'no', h.problem_number, 'reason', h.reason, 'handled_at', h.handled_at)
                            order by h.handled_at desc, h.problem_number), '[]'::jsonb)
    into v_rows
    from hit h left join naje_sets s on s.id = h.set_id;
  return jsonb_build_object('ok', true, 'rows', v_rows);
end $$;

-- ── 관리자: p_since 이후에 들어온 미처리 제보 (p_since 가 없으면 미처리 전부) ──
create or replace function public.naje_report_new(p_actor_id uuid, p_since timestamptz default null) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare v_n integer; v_last timestamptz; v_rows jsonb;
begin
  if not naje_report_admin_ok(p_actor_id) then return jsonb_build_object('ok', false, 'count', 0, 'rows', '[]'::jsonb); end if;
  select count(*)::integer, max(created_at) into v_n, v_last
    from naje_error_reports where status = 'open' and (p_since is null or created_at > p_since);
  select coalesce(jsonb_agg(x.j order by x.created_at desc), '[]'::jsonb) into v_rows
    from (select r.created_at, jsonb_build_object('set_title', s.title, 'no', r.problem_number, 'reason', r.reason,
                   'student_name', u.name, 'created_at', r.created_at) as j
            from naje_error_reports r
            left join naje_sets s on s.id = r.set_id
            left join users u on u.id = r.student_id
           where r.status = 'open' and (p_since is null or r.created_at > p_since)
           order by r.created_at desc limit 8) x;
  return jsonb_build_object('ok', true, 'count', v_n, 'last', v_last, 'rows', v_rows);
end $$;

-- ── 관리자: 처리 완료 / 되돌리기 — 되돌리면 학생 알림 칸을 비운다 (그 한 줄만 20261124 와 다르다) ──
create or replace function public.naje_report_set_status(p_actor_id uuid, p_ids uuid[], p_status text, p_note text default null)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare v_n integer; v_note text := nullif(left(btrim(coalesce(p_note, '')), 500), '');
begin
  if not naje_report_admin_ok(p_actor_id) then raise exception '권한 없음'; end if;
  if p_status not in ('open','done') then raise exception '상태 값이 올바르지 않습니다'; end if;
  update naje_error_reports
     set status = p_status,
         handled_by = case when p_status = 'done' then p_actor_id else null end,
         handled_at = case when p_status = 'done' then now() else null end,
         admin_note = case when p_status = 'done' then coalesce(v_note, admin_note) else admin_note end,
         student_notified_at = null,
         updated_at = now()
   where id = any(coalesce(p_ids, '{}'::uuid[])) and status <> p_status;
  get diagnostics v_n = row_count;
  return jsonb_build_object('ok', true, 'updated', v_n);
end $$;

revoke all on function public.naje_report_notices(uuid), public.naje_report_new(uuid, timestamptz) from public;
grant execute on function public.naje_report_notices(uuid), public.naje_report_new(uuid, timestamptz) to anon, authenticated;

commit;
