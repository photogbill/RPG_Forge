// BUILD 42 — Characters → Profiles: the whole cast as a board (up close · at range · other, or whatever rows the game's
// schema names), coloured by how each entry is known, and a page per character that edits in place.
// Loaded after the shell's own script; it uses the shell's helpers (api, post, toast, esc, modal, closeModal, go, setAddr, gid …).
// Everything on the page is drawn from the game's profiles/_schema.json — no game is named here.
(function () {
'use strict';
const css = `
#v-profiles{max-width:1640px}
.pf-top{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 10px}
.pf-top input[type=search]{font:inherit;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:8px;padding:6px 9px;width:200px}
.pf-top select{font:inherit;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:8px;padding:6px 8px}
.pf-chip{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:3px 11px;background:var(--panel);color:var(--dim);cursor:pointer;user-select:none}
.pf-chip.on{border-color:var(--accent);color:var(--ink);background:#2a2418}
.pf-head{font-size:13px;color:#cfccc5;background:#16161c;border-left:3px solid var(--accent);padding:7px 11px;border-radius:0 8px 8px 0;margin:0 0 10px}
.pf-legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12.5px;color:var(--dim);margin:0 0 10px}
.pf-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.pf-lay{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;align-items:start}
.pf-lay.open{grid-template-columns:minmax(0,1fr) minmax(460px,600px)}
@media(max-width:1250px){.pf-lay.open{grid-template-columns:1fr}}
.pf-board{width:100%;border-collapse:separate;border-spacing:0 3px;table-layout:fixed;font-size:13px}
.pf-board th{font-size:12px;color:var(--faint);font-weight:600;text-align:left;padding:2px 8px;position:sticky;top:0;background:var(--bg)}
.pf-board td{padding:5px 8px;background:var(--panel);vertical-align:top;overflow:hidden;text-overflow:ellipsis}
.pf-board tr{cursor:pointer}.pf-board tr:hover td{background:var(--panel2)}
.pf-board tr.sel td{background:var(--panel2);box-shadow:inset 0 1px 0 var(--line),inset 0 -1px 0 var(--line)}
.pf-board tr.sel td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.pf-board td:first-child{border-radius:8px 0 0 8px}.pf-board td:last-child{border-radius:0 8px 8px 0}
.pf-name b{font-weight:620}.pf-name span{display:block;font-size:11.5px;color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pf-cell{border-left:4px solid var(--c);background:color-mix(in srgb,var(--c) 13%,var(--panel))!important;line-height:1.3}
.pf-cell small{display:block;font-size:10.5px;color:var(--c);opacity:.95;letter-spacing:.02em}
.pf-cell span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pf-flags{font-size:12px;color:var(--warn);white-space:nowrap}
.pf-page{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;position:sticky;top:0;max-height:calc(100vh - 150px);overflow:auto}
.pf-page h2{margin:0 0 2px;font-size:19px}.pf-page .pf-file{font-size:11.5px;color:var(--faint);margin-bottom:10px}
.pf-sec{border-top:1px solid var(--line);padding:10px 0 4px;margin-top:8px}
.pf-sec h3{font-size:13.5px;margin:0 0 8px;color:var(--dim);font-weight:640;letter-spacing:.02em;text-transform:uppercase}
.pf-f{display:grid;grid-template-columns:150px minmax(0,1fr);gap:4px 10px;align-items:start;margin-bottom:6px}
.pf-f label{font-size:12.5px;color:var(--dim);padding-top:6px}
.pf-f input,.pf-f select,.pf-f textarea,.pf-add input{font:inherit;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:8px;padding:6px 8px;width:100%}
.pf-f textarea{min-height:64px;resize:vertical}.pf-f textarea.big{min-height:120px}
.pf-f .who{grid-column:2;font-size:11px;color:var(--faint);margin-top:-2px;border:0;background:none;padding:0 2px}
.pf-f input.dirty,.pf-f textarea.dirty{border-color:var(--warn)}
.pf-multi{display:flex;gap:12px;padding-top:5px}.pf-multi label{padding:0;display:flex;gap:4px;align-items:center;color:var(--ink)}
.pf-row{background:#16161c;border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:9px 11px;margin-bottom:9px}
.pf-row>.h{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}.pf-row>.h b{font-size:14px}
.pf-row>.h .st{font-size:11.5px;color:var(--c)}.pf-row>.h .sp{flex:1}
.pf-row>.h button,.pf-ent button,.pf-q button{padding:3px 9px;font-size:12px}
.pf-ent{border:1px solid #2a2a34;border-left:3px solid var(--c);border-radius:8px;padding:7px 9px;margin:5px 0;background:#121217}
.pf-ent .w{display:flex;gap:6px;align-items:center}.pf-ent .w input{flex:1;font:inherit;font-weight:600;color:var(--ink);background:transparent;border:1px solid transparent;border-radius:6px;padding:3px 6px}
.pf-ent .w input:hover,.pf-ent .w input:focus{border-color:var(--line);background:#16161c}
.pf-ent .st{font-size:11px;color:var(--c);white-space:nowrap}
.pf-ent .src{font-size:12.5px;color:#cfccc5;margin:3px 0 2px}.pf-ent .src q{font-style:italic;color:#e8e1cf}.pf-ent .src i{color:var(--dim)}
.pf-ent .meta{display:grid;grid-template-columns:90px minmax(0,1fr) 110px minmax(0,1fr);gap:4px 8px;align-items:center;font-size:12px;color:var(--dim);margin-top:4px}
.pf-ent .meta input{font:inherit;font-size:12px;color:var(--ink);background:#16161c;border:1px solid var(--line);border-radius:6px;padding:3px 6px;width:100%}
.pf-ent .acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.pf-none{font-size:13px;color:#d8d6de;margin:2px 0 4px}.pf-none i{color:var(--dim)}
.pf-add{display:flex;gap:6px;margin-top:6px}.pf-add input{flex:1}
.pf-links a,.pf-links span{display:block;font-size:13px;margin:2px 0}.pf-links .no{color:var(--faint)}
.pf-voice{font-size:13px;color:#cfccc5}.pf-voice.ask{color:var(--warn)}
.pf-q{display:flex;gap:8px;align-items:flex-start;font-size:13px;margin:4px 0;padding:6px 8px;background:#16161c;border-radius:8px}
.pf-q .t{flex:1}.pf-q.closed .t{text-decoration:line-through;color:var(--faint)}.pf-q small{display:block;color:var(--faint);font-size:11.5px}
.pf-dif{font-size:12.5px;color:#f0d08a;background:#2a2418;border:1px solid #6b5420;border-radius:8px;padding:7px 10px;margin:6px 0}
.pf-dif div{margin:2px 0}
.pf-hits{max-height:62vh;overflow:auto;display:flex;flex-direction:column;gap:6px}
.pf-hit{background:#16161c;border:1px solid var(--line);border-radius:8px;padding:7px 10px;font-size:13px}
.pf-hit .s{font-size:11.5px;color:var(--faint)}.pf-hit .c{color:var(--dim);font-size:12px;margin-top:2px}.pf-hit mark{background:#5a4a22;color:#ffe2a0;border-radius:3px;padding:0 2px}
.pf-empty{color:var(--dim);font-size:13.5px;line-height:1.6;max-width:760px}
`;
const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

const P = {board: null, sel: null, page: null, f: {game: '', kind: '', q: '', chips: new Set()}, dirty: new Map()};
const $ = s => document.querySelector(s);
const V = () => $('#v-profiles');
const look = s => ((P.board && P.board.schema.states) || {})[s] || {label: s, color: '#888'};
const colorOf = s => look(s).color;

async function loadProfiles(rest) {
  const want = rest && rest[0] ? decodeURIComponent(rest[0]) : null;
  let b;
  try { b = await api(`/api/suite/profiles?id=${encodeURIComponent(gid())}`); } catch (e) { V().innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  if (b.error) { paintMissing(b); return; }
  P.board = b;
  if (want) P.sel = want;
  paint();
  if (P.sel) openPage(P.sel, false);
}
window.loadProfiles = loadProfiles;

function paintMissing(b) {
  V().innerHTML = `<div class="pf-empty"><h2 style="margin-top:0">Profiles</h2><p>${esc(b.error)}.</p>
  ${b.missing && b.can_fill ? `<p>This game's adapter can make the first pages from the game's own sources — the songs, the canon document, the game's data and the rulings book. It guesses nothing: where nothing says, a cell stays <b>open</b>. It never overwrites anything a person has written, and you can run it again any time.</p>
  <p><button class="go" id="pf-fill1">Make the first pages</button></p>` : `<p>Copy <code>${esc((b.folder || 'profiles') + '/_schema.json')}</code> from the example game into this game's folder and change its sections to suit.</p>`}</div>`;
  const f = $('#pf-fill1'); if (f) f.onclick = () => doFill(false);
}

async function doFill(ask) {
  const run = async () => {
    const r = await post('profile_fill', {game: gid()});
    toast(r.message, r.ok);
    if (r.ok && r.skipped && r.skipped.length) modal(`<h3>Filled — and what it left alone</h3><p>${esc(r.message)}</p><div class="pf-hits">${r.skipped.map(s => `<div class="pf-hit">${esc(s)}</div>`).join('')}</div><div class="row"><button class="go" onclick="closeModal()">OK</button></div>`, true);
    loadProfiles([]);
  };
  if (!ask) return run();
  confirmAct('Fill again from the sources', 'Adds what the songs, the canon document, the game\'s data and the rulings book say that the pages don\'t have yet. Nothing you wrote is changed; nothing already there is added twice.', 'Fill again', run);
}

function matches(l) {
  const f = P.f;
  if (f.game && !(l.games || []).includes(f.game)) return false;
  if (f.kind && l.kind !== f.kind) return false;
  if (f.q) { const q = f.q.toLowerCase(); const hay = (l.name + ' ' + l.line + ' ' + Object.values(l.cells).map(c => c.text).join(' ')).toLowerCase(); if (!hay.includes(q)) return false; }
  for (const c of f.chips) if (!(l.flags || []).includes(c)) return false;
  return true;
}

function paint() {
  const b = P.board, rows = b.rows || [];
  const games = [...new Set(b.lines.flatMap(l => l.games || []))].sort();
  const kinds = [...new Set(b.lines.map(l => l.kind).filter(Boolean))].sort();
  const chips = [['open', 'has an open cell'], ...rows.map(r => ['no:' + r.id, 'no ' + r.label.toLowerCase()]), ['differs', "differs from the game's data"]];
  const shown = b.lines.filter(matches);
  const states = b.schema.states;
  V().innerHTML = `
  ${b.header ? `<div class="pf-head">${esc(b.header)}</div>` : ''}
  <div class="pf-legend">${['songs', 'owner', 'proposed', 'open', 'none'].map(s => `<span><i style="background:${states[s].color}"></i>${esc(states[s].label)} <b>${b.counts[s] || 0}</b></span>`).join('')}</div>
  <div class="pf-top">
    <input type="search" id="pf-q" placeholder="find a name or a weapon" value="${esc(P.f.q)}">
    <select id="pf-game"><option value="">every game</option>${games.map(g => `<option ${P.f.game === g ? 'selected' : ''}>${esc(g)}</option>`).join('')}</select>
    <select id="pf-kind"><option value="">every kind</option>${kinds.map(k => `<option ${P.f.kind === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>
    ${chips.map(([id, w]) => `<span class="pf-chip ${P.f.chips.has(id) ? 'on' : ''}" data-chip="${esc(id)}">${esc(w)}</span>`).join('')}
    <span style="flex:1"></span>
    <span style="font-size:12.5px;color:var(--faint)">${shown.length} of ${b.lines.length}</span>
    <button id="pf-addc">Add a character</button>
    <button class="ghost" id="pf-fill" title="Adds what the game's sources say and the pages don't have yet — never changes what you wrote">Fill again</button>
  </div>
  <div class="pf-lay ${P.sel ? 'open' : ''}">
    <div><table class="pf-board"><colgroup><col style="width:24%">${rows.map(() => `<col style="width:${Math.floor(68 / Math.max(1, rows.length))}%">`).join('')}<col style="width:8%"></colgroup>
      <thead><tr><th>Character</th>${rows.map(r => `<th>${esc(r.label)}</th>`).join('')}<th></th></tr></thead>
      <tbody>${shown.map(l => `<tr data-p="${esc(l.id)}" class="${P.sel === l.id ? 'sel' : ''}">
        <td class="pf-name"><b>${esc(l.name)}</b><span>${esc([l.kind, (l.games || []).join(' · ')].filter(Boolean).join(' — ') || l.line || '')}</span></td>
        ${rows.map(r => { const c = l.cells[r.id] || {state: 'open', text: ''}; return `<td class="pf-cell" style="--c:${colorOf(c.state)}" title="${esc(look(c.state).label + (c.text ? ': ' + c.text : ''))}"><small>${esc(look(c.state).label)}</small><span>${esc(c.text || '—')}</span></td>`; }).join('')}
        <td class="pf-flags">${(l.flags || []).includes('differs') ? `<span title="${esc((l.differs || []).join('\n'))}">⚑ differs</span>` : ''}${l.questions ? `<div title="open questions">? ${l.questions}</div>` : ''}</td></tr>`).join('')}</tbody></table></div>
    <div id="pf-page">${P.sel ? '<div class="pf-page">Opening…</div>' : ''}</div>
  </div>`;
  $('#pf-q').oninput = e => { P.f.q = e.target.value; repaintKeepFocus('#pf-q'); };
  $('#pf-game').onchange = e => { P.f.game = e.target.value; paint(); if (P.page) paintPage(); };
  $('#pf-kind').onchange = e => { P.f.kind = e.target.value; paint(); if (P.page) paintPage(); };
  V().querySelectorAll('[data-chip]').forEach(c => c.onclick = () => { const id = c.dataset.chip; P.f.chips.has(id) ? P.f.chips.delete(id) : P.f.chips.add(id); paint(); if (P.page) paintPage(); });
  V().querySelectorAll('tr[data-p]').forEach(tr => tr.onclick = () => openPage(tr.dataset.p, true));
  $('#pf-addc').onclick = addCharacter;
  $('#pf-fill').onclick = () => doFill(true);
  if (P.page && P.sel) paintPage();
}
function repaintKeepFocus(sel) { const el = $(sel); const pos = el ? el.selectionStart : 0; paint(); const n = $(sel); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) {} } }

function addCharacter() {
  modal(`<h3>Add a character</h3><p>Only the name — everything else you fill in on the page.</p><input id="pf-nn" style="width:100%" placeholder="name"><div class="row"><button class="ghost" onclick="closeModal()">Cancel</button><button class="go" id="m-ok">Add</button></div>`);
  setTimeout(() => $('#pf-nn').focus(), 30);
  const ok = async () => { const r = await post('profile_add', {game: gid(), name: $('#pf-nn').value}); toast(r.message, r.ok); if (r.ok) { closeModal(); P.sel = r.id; loadProfiles([r.id]); } };
  $('#m-ok').onclick = ok; $('#pf-nn').onkeydown = e => { if (e.key === 'Enter') ok(); };
}

async function openPage(pid, push) {
  await flushDirty();
  P.sel = pid;
  if (push) setAddr(addrOf('characters', 'profiles', pid));
  V().querySelectorAll('tr[data-p]').forEach(tr => tr.classList.toggle('sel', tr.dataset.p === pid));
  const lay = V().querySelector('.pf-lay'); if (lay) lay.classList.add('open');
  const r = await api(`/api/suite/profile?id=${encodeURIComponent(gid())}&p=${encodeURIComponent(pid)}`);
  if (r.error) { $('#pf-page').innerHTML = `<div class="pf-page"><div class="err">${esc(r.error)}</div></div>`; return; }
  P.page = r; paintPage();
}

function whoLine(p, ptr) { const m = (p._marks || {})[ptr]; if (!m) return ''; return `${m.fill ? 'filled by ' : ''}${esc(m.by)} · ${esc(String(m.time || '').slice(0, 10))}${m.from ? ' · from ' + esc(m.from) : ''}`; }

function srcLine(e) {
  const s = e.source || {}, o = P.page.schema.owner;
  const conf = s.confirmed ? ` · confirmed by ${esc(s.confirmed.by)} ${esc(s.confirmed.date)}` : '';
  if (s.text && s.song) return `<q>${esc(s.text)}</q> <i>— “${esc(s.song)}”${s.singer ? ', ' + esc(s.singer) : ''}</i>${conf}`;
  if (e.state === 'owner' || (s.ruling && s.text)) return `<i>${s.text ? '“' + esc(s.text) + '” — ' : ''}${esc(e.state === 'owner' ? (e.by || o) : o)}'s word${s.date ? ', ' + esc(s.date) : ''}${s.ruling ? ' · ruling ' + esc(s.ruling) : ''}</i>${conf}`;
  if (s.where || s.text) return `<i>${s.text ? '“' + esc(s.text) + '” — ' : ''}${esc(s.where || '')}</i>`;
  return `<i>${e.state === 'open' ? 'nobody knows yet' : 'no source given'}</i>`;
}

function paintPage() {
  const d = P.page; if (!d) return;
  const p = d.profile, sch = d.schema, person = G.identity && !/^claude/i.test(G.identity);
  const secHtml = sch.sections.map(sec => {
    const k = sec.kind || 'fields';
    if (k === 'fields') return `<div class="pf-sec"><h3>${esc(sec.label || sec.id)}</h3>${(sec.fields || []).map(f => fieldHtml(sec, f, p)).join('')}</div>`;
    if (k === 'rows') return `<div class="pf-sec"><h3>${esc(sec.label || sec.id)}</h3>${(sec.rows || []).map(r => rowHtml(sec, r, p, person)).join('')}</div>`;
    if (k === 'links') return `<div class="pf-sec"><h3>${esc(sec.label || sec.id)}</h3><div class="pf-links">${(d.links || []).length ? d.links.map(l => l.address ? `<a href="#${esc(l.address)}" class="${l.exists === false ? 'no' : ''}">${esc(l.label)}${l.note ? ' — ' + esc(l.note) : ''}</a>` : `<span class="${l.exists === false ? 'no' : ''}">${esc(l.label)}${l.path ? ': <code>' + esc(l.path) + '</code>' : ''}${l.note ? ' — ' + esc(l.note) : ''}</span>`).join('') : '<span class="no">nothing yet</span>'}</div></div>`;
    if (k === 'voice') return `<div class="pf-sec"><h3>${esc(sec.label || sec.id)}</h3><div class="pf-voice ${d.voice.ask ? 'ask' : ''}">${esc(d.voice.text)}${d.voice.address ? ` · <a href="#${esc(d.voice.address)}">the music profile</a>` : ''}</div></div>`;
    if (k === 'questions') { const qs = p[sec.id] || []; return `<div class="pf-sec"><h3>${esc(sec.label || sec.id)}</h3>${qs.map(q => `<div class="pf-q ${q.closed ? 'closed' : ''}"><div class="t">${esc(q.text)}<small>${esc(q.by)} · ${esc(String(q.time || '').slice(0, 10))}${q.mailed ? ' · mailed to ' + esc(q.mailed.to) : ''}${q.closed ? ' · closed by ' + esc(q.closed.by) + (q.closed.note ? ': ' + esc(q.closed.note) : '') : ''}</small></div>${q.closed ? '' : `${q.mailed ? '' : `<button data-qmail="${esc(q.id)}" title="send it as a letter">✉ Mail</button>`}<button class="ghost" data-qclose="${esc(q.id)}">Close</button>`}</div>`).join('')}
      <div class="pf-add"><input id="pf-qnew" placeholder="an open question about ${esc(d.name)}"><button id="pf-qadd">Add</button></div></div>`; }
    return '';
  }).join('');
  $('#pf-page').innerHTML = `<div class="pf-page">
    <div style="display:flex;gap:8px;align-items:flex-start"><div style="flex:1"><h2>${esc(d.name)}</h2><div class="pf-file">${esc(d.file)}</div></div>
      <button class="ghost" id="pf-undo" ${d.undo ? '' : 'disabled'} title="${d.undo ? esc('Puts back the page as it was before: ' + d.undo.what + ' (' + d.undo.who + ')') : 'nothing to undo'}">↶ Undo</button>
      <button class="ghost" id="pf-close" title="close the page">✕</button></div>
    ${d.differs.length ? `<div class="pf-dif"><b>Differs from the game's data</b> — shown, nothing changed:${d.differs.map(x => `<div>• ${esc(x)}</div>`).join('')}</div>` : ''}
    ${secHtml}</div>`;
  wirePage();
}

function fieldHtml(sec, f, p) {
  const v = (p[sec.id] || {})[f.id], ptr = `/${sec.id}/${f.id}`, k = f.kind || 'text', id = `pf-f-${sec.id}-${f.id}`;
  const attrs = `id="${id}" data-sec="${esc(sec.id)}" data-field="${esc(f.id)}" data-kind="${k}"`;
  let inp;
  if (f.readonly) inp = `<div style="padding-top:6px">${esc(Array.isArray(v) ? v.join(', ') : (v || '—'))}</div>`;
  else if (k === 'longtext') inp = `<textarea ${attrs} class="${f.id === 'notes' ? 'big' : ''}" placeholder="${esc(f.hint || '')}">${esc(v || '')}</textarea>`;
  else if (k === 'list') inp = `<textarea ${attrs} placeholder="one per line" style="min-height:44px">${esc((v || []).join('\n'))}</textarea>`;
  else if (k === 'choice') inp = `<select ${attrs}><option value=""></option>${(f.choices || []).map(c => `<option ${v === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
  else if (k === 'multi') inp = `<div class="pf-multi" ${attrs}>${(f.choices || []).map(c => `<label><input type="checkbox" value="${esc(c)}" ${(v || []).includes(c) ? 'checked' : ''}>${esc(c)}</label>`).join('')}</div>`;
  else if (k === 'number') inp = `<input ${attrs} type="number" step="any" style="max-width:120px" value="${esc(v ?? '')}" placeholder="${esc(f.hint || '')}">`;
  else inp = `<input ${attrs} value="${esc(v || '')}" placeholder="${esc(f.hint || '')}">`;
  const w = whoLine(p, ptr);
  return `<div class="pf-f"><label for="${id}">${esc(f.label || f.id)}</label>${inp}${w ? `<div class="who">${w}</div>` : ''}</div>`;
}

function rowHtml(sec, r, p, person) {
  const row = (p[sec.id] || {})[r.id] || {entries: [], none: null};
  const c = row.none ? 'none' : ((row.entries || []).length ? (row.entries.slice().sort((a, b) => rank(b.state) - rank(a.state))[0].state) : 'open');
  const ents = (row.entries || []).map(e => `<div class="pf-ent" style="--c:${colorOf(e.state)}" data-eid="${esc(e.id)}">
      <div class="w"><input data-ewhat="${esc(e.id)}" value="${esc(e.what || '')}" placeholder="what it is"><span class="st">${esc(look(e.state).label)}</span></div>
      <div class="src">${srcLine(e)}</div>
      <div class="meta"><span>seen in</span><input data-eseen="${esc(e.id)}" value="${esc(e.seen_in || '')}" placeholder="songs, scenes"><span>in the game's data as</span><input data-egame="${esc(e.id)}" value="${esc(e.game_id || '')}" placeholder="an item or ability id, or not yet"></div>
      ${e.note ? `<div class="src"><i>${esc(e.note)}</i></div>` : ''}
      <div class="acts">${person && e.state !== 'owner' && e.state !== 'open' ? `<button class="go" data-confirm="${esc(e.id)}" title="make it your word (it also goes into the rulings book)">✓ Confirm</button>` : ''}
        ${(e.state === 'owner' || e.state === 'songs') && (!e.game_id || e.game_id === 'not yet') ? `<button data-order="${esc(e.id)}" title="the game's data lacks it: a work order for a game build">Make a work order</button>` : ''}
        <button class="ghost" data-remove="${esc(e.id)}">Take off</button></div></div>`).join('');
  return `<div class="pf-row" style="--c:${colorOf(c)}" data-row="${esc(r.id)}" data-sec="${esc(sec.id)}">
    <div class="h"><b>${esc(r.label)}</b><span class="st">${esc(look(c).label)}</span>${r.hint ? `<span style="font-size:11.5px;color:var(--faint)">${esc(r.hint)}</span>` : ''}<span class="sp"></span>
      <button data-songs="1" title="every lyric line with this character near a weapon word">♪ Find it in the songs</button>
      ${row.none ? `<button class="ghost" data-unnone="1">Not none any more</button>` : `<button class="ghost" data-none="1">None, on purpose…</button>`}</div>
    ${row.none ? `<div class="pf-none">None, on purpose — <b>${esc(row.none.reason)}</b> <i>(${esc(row.none.by)}, ${esc(String(row.none.time || '').slice(0, 10))}${(row.none.source || {}).ruling ? ' · ruling ' + esc(row.none.source.ruling) : ''})</i></div>` : ''}
    ${ents || (row.none ? '' : `<div class="pf-none"><i>Open — nobody knows yet.</i></div>`)}
    <div class="pf-add"><input data-addto="${esc(r.id)}" placeholder="add: what it is (your word)"><button data-addbtn="${esc(r.id)}">Add</button></div></div>`;
}
const rank = s => ({owner: 5, songs: 4, proposed: 3, open: 1})[s] || 0;

function ctx(el) { const row = el.closest('[data-row]'); return {game: gid(), p: P.sel, section: row ? row.dataset.sec : '', row: row ? row.dataset.row : '', hash: P.page.hash}; }
async function act(name, body, quiet) { const r = await post(name, body); if (!quiet || !r.ok) toast(r.message, r.ok); if (r.ok) await refresh(); return r; }
async function refresh() {
  const pid = P.sel;
  const [b, pg] = await Promise.all([api(`/api/suite/profiles?id=${encodeURIComponent(gid())}`), api(`/api/suite/profile?id=${encodeURIComponent(gid())}&p=${encodeURIComponent(pid)}`)]);
  if (!b.error) P.board = b;
  if (!pg.error) P.page = pg;
  const scroll = (V().querySelector('.pf-page') || {}).scrollTop || 0;
  paint();
  const pp = V().querySelector('.pf-page'); if (pp) pp.scrollTop = scroll;
}

function valueOf(el) {
  const k = el.dataset.kind;
  if (k === 'list') return el.value.split('\n').map(x => x.trim()).filter(Boolean);
  if (k === 'multi') return [...el.querySelectorAll('input:checked')].map(x => x.value);
  return el.value;
}
async function saveField(el) {
  const body = {game: gid(), p: P.sel, section: el.dataset.sec, field: el.dataset.field, value: valueOf(el), hash: P.page.hash};
  P.dirty.delete(el.id);
  const r = await post('profile_set', body);
  if (!r.ok) { toast(r.message, false); return; }
  if (r.changed !== false) { toast('Saved.', true); await refresh(); }
}
async function flushDirty() {
  const els = [...P.dirty.keys()].map(id => document.getElementById(id)).filter(Boolean);
  for (const el of els) await saveField(el);
}
function keepalive() {          // the window is closing: send what was typed, so nothing is lost
  for (const id of P.dirty.keys()) {
    const el = document.getElementById(id); if (!el || !P.page) continue;
    fetch('/api/suite/act/profile_set', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-Forge': '1'},
      body: JSON.stringify({game: gid(), p: P.sel, section: el.dataset.sec, field: el.dataset.field, value: valueOf(el), hash: P.page.hash})});
  }
  P.dirty.clear();
}
window.addEventListener('pagehide', keepalive);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') keepalive(); });
window.addEventListener('beforeunload', e => { if (P.dirty.size) { keepalive(); } });

function wirePage() {
  const root = $('#pf-page');
  $('#pf-close').onclick = async () => { await flushDirty(); P.sel = null; P.page = null; setAddr(addrOf('characters', 'profiles')); paint(); };
  $('#pf-undo').onclick = () => act('profile_undo', {game: gid(), p: P.sel});
  root.querySelectorAll('[data-field]').forEach(el => {
    if (el.dataset.kind === 'multi') { el.querySelectorAll('input').forEach(c => c.onchange = () => saveField(el)); return; }
    if (el.tagName === 'SELECT') { el.onchange = () => saveField(el); return; }
    el.oninput = () => { P.dirty.set(el.id, true); el.classList.add('dirty'); };
    el.onblur = () => { if (P.dirty.has(el.id)) saveField(el); };
  });
  const entEdit = (attr, key) => root.querySelectorAll(`[${attr}]`).forEach(el => {
    el.oninput = () => el.classList.add('dirty');
    const save = () => { if (!el.classList.contains('dirty')) return; el.classList.remove('dirty'); act('profile_entry_edit', {...ctx(el), eid: el.getAttribute(attr), changes: {[key]: el.value}}, true); };
    el.onblur = save; el.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } };
  });
  entEdit('data-ewhat', 'what'); entEdit('data-eseen', 'seen_in'); entEdit('data-egame', 'game_id');
  root.querySelectorAll('[data-confirm]').forEach(b => b.onclick = () => act('profile_entry_confirm', {...ctx(b), eid: b.dataset.confirm}));
  root.querySelectorAll('[data-remove]').forEach(b => b.onclick = () => act('profile_entry_remove', {...ctx(b), eid: b.dataset.remove}));
  root.querySelectorAll('[data-order]').forEach(b => b.onclick = () => act('profile_order', {...ctx(b), eid: b.dataset.order}));
  root.querySelectorAll('[data-addbtn]').forEach(b => {
    const inp = root.querySelector(`[data-addto="${b.dataset.addbtn}"]`);
    const add = () => { if (!inp.value.trim()) return; act('profile_entry_add', {...ctx(b), entry: {what: inp.value}}); };
    b.onclick = add; inp.onkeydown = e => { if (e.key === 'Enter') add(); };
  });
  root.querySelectorAll('[data-none]').forEach(b => b.onclick = () => {
    const c = ctx(b);
    modal(`<h3>None, on purpose</h3><p>Say why — the reason is what a later session reads (e.g. “a future game's problem”).</p><input id="pf-why" style="width:100%"><div class="row"><button class="ghost" onclick="closeModal()">Cancel</button><button class="go" id="m-ok">Mark it</button></div>`);
    setTimeout(() => $('#pf-why').focus(), 30);
    $('#m-ok').onclick = async () => { const r = await act('profile_none', {...c, reason: $('#pf-why').value}); if (r.ok) closeModal(); };
  });
  root.querySelectorAll('[data-unnone]').forEach(b => b.onclick = () => act('profile_none_clear', ctx(b)));
  root.querySelectorAll('[data-songs]').forEach(b => b.onclick = () => songs(ctx(b)));
  const qa = $('#pf-qadd'); if (qa) { const add = () => { const v = $('#pf-qnew').value; if (v.trim()) act('profile_q_add', {game: gid(), p: P.sel, text: v, hash: P.page.hash}); }; qa.onclick = add; $('#pf-qnew').onkeydown = e => { if (e.key === 'Enter') add(); }; }
  root.querySelectorAll('[data-qmail]').forEach(b => b.onclick = () => act('profile_q_mail', {game: gid(), p: P.sel, qid: b.dataset.qmail}));
  root.querySelectorAll('[data-qclose]').forEach(b => b.onclick = () => act('profile_q_close', {game: gid(), p: P.sel, qid: b.dataset.qclose}));
}

async function songs(c) {
  const rowLabel = ((P.page.schema.sections.find(s => s.id === c.section) || {}).rows || []).find(r => r.id === c.row) || {label: c.row};
  modal(`<h3>Find it in the songs — ${esc(P.page.name)}, ${esc(rowLabel.label.toLowerCase())}</h3><p>Looking…</p>`, true);
  const r = await api(`/api/suite/profilesongs?id=${encodeURIComponent(gid())}&p=${encodeURIComponent(P.sel)}`);
  if (r.error) { modal(`<h3>Find it in the songs</h3><div class="err">${esc(r.error)}</div><div class="row"><button onclick="closeModal()">Close</button></div>`, true); return; }
  const mark = (line, w) => esc(line).replace(new RegExp('\\b(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\w*)', 'i'), '<mark>$1</mark>');
  modal(`<h3>Find it in the songs — ${esc(P.page.name)}, ${esc(rowLabel.label.toLowerCase())}</h3>
    <p style="font-size:12.5px;color:var(--dim)">${r.hits.length}${r.more ? ' (+' + r.more + ' more)' : ''} line(s) from ${r.songs} song(s) with ${esc(r.names.join(' / '))} near a weapon word. The words it looks for are in <code>${esc(P.board.words_file)}</code> — add to it any time. A line is quoted as written, never changed. <b>Use this line</b> puts it on the row as its source (“in the songs”).</p>
    <div class="pf-hits">${r.hits.map((h, i) => `<div class="pf-hit"><div class="s">“${esc(h.song)}” · ${esc(h.singer)} · ${esc(h.why)}</div><div>${mark(h.line, h.word)}</div>${h.context.length > 1 ? `<div class="c">${h.context.map(esc).join(' / ')}</div>` : ''}
      <div style="display:flex;gap:6px;margin-top:5px"><input data-hwhat="${i}" placeholder="what it is (e.g. ${esc(h.word)})" value="${esc(h.word)}" style="flex:1"><button class="go" data-huse="${i}">Use this line</button></div></div>`).join('') || '<div class="pf-hit">Nothing found. Add words to the list, or write it in yourself.</div>'}</div>
    <div class="row"><button onclick="closeModal()">Close</button></div>`, true);
  document.querySelectorAll('[data-huse]').forEach(b => b.onclick = async () => {
    const h = r.hits[+b.dataset.huse], what = document.querySelector(`[data-hwhat="${b.dataset.huse}"]`).value;
    const res = await act('profile_entry_add', {...c, hash: P.page.hash, entry: {what, state: 'songs', seen_in: h.song, source: {kind: 'lyric', text: h.line, song: h.song, singer: h.singer, file: h.file}}});
    if (res.ok) closeModal();
  });
}
})();
