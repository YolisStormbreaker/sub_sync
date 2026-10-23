// "Язык и дорожка": the queue of files whose original language or original audio track the service cannot settle alone.
// A save never re-renders the page: only the card concerned is replaced, or collapsed to a one-line stub with "Отменить".
'use strict';
const SECT = { need: 'Нужен ваш выбор', queue: 'В очереди на автоопределение', mine: 'Выбрано вами' };
const SPOTS = [0.5, 0.3, 0.7, 0.15, 0.85];
const WHERE = { 0.15: 'начало', 0.3: 'первая треть', 0.5: 'середина', 0.7: 'вторая половина', 0.85: 'ближе к концу' };
let D = null, seg = store.get('lang:seg', 'need'), Q = '';
const spotOf = new Map();           // path -> index into SPOTS, shared by all tracks of the file

function findFile(path) {
  for (const g of D.groups) for (const k of ['need', 'queue', 'mine']) { const f = g[k].find(x => x.path === path); if (f) return [f, g, k]; }
  return [null, null, null];
}
async function reload() { D = await api('/api/state'); railRefresh(); updateCounts(); }
const own = f => f.own || {};

// ---------- one file
function trackRow(f, t, card) {
  const n = f.tracks.length, labelled = own(f).tlangs && own(f).tlangs[t.i] != null;
  const cand = f.cands && f.cands.includes(t.i), chosen = own(f).track === t.i;
  const isOrig = (f.settled && f.settled.track === t.i) || chosen;
  const li = h('li', { class: 'track' + (labelled ? ' is-labelled' : '') + (cand ? ' is-candidate' : '') + (isOrig ? ' is-original' : '') });
  const btn = h('button', { class: 'play', type: 'button', 'aria-label': 'Послушать дорожку ' + (t.i + 1) + (n > 1 ? ' с того же момента' : '') }, icon('play'));
  const sub = h('span');
  const desc = () => [t.codec, labelled ? lname(t.lang) + ' — указали вы' : (t.lang && t.lang !== 'und' ? lname(t.lang) + ', метка в файле' : 'язык не указан'),
    t.title ? '«' + t.title + '»' : ''].filter(Boolean).join(', ');
  sub.textContent = desc();
  const prog = h('i', { class: 'track-prog', style: 'width:0' });
  btn.addEventListener('click', () => {
    if (Player.isOwner(li) && Player.a && !Player.a.paused) { Player.toggle(); return; }
    if (Player.isOwner(li) && Player.a && Player.a.paused && Player.a.currentTime > 0 && !Player.a.ended) { Player.toggle(); return; }
    const t0 = Math.max(0, Math.round((f.dur || 120) * SPOTS[spotOf.get(f.path) || 0]));
    Player.play('/api/clip?path=' + encodeURIComponent(f.path) + '&track=' + t.i + '&t=' + t0 + '&len=20', li, (state, a, err) => {
      btn.className = 'play' + (state === 'loading' ? ' is-loading' : state === 'playing' || state === 'tick' ? ' is-on' : '');
      li.classList.toggle('is-playing', state === 'playing' || state === 'tick' || state === 'loading');
      if (state === 'loading') { btn.replaceChildren(icon('spin')); btn.setAttribute('aria-label', 'Фрагмент дорожки ' + (t.i + 1) + ' готовится'); sub.className = ''; sub.textContent = 'Готовлю фрагмент, 1–3 секунды…'; }
      else if (state === 'playing' || state === 'tick') {
        if (state === 'playing') { btn.replaceChildren(icon('pause')); btn.setAttribute('aria-label', 'Пауза, дорожка ' + (t.i + 1)); }
        sub.className = 'playtime'; sub.textContent = 'Играет ' + clock(a.currentTime) + ' из ' + clock(a.duration || 20);
        prog.style.width = (100 * a.currentTime / (a.duration || 20)) + '%';
      } else if (state === 'error') { btn.replaceChildren(icon('play')); sub.className = 'feedback feedback--error'; sub.textContent = 'Не получилось: ' + err; }
      else { btn.replaceChildren(icon('play')); btn.setAttribute('aria-label', 'Послушать дорожку ' + (t.i + 1)); sub.className = ''; sub.textContent = desc(); if (state === 'ended') prog.style.width = '0'; }
    });
  });
  const sc = f.auto && f.auto.scores ? f.auto.scores[String(t.i)] : null;
  let score;
  if (labelled && !cand) score = h('div', { class: 'score' }, h('span', null, 'Не участвует в сравнении'));
  else if (f.settled && f.settled.track === t.i) score = h('div', { class: 'score' }, h('span', { class: 'badge badge--done', style: 'align-self:flex-start' }, 'Оригинал — вывод из вашей метки'));
  else if (sc != null) {
    const best = f.auto.best === t.i;
    score = h('div', { class: 'score' + (best ? ' is-best' : '') }, h('div', { class: 'score-top' }, h('span', null, 'Совпадение речи'), h('span', { class: 'score-val' }, num2(sc))),
      h('div', { class: 'score-bar' }, h('i', { style: 'width:' + Math.max(2, Math.min(100, sc * 100)) + '%' })), best && !f.auto.sure ? h('span', null, 'лучшая, но не уверенно') : null);
  } else score = h('div', { class: 'score' }, h('span', null, n > 1 ? 'Ещё не сравнивали' : ''));
  li.append(btn, h('div', { class: 'track-id' }, h('b', null, 'Дорожка ' + (t.i + 1)), sub), score);
  if (n > 1) {
    const cur = labelled ? own(f).tlangs[t.i] : '';
    const wrap = selectBox([['', 'Язык: не указан']].concat((SS.langs || []).map(([c, nm]) => [c, 'Язык: ' + nm])), cur, { class: 'select select--sm' });
    const sel = wrap.querySelector('select');
    sel.addEventListener('change', () => labelTrack(f, t.i, sel.value, card, fb));
    li.append(h('label', { class: 'tlang' }, h('span', { class: 'vh' }, 'Язык дорожки ' + (t.i + 1)), wrap));
  } else li.append(h('span', { class: 'tlang' }));
  const fb = fbEl();
  if (chosen) li.append(h('span', { class: 'tact badge badge--done' }, 'Оригинал — выбран вами'));
  else if ((labelled && !cand && !isOrig) || n === 1) li.append(h('span', { class: 'tact' }, fb));  // one track: nothing to choose, only the language
  else li.append(h('span', { class: 'tact stack', style: 'gap:4px;align-items:flex-end' },
    h('button', { class: 'btn', type: 'button', onclick: () => pick(f, t.i, card) }, 'Это оригинал'), fb));
  li.append(prog);
  return li;
}

function cardFor(f, sect) {
  const name = f.path.split('/').pop(), o = own(f), n = f.tracks.length;
  const card = h('article', { class: 'card' + (f.settled ? ' card--settled' : ''), 'data-path': f.path });
  const ep = epInfo(f.path).e != null;
  const badge = sect === 'mine' ? h('span', { class: 'badge badge--done' }, 'Выбрано вами') : sect === 'queue' ? h('span', { class: 'badge badge--queue' }, 'В очереди')
    : f.settled ? h('span', { class: 'badge badge--done' }, 'Ждёт подтверждения') : f.lang == null ? h('span', { class: 'badge badge--need' }, 'Неизвестен язык')
      : h('span', { class: 'badge badge--need' }, 'Нужен ваш выбор');
  card.append(h('div', { class: 'card-head' },
    h('div', null, h('h3', { class: 'fname', title: f.path }, name),
      h('p', { class: 'fmeta' }, f.dur ? h('span', { class: 'num' }, clock(f.dur)) : null, h('span', null, n + ' ' + plural(n, 'дорожка', 'дорожки', 'дорожек')))),
    badge));
  const why = h('p', { class: 'why' });
  (f.lines || []).forEach((l, i) => { why.append(i === 0 ? h('b', null, l) : ' ' + l); });
  if (!f.settled) card.append(why);
  if (f.settled) {
    const k = f.settled.track + 1, labs = Object.entries(o.tlangs || {}).sort((a, b) => a[0] - b[0]).map(([i, l]) => 'дорожка ' + (+i + 1) + ' — ' + lname(l)).join(', ');
    const reason = f.settled.why === 'first track that is not ru/uk/dub'
      ? 'Вы указали: ' + labs + '. Это первая дорожка не на русском, поэтому оригинал — она.'
      : 'Вы указали: ' + labs + '. Других дорожек без языка, кроме ' + k + '-й, нет, поэтому оригинал — она.';
    const v = h('div', { class: 'verdict', role: 'status' }, h('p', { class: 't-h3' }, 'Оригинал — дорожка ' + k), h('p', null, reason),
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn--primary', type: 'button', onclick: () => pick(f, f.settled.track, card) }, 'Подтвердить: оригинал — дорожка ' + k),
        h('button', { class: 'btn', type: 'button', onclick: () => { v.remove(); card.classList.remove('card--settled'); card.querySelector('.tracks .btn')?.focus(); } }, 'Выбрать другую')),
      h('span', { class: 'help', style: 'color:var(--ink-2)' }, 'После подтверждения файл перейдёт в «Выбрано вами», субтитры синхронизируются на следующем проходе.'));
    card.append(v);
  }
  if (f.cands && f.cands.length) {
    const c = f.cands.map(i => i + 1);
    card.append(h('div', { class: 'cands', role: 'status' },
      h('b', null, c.length === 1 ? 'Остался 1 кандидат: дорожка ' + c[0] + '.' : 'Осталось ' + c.length + ' ' + plural(c.length, 'кандидат', 'кандидата', 'кандидатов') + ': дорожки ' + c.slice(0, -1).join(', ') + ' и ' + c[c.length - 1] + '.'),
      h('span', null, 'Автоопределение сравнит только их, когда дойдёт очередь, — или выберите на слух сейчас.')));
  }
  if (n) {
    const label = h('span', { class: 'moment-label' }), scale = h('span', { class: 'moment-scale', 'aria-hidden': 'true' });
    const draw = () => {
      const s = SPOTS[spotOf.get(f.path) || 0], t0 = Math.round((f.dur || 120) * s);
      label.replaceChildren(n > 1 ? (n === 2 ? 'Обе дорожки играют с ' : 'Все дорожки играют с ') : 'Фрагмент с ', h('b', null, clock(t0)), ', ' + WHERE[s] + (ep ? ' серии' : ' фильма'));
      scale.replaceChildren(...[0.15, 0.3, 0.5, 0.7, 0.85].map(p => h('i', { class: p === s ? 'on' : null, style: 'left:' + p * 100 + '%' })));
    };
    draw();
    const next = h('button', { class: 'btn btn--quiet', type: 'button' }, icon('next'), 'Другой фрагмент');
    next.addEventListener('click', () => {
      spotOf.set(f.path, ((spotOf.get(f.path) || 0) + 1) % SPOTS.length); draw();
      const playing = $('.track.is-playing .play', card); if (playing) { Player.stop(); playing.click(); }
    });
    card.append(h('div', { class: 'moment' }, label, scale, next));
  }
  card.append(h('ol', { class: 'tracks' }, f.tracks.map(t => trackRow(f, t, card))));
  if (sect === 'mine' && o.track != null) {
    const fb = fbEl();
    card.append(h('div', { class: 'actions' }, h('button', { class: 'btn btn--quiet', type: 'button', onclick: async () => {
      if (await save(fb, () => post('/api/override', { path: f.path, lang: o.lang ?? null, track: null }), 'Выбор отменён, дорожку снова определяет сервис.')) { await reload(); replaceCard(card, f.path); }
    } }, 'Отменить мой выбор дорожки'), fb));
  }
  // the language of this file only
  const det = h('details', { class: 'mini' });
  det.open = f.lang == null;
  const lsel = selectBox(langOptions(f.lang == null ? 'Выберите язык' : 'Как у папки или по данным сервиса'), o.lang, { class: 'select', 'aria-label': 'Язык оригинала для ' + name });
  lsel.style.width = '280px';
  const lfb = fbEl();
  lsel.querySelector('select').addEventListener('change', async e => {
    if (await save(lfb, () => post('/api/override', { path: f.path, lang: e.target.value || null, track: o.track ?? null }), 'Сервис скачает субтитры на этом языке на следующем проходе.')) {
      await reload(); replaceCard(card, f.path, true);
    }
  });
  det.append(h('summary', null, icon('chev'), f.lang == null ? 'Язык оригинала для этого файла' : 'Другой язык оригинала для этого файла'),
    h('div', { class: 'mini-body' }, lsel, h('span', { class: 'help' }, 'Сохраняется сразу.'), lfb));
  card.append(det);
  return card;
}

// Replace one card with its fresh version, wherever the server now puts the file. The card stays where it is on the page.
function replaceCard(card, path, keepOpen) {
  const [f, , k] = findFile(path);
  if (!f) { collapse(card, path.split('/').pop() + ': больше не ждёт решения.', null); return; }
  const nc = cardFor(f, k);
  if (keepOpen) { const d = $('details.mini', nc); if (d) d.open = true; }
  card.replaceWith(nc);
}

// Card → one-line stub: pin the height, swap the content, animate to the stub's height; compensate the scroll if it was above.
function collapse(card, text, undo) {
  const r = card.getBoundingClientRect(), above = r.bottom < 0, before = r.height;
  const stub = h('div', { class: 'collapsed-stub exit', style: 'height:' + before + 'px' }, icon('check'), h('span', { style: 'flex:1' }, text),
    undo ? h('button', { class: 'btn btn--quiet', type: 'button', onclick: undo }, 'Отменить') : null);
  card.replaceWith(stub);
  requestAnimationFrame(() => { stub.style.height = '44px'; if (above) window.scrollBy(0, 44 - before); });
  setTimeout(() => { stub.style.height = ''; stub.classList.remove('exit'); }, 220);
  return stub;
}
function focusNext(stub) {
  let n = stub.nextElementSibling;
  while (n && !n.matches('.card')) n = n.nextElementSibling;
  const target = n ? $('.play', n) : stub.closest('details.sect')?.querySelector('summary');
  if (target) target.focus({ preventScroll: true });
}

async function pick(f, i, card) {
  const fb = $('.tracks li:nth-child(' + (i + 1) + ') .feedback', card);
  const prev = own(f).track ?? null;
  const ok = await save(fb, () => post('/api/override', { path: f.path, lang: own(f).lang ?? null, track: i }));
  if (!ok) return;
  if (Player.owner && card.contains(Player.owner.owner)) Player.stop();
  const name = f.path.split('/').pop();
  const stub = collapse(card, name + ': оригинал — дорожка ' + (i + 1) + '. Перенесено в «Выбрано вами».', async () => {
    try { await post('/api/override', { path: f.path, lang: own(f).lang ?? null, track: prev }); }
    catch (e) { toast('Не отменилось: ' + e.message, { iconName: 'warn' }); return; }
    await reload(); const [nf, , k] = findFile(f.path); if (nf) stub.replaceWith(cardFor(nf, k));
  });
  focusNext(stub);
  reload();
}

async function labelTrack(f, i, lang, card, fb) {
  const m = Object.assign({}, own(f).tlangs || {});
  if (lang) m[i] = lang; else delete m[i];
  const ok = await save(fb, () => post('/api/override', { path: f.path, lang: own(f).lang ?? null, track: own(f).track ?? null, tlangs: m }), 'Язык дорожки ' + (i + 1) + ': ' + (lang ? lname(lang) : 'не указан') + '.');
  if (!ok) { await reload(); replaceCard(card, f.path); return; }
  await reload();
  const [nf] = findFile(f.path);
  replaceCard(card, f.path);
  if (nf && nf.settled) toast('Язык дорожки ' + (i + 1) + ' сохранён. Оригинал теперь определён сам: дорожка ' + (nf.settled.track + 1) + '. Подтвердите или выберите другую.');
}

// ---------- groups
function folderSettings(g) {
  const o = g.override || {}, box = h('div', { class: 'folder-set' });
  const lfb = fbEl(), lw = selectBox(langOptions('Не задан: определять автоматически'), o.lang, { id: 'l-' + g.path });
  if (o.lang) setTimeout(() => { lfb.hidden = false; lfb.className = 'feedback feedback--saved'; lfb.replaceChildren(icon('check'), h('span', null, 'Указан вами. Действует на ' + (g.nfiles === 1 ? 'файл папки' : 'все ' + nfiles(g.nfiles) + ' папки') + ', кроме тех, где язык задан отдельно.')); });
  lw.querySelector('select').addEventListener('change', async e => {
    if (await save(lfb, () => post('/api/override', { path: g.path, lang: e.target.value || null, track: o.track ?? null }))) { await reload(); redrawGroup(g.path); }
  });
  const tfb = fbEl(), opts = [['', 'Решать по каждому файлу']];
  for (let i = 0; i < Math.max(g.ntracks || 0, ...g.layouts.map(([k]) => k.split(' + ').length)); i++) opts.push([String(i), 'Всегда дорожка ' + (i + 1)]);
  const tw = selectBox(opts, o.track, { id: 't-' + g.path }), tsel = tw.querySelector('select'), slot = h('div');
  const commit = async () => { if (await save(tfb, () => post('/api/override', { path: g.path, lang: o.lang ?? null, track: tsel.value === '' ? null : +tsel.value }))) { await reload(); redrawGroup(g.path); } };
  tsel.addEventListener('change', () => {
    slot.textContent = '';
    if (tsel.value === '') { commit(); return; }
    const k = +tsel.value + 1;
    slot.append(confirmBox({ title: 'Дорожка ' + k + ' для всех ' + nfiles(g.nfiles) + ' папки?', body: 'Выбирайте так, только если послушали несколько серий и везде оригинал на этом месте. Уже выбранные вами файлы не изменятся.',
      yes: 'Да, всегда дорожка ' + k, no: 'Отмена', onYes: commit, onNo: () => { tsel.value = o.track == null ? '' : String(o.track); } }));
  });
  const lay = g.layouts.map(([k, n]) => {
    const parts = k.split(' + '), und = parts.filter(p => p === 'und').length;
    return (und === parts.length ? parts.length + ' без языка' : parts.map(p => p === 'und' ? 'без языка' : p).join(' + ')) + ' — ' + nfiles(n);
  }).join(', ');
  box.append(h('div', { class: 'field' }, h('label', { for: 'l-' + g.path }, 'Язык оригинала для всей папки'), lw, lfb),
    h('div', { class: 'field' }, h('label', { for: 't-' + g.path }, 'Дорожка оригинала для всей папки'), tw, slot, tfb,
      h('span', { class: 'help' }, (lay ? 'Дорожки в папке: ' + lay + '. ' : '') + '«Всегда дорожка N» подходит, только если оригинал во всех сериях на одном месте.')));
  return box;
}
function groupEl(g) {
  const files = k => g[k].filter(x => matchQ(x.path, Q));
  const cnt = { need: files('need').length, queue: files('queue').length, mine: files('mine').length };
  const head = h('div', { class: 'group-head' },
    h('div', { class: 'group-name' }, h('span', { class: 'crumb' }, g.section), h('h2', { class: 'group-title', title: g.path }, g.title)),
    h('div', { class: 'badges' }, cnt.need ? h('span', { class: 'badge badge--need' }, cnt.need + ' ' + plural(cnt.need, 'ждёт', 'ждут', 'ждут') + ' вашего выбора') : null,
      cnt.queue ? h('span', { class: 'badge badge--queue' }, cnt.queue + ' в очереди') : null, cnt.mine ? h('span', { class: 'badge badge--done' }, cnt.mine + ' ' + plural(cnt.mine, 'выбран', 'выбраны', 'выбраны') + ' вами') : null));
  const sec = h('section', { class: 'group', 'data-group': g.path }, head);
  if (g.loose) sec.append(h('p', { class: 'help', style: 'padding:0 24px 16px' }, 'Файлы, лежащие прямо в ' + g.section + '. У каждого свой язык и свои дорожки, поэтому общих настроек папки здесь нет.'));
  else sec.append(folderSettings(g));
  for (const k of ['need', 'queue', 'mine']) {
    const list = files(k); if (!list.length) continue;
    const d = h('details', { class: 'sect' }); d.open = k === seg || !!Q.trim();
    d.append(h('summary', null, icon('chev'), SECT[k], h('span', { class: k === 'need' ? 'count' : k === 'queue' ? 'badge badge--queue' : 'badge badge--done' }, list.length),
      k === 'queue' ? h('small', null, 'можно не ждать и выбрать на слух') : k === 'mine' ? h('small', null, 'здесь можно отменить выбор') : null));
    const body = h('div', { class: 'sect-body' });
    const rel = x => x.path.slice(g.path.length + 1);
    body.append(tree(list, rel, f => cardFor(f, k), g.path + '|' + k, !!Q.trim() || list.length <= 6));
    d.append(body); sec.append(d);
  }
  return [sec, cnt];
}
function redrawGroup(path) {
  const old = $('[data-group="' + CSS.escape(path) + '"]'), g = D.groups.find(x => x.path === path);
  if (!old) return;
  if (!g) { old.remove(); return; }
  old.replaceWith(groupEl(g)[0]);
}
function updateCounts() {
  const c = { need: 0, queue: 0, mine: 0 }, folders = new Set();
  for (const g of D.groups) for (const k in c) { const n = g[k].filter(x => matchQ(x.path, Q)).length; c[k] += n; if (k === 'need' && n) folders.add(g.path); }
  $$('.seg[aria-label="Показать"] button').forEach((b, i) => { const n = $('.n', b); if (n) n.textContent = c[['need', 'queue', 'mine'][i]]; });
  $('#lead').textContent = c.need ? nfiles(c.need) + ' в ' + folders.size + ' ' + plural(folders.size, 'папке', 'папках', 'папках') + ' ждут вашего решения. Чтобы синхронизировать субтитры, сервису нужно знать язык оригинала и дорожку с оригинальной речью. ' + WHEN
    : 'Сейчас от вас ничего не нужно.';
  return c;
}
function draw() {
  const list = $('#groups'); list.textContent = '';
  let any = 0;
  for (const g of D.groups) {
    const [el, cnt] = groupEl(g);
    if (!cnt[seg] && !(Q.trim() && (cnt.need + cnt.queue + cnt.mine))) continue;
    list.append(el); any++;
  }
  const c = updateCounts();
  if (!any) list.append(seg === 'need' && !Q.trim()
    ? h('div', { class: 'empty' }, h('span', { class: 'empty-mark', html: ICON.done }), h('h2', { class: 't-h2' }, 'Всё решено, сервису от вас ничего не нужно'),
      h('p', { class: 'help', style: 'max-width:64ch' }, 'У всех ' + nfiles(D.files) + ' известны язык оригинала и дорожка' + (c.queue ? ', кроме ' + c.queue + ', которые ждут автоопределения — оно идёт само, пока хватает скачиваний' : '') + '. Новые файлы появятся здесь, только если сервис не сможет решить сам.'))
    : h('p', { class: 'muted' }, Q.trim() ? 'По этому фильтру ничего нет.' : 'Здесь пока пусто.'));
}
async function init() {
  const page = $('#page');
  page.append(pageHead('Язык оригинала и дорожка', 'Загружаю…'));
  const bar = h('div', { class: 'filterbar' }, h('div', { class: 'filterline' },
    searchBox('', v => { Q = v; draw(); }),
    segmented('Показать', [['need', 'Нужен выбор', 0], ['queue', 'В очереди', 0], ['mine', 'Выбрано вами', 0]], seg, v => { seg = v; store.set('lang:seg', v); draw(); })));
  const groups = h('div', { id: 'groups', class: 'stack', style: 'gap:24px' }, placeholders(3));
  page.append(bar, groups);
  try { D = await api('/api/state'); } catch (e) { groups.replaceChildren(h('p', { class: 'err-banner' }, 'Не удалось загрузить данные: ' + e.message)); return; }
  draw();
}
init();
