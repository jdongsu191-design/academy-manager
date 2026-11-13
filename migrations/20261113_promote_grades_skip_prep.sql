-- 학년 승급 v5 (2026-11-13) — (예비고)/(예비중) 표시가 붙은 학생을 승급 대상에서 뺀다
-- · 문제: '(예비고) ○○중' + 3학년 학생은 학교급 판정이 접두어 우선이라 high·3 이 되어 '졸업' 후보로 잡혔다.
--   11/05~06 예비고 승급 때 올라간 114명은 promoted_year=2027 로 걸러졌지만, 그 뒤 선생님이 학교명에
--   '(예비고) ' 를 직접 적어 등록한 신입 4명(개봉 중등, 11/10~12 입학)은 promoted_year 가 비어 미리보기에 졸업으로 떴다.
--   2026년을 골라 미리보기하면 114명도 전부 졸업으로 잡힌다.
-- · 고침: 접두어가 남은 학생은 종류와 무관하게 승급 계획에서 제외하고, '건너뜀' 목록에
--   '지난 승급의 (예비중)/(예비고) 표시가 남아 있음' 사유로 보인다 (원래 의도했던 동작).
-- · 그 외 로직(v4 포텐셜 처리·되돌리기 undo_grade_promotion)은 그대로. 이 파일은 promote_grades 만 다시 만든다.

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
     and t.school !~ '^\s*\(예비[중고]\)'                  -- v5: 표시가 붙은 학생은 어떤 종류로도 올리지 않는다
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
          or b.school ~ '^\s*\(예비[중고]\)'               -- v5: 건너뛴 목록에 사유와 함께 보인다
          or not ((b.lv = 'elem'   and b.g between 1 and 6)
               or (b.lv = 'middle' and b.g between 1 and 3)
               or (b.lv = 'high'   and b.g between 1 and 3)));

  select count(*) into v_total from _plan;
  select count(*), count(*) filter (where old_pt is true)
    into v_pt_off_total, v_pt_off_on
    from _plan where kind = '예비고';

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', p.id, 'name', p.name, 'code', p.student_code, 'kind', p.kind,
           'branch_id', p.branch_id,
           'from', p.old_school || ' ' || p.old_grade,
           'to',   p.new_school || ' ' || p.new_grade
             || case when p.new_grad is not null then ' (졸업)' else '' end,
           'level_from', p.old_level, 'level_to', p.new_level,
           'pt_off', (p.kind = '예비고' and p.old_pt is true))
           order by p.kind, p.old_school, p.name), '[]'::jsonb)
    into v_plan from _plan p;

  if p_dry_run then
    return jsonb_build_object(
      'ok', true, 'dry_run', true, 'year', v_year, 'today', v_today,
      'kinds', to_jsonb(v_kinds),
      'branch_id', p_branch_id, 'branch_name', v_branch_name,
      'already_promoted', v_already, 'already_list', v_already_list,
      'pt_off_total', v_pt_off_total, 'pt_off_on', v_pt_off_on,
      'total', v_total, 'changes', v_plan, 'skipped', v_skip);
  end if;

  if v_total = 0 then
    return jsonb_build_object('ok', false, 'year', v_year,
      'error', case when v_already > 0
                    then '고른 범위의 학생은 이미 ' || v_year || '년 승급이 끝났습니다. (' || v_already || '명)'
                    else '고른 종류에 해당하는 학생이 없습니다.' end);
  end if;

  -- 스냅샷: 예비고는 포텐셜 값과, 승급일 이력 줄이 이미 있었는지(upd:이전값 / new) 함께 적는다
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
                  'pt_hist_date', v_today)
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
         potential_yn  = case when p.kind = '예비고' then false else u.potential_yn end
    from _plan p
   where u.id = p.id;

  -- 예비고: 승급일 기준 '포텐셜 미참여' 이력 (베티·주말N제는 현재값 그대로). 같은 날 줄이 있으면 포텐셜만 끈다
  insert into student_settings_history (student_id, changed_at, potential_yn, bety_yn, weekend_naje_yn)
  select p.id, v_today, false, p.bety_yn, p.weekend_naje_yn
    from _plan p where p.kind = '예비고'
  on conflict (student_id, changed_at) do update set potential_yn = false;

  return jsonb_build_object('ok', true, 'dry_run', false, 'year', v_year, 'run_id', v_run_id,
    'kinds', to_jsonb(v_kinds), 'branch_id', p_branch_id, 'branch_name', v_branch_name,
    'already_promoted', v_already,
    'pt_off_total', v_pt_off_total, 'pt_off_on', v_pt_off_on,
    'total', v_total, 'changes', v_plan, 'skipped', v_skip);
end $function$;
