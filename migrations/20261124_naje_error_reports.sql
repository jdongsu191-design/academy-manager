-- 고등 N제 — 문항 오류 제보 (2026-11-24)
-- Supabase SQL Editor 에서 한 번 실행한다. 여러 번 실행해도 된다.
--
-- 학생이 푸는 중(문제 카드)·제출 후(답안 확인 화면)에 문항 오류를 제보하고, 관리자가 'N제 문제 모음 → 문항 오류 제보' 탭에서 모아 본다.
-- · 표는 RLS 를 켜고 정책을 두지 않는다 → 화면은 아래 RPC(security definer)로만 읽고 쓴다.
-- · 같은 학생이 같은 문항·같은 사유로 아직 처리 전인 제보를 또 보내면 새 줄을 만들지 않고 내용만 고친다(도배 방지).
-- · 사유: book = 책과 문제가 다름 / answer = 해설과 답이 다름 / invisible = 문제가 안 보임 / custom = 직접 작성(내용 필수)
begin;

create table if not exists public.naje_error_reports (
  id             uuid primary key default gen_random_uuid(),
  student_id     uuid not null references public.users(id) on delete cascade,
  set_id         uuid not null references public.naje_sets(id) on delete cascade,
  problem_number integer not null,
  reason         text not null check (reason in ('book','answer','invisible','custom')),
  detail         text,
  phase          text not null default 'solving' check (phase in ('solving','result')),   -- 푸는 중 / 제출 후
  day_id         uuid,            -- 요일 과제에서 보냈으면 그 날(참고용, FK 없음)
  step           integer,         -- 단계 응시에서 보냈으면 그 단계(참고용)
  my_answer      text,            -- 제보할 때 학생이 적어 둔 답(참고용)
  status         text not null default 'open' check (status in ('open','done')),
  handled_by     uuid,
  handled_at     timestamptz,
  admin_note     text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index if not exists naje_err_status_ix on public.naje_error_reports(status, created_at desc);
create index if not exists naje_err_problem_ix on public.naje_error_reports(set_id, problem_number);
alter table public.naje_error_reports enable row level security;

-- ── 관리자 판정 ─────────────────────────────────────────────
create or replace function public.naje_report_admin_ok(p_actor_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(select 1 from public.users where id = p_actor_id and role = 'admin' and status = 'active');
$$;

-- ── 학생: 제보 보내기 ───────────────────────────────────────
create or replace function public.naje_report_submit(
  p_student_id uuid, p_set_id uuid, p_no integer, p_reason text, p_detail text default null,
  p_phase text default 'solving', p_day_id uuid default null, p_step integer default null, p_answer text default null)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
  v_detail text := nullif(left(btrim(coalesce(p_detail, '')), 500), '');
  v_phase  text := case when p_phase = 'result' then 'result' else 'solving' end;
  v_ans    text := nullif(left(btrim(coalesce(p_answer, '')), 60), '');
  v_id     uuid;
begin
  if not exists(select 1 from users where id = p_student_id and role = 'student' and status = 'active') then
    return jsonb_build_object('ok', false, 'msg', '학생 계정을 확인할 수 없습니다');
  end if;
  if p_reason is null or p_reason not in ('book','answer','invisible','custom') then
    return jsonb_build_object('ok', false, 'msg', '제보 항목을 골라 주세요');
  end if;
  if p_reason = 'custom' and v_detail is null then
    return jsonb_build_object('ok', false, 'msg', '내용을 적어 주세요');
  end if;
  if not exists(select 1 from naje_problems where set_id = p_set_id and problem_number = p_no) then
    return jsonb_build_object('ok', false, 'msg', '문항을 찾을 수 없습니다');
  end if;
  -- 이 학생에게 부여된 N제인지(단계 부여 또는 요일 부여)
  if not exists(select 1 from naje_assignments where student_id = p_student_id and set_id = p_set_id)
     and not exists(select 1 from naje_daily where student_id = p_student_id and set_id = p_set_id) then
    return jsonb_build_object('ok', false, 'msg', '부여되지 않은 N제입니다');
  end if;

  select id into v_id from naje_error_reports
   where student_id = p_student_id and set_id = p_set_id and problem_number = p_no and reason = p_reason and status = 'open'
   order by created_at desc limit 1;
  if v_id is not null then
    update naje_error_reports
       set detail = coalesce(v_detail, detail), phase = v_phase, my_answer = coalesce(v_ans, my_answer),
           day_id = coalesce(p_day_id, day_id), step = coalesce(p_step, step), updated_at = now()
     where id = v_id;
    return jsonb_build_object('ok', true, 'id', v_id, 'dup', true);
  end if;
  insert into naje_error_reports(student_id, set_id, problem_number, reason, detail, phase, day_id, step, my_answer)
  values (p_student_id, p_set_id, p_no, p_reason, v_detail, v_phase, p_day_id, p_step, v_ans)
  returning id into v_id;
  return jsonb_build_object('ok', true, 'id', v_id, 'dup', false);
end $$;

-- ── 관리자: 처리 전 건수(탭 뱃지) ───────────────────────────
create or replace function public.naje_report_count(p_actor_id uuid) returns integer
language sql stable security definer set search_path = public, pg_temp as $$
  select case when not naje_report_admin_ok(p_actor_id) then 0
              else (select count(*)::integer from naje_error_reports where status = 'open') end;
$$;

-- ── 관리자: 목록 ────────────────────────────────────────────
-- p_status: 'open' | 'done' | 'all'. 최근 것부터 최대 1000건.
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

-- ── 관리자: 처리 완료 / 되돌리기 (여러 건 한 번에) ─────────
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
         updated_at = now()
   where id = any(coalesce(p_ids, '{}'::uuid[])) and status <> p_status;
  get diagnostics v_n = row_count;
  return jsonb_build_object('ok', true, 'updated', v_n);
end $$;

revoke all on function
  public.naje_report_admin_ok(uuid), public.naje_report_submit(uuid, uuid, integer, text, text, text, uuid, integer, text),
  public.naje_report_count(uuid), public.naje_report_list(uuid, text), public.naje_report_set_status(uuid, uuid[], text, text)
  from public;
grant execute on function
  public.naje_report_submit(uuid, uuid, integer, text, text, text, uuid, integer, text),
  public.naje_report_count(uuid), public.naje_report_list(uuid, text), public.naje_report_set_status(uuid, uuid[], text, text)
  to anon, authenticated;

commit;
