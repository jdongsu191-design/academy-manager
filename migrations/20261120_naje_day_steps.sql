-- 고등 N제 요일 과제 — 단계별 개별 제출 (2026-11-20, 사용자 결정)
-- 전: 하루에 1·2·3단계가 부여되면 세 단계를 한 번에 풀어 한 번에 제출.
-- 후: 같은 날 안에서도 단계마다 따로 풀고 따로 제출한다(제출한 단계는 바로 채점·결과 확인).
-- Supabase SQL Editor 에서 한 번 실행한다. (20261116_naje_daily.sql 위에 얹는다)
--
-- 구조는 그대로: 하루 = naje_submissions 1행(day_id). 표·칸은 추가하지 않는다.
--   · 제출한 단계는 result.done_steps(예: [1,2]) · result.step_at({"1":"시각"}) · result.items(그 단계 채점분) 에 쌓인다
--   · 그날의 모든 단계가 제출되면 그때 naje_finalize 로 하루 전체를 채점해 status='submitted' 로 닫는다(전과 같은 모양)
--   · 그래서 다 끝난 날은 선생님 화면·날짜별 현황이 전과 똑같이 읽는다. 일부만 낸 날은 'in_progress' + done_steps
--   · 옛 방식(하루 통째 제출) RPC 는 그대로 둔다 — 단계가 하나뿐인 날은 계속 그 길을 쓴다
begin;

-- ── 1. 헬퍼 ─────────────────────────────────────────────────
-- 그날 과제 중 한 단계의 실제 문항 번호 (제외 문항 뺀 것)
create or replace function public.naje_day_step_nums(p_student_id uuid, p_day_id uuid, p_step integer) returns integer[]
language sql stable security definer set search_path = public, pg_temp as $$
  select coalesce(array_agg(pr.problem_number order by pr.problem_number), '{}'::integer[])
  from public.naje_daily d
  cross join lateral naje_daily_problems(p_student_id, d.id) pr
  where d.id = p_day_id and d.student_id = p_student_id
    and pr.problem_number = any(naje_items_nums(
          (select coalesce(jsonb_agg(t.v), '[]'::jsonb)
             from jsonb_array_elements(coalesce(d.items, '[]'::jsonb)) as t(v)
            where t.v ? 'step' and (t.v->>'step')::integer = p_step)));
$$;

-- 그날의 단계 목록 (문항이 1개 이상인 단계만)
create or replace function public.naje_day_steps(p_student_id uuid, p_day_id uuid) returns integer[]
language sql stable security definer set search_path = public, pg_temp as $$
  select coalesce(array_agg(q.st order by q.st), '{}'::integer[])
  from (select distinct (t.v->>'step')::integer as st
          from public.naje_daily d
          cross join lateral jsonb_array_elements(coalesce(d.items, '[]'::jsonb)) as t(v)
         where d.id = p_day_id and d.student_id = p_student_id and t.v ? 'step') q
  where cardinality(naje_day_step_nums(p_student_id, p_day_id, q.st)) > 0;
$$;

-- 그 단계가 제출됐는가 (하루 전체가 닫혔거나, done_steps 에 들어 있거나)
create or replace function public.naje_sub_step_done(p_submitted_at timestamptz, p_result jsonb, p_step integer) returns boolean
language sql immutable as $$
  select p_submitted_at is not null or coalesce(coalesce(p_result->'done_steps', '[]'::jsonb) @> to_jsonb(p_step), false);
$$;

-- ── 2. 하루 과제 요약 — parts 에 단계별 상태를 싣는다 (나머지 키는 전과 같다) ──
create or replace function public.naje_day_json(p_student_id uuid, d public.naje_daily) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; has_sub boolean; cnt integer; answered integer := 0; parts jsonb := '[]'::jsonb;
        st integer; itj jsonb; nums integer[]; p_done boolean; p_ans integer; p_cor integer; p_gr integer;
        n_parts integer := 0; n_done integer := 0;
begin
  select count(*) into cnt from naje_daily_problems(p_student_id, d.id);
  select * into sub from public.naje_submissions where student_id = p_student_id and day_id = d.id and not is_void;
  has_sub := found;
  if has_sub and sub.submitted_at is null then
    select count(*) into answered from jsonb_each_text(sub.answers) e where nullif(trim(e.value), '') is not null;
  end if;
  for st in select distinct (t.v->>'step')::integer from jsonb_array_elements(coalesce(d.items, '[]'::jsonb)) as t(v) where t.v ? 'step' order by 1 loop
    select t.v into itj from jsonb_array_elements(coalesce(d.items, '[]'::jsonb)) as t(v) where t.v ? 'step' and (t.v->>'step')::integer = st limit 1;
    nums := naje_day_step_nums(p_student_id, d.id, st);
    p_done := has_sub and naje_sub_step_done(sub.submitted_at, sub.result, st);
    p_ans := 0; p_cor := null; p_gr := null;
    if p_done then
      select count(*) filter (where (t.v->>'is_correct')::boolean), count(*) filter (where (t.v->>'graded')::boolean) into p_cor, p_gr
        from jsonb_array_elements(coalesce(sub.result->'items', '[]'::jsonb)) as t(v) where (t.v->>'no')::integer = any(nums);
    elsif has_sub then
      select count(*) into p_ans from jsonb_each_text(sub.answers) e
       where (case when e.key ~ '^[0-9]+$' then e.key::integer = any(nums) else false end) and nullif(trim(e.value), '') is not null;
    end if;
    if cardinality(nums) > 0 then
      n_parts := n_parts + 1;
      if p_done then n_done := n_done + 1; end if;
    end if;
    parts := parts || jsonb_build_array(jsonb_build_object('step', st, 'name', naje_step_name(st),
      'problems', case when coalesce(jsonb_typeof(itj->'problems') = 'array', false) and jsonb_array_length(itj->'problems') > 0 then itj->'problems' else null end,
      'nums', to_jsonb(nums), 'total', cardinality(nums),
      'status', case when p_done then 'submitted' when p_ans > 0 then 'in_progress' else 'todo' end,
      'answered', p_ans, 'correct_count', p_cor, 'graded', p_gr,
      'submitted_at', case when p_done then coalesce((sub.result->'step_at'->>(st::text))::timestamptz, sub.submitted_at) else null end));
  end loop;
  return jsonb_build_object('day_id', d.id, 'day_no', d.day_no, 'label', naje_day_label(d.day_no), 'due_date', d.due_date,
    'locked', d.due_date > naje_kst_today(), 'overdue', d.due_date < naje_kst_today() and (sub.submitted_at is null),
    'parts', parts, 'parts_total', n_parts, 'parts_done', n_done,
    'total', cnt, 'status', coalesce(sub.status, 'todo'), 'answered', answered,
    'started_at', sub.started_at, 'submitted_at', sub.submitted_at,
    'correct_count', sub.result->'correct_count', 'graded', sub.result->'graded');
end $$;

-- ── 3. 단계 응시 RPC ─────────────────────────────────────────
-- 임시저장: 이 단계 문항의 답만 갈아 끼운다(다른 단계의 답은 그대로). 제출한 단계는 못 고친다
create or replace function public.naje_day_step_save_draft(p_student_id uuid, p_day_id uuid, p_step integer, p_answers jsonb, p_away integer) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; a jsonb := '{}'::jsonb; kept jsonb; kk text; v text; nums integer[];
begin
  select * into sub from public.naje_submissions where student_id = p_student_id and day_id = p_day_id and not is_void for update;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_started'); end if;
  if sub.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted'); end if;
  if naje_sub_step_done(sub.submitted_at, sub.result, p_step) then return jsonb_build_object('ok', false, 'reason', 'step_submitted'); end if;
  if jsonb_typeof(coalesce(p_answers, '{}'::jsonb)) <> 'object' then raise exception '답안 형식 오류'; end if;
  nums := naje_day_step_nums(p_student_id, p_day_id, p_step);
  if cardinality(nums) = 0 then return jsonb_build_object('ok', false, 'reason', 'no_problems'); end if;
  for kk in select jsonb_object_keys(coalesce(p_answers, '{}'::jsonb)) loop
    if kk !~ '^[0-9]+$' then raise exception '유효하지 않은 문항: %', kk; end if;
    if not (kk::integer = any(nums)) then raise exception '유효하지 않은 문항: %', kk; end if;
    v := nullif(trim(coalesce(p_answers->>kk, '')), '');
    if v is null then continue; end if;
    if length(v) > 40 then raise exception '%번 답이 너무 깁니다', kk; end if;
    a := a || jsonb_build_object(kk, v);
  end loop;
  select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb) into kept from jsonb_each(sub.answers) e
   where not (case when e.key ~ '^[0-9]+$' then e.key::integer = any(nums) else false end);
  update public.naje_submissions set answers = kept || a, last_seen_at = now(), away_count = greatest(away_count, coalesce(p_away, 0)) where id = sub.id;
  return jsonb_build_object('ok', true, 'saved', true, 'server_now', now());
end $$;

-- 제출: 이 단계만 채점해 결과에 쌓는다. 그날의 모든 단계가 끝나면 하루를 닫는다
create or replace function public.naje_day_step_submit(p_student_id uuid, p_day_id uuid, p_step integer, p_answers jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; dr jsonb; nums integer[]; pr record; resp text; is_ok boolean;
        n_correct integer := 0; n_total integer := 0; n_graded integer := 0; step_items jsonb := '[]'::jsonb;
        all_items jsonb; res jsonb; done_steps jsonb; step_at jsonb; a_cor integer; a_gr integer; a_tot integer; remaining boolean;
begin
  dr := naje_day_step_save_draft(p_student_id, p_day_id, p_step, p_answers, null);
  if not (dr->>'ok')::boolean then return dr; end if;
  select * into sub from public.naje_submissions where student_id = p_student_id and day_id = p_day_id and not is_void for update;
  nums := naje_day_step_nums(p_student_id, p_day_id, p_step);
  for pr in select q.* from naje_daily_problems(p_student_id, p_day_id) q where q.problem_number = any(nums) order by q.problem_number loop
    n_total := n_total + 1;
    resp := nullif(trim(coalesce(sub.answers->>pr.problem_number::text, '')), '');
    if pr.correct_answer is not null then n_graded := n_graded + 1; end if;
    is_ok := (pr.correct_answer is not null and resp is not null and naje_norm(resp) = naje_norm(pr.correct_answer));
    if is_ok then n_correct := n_correct + 1; end if;
    step_items := step_items || jsonb_build_array(jsonb_build_object('no', pr.problem_number, 'response', resp,
                    'is_correct', is_ok, 'graded', pr.correct_answer is not null, 'qr_url', pr.qr_url));
  end loop;
  res := coalesce(sub.result, '{}'::jsonb);
  select coalesce(jsonb_agg(u.v order by (u.v->>'no')::integer), '[]'::jsonb) into all_items from (
    select t.v from jsonb_array_elements(coalesce(res->'items', '[]'::jsonb)) as t(v) where not ((t.v->>'no')::integer = any(nums))
    union all
    select t.v from jsonb_array_elements(step_items) as t(v)) u;
  done_steps := coalesce(res->'done_steps', '[]'::jsonb);
  if not (done_steps @> to_jsonb(p_step)) then done_steps := done_steps || to_jsonb(p_step); end if;
  step_at := coalesce(res->'step_at', '{}'::jsonb) || jsonb_build_object(p_step::text, now());
  select count(*) filter (where (t.v->>'is_correct')::boolean), count(*) filter (where (t.v->>'graded')::boolean), count(*)
    into a_cor, a_gr, a_tot from jsonb_array_elements(all_items) as t(v);
  res := jsonb_build_object('correct_count', a_cor, 'total', a_tot, 'graded', a_gr, 'items', all_items, 'done_steps', done_steps, 'step_at', step_at);
  update public.naje_submissions set result = res, last_seen_at = now() where id = sub.id;
  select exists(select 1 from unnest(naje_day_steps(p_student_id, p_day_id)) as s(st) where not (done_steps @> to_jsonb(s.st))) into remaining;
  if not remaining then
    perform naje_finalize(sub.id, false);   -- 하루 전체를 다시 채점해 닫는다 (모양은 전과 같다)
    update public.naje_submissions set result = result || jsonb_build_object('done_steps', done_steps, 'step_at', step_at) where id = sub.id;
  end if;
  return jsonb_build_object('ok', true, 'step', p_step, 'day_done', not remaining,
    'correct_count', n_correct, 'total', n_total, 'graded', n_graded, 'items', step_items);
end $$;

-- 결과: 그 단계 문항만 (정답은 내려가지 않는다 — O/X · 내 답 · 해설 링크)
create or replace function public.naje_day_step_get_result(p_student_id uuid, p_day_id uuid, p_step integer) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare sub public.naje_submissions; nums integer[]; its jsonb; n_cor integer; n_gr integer; n_tot integer;
begin
  select * into sub from public.naje_submissions where student_id = p_student_id and day_id = p_day_id and not is_void;
  if not found then return jsonb_build_object('ok', false); end if;
  if not naje_sub_step_done(sub.submitted_at, sub.result, p_step) then return jsonb_build_object('ok', false); end if;
  nums := naje_day_step_nums(p_student_id, p_day_id, p_step);
  select coalesce(jsonb_agg(t.v order by (t.v->>'no')::integer), '[]'::jsonb),
         count(*) filter (where (t.v->>'is_correct')::boolean), count(*) filter (where (t.v->>'graded')::boolean), count(*)
    into its, n_cor, n_gr, n_tot
    from jsonb_array_elements(coalesce(sub.result->'items', '[]'::jsonb)) as t(v) where (t.v->>'no')::integer = any(nums);
  return jsonb_build_object('ok', true, 'step', p_step,
    'submitted_at', coalesce((sub.result->'step_at'->>(p_step::text))::timestamptz, sub.submitted_at),
    'correct_count', n_cor, 'graded', n_gr, 'total', n_tot, 'items', its);
end $$;

-- ── 4. 부여 수정 보호 — 일부 단계만 제출한 날도 '제출된 날'처럼 못 고친다 ──
-- (20261116 의 naje_daily_apply 와 같고, submitted 판정 한 줄만 다르다)
create or replace function public.naje_daily_apply(p_actor_id uuid, p_set_id uuid, p_rows jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare row_ jsonb; dj jsonb; sid uuid; dn integer; keep integer[]; n_up integer := 0; n_del integer := 0; skipped jsonb := '[]';
        existing public.naje_daily; has_sub boolean; submitted boolean; steps_u integer[]; it jsonb;
begin
  if not naje_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  if jsonb_typeof(coalesce(p_rows, '[]')) <> 'array' then raise exception '형식 오류'; end if;
  for row_ in select * from jsonb_array_elements(p_rows) loop
    sid := (row_->>'student_id')::uuid;
    keep := '{}'; steps_u := '{}';
    for dj in select * from jsonb_array_elements(coalesce(row_->'days', '[]')) loop
      dn := (dj->>'day_no')::integer;
      if dn is null or dn < 1 or dn > 5 then raise exception 'day_no 오류'; end if;
      if coalesce(jsonb_typeof(dj->'items') <> 'array', true) or jsonb_array_length(dj->'items') = 0 then continue; end if;   -- 빈 날은 저장하지 않는다
      keep := keep || dn;
      for it in select * from jsonb_array_elements(dj->'items') loop
        if not (it ? 'step') or (it->>'step')::integer < 1 or (it->>'step')::integer > 11 then raise exception 'step 오류'; end if;
        if (it ? 'problems') and jsonb_typeof(it->'problems') <> 'array' then raise exception 'problems 오류'; end if;
        if not ((it->>'step')::integer = any(steps_u)) then steps_u := steps_u || (it->>'step')::integer; end if;
      end loop;
      select * into existing from public.naje_daily where student_id = sid and set_id = p_set_id and day_no = dn;
      if found then
        select exists(select 1 from public.naje_submissions s where s.day_id = existing.id and not s.is_void
                       and (s.submitted_at is not null or jsonb_array_length(coalesce(s.result->'done_steps', '[]'::jsonb)) > 0)) into submitted;
        if submitted and (existing.items <> dj->'items' or existing.due_date <> (dj->>'due_date')::date) then
          skipped := skipped || jsonb_build_array(jsonb_build_object('student_id', sid, 'day_no', dn, 'why', 'submitted'));
          continue;
        end if;
        update public.naje_daily set items = dj->'items', due_date = (dj->>'due_date')::date, template_code = row_->>'template_code', updated_at = now()
         where id = existing.id;
      else
        insert into public.naje_daily(student_id, set_id, day_no, due_date, items, template_code, created_by)
        values (sid, p_set_id, dn, (dj->>'due_date')::date, dj->'items', row_->>'template_code', p_actor_id);
      end if;
      n_up := n_up + 1;
    end loop;
    -- 목록에 없는 날 삭제 (응시 기록 있으면 남긴다)
    for existing in select * from public.naje_daily where student_id = sid and set_id = p_set_id and not (day_no = any(keep)) loop
      select exists(select 1 from public.naje_submissions s where s.day_id = existing.id and not s.is_void) into has_sub;
      if has_sub then
        skipped := skipped || jsonb_build_array(jsonb_build_object('student_id', sid, 'day_no', existing.day_no, 'why', 'has_submission'));
        -- 지우지 못한 날의 단계도 합집합에 남긴다
        for it in select * from jsonb_array_elements(existing.items) loop
          if it ? 'step' and not ((it->>'step')::integer = any(steps_u)) then steps_u := steps_u || (it->>'step')::integer; end if;
        end loop;
        continue;
      end if;
      delete from public.naje_daily where id = existing.id;
      n_del := n_del + 1;
    end loop;
    -- 단계 부여 동기화
    if cardinality(steps_u) > 0 then
      insert into public.naje_assignments(student_id, set_id, steps, excluded_problems)
      values (sid, p_set_id, (select array_agg(x order by x) from unnest(steps_u) x), '{}'::integer[])
      on conflict (student_id, set_id) do update set steps = excluded.steps;
    elsif cardinality(keep) = 0 then
      delete from public.naje_assignments where student_id = sid and set_id = p_set_id
        and not exists(select 1 from public.naje_submissions s where s.student_id = sid and s.set_id = p_set_id and not s.is_void);
    end if;
  end loop;
  return jsonb_build_object('ok', true, 'upserted', n_up, 'deleted', n_del, 'skipped', skipped);
end $$;

-- ── 5. 권한 ─────────────────────────────────────────────────
revoke all on function
  public.naje_day_step_nums(uuid, uuid, integer), public.naje_day_steps(uuid, uuid),
  public.naje_sub_step_done(timestamptz, jsonb, integer),
  public.naje_day_step_save_draft(uuid, uuid, integer, jsonb, integer),
  public.naje_day_step_submit(uuid, uuid, integer, jsonb), public.naje_day_step_get_result(uuid, uuid, integer)
from public;
grant execute on function
  public.naje_day_step_save_draft(uuid, uuid, integer, jsonb, integer),
  public.naje_day_step_submit(uuid, uuid, integer, jsonb), public.naje_day_step_get_result(uuid, uuid, integer)
to anon, authenticated;
commit;
