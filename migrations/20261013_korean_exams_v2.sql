-- 국어 모의고사 v2 — 베티모의고사와 같은 흐름으로.
-- Supabase SQL Editor 에서 한 번 실행한다. 20261012_korean_exams.sql 이 먼저 적용돼 있어야 한다.
--
-- 바뀌는 것
--   · 시험지: 회차(session_date)·학교급·학년·선택과목·제한시간·발행 — 베티와 같은 칸
--   · 응시 대상: 학생을 고르지 않는다. 베티 참여(bety_yn) 학생 중 학교급·학년이 맞으면 자동
--   · 인증: 아이디·비밀번호 토큰 로그인을 없애고 베티처럼 actor/student id 를 넘긴다
--     (⚠ 베티와 같은 구조적 한계 — 남의 id 로 호출할 수 있다. 감독 하 시험이라 감수한 것)
--   · 응시 기록: 시작할 때 행을 만들고(status in_progress) 제한시간을 서버가 쥔다. 초기화는 is_void
--   · 채점: ko_finalize 한 곳. 출석부(weekend_bety)에는 쓰지 않는다 — 국어 칸이 없다
--   · 회차: weekend_sessions 의 program='korean' 행 (관리 화면에서 직접 insert)
begin;

-- ── 1. 시험지 ───────────────────────────────────────────────
alter table public.bmaps_ko_exams
  add column if not exists session_date   date,
  add column if not exists school_level   text,
  add column if not exists grade          integer,
  add column if not exists opens_at       timestamptz,
  add column if not exists question_count integer not null default 0,
  add column if not exists total_score    integer not null default 0,
  add column if not exists pdf_name       text,
  add column if not exists updated_at     timestamptz not null default now();
alter table public.bmaps_ko_exams alter column student_ids drop not null;
alter table public.bmaps_ko_exams alter column body       set default '[]'::jsonb;
alter table public.bmaps_ko_exams alter column answer_key set default '{}'::jsonb;
alter table public.bmaps_ko_exams alter column published  set default false;
update public.bmaps_ko_exams set question_count = coalesce((select count(*) from jsonb_array_elements(body) s, jsonb_array_elements(s->'questions')), 0)
 where question_count = 0;
create index if not exists bmaps_ko_exams_session_ix on public.bmaps_ko_exams(session_date);

-- ── 2. 응시 기록 ─────────────────────────────────────────────
alter table public.bmaps_ko_attempts
  add column if not exists id             uuid not null default gen_random_uuid(),
  add column if not exists status         text not null default 'in_progress',
  add column if not exists auto_submitted boolean not null default false,
  add column if not exists away_count     integer not null default 0,
  add column if not exists last_seen_at   timestamptz,
  add column if not exists is_void        boolean not null default false,
  add column if not exists void_reason    text,
  add column if not exists voided_at      timestamptz,
  add column if not exists voided_by      uuid;
update public.bmaps_ko_attempts set status = 'submitted' where submitted_at is not null and status <> 'submitted';
alter table public.bmaps_ko_attempts drop constraint if exists bmaps_ko_attempts_pkey;
alter table public.bmaps_ko_attempts add primary key (id);
create unique index if not exists bmaps_ko_attempts_active_uk
  on public.bmaps_ko_attempts(exam_id, student_id) where not is_void;

-- ── 3. 옛 토큰 로그인 제거 ───────────────────────────────────
drop function if exists public.bmaps_ko_api(text, text, jsonb);
drop function if exists public.bmaps_ko_login(text, text);
drop table if exists public.bmaps_ko_sessions;

-- ── 4. 공통 헬퍼 ─────────────────────────────────────────────
create or replace function public.ko_actor_ok(p_actor_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists(select 1 from public.users where id = p_actor_id and role in ('admin','desk') and status = 'active');
$$;

-- users.grade 는 '2학년' 과 '2' 가 섞여 있다 → 숫자만
create or replace function public.ko_grade_num(p_grade text) returns integer
language sql immutable as $$
  select nullif(regexp_replace(coalesce(p_grade,''), '[^0-9]', '', 'g'), '')::integer;
$$;

-- 학생이 이 시험지의 대상인가 (베티 참여 + 학교급 + 학년)
create or replace function public.ko_eligible(p_student_id uuid, p_exam public.bmaps_ko_exams) returns boolean
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare u public.users;
begin
  select * into u from public.users where id = p_student_id and role = 'student' and status = 'active' and bety_yn;
  if not found then return false; end if;
  if p_exam.school_level is not null and coalesce(u.school_level,'') not in (p_exam.school_level, 'both') then return false; end if;
  if p_exam.grade is not null and ko_grade_num(u.grade) is distinct from p_exam.grade then return false; end if;
  return true;
end $$;

-- 채점 — 한 곳. 결과 모양은 베티(bety_omr_submit)와 같게: score·total_score·correct_count·items[q_no,is_correct,response,points]
create or replace function public.ko_finalize(p_att_id uuid, p_auto boolean) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare att public.bmaps_ko_attempts; ex public.bmaps_ko_exams;
        s jsonb; q jsonb; k jsonb; n integer; pt integer; resp text;
        score integer := 0; total integer := 0; correct integer := 0; items jsonb := '[]'; res jsonb;
begin
  select * into att from public.bmaps_ko_attempts where id = p_att_id for update;
  if not found then raise exception '응시 기록이 없습니다'; end if;
  if att.submitted_at is not null then return att.result; end if;
  select * into ex from public.bmaps_ko_exams where id = att.exam_id;
  for s in select value from jsonb_array_elements(ex.body) loop
    for q in select value from jsonb_array_elements(s->'questions') loop
      n := (q->>'no')::integer; k := ex.answer_key->n::text; pt := coalesce((k->>'points')::integer, (q->>'points')::integer, 0);
      resp := att.answers->>n::text; total := total + pt;
      if resp is not null and resp = k->>'answer' then score := score + pt; correct := correct + 1; end if;
      items := items || jsonb_build_array(jsonb_build_object('q_no', n, 'points', pt, 'response', resp,
                 'is_correct', coalesce(resp = (k->>'answer'), false)));
    end loop;
  end loop;
  res := jsonb_build_object('score', score, 'total_score', total, 'correct_count', correct, 'items', items);
  update public.bmaps_ko_attempts set status = 'submitted', submitted_at = now(), auto_submitted = p_auto, result = res
   where id = p_att_id;
  return res;
end $$;

-- ── 5. 관리자 RPC ────────────────────────────────────────────
create or replace function public.ko_exam_list(p_actor_id uuid, p_session_date date) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select case when not ko_actor_ok(p_actor_id) then jsonb_build_object('error','권한 없음') else
    coalesce((select jsonb_agg(jsonb_build_object(
      'id', e.id, 'title', e.title, 'school_level', e.school_level, 'grade', e.grade, 'elective', e.elective,
      'duration_min', e.duration_min, 'published', e.published, 'opens_at', e.opens_at,
      'question_count', e.question_count, 'total_score', e.total_score, 'pdf_name', e.pdf_name, 'created_at', e.created_at,
      'submit_cnt', (select count(*) from public.bmaps_ko_attempts a where a.exam_id = e.id and not a.is_void and a.submitted_at is not null),
      'in_progress_cnt', (select count(*) from public.bmaps_ko_attempts a where a.exam_id = e.id and not a.is_void and a.submitted_at is null)
    ) order by e.grade nulls last, e.elective, e.created_at)
    from public.bmaps_ko_exams e where e.session_date = p_session_date), '[]'::jsonb) end;
$$;

create or replace function public.ko_exam_upsert(p_actor_id uuid, p_exam_id uuid, p_session_date date,
  p_school_level text, p_grade integer, p_elective text, p_duration_min integer, p_title text,
  p_published boolean, p_opens_at timestamptz) returns uuid
language plpgsql security definer set search_path = public, pg_temp as $$
declare eid uuid; t text;
begin
  if not ko_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  if p_session_date is null then raise exception '회차를 고르세요'; end if;
  if p_elective not in ('공통','화법과 작문','언어와 매체') then raise exception '선택과목 오류'; end if;
  if p_duration_min is null or p_duration_min not between 1 and 240 then raise exception '제한시간은 1~240분'; end if;
  if p_school_level is not null and p_school_level not in ('high','middle') then raise exception '학교급 오류'; end if;
  if p_grade is not null and p_grade not between 1 and 3 then raise exception '학년 오류'; end if;
  t := nullif(trim(coalesce(p_title,'')), '');
  if t is null then
    t := to_char(p_session_date, 'YYYY-MM-DD') || ' 국어 · ' ||
         case p_school_level when 'high' then '고등 ' when 'middle' then '중등 ' else '' end ||
         case when p_grade is null then '전학년' else p_grade || '학년' end || ' · ' || p_elective;
  end if;
  if p_exam_id is null then
    eid := gen_random_uuid();
    insert into public.bmaps_ko_exams(id, title, elective, duration_min, body, answer_key, student_ids, published, created_by,
                                      session_date, school_level, grade, opens_at)
    values(eid, t, p_elective, p_duration_min, '[]', '{}', null, coalesce(p_published,false), p_actor_id,
           p_session_date, p_school_level, p_grade, p_opens_at);
  else
    update public.bmaps_ko_exams set title = t, elective = p_elective, duration_min = p_duration_min,
      published = coalesce(p_published,false), session_date = p_session_date, school_level = p_school_level,
      grade = p_grade, opens_at = p_opens_at, updated_at = now()
     where id = p_exam_id returning id into eid;
    if eid is null then raise exception '시험지가 없습니다'; end if;
  end if;
  return eid;
end $$;

create or replace function public.ko_exam_delete(p_actor_id uuid, p_exam_id uuid) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if not ko_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  delete from public.bmaps_ko_attempts where exam_id = p_exam_id;
  delete from public.bmaps_ko_exams where id = p_exam_id;
  return jsonb_build_object('ok', found);
end $$;

-- Codex 분석 결과 적용: 지문·문항 이미지 경로 + 정답·배점. 이미지는 bety-exam/ko-published/<exam_id>/n.png 만 허용
create or replace function public.ko_exam_save_body(p_actor_id uuid, p_exam_id uuid, p_sets jsonb, p_keys jsonb, p_pdf_name text)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare s jsonb; q jsonb; k jsonb; n integer; pt integer; nums integer[] := '{}'; total integer := 0; new_body jsonb;
        pat text := '^ko-published/' || p_exam_id::text || '/[0-9]+[.]png$';
begin
  if not ko_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  if jsonb_typeof(p_sets) is distinct from 'array' or jsonb_array_length(p_sets) not between 1 and 99
     or jsonb_typeof(p_keys) is distinct from 'object' then raise exception '시험 데이터 형식 오류'; end if;
  for s in select value from jsonb_array_elements(p_sets) loop
    if jsonb_typeof(s->'questions') is distinct from 'array' or jsonb_array_length(s->'questions') = 0 then raise exception '지문·문항 형식 오류'; end if;
    if s->>'passage' is not null and s->>'passage' !~ pat then raise exception '지문 이미지 경로 오류'; end if;
    for q in select value from jsonb_array_elements(s->'questions') loop
      n := (q->>'no')::integer; k := p_keys->n::text;
      pt := coalesce((k->>'points')::integer, (q->>'points')::integer);
      if n is null or n not between 1 and 99 or n = any(nums) then raise exception '문항 번호 오류·중복: %', n; end if;
      if k is null or coalesce(k->>'answer','') !~ '^[1-5]$' then raise exception '%번 정답을 1~5로 입력하세요', n; end if;
      if pt is null or pt not between 1 and 10 then raise exception '%번 배점을 확인하세요', n; end if;
      if coalesce(q->>'image','') !~ pat then raise exception '%번 문항 이미지 경로 오류', n; end if;
      nums := array_append(nums, n); total := total + pt;
    end loop;
  end loop;
  -- 학생에게 보일 칸만 남긴다 (정답은 answer_key 에만)
  select jsonb_agg(jsonb_build_object('range', sr->>'range', 'area', sr->>'area', 'passage', sr->'passage',
           'questions', (select jsonb_agg(jsonb_build_object('no', (qr->>'no')::integer,
                           'points', coalesce((p_keys->(qr->>'no')->>'points')::integer, (qr->>'points')::integer),
                           'image', qr->>'image') order by (qr->>'no')::integer)
                         from jsonb_array_elements(sr->'questions') qr)))
    into new_body from jsonb_array_elements(p_sets) sr;
  update public.bmaps_ko_exams set body = new_body, answer_key = p_keys, question_count = cardinality(nums),
         total_score = total, pdf_name = coalesce(p_pdf_name, pdf_name), updated_at = now()
   where id = p_exam_id;
  if not found then raise exception '시험지가 없습니다'; end if;
  return jsonb_build_object('ok', true, 'question_count', cardinality(nums), 'total_score', total);
end $$;

-- 정답·배점만 고친다 (이미지는 그대로). 표 편집 탭이 쓴다
create or replace function public.ko_exam_save_keys(p_actor_id uuid, p_exam_id uuid, p_keys jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare ex public.bmaps_ko_exams; s jsonb; q jsonb; k jsonb; n integer; pt integer; total integer := 0; new_body jsonb;
begin
  if not ko_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  select * into ex from public.bmaps_ko_exams where id = p_exam_id for update;
  if not found then raise exception '시험지가 없습니다'; end if;
  for s in select value from jsonb_array_elements(ex.body) loop
    for q in select value from jsonb_array_elements(s->'questions') loop
      n := (q->>'no')::integer; k := p_keys->n::text;
      if k is null or coalesce(k->>'answer','') !~ '^[1-5]$' then raise exception '%번 정답을 1~5로 입력하세요', n; end if;
      pt := (k->>'points')::integer;
      if pt is null or pt not between 1 and 10 then raise exception '%번 배점을 확인하세요', n; end if;
      total := total + pt;
    end loop;
  end loop;
  select jsonb_agg(jsonb_build_object('range', sr->>'range', 'area', sr->>'area', 'passage', sr->'passage',
           'questions', (select jsonb_agg(jsonb_build_object('no', (qr->>'no')::integer,
                           'points', (p_keys->(qr->>'no')->>'points')::integer, 'image', qr->>'image') order by (qr->>'no')::integer)
                         from jsonb_array_elements(sr->'questions') qr)))
    into new_body from jsonb_array_elements(ex.body) sr;
  update public.bmaps_ko_exams set body = coalesce(new_body, '[]'), answer_key = p_keys, total_score = total, updated_at = now() where id = p_exam_id;
  return jsonb_build_object('ok', true, 'total_score', total);
end $$;

-- 관리자용 전체 조회 (정답 포함)
create or replace function public.ko_exam_get(p_actor_id uuid, p_exam_id uuid) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select case when not ko_actor_ok(p_actor_id) then jsonb_build_object('ok', false, 'reason', 'forbidden') else
    (select jsonb_build_object('ok', true, 'id', e.id, 'title', e.title, 'session_date', e.session_date, 'school_level', e.school_level,
       'grade', e.grade, 'elective', e.elective, 'duration_min', e.duration_min, 'published', e.published, 'opens_at', e.opens_at,
       'question_count', e.question_count, 'total_score', e.total_score, 'pdf_name', e.pdf_name, 'sets', e.body, 'keys', e.answer_key)
     from public.bmaps_ko_exams e where e.id = p_exam_id) end;
$$;

create or replace function public.ko_sub_list(p_actor_id uuid, p_exam_id uuid) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select case when not ko_actor_ok(p_actor_id) then '[]'::jsonb else
    coalesce((select jsonb_agg(jsonb_build_object('student_id', u.id, 'name', u.name, 'school', u.school, 'grade', u.grade,
      'status', a.status, 'started_at', a.started_at, 'submitted_at', a.submitted_at, 'auto_submitted', a.auto_submitted,
      'away_count', a.away_count, 'score', a.result->'score', 'correct_count', a.result->'correct_count', 'total_score', a.result->'total_score')
      order by a.submitted_at desc nulls first, u.name)
     from public.bmaps_ko_attempts a join public.users u on u.id = a.student_id
     where a.exam_id = p_exam_id and not a.is_void), '[]'::jsonb) end;
$$;

create or replace function public.ko_sub_reset(p_actor_id uuid, p_exam_id uuid, p_student_id uuid, p_reason text) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if not ko_actor_ok(p_actor_id) then raise exception '권한 없음'; end if;
  update public.bmaps_ko_attempts set is_void = true, void_reason = p_reason, voided_at = now(), voided_by = p_actor_id
   where exam_id = p_exam_id and student_id = p_student_id and not is_void;
  return jsonb_build_object('ok', found);
end $$;

-- ── 6. 학생 RPC (베티 bety_omr_* 와 같은 호출 규약·반환 모양) ──
create or replace function public.ko_list_for_student(p_student_id uuid) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare u public.users; rounds jsonb;
begin
  select * into u from public.users where id = p_student_id and role = 'student' and status = 'active';
  if not found or not u.bety_yn then return jsonb_build_object('ok', false, 'reason', 'not_participant'); end if;
  select coalesce(jsonb_agg(r order by r->>'session_date' desc), '[]') into rounds from (
    select jsonb_build_object('session_date', e.session_date,
             'round_no', (select ws.round_no from public.weekend_sessions ws where ws.program = 'korean' and ws.session_date = e.session_date limit 1),
             'exams', jsonb_agg(jsonb_build_object('id', e.id, 'title', e.title, 'elective', e.elective, 'duration_min', e.duration_min,
                        'total_score', e.total_score, 'question_count', e.question_count, 'opens_at', e.opens_at,
                        'status', a.status, 'submitted', a.submitted_at is not null, 'score', a.result->'score', 'expires_at', a.deadline)
                      order by e.elective)) r
    from public.bmaps_ko_exams e
    left join public.bmaps_ko_attempts a on a.exam_id = e.id and a.student_id = p_student_id and not a.is_void
    where e.published and e.session_date is not null and e.question_count > 0 and ko_eligible(p_student_id, e)
    group by e.session_date) x;
  return jsonb_build_object('ok', true, 'rounds', rounds, 'server_now', now());
end $$;

create or replace function public.ko_get_exam(p_student_id uuid, p_exam_id uuid) returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare ex public.bmaps_ko_exams; att public.bmaps_ko_attempts;
begin
  select * into ex from public.bmaps_ko_exams where id = p_exam_id and published;
  if not found then return jsonb_build_object('ok', false, 'reason', 'no_exam'); end if;
  if not ko_eligible(p_student_id, ex) then return jsonb_build_object('ok', false, 'reason', 'not_eligible'); end if;
  select * into att from public.bmaps_ko_attempts where exam_id = p_exam_id and student_id = p_student_id and not is_void;
  return jsonb_build_object('ok', true, 'submitted', att.submitted_at is not null,
    'exam', jsonb_build_object('id', ex.id, 'title', ex.title, 'session_date', ex.session_date, 'elective', ex.elective,
              'duration_min', ex.duration_min, 'question_count', ex.question_count, 'total_score', ex.total_score, 'opens_at', ex.opens_at),
    'sets', ex.body);
end $$;

create or replace function public.ko_start(p_student_id uuid, p_exam_id uuid) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare ex public.bmaps_ko_exams; att public.bmaps_ko_attempts;
begin
  select * into ex from public.bmaps_ko_exams where id = p_exam_id and published;
  if not found then return jsonb_build_object('ok', false, 'reason', 'no_exam'); end if;
  if not ko_eligible(p_student_id, ex) then return jsonb_build_object('ok', false, 'reason', 'not_eligible'); end if;
  if ex.opens_at is not null and now() < ex.opens_at then return jsonb_build_object('ok', false, 'reason', 'not_open', 'opens_at', ex.opens_at); end if;
  insert into public.bmaps_ko_attempts(exam_id, student_id, deadline, status)
    values(p_exam_id, p_student_id, now() + make_interval(mins => ex.duration_min), 'in_progress')
    on conflict (exam_id, student_id) where not is_void do nothing;
  select * into att from public.bmaps_ko_attempts where exam_id = p_exam_id and student_id = p_student_id and not is_void for update;
  if att.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted', 'result', att.result); end if;
  if now() > att.deadline then
    return jsonb_build_object('ok', false, 'reason', 'time_over', 'result', ko_finalize(att.id, true));
  end if;
  update public.bmaps_ko_attempts set last_seen_at = now() where id = att.id;
  return jsonb_build_object('ok', true, 'submission_id', att.id, 'server_now', now(), 'expires_at', att.deadline,
                            'started_at', att.started_at, 'answers', att.answers);
end $$;

create or replace function public.ko_save_draft(p_student_id uuid, p_exam_id uuid, p_answers jsonb, p_away integer) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare ex public.bmaps_ko_exams; att public.bmaps_ko_attempts; a jsonb; kk text;
begin
  select * into att from public.bmaps_ko_attempts where exam_id = p_exam_id and student_id = p_student_id and not is_void for update;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_started'); end if;
  if att.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted', 'result', att.result); end if;
  if now() > att.deadline then return jsonb_build_object('ok', false, 'reason', 'time_over', 'result', ko_finalize(att.id, true)); end if;
  select * into ex from public.bmaps_ko_exams where id = p_exam_id;
  a := coalesce(p_answers, '{}');
  if jsonb_typeof(a) <> 'object' then raise exception '답안 형식 오류'; end if;
  for kk in select jsonb_object_keys(a) loop
    if not (ex.answer_key ? kk) or coalesce(a->>kk,'') !~ '^[1-5]$' then raise exception '유효하지 않은 답안'; end if;
  end loop;
  update public.bmaps_ko_attempts set answers = a, last_seen_at = now(),
         away_count = greatest(away_count, coalesce(p_away, 0)) where id = att.id;
  return jsonb_build_object('ok', true, 'saved', true, 'server_now', now(), 'expires_at', att.deadline);
end $$;

create or replace function public.ko_submit(p_student_id uuid, p_exam_id uuid, p_answers jsonb) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare att public.bmaps_ko_attempts; d jsonb; res jsonb;
begin
  select * into att from public.bmaps_ko_attempts where exam_id = p_exam_id and student_id = p_student_id and not is_void;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_started'); end if;
  if att.submitted_at is not null then return jsonb_build_object('ok', false, 'reason', 'already_submitted'); end if;
  if now() <= att.deadline then
    d := ko_save_draft(p_student_id, p_exam_id, p_answers, null);   -- 시간 안이면 보낸 답을 쓴다
    if not (d->>'ok')::boolean and d->>'reason' = 'time_over' then return jsonb_build_object('ok', true) || (d->'result'); end if;
    res := ko_finalize(att.id, false);
  else
    res := ko_finalize(att.id, true);   -- 시간이 지났으면 저장돼 있던 답으로
  end if;
  return jsonb_build_object('ok', true) || res;
end $$;

create or replace function public.ko_get_result(p_student_id uuid, p_exam_id uuid) returns jsonb
language sql stable security definer set search_path = public, pg_temp as $$
  select coalesce((select jsonb_build_object('ok', true) || a.result
                   from public.bmaps_ko_attempts a
                   where a.exam_id = p_exam_id and a.student_id = p_student_id and not a.is_void and a.submitted_at is not null),
                  jsonb_build_object('ok', false));
$$;

-- ── 7. 권한 ─────────────────────────────────────────────────
revoke all on function
  public.ko_actor_ok(uuid), public.ko_eligible(uuid, public.bmaps_ko_exams), public.ko_finalize(uuid, boolean),
  public.ko_exam_list(uuid, date), public.ko_exam_upsert(uuid, uuid, date, text, integer, text, integer, text, boolean, timestamptz),
  public.ko_exam_delete(uuid, uuid), public.ko_exam_save_body(uuid, uuid, jsonb, jsonb, text), public.ko_exam_save_keys(uuid, uuid, jsonb),
  public.ko_exam_get(uuid, uuid), public.ko_sub_list(uuid, uuid), public.ko_sub_reset(uuid, uuid, uuid, text),
  public.ko_list_for_student(uuid), public.ko_get_exam(uuid, uuid), public.ko_start(uuid, uuid),
  public.ko_save_draft(uuid, uuid, jsonb, integer), public.ko_submit(uuid, uuid, jsonb), public.ko_get_result(uuid, uuid)
from public;
grant execute on function
  public.ko_exam_list(uuid, date), public.ko_exam_upsert(uuid, uuid, date, text, integer, text, integer, text, boolean, timestamptz),
  public.ko_exam_delete(uuid, uuid), public.ko_exam_save_body(uuid, uuid, jsonb, jsonb, text), public.ko_exam_save_keys(uuid, uuid, jsonb),
  public.ko_exam_get(uuid, uuid), public.ko_sub_list(uuid, uuid), public.ko_sub_reset(uuid, uuid, uuid, text),
  public.ko_list_for_student(uuid), public.ko_get_exam(uuid, uuid), public.ko_start(uuid, uuid),
  public.ko_save_draft(uuid, uuid, jsonb, integer), public.ko_submit(uuid, uuid, jsonb), public.ko_get_result(uuid, uuid)
to anon, authenticated;
commit;
