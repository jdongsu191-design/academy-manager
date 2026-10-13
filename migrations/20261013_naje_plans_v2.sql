-- 중등 N제 계획 v2 — 교재 목록을 재고관리 카탈로그(inventory_kv 'stock_catalog')에서 끌어온다.
-- book_id 는 그 카탈로그 항목 id(문자열, 예: xmttuotdtiyv) 가 된다. 별도 교재표(naje_plan_books)는 없앤다.
-- 20261013_naje_plans.sql 다음에 Supabase SQL Editor 에서 한 번 실행.
begin;
alter table public.naje_plans drop constraint if exists naje_plans_book_id_fkey;
alter table public.naje_plans alter column book_id type text using book_id::text;
drop table if exists public.naje_plan_books;
commit;
