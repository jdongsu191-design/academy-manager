-- 고등 N제 — 문항 일부 교체 뒤 재채점 (2026-11-26, 사용자 결정)
-- Supabase SQL Editor 에서 한 번 실행한다. 여러 번 실행해도 된다. 표·칸은 추가하지 않는다(함수 하나).
--
-- 등록한 N제의 일부 문항이 틀렸을 때 N제를 통째로 지우지 않고 그 문항만 바꾼다(nje.html '선택한 문항만 교체').
-- 문항을 바꾼 뒤 이 함수가 '이미 제출한 학생' 의 그 문항만 새 정답으로 다시 채점한다.
--   · 학생이 낸 답(response)은 그대로 둔다. 그 문항의 O/X · 채점 여부 · 해설 QR 만 지금의 naje_problems 로 갈아 끼운다
--   · 다른 문항의 결과는 건드리지 않는다. 맞은 개수(correct_count)·채점 문항 수(graded)는 다시 센다
--   · 대상: 그 N제의 유효한 응시(is_void 아님) 중 결과에 그 문항이 들어 있는 것 — 하루 제출·단계 제출·일부 단계만 낸 날 모두
--   · 아직 제출하지 않은 문항은 대상이 아니다(제출할 때 새 정답으로 채점된다)
--   · 관리자만 실행할 수 있다
begin;

create or replace function public.naje_regrade(p_actor_id uuid, p_set_id uuid, p_nos integer[]) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare sub record; it jsonb; new_items jsonb; v_no integer; v_ans text; v_qr text; v_resp text; v_ok boolean; v_hit boolean;
        v_changed boolean; old_cor integer; a_cor integer; a_gr integer; n_sub integer := 0; n_changed integer := 0; detail jsonb := '[]'::jsonb;
begin
  if not exists(select 1 from public.users where id = p_actor_id and role = 'admin' and status = 'active') then
    raise exception '관리자만 재채점할 수 있습니다';
  end if;
  if p_nos is null or cardinality(p_nos) = 0 then return jsonb_build_object('ok', true, 'subs', 0, 'changed', 0, 'rows', '[]'::jsonb); end if;
  for sub in
    select s.id, s.student_id, s.day_id, s.step, s.result
      from public.naje_submissions s
     where s.set_id = p_set_id and not s.is_void and jsonb_typeof(s.result->'items') = 'array'
       and exists(select 1 from jsonb_array_elements(s.result->'items') as t(v) where (t.v->>'no')::integer = any(p_nos))
     order by s.created_at
       for update of s
  loop
    new_items := '[]'::jsonb; v_changed := false;
    for it in select t.v from jsonb_array_elements(sub.result->'items') with ordinality as t(v, ord) order by t.ord loop
      v_no := (it->>'no')::integer;
      if v_no = any(p_nos) then
        select p.correct_answer, p.qr_url into v_ans, v_qr from public.naje_problems p where p.set_id = p_set_id and p.problem_number = v_no;
        v_hit := found;
        if v_hit then
          v_resp := nullif(trim(coalesce(it->>'response', '')), '');
          v_ok := (v_ans is not null and v_resp is not null and naje_norm(v_resp) = naje_norm(v_ans));
          if coalesce((it->>'is_correct')::boolean, false) is distinct from v_ok
             or coalesce((it->>'graded')::boolean, false) is distinct from (v_ans is not null) then v_changed := true; end if;
          it := it || jsonb_build_object('is_correct', v_ok, 'graded', v_ans is not null, 'qr_url', v_qr);
        end if;
      end if;
      new_items := new_items || jsonb_build_array(it);
    end loop;
    select count(*) filter (where (t.v->>'is_correct')::boolean), count(*) filter (where (t.v->>'graded')::boolean)
      into a_cor, a_gr from jsonb_array_elements(new_items) as t(v);
    old_cor := (sub.result->>'correct_count')::integer;
    update public.naje_submissions
       set result = result || jsonb_build_object('items', new_items, 'correct_count', a_cor, 'graded', a_gr)
     where id = sub.id;
    n_sub := n_sub + 1;
    if v_changed then
      n_changed := n_changed + 1;
      detail := detail || jsonb_build_array(jsonb_build_object('student_id', sub.student_id,
        'name', (select u.name from public.users u where u.id = sub.student_id),
        'day_id', sub.day_id, 'step', sub.step, 'before', old_cor, 'after', a_cor, 'graded', a_gr));
    end if;
  end loop;
  return jsonb_build_object('ok', true, 'subs', n_sub, 'changed', n_changed, 'rows', detail);
end $$;

revoke all on function public.naje_regrade(uuid, uuid, integer[]) from public;
grant execute on function public.naje_regrade(uuid, uuid, integer[]) to anon, authenticated;

commit;
