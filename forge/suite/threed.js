// BUILD 36 — the 3D area: Bodies · Skeleton & motions · Props & buildings · Trees · Viewer · Runs, plus the 3D models
// section of Art → Review & approve, Settings → This computer → 3D tools, and where a body stands on a Characters page.
// Loaded after the shell's own script; it uses the shell's helpers (api, post, toast, esc, modal, go, setAddr, gid …).
(function () {
'use strict';
const css = `
#v-threed{max-width:1560px}
.t3-strip{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 14px}
.t3-chip{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:3px 11px;background:var(--panel);color:var(--dim)}
.t3-chip.ok{border-color:#2f6b45;color:#9fe0b8}.t3-chip.no{border-color:#7a3a35;color:#f0b8b0}.t3-chip.warn{border-color:#7a6230;color:#f0d08a}
.t3-chip a{color:inherit}
.t3-lay{display:grid;grid-template-columns:420px minmax(0,1fr);gap:20px;align-items:start}@media(max-width:1150px){.t3-lay{grid-template-columns:1fr}}
.t3-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.t3-card h2{font-size:15px;margin:0 0 10px;font-weight:650}.t3-card h3{font-size:13.5px;margin:12px 0 6px;color:var(--dim);font-weight:600}
.t3-f{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}.t3-f label{font-size:12.5px;color:var(--dim)}
.t3-f input,.t3-f select,.t3-f textarea{font:inherit;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:8px;padding:7px 9px;width:100%}
.t3-f textarea{min-height:90px;resize:vertical}.t3-f textarea.small{min-height:64px;font-size:12.5px;color:#cfccc5}
.t3-row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}.t3-row .t3-f{flex:1;min-width:110px}.t3-f .t3-row{flex-wrap:nowrap;gap:6px}.t3-f .t3-row select{max-width:96px}
.t3-from{font-size:11.5px;color:var(--faint)}.t3-from b{color:var(--dim);font-weight:600}
.t3-warn{font-size:12.5px;color:#f0d08a;margin:2px 0}.t3-warn b{color:#ffcf6a}.t3-bad{font-size:12.5px;color:#f0b8b0}
.t3-chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0}.t3-chips span{font-size:12px;background:#2a2418;border:1px solid #6b5420;color:#f0d08a;border-radius:7px;padding:2px 8px}
.t3-rule{font-size:12.5px;color:#cfccc5;background:#16161c;border-left:3px solid var(--ac,#5fc4e8);padding:8px 10px;border-radius:0 8px 8px 0}
.t3-rule i{color:var(--dim)}
.t3-tries{display:flex;flex-direction:column;gap:4px;max-height:300px;overflow:auto}
.t3-try{display:grid;grid-template-columns:22px 52px minmax(0,1fr) auto;gap:8px;align-items:center;padding:6px 8px;border-radius:9px;cursor:pointer;border:1px solid transparent}
.t3-try:hover{background:rgba(255,255,255,.03)}.t3-try.sel{background:var(--panel2);border-color:var(--line);box-shadow:inset 3px 0 0 #5fc4e8}
.t3-try img{width:52px;height:52px;object-fit:cover;border-radius:6px;background:#22222a}.t3-try .w{font-size:12.5px;color:#cfccc5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t3-try .m{font-size:11.5px;color:var(--faint)}
.t3-steps{display:flex;gap:4px}.t3-steps i{font-style:normal;font-size:11px;border-radius:6px;padding:1px 6px;background:#25252e;color:var(--faint)}
.t3-steps i.done{background:#1f3a2a;color:#9fe0a8}.t3-steps i.running,.t3-steps i.pending{background:#2a2a18;color:#f0d08a}.t3-steps i.failed{background:#3a1f1f;color:#ffb4ad}
.t3-pics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.t3-pic{position:relative;border:2px solid transparent;border-radius:10px;overflow:hidden;cursor:pointer;background:#1a1a20}
.t3-pic img{width:100%;display:block;aspect-ratio:1/1;object-fit:cover}.t3-pic.on{border-color:#5fc4e8}.t3-pic b{position:absolute;left:6px;top:4px;font-size:12px;background:rgba(0,0,0,.6);border-radius:6px;padding:0 6px}
.t3-pic.wait{display:flex;align-items:center;justify-content:center;aspect-ratio:1/1;color:var(--faint);font-size:12.5px;cursor:default}
.t3-view{width:100%;height:470px;border:1px solid var(--line);border-radius:12px;background:#0e0e12;display:block}
.t3-view.small{height:360px}
.t3-acts{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.t3-acts button,.t3-row button{white-space:nowrap}
.t3-state{font-size:12.5px;color:var(--dim)}.t3-state.err{color:#f0b8b0;white-space:pre-wrap}
.t3-sbs{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:1000px){.t3-sbs{grid-template-columns:1fr}}
.t3-diff del{background:#3a1f1f;color:#ffb4ad}.t3-diff ins{background:#1f3a2a;color:#9fe0a8;text-decoration:none}
.t3-never{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:2px 12px;max-height:260px;overflow:auto;font-size:12.5px}
.t3-never label{display:flex;gap:6px;align-items:center;color:#cfccc5}
.t3-speeds{font-size:12.5px;width:100%;border-collapse:collapse}.t3-speeds td{padding:3px 6px;border-bottom:1px solid #24242d}.t3-speeds td:last-child{text-align:right;color:var(--dim)}
.t3-slider{display:grid;grid-template-columns:minmax(0,1fr) 120px 56px;gap:8px;align-items:center;font-size:12.5px;margin:3px 0}
.t3-slider input[type=range]{width:100%}.t3-slider span{color:var(--dim)}.t3-slider b{text-align:right;font-weight:600}
.t3-trees{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
.t3-tree{background:#16161c;border:1px solid var(--line);border-radius:10px;padding:6px;font-size:12px;color:var(--dim);cursor:pointer}
.t3-tree img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:7px;background:#22222a;display:block}
.t3-models{display:flex;flex-direction:column;gap:3px;max-height:calc(100vh - 230px);overflow:auto}
.t3-model{padding:6px 9px;border-radius:8px;cursor:pointer;font-size:12.5px;border:1px solid transparent}.t3-model:hover{background:rgba(255,255,255,.03)}
.t3-model.sel{background:var(--panel2);border-color:var(--line)}.t3-model span{display:block;color:var(--faint);font-size:11.5px}
.t3-log{white-space:pre-wrap;font:12px/1.4 ui-monospace,Consolas,monospace;background:#0f0f13;border:1px solid var(--line);border-radius:8px;padding:8px 10px;max-height:220px;overflow:auto;color:#cfccc5}
.t3-job{border-bottom:1px solid #24242d;padding:8px 0}.t3-job b{font-weight:600}
.t3-faults{font-size:12.5px;color:#cfccc5}.t3-faults li{margin:2px 0}.t3-faults b{color:#f0d08a;font-weight:600}
.t3-items{font-size:13px}.t3-items div{padding:4px 0;border-bottom:1px solid #24242d}.t3-items .fix{color:var(--faint);font-size:12px}
.r3d{margin:0 0 16px}.r3d-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.r3d-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px;font-size:12.5px}
.r3d-card img{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:8px;background:#22222a;cursor:pointer}
.r3d-card .lic{color:var(--faint);font-size:11.5px;margin:4px 0}
.r3d-card .chk{font-size:11.5px;color:#9fe0b8;margin:2px 0}
/* BUILD 39 — the world list */
.wq-st{display:inline-block;font-size:11.5px;font-weight:650;border-radius:7px;padding:1px 8px;white-space:nowrap;letter-spacing:.02em}
.wq-st.wanted{background:#26303d;color:#a9c3e6}.wq-st.making{background:#123844;color:#7fe3ff;box-shadow:0 0 0 1px #2aa9d0 inset}
.wq-st.made{background:#183a26;color:#8ef0b0}.wq-st.approved{background:#1d5a33;color:#c6ffd9}.wq-st.delivered{background:#124a4a;color:#9ff5ef}
.wq-st.held{background:#4a2414;color:#ffb38a;box-shadow:0 0 0 1px #c8642e inset}.wq-st.failed{background:#4a1818;color:#ff9a9a}
.wq-st.on.hold,.wq-st.onhold{background:#33264a;color:#d4b8ff}.wq-st.turned{background:#3a1c26;color:#f0a8bf}
.wq-head{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px}
.wq-run{font-size:13px;border-radius:10px;padding:8px 12px;border:1px solid var(--line);background:var(--panel)}
.wq-run.on{border-color:#2aa9d0;box-shadow:0 0 18px rgba(42,169,208,.18)}.wq-run.wait{border-color:#7a6230}
.wq-run b{color:#7fe3ff}.wq-run.wait b{color:#f0d08a}
.wq-counts{display:flex;flex-wrap:wrap;gap:6px}.wq-counts button{font:inherit;cursor:pointer;border:1px solid transparent;background:none;padding:0}
.wq-counts button.on .wq-st{outline:2px solid #e8e6df;outline-offset:1px}
.wq-lay{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:18px;align-items:start}@media(max-width:1200px){.wq-lay{grid-template-columns:1fr}}
.wq-list{display:flex;flex-direction:column;gap:2px;max-height:calc(100vh - 260px);overflow:auto}
.wq-row{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:8px;align-items:center;padding:6px 8px;border-radius:9px;cursor:pointer;border:1px solid transparent;font-size:13px}
.wq-row:hover{background:rgba(255,255,255,.03)}.wq-row.sel{background:var(--panel2);border-color:var(--line);box-shadow:inset 3px 0 0 #5fc4e8}
.wq-row .n{color:var(--faint);font-size:11.5px;text-align:right}.wq-row .w{color:var(--faint);font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wq-row.next{box-shadow:inset 3px 0 0 #7fe3ff}
.wq-badge{font-size:10.5px;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:0 5px;margin-left:5px}
.wq-chk{font-size:12.5px;margin:3px 0;padding:4px 8px;border-radius:7px}.wq-chk.pass{background:#14261b;color:#a8ecbf}.wq-chk.held{background:#2e1810;color:#ffbe9a}
.wq-pic{width:100%;border-radius:10px;border:1px solid var(--line);display:block;background:#18181e}
.wq-tiers{font-size:12.5px;width:100%;border-collapse:collapse}.wq-tiers td{padding:3px 6px;border-bottom:1px solid #24242d}
.wq-tiers td.m{color:#9fe0b8}.wq-tiers td.g{color:var(--faint)}
`;
const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

const T = { tab: 'bodies', d: null, who: '', tryId: '', tryv: null, pick: null, picks: new Set(), poll: null, kind: 'prop',
            form: null, species: null, numbers: null, model: null, things: '' };
const enc = encodeURIComponent;
const v3 = () => document.getElementById('v-threed');
const STEP_WORD = { pictures: 'pictures', body: 'body', skeleton: 'skeleton', motions: 'motions' };
const STATE_WORD = { pending: 'waiting for the art worker', running: 'being made now', done: 'done', failed: 'failed', paused: 'paused', missing: 'not found in the queue' };

function viewerSrc(url, o = {}) {
  if (!url) return '';
  const qs = new URLSearchParams({ u: url });
  for (const k of ['sheet', 'play', 'label', 'sub', 'light']) if (o[k]) qs.set(k, o[k]);
  return '/suite/viewer?' + qs.toString();
}
function viewer(url, o = {}) { return url ? `<iframe class="t3-view ${o.small ? 'small' : ''}" src="${esc(viewerSrc(url, o))}" title="3D viewer"></iframe>` : ''; }
function stepsBadges(states) {
  return `<span class="t3-steps">${['pictures', 'body', 'skeleton', 'motions'].map(s => `<i class="${esc(states[s] || '')}" title="${esc(STEP_WORD[s])}: ${esc(STATE_WORD[states[s]] || 'not yet')}">${s[0].toUpperCase()}</i>`).join('')}</span>`;
}
function stopPoll() { if (T.poll) { clearTimeout(T.poll); T.poll = null; } }
function pollIfBusy(fn) {
  stopPoll();
  T.poll = setTimeout(() => { const sec = v3(); if (sec && sec.style.display !== 'none') fn(); }, 6000);
}
function wordsDiff(a, b) {
  const A = String(a || '').split(/(\s+)/), B = String(b || '').split(/(\s+)/);
  const n = A.length, m = B.length, L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, out = '';
  while (i < n && j < m) { if (A[i] === B[j]) { out += esc(A[i]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) { out += `<del>${esc(A[i])}</del>`; i++; } else { out += `<ins>${esc(B[j])}</ins>`; j++; } }
  while (i < n) out += `<del>${esc(A[i++])}</del>`; while (j < m) out += `<ins>${esc(B[j++])}</ins>`;
  return out;
}

// ------------------------------------------------------------------ the frame
async function loadThreeD(tab, rest) {
  T.tab = tab || 'bodies'; rest = rest || [];
  stopPoll();
  const v = v3();
  try { T.d = await api('/api/suite/threed?id=' + enc(gid())); } catch (e) { v.innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  const strip = stripHtml();
  if (T.tab === 'bodies') return bodiesTab(rest, strip);
  if (T.tab === 'things') return thingsTab(rest, strip);
  if (T.tab === 'skeleton') return skeletonTab(rest, strip);
  if (T.tab === 'trees') return treesTab(rest, strip);
  if (T.tab === 'viewer') return viewerTab(rest, strip);
  if (T.tab === 'world') return worldTab(rest, strip);
  if (T.tab === 'places') return placesTab(rest, strip);
  if (T.tab === 'terrain') return terrainTab(rest, strip);          // BUILD 77
  if (T.tab === 'runs') return runsTab(rest, strip);
}
window.loadThreeD = loadThreeD;

function stripHtml() {
  const d = T.d, c = d.check || {}, miss = (c.items || []).filter(i => i.ok === false);
  const card = d.card || {};
  const w = d.worker;
  return `<div class="t3-strip">
    <span class="t3-chip ${w === 'rendering' || w === 'idle' ? 'ok' : 'warn'}">art worker: ${esc({ rendering: 'working', idle: 'idle', stopped: 'stopped', 'stopped-mid-job': 'stopped mid-job' }[w] || "can't tell")}</span>
    <span class="t3-chip ${card.held ? 'warn' : 'ok'}" title="Two ComfyUIs never hold the card at once: every 3D step takes this lock first.">graphics card: ${card.held ? 'held by ' + esc(card.holder) : 'free'}</span>
    <span class="t3-chip ${miss.length ? 'no' : 'ok'}">${miss.length ? `<a href="#settings/computer">3D tools: ${miss.length} missing — see Settings</a>` : '3D tools: all there'}</span>
    <span class="t3-chip"><a href="#" onclick="t3Faults();return false">what the 3D line still gets wrong</a></span>
  </div>`;
}
window.t3Faults = function () {
  const f = (T.d && T.d.rules && T.d.rules.faults) || [];
  modal(`<h3>What the 3D line still gets wrong</h3><p>Seen on the first 92 bodies (2026-11-14). The workshop shows these plainly; it does not hide them.</p>
    <ul class="t3-faults">${f.map(x => `<li><b>${esc(x[0])}</b> — ${esc(x[1])}</li>`).join('')}</ul>
    <div class="row"><button class="go" onclick="closeModal()">OK</button></div>`, true);
};

// ------------------------------------------------------------------ the form (bodies and things)
function formHtml(kind, f) {
  const d = T.d, w = (d.words || {})[kind === 'body' ? 'body' : kind] || {};
  const al = f.always != null ? f.always : (w.always || {}).text || '', ng = f.negative != null ? f.negative : (w.negative || {}).text || '';
  const people = d.people || [];
  const isBody = kind === 'body';
  const sizeKey = Object.keys(f.real_size_m || {})[0] || (kind === 'building' ? 'width' : 'height');
  return `<div class="t3-card"><h2>${isBody ? 'A character in words' : 'A thing in words'}</h2>
    ${isBody ? '' : `<div class="t3-f"><label>Kind</label><select id="t3-kind"><option value="prop" ${kind === 'prop' ? 'selected' : ''}>a prop (TRELLIS.2)</option><option value="building" ${kind === 'building' ? 'selected' : ''}>a building (Pixal3D)</option></select></div>`}
    <div class="t3-f"><label for="t3-who">${isBody ? 'Who' : 'What (its name)'}</label>
      <input id="t3-who" list="t3-people" value="${esc(f.who_name || f.who || '')}" placeholder="${isBody ? 'a character in the registry, or a new name' : 'e.g. handcart'}">
      <datalist id="t3-people">${people.map(p => `<option value="${esc(p.name)}">${esc(p.registry ? 'in the registry' : 'tried before')} · ${esc(p.stage || '')}</option>`).join('')}</datalist></div>
    <div class="t3-f"><label for="t3-look">The look, in words — this is what the picture is painted from</label>
      <textarea id="t3-look" placeholder="${isBody ? 'Hyperrealistic. A woman of thirty, …' : 'Hyperrealistic. A single wooden handcart …'}">${esc(f.look || '')}</textarea>
      <div id="t3-chips"></div></div>
    <details ${f.openWords ? 'open' : ''}><summary class="t3-from">The standing words that follow every description — <b>${esc((w.always || {}).from === 'game' ? "this game's" : "the forge's")}</b> (${esc((w.always || {}).block || '')})</summary>
      <div class="t3-f"><textarea class="small" id="t3-always">${esc(al)}</textarea>
        <div class="t3-row"><button class="ghost" onclick="t3SaveBlock('${esc((w.always || {}).block || '')}','t3-always')">Save as this game's words</button></div></div>
      <div class="t3-f"><label>Never in the picture (the negative) — ${esc((w.negative || {}).from === 'game' ? "this game's" : "the forge's")}</label><textarea class="small" id="t3-neg">${esc(ng)}</textarea>
        <div class="t3-row"><button class="ghost" onclick="t3SaveBlock('${esc((w.negative || {}).block || '')}','t3-neg')">Save as this game's words</button></div></div>
    </details>
    <div class="t3-row" style="margin-top:8px">
      <div class="t3-f"><label>Seed</label><input id="t3-seed" type="number" value="${esc(f.seed || 1001)}"></div>
      ${isBody ? `<div class="t3-f"><label>Height in metres</label><input id="t3-h" type="number" step="0.01" value="${esc(f.height_m || 1.72)}"></div>`
               : `<div class="t3-f" style="flex:2"><label>Real size in metres</label><div class="t3-row"><select id="t3-sizek">${['height', 'width', 'depth'].map(k => `<option ${k === sizeKey ? 'selected' : ''}>${k}</option>`).join('')}</select><input id="t3-sizev" type="number" step="0.05" value="${esc((f.real_size_m || {})[sizeKey] || '')}" placeholder="e.g. 1.6"></div></div>`}
      <div class="t3-f" style="flex:0"><label>&nbsp;</label><button class="ghost" title="another seed" onclick="document.getElementById('t3-seed').value=Math.floor(Math.random()*90000)+1000">🎲</button></div>
    </div>
    <div id="t3-hwarn" class="t3-warn"></div>
    ${f.parent ? `<div class="t3-from">Changed from try <b>${esc(f.parent)}</b> — what you change is shown against it once the pictures are made.</div>` : ''}
    <div class="t3-acts"><button class="go" onclick="t3Make('${esc(kind)}')">Make 4 pictures</button>${f.parent ? `<button class="ghost" onclick="t3ClearForm()">Start fresh</button>` : ''}</div>
    ${isBody ? `<div class="t3-rule"><b>The A-pose rule.</b> ${esc(d.rules.apose)}<br><i>${esc(d.rules.example)}</i></div>` : `<div class="t3-rule">Props get their loose scraps taken off and are set to the real size you give, standing on the floor. Buildings go through Pixal3D.</div>`}
  </div>`;
}
function readForm(kind) {
  const g = id => document.getElementById(id);
  const f = { kind: kind, who: g('t3-who').value.trim(), look: g('t3-look').value.trim(), always: g('t3-always').value,
              negative: g('t3-neg').value, seed: parseInt(g('t3-seed').value || '1001', 10), parent: (T.form || {}).parent || null };
  if (g('t3-kind')) f.kind = g('t3-kind').value;
  if (kind === 'body') f.height_m = parseFloat(g('t3-h').value || '1.72');
  else { const k = g('t3-sizek').value, val = parseFloat(g('t3-sizev').value); f.real_size_m = isNaN(val) ? {} : { [k]: val }; }
  const p = (T.d.people || []).find(x => x.name === f.who); if (p) f.who_id = p.id;
  return f;
}
let chipT;
function wireForm(kind) {
  const look = document.getElementById('t3-look'), h = document.getElementById('t3-h');
  const live = () => {
    clearTimeout(chipT); chipT = setTimeout(async () => {
      const k = document.getElementById('t3-kind') ? document.getElementById('t3-kind').value : kind;
      const text = look.value + ' ' + (document.getElementById('t3-always') || {}).value;
      let r; try { r = await api(`/api/suite/threed/chips?kind=${enc(k === 'body' ? 'body' : 'thing')}&text=${enc(text)}`); } catch (e) { return; }
      const lookChips = (await api(`/api/suite/threed/chips?kind=thing&text=${enc(look.value)}`)).chips;
      const el = document.getElementById('t3-chips'); if (!el) return;
      el.innerHTML = (lookChips.length ? `<div class="t3-chips">${lookChips.map(c => `<span title="${esc(c.what)}">⚠ ${esc(c.word)}: ${esc(c.what)}</span>`).join('')}</div>` : '') +
        ((r.pose || []).length ? `<div class="t3-warn"><b>A-pose:</b> ${esc(r.pose.join('; '))} — a warning, not a refusal; you decide.</div>` : '') +
        ((r.standing || []).length ? `<div class="t3-warn"><b>From the last run:</b> ${esc(r.standing.join('; '))}.</div>` : '');
    }, 350);
  };
  look.addEventListener('input', live); live();
  if (h) { const hw = () => { const x = parseFloat(h.value); document.getElementById('t3-hwarn').textContent = isNaN(x) ? 'a height in metres is needed' : x > 3 ? `${x} m is taller than any person — is it centimetres? (1.75, not 175)` : x < 0.4 ? `${x} m is very small for a person` : ''; }; h.addEventListener('input', hw); hw(); }
  const k = document.getElementById('t3-kind'); if (k) k.onchange = () => { T.kind = k.value; T.form = readForm(T.kind); T.form.always = null; T.form.negative = null; thingsTab([], stripHtml()); };
}
window.t3SaveBlock = async function (block, fieldId) {
  if (!G.identity) return askWho();
  const text = document.getElementById(fieldId).value;
  confirmAct('Save these words for this game?', `They become ${block} in this game's prompt library — every 3D picture of this kind starts from them from now on (the old words are kept in the library's history).`, 'Save', async () => {
    const r = await post('threed_block', { game: gid(), block: block, text: text }); toast(r.message, r.ok); if (r.ok) T.d = null;
  });
};
window.t3Make = async function (kind) {
  if (!G.identity) return askWho();
  const f = readForm(kind);
  if (!f.who) return toast('Say who (or what) this is first.', false);
  if (!f.look) return toast('Describe the look in words first.', false);
  const r = await post('threed_pictures', Object.assign({ game: gid() }, f));
  toast(r.message, r.ok);
  if (r.ok) { T.form = Object.assign({}, f, { who_name: f.who, parent: r.try }); T.d = null; const sid = (f.who_id || f.who).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''); go(`3d/${T.tab}/${sid}/${r.try}`); }
};
window.t3ClearForm = function () { T.form = null; loadThreeD(T.tab, A.rest); };

// ------------------------------------------------------------------ Bodies
async function bodiesTab(rest, strip) {
  const v = v3();
  const who = rest[0] || T.who || '', tid = rest[1] || '';
  T.who = who;
  const f = T.form && T.form.kind === 'body' ? T.form : { kind: 'body', who_name: ((T.d.people || []).find(p => p.id === who) || {}).name || who,
                                                          height_m: ((T.d.people || []).find(p => p.id === who) || {}).height_m || 1.72 };
  const list = (T.d.tries || []).filter(t => t.kind === 'body' && (!who || t.who === who));
  v.innerHTML = strip + `<div class="t3-lay"><div>${formHtml('body', f)}</div><div id="t3-right"></div></div>`;
  wireForm('body');
  const right = document.getElementById('t3-right');
  if (rest[2] === 'vs' && rest[3]) return sideBySide(right, rest[1], rest[3]);
  right.innerHTML = triesCard(list, who, 'bodies') + `<div id="t3-try"></div>`;
  wireTries('bodies');
  const show = tid || (list[0] || {}).id;
  if (show) await showTry(show, 'bodies');
  else document.getElementById('t3-try').innerHTML = `<div class="t3-card"><div class="empty">${who ? 'No tries for this one yet.' : 'No tries yet.'} Describe someone on the left and make four pictures.</div></div>`;
}
function triesCard(list, who, tab) {
  return `<div class="t3-card"><h2>Tries${who ? ' — ' + esc(((T.d.people || []).find(p => p.id === who) || {}).name || who) : ''} <span class="t3-from">(tick two to see them side by side)</span></h2>
    <div class="t3-tries">${list.length ? list.map(t => `<div class="t3-try ${t.id === T.tryId ? 'sel' : ''}" data-t="${esc(t.id)}" data-w="${esc(t.who)}">
      <input type="checkbox" class="t3-tick" data-t="${esc(t.id)}" ${T.picks.has(t.id) ? 'checked' : ''} onclick="event.stopPropagation()">
      ${(t.urls && t.urls.pictures && t.urls.pictures[0]) ? `<img loading="lazy" src="${esc(t.urls.pictures[0])}&w=120">` : '<img alt="">'}
      <div style="min-width:0"><div class="w">${esc(t.who_name || t.who)} — ${esc(t.look || '')}</div><div class="m">${esc(String(t.created || '').replace('T', ' ').slice(5, 16))} · seed ${esc(t.seed)} · by ${esc(t.by || '?')}${t.parent ? ' · changed from ' + esc(t.parent) : ''}${t.review ? ' · ' + esc(t.review.state) : ''}</div></div>
      ${stepsBadges(t.states || {})}</div>`).join('') : '<div class="empty">None yet.</div>'}</div>
    <div class="t3-acts"><button class="ghost" id="t3-sbs" disabled>Side by side</button></div></div>`;
}
function wireTries(tab) {
  document.querySelectorAll('.t3-try').forEach(el => el.onclick = () => go(`3d/${tab}/${el.dataset.w}/${el.dataset.t}`));
  const btn = document.getElementById('t3-sbs');
  const upd = () => { btn.disabled = T.picks.size !== 2; };
  document.querySelectorAll('.t3-tick').forEach(c => c.onchange = () => { c.checked ? T.picks.add(c.dataset.t) : T.picks.delete(c.dataset.t); if (T.picks.size > 2) { const first = [...T.picks][0]; T.picks.delete(first); document.querySelector(`.t3-tick[data-t="${first}"]`).checked = false; } upd(); });
  upd();
  btn.onclick = () => { const [a, b] = [...T.picks]; go(`3d/${tab}/${T.who || '_'}/${a}/vs/${b}`); };
}
async function showTry(tid, tab) {
  T.tryId = tid;
  document.querySelectorAll('.t3-try').forEach(el => el.classList.toggle('sel', el.dataset.t === tid));
  let t; try { t = await api(`/api/suite/threed/try?id=${enc(gid())}&t=${enc(tid)}`); } catch (e) { document.getElementById('t3-try').innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  T.tryv = t;
  const row = document.querySelector(`.t3-try[data-t="${tid}"]`);
  if (row) { const im = row.querySelector('img'), p0 = ((t.urls || {}).pictures || [])[0]; if (im && p0 && !im.getAttribute('src')) im.src = p0 + '&w=120';
             const sb = row.querySelector('.t3-steps'); if (sb) sb.outerHTML = stepsBadges(Object.fromEntries(['pictures', 'body', 'skeleton', 'motions'].map(s => [s, ((t.steps || {})[s] || {}).state]))); }
  const box = document.getElementById('t3-try'); if (!box) return;
  box.innerHTML = tryHtml(t, tab);
  wireTry(t, tab);
  const busy = Object.values(t.steps || {}).some(s => s && (s.state === 'pending' || s.state === 'running'));
  if (busy) pollIfBusy(() => { if (T.tryId === tid) showTry(tid, tab); });
}
function stepLine(s, what) {
  if (!s || !s.job) return '';
  return `<div class="t3-state ${s.state === 'failed' ? 'err' : ''}">${esc(what)}: ${esc(STATE_WORD[s.state] || s.state)}${s.state === 'failed' && s.error ? ' — ' + esc(s.error) : ''}</div>`;
}
function tryHtml(t, tab) {
  const S = t.steps || {}, P = S.pictures || {}, B = S.body || {}, U = t.urls || {};
  const pics = U.pictures || [];
  const picked = (S.picked || {}).index;
  const sel = T.pick != null && T.pick < pics.length ? T.pick : picked;
  const isBody = t.kind === 'body';
  let h = `<div class="t3-card"><h2>${esc(t.who_name || t.who)} <span class="t3-from">try ${esc(t.id)} · ${esc(t.kind)}${isBody ? ' · ' + esc(t.height_m) + ' m' : t.real_size_m && Object.keys(t.real_size_m).length ? ' · ' + Object.entries(t.real_size_m).map(([k, v]) => `${k} ${v} m`).join(', ') : ''}</span></h2>
    <div class="t3-from" style="margin-bottom:8px">${esc(t.look)}</div>
    ${(t.chips || []).length ? `<div class="t3-chips">${t.chips.map(c => `<span title="${esc(c.what)}">⚠ ${esc(c.word)}: ${esc(c.what)}</span>`).join('')}</div>` : ''}
    ${(t.pose || []).length ? `<div class="t3-warn"><b>A-pose:</b> ${esc(t.pose.join('; '))}</div>` : ''}
    ${(t.standing || []).length ? `<div class="t3-warn"><b>From the last run:</b> ${esc(t.standing.join('; '))}</div>` : ''}
    ${t.height_warning ? `<div class="t3-warn">${esc(t.height_warning)}</div>` : ''}
    <h3>1 · Pictures ${P.state && P.state !== 'done' ? '— ' + esc(STATE_WORD[P.state] || P.state) : ''}</h3>
    <div class="t3-pics">${pics.length ? pics.map((u, i) => { const g = (P.gate || [])[i]; return `<div class="t3-pic ${i === sel ? 'on' : ''}" data-i="${i}"><img src="${esc(u)}&w=420"><b>${i + 1}${i === picked ? ' · picked' : ''}${g && !g.ok ? ` <span title="${esc(g.lines.join(' · '))}" style="color:#ffb27a">⚠ gate</span>` : ''}</b></div>`; }).join('')
      : Array.from({ length: t.count || 4 }, () => `<div class="t3-pic wait">${esc(P.state === 'failed' ? 'failed' : 'being painted…')}</div>`).join('')}</div>
    ${P.state === 'failed' ? `<div class="t3-state err">${esc(P.error || '')}</div>` : ''}
    <div class="t3-acts">
      <button class="go" id="t3-mkbody" ${pics.length && sel != null ? '' : 'disabled'}>${isBody ? 'Make the body' : 'Make the model'} from picture ${sel != null ? sel + 1 : '…'}</button>
      <button class="ghost" id="t3-again">Try again with changes</button>
    </div>`;
  h += `<h3>2 · ${isBody ? 'The 3D body' : 'The 3D model'}</h3>` + (B.job ? stepLine(B, isBody ? 'the body' : 'the model') : `<div class="t3-state">Pick a picture, then make the ${isBody ? 'body' : 'model'}.</div>`);
  if (B.state === 'done' && U['body.model']) {
    const info = B.info || {}, sz = info.size_m || {};
    h += viewer(U['body.model'], { label: t.who_name || t.who, sub: isBody ? 'the body as it came out (not yet in metres)' : (B.tidy ? `tidied: ${B.tidy.pieces_before}→${B.tidy.pieces_after} pieces, set to its real size` : 'as it came out') });
    if (!isBody && B.tidy) h += `<div class="t3-from">${esc(sz.height)} m tall, ${esc(sz.width)} × ${esc(sz.depth)} m · loose pieces removed: ${esc((B.tidy.pieces_before || 0) - (B.tidy.pieces_after || 0))}</div>`;
    h += `<div class="t3-acts">${isBody ? `<button class="go" onclick="go('3d/skeleton/${esc(t.id)}')">Skeleton &amp; motions →</button>` : `<button class="go" id="t3-review">Send to Review</button>`}</div>`;
  }
  if (t.review) h += `<div class="t3-state">Review: ${esc(t.review.state)}${t.review.decided_by ? ' by ' + esc(t.review.decided_by) : ''}</div>`;
  h += `</div>`;
  return h;
}
function wireTry(t, tab) {
  document.querySelectorAll('.t3-pic[data-i]').forEach(el => el.onclick = () => { T.pick = +el.dataset.i; document.querySelectorAll('.t3-pic[data-i]').forEach(x => x.classList.toggle('on', x === el)); const b = document.getElementById('t3-mkbody'); b.disabled = false; b.textContent = `${t.kind === 'body' ? 'Make the body' : 'Make the model'} from picture ${T.pick + 1}`; });
  const mk = document.getElementById('t3-mkbody');
  if (mk) mk.onclick = async () => {
    if (!G.identity) return askWho();
    const pick = T.pick != null ? T.pick : ((t.steps || {}).picked || {}).index;
    if (pick == null) return toast('Pick a picture first.', false);
    const doIt = async () => { const r = await post('threed_body', { game: gid(), try: t.id, pick: pick }); toast(r.message, r.ok); T.pick = null; if (r.ok) showTry(t.id, tab); };
    const g = (((t.steps || {}).pictures || {}).gate || [])[pick];
    if (g && !g.ok) return confirmAct(`The picture gate has doubts about picture ${pick + 1}`, g.lines.join(' · ') + ' — the body is made from it as it is if you go on (about four minutes on the card).', 'Make it anyway', doIt);
    if ((t.steps || {}).body) confirmAct('Make it again?', 'This try already has a body. A new one from this picture replaces it in the try (the old job stays in the queue folders).', 'Make it again', doIt); else doIt();
  };
  const ag = document.getElementById('t3-again');
  if (ag) ag.onclick = () => { T.form = { kind: t.kind, who: t.who, who_name: t.who_name, look: t.look, always: t.always, negative: t.negative, seed: t.seed, height_m: t.height_m, real_size_m: t.real_size_m, parent: t.id, openWords: false }; T.kind = t.kind; loadThreeD(tab, [t.who]); setTimeout(() => { const el = document.getElementById('t3-look'); if (el) { el.focus(); el.scrollIntoView({ block: 'center' }); } }, 80); toast('The card is filled in from this try — change what you like and make four new pictures.'); };
  const rv = document.getElementById('t3-review');
  if (rv) rv.onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_review', { game: gid(), try: t.id }); toast(r.message, r.ok); if (r.ok) showTry(t.id, tab); };
}
async function sideBySide(right, a, b) {
  let ta, tb;
  try { [ta, tb] = await Promise.all([api(`/api/suite/threed/try?id=${enc(gid())}&t=${enc(a)}`), api(`/api/suite/threed/try?id=${enc(gid())}&t=${enc(b)}`)]); }
  catch (e) { right.innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  const [older, newer] = ta.id < tb.id ? [ta, tb] : [tb, ta];
  const col = t => { const U = t.urls || {}, pk = ((t.steps || {}).picked || {}).index;
    const pic = U['body.picture'] || (pk != null && U.pictures ? U.pictures[pk] : (U.pictures || [])[0]);
    const model = U['motions.moves'] || U['body.model'];
    return `<div class="t3-card"><h2>${esc(t.who_name || t.who)} <span class="t3-from">try ${esc(t.id)} · seed ${esc(t.seed)}</span></h2>
      ${pic ? `<img src="${esc(pic)}&w=600" style="width:100%;border-radius:10px">` : '<div class="empty">no picture yet</div>'}
      ${model ? viewer(model, { small: true, label: t.who_name || t.who, sheet: U['motions.sheet'] }) : '<div class="t3-state">no body yet</div>'}
      <div class="t3-acts"><button class="ghost" onclick="go('3d/bodies/${esc(t.who)}/${esc(t.id)}')">Open this try</button></div></div>`; };
  right.innerHTML = `<div class="t3-card"><h2>Side by side</h2><div class="t3-acts"><button class="ghost" onclick="go('3d/${esc(T.tab)}/${esc(T.who || '')}')">← back to the tries</button></div>
    <h3>What changed in the words (older → newer)</h3><div class="t3-diff" style="font-size:13px">${wordsDiff(older.look, newer.look)}</div>
    ${older.always !== newer.always ? `<h3>The standing words changed too</h3><div class="t3-diff" style="font-size:12px">${wordsDiff(older.always, newer.always)}</div>` : ''}
    ${older.seed !== newer.seed ? `<div class="t3-from">seed ${esc(older.seed)} → ${esc(newer.seed)}</div>` : ''}</div>
    <div class="t3-sbs">${col(older)}${col(newer)}</div>`;
}

// ------------------------------------------------------------------ Props & buildings
async function thingsTab(rest, strip) {
  const v = v3();
  const who = rest[0] || '', tid = rest[1] || '';
  T.who = who;
  const kind = (T.form && T.form.kind !== 'body') ? T.form.kind : T.kind;
  const f = T.form && T.form.kind !== 'body' ? T.form : { kind: kind, who_name: who };
  const list = (T.d.tries || []).filter(t => t.kind !== 'body' && (!who || t.who === who));
  v.innerHTML = strip + `<div class="t3-lay"><div>${formHtml(kind, f)}</div><div id="t3-right"></div></div>`;
  wireForm(kind);
  const right = document.getElementById('t3-right');
  if (rest[2] === 'vs' && rest[3]) return sideBySide(right, rest[1], rest[3]);
  right.innerHTML = triesCard(list, who, 'things') + `<div id="t3-try"></div>`;
  wireTries('things');
  const show = tid || (list[0] || {}).id;
  if (show) await showTry(show, 'things');
  else document.getElementById('t3-try').innerHTML = `<div class="t3-card"><div class="empty">No things tried yet. Describe one on the left.</div></div>`;
}

// ------------------------------------------------------------------ Skeleton & motions
async function skeletonTab(rest, strip) {
  const v = v3();
  const bodies = (T.d.tries || []).filter(t => t.kind === 'body' && (t.states || {}).body === 'done');
  const tid = rest[0] || (bodies[0] || {}).id || '';
  v.innerHTML = strip + `<div class="t3-lay"><div class="t3-card"><h2>Bodies</h2><div class="t3-tries">${bodies.length ? bodies.map(t => `<div class="t3-try ${t.id === tid ? 'sel' : ''}" onclick="go('3d/skeleton/${esc(t.id)}')">
      <span></span>${(t.urls && t.urls['body.picture']) ? `<img loading="lazy" src="${esc(t.urls['body.picture'])}&w=120">` : '<img alt="">'}
      <div style="min-width:0"><div class="w">${esc(t.who_name || t.who)}</div><div class="m">try ${esc(t.id)}</div></div>${stepsBadges(t.states || {})}</div>`).join('')
      : '<div class="empty">No bodies yet — make one in Bodies.</div>'}</div></div><div id="t3-sk"></div></div>`;
  if (tid) await showSkeleton(tid);
}
async function showSkeleton(tid) {
  let t; try { t = await api(`/api/suite/threed/try?id=${enc(gid())}&t=${enc(tid)}`); } catch (e) { document.getElementById('t3-sk').innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  const S = t.steps || {}, K = S.skeleton || {}, M = S.motions || {}, U = t.urls || {};
  const lib = T.d.library || {}, never = new Set((t.person || {}).never || []);
  let h = `<div class="t3-card"><h2>${esc(t.who_name || t.who)} <span class="t3-from">try ${esc(t.id)} · ${esc(t.height_m)} m</span></h2>
    <h3>3 · The skeleton</h3>
    <div class="t3-row"><div class="t3-f" style="max-width:260px"><label>What kind of body</label><select id="t3-rk"><option value="people" ${t.rig_kind !== 'animal' ? 'selected' : ''}>a person — Make-It-Animatable, with finger bones</option><option value="animal" ${t.rig_kind === 'animal' ? 'selected' : ''}>an animal — seams welded, then UniRig</option></select></div>
      <div class="t3-f" style="flex:0"><button class="go" id="t3-addsk">${K.job ? 'Add the skeleton again' : 'Add a skeleton'}</button></div></div>
    ${stepLine(K, 'the skeleton')}
    ${K.state === 'done' && U['skeleton.orientation'] ? `<div class="t3-from">How the rigger saw it: <a href="${esc(U['skeleton.orientation'])}" target="_blank">the orientation picture</a></div>` : ''}
    <h3>4 · The motions</h3>
    <div class="t3-acts"><button class="go" id="t3-fit" ${K.state === 'done' ? '' : 'disabled'}>${M.job ? 'Fit the motions again' : 'Fit motions'}</button>
      ${M.state === 'done' ? `<button class="ghost" id="t3-rev">Send to Review</button>` : ''}</div>
    ${stepLine(M, 'the motions')}`;
  if (M.state === 'done' && U['motions.moves']) {
    h += viewer(U['motions.moves'], { sheet: U['motions.sheet'], play: 'Walk_Loop', label: t.who_name || t.who, sub: `${t.height_m} m · ${(M.motions || []).length} motions` + ((M.left_out || []).length ? ` · never: ${M.left_out.join(', ')}` : '') });
    const sp = M.speeds || {};
    h += `<table class="t3-speeds">${['Walk_Loop', 'Jog_Fwd_Loop', 'Sprint_Loop', 'Walk_Formal_Loop', 'Crouch_Fwd_Loop'].filter(k => sp[k]).map(k => `<tr><td>${esc(k)}</td><td>${sp[k].toFixed(2)} m/s</td></tr>`).join('')}</table>
      <div class="t3-from">The library's walk is a stroll and its run nearly a sprint — these speeds are measured from it and scaled to this body's legs; a game moves the body at them so its feet don't slide.</div>`;
  } else if (U['skeleton.preview']) {
    h += viewer(U['skeleton.preview'], { small: true, label: (t.who_name || t.who) + ' — rigged, at rest' });
  }
  h += `<h3>Motions this character never does</h3>
    ${lib.there ? `<div class="t3-never">${(lib.motions || []).map(m => `<label><input type="checkbox" class="t3-nv" value="${esc(m)}" ${never.has(m) ? 'checked' : ''}> ${esc(m)}</label>`).join('')}</div>
      <div class="t3-acts"><button class="ghost" id="t3-nvsave">Keep this list with ${esc(t.who_name || t.who)}</button><span class="t3-from">Used the next time the motions are fitted.</span></div>`
      : `<div class="t3-bad">The motion library isn't at ${esc(lib.file)} — see Settings → This computer → 3D tools.</div>`}
    <div class="t3-from" style="margin-top:8px">The rigging pack's own Mixamo test dances are never fitted and can never be delivered into a game.</div></div>`;
  document.getElementById('t3-sk').innerHTML = h;
  document.getElementById('t3-addsk').onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_skeleton', { game: gid(), try: t.id, kind: document.getElementById('t3-rk').value }); toast(r.message, r.ok); if (r.ok) showSkeleton(t.id); };
  const fitb = document.getElementById('t3-fit'); if (fitb) fitb.onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_motions', { game: gid(), try: t.id }); toast(r.message, r.ok); if (r.ok) showSkeleton(t.id); };
  const rev = document.getElementById('t3-rev'); if (rev) rev.onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_review', { game: gid(), try: t.id }); toast(r.message, r.ok); };
  const nvs = document.getElementById('t3-nvsave'); if (nvs) nvs.onclick = async () => { if (!G.identity) return askWho(); const list = [...document.querySelectorAll('.t3-nv:checked')].map(x => x.value); const r = await post('threed_never', { game: gid(), who: t.who, never: list, height_m: t.height_m }); toast(r.message, r.ok); };
  const busy = [K, M].some(s => s && (s.state === 'pending' || s.state === 'running'));
  if (busy) pollIfBusy(() => showSkeleton(t.id));
}

// ------------------------------------------------------------------ Trees
async function treesTab(rest, strip) {
  const v = v3();
  const sheets = T.d.species || [];
  if (!T.species || !sheets.find(s => s.name === T.species)) T.species = (sheets[0] || {}).name;
  const sheet = sheets.find(s => s.name === T.species) || { numbers: {} };
  if (!T.numbers || T.numbersFor !== T.species) { T.numbers = Object.assign({}, sheet.numbers); T.numbersFor = T.species; }
  const sl = T.d.sliders || {};
  v.innerHTML = strip + `<div class="t3-lay"><div class="t3-card"><h2>A species, as numbers</h2>
    <div class="t3-f"><label>Start from</label><select id="t3-sp">${sheets.map(s => `<option value="${esc(s.name)}" ${s.name === T.species ? 'selected' : ''}>${esc(s.name)} (${esc(s.where === 'game' ? "this game's" : "the forge's")})</option>`).join('')}</select>
      <div class="t3-from">${esc(sheet.about || '')}</div></div>
    ${Object.entries(sl).map(([k, s]) => `<div class="t3-slider"><span title="${esc(k)}">${esc(s[0])}</span><input type="range" min="${s[1]}" max="${s[2]}" step="${s[3]}" value="${esc(T.numbers[k] ?? s[1])}" data-k="${esc(k)}"><b id="t3-n-${esc(k)}">${esc(T.numbers[k] ?? '')}</b></div>`).join('')}
    <div class="t3-row" style="margin-top:10px"><div class="t3-f"><label>Seed (the next seed is its sibling)</label><input id="t3-tseed" type="number" value="11"></div>
      <div class="t3-f"><label><input type="checkbox" id="t3-bare"> bare (winter, or dead)</label></div></div>
    <div class="t3-acts"><button class="go" id="t3-grow">Grow 4</button><button class="ghost" id="t3-spsave">Save as a species…</button></div>
    <div class="t3-rule">Trees are grown by rule, never guessed from a picture: twigs reach for free room inside the crown, limbs are as thick as what they carry, and the leaves are cards carrying a painted sprig, the way real-time trees are built.</div></div>
    <div><div class="t3-card"><h2>Grown</h2><div id="t3-tj" class="t3-trees"><div class="empty">…</div></div></div><div id="t3-tview"></div></div></div>`;
  document.getElementById('t3-sp').onchange = e => { T.species = e.target.value; T.numbers = null; treesTab([], strip); };
  document.querySelectorAll('.t3-slider input').forEach(r => r.oninput = () => { T.numbers[r.dataset.k] = parseFloat(r.value); document.getElementById('t3-n-' + r.dataset.k).textContent = r.value; });
  document.getElementById('t3-grow').onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_grow', { game: gid(), species: T.species, sheet: { name: T.species, numbers: T.numbers }, seed: parseInt(document.getElementById('t3-tseed').value || '11', 10), bare: document.getElementById('t3-bare').checked, count: 4 }); toast(r.message, r.ok); if (r.ok) loadTreeJobs(); };
  document.getElementById('t3-spsave').onclick = () => { modal(`<h3>Save these numbers as a species</h3><p>It is kept with this game (games/…/threed/species) and appears in "Start from".</p><input id="m-spn" placeholder="a name, e.g. old_oak"><textarea id="m-spa" placeholder="what kind of tree it is (optional)" style="width:100%;min-height:60px;margin-top:6px"></textarea><div class="row"><button class="ghost" onclick="closeModal()">Cancel</button><button class="go" id="m-ok">Save</button></div>`);
    document.getElementById('m-ok').onclick = async () => { const r = await post('threed_species', { game: gid(), sheet: { name: document.getElementById('m-spn').value, about: document.getElementById('m-spa').value, numbers: T.numbers } }); toast(r.message, r.ok); if (r.ok) { closeModal(); T.d = null; T.species = document.getElementById('m-spn') ? document.getElementById('m-spn').value : T.species; loadThreeD('trees', []); } }; };
  loadTreeJobs();
}
async function loadTreeJobs() {
  let d; try { d = await api('/api/suite/threed/trees?id=' + enc(gid())); } catch (e) { return; }
  const el = document.getElementById('t3-tj'); if (!el) return;
  const cells = [];
  for (const j of d.jobs) {
    if (j.state !== 'done') cells.push(`<div class="t3-tree"><div class="t3-pic wait" style="aspect-ratio:1/1">${esc(j.state === 'failed' ? 'failed' : 'growing…')}</div>${esc(j.species)} · seeds ${esc(j.seed)}–${esc((j.seed || 0) + (j.count || 1) - 1)}${j.error ? `<div class="t3-bad">${esc(j.error.slice(0, 160))}</div>` : ''}</div>`);
    else for (const t of j.trees) cells.push(`<div class="t3-tree" data-u="${esc(t.glb)}" data-l="${esc(j.species + ' seed ' + t.seed)}">${t.view ? `<img loading="lazy" src="${esc(t.view)}&w=320">` : '<div class="t3-pic wait">no picture</div>'}${esc(j.species)} · seed ${esc(t.seed)}${j.bare ? ' · bare' : ''}</div>`);
  }
  el.innerHTML = cells.join('') || '<div class="empty">Nothing grown yet.</div>';
  el.querySelectorAll('.t3-tree[data-u]').forEach(c => c.onclick = () => { document.getElementById('t3-tview').innerHTML = `<div class="t3-card">${viewer(c.dataset.u, { label: c.dataset.l })}</div>`; });
  if (d.jobs.some(j => j.state === 'pending' || j.state === 'running')) pollIfBusy(loadTreeJobs);
}

// ------------------------------------------------------------------ Viewer
async function viewerTab(rest, strip) {
  const v = v3();
  let d; try { d = await api('/api/suite/threed/models?id=' + enc(gid())); } catch (e) { v.innerHTML = strip + `<div class="err">${esc(e)}</div>`; return; }
  const ms = d.models;
  const want = rest.length ? decodeURIComponent(rest.join('/')) : (T.model || (ms[0] || {}).file);
  v.innerHTML = strip + `<div class="t3-lay"><div class="t3-card"><h2>Every model the forge has made</h2><input class="fsel" id="t3-mq" placeholder="Find a model" style="width:100%;margin-bottom:8px">
    <div class="t3-models" id="t3-ml">${ms.map(m => `<div class="t3-model ${m.file === want ? 'sel' : ''}" data-f="${esc(m.file)}">${esc(m.name || m.file)}<span>${esc(m.kind)} · ${esc(String(m.when || '').replace('T', ' ').slice(0, 16))}</span></div>`).join('') || '<div class="empty">None yet.</div>'}</div></div>
    <div id="t3-vv"></div></div>`;
  const showM = f => { const m = ms.find(x => x.file === f); if (!m) return; T.model = f; document.querySelectorAll('.t3-model').forEach(x => x.classList.toggle('sel', x.dataset.f === f));
    document.getElementById('t3-vv').innerHTML = `<div class="t3-card">${viewer(m.url, { sheet: m.sheet, label: m.name, sub: m.file })}<div class="t3-from">Turn it with the mouse; the wheel zooms. The grid is in metres; the grey figure is 1.75 m. Day and night light are in the viewer's bar.</div></div>`; };
  document.querySelectorAll('.t3-model').forEach(x => x.onclick = () => showM(x.dataset.f));
  document.getElementById('t3-mq').oninput = e => { const qv = e.target.value.toLowerCase(); document.querySelectorAll('.t3-model').forEach(x => x.style.display = x.textContent.toLowerCase().includes(qv) ? '' : 'none'); };
  if (want) showM(want);
}

// ------------------------------------------------------------------ Runs
async function runsTab(rest, strip) {
  const v = v3();
  let d; try { d = await api('/api/suite/threed/runs?id=' + enc(gid())); } catch (e) { v.innerHTML = strip + `<div class="err">${esc(e)}</div>`; return; }
  const c = d.card || {}, wq = d.world || {}, wl = wq.launcher || {}, we = wq.estimate || {};
  const wqCard = wq.error ? `<div class="t3-card"><h2>The world queue</h2><div class="t3-state err">${esc(wq.error)}</div></div>`
    : `<div class="t3-card"><h2>The world queue <a href="#3d/world" class="t3-from" style="margin-left:6px">the whole list →</a></h2>
      ${wqLauncher(wl, we, '')}
      <div class="wq-counts" style="margin:8px 0">${Object.entries(wq.counts || {}).map(([k, n]) => wqState(k).replace('</span>', ` ${n}</span>`)).join('') || '<span class="t3-from">The list is empty.</span>'}</div>
      <div class="t3-state">${esc(we.to_make || 0)} still to make — <b>${esc(we.words || '')}</b> at ${esc(we.basis || '')}${wq.next ? ` · next: <b>${esc(wq.next)}</b>` : ''}</div>
      ${(wq.held || []).length ? `<h3>Held back</h3>${wq.held.map(h => `<div class="t3-job"><a href="#3d/world/${enc(h.id)}"><b>${esc(h.id)}</b></a> <span class="t3-from">${esc((h.why || [])[0] || '')}</span></div>`).join('')}` : ''}
      <div class="t3-acts">${wl.running ? `<button class="ghost" id="wq-stop2" ${wq.stop_asked ? 'disabled' : ''}>${wq.stop_asked ? 'Stopping after this one…' : 'Stop after this one'}</button>` : `<button class="go" id="wq-start2">Start the world queue</button>`}</div></div>`;
  v.innerHTML = strip + `<div class="t3-lay"><div>
    ${wqCard}
    <div class="t3-card"><h2>The graphics card</h2><div class="t3-state">${c.held ? `Held by <b>${esc(c.holder)}</b> since ${esc(c.since)} (heartbeat ${esc(c.beat_age)} s ago).` : 'Free — no 3D step is using it.'}</div>
      <div class="t3-from">Every 3D step takes this lock before it puts work on the card, so the art ComfyUI and the rigging ComfyUI never hold it at once. A holder that stops answering for fifteen minutes is taken over.</div></div>
    <div class="t3-card"><h2>Run a whole list overnight</h2>${(d.lists || []).length ? d.lists.map(l => `<div class="t3-job"><b>${esc(l.batch)}</b> — ${esc(l.bodies)} bodies, ${esc(l.done)} through already<br>
      <span class="t3-from">to make: ${Object.entries(l.estimate.to_make).map(([k, n]) => `${n} ${k}`).join(', ')} — ${esc(l.estimate.words)}</span>
      <div class="t3-acts"><button class="go" data-f="${esc(l.file)}" data-w="${esc(l.estimate.words)}" data-b="${esc(l.batch)}">Run it</button></div></div>`).join('')
      : `<div class="empty">No lists yet. A list is a file in this game's threed/lists folder — the same format the overnight cast runs read (an id, the words, the height for each body).</div>`}</div>
    <div class="t3-card"><h2>Failed lately</h2>${(d.failed || []).map(j => `<div class="t3-job"><b>${esc(j.type)}</b> ${esc(j.name || '')} <span class="t3-from">${esc(j.id)}</span><div class="t3-state err">${esc(j.error)}</div></div>`).join('') || '<div class="empty">Nothing.</div>'}</div>
  </div><div>
    <div class="t3-card"><h2>Running and waiting</h2>${(d.active || []).map(j => `<div class="t3-job"><b>${esc(j.type)}</b> ${esc(j.name || '')} — ${esc(STATE_WORD[j.state] || j.state)} <span class="t3-from">${esc(j.id)}</span>${j.log ? `<div class="t3-log">${esc(j.log)}</div>` : ''}</div>`).join('') || '<div class="empty">No 3D work in the queue.</div>'}</div>
    <div class="t3-card"><h2>Whole-list runs</h2>${(d.batches || []).map(b => `<details class="t3-job"><summary><b>${esc(b.batch)}</b> <span class="t3-from">${esc(b.when)}</span></summary>${b.report ? `<div class="t3-log">${esc(b.report)}</div>` : ''}${b.log ? `<div class="t3-log">${esc(b.log)}</div>` : ''}</details>`).join('') || '<div class="empty">None yet.</div>'}</div>
    <div class="t3-card"><h2>Earlier runs (read only)</h2>${(d.earlier || []).map(b => `<details class="t3-job"><summary><b>${esc(b.batch)}</b> <span class="t3-from">${esc(b.when)}</span></summary><div class="t3-log">${esc(b.report)}</div></details>`).join('') || '<div class="empty">None.</div>'}</div>
    <div class="t3-card"><h2>Finished lately</h2>${(d.recent || []).map(j => `<div class="t3-job"><b>${esc(j.type)}</b> ${esc(j.name || '')} <span class="t3-from">${esc(String(j.finished || '').replace('T', ' ').slice(5, 16))}</span></div>`).join('') || '<div class="empty">Nothing yet.</div>'}</div>
  </div></div>`;
  v.querySelectorAll('button[data-f]').forEach(b => b.onclick = () => { if (!G.identity) return askWho();
    confirmAct(`Run ${b.dataset.b} overnight?`, `Picture → body → skeleton → motions for every body still to make — ${b.dataset.w}. It goes into the art worker's queue and holds the graphics card while it works; it approves nothing.`, 'Run it', async () => { const r = await post('threed_runlist', { game: gid(), file: b.dataset.f }); toast(r.message, r.ok); runsTab([], strip); }); });
  const ws = document.getElementById('wq-start2');
  if (ws) ws.onclick = () => { if (!G.identity) return askWho();
    confirmAct('Start the world queue?', `It makes what the world list wants, next thing first — ${esc(we.to_make || 0)} things, ${esc(we.words || '')}. It waits whenever the graphics card is someone else's and approves nothing.`, 'Start', async () => {
      const r = await post('threed_world_start', { game: gid() }); toast(r.message, r.ok); setTimeout(() => runsTab([], stripHtml()), 3000); }); };
  const wsp = document.getElementById('wq-stop2');
  if (wsp) wsp.onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_world_stop', { game: gid() }); toast(r.message, r.ok); runsTab([], strip); };
  if ((d.active || []).length || wl.running) pollIfBusy(() => runsTab([], stripHtml()));
}

// ------------------------------------------------------------------ World list (BUILD 39)
const WQ_WORD = { wanted: 'wanted', making: 'being made', made: 'made · in Review', approved: 'approved', delivered: 'delivered',
  held: 'held back', failed: 'failed', 'on hold': 'on hold', 'turned down': 'turned down' };
function wqState(st) { return `<span class="wq-st ${esc(String(st).replace(' ', ''))} ${esc(st)}">${esc(WQ_WORD[st] || st)}</span>`; }
function wqLauncher(L, est, machine) {
  if (L.running) return `<div class="wq-run ${L.waiting ? 'wait' : 'on'}">${L.waiting ? `Waiting before <b>${esc(L.item || '')}</b>: ${esc(L.waiting)}`
    : (L.item ? `Making <b>${esc(L.item)}</b> — ${esc(L.step || '')} <span class="t3-from">since ${esc(String(L.since || '').slice(11, 16))}</span>` : `Running — ${esc(L.step || '')}`)}</div>`;
  return `<div class="wq-run">The world queue is not running${L.stopped ? ` <span class="t3-from">(stopped ${esc(String(L.stopped).replace('T', ' ').slice(5, 16))})</span>` : ''}.
    ${machine ? `<span class="t3-from">If started now it would wait: ${esc(machine)}.</span>` : ''}</div>`;
}
async function worldTab(rest, strip) {
  const v = v3();
  let d; try { d = await api('/api/suite/threed/world?id=' + enc(gid())); } catch (e) { v.innerHTML = strip + `<div class="err">${esc(e)}</div>`; return; }
  T.wq = d; T.wqSel = rest[0] ? decodeURIComponent(rest[0]) : (T.wqSel || '');
  const L = d.launcher || {}, est = d.estimate || {};
  const order = ['wanted', 'making', 'made', 'approved', 'delivered', 'held', 'failed', 'on hold', 'turned down'];
  const counts = Object.entries(d.counts || {}).sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  v.innerHTML = strip + `<div class="wq-head">${wqLauncher(L, est, d.machine)}
      ${L.running ? `<button class="ghost" id="wq-stop" ${d.stop_asked ? 'disabled' : ''}>${d.stop_asked ? 'Stopping after this one…' : 'Stop after this one'}</button>`
        : `<button class="go" id="wq-start" ${d.launcher_bat ? '' : 'disabled'}>Start the world queue</button>`}
      <span class="t3-chip">${esc(est.to_make || 0)} to make — <b>${esc(est.words || '')}</b> at ${esc(est.basis || '')}</span></div>
    <div class="wq-counts" style="margin:0 0 12px"><button data-f="" class="${T.wqF ? '' : 'on'}"><span class="wq-st wanted">all ${esc((d.items || []).length)}</span></button>
      ${counts.map(([k, n]) => `<button data-f="${esc(k)}" class="${T.wqF === k ? 'on' : ''}">${wqState(k).replace('</span>', ` ${n}</span>`)}</button>`).join('')}
      <input id="wq-q" placeholder="find…" style="margin-left:8px;font:inherit;background:#121217;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:3px 9px;width:160px"></div>
    <div id="wq-approve"></div>
    ${wqRelease(d.release || {})}
    ${(d.problems || []).length ? `<div class="t3-card" style="border-color:#7a6230"><h2>Problems in the list</h2>${d.problems.map(p => `<div class="t3-warn">${esc(p)}</div>`).join('')}</div>` : ''}
    <div class="wq-lay"><div class="t3-card"><h2>What the world needs — in the order it first appears</h2>
      <div class="wq-list" id="wq-list">${(d.items || []).length ? '' : `<div class="empty">The list is empty. Add a thing below, or drop a file into ${esc(d.list_dir)}.</div>`}</div></div>
    <div><div id="wq-detail"></div>
      <details class="t3-card"><summary><b>Add to the list</b></summary>
        <div class="t3-row"><div class="t3-f"><label>id (one word)</label><input id="wq-id" placeholder="jersey_barrier"></div>
          <div class="t3-f"><label>kind</label><select id="wq-kind">${(d.kinds || []).map(k => `<option>${esc(k)}</option>`).join('')}</select></div>
          <div class="t3-f"><label>size tier</label><select id="wq-tier"><option value="">(the kind's usual)</option>${(d.tier_names || []).map(k => `<option>${esc(k)}</option>`).join('')}</select></div></div>
        <div class="t3-f"><label>what it looks like (the picture is painted from these words)</label><textarea id="wq-words" class="small"></textarea></div>
        <div class="t3-row"><div class="t3-f"><label>real size</label><div class="t3-row"><select id="wq-dim"><option>height</option><option>width</option><option>depth</option></select><input id="wq-m" placeholder="metres"></div></div>
          <div class="t3-f"><label>first appears (where)</label><input id="wq-where" placeholder="the first mission, the approach"></div>
          <div class="t3-f"><label>order (lower is made first)</label><input id="wq-order" placeholder="1.02"></div></div>
        <div class="t3-acts"><button class="go" id="wq-add">Add it</button></div></details>
      <details class="t3-card"><summary><b>Size tiers</b> <span class="t3-from">faces and texture by tier</span></summary>
        <table class="wq-tiers">${Object.entries(d.tiers || {}).map(([k, t]) => `<tr><td><b>${esc(k)}</b></td><td>${esc(t.faces)} faces</td><td>${esc(t.texture)} px</td><td class="${t.measured ? 'm' : 'g'}">${t.measured ? 'measured' : 'first setting'}</td><td class="t3-from">${esc(t.for)}</td></tr>`).join('')}</table></details>
      ${d.log ? `<details class="t3-card"><summary><b>The queue's log</b> <span class="t3-from">newest lines</span></summary><div class="t3-log">${esc(d.log)}</div></details>` : ''}
    </div></div>`;
  const paintList = () => {
    const qv = (document.getElementById('wq-q').value || '').toLowerCase();
    const rows = (d.items || []).filter(i => (!T.wqF || i.shown === T.wqF) && (!qv || (i.id + ' ' + i.words + ' ' + ((i.first || {}).where || '')).toLowerCase().includes(qv)));
    document.getElementById('wq-list').innerHTML = rows.map((i, n) => `<div class="wq-row ${i.id === T.wqSel ? 'sel' : ''} ${i.next ? 'next' : ''}" data-i="${esc(i.id)}">
      <span class="n">${esc((i.first || {}).order ?? '–')}</span>
      <div><b>${esc(i.id)}</b><span class="wq-badge">${esc(i.kind)}</span><span class="wq-badge">${esc(i.tier)}</span>${i.adopted ? '<span class="wq-badge">made earlier</span>' : ''}${i.changed ? '<span class="wq-badge" style="color:#f0d08a">changed since made</span>' : ''}${i.next ? '<span class="wq-badge" style="color:#7fe3ff">next</span>' : ''}
        <div class="w">${esc(i.why && i.why.length ? i.why[0] : (i.error || (i.first || {}).where || i.words || ''))}</div></div>
      ${wqState(i.shown)}</div>`).join('') || '<div class="empty">Nothing here.</div>';
    document.querySelectorAll('.wq-row').forEach(r => r.onclick = () => { T.wqSel = r.dataset.i; if (typeof setAddr === 'function') setAddr('3d/world/' + enc(T.wqSel)); paintList(); wqDetail(); });
  };
  paintList();
  wqDetail();
  document.getElementById('wq-q').oninput = paintList;
  v.querySelectorAll('.wq-counts button[data-f]').forEach(b => b.onclick = () => { T.wqF = b.dataset.f; worldTab([], strip); });
  const st = document.getElementById('wq-start');
  if (st) st.onclick = () => { if (!G.identity) return askWho();
    confirmAct('Start the world queue?', `It makes what the list wants, the thing that first appears first — ${esc(est.to_make || 0)} things, ${esc(est.words || '')} at ${esc(est.basis || '')}. It waits whenever the graphics card is someone else's, checks every model, and approves nothing.`, 'Start', async () => {
      const r = await post('threed_world_start', { game: gid() }); toast(r.message, r.ok); setTimeout(() => worldTab([], stripHtml()), 3000); }); };
  const sp = document.getElementById('wq-stop');
  if (sp) sp.onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_world_stop', { game: gid() }); toast(r.message, r.ok); worldTab([], strip); };
  document.getElementById('wq-add').onclick = async () => { if (!G.identity) return askWho();
    const val = id => document.getElementById(id).value.trim();
    const entry = { id: val('wq-id'), kind: val('wq-kind'), words: val('wq-words'), first: { where: val('wq-where') } };
    if (val('wq-tier')) entry.tier = val('wq-tier');
    if (val('wq-m')) entry.real_size_m = { [val('wq-dim')]: parseFloat(val('wq-m')) };
    if (val('wq-order')) entry.first.order = parseFloat(val('wq-order'));
    const r = await post('threed_world_add', { game: gid(), entry }); toast(r.message, r.ok); if (r.ok) { T.wqSel = r.id; worldTab([], strip); } };
  wqReleaseWire(d.release || {}, strip);
  if (window.approveCard) window.approveCard('world', document.getElementById('wq-approve'), () => worldTab([], stripHtml()));   // BUILD 78
  if (L.running) pollIfBusy(() => worldTab([], stripHtml()));
}
/* BUILD 73 — one button for what is left: Match and release, Straighten and release, and which way is up */
function wqRelease(R) {
  const m = R.match || [], s = R.straighten || [], u = R.unclear_up || [];
  if (!m.length && !s.length && !u.length) return '';
  const pic = (url, t) => url ? `<a href="${esc(url)}" target="_blank"><img src="${esc(url)}&w=520" title="${esc(t)}" style="max-width:100%;border-radius:6px"></a>` : `<div class="t3-from">${esc(t)}: no picture</div>`;
  return `<details class="t3-card" open style="border-color:#3f6a52"><summary><b>What is left — one button each</b> <span class="t3-from">nothing here is remade; every release is written down with who pressed it</span></summary>
    ${m.length ? `<h3>Match and release <span class="t3-from">${m.length} held for their colours alone — as made · matched · the picture; untick any you don't want</span></h3>
      ${m.map(r => `<div class="wq-rel" style="display:grid;grid-template-columns:22px 1fr;gap:8px;margin:6px 0"><input type="checkbox" class="wq-m" data-i="${esc(r.id)}" ${r.release === 'as made' ? '' : 'checked'}>
        <div><b>${esc(r.id)}</b> <span class="wq-badge">${esc(r.kind)}</span>${r.release === 'as made' ? ' <span class="wq-badge" style="border-color:#7a6230;color:#ffd58a" title="the match is worse than the thing as made — Approve everything here releases it as made; so does Release as made on its own card">as made</span>' : ''}<span class="t3-from"> ${esc((r.why || [])[0] || '')}</span>
        <div style="display:flex;gap:6px;flex-wrap:wrap">${pic(r.urls.colour, 'as made · matched · the picture')}${r.urls.head ? pic(r.urls.head, 'the head: as made · matched · the picture') : ''}</div></div></div>`).join('')}
      <div class="t3-acts"><button class="go" id="wq-mrel">Match and release the ticked</button></div>` : ''}
    ${s.length ? `<h3>Straighten and release <span class="t3-from">${s.length} that lean as a whole ("If the buildings can be straightened, no need to waste them")</span></h3>
      ${s.map(r => `<div style="margin:4px 0"><label><input type="checkbox" class="wq-s" data-i="${esc(r.id)}" checked> <b>${esc(r.id)}</b> — leans ${esc(r.tilt_deg)}°${(r.others || []).length ? ` <span class="t3-from">(also held for: ${esc(r.others.join(', '))} — it stays held for those)</span>` : ''}</label></div>`).join('')}
      <div class="t3-acts"><button class="go" id="wq-srel">Straighten and release the ticked</button></div>` : ''}
    ${u.length ? `<h3>Which way is up? <span class="t3-from">its resting plane and its own walls disagree — click the one standing up</span></h3>
      ${u.map(r => `<div style="margin:6px 0"><b>${esc(r.id)}</b> <button class="ghost wq-up" data-i="${esc(r.id)}">Show the three</button><div class="wq-upbox" id="wq-up-${esc(r.id)}"></div></div>`).join('')}` : ''}
  </details>`;
}
function wqReleaseWire(R, strip) {
  const mb = document.getElementById('wq-mrel');
  if (mb) mb.onclick = () => { if (!G.identity) return askWho();
    const ids = [...document.querySelectorAll('.wq-m:checked')].map(x => x.dataset.i);
    if (!ids.length) return toast('Nothing is ticked.', false);
    confirmAct(`Match and release ${ids.length}?`, 'Each takes its colours matched to its picture. Props and buildings go to Review & approve; bodies go back to the queue for their skeleton and motions only (no new picture, no new body). Nothing is approved.', 'Release', async () => {
      const r = await post('threed_world_match_release', { game: gid(), ids }); toast(r.message, r.ok); worldTab([], stripHtml()); }); };
  const sb = document.getElementById('wq-srel');
  if (sb) sb.onclick = async () => { if (!G.identity) return askWho();
    const ids = [...document.querySelectorAll('.wq-s:checked')].map(x => x.dataset.i);
    if (!ids.length) return toast('Nothing is ticked.', false);
    const r = await post('threed_world_straighten_release', { game: gid(), ids }); toast(r.message, r.ok); worldTab([], stripHtml()); };
  document.querySelectorAll('.wq-up').forEach(b => b.onclick = async () => {
    const box = document.getElementById('wq-up-' + b.dataset.i); box.innerHTML = '<div class="t3-from">drawing…</div>';
    const r = await post('threed_world_up_choices', { game: gid(), id: b.dataset.i });
    if (!r.ok) { box.innerHTML = `<div class="err">${esc(r.message)}</div>`; return; }
    box.innerHTML = `<div style="display:flex;gap:8px">${r.choices.map(c => `<figure style="margin:0;cursor:pointer" class="wq-upc" data-c="${esc(c.choice)}"><img src="${esc(c.url)}" style="width:160px;border-radius:6px;border:2px solid transparent"><figcaption class="t3-from">${esc(c.name)}</figcaption></figure>`).join('')}</div>`;
    box.querySelectorAll('.wq-upc').forEach(f => f.onclick = async () => { if (!G.identity) return askWho();
      const r2 = await post('threed_world_up_pick', { game: gid(), id: b.dataset.i, choice: f.dataset.c }); toast(r2.message, r2.ok); worldTab([], stripHtml()); });
  });
}
function wqDetail() {
  const box = document.getElementById('wq-detail'); if (!box) return;
  const i = (T.wq.items || []).find(x => x.id === T.wqSel);
  if (!i) { box.innerHTML = `<div class="t3-card"><div class="t3-from">Pick a thing on the left to see what was made, what the checks saw and what you can do with it.</div></div>`; return; }
  const U = i.urls || {}, f = i.first || {};
  const lines = i.checks || [];
  box.innerHTML = `<div class="t3-card"><h2>${esc(i.id)} ${wqState(i.shown)}</h2>
    <div class="t3-from">${esc(i.kind)} · ${esc(i.tier)} · ${Object.entries(i.size || {}).map(([k, m]) => `${k} ${m} m`).join(', ') || 'no size given'} · first appears: <b>${esc(f.where || '–')}</b>${f.order != null ? ` (order ${esc(f.order)})` : ''} · from ${esc(i.file)}</div>
    ${i.words ? `<div class="t3-rule" style="margin:8px 0">${esc(i.words)}</div>` : ''}
    ${(i.notes || []).map(n => `<div class="t3-warn">${esc(n)}</div>`).join('')}
    ${(i.put_right || []).map(n => `<div class="wq-chk pass">✓ ${esc(n)}</div>`).join('')}
    ${U.checks ? `<a href="${esc(U.checks)}" target="_blank"><img class="wq-pic" src="${esc(U.checks)}&w=1200" title="what the checks saw — open full size"></a>` : ''}
    ${U.colour ? `<a href="${esc(U.colour)}" target="_blank"><img class="wq-pic" src="${esc(U.colour)}&w=1200" title="colours: as made · matched to the picture · the picture"></a>` : ''}
    ${U.gate ? `<div class="t3-warn"><b>Held by the picture gate</b> — the picture was measured before the body was made from it, and every try missed. The tries, side by side:</div><a href="${esc(U.gate)}" target="_blank"><img class="wq-pic" src="${esc(U.gate)}&w=1200" title="the tries, side by side, with why each missed — open full size"></a>` : ''}
    ${i.gate_override ? `<div class="wq-chk pass">✓ Picture gate overruled by ${esc(i.gate_override.by)} (try ${esc(i.gate_override.try)})</div>` : ''}
    ${i.motion_note ? `<div class="t3-warn">${esc(i.motion_note)}</div>` : ''}
    ${lines.map(l => `<div class="wq-chk ${/held back|— held|Held back/.test(l) ? 'held' : 'pass'}">${esc(l)}</div>`).join('')}
    ${i.error ? `<div class="t3-state err">${esc(i.error)}</div>` : ''}
    <div class="t3-acts">
      ${i.straighten ? `<button class="go" data-w="straighten">Straighten</button>` : ''}
      ${i.colour_offer && i.state === 'held' ? `<button class="go" data-w="colours" title="yours: use the version matched to the picture (the model as made is kept)">Use the matched colours</button>` : ''}
      ${i.state === 'held' && i.held_by === 'picture gate' ? `<span class="t3-from" style="align-self:center">try</span><select id="wq-gtry" style="font:inherit;background:#121217;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:3px 7px">${((i.gate || {}).tries || []).map(t => `<option value="${esc(t.try)}" ${t.try === ((i.gate || {}).tries || []).slice(-1)[0].try ? 'selected' : ''}>${esc(t.try)}</option>`).join('')}</select><button class="go" data-w="gate" title="yours: make the body from this try's picture as it is">Make the body from this picture anyway</button>` : ''}
      ${i.state === 'held' && i.only_colour ? `<button class="${i.release === 'as made' ? 'go' : 'ghost'}" data-w="asmade" title="the colours as they were made — for when the match is worse than the thing as made">Release as made</button>` : ''}
      ${i.state === 'held' && i.held_by !== 'picture gate' ? `<button class="ghost" data-w="through" title="the person's: overrule the checks">Let it through anyway</button>` : ''}
      ${i.state === 'failed' ? `<button class="go" data-w="tryagain" title="back in line keeping what it had — the folder, a body kept by a release; no fresh picture">Try again</button>` : ''}
      ${['made', 'held', 'failed'].includes(i.state) || i.shown === 'turned down' ? `<button class="ghost" data-w="again">Make again</button>` : ''}
      <button class="ghost" data-w="hold">${i.hold ? 'Take off hold' : 'Hold'}</button>
      <span class="t3-from" style="align-self:center">rank</span><input id="wq-rank" value="${esc(i.rank || '')}" placeholder="0" style="width:56px;font:inherit;background:#121217;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:3px 7px" title="the order of need when things first appear together (lower first) — yours">
    </div>
    ${U.model ? viewer(U.model, { label: i.id, small: true, light: i.flame || i.glow ? 'night' : '' }) : ''}</div>`;
  box.querySelectorAll('button[data-w]').forEach(b => b.onclick = async () => { if (!G.identity) return askWho();
    const w = b.dataset.w;
    const act = { straighten: 'threed_world_straighten', colours: 'threed_world_colours', through: 'threed_world_through', again: 'threed_world_again', hold: 'threed_world_hold', gate: 'threed_world_gate', asmade: 'threed_world_as_made', tryagain: 'threed_world_try_again' }[w];
    const gsel = document.getElementById('wq-gtry');
    const run = async () => { const r = await post(act, { game: gid(), id: i.id, hold: !i.hold, pick: gsel ? +gsel.value : null }); toast(r.message, r.ok); worldTab([], stripHtml()); };
    if (w === 'gate') return confirmAct(`Make ${i.id}'s body from try ${gsel ? gsel.value : ''}?`, 'The picture gate found something wrong with every try (see the pictures above). The body is made from the try you picked, as it is; about four minutes on the card.', 'Make it anyway', run);
    if (w === 'through') return confirmAct(`Let ${i.id} through?`, 'Its checks failed. It goes to Review & approve as it is, with the failed checks shown beside it.', 'Let it through', run);
    if (w === 'asmade') return confirmAct(`Release ${i.id} as made?`, i.kind === 'body' ? 'Its colours stay as they were made — nothing is matched. It goes back in the queue for its skeleton and motions only; nothing is remade.' : 'Its colours stay as they were made. It is sized and goes to Review & approve as it is.', 'Release as made', run);
    if (w === 'again') return confirmAct(`Make ${i.id} again?`, 'What was made is kept (renamed); the thing goes back into the queue and gets a fresh picture.', 'Make again', run);
    run(); });
  const rk = document.getElementById('wq-rank');
  if (rk) rk.onchange = async () => { if (!G.identity) return askWho(); const r = await post('threed_world_rank', { game: gid(), id: i.id, rank: parseFloat(rk.value) || 0 }); toast(r.message, r.ok); };
}

// ------------------------------------------------------------------ Art → Review & approve: the 3D models
async function paintReview3d() {
  const el = document.getElementById('r-3d'); if (!el) return;
  let d; try { d = await api('/api/suite/threed/review?id=' + enc(gid())); } catch (e) { el.innerHTML = ''; return; }
  const appr = Object.entries(d.approved || {}), todo = appr.filter(([, a]) => !a.delivered);
  if (!d.waiting.length && !todo.length) { el.innerHTML = ''; return; }
  const card = x => { const U = x.urls || {}, pic = U['body.picture'] || (U.pictures || [])[0], model = U['motions.moves'] || U['body.model'];
    return `<div class="r3d-card">${pic ? `<img src="${esc(pic)}&w=420" data-m="${esc(model || '')}" data-s="${esc(U['motions.sheet'] || '')}" data-l="${esc(x.who_name || x.who)}" title="look at it in 3D">` : ''}
      <b>${esc(x.who_name || x.who)}</b> <span class="t3-from">${esc(x.kind)} · try ${esc(x.id)}</span><div class="t3-from">${esc((x.look || '').slice(0, 140))}</div>
      ${x.from === 'world' ? `<div class="chk">From the world list${x.check_picture ? ` · <a href="${esc(x.check_picture)}" target="_blank">what the checks saw</a>` : ''}</div>${(x.checks || []).slice(0, 5).map(l => `<div class="chk" style="color:${/held back|— held/.test(l) ? '#ffbe9a' : '#9fe0b8'}">${esc(l)}</div>`).join('')}` : ''}
      <div class="chk" style="color:#ffd58a" title="BUILD 40: one front picture cannot show a back — the farm wife's dress came out ragged behind, the farmhouse with a hole in its roof at the back. Only Pixal3D (buildings) can take a back picture; TRELLIS.2 takes one.">↻ Seen from behind? Turn it round in the viewer before approving — nobody saw its back${x.back_view ? ' (made with a back picture)' : ''}.</div>
      <div class="lic">${x.commercial_ok ? '✓ every tool behind it is commercial-OK' : '✗ not every tool is known commercial-OK'} · goes to ${esc(x.dest)}</div>
      <div class="t3-acts"><button class="go" data-a="approve" data-t="${esc(x.id)}" ${x.commercial_ok ? '' : 'disabled'}>Approve</button><button class="ghost" data-a="reject" data-t="${esc(x.id)}">Not this one</button></div></div>`; };
  el.innerHTML = `<div class="r3d"><div class="hero" style="margin:0 0 8px"><h2 style="margin:0">3D models</h2><span class="spacer" style="flex:1"></span>
      ${todo.length ? `<button class="go" id="r3d-dl">Deliver ${todo.length} approved model${todo.length === 1 ? '' : 's'}</button>` : ''}</div>
    ${d.waiting.length ? `<div class="r3d-grid">${d.waiting.map(card).join('')}</div>` : '<div class="t3-from">Nothing waiting.</div>'}</div>`;
  el.querySelectorAll('img[data-m]').forEach(i => i.onclick = () => { if (i.dataset.m) modal(`<h3>${esc(i.dataset.l)}</h3>${viewer(i.dataset.m, { sheet: i.dataset.s, label: i.dataset.l })}<div class="row"><button class="go" onclick="closeModal()">Close</button></div>`, true); });
  el.querySelectorAll('button[data-a]').forEach(b => b.onclick = async () => { if (!G.identity) return askWho();
    const r = await post('threed_decide', { game: gid(), try: b.dataset.t, verdict: b.dataset.a }); toast(r.message, r.ok); paintReview3d(); });
  const dlb = document.getElementById('r3d-dl');
  if (dlb) dlb.onclick = async () => { if (!G.identity) return askWho();
    const p = await post('threed_deliver', { game: gid(), dry: true });
    if (!p.ok) return toast(p.message, false);
    confirmAct('Deliver into the game?', (p.plan || []).map(x => `${x.what} → ${x.dest}`).join(' · ') + (p.game_reachable ? '' : ' — the game folder is not reachable from this computer.') + ' What it replaces is kept in out/_replaced/.', 'Deliver', async () => {
      const r = await post('threed_deliver', { game: gid(), dry: false }); toast(r.message, r.ok); paintReview3d(); }); };
}

// ------------------------------------------------------------------ Settings → This computer → 3D tools
async function paintTools3d(fresh) {
  const v = document.getElementById('v-settings'); if (!v) return;
  let box = document.getElementById('s-3d');
  if (!box) { box = document.createElement('div'); box.id = 's-3d'; box.className = 't3-card'; box.style.marginTop = '16px'; v.appendChild(box); }
  let c, runs; try { [c, runs] = await Promise.all([api('/api/suite/threed/check' + (fresh ? '?fresh=1' : '')), api('/api/suite/threed/runs?id=' + enc(gid()))]); } catch (e) { box.innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  box.innerHTML = `<h2>3D tools</h2><div class="t3-from">The rigging ComfyUI (a second ComfyUI with Blender inside, on port ${esc(c.port)}), the image-to-3D model files, the picture model and the motion library. Everything lives on the forge's own drive — the installer's defaults would put gigabytes in the user profile, and the forge moves them.</div>
    <div class="t3-items">${(c.items || []).map(i => `<div>${i.ok ? '✓' : '✗'} ${esc(i.what)}${i.detail ? ` <span class="t3-from">— ${esc(i.detail)}</span>` : ''}${!i.ok && i.fix ? `<div class="fix">→ ${esc(i.fix)}</div>` : ''}</div>`).join('')}</div>
    <div class="t3-acts"><button class="ghost" id="s3d-check">Check again</button><button class="go" id="s3d-install">Install the rigging ComfyUI</button></div>
    ${c.last_install ? `<details><summary class="t3-from">The last install's report</summary><div class="t3-log">${esc(c.last_install)}</div></details>` : ''}
    ${runs.install_log ? `<h3>Install log (newest lines)</h3><div class="t3-log">${esc(runs.install_log)}</div>` : ''}`;
  document.getElementById('s3d-check').onclick = () => paintTools3d(true);
  document.getElementById('s3d-install').onclick = () => { if (!G.identity) return askWho();
    confirmAct('Install the rigging ComfyUI?', 'It puts a second ComfyUI in engines/rig with its own Python and Blender, then starts it once on the processor to check its nodes. The first time takes about an hour and wants 40 GB free; finished steps are skipped next time. Nothing in the art ComfyUI changes.', 'Install', async () => {
      const r = await post('threed_install', { game: gid() }); toast(r.message, r.ok); setTimeout(() => paintTools3d(false), 4000); }); };
}

// ------------------------------------------------------------------ hooks into the shell's own screens
function wrap(name, after) {
  const orig = window[name];
  if (typeof orig !== 'function') return;
  window[name] = async function (...a) { const r = await orig.apply(this, a); try { await after(...a); } catch (e) { console.warn('3d hook', name, e); } return r; };
}
wrap('loadReview', () => paintReview3d());
wrap('loadSettings', () => paintTools3d(false));
wrap('paintChar', async () => {
  const pg = document.getElementById('c-page'); if (!pg || typeof C === 'undefined' || !C.page) return;
  const cid = C.page.id || C.sel; if (!cid) return;
  let d; try { d = await api(`/api/suite/threed/stage?id=${enc(gid())}&who=${enc(cid)}`); } catch (e) { return; }
  let el = document.getElementById('c-3d'); if (!el) { el = document.createElement('div'); el.id = 'c-3d'; el.className = 't3-card'; pg.prepend(el); }
  const order = ['no picture', 'picture', 'body', 'skeleton', 'motions', 'approved'];
  el.innerHTML = `<b>3D body:</b> ${order.map(s => s === d.stage ? `<b style="color:#5fc4e8">${esc(s)}</b>` : `<span class="t3-from">${esc(s)}</span>`).join(' · ')}
    <a href="#3d/bodies/${enc(cid)}" style="margin-left:10px">open in 3D →</a>`;
});

// ------------------------------------------------------------------ Places (BUILD 34): a game's places as stages
const PL_WORD = { made: 'made', held: 'held', waiting: 'waiting' };
async function placesTab(rest, strip) {
  const v = v3();
  let d; try { d = await api('/api/suite/threed/places?id=' + enc(gid())); } catch (e) { v.innerHTML = strip + `<div class="err">${esc(e)}</div>`; return; }
  T.pl = d;
  const list = d.places || [];
  T.plSel = rest[0] ? decodeURIComponent(rest[0]) : (T.plSel && list.find(p => p.id === T.plSel) ? T.plSel : (list[0] || {}).id);
  const p = list.find(x => x.id === T.plSel);
  const busy = p && (p.jobs || []).some(j => j.state === 'pending' || j.state === 'running');
  v.innerHTML = strip + `<div class="wq-head"><span class="t3-chip">${esc(list.length)} place${list.length === 1 ? '' : 's'} in ${esc(d.folder)}</span>
      <span class="t3-from">A place plan is compiled into the game's own stage folder; what it still needs goes on the World list held — nothing is made until someone releases it there.</span></div>
    <div class="wq-lay"><div class="t3-card"><h2>Places</h2><div class="wq-list">${list.length ? list.map(x => `<div class="wq-row ${x.id === T.plSel ? 'sel' : ''}" data-p="${esc(x.id)}">
        <span class="n">${x.compiled && x.compiled.at ? '◆' : '◇'}</span><div><b>${esc(x.name || x.id)}</b>${(x.problems || []).length ? `<span class="wq-badge" style="color:#ff9a8f">${x.problems.length} problem${x.problems.length > 1 ? 's' : ''}</span>` : ''}${x.compiled && x.compiled.stale ? '<span class="wq-badge" style="color:#f0d08a">plan changed since compiled</span>' : ''}
          <div class="w">${x.size ? esc(x.size[0]) + ' × ' + esc(x.size[1]) + ' m · ' : ''}${esc(x.things || 0)} things · ${x.counts ? `${x.counts.made} made, ${x.counts.held} held, ${x.counts.waiting} waiting` : ''}</div></div></div>`).join('')
        : `<div class="empty">No place plans yet. A plan is <code>${esc(d.folder)}/&lt;id&gt;.place.json</code> — or approve a floor plan "as a stage" in Art → Floor plans.</div>`}</div></div>
      <div id="pl-detail">${p ? placeHtml(p, d, busy) : ''}</div></div>`;
  document.querySelectorAll('.wq-row[data-p]').forEach(r => r.onclick = () => { T.plSel = r.dataset.p; if (typeof setAddr === 'function') setAddr('3d/places/' + enc(T.plSel)); placesTab([enc(T.plSel)], strip); });
  wirePlace(p, strip);
  if (busy) pollIfBusy(() => placesTab([enc(T.plSel)], stripHtml()));
}
function placeHtml(p, d, busy) {
  const c = p.compiled || {};
  const ents = p.entries || [];
  return `<div class="t3-card"><h2>${esc(p.name || p.id)}</h2>
      <div class="t3-from">${esc(p.file)} · ${p.size ? esc(p.size[0]) + ' × ' + esc(p.size[1]) + ' m' : ''} · ${esc(p.solids)} plan-built solids · ${esc(p.lights)} lamps · anchors: ${esc((p.anchors || []).join(', ') || 'none')}</div>
      ${(p.problems || []).map(x => `<div class="t3-warn">${esc(x)}</div>`).join('')}
      ${(p.asked || []).length ? `<div class="t3-from" style="margin-top:6px">Asked of William, grey meanwhile: ${esc(p.asked.join(' · '))}</div>` : ''}
      <div class="t3-acts">
        <button class="go" id="pl-compile" ${busy || (p.problems || []).length ? 'disabled' : ''}>${busy ? 'Compiling…' : 'Compile again'}</button>
        <button id="pl-day" ${d.can_play && (p.maps || []).length ? '' : 'disabled'} title="${(p.maps || []).length ? 'tools\\play_at.bat ' + esc(p.maps[0]) : 'no map in the game shows this place yet'}">Open in the game here — day</button>
        <button id="pl-night" ${d.can_play && (p.maps || []).length ? '' : 'disabled'}>— night</button>
        <button class="ghost" id="pl-draw">Draw the plan again</button></div>
      ${(d.looks || []).length ? `<div class="t3-acts"><span class="t3-from">The look (BUILD 63):</span>
        <select id="pl-look">${d.looks.map(l => `<option value="${esc(l)}">${esc(l.replace(/_/g, ' '))}</option>`).join('')}</select>
        <button id="pl-look-play" ${d.can_play && (p.maps || []).length ? '' : 'disabled'}>Open in the game under this look</button>
        <button id="pl-pictures" ${d.can_take && (p.maps || []).length && !(p.taking && p.taking.left) ? '' : 'disabled'} title="the game's still mode: one picture a look, at the film tier — keep the graphics card free">${p.taking && p.taking.left ? 'Taking the pictures… ' + esc(p.taking.left) + ' left' : 'Take the pictures'}</button></div>` : ''}
      <div class="t3-from">${c.at ? `Compiled ${esc(c.at)} into ${esc(c.folder || '')} — ${esc(c.things)} placed things${c.model ? ', the stage model' : ''}${c.stale ? ' · <b style="color:#f0d08a">the plan has changed since</b>' : ''}.` : 'Not compiled yet.'}
        ${(p.maps || []).length ? ` In the game as: <b>${esc(p.maps.join(', '))}</b>.` : ' No map in the game shows it yet.'}</div>
      ${(p.jobs || []).length ? `<div class="t3-from">Compiles: ${p.jobs.map(j => `${esc(j.state)}${j.error ? ' — ' + esc(j.error) : ''}`).join(' · ')}</div>` : ''}
    </div>
    ${(p.look_pictures || []).length ? `<div class="t3-card"><h2>The game's own pictures — one a look</h2><div class="t3-from">Taken by the game's still mode at the film tier: how the stage looks, not greybox.</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px;margin-top:6px">${p.look_pictures.map(lp => `<a href="${esc(lp.picture)}" target="_blank" title="${esc(lp.at || '')}"><img src="${esc(lp.picture)}&t=${Date.now()}" style="width:100%;border-radius:6px" alt="${esc(lp.look)}"><div class="t3-from">${esc(lp.look.replace(/_/g, ' '))}</div></a>`).join('')}</div></div>` : ''}
    ${p.picture ? `<div class="t3-card"><h2>The plan from above</h2><div class="t3-from">${esc(d.stamp)} — the game's own pictures of a stage come from the game (play it).</div>
      <a href="${esc(p.picture)}" target="_blank"><img src="${esc(p.picture)}&t=${Date.now()}" style="max-width:100%;border-radius:8px;margin-top:6px" alt="${esc(p.id)} from above"></a></div>` : ''}
    <div class="t3-card"><h2>What it still needs — on the World list</h2>
      ${ents.length ? `<div class="wq-list">${ents.map(e => `<div class="wq-row" onclick="go('3d/world/${enc(e.id)}')"><span class="n">${e.state === 'made' ? '✓' : e.state === 'held' ? '❚❚' : '…'}</span>
        <div><b>${esc(e.id)}</b><span class="wq-badge">${esc(e.kind || '')}</span><span class="wq-badge">${esc(e.tier || '')}</span>${e.words ? '' : '<span class="wq-badge" style="color:#f0d08a">no words yet</span>'}
        <div class="w">${esc((e.why || [])[0] || e.shown || '')}</div></div><span class="wq-st ${esc(e.state)}">${esc(PL_WORD[e.state] || e.state)}</span></div>`).join('')}</div>`
      : '<div class="empty">Nothing on the World list for this place yet — compile it.</div>'}
    </div>`;
}
function wirePlace(p, strip) {
  if (!p) return;
  const b = id => document.getElementById(id);
  if (b('pl-compile')) b('pl-compile').onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_places_compile', { game: gid(), place: p.id }); toast(r.message, r.ok); placesTab([enc(p.id)], strip); };
  const play = async (time) => { const r = await post('threed_places_play', { game: gid(), place: p.id, time: time }); toast(r.message, r.ok); };
  if (b('pl-day')) b('pl-day').onclick = () => play('day');
  if (b('pl-night')) b('pl-night').onclick = () => play('night');
  if (b('pl-draw')) b('pl-draw').onclick = async () => { const r = await post('threed_places_draw', { game: gid(), place: p.id }); toast(r.message, r.ok); placesTab([enc(p.id)], strip); };
  if (b('pl-look-play')) b('pl-look-play').onclick = () => play(b('pl-look').value);                       // BUILD 63
  if (b('pl-pictures')) b('pl-pictures').onclick = async () => { if (!G.identity) return askWho(); const r = await post('threed_places_pictures', { game: gid(), place: p.id }); toast(r.message, r.ok); placesTab([enc(p.id)], strip); };
  if (p.taking && p.taking.left) setTimeout(() => { if (T.plSel === p.id) placesTab([enc(p.id)], stripHtml()); }, 15000);
}

// ------------------------------------------------------------------ BUILD 77 — 3D → Terrain: real ground from DTED Level 0
async function terrainTab(rest, strip) {
  const v = v3();
  let d; try { d = await api('/api/suite/threed/terrain?id=' + enc(gid())); } catch (e) { v.innerHTML = strip + `<div class="err">${esc(e)}</div>`; return; }
  T.tr = d;
  const W = d.windows || [];
  const sel = T.trSel || (W[0] || {}).id || '';
  const w = W.find(x => x.id === sel) || W[0] || { south: 38.4, west: -79.42, north: 38.62, east: -78.95, dials: {} };
  const dl = Object.assign({ exaggerate: 1, relief_x: 6, sun_az: 315, sun_el: 35, detail_m: 0, smooth: 0 }, w.dials || {});
  const slider = (k, name, min, max, step) => `<div class="t3-f"><label>${esc(name)} <b id="tr-v-${k}">${esc(dl[k])}</b></label><input type="range" class="tr-dial" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${esc(dl[k])}"></div>`;
  const C = d.colours || {};
  v.innerHTML = strip + `<div class="t3-card"><h2>Terrain <span class="t3-from">DTED Level 0 — 30 arc-second posts, about 900 m; the processor only</span></h2>
      ${d.found ? `<div class="wq-chk pass">✓ ${esc(d.cells)} cells found in ${esc(d.dted_dir)}${(d.zips || []).length ? ` (read straight from ${esc(d.zips.length)} zip${d.zips.length > 1 ? 's' : ''})` : ''}${d.skipped_count ? ` · ${esc(d.skipped_count)} skipped (not Level 0)` : ''}${(d.bad || []).length ? ` · ${esc(d.bad.length)} bad cell(s) skipped` : ''}</div>`
        : `<div class="t3-warn">${esc(d.say)}</div>`}
      <div class="t3-from">Colours by how a height was produced: <span style="color:${C.measured}">■ measured</span> (the data) · <span style="color:${C.invented}">■ invented</span> (detail added below the data's scale) · <span style="color:${C.edited}">■ edited</span> (a crater, a pad). Level 0 gives ranges, basins and the fall line — not a street or a hill behind a farm; a town's pad is the place plan's.</div></div>
    <div class="wq-lay"><div class="t3-card"><h2>A window</h2>
      <div class="t3-row"><div class="t3-f"><label>the game's windows</label><select id="tr-win">${W.map(x => `<option value="${esc(x.id)}" ${x.id === sel ? 'selected' : ''}>${esc(x.id)} — ${esc(x.name || '')}${x.edits ? ` (${x.edits} edit${x.edits > 1 ? 's' : ''})` : ''}</option>`).join('')}<option value="">(my own)</option></select></div></div>
      <div class="t3-row">${['south', 'west', 'north', 'east'].map(k => `<div class="t3-f"><label>${k}</label><input id="tr-${k}" value="${esc(w[k])}" style="width:90px"></div>`).join('')}</div>
      ${slider('exaggerate', 'exaggerate (vertical)', 0.5, 8, 0.25)}${slider('relief_x', 'relief in the light', 1, 20, 0.5)}
      ${slider('sun_az', 'sun from (°)', 0, 359, 5)}${slider('sun_el', 'sun height (°)', 5, 80, 1)}
      ${slider('detail_m', 'detail added (m, invented)', 0, 30, 1)}${slider('smooth', 'smooth (passes)', 0, 6, 1)}
      <div class="t3-acts"><button class="go" id="tr-draw">Draw</button><button class="ghost" id="tr-bake" ${d.found ? '' : 'disabled'}>Bake ${esc(sel || 'the game\'s windows')}</button><button class="ghost" id="tr-bakeall" ${d.found ? '' : 'disabled'}>Bake every window</button><button class="ghost" id="tr-proof" ${d.found ? '' : 'disabled'}>Prove the reader</button></div>
      <div class="t3-from" id="tr-info"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><img id="tr-shade" style="max-width:49%;border-radius:6px"><img id="tr-how" style="max-width:49%;border-radius:6px" title="how each height was produced"></div></div>
    <div><div class="t3-card"><h2>Check a point</h2><div class="t3-row"><div class="t3-f"><label>latitude</label><input id="tr-lat" value="38.50" style="width:90px"></div><div class="t3-f"><label>longitude</label><input id="tr-lon" value="-79.28" style="width:90px"></div><button class="go" id="tr-check" style="align-self:end">Check</button></div><div id="tr-pt" class="t3-from"></div></div>
      <div class="t3-card"><h2>Baked</h2>${d.bake && d.bake.running ? `<div class="t3-state">baking…</div>` : ''}${(d.bake && d.bake.lines || []).map(l => `<div class="t3-from">${esc(l)}</div>`).join('')}
        ${(d.baked || []).length ? `<div class="t3-from">${esc(d.out)}</div>${d.baked.map(n => `<div class="t3-from">${esc(n)}</div>`).join('')}` : `<div class="t3-from">nothing baked yet</div>`}
        ${(d.profiles || []).length ? `<h3>Lines the story asks for</h3>${d.profiles.map(p => `<div class="t3-from">${esc(p.id)} — ${esc(p.title || '')}</div>`).join('')}<div class="t3-from">terrain_profile.bat draws them.</div>` : ''}</div>
      <div class="t3-card" id="tr-prooft" style="display:none"></div></div></div>`;
  const val = id => parseFloat(document.getElementById(id).value);
  const dials = () => { const o = {}; document.querySelectorAll('.tr-dial').forEach(x => o[x.dataset.k] = parseFloat(x.value)); return o; };
  let pending = null;
  const draw = async () => {
    const info = document.getElementById('tr-info'); info.textContent = 'drawing…';
    const r = await post('threed_terrain_preview', { game: gid(), south: val('tr-south'), west: val('tr-west'), north: val('tr-north'), east: val('tr-east'), dials: dials() });
    if (!r.ok) { info.textContent = r.message || 'not drawn'; return; }
    document.getElementById('tr-shade').src = r.shade; document.getElementById('tr-how').src = r.how;
    info.textContent = `${Math.round(r.size_m.width / 1000)} × ${Math.round(r.size_m.height / 1000)} km · ${r.m_per_post} m a post · ${r.min_m} to ${r.max_m} m · ${r.cells} cell(s)${r.missing ? ` · ${r.missing} without data (sea)` : ''}`;
  };
  document.querySelectorAll('.tr-dial').forEach(x => x.oninput = () => { document.getElementById('tr-v-' + x.dataset.k).textContent = x.value; clearTimeout(pending); pending = setTimeout(draw, 350); });
  document.getElementById('tr-win').onchange = e => { T.trSel = e.target.value; terrainTab([], strip); };
  document.getElementById('tr-draw').onclick = draw;
  document.getElementById('tr-check').onclick = async () => { const r = await post('threed_terrain_check', { game: gid(), lat: val('tr-lat'), lon: val('tr-lon') }); document.getElementById('tr-pt').textContent = r.message; };
  const bake = only => async () => { if (!G.identity) return askWho(); const r = await post('threed_terrain_bake', { game: gid(), only }); toast(r.message, r.ok); setTimeout(() => terrainTab([], stripHtml()), 4000); };
  const b1 = document.getElementById('tr-bake'); if (b1) b1.onclick = bake(sel || null);
  const b2 = document.getElementById('tr-bakeall'); if (b2) b2.onclick = bake(null);
  const pr = document.getElementById('tr-proof'); if (pr) pr.onclick = async () => { const box = document.getElementById('tr-prooft'); box.style.display = ''; box.innerHTML = '<div class="t3-from">reading…</div>';
    const r = await post('threed_terrain_proof', { game: gid() }); const t = r.table || { rows: [] };
    box.innerHTML = `<h2>The reader against known ground</h2><table class="wq-tiers">${t.rows.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.published_m)} m</td><td>${x.reads_m == null ? 'no data' : esc(x.reads_m) + ' m'}</td><td class="${x.diff_m != null && Math.abs(x.diff_m) < 60 ? 'm' : 'g'}">${x.diff_m == null ? '' : (x.diff_m > 0 ? '+' : '') + esc(x.diff_m)}</td></tr>`).join('')}</table><div class="t3-from">Summits read low: Level 0's posts are about 900 m apart.${t.stop && t.stop.length ? ' STOP — a low point reads high.' : ''}</div>`; };
  if (d.found && W.length) draw();
  if (d.bake && d.bake.running) setTimeout(() => terrainTab([], stripHtml()), 5000);
}

})();


