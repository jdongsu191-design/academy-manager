-- 운영 일정 (2026-10-16) — calendar.html
-- · 학원 운영(academy) · 학교 시험(exam) · 학교 행사(school) · 개인 메모(personal)
-- · 여러 날은 starts_on~ends_on, 종일/시간, 반복(rrule jsonb)+제외일(exdates), 공개 범위(all/shared/private)+참조자(share_user_ids)
-- Supabase SQL Editor 에서 전체 선택(Ctrl+A) 후 한 번 실행.

create table if not exists public.cal_events (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  category text not null default 'academy' check (category in ('academy','exam','school','personal')),
  school text,
  branch_id uuid references public.branches(id) on delete set null,
  starts_on date not null,
  ends_on date not null,
  all_day boolean not null default true,
  start_time time,
  end_time time,
  rrule jsonb,
  exdates date[] not null default '{}',
  visibility text not null default 'all' check (visibility in ('all','shared','private')),
  share_user_ids uuid[] not null default '{}',
  owner_id uuid references public.users(id) on delete set null,
  memo text,
  source text not null default 'manual',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint cal_events_range check (ends_on >= starts_on)
);
create index if not exists cal_events_range_idx on public.cal_events (starts_on, ends_on);
create index if not exists cal_events_owner_idx on public.cal_events (owner_id);

grant select, insert, update, delete on public.cal_events to anon, authenticated;
