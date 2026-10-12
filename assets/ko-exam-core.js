(function(root){
  'use strict';
  function selectSets(draft,elective){
    if(!draft || !draft.sets || !Array.isArray(draft.codexReview)) throw Error('Codex 분석 완료 후 시험을 준비하세요.');
    var sets=draft.sets.filter(function(s){return !['화법과 작문','언어와 매체'].includes(s.area)||s.area===elective;});
    var seen=new Set();
    sets.forEach(function(s){s.qs.forEach(function(q){if(seen.has(q.no))throw Error('중복 문항 번호가 있습니다. 선택과목을 확인하세요.');seen.add(q.no);});});
    if(!seen.size)throw Error('선택한 과목에 문항이 없습니다.');
    return sets;
  }
  function validate(rows){
    if(!rows.length)throw Error('문항이 없습니다.');
    var seen=new Set();rows.forEach(function(r){
      if(!Number.isInteger(r.no)||seen.has(r.no)||r.no<1||r.no>99)throw Error('문항 번호 오류');seen.add(r.no);
      if(!Number.isInteger(+r.answer)||+r.answer<1||+r.answer>5)throw Error(r.no+'번 정답을 1~5로 입력하세요.');
      if(!Number.isInteger(+r.points)||+r.points<1||+r.points>10)throw Error(r.no+'번 배점을 확인하세요.');
    });return rows.reduce(function(n,r){return n+(+r.points);},0);
  }
  var api={selectSets:selectSets,validate:validate};
  if(typeof module!=='undefined')module.exports=api;else root.KoExamCore=api;
})(typeof window==='undefined'?{}:window);
