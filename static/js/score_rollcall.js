/* Score roll call: one student at a time, each score auto-saved in the background. */
(function () {
  'use strict';

  const students = RC.students.map(s => ({ eid: s.eid, name: s.name, no: s.no || '',
    score: s.score, saved: s.score, state: 'ok' }));   // state: ok | saving | error
  const total = students.length;
  const max = RC.max;

  const $ = id => document.getElementById(id);
  const inputEl = $('rcInput'), errorEl = $('rcError'), toastEl = $('toast');
  const mainEl = $('rcMain'), doneEl = $('rcDone');

  let idx = students.findIndex(s => s.score === null);
  let allWereScored = idx === -1;
  if (idx === -1) idx = 0;
  let pending = 0;
  let chain = Promise.resolve();
  let enteredCount = 0, loggedCount = 0;

  function fmt(n) { return String(+Number(n).toFixed(2)); }
  function vibrate(ms) { try { if (navigator.vibrate) navigator.vibrate(ms || 12); } catch (e) {} }

  function toast(msg, type) {
    toastEl.textContent = msg;
    toastEl.className = 'toast ' + (type === 'err' ? 'err' : 'ok');
    toastEl.style.display = 'block';
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { toastEl.style.display = 'none'; }, type === 'err' ? 5000 : 1800);
  }

  function showError(msg) {
    errorEl.textContent = msg;
    inputEl.classList.add('bad');
    inputEl.classList.remove('shake');
    void inputEl.offsetWidth;            // restart the animation
    inputEl.classList.add('shake');
    vibrate(30);
  }
  function hideError() { errorEl.textContent = ''; inputEl.classList.remove('bad', 'shake'); }

  // ---------------------------------------------------------------- saving
  function send(s, v) {
    return fetch(RC.saveUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: RC.subject, section: RC.section, item_id: RC.itemId,
                             enrollment_id: s.eid, score: v })
    }).then(res => res.json().catch(() => ({})).then(data => ({ ok: res.ok && data.ok, data })))
      .then(r => {
        if (r.ok) {
          s.saved = v;
          if (s.score === v) s.state = 'ok';
          if (v !== null) enteredCount++;
        } else {
          s.state = 'error';
          toast((r.data && r.data.error) || 'Could not save ' + s.name + '.', 'err');
        }
      })
      .catch(() => {
        s.state = 'error';
        toast('Could not reach the site. Is the server window running?', 'err');
      })
      .then(() => { pending--; paintStatus(); paintJump(); });
  }

  function save(s, v) {
    s.score = v;
    s.state = 'saving';
    pending++;
    paintStatus();
    chain = chain.then(() => send(s, v));      // one request at a time keeps the order right
  }

  function retryFailed() {
    students.forEach(s => { if (s.state === 'error') save(s, s.score); });
  }

  function paintStatus() {
    const errors = students.filter(s => s.state === 'error').length;
    const el = $('rcSaveState');
    if (errors) { el.textContent = '⚠ ' + errors + ' not saved'; el.className = 'sc-savestate bad'; }
    else if (pending) { el.textContent = 'Saving…'; el.className = 'sc-savestate'; }
    else { el.textContent = 'All saved ✓'; el.className = 'sc-savestate ok'; }
    $('rcRetry').style.display = errors ? '' : 'none';
    const scored = students.filter(s => s.score !== null);
    $('dockEntered').textContent = scored.length + ' / ' + total;
    $('dockAvg').textContent = scored.length
      ? 'Avg ' + fmt(scored.reduce((a, s) => a + s.score, 0) / scored.length)
      : 'Avg –';
  }

  // ---------------------------------------------------------------- reading the box
  // Returns false when the typed text is a mistake (the student stays on screen).
  function tryCommit() {
    const s = students[idx];
    if (!s) return true;
    const raw = inputEl.value.trim().replace(',', '.');
    if (raw === '') { hideError(); return true; }            // blank = leave this score as it is
    if (!/^(\d+\.?\d*|\.\d+)$/.test(raw)) { showError('Type a number from 0 to ' + fmt(max) + '.'); return false; }
    const v = Math.round(Number(raw) * 100) / 100;
    if (v > max) { showError('The highest possible score is ' + fmt(max) + '.'); return false; }
    hideError();
    if (v !== s.saved || s.state === 'error') save(s, v);
    return true;
  }

  function goTo(i) {
    idx = Math.max(0, Math.min(total, i));
    render();
  }

  function next() { if (tryCommit()) { vibrate(10); goTo(idx + 1); } }
  function prev() { if (tryCommit()) goTo(idx - 1); }

  function quick(v) {
    const s = students[idx];
    if (!s) return;
    hideError();
    if (v !== s.saved || s.state === 'error') save(s, v);
    vibrate(14);
    goTo(idx + 1);
  }

  function clearScore() {
    const s = students[idx];
    if (!s) return;
    hideError();
    inputEl.value = '';
    if (s.saved !== null || s.score !== null) save(s, null);
    render(true);
  }

  // ---------------------------------------------------------------- drawing
  function render(keepFocus) {
    hideError();
    if (idx >= total) { showDone(); paintJump(); paintStatus(); return; }
    mainEl.style.display = ''; doneEl.style.display = 'none';
    const s = students[idx];
    $('rcIndex').textContent = 'Student #' + (idx + 1) + ' of ' + total;
    $('rcName').textContent = s.name;
    $('rcMeta').textContent = s.no ? 'ID ' + s.no : '';
    const pill = $('rcCurrent');
    if (s.score === null) { pill.textContent = 'No score yet'; pill.className = 'rc-current-pill'; }
    else { pill.textContent = 'Score: ' + fmt(s.score) + ' / ' + fmt(max); pill.className = 'rc-current-pill p'; }
    inputEl.value = s.score === null ? '' : fmt(s.score);
    const pct = Math.round((idx / total) * 100);
    $('rcProgressBar').style.width = pct + '%';
    $('rcCounter').textContent = 'Student ' + (idx + 1) + ' of ' + total;
    $('rcPercent').textContent = pct + '%';
    paintJump(); paintStatus();
    inputEl.focus({ preventScroll: true });
    inputEl.select();
  }

  function showDone() {
    mainEl.style.display = 'none'; doneEl.style.display = '';
    $('rcProgressBar').style.width = '100%';
    $('rcCounter').textContent = 'All ' + total + ' students reviewed';
    $('rcPercent').textContent = '100%';
    const scored = students.filter(s => s.score !== null);
    const missing = students.filter(s => s.score === null);
    const vals = scored.map(s => s.score);
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    $('rcDoneSub').textContent = RC.itemLabel + ': ' + RC.itemTitle + ' (out of ' + fmt(max) + ')';
    const chip = (cls, t) => '<span class="dcount ' + cls + '">' + t + '</span>';
    $('rcStats').innerHTML =
      chip('s-p', 'Scored ' + scored.length) +
      chip(missing.length ? 's-x' : 's-e', 'Blank ' + missing.length) +
      (avg === null ? '' :
        chip('s-e', 'Average ' + fmt(avg) + ' (' + fmt(avg / max * 100) + '%)') +
        chip('s-p', 'High ' + fmt(Math.max.apply(null, vals))) +
        chip('s-l', 'Low ' + fmt(Math.min.apply(null, vals))));
    const miss = $('rcMissing');
    miss.innerHTML = '';
    if (missing.length) {
      miss.style.display = '';
      const lab = document.createElement('div');
      lab.className = 'muted'; lab.textContent = 'Still blank (tap to enter):';
      miss.appendChild(lab);
      missing.forEach(s => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'chip sc-miss-chip'; b.textContent = s.name;
        b.onclick = () => goTo(students.indexOf(s));
        miss.appendChild(b);
      });
    } else { miss.style.display = 'none'; }
    chain.then(sendLog);                       // wait for the last background save so the count is right
  }

  function paintJump() {
    const box = $('rcJump');
    box.innerHTML = '';
    students.forEach((s, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'sc-jump-item' + (i === idx ? ' cur' : '') + (s.score === null ? ' blank' : '') +
                    (s.state === 'error' ? ' err' : '') + (s.state === 'saving' ? ' busy' : '');
      const n = document.createElement('span'); n.className = 'sc-jn'; n.textContent = (i + 1) + '. ' + s.name;
      const v = document.createElement('b'); v.textContent = s.score === null ? '–' : fmt(s.score);
      b.appendChild(n); b.appendChild(v);
      b.onclick = () => { if (tryCommit()) { goTo(i); window.scrollTo({ top: 0, behavior: 'smooth' }); } };
      box.appendChild(b);
    });
    const done = students.filter(s => s.score !== null).length;
    $('rcAllCount').textContent = '(' + done + ' of ' + total + ' scored)';
  }

  // ---------------------------------------------------------------- change log (one line per session)
  function sendLog() {
    if (enteredCount <= loggedCount) return;
    const count = enteredCount;
    loggedCount = count;
    try {
      fetch(RC.logUrl, { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: RC.subject, section: RC.section, item_id: RC.itemId, count: count }) });
    } catch (e) {}
  }

  // ---------------------------------------------------------------- wiring
  $('rcNext').onclick = next;
  $('rcSkip').onclick = next;
  $('rcPrev').onclick = prev;
  $('rcPerfect').onclick = () => quick(max);
  $('rcZero').onclick = () => quick(0);
  $('rcClear').onclick = clearScore;
  $('rcRetry').onclick = retryFailed;
  $('rcReview').onclick = () => goTo(0);

  inputEl.addEventListener('input', hideError);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); prev(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); next(); }
    else if (e.key === 'Escape') { inputEl.value = students[idx].score === null ? '' : fmt(students[idx].score); hideError(); }
  });

  window.addEventListener('beforeunload', e => {
    if (pending || students.some(s => s.state === 'error')) { e.preventDefault(); e.returnValue = ''; }
  });
  window.addEventListener('pagehide', sendLog);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') sendLog(); });

  if (allWereScored) {
    const note = $('rcNote');
    note.textContent = 'Every student already has a score here, so you are editing. Type a new score to change one, or press Enter to keep it.';
    note.style.display = '';
  }
  render();
})();
