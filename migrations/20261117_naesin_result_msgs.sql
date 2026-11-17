-- 내신대비(주말 프로그램) 결과별 멘트 — 선생님이 A(통과)·C(미통과)·F(결석) 멘트 문구를 각자 편집해 저장한다
-- Supabase SQL Editor 에서 한 번 실행한다. 행이 없으면 화면이 기본 문구를 쓴다.
begin;
create table if not exists public.weekend_naesin_result_msgs (
  teacher_id uuid primary key references public.users(id) on delete cascade,
  msg_a text,            -- 결과 A(테스트 완료 & 통과) 멘트. {이름} {날짜} 치환
  msg_c text,            -- 결과 C(테스트 완료 & 미통과)
  msg_f text,            -- 결과 F(결석)
  updated_at timestamptz not null default now()
);
grant select, insert, update, delete on public.weekend_naesin_result_msgs to anon, authenticated;
commit;
