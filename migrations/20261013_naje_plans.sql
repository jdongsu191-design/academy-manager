-- 중등 N제 계획 — 학생별 'N제 교재 + 풀어야 하는 기간'. Supabase SQL Editor 에서 한 번 실행.
-- 다른 BMAPS 표와 같이 anon 접근(RLS 미설정) 으로 둔다. (RLS 전면 적용은 별도 과제)
begin;

create table if not exists public.naje_plan_books (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,            -- 예: 중2B2 4주차
  grade_label text,                            -- 표시용 (예: 중2), 선택
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now()
);

create table if not exists public.naje_plans (
  id          uuid primary key default gen_random_uuid(),
  student_id  uuid not null references public.users(id) on delete cascade,
  book_id     uuid references public.naje_plan_books(id) on delete set null,
  book_name   text not null,                   -- 교재 이름 스냅샷: 교재를 지워도 계획은 남는다
  start_date  date not null,
  end_date    date not null,
  note        text,
  created_by  uuid,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint naje_plans_period_ck check (end_date >= start_date)
);
create index if not exists naje_plans_student_ix on public.naje_plans(student_id, start_date);
create index if not exists naje_plans_end_ix     on public.naje_plans(end_date);

commit;
