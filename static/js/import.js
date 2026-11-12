(function () {
  var D = JSON.parse(document.getElementById('meetData').textContent);
  var S = D.students, U = D.unmatched;
  var assign = U.map(function () { return -1; });
  var touched = S.map(function () { return false; });
  var LABEL = {p: 'Present', x: 'Absent', l: 'Late', e: 'Excused', r: 'Recited'};
  var rows = document.getElementById('rows'), urows = document.getElementById('urows');
  function z(n) { return (n < 10 ? '0' : '') + n; }
  function fmt(s) { var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? h + ':' + z(m) + ':' + z(s % 60) : m + ':' + z(s % 60); }
  function secsOf(i) { var t = S[i].secs; U.forEach(function (u, k) { if (assign[k] === i) t += u.secs; }); return t; }
  function nameOf(i) { var n = S[i].meet ? [S[i].meet] : []; U.forEach(function (u, k) { if (assign[k] === i) n.push(u.meet); }); return n.join(', '); }
  function auto(i) {
    var t = secsOf(i), old = S[i].old;
    if (t >= D.threshold) return (old === 'r' || old === 'l') ? old : 'p';
    return old === 'e' ? 'e' : 'x';
  }
  function cell(tr, text, cls) { var td = document.createElement('td'); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); return td; }
  document.getElementById('thr').textContent = fmt(D.threshold);
  document.getElementById('len').textContent = fmt(D.length);
  var sels = [], metaCells = [], timeCells = [], trs = [];
  S.forEach(function (s, i) {
    var tr = document.createElement('tr');
    cell(tr, String(i + 1)); cell(tr, s.name, 'nm');
    metaCells[i] = cell(tr, ''); timeCells[i] = cell(tr, '');
    var td = document.createElement('td'), sel = document.createElement('select');
    Object.keys(LABEL).forEach(function (c) { var o = document.createElement('option'); o.value = c; o.textContent = LABEL[c]; sel.appendChild(o); });
    sel.addEventListener('change', function () { touched[i] = true; summary(); });
    td.appendChild(sel); tr.appendChild(td); rows.appendChild(tr);
    sels[i] = sel; trs[i] = tr;
  });
  U.forEach(function (u, k) {
    var tr = document.createElement('tr');
    cell(tr, u.meet); cell(tr, fmt(u.secs));
    var td = document.createElement('td'), sel = document.createElement('select');
    var o0 = document.createElement('option'); o0.value = '-1'; o0.textContent = 'Not a student on my list'; sel.appendChild(o0);
    S.forEach(function (s, i) { var o = document.createElement('option'); o.value = String(i); o.textContent = s.name; sel.appendChild(o); });
    sel.addEventListener('change', function () { assign[k] = parseInt(sel.value, 10); refresh(); });
    td.appendChild(sel); tr.appendChild(td); urows.appendChild(tr);
  });
  if (!U.length) document.getElementById('ucard').style.display = 'none';
  function summary() {
    var n = {p: 0, x: 0, l: 0, e: 0, r: 0};
    sels.forEach(function (s) { n[s.value]++; });
    document.querySelector('#summary b').textContent = 'Present ' + n.p + ' · Absent ' + n.x + ' · Late ' + n.l + ' · Excused ' + n.e + ' · Recited ' + n.r;
  }
  function refresh() {
    S.forEach(function (s, i) {
      var t = secsOf(i);
      metaCells[i].textContent = nameOf(i) || '—';
      timeCells[i].textContent = t ? fmt(t) + ' (' + Math.round(Math.min(1, t / D.length) * 100) + '%)' : '—';
      if (!touched[i]) sels[i].value = auto(i);
      trs[i].className = (t > 0 && t < D.threshold) ? 'partial' : (t === 0 ? 'gone' : '');
      if (t > 0 && t < D.threshold) timeCells[i].textContent += ' · left early';
    });
    summary();
  }
  refresh();
  var btn = document.getElementById('saveBtn'), msg = document.getElementById('msg');
  function post(url, body) {
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function (r) { return r.json().catch(function () { return {ok: false, error: 'Unexpected reply from the site.'}; }); });
  }
  btn.addEventListener('click', function () {
    btn.disabled = true; msg.textContent = 'Saving…';
    var aliases = [];
    U.forEach(function (u, k) { if (assign[k] >= 0) aliases.push({meet: u.meet, student: S[assign[k]].name}); });
    var marks = S.map(function (s, i) { return {row: s.row, name: s.name, code: sels[i].value}; });
    (aliases.length ? post(D.alias_url, {aliases: aliases}) : Promise.resolve({ok: true}))
      .then(function () { return post(D.save_url, {subject: D.subject, section: D.section || '', date: D.date_iso, topic: D.topic, marks: marks, source: 'meet'}); })
      .then(function (r) { if (r.ok) { location.href = D.records_url; } else { msg.textContent = r.error || 'Could not save.'; btn.disabled = false; } })
      .catch(function () { msg.textContent = 'Could not reach the site.'; btn.disabled = false; });
  });
})();
