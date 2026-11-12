const $ = id => document.getElementById(id);
let entries = [], override = {}, blob = null;

function toast(msg, bad) {
  const t = $('toast'); t.textContent = msg; t.className = 'toast' + (bad ? ' err' : '');
  t.style.display = 'block'; clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = 'none', bad ? 6000 : 2500);
}
function showErr(msg) { const e = $('err'); e.textContent = msg; e.style.display = msg ? 'block' : 'none'; }

if ($('keySave')) $('keySave').onclick = async () => {
  const r = await fetch(KEY_URL, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: $('keyIn').value})});
  const j = await r.json();
  if (j.ok) { location.reload(); } else { $('keyMsg').textContent = j.error; }
};

// shrink big phone photos in the browser before uploading
async function shrink(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    const max = 2000, k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    return await new Promise(res => c.toBlob(res, 'image/jpeg', 0.88));
  } finally { URL.revokeObjectURL(url); }
}

const MAX_IMAGES = MAX_IMAGES_LIMIT;
let blobs = [];
function showPreviews() {
  const box = $('previews'); box.textContent = '';
  blobs.forEach(b => {
    const im = document.createElement('img'); im.alt = ''; im.src = URL.createObjectURL(b);
    im.style.cssText = 'height:110px;border-radius:8px;border:1px solid var(--line)';
    box.appendChild(im);
  });
  $('read').textContent = blobs.length > 1 ? ('Read these ' + blobs.length + ' images') : 'Read the sheet';
  $('read').disabled = !blobs.length;
}
$('file').onchange = async e => {
  let files = Array.from(e.target.files); blobs = []; showErr(''); showPreviews();
  if (files.length > MAX_IMAGES) { showErr('Please choose at most ' + MAX_IMAGES + ' images. Using the first ' + MAX_IMAGES + '.'); files = files.slice(0, MAX_IMAGES); }
  try {
    for (const f of files) blobs.push(await shrink(f));
    showPreviews();
  } catch (err) { blobs = []; showPreviews(); showErr('One of those files could not be opened as a picture. Try JPG or PNG images.'); }
};

$('read').onclick = async () => {
  if (!blobs.length) return;
  $('read').disabled = true; $('busy').textContent = 'Reading… this can take up to a minute if the AI service is busy.'; showErr('');
  const fd = new FormData(); fd.append('subject', subject);
  blobs.forEach((b, i) => fd.append('image', b, 'sheet' + (i + 1) + '.jpg'));
  try {
    const r = await fetch(SCAN_URL, {method: 'POST', body: fd});
    const j = await r.json();
    if (!j.ok) { showErr(j.error || 'Could not read the sheet.'); if (j.code === 'no_key') location.reload(); }
    else startReview(j.result);
  } catch (err) { showErr('Could not reach the site. Is the black window still open?'); }
  $('busy').textContent = ''; $('read').disabled = !blobs.length;
};

function startReview(res) {
  entries = res.entries.map(e => Object.assign({}, e, {orig: e.roster_match, assign: e.roster_match}));
  override = {};
  if (!entries.length) { showErr('I could not find any names on those images. Try clearer, straight-on photos.'); return; }
  const marked = entries.filter(e => e.mark === 'signed' || e.mark === 'checked').length;
  const withPct = entries.filter(e => e.attended_percent >= 0).length;
  $('mode').value = (withPct / entries.length >= 0.5) ? 'percent' : (marked / entries.length >= 0.5) ? 'marks' : 'list';
  $('unDetails').open = entries.filter(e => e.orig === '').length <= 3;
  $('date').value = '';
  $('dateNote').textContent = res.date_text ? ('The sheet says: ' + res.date_text + '. The date is left empty on purpose, so pick it yourself.') : 'No date was found on the sheet. Pick the date yourself.';
  $('step1').style.display = 'none'; $('review').style.display = 'block'; $('done').style.display = 'none';
  render(); window.scrollTo(0, 0);
}

function autoStatus(e) {
  if (e && e.written_status) return e.written_status;
  if (e && e.mark === 'crossed_out') return 'x';
  const m = $('mode').value;
  if (m === 'list') return e ? 'p' : 'x';
  if (m === 'percent') {
    if (!e) return 'x';
    if (e.attended_percent < 0) return 'p';          // listed but no percentage shown
    return e.attended_percent >= (parseFloat($('thr').value) || 0) ? 'p' : 'x';
  }
  return (e && (e.mark === 'signed' || e.mark === 'checked')) ? 'p' : 'x';
}
function rowsData() {
  const out = students.map(s => ({key: s.name, name: s.name, row: s.row, isNew: false, e: entries.find(x => x.assign === s.name)}));
  entries.filter(x => x.assign === '__new__').forEach((e, i) => out.push({key: '__new__' + i, name: e.written_name, row: null, isNew: true, e: e}));
  out.forEach(r => { r.auto = autoStatus(r.e); r.code = override[r.key] || r.auto; });
  return out;
}
const MARKS = {signed: '✍ signed', checked: '✓ ticked', crossed_out: '✗ crossed out', none: 'no mark'};

function render() {
  const rows = rowsData(), box = $('rows'); box.textContent = '';
  const n = {p: 0, x: 0, l: 0, e: 0};
  const md = $('mode').value;
  $('thrWrap').style.display = md === 'percent' ? 'inline' : 'none';
  $('modeNote').textContent = md === 'list'
    ? 'Everyone found on the sheet is Present; everyone else on your class list is Absent.'
    : md === 'percent'
    ? 'Students who attended at least ' + ($('thr').value || 0) + '% are Present; anyone below that, or not in the report, is Absent. Change the number if your rule is different.'
    : 'Only students with a signature or tick are Present; the rest are Absent.';
  rows.forEach(r => {
    n[r.code]++;
    const div = document.createElement('div');
    const doubt = r.e && r.e.confidence !== 'high';
    div.className = 'srow' + (doubt ? ' needs' : '');
    const nm = document.createElement('div'); nm.className = 'sname';
    nm.appendChild(document.createTextNode(r.name));
    if (r.isNew) { const t = document.createElement('span'); t.className = 'tag new'; t.textContent = 'NEW'; nm.appendChild(t); }
    if (doubt) { const t = document.createElement('span'); t.className = 'tag warn'; t.textContent = 'check'; nm.appendChild(t); }
    const sub = document.createElement('div'); sub.className = 'sub';
    sub.textContent = r.e
      ? ('Read as “' + r.e.written_name + '” · ' + (md === 'percent' && r.e.attended_percent >= 0 ? (r.e.attended_percent + '% attended') : (MARKS[r.e.mark] || '')))
      : 'Not found on the sheet';
    nm.appendChild(sub);
    const g = document.createElement('div'); g.className = 'btns';
    ['p', 'x', 'l', 'e'].forEach(c => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'cb sm ' + c + (r.code === c ? ' on' : '');
      b.textContent = c === 'x' ? 'A' : c.toUpperCase();
      b.onclick = () => { override[r.key] = c; render(); };
      g.appendChild(b);
    });
    div.appendChild(nm); div.appendChild(g); box.appendChild(div);
  });
  $('cp').textContent = 'P ' + n.p; $('cx').textContent = 'A ' + n.x; $('cl').textContent = 'L ' + n.l; $('ce').textContent = 'E ' + n.e;

  // names that could not be matched
  const un = entries.filter(e => e.orig === ''), ub = $('unmatched'); ub.textContent = '';
  $('unmatchedCard').style.display = un.length ? 'block' : 'none';
  $('unSummary').textContent = un.length + (un.length === 1 ? ' name is' : ' names are') + " not on your class list and " + (un.length === 1 ? 'is' : 'are') + ' ignored. Tap to review.';
  un.forEach(e => {
    const row = document.createElement('div'); row.className = 'srow';
    const nm = document.createElement('div'); nm.className = 'sname'; nm.textContent = e.written_name;
    const sel = document.createElement('select'); sel.className = 'slim';
    const add = (v, t) => { const o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o); };
    add('', 'Ignore this name'); add('__new__', 'Add as a new student');
    students.forEach(s => add(s.name, 'Same person as: ' + s.name));
    sel.value = e.assign;
    sel.onchange = () => { e.assign = sel.value; render(); };
    row.appendChild(nm); row.appendChild(sel); ub.appendChild(row);
  });
}
$('mode').onchange = render;
$('thr').oninput = render;

function reset() {
  $('review').style.display = 'none'; $('done').style.display = 'none'; $('step1').style.display = 'block';
  $('file').value = ''; blobs = []; showPreviews(); showErr('');
}
$('cancel').onclick = () => { if (confirm('Discard this scan? Nothing has been saved.')) reset(); };
$('again').onclick = reset;

$('confirm').onclick = async () => {
  const d = $('date').value;
  if (!d) { toast('Pick a date first.', true); $('date').focus(); return; }
  if (recorded.includes(d) && !confirm('Attendance for ' + d + ' is already recorded. Replace it with this scan?')) return;
  const rows = rowsData(), btn = $('confirm'); btn.disabled = true;
  try {
    const r = await fetch(SAVE_URL, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subject, date: d, topic: $('topic').value, source: 'scan',
        new_students: rows.filter(x => x.isNew).map(x => x.name),
        marks: rows.map(x => ({row: x.row, name: x.name, code: x.code}))})});
    const j = await r.json();
    if (j.ok) {
      if (!recorded.includes(d)) recorded.push(d);
      const c = {p: 0, x: 0, l: 0, e: 0}; rows.forEach(x => c[x.code]++);
      $('doneMsg').textContent = d + ': ' + c.p + ' present, ' + c.x + ' absent, ' + c.l + ' late, ' + c.e + ' excused.';
      $('doneLink').href = recordsUrl;
      $('review').style.display = 'none'; $('done').style.display = 'block'; window.scrollTo(0, 0);
    } else { toast(j.error || 'Could not save.', true); }
  } catch (err) { toast('Could not reach the site. Is the black window still open?', true); }
  btn.disabled = false;
};
