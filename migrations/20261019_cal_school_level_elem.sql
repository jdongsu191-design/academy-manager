-- 운영 일정 학교급에 초등 추가 (2026-10-19) — cal_events.school_level: 'elem'(초등) | 'middle'(중등) | 'high'(고등) | null
alter table public.cal_events drop constraint if exists cal_events_school_level_check;
alter table public.cal_events add constraint cal_events_school_level_check check (school_level in ('elem','middle','high'));
