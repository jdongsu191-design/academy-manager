-- 고등 일일N제 v2 — 응시를 베티모의고사와 같은 방식으로.
-- Supabase SQL Editor 에서 한 번 실행한다.
--
-- 유지: naje_sets · naje_problems · naje_folders · naje_assignments(단계 부여) · naje_answers(옛 답안, 더 쓰지 않음)
-- 신설: naje_submissions — 학생 × N제 × 단계마다 응시 1행. 서버가 시작·임시저장·채점을 맡는다.
--   · 응시 자격 = naje_assignments 에 그 단계가 들어 있을 것. 제외 문항(excluded_problems)은 서버가 뺀다
--   · 채점은 naje_finalize 한 곳. 비교 규칙은 기존 화면과 같다(공백 제거 · ①~⑤ → 1~5 · 소문자)
--   · 정답은 학생 RPC 로 절대 내려가지 않는다 (결과도 O/X · 내 답 · 해설 링크만)
--   · 초기화는 is_void (기록이 남는다). 제한시간은 없다
--   · 호출 규약·반환 모양은 bety_omr_* / ko_* 와 같게 (actor/student id 를 넘긴다 — 같은 구조적 한계)
begin;

-- ── 1. 응시 기록 ─────────────────────────────────────────────
create table if not exists public.naje_submissions (
  id             uuid primary key default gen_random_uuid(),
  student_id     uuid not null references public.users(id) on delete cascade,
  set_id         uuid not null references public.naje_sets(id) on delete cascade,
  step           integer not null check (step between 1 and 11),
  status         text not null default 'in_progress' check (status in ('in_progress','submitted')),
  started_at     timestamptz not null default now(),
  submitted_at   timestamptz,
  last_seen_at   timestamptz,
  away_count     integer not null default 0,
  auto_submitted boolean not null default false,
  answers        jsonb not null default '{}'::jsonb,   -- {"문항번호": "답"}
  result         jsonb,                                -- 채점 결과 (naje_finalize)
  is_void        boolean not null default false,
  void_reason    text,
  voided_at      timestamptz,
  voided_by      uuid,
  created_at     timestamptz not null default now()
);
create unique index if not exists naje_sub_active_uk on public.naje_submissions(student_id, set_id, step) where not is_void;
create index if not exists naje_sub_set_ix on public.naje_submissions(set_id);
create index if not exists naje_sub_student_ix on public.naje_submissions(student_id);

-- ── 2. 공통 헬퍼 ─────────────────────────────────────────────
-- 단계 → 문항 번호 범위 (8문항씩 10단계, 81번부터 킬러)
create or replace function public.naje_step_lo(p_step integer) returns integer
language sql immutable as $$ select (p_step - 1) * 8 + 1 $$;
create or replace function public.naje_step_hi(p_step integer) returns integer
language sql immutable as $$ select case when p_step >= 11 then 9999 else p_step * 8 end $$;

create or replace function public.naje_step_name(p_step integer) returns text
language sql immutable as $$
  select case p_step when 1 then '내신3점' when 2 then '내신3점' when 3 then '모고3점' when 4 then '모고3점'
    when 5 then '내신4점' when 6 then '내신4점' when 7 then '모고쉬사' when 8 then '모고어사'
    when 9 then '내신심화' when 10 then '내신심화' else '모고킬러' end $$;
create or replace function public.naje_step_type(p_step integer) returns text
language sql immutable as $$
  select case when p_step in (1,2,5,6,9,10) then '내신' else '모고' end $$;

-- 답 비교 규칙 — 기존 화면의 normalizeAnswer 와 같다
create or replace function public.naje_norm(p text) returns text
language sql immutable as $$
  select lower(translate(regexp_replace(coalesce(p,''), '\s+', '', 'g'), '①②③④⑤', '12345')) $$;

create or replace function public.naje_actor_ok(p_actor_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(select 1 from public.users where id = p_actor_id and role in ('admin','desk','teacher') and status = 'active');
$$;

-- 이 학생이 이 N제의 이 단계를 풀 수 있는가 (부여 + 재원)
create or replace function public.naje_eligible(p_student_id uuid, p_set_id uuid, p_step integer) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(
    select 1 from public.naje_assignments a
    join public.users u on u.id = a.student_id and u.role = 'student' and u.status = 'active'
    where a.student_id = p_student_id and a.set_id = p_set_id
      and p_step = any(coalesce(a.steps, '{}'::integer[])));
$$;

-- 단계의 실제 문항 (제외 문항 뺀 것) — 번호 순
create or replace function public.naje_step_problems(p_student_id uuid, p_set_id uuid, p_step integer)
returns table(id uuid, problem_number integer, image_url text, qr_url text, correct_answer text, level_name text)
language sql stable security definer set search_path = public, pg_temp as $$
  select p.id, p.problem_number, p.image_url, p.qr_url, p.correct_answer, p.level_name
  from public.naje_problems p
  left join public.naje_assignments a on a.student_id = p_student_id and a.set_id = p_set_id
  where p.set_id = p_set_id
    and p.problem_number between naje_step_lo(p_step) and naje_step_hi(p_step)
    and not (p.problem_number = any(coalesce(a.excluded_problems, '{}'::integer[])))
  order by p.problem_number;
$$;

-- 채점 — 한 곳. 결과: correct_count · total · graded(정답이 있는 문항 수) · items[no, response, is_correct, graded, qr_url]
create or replace function public.naje_finalize(p_sub_id uuid, p_auto boolean) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; pr record; resp text; ok boolean;
        correct integer := 0; total integer := 0; graded integer := 0; items jsonb := '[]'; res jsonb;
begin
  select * into sub from public.naje_submissions where id = p_sub_id for update;
  if not found then raise exception '응시 기록이 없습니다'; end if;
  if sub.submitted_at is not null then return sub.result; end if;
  for pr in select * from naje_step_problems(sub.student_id, sub.set_id, sub.step) loop
    total := total + 1;
    resp := nullif(trim(coalesce(sub.answers->>pr.problem_number::text, '')), '');
    if pr.correct_answer is not null then graded := graded + 1; end if;
    ok := (pr.correct_answer is not null and resp is not null and naje_norm(resp) = naje_norm(pr.correct_answer));
    if ok then correct := correct + 1; end if;
    items := items || jsonb_build_array(jsonb_build_object('no', pr.problem_number, 'response', resp,
               'is_correct', ok, 'graded', pr.correct_answer is not null, 'qr_url', pr.qr_url));
  end loop;
  res := jsonb_build_object('correct_count', correct, 'total', total, 'graded', graded, 'items', items);
  update public.naje_submissions set status = 'submitted', submitted_at = now(), auto_submitted = p_auto, result = res
   where id = p_sub_id;
  return res;
end $$;

-- ── 3. 학생 RPC (bety_omr_* / ko_* 와 같은 호출 규약) ───────
-- 부여된 N제와 단계 목록. 단계마다 문항 수·상태·점수
create or replace function public.naje_list_for_student(p_student_id uuid) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare u public.users; a record; st integer; sets jsonb := '[]'; steps jsonb; cnt integer; sub public.naje_submissions; answered integer;
begin
  select * into u from public.users where id = p_student_id and role = 'student' and status = 'active';
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_student'); end if;
  for a in select s.id, s.title, s.target_grade, s.folder_name, s.week_number, s.subject, s.created_at, asg.steps as asg_steps
           from public.naje_assignments asg join public.naje_sets s on s.id = asg.set_id
           where asg.student_id = p_student_id order by s.created_at desc loop
    steps := '[]';
    for st in select unnest(coalesce(a.asg_steps, '{}'::integer[])) order by 1 loop
      select count(*) into cnt from naje_step_problems(p_student_id, a.id, st);
      if cnt = 0 then continue; end if;   -- 전부 제외됐거나 문항이 없는 단계는 숨긴다
      select * into sub from public.naje_submissions where student_id = p_student_id and set_id = a.id and step = st and not is_void;
      answered := 0;
      if found and sub.submitted_at is null then
        select count(*) into answered from jsonb_each_text(sub.answers) e where nullif(trim(e.value), '') is not null;
      end if;
      steps := steps || jsonb_build_array(jsonb_build_object('step', st, 'name', naje_step_name(st), 'type', naje_step_type(st),
        'total', cnt, 'status', coalesce(sub.status, 'todo'), 'answered', answered,
        'started_at', sub.started_at, 'submitted_at', sub.submitted_at,
        'correct_count', sub.result->'correct_count', 'graded', sub.result->'graded'));
      sub := null;
    end loop;
    if jsonb_array_length(steps) = 0 then continue; end if;
    sets := sets || jsonb_build_array(jsonb_build_object('id', a.id, 'title', a.title, 'target_grade', a.target_grade,
      'folder_name', a.folder_name, 'week_number', a.week_number, 'subject', a.subject, 'created_at', a.created_at, 'steps', steps));
  end loop;
  return jsonb_build_object('ok', true, 'sets', sets, 'server_now', now());
end $$;

-- 단계의 문항 (정답 없음). 응시 전에 시작 안내에 쓰고, 시작 뒤 화면에 쓴다
create or replace function public.naje_get_step(p_student_id uuid, p_set_id uuid, p_step integer) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare s public.naje_sets; sub public.naje_submissions; probs jsonb;
begin
  select * into s from public.naje_sets where id = p_set_id;
  if not found then return jsonb_build_object('ok', false, 'reason', 'no_set'); end if;
  if not naje_eligible(p_student_id, p_set_id, p_step) then return jsonb_build_object('ok', false, 'reason', 'not_eligible'); end if;
  select coalesce(jsonb_agg(jsonb_build_object('no', pr.problem_number, 'image_url', pr.image_url, 'level_name', pr.level_name) order by pr.problem_number), '[]')
    into probs from naje_step_problems(p_student_id, p_set_id, p_step) pr;
  select * into sub from public.naje_submissions where student_id = p_student_id and set_id = p_set_id and step = p_step and not is_void;
  return jsonb_build_object('ok', true, 'submitted', sub.submitted_at is not null, 'status', coalesce(sub.status, 'todo'),
    'set', jsonb_build_object('id', s.id, 'title', s.title, 'target_grade', s.target_grade, 'week_number', s.week_number),
    'step', jsonb_build_object('step', p_step, 'name', naje_step_name(p_step), 'type', naje_step_type(p_step)),
    'problems', probs);
end $$;

create or replace function public.naje_start(p_student_id uuid, p_set_id uuid, p_step integer) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions;
begin
  if not naje_eligible(p_student_id, p_set_id, p_step) then return jsonb_build_object('ok', false, 'reason', 'not_eligible'); end if;
  if not exists(select 1 from naje_step_problems(p_student_id, p_set_id, p_step)) then return jsonb_build_object('ok', false, 'reason', 'no_problems'); end if;
  insert into public.naje_submissions(student_id, set_id, step, status) values(p_student_id, p_set_id, p_step, 'in_progress')
    on conflict (student_id, set_id, step) where not is_void do nothing;
  select * into sub from public.naje_submissions where student_id = p_student_id and set_id = p_set_id and step = p_step and not is_void for update;
  if sub.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted', 'result', sub.result); end if;
  update public.naje_submissions set last_seen_at = now() where id = sub.id;
  return jsonb_build_object('ok', true, 'submission_id', sub.id, 'server_now', now(), 'started_at', sub.started_at, 'answers', sub.answers);
end $$;

-- 임시저장 — 답은 그 단계의 (제외되지 않은) 문항 번호만, 40자 이내. 빈 답은 지운다
create or replace function public.naje_save_draft(p_student_id uuid, p_set_id uuid, p_step integer, p_answers jsonb, p_away integer) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; a jsonb := '{}'; kk text; v text; nums integer[];
begin
  select * into sub from public.naje_submissions where student_id = p_student_id and set_id = p_set_id and step = p_step and not is_void for update;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_started'); end if;
  if sub.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted', 'result', sub.result); end if;
  if jsonb_typeof(coalesce(p_answers, '{}')) <> 'object' then raise exception '답안 형식 오류'; end if;
  select coalesce(array_agg(problem_number), '{}') into nums from naje_step_problems(p_student_id, p_set_id, p_step);
  for kk in select jsonb_object_keys(coalesce(p_answers, '{}')) loop
    if kk !~ '^[0-9]+$' or not (kk::integer = any(nums)) then raise exception '유효하지 않은 문항: %', kk; end if;
    v := nullif(trim(coalesce(p_answers->>kk, '')), '');
    if v is null then continue; end if;
    if length(v) > 40 then raise exception '%번 답이 너무 깁니다', kk; end if;
    a := a || jsonb_build_object(kk, v);
  end loop;
  update public.naje_submissions set answers = a, last_seen_at = now(), away_count = greatest(away_count, coalesce(p_away, 0)) where id = sub.id;
  return jsonb_build_object('ok', true, 'saved', true, 'server_now', now());
end $$;

create or replace function public.naje_submit(p_student_id uuid, p_set_id uuid, p_step integer, p_answers jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; d jsonb;
begin
  select * into sub from public.naje_submissions where student_id = p_student_id and set_id = p_set_id and step = p_step and not is_void;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_started'); end if;
  if sub.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted', 'result', sub.result); end if;
  d := naje_save_draft(p_student_id, p_set_id, p_step, p_answers, null);
  if not (d->>'ok')::boolean then return d; end if;
  return jsonb_build_object('ok', true) || naje_finalize(sub.id, false);
end $$;

create or replace function public.naje_get_result(p_student_id uuid, p_set_id uuid, p_step integer) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select coalesce((select jsonb_build_object('ok', true, 'submitted_at', s.submitted_at) || s.result
                   from public.naje_submissions s
                   where s.student_id = p_student_id and s.set_id = p_set_id and s.step = p_step and not s.is_void and s.submitted_at is not null),
                  jsonb_build_object('ok', false));
$$;

-- ── 4. 선생님·관리자 RPC ─────────────────────────────────────
-- N제 하나의 응시 현황 (학생 × 단계)
create or replace function public.naje_sub_list(p_actor_id uuid, p_set_id uuid) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select case when not naje_actor_ok(p_actor_id) then '[]'::jsonb else
    coalesce((select jsonb_agg(jsonb_build_object('id', s.id, 'student_id', u.id, 'name', u.name, 'school', u.school, 'grade', u.grade,
      'teacher_id', u.teacher_id, 'step', s.step, 'step_name', naje_step_name(s.step), 'status', s.status,
      'started_at', s.started_at, 'submitted_at', s.submitted_at, 'away_count', s.away_count,
      'correct_count', s.result->'correct_count', 'total', s.result->'total', 'graded', s.result->'graded')
      order by u.name, s.step)
     from public.naje_submissions s join public.users u on u.id = s.student_id
     where s.set_id = p_set_id and not s.is_void), '[]'::jsonb) end;
$$;

-- 초기화 — 학생이 그 단계를 다시 풀 수 있게. 기록은 is_void 로 남는다. p_step 이 null 이면 그 N제 전체
create or replace function public.naje_sub_reset(p_actor_id uuid, p_set_id uuid, p_student_id uuid, p_step integer, p_reason text) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare n integer;
begin
  if not naje_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  update public.naje_submissions set is_void = true, void_reason = p_reason, voided_at = now(), voided_by = p_actor_id
   where set_id = p_set_id and student_id = p_student_id and not is_void and (p_step is null or step = p_step);
  get diagnostics n = row_count;
  return jsonb_build_object('ok', n > 0, 'count', n);
end $$;

-- ── 5. 권한 ─────────────────────────────────────────────────
revoke all on function
  public.naje_actor_ok(uuid), public.naje_eligible(uuid, uuid, integer), public.naje_step_problems(uuid, uuid, integer),
  public.naje_finalize(uuid, boolean),
  public.naje_list_for_student(uuid), public.naje_get_step(uuid, uuid, integer), public.naje_start(uuid, uuid, integer),
  public.naje_save_draft(uuid, uuid, integer, jsonb, integer), public.naje_submit(uuid, uuid, integer, jsonb),
  public.naje_get_result(uuid, uuid, integer), public.naje_sub_list(uuid, uuid), public.naje_sub_reset(uuid, uuid, uuid, integer, text)
from public;
grant execute on function
  public.naje_list_for_student(uuid), public.naje_get_step(uuid, uuid, integer), public.naje_start(uuid, uuid, integer),
  public.naje_save_draft(uuid, uuid, integer, jsonb, integer), public.naje_submit(uuid, uuid, integer, jsonb),
  public.naje_get_result(uuid, uuid, integer), public.naje_sub_list(uuid, uuid), public.naje_sub_reset(uuid, uuid, uuid, integer, text)
to anon, authenticated;
-- 결과 화면(선생님·관리자)은 기존처럼 표를 직접 읽는다 (다른 naje_* 표와 같은 권한)
grant select on public.naje_submissions to anon, authenticated;
commit;
