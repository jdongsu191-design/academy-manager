-- 고등 N제 일일 리포트 발송 기록 — 데스크가 이미지 리포트를 보낸 시각·사람을 naje_daily 에 남긴다 (브라우저 저장 대신 DB)
-- Supabase SQL Editor 에서 한 번 실행한다. (20261116_naje_daily.sql 적용 뒤)
begin;
alter table public.naje_daily add column if not exists report_sent_at timestamptz;
alter table public.naje_daily add column if not exists report_sent_by uuid;
-- 화면이 표를 직접 갱신한다 (이 두 컬럼만)
grant update (report_sent_at, report_sent_by) on public.naje_daily to anon, authenticated;
commit;
