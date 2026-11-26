-- 고등 N제 — 문항 오류 제보: 처리 완료할 때 학생에게 보내는 메시지 (2026-11-26, 사용자 요청)
-- Supabase SQL Editor 에서 한 번 실행한다. 여러 번 실행해도 된다. (20261126_naje_report_notice.sql 위에 얹는다)
--
-- · naje_error_reports.student_message 칸 하나를 더한다. 관리자가 처리 완료하면서 적으면, 학생의 '처리됐어요' 팝업에 함께 보인다
-- · 관리자 메모(admin_note)는 전과 같이 내부용이다 — 학생에게 내려가지 않는다
-- · 미처리로 되돌리면 메시지를 비운다(다시 처리할 때 새로 적는다)
-- · naje_report_set_status 에 p_message 인자를 더한다(기본 null) — 인자 4개로 부르던 옛 화면도 그대로 동작한다
begin;

alter table public.naje_error_reports add column if not exists student_message text;

-- ── 관리자: 처리 완료 / 되돌리기 ─────────────────────────────
drop function if exists public.naje_report_set_status(uuid, uuid[], text, text);
create or replace function public.naje_report_set_status(p_actor_id uuid, p_ids uuid[], p_status text, p_note text default null, p_message text default null)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare v_n integer; v_note text := nullif(left(btrim(coalesce(p_note, '')), 500), '');
        v_msg text := nullif(left(btrim(coalesce(p_message, '')), 500), '');
begin
  if not naje_report_admin_ok(p_actor_id) then raise exception '권한 없음'; end if;
  if p_status not in ('open','done') then raise exception '상태 값이 올바르지 않습니다'; end if;
  update naje_error_reports
     set status = p_status,
         handled_by = case when p_status = 'done' then p_actor_id else null end,
         handled_at = case when p_status = 'done' then now() else null end,
         admin_note = case when p_status = 'done' then coalesce(v_note, admin_note) else admin_note end,
         student_message = case when p_status = 'done' then v_msg else null end,
         student_notified_at = null,
         updated_at = now()
   where id = any(coalesce(p_ids, '{}'::uuid[])) and status <> p_status;
  get diagnostics v_n = row_count;
  return jsonb_build_object('ok', true, 'updated', v_n);
end $$;

-- ── 학생: 처리 완료 알림 받기 — 메시지를 함께 내려 준다 ──────
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
    returning r.set_id, r.problem_number, r.reason, r.handled_at, r.student_message
  )
  select coalesce(jsonb_agg(jsonb_build_object('set_title', s.title, 'no', h.problem_number, 'reason', h.reason, 'handled_at', h.handled_at,
                                               'message', h.student_message)
                            order by h.handled_at desc, h.problem_number), '[]'::jsonb)
    into v_rows
    from hit h left join naje_sets s on s.id = h.set_id;
  return jsonb_build_object('ok', true, 'rows', v_rows);
end $$;

-- ── 관리자: 목록 — student_message 한 칸만 더 싣는다 (나머지는 20261124 와 같다) ──
create or replace function public.naje_report_list(p_actor_id uuid, p_status text default 'open')
returns jsonb language plpgsql stable security definer set search_path = public, pg_temp as $$
declare v_rows jsonb; v_open integer; v_done integer;
begin
  if not naje_report_admin_ok(p_actor_id) then raise exception '권한 없음'; end if;
  select count(*) filter (where status = 'open'), count(*) filter (where status = 'done') into v_open, v_done from naje_error_reports;
  select coalesce(jsonb_agg(x.j order by x.created_at desc), '[]'::jsonb) into v_rows
    from (
      select r.created_at,
             jsonb_build_object(
               'id', r.id, 'created_at', r.created_at, 'updated_at', r.updated_at,
               'set_id', r.set_id, 'set_title', s.title, 'grade', s.target_grade,
               'no', r.problem_number, 'reason', r.reason, 'detail', r.detail, 'phase', r.phase,
               'step', r.step, 'my_answer', r.my_answer,
               'status', r.status, 'handled_at', r.handled_at, 'handled_by_name', hb.name, 'admin_note', r.admin_note,
               'student_message', r.student_message,
               'student_id', r.student_id, 'student_name', u.name, 'school', u.school, 'student_grade', u.grade,
               'teacher_name', t.name,
               'image_url', p.image_url, 'correct_answer', p.correct_answer, 'level_name', p.level_name, 'qr_url', p.qr_url
             ) as j
        from naje_error_reports r
        join naje_sets s on s.id = r.set_id
        left join users u on u.id = r.student_id
        left join users t on t.id = u.teacher_id
        left join users hb on hb.id = r.handled_by
        left join lateral (select pp.image_url, pp.correct_answer, pp.level_name, pp.qr_url from naje_problems pp
                            where pp.set_id = r.set_id and pp.problem_number = r.problem_number limit 1) p on true
       where coalesce(p_status, 'open') = 'all' or r.status = coalesce(p_status, 'open')
       order by r.created_at desc
       limit 1000
    ) x;
  return jsonb_build_object('ok', true, 'open', v_open, 'done', v_done, 'rows', v_rows);
end $$;

revoke all on function public.naje_report_set_status(uuid, uuid[], text, text, text) from public;
grant execute on function public.naje_report_set_status(uuid, uuid[], text, text, text) to anon, authenticated;

commit;
