// ============================================================================
// MARK ATTENDANCE — MOBILE-FIRST ENHANCED (Gestures + Haptics + Offline)
// ============================================================================

// --- Constants & Config ---
const CODES = ['p', 'x', 'l', 'e', 'r'];
const CODE_NAMES = { p: 'Present', x: 'Absent', l: 'Late', e: 'Excused', r: 'Recited' };
const CODE_LETTERS = { p: 'P', x: 'A', l: 'L', e: 'E', r: 'R' };
const CODE_COLORS = {
  p: { bg: 'var(--pbg)', border: 'var(--p-border)', text: 'var(--p-ink)', solid: 'var(--p)' },
  x: { bg: 'var(--xbg)', border: 'var(--x-border)', text: 'var(--x-ink)', solid: 'var(--x)' },
  l: { bg: 'var(--lbg)', border: 'var(--l-border)', text: 'var(--l-ink)', solid: 'var(--l)' },
  e: { bg: 'var(--ebg)', border: 'var(--e-border)', text: 'var(--e-ink)', solid: 'var(--e)' },
  r: { bg: 'var(--rbg)', border: 'var(--r-border)', text: 'var(--r-ink)', solid: 'var(--r)' },
};

// --- State ---
let dirty = false;
let curRollIndex = 0;
let activeFilter = 'all';
let searchQuery = '';
let isOnline = navigator.onLine;
let pendingSync = false;
let lastSavedState = null;
let rollCallStartTime = Date.now();
let studentStartTime = Date.now();
let gestureStartX = 0;
let gestureStartY = 0;
let isGesturing = false;
let currentGestureStudent = null;

// --- DOM Elements ---
const els = {
  list: document.getElementById('studentsList'),
  search: document.getElementById('search'),
  clearSearch: document.getElementById('clearSearch'),
  emptyMsg: document.getElementById('emptyFilterMsg'),
  toast: document.getElementById('toast'),
  saveBtn: document.getElementById('save'),
  saveDot: document.getElementById('saveDot'),
  saveText: document.getElementById('saveBtnText'),
  topic: document.getElementById('topic'),
  btnList: document.getElementById('btnModeList'),
  btnRoll: document.getElementById('btnModeRoll'),
  listView: document.getElementById('listViewArea'),
  rollView: document.getElementById('rollCallArea'),
  rcIndex: document.getElementById('rcStudentIndex'),
  rcName: document.getElementById('rcStudentName'),
  rcPill: document.getElementById('rcCurrentPill'),
  rcProgress: document.getElementById('rollProgressBar'),
  rcCounter: document.getElementById('rollCounterText'),
  rcPercent: document.getElementById('rollPercentText'),
  rcMain: document.getElementById('rollCardMain'),
  rcDone: document.getElementById('rollCardDone'),
  rcStats: document.getElementById('doneStatsSummary'),
  mobileDock: document.getElementById('mobileDock'),
  dockCounts: document.getElementById('dockCounts'),
};

// --- Utility: Haptics ---
function haptic(type = 'light') {
  try {
    if (!navigator.vibrate) return;
    const patterns = {
      light: 10,
      medium: 18,
      heavy: 30,
      success: [15, 50, 15],
      error: [30, 40, 30],
      warning: [10, 30, 10, 30, 10],
      select: 5,
    };
    navigator.vibrate(patterns[type] || patterns.light);
  } catch (e) {}
}

// --- Utility: Toast ---
function toast(msg, type = 'ok') {
  const t = els.toast;
  t.textContent = msg;
  t.className = 'toast ' + (type === 'err' ? 'err' : type === 'warn' ? 'warn' : 'ok');
  t.style.display = 'block';
  t.style.animation = 'toastIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => {
    t.style.animation = 'toastOut 0.2s ease-in';
    setTimeout(() => { t.style.display = 'none'; }, 200);
  }, type === 'err' ? 5000 : 2400);
}

// --- Utility: Confetti Celebration ---
function celebrate() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;';
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  const W = canvas.width = window.innerWidth;
  const H = canvas.height = window.innerHeight;
  const pieces = Array.from({ length: 60 }, () => ({
    x: Math.random() * W,
    y: -20,
    size: 8 + Math.random() * 10,
    color: ['var(--p)', 'var(--blue-500)', 'var(--r)', 'var(--l)', '#fff'][Math.floor(Math.random() * 5)],
    vx: (Math.random() - 0.5) * 6,
    vy: 2 + Math.random() * 4,
    rot: Math.random() * 360,
    vr: (Math.random() - 0.5) * 10,
  }));
  function tick() {
    ctx.clearRect(0, 0, W, H);
    let alive = 0;
    pieces.forEach(p => {
      p.y += p.vy; p.x += p.vx; p.rot += p.vr; p.vy += 0.08;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot * Math.PI / 180);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size/2, -p.size/2, p.size, p.size);
      ctx.restore();
      if (p.y < H + 50) alive++;
    });
    if (alive) requestAnimationFrame(tick);
    else { canvas.remove(); }
  }
  tick();
}

// --- Utility: Optimistic Storage ---
const STORAGE_KEY = 'attendance_draft_' + subject + '_' + section + '_' + dateIso;
function saveDraft() {
  const state = {
    students: students.map(s => ({ row: s.row, name: s.name, code: s.code })),
    topic: els.topic?.value || '',
    timestamp: Date.now(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  lastSavedState = state;
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const state = JSON.parse(raw);
    if (Date.now() - state.timestamp > 7 * 24 * 60 * 60 * 1000) { clearDraft(); return false; }
    const map = new Map(state.students.map(s => [s.row, s.code]));
    let restored = 0;
    students.forEach(s => { if (map.has(s.row)) { s.code = map.get(s.row); restored++; } });
    if (els.topic && state.topic) els.topic.value = state.topic;
    if (restored > 0) {
      toast(`Restored ${restored} unsaved mark${restored > 1 ? 's' : ''} from draft`, 'ok');
      return true;
    }
    return false;
  } catch (e) { return false; }
}

function clearDraft() {
  localStorage.removeItem(STORAGE_KEY);
  lastSavedState = null;
}

// --- Utility: Online/Offline ---
function updateOnlineStatus() {
  isOnline = navigator.onLine;
  document.body.classList.toggle('offline', !isOnline);
  if (els.saveBtn) els.saveBtn.title = isOnline ? 'Save (Ctrl+S)' : 'Save (Offline - will sync when online)';
  if (!isOnline) toast('You\'re offline. Changes saved locally.', 'warn');
  else if (pendingSync) { toast('Back online — syncing...', 'ok'); syncPending(); }
}
window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
updateOnlineStatus();

// --- Sync Logic ---
async function syncPending() {
  if (!isOnline || !dirty) return;
  pendingSync = true;
  try {
    await saveAttendance(true);
    pendingSync = false;
  } catch (e) {
    pendingSync = false;
  }
}

// --- Core Render ---
const studentEls = [];

students.forEach((s, idx) => {
  if (!s.code) s.code = '';
  const card = createStudentCard(s, idx);
  els.list.appendChild(card.el);
  studentEls.push(card);
});

function createStudentCard(student, index) {
  const card = document.createElement('div');
  card.className = 'student-card';
  card.dataset.name = student.name.toLowerCase();
  card.dataset.index = index;
  card.dataset.row = student.row;
  card.style.transform = 'translateY(10px)';
  card.style.opacity = '0';
  card.style.transition = 'opacity 0.3s ease, transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)';
  requestAnimationFrame(() => { card.style.transform = 'translateY(0)'; card.style.opacity = '1'; });

  const header = document.createElement('div');
  header.className = 'student-card-head';

  const idName = document.createElement('div');
  idName.className = 'student-id-name';

  const num = document.createElement('span');
  num.className = 'student-num-badge';
  num.textContent = '#' + (index + 1);

  const name = document.createElement('span');
  name.className = 'student-name-text';
  name.textContent = student.name;

  idName.append(num, name);

  const badge = document.createElement('span');
  badge.className = 'student-status-chip blank';
  badge.textContent = 'Unmarked';

  header.append(idName, badge);

  const grid = document.createElement('div');
  grid.className = 'thumb-buttons-grid';
  const btnMap = {};

  CODES.forEach(c => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cb ' + c;
    btn.dataset.code = c;
    btn.dataset.index = index;
    btn.innerHTML = `<strong>${CODE_LETTERS[c]}</strong><small>${CODE_NAMES[c]}</small>`;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      haptic('light');
      selectCode(index, c);
    });
    // Touch ripple
    btn.addEventListener('touchstart', () => btn.style.transform = 'scale(0.96)', { passive: true });
    btn.addEventListener('touchend', () => btn.style.transform = '', { passive: true });
    btn.addEventListener('touchcancel', () => btn.style.transform = '', { passive: true });
    grid.appendChild(btn);
    btnMap[c] = btn;
  });

  card.append(header, grid);

  // Swipe gesture on card for quick actions
  let touchStartX = 0, touchStartY = 0;
  card.addEventListener('touchstart', e => {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    card.style.transition = 'none';
  }, { passive: true });
  card.addEventListener('touchmove', e => {
    const dx = e.touches[0].clientX - touchStartX;
    const dy = e.touches[0].clientY - touchStartY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 20) {
      e.preventDefault();
      card.style.transform = `translateX(${Math.max(-80, Math.min(80, dx))}px)`;
      // Show hint
      if (dx > 40) card.dataset.swipeHint = 'present';
      else if (dx < -40) card.dataset.swipeHint = 'absent';
      else delete card.dataset.swipeHint;
    }
  }, { passive: false });
  card.addEventListener('touchend', e => {
    card.style.transition = 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1)';
    const dx = e.changedTouches[0].clientX - touchStartX;
    if (dx > 60) selectCode(index, 'p');
    else if (dx < -60) selectCode(index, 'x');
    card.style.transform = '';
    delete card.dataset.swipeHint;
  }, { passive: true });

  return { el: card, badge, buttons: btnMap, student };
}

// --- Paint / Update UI ---
function paint() {
  const counts = { p: 0, x: 0, l: 0, e: 0, r: 0, unmarked: 0 };
  let visibleCount = 0;

  studentEls.forEach(item => {
    const code = item.student.code;
    if (code && counts.hasOwnProperty(code)) counts[code]++;
    else counts.unmarked++;

    CODES.forEach(c => item.buttons[c].classList.toggle('on', c === code));

    item.badge.className = 'student-status-chip ' + (code || 'blank');
    item.badge.textContent = code ? CODE_NAMES[code] : 'Unmarked';
    if (code) item.badge.classList.add(code);

    const matchesSearch = !searchQuery || item.student.name.toLowerCase().includes(searchQuery);
    let matchesFilter = true;
    if (activeFilter === 'unmarked') matchesFilter = !code;
    else if (activeFilter !== 'all') matchesFilter = (code === activeFilter);

    const visible = matchesSearch && matchesFilter;
    item.el.style.display = visible ? '' : 'none';
    if (visible) visibleCount++;
  });

  els.emptyMsg.style.display = visibleCount === 0 && (searchQuery || activeFilter !== 'all') ? 'block' : 'none';

  const total = students.length;
  ['all', 'unmarked', 'p', 'x', 'l', 'e', 'r'].forEach((f, i) => {
    const el = document.getElementById('fcount-' + f);
    if (el) el.textContent = f === 'all' ? total : (f === 'unmarked' ? counts.unmarked : counts[f]);
  });

  ['cp', 'cx', 'cl', 'ce', 'cr'].forEach((id, i) => {
    const el = document.getElementById(id);
    const code = CODES[i];
    if (el) el.textContent = `${CODE_LETTERS[code]} ${counts[code]}`;
  });

  if (els.saveDot) els.saveDot.classList.toggle('dirty', dirty);
  if (els.saveText) els.saveText.textContent = dirty ? 'Save *' : 'Save';
  if (els.saveBtn) els.saveBtn.classList.toggle('dirty', dirty);

  if (els.rollView.style.display !== 'none') renderRollCall();

  // Auto-save draft every 2s when dirty
  if (dirty) { clearTimeout(paint._draftTimer); paint._draftTimer = setTimeout(saveDraft, 2000); }
}

// --- Filter Pills ---
document.querySelectorAll('.fpill').forEach(pill => {
  pill.addEventListener('click', () => {
    haptic('select');
    document.querySelectorAll('.fpill').forEach(p => p.classList.remove('on'));
    pill.classList.add('on');
    activeFilter = pill.dataset.filter;
    paint();
  });
});

// --- Search ---
els.search.addEventListener('input', e => {
  searchQuery = e.target.value.toLowerCase().trim();
  els.clearSearch.style.display = searchQuery ? 'flex' : 'none';
  paint();
});
els.clearSearch.addEventListener('click', () => {
  haptic('light');
  els.search.value = '';
  searchQuery = '';
  els.clearSearch.style.display = 'none';
  els.search.focus();
  paint();
});

// --- View Mode Toggle ---
function setMode(mode) {
  haptic('medium');
  if (mode === 'roll') {
    els.listView.style.display = 'none';
    els.rollView.style.display = 'block';
    els.btnRoll.classList.add('on');
    els.btnList.classList.remove('on');
    curRollIndex = 0;
    rollCallStartTime = Date.now();
    studentStartTime = Date.now();
    renderRollCall();
  } else {
    els.listView.style.display = 'block';
    els.rollView.style.display = 'none';
    els.btnList.classList.add('on');
    els.btnRoll.classList.remove('on');
  }
}
els.btnList.addEventListener('click', () => setMode('list'));
els.btnRoll.addEventListener('click', () => setMode('roll'));

// --- List View Actions ---
function selectCode(index, code) {
  if (students[index].code === code) return;
  students[index].code = code;
  dirty = true;
  paint();
  haptic('medium');
}
document.getElementById('allP').addEventListener('click', () => {
  haptic('success');
  students.forEach(s => s.code = 'p');
  dirty = true;
  paint();
  toast('All marked Present', 'ok');
});
document.getElementById('clearAll').addEventListener('click', () => {
  if (!confirm('Clear all attendance marks for this date?')) return;
  haptic('warning');
  students.forEach(s => s.code = '');
  dirty = true;
  paint();
  toast('Attendance cleared', 'warn');
});

// --- Roll-Call Mode ---
function renderRollCall() {
  const total = students.length;
  if (curRollIndex >= total) {
    showRollComplete();
    return;
  }
  els.rcMain.style.display = 'block';
  els.rcDone.style.display = 'none';

  const s = students[curRollIndex];
  els.rcIndex.textContent = `Student ${curRollIndex + 1} of ${total}`;
  els.rcName.textContent = s.name;

  const code = s.code;
  els.rcPill.textContent = code ? `Currently: ${CODE_NAMES[code]}` : 'Not marked yet';
  els.rcPill.className = 'rc-current-pill ' + (code || 'blank');
  if (code) els.rcPill.classList.add(code);

  const pct = Math.round((curRollIndex / total) * 100);
  els.rcProgress.style.width = pct + '%';
  els.rcCounter.textContent = `Student ${curRollIndex + 1} of ${total}`;
  els.rcPercent.textContent = pct + '%';

  studentStartTime = Date.now();
}

function showRollComplete() {
  els.rcMain.style.display = 'none';
  els.rcDone.style.display = 'block';
  els.rcProgress.style.width = '100%';
  els.rcCounter.textContent = `All ${students.length} Students Checked`;
  els.rcPercent.textContent = '100%';

  const counts = { p: 0, x: 0, l: 0, e: 0, r: 0 };
  students.forEach(s => { if (s.code) counts[s.code]++; });
  els.rcStats.innerHTML =
    '<span class="dcount s-p">P ' + counts.p + '</span>' +
    '<span class="dcount s-x">A ' + counts.x + '</span>' +
    '<span class="dcount s-l">L ' + counts.l + '</span>' +
    '<span class="dcount s-e">E ' + counts.e + '</span>' +
    '<span class="dcount s-r">R ' + counts.r + '</span>';

  celebrate();
  haptic('success');
  toast('Roll call complete!', 'ok');
}

// Roll-call big buttons
document.querySelectorAll('.rc-big-btn').forEach(btn => {
  btn.addEventListener('click', () => handleRollSelect(btn.dataset.code));
  btn.addEventListener('touchstart', () => btn.style.transform = 'scale(0.96)', { passive: true });
  btn.addEventListener('touchend', () => btn.style.transform = '', { passive: true });
  btn.addEventListener('touchcancel', () => btn.style.transform = '', { passive: true });
});

function handleRollSelect(code) {
  haptic('medium');
  students[curRollIndex].code = code;
  dirty = true;
  curRollIndex++;
  paint();
  renderRollCall();
}

document.getElementById('rcBtnPrev').addEventListener('click', () => {
  haptic('light');
  if (curRollIndex > 0) { curRollIndex--; renderRollCall(); }
});
document.getElementById('rcBtnSkip').addEventListener('click', () => {
  haptic('light');
  if (curRollIndex < students.length) { curRollIndex++; renderRollCall(); }
});
document.getElementById('rcBtnSwitchList').addEventListener('click', () => setMode('list'));
document.getElementById('doneReviewBtn').addEventListener('click', () => { curRollIndex = 0; setMode('list'); });
document.getElementById('doneSaveBtn').addEventListener('click', saveAttendance);

// --- Keyboard Shortcuts ---
window.addEventListener('keydown', e => {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault(); saveAttendance(); return;
  }
  if (els.rollView.style.display !== 'none') {
    const k = e.key.toLowerCase();
    if (CODES.includes(k)) { handleRollSelect(k); }
    else if (k === 'arrowleft') { document.getElementById('rcBtnPrev').click(); }
    else if (k === 'arrowright') { document.getElementById('rcBtnSkip').click(); }
    else if (k === 'backspace' && curRollIndex > 0) { curRollIndex--; renderRollCall(); haptic('light'); }
  }
});

// --- Roll-Call Swipe Gestures (on flashcard) ---
const rcCard = els.rcMain;
rcCard.addEventListener('touchstart', e => {
  gestureStartX = e.touches[0].clientX;
  gestureStartY = e.touches[0].clientY;
  isGesturing = true;
  rcCard.style.transition = 'none';
}, { passive: true });
rcCard.addEventListener('touchmove', e => {
  if (!isGesturing) return;
  const dx = e.touches[0].clientX - gestureStartX;
  const dy = e.touches[0].clientY - gestureStartY;
  if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 15) {
    e.preventDefault();
    const clamped = Math.max(-100, Math.min(100, dx));
    rcCard.style.transform = `translateX(${clamped}px) rotate(${clamped * 0.05}deg)`;
    // Visual hint
    if (dx > 50) rcCard.dataset.gesture = 'right';
    else if (dx < -50) rcCard.dataset.gesture = 'left';
    else delete rcCard.dataset.gesture;
  }
}, { passive: false });
rcCard.addEventListener('touchend', e => {
  if (!isGesturing) return;
  isGesturing = false;
  rcCard.style.transition = 'transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)';
  const dx = e.changedTouches[0].clientX - gestureStartX;
  const dy = e.changedTouches[0].clientY - gestureStartY;
  rcCard.style.transform = '';
  delete rcCard.dataset.gesture;

  if (Math.abs(dx) > Math.abs(dy)) {
    if (dx > 70) { handleRollSelect('p'); } // Swipe right = Present
    else if (dx < -70) { handleRollSelect('x'); } // Swipe left = Absent
    else if (dy < -70) { handleRollSelect('l'); } // Swipe up = Late
    else if (dy > 70) { handleRollSelect('e'); } // Swipe down = Excused
  }
}, { passive: true });

// --- Topic input dirty tracking ---
if (els.topic) {
  els.topic.addEventListener('input', () => {
    dirty = true;
    if (els.saveDot) els.saveDot.classList.add('dirty');
  });
}

// --- Save / Sync ---
async function saveAttendance(silent = false) {
  const unmarked = students.filter(s => !s.code).length;
  if (unmarked === students.length && !wasRecorded) {
    if (!silent) toast('No students marked yet. Mark at least one first.', 'err');
    return false;
  }
  if (unmarked > 0 && !silent) {
    if (!confirm(`${unmarked} student${unmarked > 1 ? 's are' : ' is'} unmarked. Save anyway?`)) return false;
  }

  els.saveBtn.disabled = true;
  if (els.saveText) els.saveText.textContent = 'Saving...';

  const payload = {
    subject,
    section: typeof section !== 'undefined' ? section : '',
    date: dateIso,
    topic: els.topic?.value || '',
    marks: students.map(s => ({ row: s.row, name: s.name, code: s.code, clear: !s.code })),
  };

  try {
    const res = await fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      dirty = false;
      wasRecorded = true;
      clearDraft();
      haptic('success');
      if (!silent) toast('Saved ✓', 'ok');
      const badgeSlot = document.querySelector('.date-badge-slot');
      if (badgeSlot) badgeSlot.innerHTML = '<span class="badge done">✓ Saved</span>';
      if (els.saveDot) els.saveDot.classList.remove('dirty');
      if (els.saveText) els.saveText.textContent = 'Save';
      pendingSync = false;
      return true;
    } else {
      throw new Error(data.error || 'Save failed');
    }
  } catch (err) {
    dirty = true;
    saveDraft(); // Keep local draft
    if (!isOnline) {
      pendingSync = true;
      if (!silent) toast('Saved offline. Will sync when online.', 'warn');
    } else {
      if (!silent) toast('Save failed: ' + err.message, 'err');
    }
    if (els.saveText) els.saveText.textContent = dirty ? 'Save *' : 'Save';
    return false;
  } finally {
    els.saveBtn.disabled = false;
    paint();
  }
}
els.saveBtn.addEventListener('click', () => saveAttendance());

// --- Before Unload ---
window.addEventListener('beforeunload', e => {
  if (dirty) {
    saveDraft();
    e.preventDefault();
    e.returnValue = 'You have unsaved attendance changes.';
  }
});

// --- Restore Draft on Load ---
if (loadDraft()) {
  dirty = true;
  paint();
}

// --- Pull to Refresh (List View) ---
let pullStartY = 0, pullCurrentY = 0, pulling = false;
const pullThreshold = 80;
const listContainer = els.listView;

listContainer.addEventListener('touchstart', e => {
  if (window.scrollY === 0) {
    pullStartY = e.touches[0].clientY;
    pulling = true;
    listContainer.style.transition = 'none';
  }
}, { passive: true });
listContainer.addEventListener('touchmove', e => {
  if (!pulling) return;
  pullCurrentY = e.touches[0].clientY;
  const dy = pullCurrentY - pullStartY;
  if (dy > 10) {
    e.preventDefault();
    const progress = Math.min(1, dy / pullThreshold);
    listContainer.style.transform = `translateY(${dy * 0.5}px)`;
    listContainer.style.opacity = 1 - progress * 0.3;
    if (dy > pullThreshold) listContainer.dataset.pullReady = 'true';
    else delete listContainer.dataset.pullReady;
  }
}, { passive: false });
listContainer.addEventListener('touchend', () => {
  if (!pulling) return;
  pulling = false;
  listContainer.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.3s';
  if (listContainer.dataset.pullReady) {
    haptic('medium');
    toast('Refreshing...', 'ok');
    setTimeout(() => { location.reload(); }, 300);
  }
  listContainer.style.transform = '';
  listContainer.style.opacity = '';
  delete listContainer.dataset.pullReady;
}, { passive: true });

// --- Service Worker Registration ---
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
    .then(reg => console.log('SW registered:', reg.scope))
    .catch(err => console.log('SW registration failed:', err));
}

// --- Initialize ---
paint();

// --- Export for debugging ---
window.__attendance = { students, paint, saveAttendance, toast, haptic };