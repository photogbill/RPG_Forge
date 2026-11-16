// Motion capture (2026-11-15) — the takes that have to be filmed, so none is forgotten, and how to film them.
// Loaded after the shell's own script; it uses the shell's helpers (api, post, toast, esc, gid, $). No game is named here.
(function () {
'use strict';
const css = `
#v-mocap{max-width:1500px}
.mc-top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.mc-chip{font-size:12.5px;border:1px solid var(--line);border-radius:999px;padding:3px 11px;background:var(--panel);color:var(--dim);cursor:pointer;user-select:none}
.mc-chip.on{border-color:var(--accent);color:var(--ink);background:#2a2418}
.mc-head{font-size:13px;color:#cfccc5;background:#16161c;border-left:3px solid #ff7aa8;padding:7px 11px;border-radius:0 8px 8px 0;margin:0 0 12px}
.mc-card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 9px}
.mc-card.done{opacity:.62}
.mc-row{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline}
.mc-title{font-weight:640;font-size:14.5px}
.mc-tag{font-size:11.5px;border-radius:999px;padding:1px 8px;border:1px solid var(--line);color:var(--dim)}
.mc-tag.now{border-color:#ff8a4c;color:#ffb38c}.mc-tag.soon{border-color:#f0b040;color:#f3cf86}.mc-tag.someday{color:var(--faint)}
.mc-st{font-size:11.5px;border-radius:6px;padding:1px 8px;font-weight:600}
.mc-st.needed{background:#3a1f1f;color:#ff9c9c}.mc-st.planned{background:#3a331f;color:#f3cf86}.mc-st.filmed{background:#1f2f3a;color:#9cd2ff}
.mc-st.processed{background:#2a1f3a;color:#d2a6ff}.mc-st.in_game{background:#1f3a26;color:#8fe0a5}
.mc-k{font-size:12px;color:var(--faint);min-width:84px;display:inline-block}
.mc-v{font-size:13px;color:var(--ink)}
.mc-line{margin:4px 0 0}
.mc-edit{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 0;align-items:center}
.mc-edit select,.mc-edit input,.mc-form input,.mc-form select,.mc-form textarea{font:inherit;font-size:13px;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:7px;padding:4px 8px}
.mc-edit input.wide{flex:1;min-width:240px}
.mc-btn{font:inherit;font-size:12.5px;border:1px solid var(--line);border-radius:7px;padding:4px 10px;background:var(--panel2);color:var(--ink);cursor:pointer}
.mc-btn:hover{border-color:var(--accent)}
.mc-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:6px 0 14px}
.mc-form textarea{min-height:54px;grid-column:1/-1}
.mc-guide h3{font-size:14px;margin:14px 0 5px;color:#ffb3cc}
.mc-guide li{font-size:13.5px;line-height:1.5;margin:0 0 3px}
`;
const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
const MC = {filter: 'open', data: null, tab: 'takes'};
const WORD = {needed: 'needed', planned: 'planned', filmed: 'filmed', processed: 'turned into motion', in_game: 'in the game'};

async function load(tab) {
  const v = $('#v-mocap'); MC.tab = tab || 'takes';
  let d; try { d = await api('/api/suite/mocap?id=' + encodeURIComponent(gid())); } catch (e) { v.innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  if (d.error) { v.innerHTML = `<div class="err">${esc(d.error)}</div>`; return; }
  MC.data = d;
  if (MC.tab === 'howto') return paintGuide(v, d);
  paintTakes(v, d);
}

function paintTakes(v, d) {
  const c = d.counts || {};
  const open = (c.needed || 0) + (c.planned || 0);
  let h = `<div class="mc-head">Everything that has to be filmed for motion, so none of it is forgotten. ${open} still to film`
        + ` · ${c.filmed || 0} filmed · ${(c.processed || 0) + (c.in_game || 0)} turned into motion. Footage stays on this computer.</div>`;
  h += `<div class="mc-top">` + [['open', 'Still to film'], ['done', 'Filmed and after'], ['all', 'All']].map(([k, w]) =>
        `<span class="mc-chip ${MC.filter === k ? 'on' : ''}" data-f="${k}">${w}</span>`).join('') + `</div>`;
  const rows = d.takes.filter(t => MC.filter === 'all' || (MC.filter === 'open' ? ['needed', 'planned'].includes(t.status) : !['needed', 'planned'].includes(t.status)));
  if (!rows.length) h += `<div class="mc-card">Nothing here.</div>`;
  for (const t of rows) {
    const done = !['needed', 'planned'].includes(t.status);
    h += `<div class="mc-card ${done ? 'done' : ''}" data-id="${esc(t.id)}">
      <div class="mc-row"><span class="mc-title">${esc(t.title)}</span><span class="mc-st ${esc(t.status)}">${esc(WORD[t.status] || t.status)}</span>
        <span class="mc-tag ${esc(t.priority)}">${esc(t.priority)}</span>
        <span class="mc-tag">${esc(t.who)}${t.performer ? ' · performed by ' + esc(t.performer) : ''}${t.partner ? ' · with ' + esc(t.partner) : ''}</span></div>
      ${t.where ? `<div class="mc-line"><span class="mc-k">Where</span><span class="mc-v">${esc(t.where)}${t.song ? ' — ' + esc(t.song) : ''}</span></div>` : ''}
      <div class="mc-line"><span class="mc-k">Perform</span><span class="mc-v">${esc(t.perform)}</span></div>
      ${t.marks ? `<div class="mc-line"><span class="mc-k">Marks</span><span class="mc-v">${esc(t.marks)}</span></div>` : ''}
      ${t.length_sec ? `<div class="mc-line"><span class="mc-k">Length</span><span class="mc-v">about ${Math.round(t.length_sec)} s</span></div>` : ''}
      <div class="mc-edit">
        <select data-k="status">${d.statuses.map(s => `<option value="${s}" ${s === t.status ? 'selected' : ''}>${WORD[s] || s}</option>`).join('')}</select>
        <select data-k="priority">${d.priorities.map(s => `<option value="${s}" ${s === t.priority ? 'selected' : ''}>${s}</option>`).join('')}</select>
        <input class="wide" data-k="footage" placeholder="Footage (where the files are, once filmed)" value="${esc(t.footage || '')}">
        <input class="wide" data-k="notes" placeholder="Notes" value="${esc(t.notes || '')}">
      </div></div>`;
  }
  h += `<h3 style="margin:18px 0 4px;font-size:14px">Add a take</h3>
    <div class="mc-form" id="mc-add">
      <input name="title" placeholder="Title (e.g. The bow at the curtain call)">
      <input name="who" placeholder="For (the character)">
      <input name="performer" placeholder="Performed by">
      <input name="where" placeholder="Where (scene, song)">
      <select name="priority">${d.priorities.map(s => `<option ${s === 'soon' ? 'selected' : ''}>${s}</option>`).join('')}</select>
      <input name="marks" placeholder="Marks (where to stand, turn, stop)">
      <textarea name="perform" placeholder="What to perform, in plain words"></textarea>
      <button class="mc-btn" id="mc-add-go">Add the take</button>
    </div>`;
  v.innerHTML = h;
  v.querySelectorAll('.mc-chip').forEach(e => e.onclick = () => { MC.filter = e.dataset.f; paintTakes(v, MC.data); });
  v.querySelectorAll('.mc-edit [data-k]').forEach(e => e.onchange = async () => {
    const id = e.closest('.mc-card').dataset.id;
    const r = await post('mocap_set', {game: gid(), id, field: e.dataset.k, value: e.value});
    toast(r.message, r.ok); if (r.ok) load(MC.tab); else load(MC.tab);
  });
  $('#mc-add-go').onclick = async () => {
    const f = {}; v.querySelectorAll('#mc-add [name]').forEach(e => f[e.name] = e.value);
    const r = await post('mocap_add', {game: gid(), take: f});
    toast(r.message, r.ok); if (r.ok) load('takes');
  };
}

function paintGuide(v, d) {
  let h = `<div class="mc-head">How to film a take so the motion tools can read it. Read once before a session; the takes list says what to film.</div><div class="mc-guide">`;
  for (const s of d.guide) h += `<h3>${esc(s.title)}</h3><ul>${s.lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul>`;
  v.innerHTML = h + `</div>`;
}

window.loadMocap = load;
})();
