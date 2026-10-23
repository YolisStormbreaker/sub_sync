// Shared by every page: DOM helpers, icons, formatting (local time, decimal comma), API calls, save feedback, inline
// confirmation, undo toast, the library filter and tree, one shared audio element, and the rail (service status, badges).
// All text from the server goes through textContent; innerHTML is used only for the constant icons below.
'use strict';
const SS = window.SS || {};
const LN = Object.fromEntries(SS.langs || []);

const ICON = {
  chev: '<svg class="chev" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  down: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 6L8 10.5 12.5 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.2v9.6L12.6 8z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor"/><rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor"/></svg>',
  spin: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="26 12" stroke-linecap="round"/></svg>',
  check: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  warn: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5l6 11H2z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v3M8 11.8v.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  clock: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.8V8l2.2 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  next: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3.5v9l6.5-4.5z" fill="currentColor"/><path d="M12 3.5v9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  done: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

// ---------- DOM
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;                       // constants only (icons)
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style') e.style.cssText = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : String(k));
  return e;
}
const icon = name => { const t = document.createElement('template'); t.innerHTML = ICON[name]; return t.content.firstChild; };
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => [...(root || document).querySelectorAll(sel)];
const store = {
  get(k, d) { try { const v = localStorage.getItem('ss:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('ss:' + k, JSON.stringify(v)); } catch (e) { /* private window: forget it */ } },
};

// ---------- formatting
const nf2 = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num2 = x => nf2.format(x);
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  return (a > 10 && a < 20) ? many : b === 1 ? one : (b >= 2 && b <= 4) ? few : many;
}
const nfiles = n => n + ' ' + plural(n, 'файл', 'файла', 'файлов');
function clock(t) {
  t = Math.max(0, Math.round(t)); const hh = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
  return (hh ? hh + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
}
const hm = d => d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
function when(ts, withTime) {               // local time: "сегодня, 03:12", "вчера", "21 октября"
  const d = new Date(ts * 1000), now = new Date(), day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(d) - day(now)) / 864e5);
  const label = diff === 0 ? 'сегодня' : diff === -1 ? 'вчера' : diff === 1 ? 'завтра' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
  return withTime ? label + ', ' + hm(d) : label;
}
const lname = c => LN[c] || c;
function duration(sec) {
  const m = Math.round(sec / 60); return m < 60 ? m + ' мин' : Math.floor(m / 60) + ' ч ' + (m % 60) + ' мин';
}

// ---------- API
async function api(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(await r.text() || r.statusText);
  return r.json();
}
async function post(url, body, opts) {
  let r;
  try { r = await fetch(url, Object.assign({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, opts || {})); }
  catch (e) { const x = new Error('сервис не ответил'); x.unreachable = true; throw x; }
  if (!r.ok) throw new Error(await r.text() || r.statusText);
  return r.text();
}
const WHEN = 'Применится на следующем проходе: новые файлы — в течение 2 минут, старая библиотека — сегодня ночью.';

// Save with feedback next to the control: "Сохраняю…" → "Сохранено. <note>" (fades after 4 s) or the server's error (stays).
async function save(fb, call, note) {
  setFb(fb, 'saving', 'Сохраняю…');
  try { await call(); setFb(fb, 'saved', 'Сохранено. ' + (note || WHEN)); return true; }
  catch (e) {
    const msg = e.unreachable ? 'Не сохранилось: сервис не ответил. Значение прежнее.' : 'Не сохранилось: ' + e.message + '. Значение прежнее.';
    if (fb) setFb(fb, 'error', msg); else toast(msg, { iconName: 'warn' });
    return false;
  }
}
function setFb(fb, state, text) {
  if (!fb) return;
  clearTimeout(fb._t); fb.className = 'feedback feedback--' + state; fb.textContent = '';
  fb.append(icon(state === 'saving' ? 'spin' : state === 'saved' ? 'check' : 'warn'), h('span', null, text));
  fb.hidden = false;
  if (state === 'saved') fb._t = setTimeout(() => { fb.hidden = true; }, 6000);
}
const fbEl = () => h('span', { class: 'feedback', hidden: true, role: 'status' });

// ---------- form bits
function selectBox(options, value, attrs) {      // options: [[value, label], ...]
  const s = h('select', Object.assign({ class: 'select' }, attrs || {}));
  for (const [v, t] of options) s.append(new Option(t, v));
  s.value = value == null ? '' : String(value);
  return h('span', { class: 'selectwrap' }, s, icon('down'));
}
function langOptions(first) { return [['', first]].concat((SS.langs || []).map(([c, n]) => [c, n[0].toUpperCase() + n.slice(1) + ' (' + c + ')'])); }

// Inline confirmation in place of a native dialog.
function confirmBox({ title, body, yes, no, onYes, onNo }) {
  const box = h('div', { class: 'confirm', role: 'alertdialog' },
    h('p', { class: 't-h3' }, title), h('p', null, body),
    h('div', { class: 'actions' },
      h('button', { class: 'btn btn--danger-solid', type: 'button', onclick: () => { box.remove(); onYes(); } }, yes),
      h('button', { class: 'btn', type: 'button', onclick: () => { box.remove(); onNo && onNo(); } }, no || 'Отмена')));
  setTimeout(() => box.querySelector('button').focus(), 0);
  return box;
}

// Undo toast. With seconds > 0 the action is committed when the countdown ends (or when the page is closed), unless undone.
function toast(text, { seconds = 0, undo, commit, iconName = 'check' } = {}) {
  let wrap = $('.toasts'); if (!wrap) { wrap = h('div', { class: 'toasts', 'aria-live': 'polite' }); ($('#ss') || document.body).append(wrap); }  // inside .ss: the tokens live there
  const timer = h('span', { class: 'toast-timer num' });
  const t = h('div', { class: 'toast', role: 'status' }, icon(iconName), h('span', { class: 'grow' }, text), seconds ? timer : null);
  let left = seconds, done = false;
  const finish = ok => { if (done) return; done = true; clearInterval(iv); window.removeEventListener('pagehide', onHide); t.remove(); if (ok && commit) commit(false); };
  const onHide = () => { if (!done && commit) { done = true; commit(true); } };
  if (undo) t.append(h('button', { class: 'btn', type: 'button', onclick: () => { finish(false); undo(); } }, 'Отменить'));
  wrap.append(t);
  let iv = null;
  if (seconds) {
    const tick = () => { timer.textContent = 'через ' + left + ' с'; if (left-- <= 0) finish(true); };
    tick(); iv = setInterval(tick, 1000); window.addEventListener('pagehide', onHide);
  } else setTimeout(() => finish(false), 6000);
  return t;
}

// ---------- library filter, natural order, tree (shared by every list)
const natKey = s => String(s).toLowerCase().replace(/\d+/g, d => d.padStart(8, '0'));
const natcmp = (a, b) => { a = natKey(a); b = natKey(b); return a < b ? -1 : a > b ? 1 : 0; };
const SEAS = /(?:^|[^a-zа-я])(?:s|season|сезон)[ ._-]*(\d{1,3})(?!\d)/i;
const EPIS = [/(?:^|[^a-z])s(\d{1,3})[ ._-]?e(\d{1,4})(?!\d)/i, /(?:^|[^\d])(\d{1,2})x(\d{2,3})(?!\d)/i];
function epInfo(rel) {
  const p = rel.split('/'), f = p[p.length - 1]; let s = null, e = null;
  for (const r of EPIS) { const m = r.exec(f); if (m) { s = +m[1]; e = +m[2]; break; } }
  if (s === null) for (let i = p.length - 2; i >= 1; i--) { const m = SEAS.exec(p[i]); if (m) { s = +m[1]; break; } }
  return { s, e };
}
const dirOf = rel => rel.split('/').slice(0, -1).join('/');
function relCmp(a, b) { const x = epInfo(a), y = epInfo(b); return ((x.s ?? 1e9) - (y.s ?? 1e9)) || ((x.e ?? 1e9) - (y.e ?? 1e9)) || natcmp(a.split('/').pop(), b.split('/').pop()); }
function libCmp(a, b) { return natcmp(dirOf(a), dirOf(b)) || relCmp(a, b); }
function matchQ(rel, q) {
  q = (q || '').trim().toLowerCase(); if (!q) return true;
  const n = rel.toLowerCase().replace(/[._]+/g, ' '), ei = epInfo(rel);
  return q.split(/\s+/).every(t => {
    let m;
    if ((m = /^s(\d+)e(\d+)$/.exec(t)) || (m = /^(\d+)x(\d+)$/.exec(t))) return ei.s === +m[1] && ei.e === +m[2];
    if ((m = /^s(\d+)$/.exec(t))) return ei.s === +m[1];
    if ((m = /^e(\d+)$/.exec(t))) return ei.e === +m[1];
    return n.includes(t.replace(/[._]+/g, ' '));
  });
}
function searchBox(value, oninput) {
  const inp = h('input', { type: 'search', placeholder: 'Название или серия: s06e05, 6x05, s06, e05', value: value || '' });
  inp.addEventListener('input', () => oninput(inp.value));
  return h('label', { class: 'search' }, icon('search'), h('span', { class: 'vh' }, 'Фильтр библиотеки'), inp);
}
// items → nested <details class="node"> mirroring the folders of relOf(item); open state kept per tree in localStorage.
function tree(items, relOf, leaf, key, forceOpen) {
  const mk = () => ({ dirs: new Map(), items: [], n: 0 }), root = mk();
  for (const it of items) {
    const p = relOf(it).split('/'); let n = root; n.n++;
    for (let i = 0; i < p.length - 1; i++) { let c = n.dirs.get(p[i]); if (!c) { c = mk(); n.dirs.set(p[i], c); } n = c; n.n++; }
    n.items.push(it);
  }
  const open = store.get('tree:' + key, {});
  const draw = (n, path, into) => {
    for (const k of [...n.dirs.keys()].sort(natcmp)) {
      const c = n.dirs.get(k), id = path + k + '/';
      const d = h('details', { class: 'node' }), body = h('div', { class: 'node-body' });
      d.open = forceOpen || (id in open ? open[id] : items.length <= 6);
      d.addEventListener('toggle', () => { if (!forceOpen) { const o = store.get('tree:' + key, {}); o[id] = d.open; store.set('tree:' + key, o); } });
      const s = h('summary', null, icon('chev'), k, h('span', { class: 'tally' }, nfiles(c.n)));
      draw(c, id, body); d.append(s, body); into.append(d);
    }
    n.items.sort((a, b) => relCmp(relOf(a), relOf(b)) || String(a.lang || '').localeCompare(String(b.lang || ''))).forEach(it => into.append(leaf(it)));
  };
  const out = h('div', { class: 'stack', style: 'gap:12px' }); draw(root, '', out); return out;
}
function segmented(label, options, value, onchange) {   // options: [[value, label, count?], ...]
  const g = h('div', { class: 'seg', role: 'group', 'aria-label': label });
  for (const [v, t, n] of options) {
    const b = h('button', { type: 'button', 'aria-pressed': String(v === value) }, t, n != null ? h('span', { class: 'n' }, n) : null);
    b.addEventListener('click', () => { $$('button', g).forEach(x => x.setAttribute('aria-pressed', String(x === b))); onchange(v); });
    g.append(b);
  }
  return g;
}
function placeholders(n) { return Array.from({ length: n }, () => h('div', { class: 'ph', style: 'height:' + (120 + 40 * Math.random() | 0) + 'px' }, h('i'), h('i'), h('i'))); }
function pageHead(title, lead) { return h('header', { class: 'pagehead' }, h('h1', { class: 't-h1' }, title), h('p', { id: 'lead' }, lead || '')); }

// ---------- one audio element for the whole page
const Player = {
  a: null, owner: null,
  play(src, owner, cb) {        // cb(state, audio): 'loading' | 'playing' | 'paused' | 'ended' | 'error'
    if (!this.a) { this.a = new Audio(); this.a.preload = 'auto'; }
    const a = this.a;
    if (this.owner && this.owner.cb) this.owner.cb('paused', a);
    this.owner = { src, cb, owner };
    a.src = src; cb('loading', a);
    const me = this.owner;
    a.oncanplay = () => { if (this.owner === me) a.play().catch(() => {}); };
    a.onplaying = () => { if (this.owner === me) cb('playing', a); };
    a.ontimeupdate = () => { if (this.owner === me) cb('tick', a); };
    a.onpause = () => { if (this.owner === me && !a.ended) cb('paused', a); };
    a.onended = () => { if (this.owner === me) cb('ended', a); };
    a.onerror = async () => { if (this.owner !== me) return; let t = 'не удалось получить фрагмент'; try { t = await (await fetch(src)).text(); } catch (e) {} cb('error', a, t); };
    a.load();
  },
  toggle() { if (!this.a) return; if (this.a.paused) this.a.play().catch(() => {}); else this.a.pause(); },
  stop() { if (this.a) { this.a.pause(); if (this.owner && this.owner.cb) this.owner.cb('paused', this.a); } this.owner = null; },
  isOwner(o) { return this.owner && this.owner.owner === o; },
};

// ---------- rail: service status and badges
async function railRefresh() {
  let s;
  try { s = await api('/api/status'); } catch (e) { s = null; }
  const st = $('#status'), mini = $('#status-mini'); st.textContent = ''; mini.textContent = '';
  if (!s) { st.append(h('div', { class: 'live', style: 'color:var(--danger)' }, h('i', { class: 'dot dot--off' }), 'Панель не получила статус сервиса')); return; }
  const kind = { night: 'идёт ночной проход', new: 'обрабатывает новые файлы', hint: 'ищет по вашим подсказкам' }[s.kind];
  if (s.alive) st.append(h('div', { class: 'live' }, h('i', { class: 'dot' }), 'Сервис работает' + (kind ? ': ' + kind : '')));
  else st.append(h('div', { class: 'live', style: 'color:var(--danger);align-items:flex-start' }, h('i', { class: 'dot dot--off', style: 'margin-top:6px' }),
    h('span', null, 'Сервис не отвечает' + (s.beat ? ' с ' + when(s.beat, true) : '') + '. Решения сохраняются, но применятся после перезапуска.')));
  const nt = s.night;
  if (nt) {
    st.append(h('div', { class: 'status-item' }, h('b', null, 'Ночной проход'),
      h('span', null, when(nt.start, true) + ', занял ' + duration(nt.busy || (nt.end - nt.start)) + (nt.finished ? '' : ', прерван новыми файлами и продолжится')),
      h('dl', { class: 'night' }, h('dt', null, 'записано'), h('dd', null, nt.written || 0), h('dt', null, 'отложено на проверку'), h('dd', null, nt.held || 0),
        h('dt', null, 'не найдено'), h('dd', null, nt.notfound || 0))));
  }
  const q = s.quota, pct = Math.min(100, Math.round(100 * q.used / q.limit));
  st.append(h('div', { class: 'status-item' }, h('b', null, 'Скачивания сегодня: ' + q.used + ' из ' + q.limit),
    h('div', { class: 'meter' }, h('i', { style: 'width:' + pct + '%' })),
    h('span', null, 'Счётчик обнулится в ' + hm(new Date(q.reset * 1000)) + '. Новые файлы проверяются каждые 2 минуты.')));
  mini.append(h('span', { class: 'live' }, h('i', { class: 'dot' + (s.alive ? '' : ' dot--off') }), s.alive ? 'Работает' : 'Не отвечает'));
  if (nt) mini.append(h('span', null, 'ночью записано ' + (nt.written || 0)));
  mini.append(h('span', { class: 'num' }, 'скачано ' + q.used + ' из ' + q.limit));
  const titles = { lang: 'ждут решения', review: 'ждут проверки', missing: 'можно исправить' };
  for (const a of $$('.nav a')) {
    const k = a.dataset.badge, n = s.badges[k]; let b = $('.count', a);
    if (!n) { if (b) b.remove(); continue; }
    if (!b) { b = h('span', { class: 'count' }); a.append(b); }
    b.textContent = n; b.setAttribute('aria-label', n + ' ' + titles[k]);
  }
}
function railInit() {
  railRefresh(); setInterval(railRefresh, 60000);
  const cur = $('.nav a[aria-current="page"]'); if (cur && cur.parentElement.scrollWidth > cur.parentElement.clientWidth) cur.parentElement.scrollLeft = cur.offsetLeft - 16;
}
document.addEventListener('DOMContentLoaded', railInit);
