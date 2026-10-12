-- Run manually in Supabase SQL Editor. Additive: existing math tables are untouched.
begin;
create table if not exists public.bmaps_ko_sessions (
 token_hash text primary key, user_id uuid not null references public.users(id),
 expires_at timestamptz not null default now()+interval '12 hours'
);
create table if not exists public.bmaps_ko_exams (
 id uuid primary key, title text not null, elective text not null,
 duration_min integer not null check(duration_min between 1 and 240),
 body jsonb not null, answer_key jsonb not null, student_ids uuid[] not null,
 published boolean not null default true, created_by uuid not null references public.users(id),
 created_at timestamptz not null default now()
);
create table if not exists public.bmaps_ko_attempts (
 exam_id uuid not null references public.bmaps_ko_exams(id), student_id uuid not null references public.users(id),
 started_at timestamptz not null default now(), deadline timestamptz not null,
 answers jsonb not null default '{}', submitted_at timestamptz, result jsonb,
 primary key(exam_id,student_id)
);
alter table public.bmaps_ko_sessions enable row level security;
alter table public.bmaps_ko_exams enable row level security;
alter table public.bmaps_ko_attempts enable row level security;
revoke all on public.bmaps_ko_sessions,public.bmaps_ko_exams,public.bmaps_ko_attempts from anon,authenticated;

-- Existing BMAPS accounts use users.password. Verify it server-side; an actor UUID alone is insufficient.
create or replace function public.bmaps_ko_login(p_username text,p_password text)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare u public.users; t text;
begin
 if length(coalesce(p_username,''))>200 or length(coalesce(p_password,''))>200 or coalesce(p_password,'')='' then raise exception '아이디와 비밀번호를 확인하세요'; end if;
 select * into u from public.users where username=p_username and password=p_password and status='active' and role in ('admin','desk','student');
 if not found then raise exception '아이디와 비밀번호 또는 계정 상태를 확인하세요'; end if;
 delete from public.bmaps_ko_sessions where expires_at<now();
 t:=replace(gen_random_uuid()::text,'-','')||replace(gen_random_uuid()::text,'-','');
 insert into public.bmaps_ko_sessions(token_hash,user_id) values(encode(sha256(convert_to(t,'UTF8')),'hex'),u.id);
 return jsonb_build_object('token',t,'name',u.name,'role',u.role,'id',u.id);
end $$;

create or replace function public.bmaps_ko_api(p_token text,p_action text,p_data jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
 uid uuid; ur text; ex public.bmaps_ko_exams; att public.bmaps_ko_attempts;
 eid uuid; st uuid[]; s jsonb; q jsonb; k jsonb; im jsonb; a jsonb; items jsonb:='[]';
 body jsonb; keys jsonb; nums integer[]:='{}'; n integer; pt integer; ans text;
 score integer:=0; total integer:=0; correct integer:=0; outdata jsonb; is_admin boolean;
begin
 select u.id,u.role into uid,ur from public.bmaps_ko_sessions t join public.users u on u.id=t.user_id
 where t.token_hash=encode(sha256(convert_to(coalesce(p_token,''),'UTF8')),'hex') and t.expires_at>now() and u.status='active';
 if uid is null then raise exception '국어 시험 인증이 만료됐습니다. 다시 로그인하세요'; end if;
 is_admin:=ur in ('admin','desk');
 if p_action='logout' then delete from public.bmaps_ko_sessions where token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex'); return '{"ok":true}'; end if;
 if p_action='students' and is_admin then
  select coalesce(jsonb_agg(jsonb_build_object('id',id,'name',name,'school',school,'grade',grade) order by name),'[]') into outdata from public.users where role='student' and status='active'; return outdata;
 end if;
 if p_action='list' then
  select coalesce(jsonb_agg(jsonb_build_object('id',e.id,'title',e.title,'elective',e.elective,'duration',e.duration_min,'published',e.published,'created_at',e.created_at,'submitted',a.submitted_at is not null) order by e.created_at desc),'[]') into outdata
  from public.bmaps_ko_exams e left join public.bmaps_ko_attempts a on a.exam_id=e.id and a.student_id=uid
  where is_admin or (ur='student' and uid=any(e.student_ids) and e.published);
  return outdata;
 end if;
 eid:=(p_data->>'id')::uuid;
 if p_action='publish' and is_admin then
  body:=p_data->'sets';keys:=p_data->'keys';
  if jsonb_typeof(body) is distinct from 'array' or jsonb_array_length(body) not between 1 and 99 or jsonb_typeof(keys) is distinct from 'object' then raise exception '시험 데이터 형식 오류'; end if;
  if length(coalesce(p_data->>'title','')) not between 1 and 150 or (p_data->>'duration')::integer not between 1 and 240 then raise exception '시험명·시간을 확인하세요';end if;
  if p_data->>'elective' not in ('공통','화법과 작문','언어와 매체') then raise exception '선택과목 오류';end if;
  select array_agg(value::uuid) into st from jsonb_array_elements_text(p_data->'students');
  if coalesce(cardinality(st),0)=0 or exists(select 1 from unnest(st) x where not exists(select 1 from public.users where id=x and role='student' and status='active')) then raise exception '응시 대상 학생을 확인하세요';end if;
  for s in select value from jsonb_array_elements(body) loop
   if jsonb_typeof(s->'passage') is distinct from 'array' or jsonb_typeof(s->'questions') is distinct from 'array' or jsonb_array_length(s->'questions')=0 then raise exception '지문·문항 형식 오류';end if;
   for im in select value from jsonb_array_elements(s->'passage') loop
    if coalesce(im#>>'{}','') !~ ('^ko-published/'||eid::text||'/[0-9]+[.]png$') then raise exception '지문 이미지 경로 오류';end if;
   end loop;
   for q in select value from jsonb_array_elements(s->'questions') loop
    n:=(q->>'no')::integer;pt:=(q->>'points')::integer;k:=keys->n::text;
    if n is null or n not between 1 and 99 or n=any(nums) or pt is null or pt not between 1 and 10 or k is null or coalesce(k->>'answer','') !~ '^[1-5]$' or (k->>'points')::integer is distinct from pt then raise exception '정답·배점·중복 문항을 확인하세요';end if;
    if jsonb_typeof(q->'images') is distinct from 'array' or jsonb_array_length(q->'images')=0 then raise exception '문항 이미지 누락';end if;
    for im in select value from jsonb_array_elements(q->'images') loop
     if coalesce(im#>>'{}','') !~ ('^ko-published/'||eid::text||'/[0-9]+[.]png$') then raise exception '문항 이미지 경로 오류';end if;
    end loop;
    -- Whitelist student-visible fields; never copy administrator-supplied keys/answers.
    nums:=array_append(nums,n);
   end loop;
  end loop;
  if cardinality(nums)=0 then raise exception '문항이 없습니다';end if;
  select jsonb_agg(jsonb_build_object('range',setrow->>'range','area',setrow->>'area','passage',setrow->'passage','questions',
   (select jsonb_agg(jsonb_build_object('no',qrow->'no','points',qrow->'points','images',qrow->'images')) from jsonb_array_elements(setrow->'questions') qrow))) into body from jsonb_array_elements(body) setrow;
  insert into public.bmaps_ko_exams(id,title,elective,duration_min,body,answer_key,student_ids,created_by)
   values(eid,p_data->>'title',p_data->>'elective',(p_data->>'duration')::integer,body,keys,st,uid) on conflict(id) do nothing;
  return jsonb_build_object('ok',true,'id',eid);
 end if;
 select * into ex from public.bmaps_ko_exams where id=eid;
 if not found then raise exception '시험을 찾을 수 없습니다';end if;
 if is_admin then
  if p_action='visibility' then update public.bmaps_ko_exams set published=(p_data->>'published')::boolean where id=eid;return '{"ok":true}';end if;
  if p_action='results' then
   select coalesce(jsonb_agg(jsonb_build_object('name',u.name,'school',u.school,'grade',u.grade,'submitted_at',a.submitted_at,'started_at',a.started_at,'result',a.result) order by u.name),'[]') into outdata
   from public.users u left join public.bmaps_ko_attempts a on a.student_id=u.id and a.exam_id=eid where u.id=any(ex.student_ids);return outdata;
  end if;
  raise exception '학생 계정으로 응시하세요';
 end if;
 if ur<>'student' or not(uid=any(ex.student_ids)) or not ex.published then raise exception '응시 대상이 아니거나 비공개 시험입니다';end if;
 if p_action='start' then
  insert into public.bmaps_ko_attempts(exam_id,student_id,deadline) values(eid,uid,now()+make_interval(mins=>ex.duration_min)) on conflict do nothing;
 end if;
 select * into att from public.bmaps_ko_attempts where exam_id=eid and student_id=uid for update;
 if not found then raise exception '먼저 응시를 시작하세요';end if;
 if att.submitted_at is not null then return jsonb_build_object('submitted',true,'result',att.result);end if;
 if p_action='start' then return jsonb_build_object('id',eid,'title',ex.title,'sets',ex.body,'answers',att.answers,'deadline',att.deadline,'server_now',now());end if;
 if p_action not in ('save','submit') then raise exception '지원하지 않는 요청';end if;
 a:=coalesce(p_data->'answers','{}');
 if jsonb_typeof(a)<>'object' then raise exception '답안 형식 오류';end if;
 for ans in select jsonb_object_keys(a) loop
  if not(ex.answer_key ? ans) or coalesce(a->>ans,'') !~ '^[1-5]$' then raise exception '유효하지 않은 답안';end if;
 end loop;
 if now()<=att.deadline then
  update public.bmaps_ko_attempts set answers=a where exam_id=eid and student_id=uid;
 else a:=att.answers;end if;
 if p_action='save' then return jsonb_build_object('ok',now()<=att.deadline,'expired',now()>att.deadline);end if;
 for s in select value from jsonb_array_elements(ex.body) loop
  for q in select value from jsonb_array_elements(s->'questions') loop
   n:=(q->>'no')::integer;k:=ex.answer_key->n::text;pt:=(k->>'points')::integer;total:=total+pt;
   if a->>n::text=k->>'answer' then score:=score+pt;correct:=correct+1;end if;
   items:=items||jsonb_build_array(jsonb_build_object('no',n,'answer',k->>'answer','response',a->>n::text,'correct',coalesce(a->>n::text=k->>'answer',false),'points',pt));
  end loop;
 end loop;
 outdata:=jsonb_build_object('score',score,'total',total,'correct_count',correct,'items',items);
 update public.bmaps_ko_attempts set submitted_at=now(),result=outdata where exam_id=eid and student_id=uid;
 return jsonb_build_object('submitted',true,'result',outdata);
end $$;
revoke all on function public.bmaps_ko_login(text,text),public.bmaps_ko_api(text,text,jsonb) from public;
grant execute on function public.bmaps_ko_login(text,text),public.bmaps_ko_api(text,text,jsonb) to anon,authenticated;
commit;
