-- 운영 일정 학교급 (2026-10-16) — cal_events.school_level: 'middle'(중등) | 'high'(고등) | null(구분 없음)
alter table public.cal_events add column if not exists school_level text check (school_level in ('middle','high'));
