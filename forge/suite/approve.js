/* BUILD 78 — approvals made easy.
   ✦ William, 2026-11-17 23:37: "I would rather notice something wrong to fix later, than to go item by item which takes longer."
   One card at the top of every page that holds things for a person (3D → World list, Art → Review & approve): the count,
   one plain line a group saying what will happen, one button — and below it what was approved, each with its Undo.
   Settings gets the switch "<assistant> may approve for me". Nothing here names a game. */
(function () {
'use strict';
const enc = encodeURIComponent;
const PAGE_WORD = { world: 'World list', review: 'Review & approve' };

function settingChip(s) {
  if (!s) return '';
  return `<span class="ap-chip ${s.on ? 'on' : ''}" title="${esc(s.said || '')} (${esc(s.where || '')}) — Settings → Approvals">${s.on ? '✓' : '·'} ${esc(((s.assistants || [])[0] || 'An assistant').replace(/^Claude /, ''))} may approve for you: <b>${s.on ? 'on' : 'off'}</b></span>`;
}

function recentHtml(list) {
  if (!list || !list.length) return '';
  const rows = list.slice(0, 40).map(r => `<div class="ap-row ${r.undone ? 'undone' : ''}"><span class="ap-when">${esc(String(r.at || '').replace('T', ' ').slice(5, 16))}</span>
      <b>${esc(r.id)}</b> <span class="t3-from">${esc(r.what || '')} · ${esc(r.by || '')}</span>
      ${r.undone ? '<span class="t3-from">— undone</span>' : `<button class="ghost ap-undo" data-u="${esc(r.uid)}" title="put it back as it was before">Undo</button>`}</div>`).join('');
  return `<details class="ap-recent"><summary class="t3-from">What was approved here — ${list.length} (each can be undone while it is still where it was left)</summary>${rows}</details>`;
}

async function approveCard(page, el, refresh) {
  if (!el) return;
  let d;
  try { d = await api(`/api/suite/approve?id=${enc(gid())}&page=${enc(page)}`); } catch (e) { el.innerHTML = ''; return; }
  const n = d.count || 0;
  const lines = (d.lines || []).map(l => `<div class="ap-line">→ ${esc(l)}</div>`).join('');
  const left = (d.left || []).map(l => `<div class="ap-line left">· ${esc(l)}</div>`).join('');
  if (!n && !(d.recent || []).length) { el.innerHTML = ''; return; }
  el.innerHTML = `<div class="t3-card ap-card">
      <div class="ap-head"><h2 style="margin:0">${n ? 'Waiting for you' : 'Nothing waiting'}</h2>${settingChip(d.setting)}<span style="flex:1"></span>
        ${n ? `<button class="go ap-go" id="ap-go-${esc(page)}">✓ Approve everything here (${n})</button>` : ''}</div>
      ${n ? lines : `<div class="t3-from">${esc(d.nothing || '')}</div>`}${left}
      ${n ? '<div class="t3-from" style="margin-top:6px">Wrong one later? Undo it below, or turn it down where it waits — nothing is deleted.</div>' : ''}
      ${recentHtml(d.recent)}
    </div>`;
  const go = document.getElementById('ap-go-' + page);
  if (go) go.onclick = () => { if (!G.identity) return askWho();
    confirmAct(`Approve everything here (${n})?`, (d.lines || []).join(' ') + ' Each one can be undone afterwards.', 'Approve everything', async () => {
      go.disabled = true; go.textContent = 'Approving…';
      const r = await post('approve_all', { game: gid(), page });
      toast(r.message, r.ok !== false && (r.done || []).length > 0);
      if (refresh) refresh(); else approveCard(page, el, refresh);
    }); };
  el.querySelectorAll('.ap-undo').forEach(b => b.onclick = async () => { if (!G.identity) return askWho();
    b.disabled = true;
    const r = await post('approve_undo', { game: gid(), uid: b.dataset.u });
    toast(r.message, r.ok);
    if (refresh) refresh(); else approveCard(page, el, refresh);
  });
}
window.approveCard = approveCard;

// Art → Review & approve: the card above everything else on the page
function hook(name, after) {
  const orig = window[name];
  if (typeof orig !== 'function') return;
  window[name] = async function (...a) { const r = await orig.apply(this, a); try { await after(...a); } catch (e) { console.warn('approve hook', name, e); } return r; };
}
hook('loadReview', () => approveCard('review', document.getElementById('r-approve'), () => { if (typeof loadReview === 'function') loadReview(); }));

// Settings → Approvals: the switch
hook('loadSettings', async () => {
  const v = document.getElementById('v-settings'); if (!v) return;
  let box = document.getElementById('s-approve');
  if (!box) { box = document.createElement('div'); box.id = 's-approve'; box.className = 't3-card'; box.style.marginTop = '16px'; v.prepend(box); }
  let d; try { d = await api(`/api/suite/approve?id=${enc(gid())}&page=world`); } catch (e) { box.innerHTML = ''; return; }
  const s = d.setting || {};
  const who = (s.assistants || [])[0] || 'An assistant';
  box.innerHTML = `<h2>Approvals</h2>
    <label class="chk" style="font-size:15px"><input type="checkbox" id="ap-set" ${s.on ? 'checked' : ''}><span><b>${esc(who.replace(/^Claude /, ''))} may approve for me</b></span></label>
    <div class="t3-from" style="margin:4px 0 0 26px">${esc(s.said || '')} It covers made things — releases on the World list and Review & approve. Words stay yours: canon, lyrics, rulings and approved text.
      <br>Now: <b>${s.on ? 'on' : 'off'}</b> (${esc(s.where || '')}${s.set_by ? ', ' + esc(s.set_by) : ''}${s.set_at ? ' ' + esc(String(s.set_at).replace('T', ' ').slice(0, 16)) : ''}).</div>`;
  document.getElementById('ap-set').onchange = async e => { if (!G.identity) { e.target.checked = !e.target.checked; return askWho(); }
    const r = await post('approve_setting', { game: gid(), on: e.target.checked });
    toast(r.message, r.ok); if (!r.ok) e.target.checked = !e.target.checked; };
});

// its looks, in the page's own colours
const css = document.createElement('style');
css.textContent = `.ap-card{border-color:#3f6a52}.ap-head{display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.ap-go{font-size:16px;padding:9px 18px}.ap-line{margin:3px 0;color:var(--ink)}.ap-line.left{color:var(--dim)}
.ap-chip{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12.5px;color:var(--dim)}.ap-chip.on{border-color:#3f6a52;color:#9fe0b8}
.ap-recent{margin-top:10px}.ap-row{display:flex;gap:8px;align-items:center;padding:3px 0;border-top:1px solid var(--line)}.ap-row.undone{opacity:.55}
.ap-when{color:var(--faint);font-size:12px;min-width:80px}.ap-undo{padding:2px 10px}`;
document.head.appendChild(css);
})();
