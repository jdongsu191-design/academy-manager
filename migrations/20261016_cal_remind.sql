-- 운영 일정 알림 (2026-10-16) — cal_events.remind
-- { "days": 3, "mode": "once" | "daily", "to": "shared" | "all" }
--   days: 며칠 전부터(0=당일) · mode: once=한 번만 / daily=매일 지속 · to: shared=작성자+참조자 / all=볼 수 있는 모든 직원
alter table public.cal_events add column if not exists remind jsonb;
