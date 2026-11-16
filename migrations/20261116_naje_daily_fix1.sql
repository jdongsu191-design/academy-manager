-- 핫픽스 2026-11-16: problems 키가 없는 조각에서 jsonb_typeof(null) 이 null 이 되어 단계 전체 범위가 빠지던 것(coalesce). 20261116_naje_daily.sql 에도 반영됨
-- items → 문항 번호 배열 (단계 전체면 lo~hi, problems 가 있으면 그 번호만). 중복 제거·오름차순
create or replace function public.naje_items_nums(p_items jsonb) returns integer[]
language sql immutable as $$
  select coalesce(array_agg(distinct n order by n), '{}'::integer[])
  from jsonb_array_elements(coalesce(p_items, '[]'::jsonb)) it
  cross join lateral (
    select (x)::integer as n from jsonb_array_elements_text(it->'problems') x
    where coalesce(jsonb_typeof(it->'problems') = 'array' and jsonb_array_length(it->'problems') > 0, false)
    union all
    select generate_series(naje_step_lo((it->>'step')::integer), least(naje_step_hi((it->>'step')::integer), 200))
    where it ? 'step' and not coalesce(jsonb_typeof(it->'problems') = 'array' and jsonb_array_length(it->'problems') > 0, false)
  ) q;
$$;

