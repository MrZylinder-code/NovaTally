/* Spielzeit – Oberfläche (Vanilla JS, eigene SVG-Diagramme, keine externen Bibliotheken). */
'use strict';

/* ================================================================ Grundlagen */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const main = $('#main');
const params = new URLSearchParams(location.search);

const state = {
  status: null,
  range: load('range', '30'),
  gamesSort: load('gamesSort', 'time'),
  gamesQuery: '',
  historyLimit: 300,
  redraw: null,        // zeichnet die Diagramme der aktuellen Ansicht neu (Größe/Thema)
  pageTimer: null,     // periodische Aktualisierung der aktuellen Ansicht
  route: '',
  serverOffset: 0,     // Serverzeit - Browserzeit (Sekunden)
};

function load(key, fallback) {
  try { return localStorage.getItem('spielzeit.' + key) || fallback; } catch (e) { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem('spielzeit.' + key, value); } catch (e) { /* egal */ }
}

async function api(path, body) {
  const opts = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Spielzeit': '1' } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/' + path, opts);
  const isJson = (res.headers.get('Content-Type') || '').includes('json');
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || ('Fehler ' + res.status));
  return data;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ================================================================ Formate */
const WD = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const MON = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
const MON_LONG = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const nf1 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });

function nowSec() { return Date.now() / 1000 + state.serverOffset; }

function fmtDur(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(sec / 60);
  if (m < 1) return sec > 0 ? '< 1 Min' : '0 Min';
  const h = Math.floor(m / 60), mm = m % 60;
  if (!h) return `${mm} Min`;
  return mm ? `${nf0.format(h)} Std ${mm} Min` : `${nf0.format(h)} Std`;
}
function fmtHours(sec) { return nf1.format((sec || 0) / 3600) + ' Std'; }
function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = sec % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
function pad(n) { return String(n).padStart(2, '0'); }
function parseDay(iso) { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); }
function fmtDay(date, withYear) {
  const y = withYear || date.getFullYear() !== new Date().getFullYear();
  return `${WD[date.getDay()]}, ${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${y ? date.getFullYear() : ''}`;
}
function fmtTime(ts) { const d = new Date(ts * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; }
function fmtDate(ts, withYear) { return fmtDay(new Date(ts * 1000), withYear); }
function fmtDateShort(ts) { const d = new Date(ts * 1000); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`; }
function dayKey(date) { return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`; }
function relDay(ts) {
  if (!ts) return 'noch nie';
  const d = new Date(ts * 1000); d.setHours(0, 0, 0, 0);
  const t = new Date(); t.setHours(0, 0, 0, 0);
  const diff = Math.round((t - d) / 86400000);
  if (diff <= 0) return 'heute';
  if (diff === 1) return 'gestern';
  if (diff < 7) return `vor ${diff} Tagen`;
  return fmtDate(ts);
}
function kpiHtml(sec) {
  const m = Math.floor((sec || 0) / 60), h = Math.floor(m / 60), mm = m % 60;
  if (h >= 100) return `${nf0.format(h)}<small>Std</small>`;
  if (!h) return `${mm}<small>Min</small>`;
  return `${h}<small>Std</small> ${mm}<small>Min</small>`;
}

/* ================================================================ Farben & Cover */
function seriesColor(slot) { return slot ? `var(--s${slot})` : 'var(--s-other)'; }

function hashStr(s) { let h = 2166136261; for (const c of String(s)) { h ^= c.codePointAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
function initials(name) {
  let words = String(name).replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return '?';
  const caps = words.filter(w => /^[\p{Lu}\p{N}]/u.test(w));  // „of“, „the“ … überspringen
  if (caps.length) words = caps;
  return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}
function placeholderStyle(name) {
  const h = hashStr(name) % 360, h2 = (h + 50) % 360;
  return `background: linear-gradient(135deg, hsl(${h} 62% 46%), hsl(${h2} 58% 24%))`;
}
function coverUrl(game) {
  return game && game.appid && /^\d+$/.test(String(game.appid))
    ? `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.appid}/header.jpg` : null;
}
/** Cover mit Platzhalter darunter – fällt das Bild aus, bleibt der Platzhalter sichtbar. */
function coverHtml(game, cls = '') {
  const url = coverUrl(game);
  return `<div class="cover ${cls}"><div class="ph" style="${placeholderStyle(game.name)}">${esc(initials(game.name))}</div>` +
    (url ? `<img src="${url}" alt="" loading="lazy" data-cover style="position:absolute;inset:0">` : '') + '</div>';
}
function bgHtml(game) {
  const url = coverUrl(game);
  return `<div class="bg"><div class="ph" style="${placeholderStyle(game.name)}"></div>` +
    (url ? `<img src="${url}" alt="" data-cover style="position:absolute;inset:0">` : '') + '</div>';
}
function wireCovers(root = document) {
  for (const img of $$('img[data-cover]', root)) {
    const fail = () => img.remove();
    if (img.complete && img.naturalWidth === 0 && img.src) { fail(); continue; }
    img.addEventListener('error', fail, { once: true });
  }
}

/* ================================================================ Tooltip */
const tipEl = $('#tooltip');
const tip = {
  show(html, ev) { tipEl.innerHTML = html; tipEl.classList.add('show'); tip.move(ev); },
  move(ev) {
    if (!ev) return;
    const pad = 14, r = tipEl.getBoundingClientRect();
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
    tipEl.style.left = Math.max(8, x) + 'px';
    tipEl.style.top = Math.max(8, y) + 'px';
  },
  hide() { tipEl.classList.remove('show'); },
};
function bindTip(el, htmlFn) {
  el.addEventListener('mouseenter', ev => tip.show(htmlFn(), ev));
  el.addEventListener('mousemove', ev => tip.move(ev));
  el.addEventListener('mouseleave', () => tip.hide());
}
function ttRow(color, label, value) {
  return `<div class="tt-row"><span>${color ? `<i style="background:${color}"></i>` : ''}${esc(label)}</span><b>${esc(value)}</b></div>`;
}

/* ================================================================ Modal & Toast */
const modal = $('#modal');
function openModal({ title, text = '', value = null, okLabel = 'OK', danger = false }) {
  $('#modal-title').textContent = title;
  $('#modal-text').textContent = text;
  $('#modal-text').style.display = text ? '' : 'none';
  const input = $('#modal-input');
  input.style.display = value === null ? 'none' : '';
  input.value = value || '';
  const ok = $('#modal-ok');
  ok.textContent = okLabel;
  ok.className = 'btn ' + (danger ? 'danger' : 'primary');
  modal.returnValue = '';
  return new Promise(resolve => {
    const onKey = ev => { if (ev.key === 'Enter') { ev.preventDefault(); modal.close('ok'); } };
    input.addEventListener('keydown', onKey);
    modal.addEventListener('close', () => {
      input.removeEventListener('keydown', onKey);
      const okd = modal.returnValue === 'ok';
      resolve(value === null ? okd : (okd ? input.value.trim() : null));
    }, { once: true });
    modal.showModal();
    if (value !== null) { input.focus(); input.select(); } else ok.focus();
  });
}
let toastTimer = null;
function toast(msg, error = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('error', error);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; }
  catch (e) { toast(e.message || String(e), true); return undefined; }
}

/* ================================================================ Diagramme */
function niceStep(maxHours, targetTicks = 4) {
  const steps = [0.25, 0.5, 1, 2, 3, 4, 5, 10, 15, 20, 25, 50, 100, 150, 200, 250, 500, 1000, 2000, 5000];
  for (const s of steps) if (maxHours / s <= targetTicks) return s;
  return Math.ceil(maxHours / targetTicks);
}
function hourLabel(h) {
  if (h === 0) return '0';
  if (h < 1) return `${Math.round(h * 60)} Min`;
  return `${nf0.format(h)} Std`;
}
/** Balken mit abgerundetem Datenende (oben, 4 px) und gerader Grundlinie. */
function barPath(x, y, w, h, r = 4) {
  r = Math.max(0, Math.min(r, w / 2, h));
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
/** Gemeinsames Gerüst für Säulendiagramme: Raster + Achse. Gibt Skalen zurück. */
function frame(width, height, maxSec, m) {
  const maxH = Math.max(maxSec / 3600, 0.5);
  const step = niceStep(maxH);
  const top = Math.ceil(maxH / step) * step;
  const pw = width - m.l - m.r, ph = height - m.t - m.b;
  const y = sec => m.t + ph - (sec / 3600) / top * ph;
  let grid = '';
  for (let v = 0; v <= top + 1e-9; v += step) {
    const yy = Math.round(y(v * 3600)) + 0.5;
    grid += `<line class="${v === 0 ? 'baseline' : 'gridline'}" x1="${m.l}" x2="${width - m.r}" y1="${yy}" y2="${yy}"/>` +
      `<text class="axis" x="${m.l - 8}" y="${yy + 4}" text-anchor="end">${hourLabel(v)}</text>`;
  }
  return { pw, ph, y, grid };
}

function stackedChart(el, hist) {
  const width = Math.max(320, el.clientWidth), height = 270;
  const m = { l: 56, r: 6, t: 10, b: 28 };
  const n = hist.buckets.length;
  const totals = hist.buckets.map(b => b.values.reduce((a, v) => a + v, 0));
  const { pw, y, grid } = frame(width, height, Math.max(...totals, 0), m);
  const band = pw / n;
  const bw = Math.max(2, Math.min(band * 0.62, 30));
  const base = y(0);
  let bars = '', hits = '', labels = '';
  hist.buckets.forEach((b, i) => {
    const x = m.l + i * band + (band - bw) / 2;
    let cur = base;
    const segs = b.values.map((v, si) => ({ v, si })).filter(s => s.v > 0);
    segs.forEach((s, k) => {
      const h = base - y(s.v);
      const isTop = k === segs.length - 1;
      const gap = isTop ? 0 : Math.min(2, h / 2);
      const top = cur - h;
      const color = seriesColor(hist.series[s.si].slot);
      bars += isTop
        ? `<path d="${barPath(x, top, bw, h)}" style="fill:${color}"/>`
        : `<rect x="${x}" y="${top + gap}" width="${bw}" height="${Math.max(0, h - gap)}" style="fill:${color}"/>`;
      cur = top;
    });
    hits += `<rect class="hit" data-i="${i}" x="${m.l + i * band}" y="${m.t}" width="${band}" height="${base - m.t}"/>`;
  });
  // Beschriftung der x-Achse
  const d0 = hist.buckets.map(b => parseDay(b.start));
  const maxLabels = Math.max(2, Math.floor(pw / 70));
  if (hist.unit === 'week') {
    let lastX = -999;
    d0.forEach((d, i) => {
      const end = new Date(d); end.setDate(d.getDate() + 6);
      if (end.getMonth() !== d.getMonth() || d.getDate() === 1 || i === 0) {
        const md = end.getMonth() !== d.getMonth() ? end : d;
        const x = m.l + i * band + band / 2;
        if (x - lastX < 42) return;
        lastX = x;
        labels += `<text class="axis" x="${x}" y="${height - 8}" text-anchor="middle">${MON[md.getMonth()]}</text>`;
      }
    });
  } else {
    const step = Math.ceil(n / maxLabels);
    d0.forEach((d, i) => {
      if ((n - 1 - i) % step !== 0) return;
      const x = m.l + i * band + band / 2;
      let t;
      if (hist.unit === 'month') t = `${MON[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`;
      else if (n <= 7) t = `${WD[d.getDay()]} ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`;
      else t = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`;
      labels += `<text class="axis" x="${x}" y="${height - 8}" text-anchor="middle">${t}</text>`;
    });
  }
  el.innerHTML = `<svg width="${width}" height="${height}" role="img" aria-label="Spielzeit-Verlauf">${grid}${bars}${labels}${hits}</svg>`;
  $$('.hit', el).forEach(r => bindTip(r, () => {
    const i = +r.dataset.i, b = hist.buckets[i], d = d0[i];
    let title;
    if (hist.unit === 'day') title = fmtDay(d, true);
    else if (hist.unit === 'week') { const e = new Date(d); e.setDate(d.getDate() + 6); title = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}. – ${pad(e.getDate())}.${pad(e.getMonth() + 1)}.${e.getFullYear()}`; }
    else title = `${MON_LONG[d.getMonth()]} ${d.getFullYear()}`;
    const rows = hist.series.map((s, si) => ({ s, v: b.values[si] })).filter(x => x.v > 0).reverse();
    if (!rows.length) return `<div class="tt-title">${esc(title)}</div><div class="muted">Nicht gespielt</div>`;
    return `<div class="tt-title">${esc(title)}</div>` +
      rows.map(x => ttRow(seriesColor(x.s.slot), x.s.name, fmtDur(x.v))).join('') +
      (rows.length > 1 ? `<div class="tt-total">${ttRow(null, 'Gesamt', fmtDur(totals[i]))}</div>` : '');
  }));
}

function simpleBars(el, values, opts) {
  const width = Math.max(260, el.clientWidth), height = opts.height || 220;
  const m = { l: 56, r: 6, t: 10, b: 28 };
  const n = values.length;
  const { pw, y, grid } = frame(width, height, Math.max(...values, 0), m);
  const band = pw / n, bw = Math.max(2, Math.min(band * 0.62, opts.maxBar || 26));
  const base = y(0);
  let bars = '', hits = '', labels = '';
  values.forEach((v, i) => {
    const x = m.l + i * band + (band - bw) / 2;
    if (v > 0) bars += `<path d="${barPath(x, y(v), bw, base - y(v))}" style="fill:${opts.color}"/>`;
    hits += `<rect class="hit" data-i="${i}" x="${m.l + i * band}" y="${m.t}" width="${band}" height="${base - m.t}"/>`;
    const lab = opts.label(i);
    if (lab) labels += `<text class="axis" x="${m.l + i * band + band / 2}" y="${height - 8}" text-anchor="middle">${lab}</text>`;
  });
  el.innerHTML = `<svg width="${width}" height="${height}" role="img" aria-label="${esc(opts.aria)}">${grid}${bars}${labels}${hits}</svg>`;
  $$('.hit', el).forEach(r => bindTip(r, () => opts.tooltip(+r.dataset.i)));
}

function heatLevel(sec) {
  if (sec <= 0) return 0;
  if (sec < 1800) return 1;
  if (sec < 5400) return 2;
  if (sec < 10800) return 3;
  if (sec < 18000) return 4;
  return 5;
}
function heatmap(el, heat, todayIso) {
  const width = Math.max(320, el.clientWidth);
  const cols = Math.ceil(heat.days.length / 7);
  const left = 28, topPad = 20, gap = 3;
  const cell = Math.max(7, Math.min(17, Math.floor((width - left) / cols) - gap));
  const height = topPad + 7 * (cell + gap);
  const start = parseDay(heat.start);
  let cells = '', months = '', lastMonth = -1, lastX = -99;
  heat.days.forEach((sec, i) => {
    const c = Math.floor(i / 7), r = i % 7;
    const d = new Date(start); d.setDate(start.getDate() + i);
    const x = left + c * (cell + gap), yy = topPad + r * (cell + gap);
    cells += `<rect class="hc" data-i="${i}" x="${x}" y="${yy}" width="${cell}" height="${cell}" rx="${Math.min(3, cell / 4)}" style="fill:var(--h${heatLevel(sec)})"/>`;
    if (r === 0 && d.getMonth() !== lastMonth) {
      // Monatslabel an der ersten Woche, die (überwiegend) im neuen Monat liegt
      if (x - lastX > 30 && (i > 0 || d.getDate() <= 7)) {
        months += `<text class="axis" x="${x}" y="12">${MON[d.getMonth()]}</text>`;
        lastX = x;
      }
      lastMonth = d.getMonth();
    }
  });
  const wd = ['Mo', '', 'Mi', '', 'Fr', '', ''].map((t, r) => t ? `<text class="axis" x="0" y="${topPad + r * (cell + gap) + cell - 1}">${t}</text>` : '').join('');
  const svgW = left + cols * (cell + gap);
  el.innerHTML = `<svg width="${svgW}" height="${height}" role="img" aria-label="Aktivitäts-Kalender">${months}${wd}${cells}</svg>`;
  $$('.hc', el).forEach(r => bindTip(r, () => {
    const i = +r.dataset.i, d = new Date(start); d.setDate(start.getDate() + i);
    const sec = heat.days[i];
    return `<div class="tt-title">${esc(fmtDay(d, true))}</div><div>${sec > 0 ? esc(fmtDur(sec)) : '<span class="muted">Nicht gespielt</span>'}</div>`;
  }));
}

/* ================================================================ Status & Seitenleiste */
async function refreshStatus() {
  try {
    const s = await api('status');
    state.serverOffset = s.now - Date.now() / 1000;
    state.status = s;
    const el = $('#sidebar-status');
    el.className = 'sidebar-status ' + (s.demo ? 'demo' : !s.tracking ? 'off' : s.paused ? 'paused' : 'on');
    $('.label', el).textContent = s.demo ? 'Demo-Modus' : !s.tracking ? 'Erkennung aus' : s.paused ? 'Tracking pausiert' : 'Tracking aktiv';
    el.title = s.tracker_note || '';
    applyTheme(s.theme);
    const nowCard = $('#now-card');
    if (nowCard) renderNowCard(nowCard);
  } catch (e) {
    const el = $('#sidebar-status');
    el.className = 'sidebar-status off';
    $('.label', el).textContent = 'Keine Verbindung';
  }
}
function applyTheme(theme) {
  const t = params.get('theme') || theme || 'dark';
  if (document.documentElement.dataset.theme !== t) {
    document.documentElement.dataset.theme = t;
    if (state.redraw) state.redraw();
  }
}
function tickTimers() {
  for (const el of $$('[data-since]')) el.textContent = fmtClock(nowSec() - Number(el.dataset.since));
}

/* ================================================================ Router */
const routes = {
  uebersicht: renderOverview,
  spiele: arg => (arg ? renderGame(arg) : renderGames()),
  verlauf: renderHistory,
  einstellungen: renderSettings,
};
async function route() {
  const [page, arg] = (location.hash.replace(/^#\/?/, '') || 'uebersicht').split('/');
  const fn = routes[page] || routes.uebersicht;
  state.redraw = null;
  clearInterval(state.pageTimer);
  state.pageTimer = null;
  tip.hide();
  for (const a of $$('.nav a')) a.classList.toggle('active', a.dataset.route === (routes[page] ? page : 'uebersicht'));
  const key = location.hash;
  state.route = key;
  try {
    await fn(arg);
  } catch (e) {
    if (state.route === key) main.innerHTML = `<div class="page"><div class="card empty">Konnte nicht geladen werden: ${esc(e.message)}</div></div>`;
  }
}
function isCurrent(key) { return state.route === key; }

/* ================================================================ Übersicht */
function renderNowCard(el) {
  const s = state.status;
  if (!s) return;
  const run = s.running && s.running[0];
  const key = run ? `run:${run.session_id}:${run.name}` : `last:${s.last ? s.last.id + ':' + s.last.end + ':' + s.last.name : 'none'}`;
  if (el.dataset.key === key) return;  // nichts geändert -> Bilder nicht neu laden
  el.dataset.key = key;
  if (run) {
    const more = s.running.length > 1 ? `<div class="now-more">außerdem: ${s.running.slice(1).map(r => esc(r.name)).join(', ')}</div>` : '';
    el.innerHTML = `${bgHtml(run)}<div class="now-inner">${coverHtml(run)}<div class="now-text">
      <div class="now-label"><span class="live"></span>Jetzt im Spiel</div>
      <a class="now-name" href="#/spiele/${run.id}">${esc(run.name)}</a>
      <div class="now-timer" data-since="${run.start}">${fmtClock(nowSec() - run.start)}</div>
      <div class="now-sub">gestartet um ${fmtTime(run.start)} Uhr</div>${more}</div></div>`;
  } else if (s.last) {
    const l = s.last;
    el.innerHTML = `${bgHtml(l)}<div class="now-inner">${coverHtml(l)}<div class="now-text">
      <div class="now-label">Zuletzt gespielt</div>
      <a class="now-name" href="#/spiele/${l.id}">${esc(l.name)}</a>
      <div class="now-sub">${esc(relDay(l.end))} · ${fmtTime(l.start)}–${fmtTime(l.end)} Uhr · ${esc(fmtDur(l.end - l.start))}</div>
      <div class="now-sub">${s.paused ? 'Tracking ist pausiert.' : 'Starte ein Spiel – es wird automatisch erkannt.'}</div></div></div>`;
  } else {
    el.innerHTML = `<div class="now-inner"><div class="now-text">
      <div class="now-label">Noch keine Spielzeit</div>
      <div class="now-name">Starte ein Spiel!</div>
      <div class="now-sub">Spielzeit läuft im Hintergrund und erkennt Spiele aus Steam, Epic, GOG, Ubisoft, Xbox und mehr automatisch.</div></div></div>`;
  }
  wireCovers(el);
}

const RANGES = [['7', '7 T'], ['30', '30 T'], ['90', '90 T'], ['365', '1 J'], ['all', 'Gesamt']];

async function renderOverview() {
  const key = location.hash;
  const [o] = await Promise.all([api('overview?range=' + state.range), state.status ? null : refreshStatus()]);
  if (!isCurrent(key)) return;
  const s = state.status || {};
  const today = new Date();
  const longest = o.longest_session;
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Übersicht</h1><div class="sub">${esc(fmtDay(today, true))}</div></div></div>
    ${s.tracker_note ? `<div class="banner">ℹ️ ${esc(s.tracker_note)}</div>` : ''}
    <div class="hero">
      <div class="card now-card" id="now-card"></div>
      <div class="kpis">
        <div class="card kpi"><div class="label">Heute</div><div class="value">${kpiHtml(o.kpis.today)}</div></div>
        <div class="card kpi"><div class="label">Diese Woche</div><div class="value">${kpiHtml(o.kpis.week)}</div></div>
        <div class="card kpi"><div class="label">Dieser Monat</div><div class="value">${kpiHtml(o.kpis.month)}</div></div>
        <div class="card kpi"><div class="label">Gesamt</div><div class="value">${kpiHtml(o.kpis.total)}</div></div>
      </div>
    </div>
    <div class="facts">
      <div class="card fact"><div class="label">Aktuelle Serie</div><div class="value">${o.streak.current} ${o.streak.current === 1 ? 'Tag' : 'Tage'}</div><div class="hint">am Stück gespielt</div></div>
      <div class="card fact"><div class="label">Längste Serie</div><div class="value">${o.streak.longest} ${o.streak.longest === 1 ? 'Tag' : 'Tage'}</div><div class="hint">Rekord</div></div>
      <div class="card fact"><div class="label">Längste Sitzung</div><div class="value">${longest ? esc(fmtDur(longest.seconds)) : '–'}</div><div class="hint">${longest ? esc(longest.game.name) + ' · ' + esc(fmtDate(longest.start)) : '&nbsp;'}</div></div>
      <div class="card fact"><div class="label">Spiele</div><div class="value">${nf0.format(o.games)}</div><div class="hint">mit Spielzeit</div></div>
      <div class="card fact"><div class="label">Sitzungen</div><div class="value">${nf0.format(o.sessions)}</div><div class="hint">insgesamt</div></div>
    </div>
    <div class="toolbar">
      <div class="seg" id="range">${RANGES.map(([v, l]) => `<button data-v="${v}" class="${String(o.range) === v ? 'active' : ''}">${l}</button>`).join('')}</div>
      <div class="meta">${esc(fmtDur(o.range_total))} im Zeitraum · an ${o.active_days} von ${o.range_days} Tagen gespielt · Ø ${esc(fmtDur(o.range_total / Math.max(1, o.range_days)))} pro Tag</div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Spielzeit-Verlauf</h2><div class="meta">${{ day: 'pro Tag', week: 'pro Woche', month: 'pro Monat' }[o.history.unit]}</div></div>
      <div class="chart" id="chart-history"></div>
      <div class="legend">${o.history.series.map(x => `<span><i style="background:${seriesColor(x.slot)}"></i>${esc(x.name)}</span>`).join('')}</div>
    </div>
    <div class="grid-2">
      <div class="card"><div class="card-head"><h2>Top-Spiele</h2><div class="meta">im Zeitraum</div></div><div class="top-list" id="top-list"></div></div>
      <div class="card"><div class="card-head"><h2>Wann spielst du?</h2><div class="meta">nach Uhrzeit, im Zeitraum</div></div><div class="chart" id="chart-hours"></div></div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Aktivität</h2>
        <div class="heat-legend"><span class="l">weniger</span>${[0, 1, 2, 3, 4, 5].map(l => `<i style="background:var(--h${l})"></i>`).join('')}<span class="l">mehr</span></div></div>
      <div class="chart" id="chart-heat"></div>
    </div>
  </div>`;

  renderNowCard($('#now-card'));
  // Top-Spiele
  const top = $('#top-list');
  const maxTop = Math.max(1, ...o.top.map(g => g.seconds));
  top.innerHTML = o.top.length ? o.top.map((g, i) => `<a class="top-row" href="#/spiele/${g.id}" data-i="${i}">
      ${coverHtml(g, 'thumb')}
      <div style="min-width:0"><div class="name">${esc(g.name)}</div><div class="bar" style="width:${(g.seconds / maxTop * 100).toFixed(1)}%;background:${seriesColor(g.slot)}"></div></div>
      <div class="val">${esc(fmtDur(g.seconds))}</div></a>`).join('')
    : '<div class="empty">In diesem Zeitraum wurde nicht gespielt.</div>';
  wireCovers(top);
  $$('.top-row', top).forEach(row => bindTip(row, () => {
    const g = o.top[+row.dataset.i];
    return `<div class="tt-title">${esc(g.name)}</div>${ttRow(seriesColor(g.slot), 'Spielzeit', fmtDur(g.seconds))}` +
      ttRow(null, 'Anteil', nf0.format(g.seconds / Math.max(1, o.range_total) * 100) + ' %');
  }));

  $$('#range button').forEach(b => b.addEventListener('click', () => {
    state.range = b.dataset.v; save('range', state.range); renderOverview();
  }));

  state.redraw = () => {
    if (!$('#chart-history')) return;
    stackedChart($('#chart-history'), o.history);
    simpleBars($('#chart-hours'), o.hours, {
      color: 'var(--s1)', aria: 'Spielzeit nach Uhrzeit', height: Math.max(220, top.clientHeight - 4),
      label: i => (i % 3 === 0 ? String(i) : ''),
      tooltip: i => `<div class="tt-title">${i}–${i + 1} Uhr</div><div>${esc(fmtDur(o.hours[i]))}</div>`,
    });
    heatmap($('#chart-heat'), o.heatmap, o.today);
  };
  state.redraw();
  clearInterval(state.pageTimer);
  state.pageTimer = setInterval(() => { if (isCurrent(key) && !document.hidden) renderOverview(); }, 60000);
}

/* ================================================================ Spiele */
const SORTS = [['time', 'Spielzeit'], ['last', 'Zuletzt gespielt'], ['name', 'Name']];
async function renderGames() {
  const key = location.hash;
  const games = await api('games');
  if (!isCurrent(key)) return;
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Spiele</h1><div class="sub">${games.length} ${games.length === 1 ? 'Spiel' : 'Spiele'} mit Spielzeit</div></div>
      <div class="games-tools">
        <input class="input" id="search" type="search" placeholder="Spiel suchen …" value="${esc(state.gamesQuery)}">
        <div class="seg" id="sort">${SORTS.map(([v, l]) => `<button data-v="${v}" class="${state.gamesSort === v ? 'active' : ''}">${l}</button>`).join('')}</div>
      </div></div>
    <div class="games-grid" id="games-grid"></div></div>`;
  const grid = $('#games-grid');
  const draw = () => {
    const q = state.gamesQuery.trim().toLowerCase();
    const list = games.filter(g => !q || g.name.toLowerCase().includes(q));
    const cmp = {
      time: (a, b) => b.seconds - a.seconds,
      last: (a, b) => (b.last || 0) - (a.last || 0),
      name: (a, b) => a.name.localeCompare(b.name, 'de'),
    }[state.gamesSort];
    list.sort(cmp);
    grid.innerHTML = list.length ? list.map(g => `<a class="card tile" href="#/spiele/${g.id}">
        ${coverHtml(g)}
        <div class="body"><div class="name" title="${esc(g.name)}">${esc(g.name)}</div>
          <div class="row"><div class="hours">${esc(fmtHours(g.seconds))}</div>
          <div class="last"><span class="swatch" style="background:${seriesColor(g.slot)}"></span>${esc(relDay(g.last))}</div></div>
        </div></a>`).join('')
      : `<div class="card empty" style="grid-column:1/-1">${games.length ? 'Kein Spiel passt zur Suche.' : 'Noch keine Spiele erfasst. Starte ein Spiel – Spielzeit erkennt es automatisch.'}</div>`;
    wireCovers(grid);
  };
  draw();
  $('#search').addEventListener('input', e => { state.gamesQuery = e.target.value; draw(); });
  $$('#sort button').forEach(b => b.addEventListener('click', () => {
    state.gamesSort = b.dataset.v; save('gamesSort', b.dataset.v);
    $$('#sort button').forEach(x => x.classList.toggle('active', x === b));
    draw();
  }));
}

const SOURCE_LABELS = {
  steam: 'Steam', epic: 'Epic Games', gog: 'GOG', ubisoft: 'Ubisoft Connect', xbox: 'Xbox / Game Pass', ea: 'EA',
  riot: 'Riot Games', battlenet: 'Battle.net', folder: 'Spieleordner', custom: 'Eigener Ordner', manual: 'Manuell hinzugefügt',
};

async function renderGame(id) {
  const key = location.hash;
  const g = await api('game/' + encodeURIComponent(id));
  if (!isCurrent(key)) return;
  const color = seriesColor(g.slot);
  main.innerHTML = `<div class="page">
    <div><a class="back" href="#/spiele">← Alle Spiele</a></div>
    <div class="card detail-hero">${bgHtml(g)}<div class="detail-inner">${coverHtml(g)}
      <div class="detail-info">
        <div><span class="badge">${esc(SOURCE_LABELS[g.source] || g.source || 'Unbekannt')}</span>${g.ignored ? ' <span class="badge">ausgeblendet</span>' : ''}</div>
        <h1>${esc(g.name)}</h1>
        <div class="muted">${esc(fmtDur(g.seconds))} gespielt · zuletzt ${esc(relDay(g.last))}</div>
        <div class="detail-actions">
          <button class="btn small" id="btn-rename">Umbenennen</button>
          <button class="btn small" id="btn-ignore">${g.ignored ? 'Wieder einblenden' : 'Ausblenden'}</button>
        </div>
      </div></div></div>
    <div class="stat-grid">
      <div class="card fact"><div class="label">Gesamt</div><div class="value">${esc(fmtHours(g.seconds))}</div></div>
      <div class="card fact"><div class="label">Sitzungen</div><div class="value">${nf0.format(g.session_count)}</div></div>
      <div class="card fact"><div class="label">Ø Sitzung</div><div class="value">${esc(fmtDur(g.average))}</div></div>
      <div class="card fact"><div class="label">Längste Sitzung</div><div class="value">${esc(fmtDur(g.longest))}</div></div>
      <div class="card fact"><div class="label">Erstes Mal</div><div class="value">${g.first ? esc(fmtDateShort(g.first)) : '–'}</div></div>
      <div class="card fact"><div class="label">Zuletzt</div><div class="value">${g.last ? esc(fmtDateShort(g.last)) : '–'}</div></div>
    </div>
    <div class="card"><div class="card-head"><h2>Spielzeit pro Monat</h2><div class="meta">letzte 12 Monate</div></div><div class="chart" id="chart-months"></div></div>
    <div class="card"><div class="card-head"><h2>Sitzungen</h2><div class="meta">${g.session_count} insgesamt</div></div>
      ${g.sessions_list.length ? `<table class="table"><thead><tr><th>Datum</th><th>Uhrzeit</th><th class="r">Dauer</th><th class="act"></th></tr></thead><tbody>
      ${g.sessions_list.map(s => `<tr><td>${esc(fmtDate(s.start, true))}</td><td>${fmtTime(s.start)} – ${s.open ? '<span class="live-tag">läuft</span>' : fmtTime(s.end)}</td>
        <td class="r">${esc(fmtDur(s.end - s.start))}</td>
        <td class="act">${s.open ? '' : `<button class="icon-btn" data-del="${s.id}" title="Sitzung löschen" aria-label="Sitzung löschen">${TRASH}</button>`}</td></tr>`).join('')}
      </tbody></table>` : '<div class="empty">Keine Sitzungen.</div>'}
    </div></div>`;
  wireCovers(main);
  state.redraw = () => {
    const el = $('#chart-months');
    if (!el) return;
    simpleBars(el, g.months.map(x => x.seconds), {
      color, aria: 'Spielzeit pro Monat', height: 220, maxBar: 34,
      label: i => MON[parseDay(g.months[i].start).getMonth()],
      tooltip: i => { const d = parseDay(g.months[i].start); return `<div class="tt-title">${MON_LONG[d.getMonth()]} ${d.getFullYear()}</div><div>${esc(fmtDur(g.months[i].seconds))}</div>`; },
    });
  };
  state.redraw();
  $('#btn-rename').addEventListener('click', async () => {
    const name = await openModal({ title: 'Spiel umbenennen', value: g.name, okLabel: 'Speichern' });
    if (name && name !== g.name) { await act(() => api(`game/${g.id}/rename`, { name }), 'Umbenannt'); route(); }
  });
  $('#btn-ignore').addEventListener('click', async () => {
    if (!g.ignored) {
      const ok = await openModal({ title: 'Spiel ausblenden?', text: `„${g.name}“ wird nicht mehr erfasst und aus allen Statistiken ausgeblendet. Unter Einstellungen kannst du es wieder einblenden.`, okLabel: 'Ausblenden', danger: true });
      if (!ok) return;
    }
    await act(() => api(`game/${g.id}/ignore`, { ignored: !g.ignored }), g.ignored ? 'Wieder eingeblendet' : 'Ausgeblendet');
    if (g.ignored) route(); else location.hash = '#/spiele';
  });
  wireDeletes(main);
}

const TRASH = '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>';
function wireDeletes(root) {
  $$('[data-del]', root).forEach(b => b.addEventListener('click', async ev => {
    ev.preventDefault();
    const ok = await openModal({ title: 'Sitzung löschen?', text: 'Die Sitzung wird endgültig aus der Statistik entfernt.', okLabel: 'Löschen', danger: true });
    if (!ok) return;
    const r = await act(() => api(`session/${b.dataset.del}/delete`, {}), 'Sitzung gelöscht');
    if (r) route();
  }));
}

/* ================================================================ Verlauf */
async function renderHistory() {
  const key = location.hash;
  const sessions = await api('sessions?limit=' + state.historyLimit);
  if (!isCurrent(key)) return;
  const groups = [];
  for (const s of sessions) {
    const k = dayKey(new Date(s.start * 1000));
    let g = groups[groups.length - 1];
    if (!g || g.key !== k) { g = { key: k, items: [], sum: 0 }; groups.push(g); }
    g.items.push(s);
    g.sum += s.end - s.start;
  }
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Verlauf</h1><div class="sub">Alle Sitzungen nach Tagen</div></div></div>
    ${groups.length ? groups.map(g => `<div class="card day-group">
      <div class="day-head"><h3>${esc(fmtDay(parseDay(g.key), true))}</h3><div class="sum">${esc(fmtDur(g.sum))}</div></div>
      ${g.items.map(s => `<a class="sess-row" href="#/spiele/${s.game.id}">
        ${coverHtml(s.game, 'mini')}
        <div class="name">${esc(s.game.name)}</div>
        <div class="time">${fmtTime(s.start)} – ${s.open ? '<span class="live-tag">läuft</span>' : fmtTime(s.end) + ' Uhr'}</div>
        <div class="dur">${esc(fmtDur(s.end - s.start))}</div>
        <div>${s.open ? '' : `<button class="icon-btn" data-del="${s.id}" title="Sitzung löschen" aria-label="Sitzung löschen">${TRASH}</button>`}</div>
      </a>`).join('')}</div>`).join('')
      : '<div class="card empty">Noch keine Sitzungen. Starte ein Spiel – Spielzeit erkennt es automatisch.</div>'}
    ${sessions.length >= state.historyLimit ? '<div style="text-align:center"><button class="btn" id="more">Ältere Sitzungen laden</button></div>' : ''}
  </div>`;
  wireCovers(main);
  wireDeletes(main);
  const more = $('#more');
  if (more) more.addEventListener('click', () => { state.historyLimit += 300; renderHistory(); });
}

/* ================================================================ Einstellungen */
async function renderSettings() {
  const key = location.hash;
  const st = await api('settings');
  if (!isCurrent(key)) return;
  main.innerHTML = `<div class="page">
    <div class="page-head"><div><h1>Einstellungen</h1><div class="sub">Spielzeit ${esc(st.version)}${st.demo ? ' · Demo-Modus' : ''}</div></div></div>
    ${st.tracker_note ? `<div class="banner">ℹ️ ${esc(st.tracker_note)}</div>` : ''}
    <div class="settings">
      <div class="col">
        <div class="card"><div class="card-head"><h2>Allgemein</h2></div>
          <div class="set-row"><div><div class="t">Mit Windows starten</div><div class="d">${st.autostart_supported ? 'Spielzeit startet unauffällig im Infobereich.' : 'Nur in der Windows-Version verfügbar.'}</div></div>
            <label class="switch"><input type="checkbox" id="set-autostart" ${st.autostart ? 'checked' : ''} ${st.autostart_supported ? '' : 'disabled'}><span></span></label></div>
          <div class="set-row"><div><div class="t">Tracking pausieren</div><div class="d">Solange pausiert, wird keine Spielzeit erfasst.</div></div>
            <label class="switch"><input type="checkbox" id="set-paused" ${st.paused ? 'checked' : ''}><span></span></label></div>
          <div class="set-row"><div><div class="t">Design</div><div class="d">Dunkel, hell oder wie Windows.</div></div>
            <div class="seg" id="set-theme">${[['system', 'System'], ['dark', 'Dunkel'], ['light', 'Hell']].map(([v, l]) => `<button data-v="${v}" class="${st.theme === v ? 'active' : ''}">${l}</button>`).join('')}</div></div>
        </div>
        <div class="card"><div class="card-head"><h2>Spiel manuell hinzufügen</h2></div>
          <p class="help">Ein Spiel wird nicht erkannt? Starte es, lade die Liste der laufenden Programme und füge es hinzu.</p>
          <button class="btn" id="load-procs">Laufende Programme anzeigen</button>
          <div class="list proc-list" id="proc-list"></div>
          <div class="add-row"><input class="input" id="exe-path" placeholder="oder Pfad zur EXE, z. B. D:\\Spiele\\MeinSpiel\\game.exe"><button class="btn" id="add-exe">Hinzufügen</button></div>
        </div>
        <div class="card"><div class="card-head"><h2>Eigene Spieleordner</h2></div>
          <p class="help">Jeder Unterordner eines solchen Ordners zählt als ein Spiel.</p>
          <div class="list" id="folder-list">${st.extra_folders.length ? st.extra_folders.map((f, i) => `<div class="list-item"><div class="grow path">${esc(f)}</div><button class="btn small ghost" data-rm="${i}">Entfernen</button></div>`).join('') : '<div class="muted">Keine eigenen Ordner.</div>'}</div>
          <div class="add-row"><input class="input" id="folder-path" placeholder="z. B. D:\\Spiele"><button class="btn" id="add-folder">Ordner hinzufügen</button></div>
        </div>
      </div>
      <div class="col">
        <div class="card"><div class="card-head"><h2>Ausgeblendete Spiele</h2></div>
          <div class="list">${st.ignored.length ? st.ignored.map(g => `<div class="list-item">${coverHtml(g, 'mini')}<div class="grow"><div class="t">${esc(g.name)}</div></div><button class="btn small" data-unhide="${g.id}">Einblenden</button></div>`).join('') : '<div class="muted">Keine ausgeblendeten Spiele.</div>'}</div>
        </div>
        <div class="card"><div class="card-head"><h2>Daten</h2></div>
          <div class="set-row"><div><div class="t">CSV-Export</div><div class="d">Alle Sitzungen als Tabelle (Excel-kompatibel).</div></div><button class="btn" id="export">Exportieren</button></div>
          <div class="set-row"><div style="min-width:0"><div class="t">Datenordner</div><div class="path">${esc(st.data_dir)}</div></div></div>
          <div class="set-row"><div><div class="t">Datenschutz</div><div class="d">Alles bleibt lokal auf diesem PC. Nur Steam-Coverbilder werden aus dem Internet geladen.</div></div></div>
        </div>
        <div class="card"><div class="card-head"><h2>Erkannte Bibliotheken</h2><div class="meta">${st.library_total} installierte Spiele</div></div>
          ${st.libraries.length ? st.libraries.map(l => `<details class="lib"><summary><span>${esc(l.label)}</span><span class="count">${l.count}</span></summary><div class="names">${l.games.map(esc).join(' · ')}</div></details>`).join('')
            : '<div class="muted">Keine Spielebibliotheken gefunden.</div>'}
        </div>
      </div>
    </div></div>`;
  wireCovers(main);

  const post = async (body, msg) => { const r = await act(() => api('settings', body), msg); refreshStatus(); return r; };
  $('#set-autostart').addEventListener('change', e => post({ autostart: e.target.checked }, e.target.checked ? 'Autostart eingeschaltet' : 'Autostart ausgeschaltet').then(r => { if (!r) route(); }));
  $('#set-paused').addEventListener('change', e => post({ paused: e.target.checked }, e.target.checked ? 'Tracking pausiert' : 'Tracking läuft wieder'));
  $$('#set-theme button').forEach(b => b.addEventListener('click', async () => {
    $$('#set-theme button').forEach(x => x.classList.toggle('active', x === b));
    await post({ theme: b.dataset.v });
  }));
  $$('[data-unhide]').forEach(b => b.addEventListener('click', async () => {
    await act(() => api(`game/${b.dataset.unhide}/ignore`, { ignored: false }), 'Wieder eingeblendet');
    route();
  }));
  const setFolders = async folders => { if (await post({ extra_folders: folders }, 'Ordner gespeichert')) route(); };
  $$('[data-rm]').forEach(b => b.addEventListener('click', () => setFolders(st.extra_folders.filter((_, i) => i !== +b.dataset.rm))));
  $('#add-folder').addEventListener('click', () => {
    const v = $('#folder-path').value.trim();
    if (v) setFolders(st.extra_folders.concat([v]));
  });
  const addGame = async (exe, suggested) => {
    const name = await openModal({ title: 'Spiel hinzufügen', text: exe, value: suggested, okLabel: 'Hinzufügen' });
    if (!name) return;
    const r = await act(() => api('games/add', { exe, name }), `„${name}“ wird ab jetzt erfasst`);
    if (r) route();
  };
  $('#add-exe').addEventListener('click', () => {
    const exe = $('#exe-path').value.trim().replace(/^"|"$/g, '');
    if (exe) addGame(exe, exe.split(/[\\/]/).pop().replace(/\.exe$/i, ''));
  });
  $('#load-procs').addEventListener('click', async () => {
    const box = $('#proc-list');
    box.innerHTML = '<div class="muted">Lade …</div>';
    const r = await act(() => api('processes'));
    if (!r) { box.innerHTML = ''; return; }
    if (!r.available) { box.innerHTML = '<div class="muted">Die Prozessliste ist nur verfügbar, wenn die Erkennung läuft.</div>'; return; }
    box.innerHTML = r.processes.length ? r.processes.map((p, i) => `<div class="list-item"><div class="grow"><div class="t">${esc(p.title)}${p.tracked ? ` <span class="badge">${p.game ? 'erkannt: ' + esc(p.game) : 'bereits erfasst'}</span>` : ''}</div><div class="d" title="${esc(p.exe)}">${esc(p.exe)}</div></div>
      ${p.tracked ? '' : `<button class="btn small" data-proc="${i}">Hinzufügen</button>`}</div>`).join('') : '<div class="muted">Keine passenden Programme gefunden.</div>';
    $$('[data-proc]', box).forEach(b => b.addEventListener('click', () => { const p = r.processes[+b.dataset.proc]; addGame(p.exe, p.title); }));
  });
  $('#export').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/export.csv', { headers: { 'X-Spielzeit': '1' } });
      if (!res.ok) throw new Error('Export fehlgeschlagen');
      const blob = await res.blob();
      const cd = res.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename="([^"]+)"/);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = m ? m[1] : 'spielzeit.csv';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      toast('CSV-Datei wird heruntergeladen');
    } catch (e) { toast(e.message, true); }
  });
}

/* ================================================================ Start */
let resizeTimer = null;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => state.redraw && state.redraw(), 120); });
addEventListener('hashchange', route);
if (window.matchMedia) matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => state.redraw && state.redraw());
applyTheme(null);
refreshStatus().then(route);
setInterval(refreshStatus, 5000);
setInterval(tickTimers, 1000);
