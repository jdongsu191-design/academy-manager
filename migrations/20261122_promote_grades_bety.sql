-- 학년 승급 v5 (2026-11-22) — 예비고 학생은 베티모의고사 참여로 (사용자 결정: 예비고는 전원 베티 체크)
-- · 예비고(중3) 로 올라가는 학생은 승급과 함께 users.bety_yn=true, 승급일 이력에도 bety_yn=true (포텐셜 미참여는 v4 그대로).
--   명단이 '회차 날짜 이전 최신 이력' 으로 판정하므로 users 만 켜면 안 되고 이력 줄이 있어야 명단에 오른다.
-- · 되돌리기는 베티 값·이력도 원복한다(스냅샷 bety_yn · bt_hist_prev). 옛 스냅샷엔 키가 없어 베티는 건드리지 않는다.
-- · 미리보기 반환에 bt_on(베티가 새로 켜지는 학생 수) · changes[].bt_on 추가.
-- · 끝에 이미 예비고인 재원 학생 중 베티가 꺼진 학생 일회성 처리 포함(오늘 날짜 이력).
--   ⚠ 일회성 처리는 승급 되돌리기와 맞물리지 않는다(되돌려도 베티는 켜진 채로 남는다).

-- ── 1. 승급 함수 ─────────────────────────────────────────────────
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
  v_pt_off_total int;    -- 예비고 전원(포텐셜 미참여 처리 대상)
  v_pt_off_on    int;    -- 그중 지금 참여 중인 학생(실제로 바뀌는 수)
  v_bt_on        int;    -- 예비고 중 지금 베티 미참여인 학생(베티 참여로 바뀌는 수)
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
         u.potential_yn, u.bety_yn, u.weekend_naje_yn,
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
         t.potential_yn as old_pt,
         t.bety_yn, t.weekend_naje_yn,
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
  select count(*), count(*) filter (where old_pt is true), count(*) filter (where bety_yn is not true)
    into v_pt_off_total, v_pt_off_on, v_bt_on
    from _plan where kind = '예비고';

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', p.id, 'name', p.name, 'code', p.student_code, 'kind', p.kind,
           'branch_id', p.branch_id,
           'from', p.old_school || ' ' || p.old_grade,
           'to',   p.new_school || ' ' || p.new_grade
             || case when p.new_grad is not null then ' (졸업)' else '' end,
           'level_from', p.old_level, 'level_to', p.new_level,
           'pt_off', (p.kind = '예비고' and p.old_pt is true),
           'bt_on',  (p.kind = '예비고' and p.bety_yn is not true))
           order by p.kind, p.old_school, p.name), '[]'::jsonb)
    into v_plan from _plan p;

  if p_dry_run then
    return jsonb_build_object(
      'ok', true, 'dry_run', true, 'year', v_year, 'today', v_today,
      'kinds', to_jsonb(v_kinds),
      'branch_id', p_branch_id, 'branch_name', v_branch_name,
      'already_promoted', v_already, 'already_list', v_already_list,
      'pt_off_total', v_pt_off_total, 'pt_off_on', v_pt_off_on, 'bt_on', v_bt_on,
      'total', v_total, 'changes', v_plan, 'skipped', v_skip);
  end if;

  if v_total = 0 then
    return jsonb_build_object('ok', false, 'year', v_year,
      'error', case when v_already > 0
                    then '고른 범위의 학생은 이미 ' || v_year || '년 승급이 끝났습니다. (' || v_already || '명)'
                    else '고른 종류에 해당하는 학생이 없습니다.' end);
  end if;

  -- 스냅샷: 예비고는 포텐셜·베티 값과, 승급일 이력 줄이 이미 있었는지(upd:이전값 / new) 함께 적는다
  select coalesce(jsonb_agg(
           jsonb_build_object(
             'id', p.id, 'school', p.old_school, 'grade', p.old_grade,
             'school_level', p.old_level, 'graduated_at', p.old_grad,
             'promoted_year', p.old_promoted)
           || case when p.kind = '예비고' then
                jsonb_build_object(
                  'potential_yn', p.old_pt,
                  'pt_hist', case when h.id is null then 'new' else 'upd' end,
                  'pt_hist_prev', h.potential_yn,
                  'pt_hist_date', v_today,
                  'bety_yn', p.bety_yn,
                  'bt_hist_prev', h.bety_yn)
              else '{}'::jsonb end), '[]'::jsonb)
    into v_snap
    from _plan p
    left join student_settings_history h on h.student_id = p.id and h.changed_at = v_today;

  insert into grade_promotion_runs(run_year, total, snapshot, kinds, branch_id)
  values (v_year, v_total, v_snap, v_kinds, p_branch_id)
  returning id into v_run_id;

  update users u
     set school        = p.new_school,
         grade         = p.new_grade,
         school_level  = p.new_level,
         graduated_at  = p.new_grad,
         promoted_year = v_year,
         potential_yn  = case when p.kind = '예비고' then false else u.potential_yn end,
         bety_yn       = case when p.kind = '예비고' then true  else u.bety_yn end
    from _plan p
   where u.id = p.id;

  -- 예비고: 승급일 기준 '포텐셜 미참여 · 베티 참여' 이력 (주말N제는 현재값 그대로). 같은 날 줄이 있으면 그 두 칸만 바꾼다
  insert into student_settings_history (student_id, changed_at, potential_yn, bety_yn, weekend_naje_yn)
  select p.id, v_today, false, true, p.weekend_naje_yn
    from _plan p where p.kind = '예비고'
  on conflict (student_id, changed_at) do update set potential_yn = false, bety_yn = true;

  return jsonb_build_object('ok', true, 'dry_run', false, 'year', v_year, 'run_id', v_run_id,
    'kinds', to_jsonb(v_kinds), 'branch_id', p_branch_id, 'branch_name', v_branch_name,
    'already_promoted', v_already,
    'pt_off_total', v_pt_off_total, 'pt_off_on', v_pt_off_on, 'bt_on', v_bt_on,
    'total', v_total, 'changes', v_plan, 'skipped', v_skip);
end $function$;

-- ── 2. 되돌리기: 포텐셜·베티 값과 이력 줄도 원복 (옛 스냅샷엔 베티 키가 없어 베티는 그대로 둔다) ──
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
         promoted_year = s.promoted_year,      -- 옛 스냅샷(키 없음)은 null 로 돌아간다
         potential_yn  = case when s.has_pt then s.potential_yn else u.potential_yn end,
         bety_yn       = case when s.has_bt then s.bety_yn      else u.bety_yn end
    from (
      select (e->>'id')::uuid as id, e->>'school' as school, e->>'grade' as grade,
             e->>'school_level' as school_level, (e->>'graduated_at')::date as graduated_at,
             (e->>'promoted_year')::int as promoted_year,
             (e ? 'potential_yn') as has_pt, (e->>'potential_yn')::boolean as potential_yn,
             (e ? 'bety_yn') as has_bt, (e->>'bety_yn')::boolean as bety_yn
        from jsonb_array_elements(v_run.snapshot) e
    ) s
   where u.id = s.id;
  get diagnostics v_n = row_count;

  -- 승급이 새로 만든 이력 줄은 지우고, 그날 이미 있던 줄은 이전 포텐셜 값으로
  delete from student_settings_history h
   using (select (e->>'id')::uuid as id, (e->>'pt_hist_date')::date as d
            from jsonb_array_elements(v_run.snapshot) e where e->>'pt_hist' = 'new') s
   where h.student_id = s.id and h.changed_at = s.d;
  update student_settings_history h
     set potential_yn = s.prev,
         bety_yn      = case when s.has_bt then s.bt_prev else h.bety_yn end
    from (select (e->>'id')::uuid as id, (e->>'pt_hist_date')::date as d, (e->>'pt_hist_prev')::boolean as prev,
                 (e ? 'bt_hist_prev') as has_bt, (e->>'bt_hist_prev')::boolean as bt_prev
            from jsonb_array_elements(v_run.snapshot) e where e->>'pt_hist' = 'upd') s
   where h.student_id = s.id and h.changed_at = s.d;

  update grade_promotion_runs set undone_at = now() where id = p_run_id;
  return jsonb_build_object('ok', true, 'run_id', p_run_id, 'year', v_run.run_year,
    'kinds', to_jsonb(v_run.kinds), 'branch_id', v_run.branch_id, 'restored', v_n);
end $function$;

-- ── 3. 일회성: 이미 (예비고) 인 재원 학생 중 베티가 꺼진 학생을 전원 참여로 ──
-- 대상: 학원 재원 학생(독서실 전용 계정·테스트 계정 제외), 학교명이 '(예비고' 로 시작. 오늘(한국 날짜) 이력으로 남겨 오늘 회차부터 명단에 오른다.
-- 이전 회차의 명단·기록은 그대로다. 포텐셜·주말N제 값은 지금 값 그대로 복사한다. 여러 번 실행해도 결과가 같다.
do $$
declare v_d date := (now() at time zone 'Asia/Seoul')::date; v_n int; v_h int;
begin
  drop table if exists _bt_fix;
  create temp table _bt_fix as
  select u.id, u.potential_yn, u.weekend_naje_yn
    from users u
    left join lateral (select h.bety_yn from student_settings_history h
                        where h.student_id = u.id order by h.changed_at desc limit 1) lh on true
   where u.role = 'student' and u.status = 'active'
     and u.is_test is not true
     and u.reading_room_yn is not true
     and (u.reading_room_class is null or btrim(u.reading_room_class) = '')
     and u.school ~ '^\s*\(예비고'
     and (u.bety_yn is not true or lh.bety_yn is not true);   -- users 값이나 최신 이력 중 하나라도 꺼져 있으면
  update users u set bety_yn = true from _bt_fix f where u.id = f.id and u.bety_yn is not true;
  get diagnostics v_n = row_count;
  insert into student_settings_history (student_id, changed_at, potential_yn, bety_yn, weekend_naje_yn)
  select f.id, v_d, f.potential_yn, true, f.weekend_naje_yn from _bt_fix f
  on conflict (student_id, changed_at) do update set bety_yn = true;
  get diagnostics v_h = row_count;
  drop table _bt_fix;
  raise notice '예비고 베티 참여 처리: users % 명, 이력 % 줄 (%)', v_n, v_h, v_d;
end $$;

-- 확인: (예비고) 재원 학생 중 아직 베티가 꺼진 학생 — still_off 가 0 이어야 한다
select count(*) filter (where bety_yn is not true) as still_off, count(*) as total
  from users
 where role = 'student' and status = 'active' and is_test is not true and reading_room_yn is not true
   and (reading_room_class is null or btrim(reading_room_class) = '') and school ~ '^\s*\(예비고';
