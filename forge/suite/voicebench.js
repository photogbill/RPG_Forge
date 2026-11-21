// Characters → Voice bench (BUILD 71) — a face, a line, a voice, and whether the mouth matches.
// Loaded after the shell's own script; it uses the shell's helpers (api, post, toast, esc, gid, G, askWho). No game is named here.
(function () {
'use strict';
const css = `
#v-voicebench{max-width:1500px}
.vb-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.vb-card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.vb-card h2{font-size:15px;margin:0 0 8px}.vb-card h3{font-size:13px;margin:10px 0 4px;color:var(--dim)}
.vb-card select,.vb-card input,.vb-card textarea{font:inherit;font-size:13px;color:var(--ink);background:#121217;border:1px solid var(--line);border-radius:7px;padding:4px 8px;max-width:100%}
.vb-card textarea{width:100%;min-height:70px}
.vb-btn{font:inherit;font-size:12.5px;border:1px solid var(--line);border-radius:7px;padding:4px 10px;background:var(--panel2);color:var(--ink);cursor:pointer;margin:2px}
.vb-btn.go{border-color:var(--accent)}.vb-btn:disabled{opacity:.45;cursor:default}
.vb-need{font-size:12.5px;margin:2px 0}.vb-need.ok{color:#8fe0a5}.vb-need.no{color:#ffb38c}
.vb-stage{position:relative;display:inline-block;background:#0e0e12;border-radius:8px;overflow:hidden}
.vb-stage img{display:block;max-width:100%}
.vb-lane{position:relative;height:20px;margin:3px 0;background:#15151b;border-radius:4px;overflow:hidden;cursor:pointer}
.vb-lane.on{outline:1px solid var(--accent)}
.vb-lane span{position:absolute;top:0;bottom:0;font-size:10px;color:#111;text-align:center;overflow:hidden;border-right:1px solid #0006}
.vb-head{position:absolute;top:0;bottom:0;width:2px;background:#fff}
.vb-words span{display:inline-block;margin:1px 2px;padding:0 4px;border-radius:4px;background:#1f2a1f;font-size:12.5px}
.vb-words span.bad{background:#3a1f1f;color:#ffb3b3}
.vb-take{font-size:12.5px;border-top:1px solid var(--line);padding:5px 0}
.vb-warn{font-size:12.5px;color:#f3cf86;margin:4px 0}`;
const SC = {A: '#7aa7ff', B: '#9cd2ff', C: '#8fe0a5', D: '#f3cf86', E: '#ffb38c', F: '#d2a6ff', G: '#ff9c9c', H: '#c0e08f', X: '#55555f'};
const V = { d: null, face: null, frames: null, box: null, take: null, lanes: null, laneOn: 'rhubarb', audio: null, raf: 0, offset: 0, blend: 0.06 };

async function loadVoiceBench() {
  if (!document.getElementById('vb-css')) { const s = document.createElement('style'); s.id = 'vb-css'; s.textContent = css; document.head.appendChild(s); }
  const v = document.getElementById('v-voicebench');
  let d; try { d = await api('/api/suite/voicebench?id=' + encodeURIComponent(gid())); } catch (e) { v.innerHTML = `<div class="err">${esc(e)}</div>`; return; }
  if (d.error) { v.innerHTML = `<div class="err">${esc(d.error)}</div>`; return; }
  V.d = d;
  const need = (k, n) => { const [ok, w] = d.tools[k] || [false, '']; return `<div class="vb-need ${ok ? 'ok' : 'no'}">${ok ? '✓' : '✗'} ${esc(n)} — ${esc(w)} ${!ok && (k === 'rhubarb' || k === 'whisper') ? `<button class="vb-btn" data-get="${k}">Get it</button>` : ''}</div>`; };
  const eng = d.engines.map(e => `<option value="${esc(e.id)}" ${!e.installed || !e.licence_ok ? 'disabled' : ''}>${esc(e.name)}${e.installed ? '' : ' (not installed)'}${e.licence_ok ? '' : ' — licence not read'}</option>`).join('');
  v.innerHTML = `<div class="vb-card" style="margin-bottom:12px"><h2>Voice bench <span class="t3-from">a face, a line, a voice — and whether the mouth matches, before any of it is in the game</span></h2>
      ${need('rhubarb', 'Rhubarb (the careful timing)')}${need('whisper', 'Whisper large-v3 (the words check)')}${need('voice_engine', 'a voice engine (optional)')}
      <div class="vb-need ${d.card.free ? 'ok' : 'no'}">${d.card.free ? 'The graphics card is free — asked for, never taken.' : 'The card is busy (' + esc(d.card.why) + ') — runs go on the processor.'}</div>
      <div class="vb-warn">${esc(d.song_rule)}</div></div>
    <div class="vb-grid">
      <div class="vb-card"><h2>Face</h2>
        <h3>one picture (a labelled stand-in mouth)</h3><input type="file" id="vb-pic" accept="image/*">
        <div class="t3-from">Drag a box round the mouth on the picture; the bench draws a stand-in mouth a shape. It says STAND-IN on it and is never saved as art.</div>
        <div class="vb-stage" id="vb-stage"><img id="vb-img"></div>
        <h3>or a portrait set from the game</h3><select id="vb-port"><option value="">—</option>${d.portraits.map(x => `<option>${esc(x)}</option>`).join('')}</select>
        <div class="t3-from" id="vb-avail"></div></div>
      <div class="vb-card"><h2>Script</h2>
        <select id="vb-for"><option value="">(loose — no character)</option>${d.people.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select>
        <div class="t3-from" id="vb-voicerec"></div>
        <textarea id="vb-line" placeholder="the line, as it will be said"></textarea>
        <div><select id="vb-mood">${d.moods.map(m => `<option>${esc(m)}</option>`).join('')}</select> <select id="vb-lang"><option value="en">English</option><option value="it">Italian (phonetic timing)</option></select></div></div>
      <div class="vb-card"><h2>Voice</h2>
        <h3>from a recording</h3>
        <select id="vb-cut"><option value="">a cut from the songs…</option>${d.cuts.map(c => `<option>${esc(c)}</option>`).join('')}</select>
        <select id="vb-sample"><option value="">a sample…</option>${d.samples.map(c => `<option>${esc(c)}</option>`).join('')}</select>
        <div><input type="file" id="vb-file" accept="audio/*"></div>
        <h3>or an engine</h3><select id="vb-eng"><option value="file">(a recording)</option>${eng}</select> <label class="t3-from"><input type="checkbox" id="vb-usecard"> use the card if it is free</label>
        <div class="vb-btn go" id="vb-run" role="button" style="display:inline-block;margin-top:8px">Test it</div></div>
    </div>
    <div class="vb-card" style="margin-top:12px"><h2>Test</h2><div id="vb-test" class="t3-from">Pick a face, write the line, choose a voice, then Test it.</div></div>
    <div class="vb-grid" style="margin-top:12px">
      <div class="vb-card"><h2>Takes</h2><button class="vb-btn" id="vb-clear">Clear the takes nobody marked</button><div id="vb-takes">${d.takes.map(t => `<div class="vb-take"><b>${esc(t.for || 'loose')}</b> · ${esc(t.engine)} · ${esc(t.origin)} · ${esc((t.line || '').slice(0, 70))} ${t.marked ? '✓ marked' : ''}${t.words ? (t.words.match ? ' · words match' : ' · words differ') : ''}</div>`).join('') || '<div class="t3-from">none yet</div>'}</div></div>
      <div class="vb-card"><h2>Voice cards</h2>${d.cards.map(c => `<div class="vb-take"><b>${esc(c.id)}</b> · ${esc(c.engine || '')} · ${esc(c.way || '')} · ${esc(c.reference_origin || '')} · <b>${esc(c.status)}</b> ${String(c.status || '').startsWith('locked') ? '' : `<button class="vb-btn" data-lock="${esc(c.id)}">Lock (yours)</button>`}</div>`).join('') || '<div class="t3-from">No cards yet. A card is saved from a take you like; only William locks one.</div>'}</div>
      <div class="vb-card"><h2>What we have learned</h2>${Object.entries(d.learned.engines || {}).map(([k, e]) => `<div class="vb-take"><b>${esc(k)}</b> · ${e.takes} takes · words matched ${e.words_match}/${e.words_checked} · "sounds like them" ${e.sounds_like} · ${e.seconds_a_line ?? '–'} s a line</div>`).join('') || '<div class="t3-from">Nothing yet.</div>'}
        ${d.learned.offset_median != null ? `<div class="vb-take">the offset left on marked takes: ${Math.round(d.learned.offset_median * 1000)} ms</div>` : ''}</div>
    </div>`;
  wire();
}

function wire() {
  const d = V.d;
  document.querySelectorAll('[data-get]').forEach(b => b.onclick = async () => { if (!G.identity) return askWho(); const r = await post('voice_get', { game: gid(), what: b.dataset.get }); toast(r.message, r.ok); });
  document.getElementById('vb-for').onchange = e => { const p = d.people.find(x => x.id === e.target.value); document.getElementById('vb-voicerec').textContent = p ? (p.voice ? 'On record (how they sing): ' + JSON.stringify(p.voice).slice(0, 220) : 'No voice on record — ask Bill.') : ''; };
  document.getElementById('vb-pic').onchange = e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = () => { V.face = r.result; V.frames = null; V.box = null; document.getElementById('vb-img').src = r.result; boxDrag(); }; r.readAsDataURL(f); };
  document.getElementById('vb-run').onclick = run;
  document.getElementById('vb-clear').onclick = async () => { if (!G.identity) return askWho(); const r = await post('voice_clear', { game: gid() }); toast(r.message, r.ok); loadVoiceBench(); };
  document.querySelectorAll('[data-lock]').forEach(b => b.onclick = async () => { if (!G.identity) return askWho(); const r = await post('voice_card_lock', { game: gid(), id: b.dataset.lock, by_person: true }); toast(r.message, r.ok); loadVoiceBench(); });
}

function boxDrag() {
  const img = document.getElementById('vb-img'), st = document.getElementById('vb-stage');
  let a = null, el = null;
  img.onmousedown = e => { e.preventDefault(); const r = img.getBoundingClientRect(); a = [e.clientX - r.left, e.clientY - r.top]; if (el) el.remove(); el = document.createElement('div'); el.style.cssText = 'position:absolute;border:2px dashed #ffdc00;pointer-events:none'; st.appendChild(el); };
  img.onmousemove = e => { if (!a) return; const r = img.getBoundingClientRect(); const b = [e.clientX - r.left, e.clientY - r.top]; Object.assign(el.style, { left: Math.min(a[0], b[0]) + 'px', top: Math.min(a[1], b[1]) + 'px', width: Math.abs(b[0] - a[0]) + 'px', height: Math.abs(b[1] - a[1]) + 'px' }); };
  img.onmouseup = async e => { if (!a) return; const r = img.getBoundingClientRect(); const b = [e.clientX - r.left, e.clientY - r.top]; const k = img.naturalWidth / r.width;
    V.box = [Math.min(a[0], b[0]) * k, Math.min(a[1], b[1]) * k, Math.max(a[0], b[0]) * k, Math.max(a[1], b[1]) * k]; a = null;
    const res = await post('voice_standin', { game: gid(), picture: V.face, box: V.box }); if (res.ok) { V.frames = res.frames; document.getElementById('vb-avail').textContent = 'stand-in shapes: ' + Object.keys(res.frames).join(' '); img.src = res.frames.X; } else toast(res.message, false); };
}

async function run() {
  const line = document.getElementById('vb-line').value.trim(); if (!line) return toast('Write the line first.', false);
  const body = { game: gid(), line, for: document.getElementById('vb-for').value, mood: document.getElementById('vb-mood').value, language: document.getElementById('vb-lang').value,
    engine: document.getElementById('vb-eng').value, use_card: document.getElementById('vb-usecard').checked, offset: V.offset, blend: V.blend,
    available: V.frames ? Object.keys(V.frames) : null };
  const cut = document.getElementById('vb-cut').value, sm = document.getElementById('vb-sample').value, f = document.getElementById('vb-file').files[0];
  if (body.engine === 'file') {
    if (cut) { body.from = 'cuts'; body.sound = cut; } else if (sm) { body.from = 'samples'; body.sound = sm; }
    else if (f) { body.sound = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(f); }); body.ext = '.' + f.name.split('.').pop(); }
    else return toast('Choose a recording, or an engine.', false);
  }
  document.getElementById('vb-test').textContent = 'working… (the mouth by both methods, then the words)';
  const r = await post('voice_take', body); if (!r.ok) { document.getElementById('vb-test').textContent = r.message; return; }
  V.take = r.take; V.lanes = r.take.face_lanes; V.laneOn = V.lanes.rhubarb ? 'rhubarb' : 'loud'; paintTest();
}

function paintTest() {
  const t = V.take, box = document.getElementById('vb-test');
  const dur = Math.max(t.duration, 0.1);
  const laneHtml = Object.entries(V.lanes).map(([k, rows]) => { let s = '', prev = null, st = 0;
    rows.forEach((r, i) => { const sh = r.to; if (sh !== prev || i === rows.length - 1) { if (prev !== null) s += `<span style="left:${st / dur * 100}%;width:${(r.t - st) / dur * 100}%;background:${SC[prev]}">${prev}</span>`; prev = sh; st = r.t; } });
    return `<div class="t3-from">${esc(k)}${k === 'loud' ? ' — loudness' : k === 'rhubarb' ? ' — Rhubarb' : ''}</div><div class="vb-lane ${k === V.laneOn ? 'on' : ''}" data-l="${esc(k)}">${s}<div class="vb-head"></div></div>`; }).join('');
  const env = t.envelope || [];
  const w = (t.heard && t.heard.words) || [];
  const bad = new Set(((t.words || {}).differ || []).flatMap(x => (x.heard || '').split(' ')));
  box.innerHTML = `<div style="display:flex;gap:14px;flex-wrap:wrap"><div><div class="vb-stage" style="width:${V.frames ? 260 : 0}px"><img id="vb-face" style="width:260px"></div>
      <div class="vb-stage" style="width:${V.frames ? 520 : 0}px;margin-top:6px"><img id="vb-face2" style="width:520px"></div></div>
    <div style="flex:1;min-width:360px"><canvas id="vb-wave" width="900" height="60" style="width:100%;background:#15151b;border-radius:4px"></canvas>${laneHtml}
      <div class="vb-words">${w.map(x => `<span class="${bad.has(x.w.toLowerCase().replace(/[^a-z0-9']/g, '')) ? 'bad' : ''}">${esc(x.w)}</span>`).join('') || `<span>${t.words === null ? 'words not checked (' + esc(t.checks.whisper || '') + ')' : ''}</span>`}</div>
      <div class="t3-from">${t.words ? (t.words.match ? '✓ the words match' : '✗ the words differ: ' + esc(t.words.differ.map(x => `“${x.said}” → “${x.heard}”`).join('; '))) : ''}</div>
      <div><button class="vb-btn go" id="vb-play">▶ Play</button><button class="vb-btn" id="vb-half">½ speed</button>
        <label class="t3-from"> offset <input type="range" id="vb-off" min="-200" max="200" step="10" value="${V.offset * 1000}"> <b id="vb-offv">${Math.round(V.offset * 1000)} ms</b></label>
        <label class="t3-from"> blend <input type="range" id="vb-bl" min="0" max="150" step="10" value="${V.blend * 1000}"> <b id="vb-blv">${Math.round(V.blend * 1000)} ms</b></label></div>
      <div style="margin-top:6px">${V.d.verdicts.map(m => `<button class="vb-btn" data-v="${esc(m)}">${esc(m)}</button>`).join('')} <input id="vb-note" placeholder="a note"></div></div></div>`;
  const cv = document.getElementById('vb-wave').getContext('2d'); cv.fillStyle = '#9cd2ff';
  env.forEach((e, i) => { const x = i / env.length * 900, h = e * 58; cv.fillRect(x, 30 - h / 2, Math.max(1, 900 / env.length), h); });
  document.querySelectorAll('.vb-lane').forEach(l => l.onclick = () => { V.laneOn = l.dataset.l; paintTest(); });
  const relane = async () => { const r = await post('voice_lanes', { game: gid(), folder: t.folder, offset: V.offset, blend: V.blend, available: V.frames ? Object.keys(V.frames) : null }); if (r.ok) { V.lanes = r.lanes; paintTest(); } };
  document.getElementById('vb-off').onchange = e => { V.offset = +e.target.value / 1000; relane(); };
  document.getElementById('vb-off').oninput = e => document.getElementById('vb-offv').textContent = e.target.value + ' ms';
  document.getElementById('vb-bl').onchange = e => { V.blend = +e.target.value / 1000; relane(); };
  document.getElementById('vb-play').onclick = () => play(1);
  document.getElementById('vb-half').onclick = () => play(0.5);
  document.querySelectorAll('[data-v]').forEach(b => b.onclick = async () => { if (!G.identity) return askWho();
    const r = await post('voice_verdict', { game: gid(), folder: t.folder, marks: [b.dataset.v], note: document.getElementById('vb-note').value }); toast(r.ok ? 'Written down.' : r.message, r.ok); });
  showFrame(0);
}

function showFrame(t) {
  if (!V.frames || !V.lanes) return;
  const rows = V.lanes[V.laneOn] || []; const i = Math.min(rows.length - 1, Math.max(0, Math.round(t * 30)));
  const r = rows[i] || { to: 'X', frame_to: 'X' }; const src = V.frames[r.frame_to || r.to] || V.frames.X;
  const a = document.getElementById('vb-face'), b = document.getElementById('vb-face2'); if (a) a.src = src; if (b) b.src = src;
  const dur = Math.max(V.take.duration, 0.1); document.querySelectorAll('.vb-head').forEach(h => h.style.left = (t / dur * 100) + '%');
}

function play(rate) {
  if (V.audio) { V.audio.pause(); cancelAnimationFrame(V.raf); }
  const url = '/suite/voicefile?id=' + encodeURIComponent(gid()) + '&p=' + encodeURIComponent(V.take.folder + '/' + V.take.sound);
  V.audio = new Audio(url); V.audio.playbackRate = rate; V.audio.play();
  const tick = () => { showFrame(V.audio.currentTime); if (!V.audio.paused) V.raf = requestAnimationFrame(tick); }; tick();
}

window.loadVoiceBench = loadVoiceBench;
})();
