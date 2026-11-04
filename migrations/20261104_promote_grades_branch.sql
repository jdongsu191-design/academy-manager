-- 학년 승급 v3 (2026-11-04)
-- 1) 초6·중3 은 학교명 앞에 '(예비중) '·'(예비고) ' 만 붙이고 학년은 그대로 둔다 (선생님이 나중에 학교명·학년을 함께 고친다)
--    학교급은 그 접두어를 끝글자보다 먼저 본다 — '(예비중) 광명초' 는 중등, '(예비고) 광명중' 은 고등
--    접두어가 남은 채 다음 해가 오면(예: 중등인데 6학년) 범위 밖이라 건너뛰고 미리보기에 붉게 표시된다
-- 2) 분원별 실행: p_branch_id (NULL = 전체). 학생 분원은 본인 branch_id, 없으면 담당 선생님 분원 (화면 _admBranchOf 와 같은 규칙)
-- 3) 중복 방지는 학생 단위: users.promoted_year 에 승급 연도를 찍고, 같은 해에 이미 찍힌 학생은 어떤 실행(분원·종류·전체·pg_cron)에서도 뺀다
--    → 옛 '같은 해 같은 종류 재실행 차단' 규칙은 없앤다. 되돌리기는 스냅샷의 promoted_year 도 함께 복원한다

-- ── 1. 컬럼 ──────────────────────────────────────────────────────
alter table public.users add column if not exists promoted_year integer;
alter table public.grade_promotion_runs add column if not exists branch_id uuid;
create index if not exists users_promoted_year_idx on public.users (promoted_year);

-- ── 2. 승급 함수 ─────────────────────────────────────────────────
drop function if exists public.promote_grades(integer, boolean, text[]);
create or replace function public.promote_grades(
  p_year integer default null, p_dry_run boolean default true,
  p_kinds text[] default null, p_branch_id uuid default null)
returns jsonb
language plpgsql
as $function$
declare
  v_year   int  := coalesce(p_year, extract(year from (now() at time zone 'Asia/Seoul'))::int);
  v_today  date := (now() at time zone 'Asia/Seoul')::date;
  v_all    text[] := array['학년+1','예비중','예비고','졸업'];
  v_kinds  text[] := coalesce(p_kinds, v_all);
  v_total  int;
  v_already int;
  v_already_list jsonb;
  v_snap   jsonb;
  v_plan   jsonb;
  v_skip   jsonb;
  v_run_id bigint;
  v_branch_name text;
begin
  if array_length(v_kinds, 1) is null then
    return jsonb_build_object('ok', false, 'year', v_year, 'error', '실행할 종류를 하나 이상 고르세요.');
  end if;
  if p_branch_id is not null then
    select name into v_branch_name from branches where id = p_branch_id;
    if v_branch_name is null then
      return jsonb_build_object('ok', false, 'year', v_year, 'error', '분원을 찾지 못했습니다.');
    end if;
  end if;

  -- 학원 재원 학생 전원 + 분원 + 학교급(접두어 우선) + 학년 숫자
  drop table if exists _base;
  create temp table _base on commit drop as
  select u.id, u.name, u.school, u.grade, u.school_level, u.student_code, u.graduated_at, u.promoted_year,
         coalesce(u.branch_id, t.branch_id) as branch_id,
         case
           when u.school ~ '^\s*\(예비고\)'   then 'high'
           when u.school ~ '^\s*\(예비중\)'   then 'middle'
           when u.school ~ '(고등학교|고)$'   then 'high'
           when u.school ~ '(중학교|중)$'     then 'middle'
           when u.school ~ '(초등학교|초)$'   then 'elem'
         end                                              as lv,
         nullif(substring(u.grade from '[0-9]+'), '')::int as g
    from users u
    left join users t on t.id = u.teacher_id
   where u.role = 'student'
     and u.status = 'active'
     and u.reading_room_yn is not true
     and (u.reading_room_class is null or btrim(u.reading_room_class) = '')
     and u.graduated_at is null
     and (p_branch_id is null or coalesce(u.branch_id, t.branch_id) = p_branch_id);

  -- 이 해에 이미 승급된 학생 (분원·종류를 나눠 먼저 돌렸거나 pg_cron 이 돌았거나) — 어떤 실행에서도 다시 올리지 않는다
  select count(*), coalesce(jsonb_agg(jsonb_build_object('id', b.id, 'name', b.name, 'school', b.school, 'grade', b.grade) order by b.school, b.name), '[]'::jsonb)
    into v_already, v_already_list
    from _base b where b.promoted_year = v_year;

  drop table if exists _plan;
  create temp table _plan on commit drop as
  with plan0 as (
  select t.id, t.name, t.student_code, t.branch_id,
         t.school       as old_school,
         t.grade        as old_grade,
         t.school_level as old_level,
         t.graduated_at as old_grad,
         t.promoted_year as old_promoted,
         t.lv, t.g,
         case when t.lv = 'elem'   and t.g = 6 then '(예비중) ' || btrim(t.school)
              when t.lv = 'middle' and t.g = 3 then '(예비고) ' || btrim(t.school)
              else t.school end                             as new_school,
         case when t.lv = 'high'   and t.g = 3 then t.grade      -- 졸업: 학년 유지
              when t.lv = 'elem'   and t.g = 6 then t.grade      -- 예비중: 학년 유지 (선생님이 학교명과 함께 고친다)
              when t.lv = 'middle' and t.g = 3 then t.grade      -- 예비고: 학년 유지
              else (t.g + 1)::text || '학년' end             as new_grade,
         case when t.lv = 'elem'   and t.g = 6
                then case when t.school_level in ('middle','high','both')
                          then t.school_level else 'middle' end
              when t.lv = 'middle' and t.g = 3
                then case when t.school_level in ('high','both')
                          then t.school_level else 'high' end
              else t.school_level end                       as new_level,
         case when t.lv = 'high' and t.g = 3 then v_today end as new_grad,
         case when t.lv = 'elem'   and t.g = 6 then '예비중'
              when t.lv = 'middle' and t.g = 3 then '예비고'
              when t.lv = 'high'   and t.g = 3 then '졸업'
              else '학년+1' end                              as kind
    from _base t
   where (t.promoted_year is null or t.promoted_year <> v_year)
     and t.lv is not null
     and t.g is not null
     and ((t.lv = 'elem'   and t.g between 1 and 6)
       or (t.lv = 'middle' and t.g between 1 and 3)
       or (t.lv = 'high'   and t.g between 1 and 3))
  )
  select * from plan0 where kind = any(v_kinds);          -- 고른 종류만

  -- 판정하지 못해 건너뛴 학생 (종류 선택과 무관, 이미 승급된 학생은 제외)
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', b.id, 'name', b.name, 'school', b.school,
           'grade', b.grade, 'school_level', b.school_level,
           'why', case
             when b.school is null or btrim(b.school) = ''   then '학교명 없음'
             when b.lv is null                                then '학교명으로 학교급을 못 읽음'
             when b.g is null                                 then '학년 숫자 없음'
             when b.school ~ '^\s*\(예비[중고]\)'              then '지난 승급의 (예비중)/(예비고) 표시가 남아 있음 — 학교명·학년을 고치세요'
             else '학년이 범위 밖' end) order by b.school, b.name), '[]'::jsonb)
    into v_skip
    from _base b
   where (b.promoted_year is null or b.promoted_year <> v_year)
     and (b.lv is null or b.g is null
          or not ((b.lv = 'elem'   and b.g between 1 and 6)
               or (b.lv = 'middle' and b.g between 1 and 3)
               or (b.lv = 'high'   and b.g between 1 and 3)));

  select count(*) into v_total from _plan;

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', p.id, 'name', p.name, 'code', p.student_code, 'kind', p.kind,
           'branch_id', p.branch_id,
           'from', p.old_school || ' ' || p.old_grade,
           'to',   p.new_school || ' ' || p.new_grade
             || case when p.new_grad is not null then ' (졸업)' else '' end,
           'level_from', p.old_level, 'level_to', p.new_level)
           order by p.kind, p.old_school, p.name), '[]'::jsonb)
    into v_plan from _plan p;

  if p_dry_run then
    return jsonb_build_object(
      'ok', true, 'dry_run', true, 'year', v_year, 'today', v_today,
      'kinds', to_jsonb(v_kinds),
      'branch_id', p_branch_id, 'branch_name', v_branch_name,
      'already_promoted', v_already, 'already_list', v_already_list,
      'total', v_total, 'changes', v_plan, 'skipped', v_skip);
  end if;

  if v_total = 0 then
    return jsonb_build_object('ok', false, 'year', v_year,
      'error', case when v_already > 0
                    then '고른 범위의 학생은 이미 ' || v_year || '년 승급이 끝났습니다. (' || v_already || '명)'
                    else '고른 종류에 해당하는 학생이 없습니다.' end);
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', p.id, 'school', p.old_school, 'grade', p.old_grade,
           'school_level', p.old_level, 'graduated_at', p.old_grad,
           'promoted_year', p.old_promoted)), '[]'::jsonb)
    into v_snap from _plan p;

  insert into grade_promotion_runs(run_year, total, snapshot, kinds, branch_id)
  values (v_year, v_total, v_snap, v_kinds, p_branch_id)
  returning id into v_run_id;

  update users u
     set school        = p.new_school,
         grade         = p.new_grade,
         school_level  = p.new_level,
         graduated_at  = p.new_grad,
         promoted_year = v_year
    from _plan p
   where u.id = p.id;

  return jsonb_build_object('ok', true, 'dry_run', false, 'year', v_year, 'run_id', v_run_id,
    'kinds', to_jsonb(v_kinds), 'branch_id', p_branch_id, 'branch_name', v_branch_name,
    'already_promoted', v_already,
    'total', v_total, 'changes', v_plan, 'skipped', v_skip);
end $function$;

-- ── 3. 되돌리기: promoted_year 도 함께 복원 ──────────────────────
create or replace function public.undo_grade_promotion(p_run_id bigint)
returns jsonb
language plpgsql
as $function$
declare
  v_run grade_promotion_runs%rowtype;
  v_n   int;
begin
  select * into v_run from grade_promotion_runs where id = p_run_id;
  if v_run.id is null then
    return jsonb_build_object('ok', false, 'error', '실행 기록을 찾지 못했습니다.');
  end if;
  if v_run.undone_at is not null then
    return jsonb_build_object('ok', false, 'error', '이미 되돌린 기록입니다.');
  end if;

  update users u
     set school        = s.school,
         grade         = s.grade,
         school_level  = s.school_level,
         graduated_at  = s.graduated_at,
         promoted_year = s.promoted_year      -- 옛 스냅샷(키 없음)은 null 로 돌아간다
    from (
      select (e->>'id')::uuid as id, e->>'school' as school, e->>'grade' as grade,
             e->>'school_level' as school_level, (e->>'graduated_at')::date as graduated_at,
             (e->>'promoted_year')::int as promoted_year
        from jsonb_array_elements(v_run.snapshot) e
    ) s
   where u.id = s.id;
  get diagnostics v_n = row_count;

  update grade_promotion_runs set undone_at = now() where id = p_run_id;
  return jsonb_build_object('ok', true, 'run_id', p_run_id, 'year', v_run.run_year,
    'kinds', to_jsonb(v_run.kinds), 'branch_id', v_run.branch_id, 'restored', v_n);
end $function$;

-- pg_cron 은 promote_grades(null, false) 그대로 — 전체 분원·전체 종류, 이미 승급된 학생은 자동으로 뺀다

-- 확인
select id, run_year, kinds, branch_id, total, run_at, undone_at from public.grade_promotion_runs order by id;
