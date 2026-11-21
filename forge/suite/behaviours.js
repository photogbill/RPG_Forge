// BUILD 31 — Characters → Behaviours: what each character does off duty, as cards; a preview by place and era; coverage.
// Loaded after the shell's own script; it uses the shell's helpers (api, post, toast, esc, gid). No game is named here:
// everything comes from the game's own decks and its adapter's places.
(function () {
'use strict';
const css = `
#v-behaviours{max-width:1500px}
.bh-top{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 10px}
.bh-top select{font:inherit;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:8px;padding:6px 8px}
.bh-head{font-size:13px;color:#cfccc5;background:#16161c;border-left:3px solid var(--accent);padding:7px 11px;border-radius:0 8px 8px 0;margin:0 0 10px}
.bh-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.bh-deck{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.bh-deck h3{margin:0 0 8px;font-size:16px;display:flex;justify-content:space-between;align-items:baseline}
.bh-deck h3 small{font-size:11.5px;color:var(--faint);font-weight:400}
.bh-card{border-left:4px solid var(--c);background:color-mix(in srgb,var(--c) 10%,var(--panel2));border-radius:0 8px 8px 0;padding:7px 9px;margin:0 0 7px;font-size:13px}
.bh-card .what{color:var(--ink);line-height:1.35}
.bh-card .when,.bh-card .src{font-size:11.5px;color:var(--faint);margin-top:3px}
.bh-card .row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:5px}
.bh-card .st{font-size:11px;color:var(--c);letter-spacing:.02em;text-transform:uppercase}
.bh-card button{font:inherit;font-size:12px;padding:3px 10px;border-radius:7px;border:1px solid var(--line);background:#121217;color:var(--ink);cursor:pointer}
.bh-thin{color:var(--warn);font-size:12.5px;margin:4px 0 0}
.bh-prev{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:0 0 14px}
.bh-prev table{border-collapse:collapse;width:100%;font-size:13px}
.bh-prev td{padding:4px 8px;border-top:1px solid var(--line);vertical-align:top}
.bh-ok{color:var(--good)}.bh-no{color:var(--warn)}
`;
const COL = {approved: '#f0b040', draft: '#b58cff', flagged: '#ff6b6b'};
const B = {data: null, place: '', era: ''};
function style() { if (!document.getElementById('bh-css')) { const s = document.createElement('style'); s.id = 'bh-css'; s.textContent = css; document.head.appendChild(s); } }
function whenText(w) {
  const bits = [];
  for (const [k, v] of Object.entries(w || {})) bits.push(k + ': ' + (Array.isArray(v) ? v.join(', ') : (typeof v === 'object' ? 'a condition' : v)));
  return bits.length ? bits.join(' · ') : 'anywhere, any time';
}
function card(deck, b) {
  const c = COL[b.status] || '#8d8d99';
  const act = b.status === 'approved' ? `<button data-un="1" data-d="${esc(deck.id)}" data-b="${esc(b.id)}">Back to a draft</button>`
                                      : `<button data-d="${esc(deck.id)}" data-b="${esc(b.id)}">Approve</button>`;
  const rx = (b.reactions || []).map(r => `${esc(r.who)}: “${esc(r.line)}”`).join(' · ');
  return `<div class="bh-card" style="--c:${c}"><div class="what">${esc(b.what)}</div>
    <div class="when">${esc(whenText(b.when))} · weight ${esc(b.weight)}${b.npc_reaction ? ' · the room: ' + esc(b.npc_reaction) : ''}</div>
    ${rx ? `<div class="when">reaction — ${rx}</div>` : ''}
    ${b.source ? `<div class="src">${esc(b.source)}</div>` : ''}
    <div class="row"><span class="st">${esc(b.status)} · ${esc(b.id)}</span>${act}</div></div>`;
}
async function preview() {
  const box = document.getElementById('bh-preview');
  if (!B.place) { box.innerHTML = '<div class="empty">Pick a place and an era to see who could do what there.</div>'; return; }
  const r = await api(`/api/suite/behaviourpreview?id=${encodeURIComponent(gid())}&place=${encodeURIComponent(B.place)}&era=${encodeURIComponent(B.era || 'any')}`);
  if (r.error) { box.innerHTML = `<div class="empty">${esc(r.error)}</div>`; return; }
  box.innerHTML = `<table>${r.members.map(m => `<tr><td><b>${esc(m.character)}</b><br><span class="${m.enough ? 'bh-ok' : 'bh-no'}">${m.count} could happen</span></td>
    <td>${m.could.map(b => esc(b.what)).join('<br>') || '<span class="bh-no">nothing to do here</span>'}</td></tr>`).join('')}</table>`;
}
function paint() {
  const d = B.data, v = document.getElementById('v-behaviours');
  const places = d.places.map(p => `<option value="${esc(p.id)}"${p.id === B.place ? ' selected' : ''}>${esc(p.name || p.id)} (${esc(p.place)})</option>`).join('');
  const eras = d.eras.map(e => `<option${e === B.era ? ' selected' : ''}>${esc(e)}</option>`).join('');
  const thin = Object.fromEntries(d.thin.map(t => [t.character, t]));
  v.innerHTML = `<div class="bh-head">${d.counts.decks} characters · ${d.counts.behaviours} behaviours · ${d.counts.approved} approved — the party splits up in a town and each does their own thing. Approving is yours; a session can only propose.</div>
    <div class="bh-top"><b>Preview</b><select id="bh-place"><option value="">a place…</option>${places}</select><select id="bh-era">${eras}</select></div>
    <div class="bh-prev" id="bh-preview"></div>
    <div class="bh-grid">${d.decks.map(k => `<div class="bh-deck"><h3>${esc(k.character)} <small>${k.behaviours.length} · ${esc(k.file)}</small></h3>
      ${thin[k.character] ? `<div class="bh-thin">fewer than ${d.min} things to do in ${thin[k.character].count} place/era(s)</div>` : ''}
      ${k.behaviours.map(b => card(k, b)).join('')}</div>`).join('')}</div>`;
  document.getElementById('bh-place').onchange = e => { B.place = e.target.value; preview(); };
  document.getElementById('bh-era').onchange = e => { B.era = e.target.value; preview(); };
  v.querySelectorAll('.bh-card button').forEach(btn => btn.onclick = async () => {
    const r = await post(btn.dataset.un ? 'behaviour_unapprove' : 'behaviour_approve', {game: gid(), deck: btn.dataset.d, behaviour: btn.dataset.b});
    toast(r.message || (r.ok ? 'done' : 'not saved'), !!r.ok);
    if (r.ok) window.loadBehaviours();
  });
  preview();
}
window.loadBehaviours = async function () {
  style();
  const v = document.getElementById('v-behaviours');
  v.innerHTML = '<div class="empty">Reading the decks…</div>';
  const r = await api(`/api/suite/behaviours?id=${encodeURIComponent(gid())}`);
  if (r.error) { v.innerHTML = `<div class="empty">${esc(r.error)}</div>`; return; }
  B.data = r;
  if (!B.era && r.eras.length) B.era = r.eras[0];
  paint();
};
})();
