/* 운영 일정 공용 규칙 — 반복 전개 · 알림 판정 (calendar.html 의 expand 와 같은 규칙, BMAPS 메인 팝업이 쓴다)
   window.CalRules = { ymd, pd, addDays, daysBetween, expand, dueAlarms } */
(function () {
  'use strict';
  function ymd(d){ return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }
  function pd(s){ var p = String(s).slice(0,10).split('-'); return new Date(+p[0], +p[1]-1, +p[2]); }
  function addDays(d, n){ var x = new Date(d); x.setDate(x.getDate()+n); return x; }
  function daysBetween(a, b){ return Math.round((pd(b) - pd(a)) / 86400000); }

  /* 범위 안 발생분 [{ev, start, end, occ}] — calendar.html expand 와 동일 */
  function expand(ev, from, to){
    var out = [], len = daysBetween(ev.starts_on, ev.ends_on), fromY = ymd(from), toY = ymd(to);
    var ex = {}; (ev.exdates || []).forEach(function(d){ ex[String(d).slice(0,10)] = 1; });
    var push = function(s){ var sy = ymd(s), e = ymd(addDays(s, len)); if(e < fromY || sy > toY) return; if(ex[sy]) return; out.push({ ev:ev, start:sy, end:e, occ:sy }); };
    var r = ev.rrule;
    if(!r || !r.freq){ push(pd(ev.starts_on)); return out; }
    var until = r.until ? String(r.until).slice(0,10) : null, iv = Math.max(1, parseInt(r.interval) || 1), start = pd(ev.starts_on);
    var limit = until && until < toY ? until : toY, n = 0;
    if(r.freq === 'daily'){ for(var d = new Date(start); ymd(d) <= limit && n < 2000; d = addDays(d, iv), n++) push(d); }
    else if(r.freq === 'weekly'){
      var days = Array.isArray(r.byday) && r.byday.length ? r.byday.map(Number) : [start.getDay()];
      var wk0 = addDays(start, -start.getDay());
      for(var w = new Date(wk0); ymd(w) <= limit && n < 1000; w = addDays(w, 7 * iv), n++){
        days.forEach(function(dw){ var d2 = addDays(w, dw); if(ymd(d2) >= ymd(start) && ymd(d2) <= limit) push(d2); });
      }
    }
    else if(r.freq === 'monthly'){
      var mdays = Array.isArray(r.bymonthday) && r.bymonthday.length ? r.bymonthday : [start.getDate()];
      for(var m = 0; n < 600; m += iv, n++){
        var y0 = start.getFullYear(), m0 = start.getMonth() + m, lastD = new Date(y0, m0 + 1, 0).getDate();
        if(ymd(new Date(y0, m0, 1)) > limit) break;
        mdays.forEach(function(md){ var dd = md === 'L' ? lastD : md; if(dd > lastD) return; var dm = new Date(y0, m0, dd); if(ymd(dm) < ymd(start) || ymd(dm) > limit) return; push(dm); });
      }
    }
    else if(r.freq === 'yearly'){ for(var y = 0; n < 100; y += iv, n++){ var dy = new Date(start.getFullYear() + y, start.getMonth(), start.getDate()); if(ymd(dy) > limit) break; push(dy); } }
    return out;
  }

  /* 오늘 띄울 알림.
     remind: { days: 며칠 전부터(0=당일), mode: 'once'|'daily', to: 'shared'|'all' }
     · once  : 창(시작-days ~ 시작일) 안에 처음 본 날 한 번. 한 번 닫으면 그 발생분은 다시 안 뜸(seen 에 occ 키)
     · daily : 창 안 매일. 그날 닫으면 그날만 안 뜸(seen 에 occ|날짜 키)
     대상: owner + share_user_ids, to==='all' 이면 볼 수 있는 모든 직원
     seen: {key:true} — 브라우저 localStorage 에 저장(기기별) */
  function dueAlarms(events, todayY, userId, seen){
    var today = pd(todayY), out = [];
    seen = seen || {};
    (events || []).forEach(function(ev){
      var rm = ev.remind; if(!rm || rm.days == null) return;
      var days = Math.max(0, parseInt(rm.days) || 0), mode = rm.mode === 'daily' ? 'daily' : 'once';
      var mine = ev.owner_id === userId || (ev.share_user_ids || []).indexOf(userId) >= 0;
      if(!mine && rm.to !== 'all') return;
      /* 발생분: 시작일이 오늘 ~ 오늘+days 사이 (창 안) */
      expand(ev, today, addDays(today, days)).forEach(function(o){
        if(o.start < todayY) return;
        var dleft = daysBetween(todayY, o.start);
        var key = ev.id + '|' + o.occ + (mode === 'daily' ? '|' + todayY : '');
        if(seen[key] || seen[ev.id + '|' + o.occ + '|off']) return;   /* off = '이 일정 알림 끄기'(매일 지속을 그 발생분 전체에서 끔) */
        out.push({ ev:ev, start:o.start, end:o.end, occ:o.occ, daysLeft:dleft, key:key, mode:mode });
      });
    });
    out.sort(function(a, b){ return a.daysLeft - b.daysLeft || a.start.localeCompare(b.start); });
    return out;
  }

  window.CalRules = { ymd:ymd, pd:pd, addDays:addDays, daysBetween:daysBetween, expand:expand, dueAlarms:dueAlarms };
})();
