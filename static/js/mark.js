
let dirty = false;
let curRollIndex = 0;
let activeFilter = 'all';
let searchQuery = '';

const codes = ['p', 'x', 'l', 'e', 'r'];
const codeNames = {
  p: 'Present',
  x: 'Absent',
  l: 'Late',
  e: 'Excused',
  r: 'Recited'
};
const codeLetters = {
  p: 'P',
  x: 'A',
  l: 'L',
  e: 'E',
  r: 'R'
};

function vibrate(ms) {
  try {
    if (window.navigator && window.navigator.vibrate) {
      window.navigator.vibrate(ms || 12);
    }
  } catch (e) {}
}

const listEl = document.getElementById('studentsList');
const searchEl = document.getElementById('search');
const clearSearchBtn = document.getElementById('clearSearch');
const emptyFilterMsg = document.getElementById('emptyFilterMsg');
const toastEl = document.getElementById('toast');
const saveBtn = document.getElementById('save');
const saveDot = document.getElementById('saveDot');
const saveBtnText = document.getElementById('saveBtnText');
const topicEl = document.getElementById('topic');

const btnModeList = document.getElementById('btnModeList');
const btnModeRoll = document.getElementById('btnModeRoll');
const listViewArea = document.getElementById('listViewArea');
const rollCallArea = document.getElementById('rollCallArea');

const rcStudentIndex = document.getElementById('rcStudentIndex');
const rcStudentName = document.getElementById('rcStudentName');
const rcCurrentPill = document.getElementById('rcCurrentPill');
const rollProgressBar = document.getElementById('rollProgressBar');
const rollCounterText = document.getElementById('rollCounterText');
const rollPercentText = document.getElementById('rollPercentText');
const rollCardMain = document.getElementById('rollCardMain');
const rollCardDone = document.getElementById('rollCardDone');
const doneStatsSummary = document.getElementById('doneStatsSummary');

const studentRowEls = [];

students.forEach((s, idx) => {
  if (!s.code) s.code = 'p';

  const card = document.createElement('div');
  card.className = 'student-card';
  card.dataset.name = s.name.toLowerCase();
  card.dataset.index = idx;

  const header = document.createElement('div');
  header.className = 'student-card-head';

  const idName = document.createElement('div');
  idName.className = 'student-id-name';

  const numSpan = document.createElement('span');
  numSpan.className = 'student-num-badge';
  numSpan.textContent = '#' + (idx + 1);

  const nameSpan = document.createElement('span');
  nameSpan.className = 'student-name-text';
  nameSpan.textContent = s.name;

  idName.appendChild(numSpan);
  idName.appendChild(nameSpan);

  const badge = document.createElement('span');
  badge.className = 'student-status-chip';
  badge.textContent = codeNames[s.code] || 'Unmarked';
  if (s.code) badge.classList.add(s.code);
  else badge.classList.add('blank');

  header.appendChild(idName);
  header.appendChild(badge);

  const grid = document.createElement('div');
  grid.className = 'thumb-buttons-grid';

  const buttonMap = {};
  codes.forEach(c => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cb ' + c;
    btn.dataset.code = c;

    const strong = document.createElement('span');
    strong.textContent = codeLetters[c];
    const sm = document.createElement('small');
    sm.textContent = codeNames[c];

    btn.appendChild(strong);
    btn.appendChild(sm);

    btn.onclick = (e) => {
      e.stopPropagation();
      vibrate(14);
      s.code = c;
      dirty = true;
      paint();
    };

    grid.appendChild(btn);
    buttonMap[c] = btn;
  });

  card.appendChild(header);
  card.appendChild(grid);
  listEl.appendChild(card);

  studentRowEls.push({
    card,
    badge,
    buttons: buttonMap,
    student: s
  });
});

function paint() {
  const counts = { p: 0, x: 0, l: 0, e: 0, r: 0, unmarked: 0 };

  studentRowEls.forEach(item => {
    const code = item.student.code;
    if (code && counts.hasOwnProperty(code)) {
      counts[code]++;
    } else {
      counts.unmarked++;
    }

    codes.forEach(c => {
      item.buttons[c].classList.toggle('on', c === code);
    });

    item.badge.className = 'student-status-chip ' + (code || 'blank');
    item.badge.textContent = codeNames[code] || 'Unmarked';

    const matchesSearch = !searchQuery || item.student.name.toLowerCase().includes(searchQuery);
    let matchesFilter = true;
    if (activeFilter === 'unmarked') {
      matchesFilter = !code;
    } else if (activeFilter !== 'all') {
      matchesFilter = (code === activeFilter);
    }

    const visible = matchesSearch && matchesFilter;
    item.card.style.display = visible ? '' : 'none';
  });

  const visibleCount = studentRowEls.filter(i => i.card.style.display !== 'none').length;
  emptyFilterMsg.style.display = (visibleCount === 0) ? 'block' : 'none';

  const total = students.length;
  document.getElementById('fcount-all').textContent = total;
  document.getElementById('fcount-unmarked').textContent = counts.unmarked;
  document.getElementById('fcount-p').textContent = counts.p;
  document.getElementById('fcount-x').textContent = counts.x;
  document.getElementById('fcount-l').textContent = counts.l;
  document.getElementById('fcount-e').textContent = counts.e;
  document.getElementById('fcount-r').textContent = counts.r;

  document.getElementById('cp').textContent = 'P ' + counts.p;
  document.getElementById('cx').textContent = 'A ' + counts.x;
  document.getElementById('cl').textContent = 'L ' + counts.l;
  document.getElementById('ce').textContent = 'E ' + counts.e;
  document.getElementById('cr').textContent = 'R ' + counts.r;

  if (saveDot) saveDot.classList.toggle('dirty', dirty);
  if (saveBtnText) saveBtnText.textContent = dirty ? 'Save *' : 'Save';

  if (rollCallArea.style.display !== 'none') {
    renderRollCall();
  }
}

function setViewMode(mode) {
  if (mode === 'roll') {
    listViewArea.style.display = 'none';
    rollCallArea.style.display = 'block';
    btnModeRoll.classList.add('on');
    btnModeList.classList.remove('on');
    renderRollCall();
  } else {
    listViewArea.style.display = 'block';
    rollCallArea.style.display = 'none';
    btnModeList.classList.add('on');
    btnModeRoll.classList.remove('on');
  }
}

btnModeList.onclick = () => setViewMode('list');
btnModeRoll.onclick = () => setViewMode('roll');

function renderRollCall() {
  const total = students.length;
  if (curRollIndex >= total) {
    rollCardMain.style.display = 'none';
    rollCardDone.style.display = 'block';
    rollProgressBar.style.width = '100%';
    rollCounterText.textContent = 'All ' + total + ' Students Checked';
    rollPercentText.textContent = '100%';

    const counts = { p: 0, x: 0, l: 0, e: 0, r: 0 };
    students.forEach(s => { if (s.code) counts[s.code]++; });
    doneStatsSummary.innerHTML =
      '<span class="dcount s-p">P ' + counts.p + '</span>' +
      '<span class="dcount s-x">A ' + counts.x + '</span>' +
      '<span class="dcount s-l">L ' + counts.l + '</span>' +
      '<span class="dcount s-e">E ' + counts.e + '</span>' +
      '<span class="dcount s-r">R ' + counts.r + '</span>';
    return;
  }

  rollCardMain.style.display = 'block';
  rollCardDone.style.display = 'none';

  const s = students[curRollIndex];
  rcStudentIndex.textContent = 'Student #' + (curRollIndex + 1) + ' of ' + total;
  rcStudentName.textContent = s.name;

  const currentCode = s.code;
  rcCurrentPill.textContent = currentCode ? ('Marked: ' + codeNames[currentCode]) : 'Not marked yet';
  rcCurrentPill.className = 'rc-current-pill ' + (currentCode || 'blank');

  const pct = Math.round((curRollIndex / total) * 100);
  rollProgressBar.style.width = pct + '%';
  rollCounterText.textContent = 'Student ' + (curRollIndex + 1) + ' of ' + total;
  rollPercentText.textContent = pct + '%';
}

function handleRollCallSelect(code) {
  vibrate(16);
  students[curRollIndex].code = code;
  dirty = true;
  curRollIndex++;
  paint();
  renderRollCall();
}

document.querySelectorAll('.rc-big-btn').forEach(btn => {
  btn.onclick = () => handleRollCallSelect(btn.dataset.code);
});

document.getElementById('rcBtnPrev').onclick = () => {
  if (curRollIndex > 0) {
    curRollIndex--;
    renderRollCall();
  }
};

document.getElementById('rcBtnSkip').onclick = () => {
  if (curRollIndex < students.length) {
    curRollIndex++;
    renderRollCall();
  }
};

document.getElementById('rcBtnSwitchList').onclick = () => setViewMode('list');
document.getElementById('doneReviewBtn').onclick = () => {
  curRollIndex = 0;
  setViewMode('list');
};
document.getElementById('doneSaveBtn').onclick = () => saveAttendance();

document.querySelectorAll('.fpill').forEach(pill => {
  pill.onclick = () => {
    vibrate(10);
    document.querySelectorAll('.fpill').forEach(p => p.classList.remove('on'));
    pill.classList.add('on');
    activeFilter = pill.dataset.filter;
    paint();
  };
});

searchEl.oninput = (e) => {
  searchQuery = e.target.value.toLowerCase().trim();
  clearSearchBtn.style.display = searchQuery ? 'flex' : 'none';
  paint();
};

clearSearchBtn.onclick = () => {
  searchEl.value = '';
  searchQuery = '';
  clearSearchBtn.style.display = 'none';
  searchEl.focus();
  paint();
};

document.getElementById('allP').onclick = () => {
  vibrate(20);
  students.forEach(s => s.code = 'p');
  dirty = true;
  paint();
  toast('All marked Present (P)', 'ok');
};

document.getElementById('clearAll').onclick = () => {
  if (confirm('Clear attendance for all students on this date?')) {
    vibrate(15);
    students.forEach(s => s.code = '');
    dirty = true;
    paint();
    toast('Attendance cleared', 'err');
  }
};

document.getElementById('dateIn').onchange = e => {
  if (e.target.value) location.href = baseUrl + '&date=' + e.target.value;
};
if (topicEl) {
  topicEl.oninput = () => { dirty = true; if (saveDot) saveDot.classList.add('dirty'); };
}

window.onbeforeunload = () => dirty ? 'You have unsaved changes.' : undefined;

function toast(msg, type) {
  toastEl.textContent = msg;
  toastEl.className = 'toast ' + (type === 'err' ? 'err' : 'ok');
  toastEl.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    toastEl.style.display = 'none';
  }, type === 'err' ? 5000 : 2400);
}

async function saveAttendance() {
  const blank = students.filter(s => !s.code).length;
  if (blank === students.length && !wasRecorded) {
    toast('Nobody is marked yet. Mark at least one student first.', 'err');
    return;
  }
  if (blank && !confirm(blank + (blank === 1 ? ' student is' : ' students are') + ' not marked and will be left blank. Save anyway?')) {
    return;
  }

  saveBtn.disabled = true;
  if (saveBtnText) saveBtnText.textContent = 'Saving...';

  try {
    const payload = {
      subject,
      section: typeof section !== 'undefined' ? section : '',
      date: dateIso,
      topic: topicEl ? topicEl.value : '',
      marks: students.map(s => ({
        row: s.row,
        name: s.name,
        code: s.code,
        clear: !s.code
      }))
    };

    const res = await fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      dirty = false;
      wasRecorded = true;
      vibrate(25);
      toast('Saved ✓', 'ok');
      const badgeSlot = document.querySelector('.date-badge-slot');
      if (badgeSlot) {
        badgeSlot.innerHTML = '<span class="badge done">✓ Saved</span>';
      }
    } else {
      toast(data.error || 'Could not save.', 'err');
    }
  } catch (err) {
    toast('Could not reach the site. Is the server window running?', 'err');
  } finally {
    saveBtn.disabled = false;
    paint();
  }
}
saveBtn.onclick = saveAttendance;

window.addEventListener('keydown', (e) => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && key === 's') {
    e.preventDefault();
    saveAttendance();
    return;
  }
  if (rollCallArea.style.display !== 'none') {
    if (codes.includes(key)) {
      handleRollCallSelect(key);
    } else if (key === 'arrowleft') {
      document.getElementById('rcBtnPrev').click();
    } else if (key === 'arrowright') {
      document.getElementById('rcBtnSkip').click();
    }
  }
});

paint();
