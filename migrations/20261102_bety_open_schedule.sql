-- 베티모의고사 시험지 오픈 시각 예약 + 응시 시작 시각 표시 (2026-11-02)
-- 컬럼 bety_omr_exams.opens_at / bety_omr_submissions.started_at·status 는 이미 있음 (10/01 DDL).
-- ① get_exam: 오픈 전에는 문항(이미지 경로)을 내려주지 않는다 → 'not_open' (start 와 같은 규칙)
-- ② list_submissions: 응시 중(in_progress) 행도 포함, 시작 시각·상태·만료 시각·자동제출·이탈 횟수 추가
--    (돌려주던 열 student_id·name·grade·score·raw_score·correct_count·submitted_at 은 그대로)

-- ① ───────────────────────────────────────────────────────────────
create or replace function public.bety_omr_get_exam(p_student_id uuid, p_exam_id uuid)
returns jsonb language plpgsql security definer set search_path to 'public' as $function$
declare v_u users%rowtype; v_exam bety_omr_exams%rowtype; v_g int; v_has boolean; v_opens timestamptz;
begin
  select * into v_u from users where id = p_student_id;
  if not found or coalesce(v_u.bety_yn,false) = false then
    return jsonb_build_object('ok', false, 'reason', 'not_participant');
  end if;
  select * into v_exam from bety_omr_exams where id = p_exam_id and is_published;
  if not found then return jsonb_build_object('ok', false, 'reason', 'no_exam'); end if;
  v_g := bety_grade_num(v_u.grade);
  if not ((v_exam.grade is null or v_exam.grade = v_g)
      and (v_exam.school_level is null or v_u.school_level = v_exam.school_level
           or v_u.school_level = 'both')) then
    return jsonb_build_object('ok', false, 'reason', 'not_eligible');
  end if;
  select exists(select 1 from bety_omr_submissions
                 where exam_id = v_exam.id and student_id = p_student_id
                   and not is_void and status <> 'in_progress')
    into v_has;
  -- 오픈 전엔 문항을 주지 않는다 (제출한 학생의 결과 보기는 제외). opens_at 비면 회차 날짜 00시(한국)
  if not v_has then
    v_opens := coalesce(v_exam.opens_at, (v_exam.session_date::timestamp at time zone 'Asia/Seoul'));
    if now() < v_opens then
      return jsonb_build_object('ok', false, 'reason', 'not_open', 'opens_at', v_opens);
    end if;
  end if;
  return jsonb_build_object('ok', true, 'submitted', v_has,
    'exam', jsonb_build_object('id', v_exam.id, 'level', v_exam.level,
            'elective', v_exam.elective, 'session_date', v_exam.session_date,
            'question_count', v_exam.question_count, 'total_score', v_exam.total_score,
            'time_limit_min', v_exam.time_limit_min),
    'questions', (select coalesce(jsonb_agg(jsonb_build_object(
                    'q_no', q_no, 'q_type', q_type, 'points', points,
                    'is_excluded', is_excluded,
                    'image_path', image_path, 'source_label', source_label) order by q_no), '[]'::jsonb)
                   from bety_omr_questions where exam_id = v_exam.id));
end $function$;

-- ② ───────────────────────────────────────────────────────────────
-- 옛 함수의 반환형이 다를 수 있어(setof/table) 먼저 지운다. 되돌리기: 옛 정의를 다시 만들면 됨
drop function if exists public.bety_omr_list_submissions(uuid, uuid);
create or replace function public.bety_omr_list_submissions(p_actor_id uuid, p_exam_id uuid)
returns jsonb language plpgsql security definer set search_path to 'public' as $function$
declare v_role text;
begin
  select role into v_role from users where id = p_actor_id;
  if v_role is null or v_role not in ('admin','desk') then
    raise exception '권한이 없습니다';
  end if;
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'submission_id',  s.id,
             'student_id',     s.student_id,
             'name',           u.name,
             'grade',          u.grade,
             'status',         coalesce(s.status, 'submitted'),
             'started_at',     s.started_at,
             'submitted_at',   s.submitted_at,
             'expires_at',     s.expires_at,
             'auto_submitted', coalesce(s.auto_submitted, false),
             'away_count',     coalesce(s.away_count, 0),
             'score',          s.score,
             'raw_score',      s.raw_score,
             'correct_count',  s.correct_count
           ) order by (coalesce(s.status,'submitted') = 'in_progress') desc, u.name), '[]'::jsonb)
      from bety_omr_submissions s
      join users u on u.id = s.student_id
     where s.exam_id = p_exam_id and not s.is_void);
end $function$;
