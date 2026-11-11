-- 학부모용 공개 진도계획서(plan.html) 전용 RPC
-- 선생님 id 하나로 그 선생님의 모든 달 진도계획서를 돌려주되, 강좌에 박힌 사진(photo, base64)은 뺀다.
-- 공개 페이지는 이 함수 하나만 호출한다 (users 등 다른 테이블 접근 없음).
-- 나중에 bmaps_syllabuses 에 RLS 를 걸어도 security definer 라 이 함수는 계속 동작한다.
create or replace function public.plan_public(p_teacher uuid)
returns table (period text, teacher_name text, updated_at timestamptz, courses jsonb)
language sql
stable
security definer
set search_path = public
as $$
  select s.period,
         s.teacher_name,
         s.updated_at,
         coalesce(
           (select jsonb_agg(e.c - 'photo' order by e.ord)
              from jsonb_array_elements(coalesce(s.courses::jsonb, '[]'::jsonb)) with ordinality as e(c, ord)),
           '[]'::jsonb
         ) as courses
    from public.bmaps_syllabuses s
   where s.teacher_id = p_teacher
   order by s.period;
$$;

revoke all on function public.plan_public(uuid) from public;
grant execute on function public.plan_public(uuid) to anon, authenticated;
