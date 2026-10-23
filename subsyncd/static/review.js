// "Проверка": subtitles the quality gate held back. List on the left, workbench on the right: listen to the original track,
// watch the lines appear on a 40 s ruler, then approve (written after an 8 s undo window), reject or have it made again.
'use strict';
const LEN = 40;
const ST = { pending: 'Ждут проверки', approved: 'Одобрено', rejected: 'Отклонено' };
const ST1 = { pending: 'Ждёт проверки', approved: 'Одобрено', rejected: 'Отклонено' };
let DATA = [], Q = '', status = 'pending', lang = '', cur = null;
const pendingWrites = new Set();   // ids approved in this tab whose write is still inside the undo window
const plain = t => t.replace(/<[^>]*>|\{\\[^}]*\}/g, '');
const subsName = l => ({ ru: 'русские', en: 'английские' }[l] || lname(l)) + ' субтитры';

function visible() {
  return DATA.filter(m => m.status === status && (!lang || m.lang === lang) && matchQ(m.rel, Q) && !pendingWrites.has(m.id))
    .sort((a, b) => libCmp(a.rel, b.rel) || a.lang.localeCompare(b.lang));
}
function drawList() {
  const box = $('#qlist'); box.textContent = '';
  const rows = visible(); let last = null;
  for (const m of rows) {
    const d = dirOf(m.rel);
    if (d !== last) { box.append(h('span', { class: 'qhead' }, d.split('/').join(' / '))); last = d; }
    box.append(h('button', { class: 'qitem', type: 'button', 'aria-current': String(cur && cur.id === m.id), onclick: () => select(m.id) },
      h('b', null, m.rel.split('/').pop()), h('span', { class: 'row' }, h('span', null, subsName(m.lang)), h('span', { class: 'num' }, 'уверенность ' + num2(m.score)))));
  }
  if (!rows.length) box.append(h('p', { class: 'muted', style: 'padding:12px 14px' }, Q.trim() ? 'По фильтру ничего нет.' : 'Здесь пусто.'));
  const n = k => DATA.filter(m => m.status === k && !pendingWrites.has(m.id)).length;
  $$('.seg[aria-label="Статус"] button').forEach((b, i) => { $('.n', b).textContent = n(['pending', 'approved', 'rejected'][i]); });
  $('#lead').textContent = n('pending') ? n('pending') + ' ' + plural(n('pending'), 'субтитр задержан', 'субтитра задержаны', 'субтитров задержаны') +
    ': сервис не уверен, что время подогнано точно. Послушайте оригинальную дорожку и посмотрите, появляются ли строки вместе с речью. Текст субтитров не меняется, только время.'
    : 'Сейчас ничего не ждёт проверки.';
}
function select(id) {
  cur = DATA.find(m => m.id === id) || null;
  if (cur) history.replaceState(null, '', '#' + cur.id);
  Player.stop(); drawList(); drawBench();
}

function drawBench() {
  const bench = $('#bench'); bench.textContent = '';
  const rows = visible();
  if (!cur || !rows.includes(cur)) cur = rows[0] || null;
  if (!cur) { bench.append(h('p', { class: 'muted' }, 'Выберите субтитр в списке.')); return; }
  const m = cur, idx = rows.indexOf(m);
  bench.append(h('div', { class: 'bench-head' },
    h('div', { class: 'stack', style: 'gap:4px;min-width:0' }, h('span', { class: 'crumb' }, dirOf(m.rel).split('/').join(' / ')),
      h('h2', { class: 't-h2', style: 'overflow-wrap:anywhere' }, m.rel.split('/').pop()),
      h('div', { class: 'badges' }, h('span', { class: 'badge' }, subsName(m.lang)),
        h('span', { class: 'badge ' + (m.status === 'pending' ? 'badge--need' : m.status === 'approved' ? 'badge--done' : 'badge--bad') }, ST1[m.status]))),
    h('div', { class: 'pager' },
      h('button', { class: 'btn btn--quiet', type: 'button', disabled: idx <= 0, onclick: () => select(rows[idx - 1].id) }, 'Назад'),
      h('span', { class: 'num' }, (idx + 1) + ' из ' + rows.length),
      h('button', { class: 'btn btn--quiet', type: 'button', disabled: idx >= rows.length - 1, onclick: () => select(rows[idx + 1].id) }, 'Дальше'))));
  const reasons = (m.reasons_ru && m.reasons_ru.length ? m.reasons_ru : m.reasons);
  bench.append(h('div', { class: 'stack', style: 'gap:10px' },
    h('ul', { class: 'held-why' }, (reasons.length ? reasons : ['Сам алгоритм доверяет результату; субтитр удержан по запросу.']).map(r => h('li', null, icon('warn'), h('span', null, r)))),
    h('div', { class: 'conf' }, h('span', null, 'Уверенность'), h('div', { class: 'meter', 'aria-hidden': 'true' }, h('i', { style: 'width:' + Math.round(m.score * 100) + '%' })),
      h('span', { class: 'num' }, h('b', null, num2(m.score)), ' из 1' + (m.threshold ? ', автоматически пишется от ' + num2(m.threshold) : '')))));
  if (m.status !== 'approved') bench.append(workbench(m));
  bench.append(decideBar(m));
}

function workbench(m) {
  const now = h('p', { class: 'sub-now' }, 'Выберите точку и нажмите «Слушать»'), next = h('p', { class: 'sub-next' });
  const ruler = h('div', { class: 'ruler', title: 'Нажмите, чтобы перейти в это место' }, h('span', { class: 'ruler-base' }));
  const head = h('span', { class: 'playhead', style: 'left:0' }), time = h('span', { class: 'time num' }, '0:00 ', h('span', null, '/ 0:00'));
  const big = h('button', { class: 'bigplay', type: 'button', 'aria-label': 'Слушать' }, icon('play'));
  let cues = [], t0 = (m.points || [0])[0], loaded = false;
  const chips = h('div', { class: 'points' }, h('span', { class: 'small', style: 'color:var(--ink-2)' }, 'Слушать с точки, где сервис сомневается:'));
  const tick = a => {
    const t = a.currentTime || 0; head.style.left = Math.min(100, t / LEN * 100) + '%';
    const on = cues.filter(x => x.s <= t && t <= x.e), nx = cues.find(x => x.s > t);
    now.textContent = on.length ? on.map(x => plain(x.text)).join('\n') : '—';
    next.textContent = ''; if (nx) next.append('Следующая строка через ', h('b', null, num2(nx.s - t).replace(/,?0+$/, '') + ' с'), ': «' + plain(nx.text).replace(/\n/g, ' ') + '»');
    $$('.cue', ruler).forEach((c, i) => c.classList.toggle('is-now', cues[i] && cues[i].s <= t && t <= cues[i].e));
    time.firstChild.textContent = clock(t0 + t) + ' '; time.lastChild.textContent = '/ ' + clock(t0 + LEN);
  };
  async function load(p, autoplay) {
    t0 = p; loaded = true;
    $$('.chip', chips).forEach(c => c.setAttribute('aria-pressed', String(+c.dataset.t === p)));
    now.textContent = 'Готовлю фрагмент, 1–3 секунды…'; next.textContent = '';
    try { cues = await api('/api/review/' + m.id + '/cues?t=' + p + '&len=' + LEN); } catch (e) { now.textContent = 'Не получилось: ' + e.message; return; }
    $$('.cue, .tick', ruler).forEach(x => x.remove());
    cues.forEach(x => ruler.insertBefore(h('span', { class: 'cue', style: 'left:' + Math.max(0, x.s) / LEN * 100 + '%;width:' + Math.max(0.4, (Math.min(LEN, x.e) - Math.max(0, x.s)) / LEN * 100) + '%' }), head));
    [0, 25, 50, 75, 97].forEach((x, i) => ruler.append(h('span', { class: 'tick', style: 'left:' + x + '%' }, clock(p + i * LEN / 4))));
    if (autoplay !== false) Player.play('/api/review/' + m.id + '/clip?t=' + p + '&len=' + LEN, big, (state, a, err) => {
      if (state === 'loading') { big.replaceChildren(icon('spin')); big.setAttribute('aria-label', 'Фрагмент готовится'); }
      else if (state === 'playing') { big.replaceChildren(icon('pause')); big.setAttribute('aria-label', 'Пауза'); }
      else if (state === 'error') { big.replaceChildren(icon('play')); now.textContent = 'Не получилось: ' + err; }
      else if (state !== 'tick') { big.replaceChildren(icon('play')); big.setAttribute('aria-label', 'Слушать'); }
      tick(a);
    });
  }
  (m.points || [0]).forEach(p => chips.append(h('button', { class: 'chip', type: 'button', 'aria-pressed': 'false', 'data-t': p, onclick: () => load(p) }, clock(p))));
  big.addEventListener('click', () => { if (loaded && Player.isOwner(big)) Player.toggle(); else load(t0); });
  ruler.addEventListener('click', e => {
    if (!loaded || !Player.a) return;
    const r = ruler.getBoundingClientRect(); Player.a.currentTime = Math.max(0, Math.min(LEN - 0.1, (e.clientX - r.left) / r.width * LEN));
    if (Player.a.paused) Player.toggle();
  });
  ruler.append(head);
  const back5 = h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => { if (Player.a && loaded) Player.a.currentTime = Math.max(0, Player.a.currentTime - 5); } }, 'Назад на 5 с');
  const again = h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => {
    if (!Player.a || !loaded) return; const t = Player.a.currentTime, c = cues.filter(x => x.s <= t).pop();
    Player.a.currentTime = Math.max(0, c ? c.s - 0.3 : t - 3); if (Player.a.paused) Player.toggle();
  } }, 'Повторить строку');
  const screen = h('div', { class: 'screen' }, h('div', { class: 'sub-stage', 'aria-live': 'polite' }, now, next), ruler,
    h('div', { class: 'transport' }, big, time, back5, again,
      h('span', { class: 'ruler-legend', style: 'margin-left:auto' }, h('span', null, h('i', { style: 'background:var(--screen-cue)' }), 'строка'),
        h('span', null, h('i', { style: 'background:var(--screen-cue-now)' }), 'звучит сейчас'))));
  load(t0, false);
  return h('div', { class: 'stack', style: 'gap:20px' }, chips, screen);
}

function decideBar(m) {
  const bar = h('div', { class: 'decide' }), fb = fbEl(), slot = h('div', { style: 'flex-basis:100%' });
  const go = async (action, okText) => {
    if (!await save(fb, () => post('/api/review/' + m.id, { action }), okText)) return;
    await reload();
  };
  if (m.status === 'pending' || m.status === 'rejected') {
    bar.append(h('button', { class: 'btn btn--primary btn--lg', type: 'button', onclick: () => approve(m) }, 'Одобрить и записать рядом с видео'));
  }
  if (m.status === 'pending') bar.append(h('button', { class: 'btn btn--danger btn--lg', type: 'button', onclick: () => go('reject', 'Отклонено. Рядом с видео ничего не записано.') }, 'Отклонить'));
  bar.append(h('span', { class: 'spacer' }));
  if (m.status === 'approved') bar.append(h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => go('retry', 'Убрано из списка.') }, 'Убрать из списка'));
  else bar.append(h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => {
    slot.replaceChildren(confirmBox({ title: 'Сделать субтитр заново?', body: 'Текущий результат удалится. Сервис соберёт субтитр заново на следующем проходе, сегодня ночью. Рядом с видео ничего не меняется.',
      yes: 'Да, сделать заново', no: 'Оставить как есть', onYes: () => go('retry', 'Удалено; субтитр будет собран заново на следующем проходе.') }));
  } }, 'Сделать заново…'));
  bar.append(slot, fb);
  if (m.status !== 'approved') bar.append(h('p', { class: 'decide-note' }, '«Одобрить» записывает ' + m.srt + ' рядом с видео — текст байт в байт как скачан. 8 секунд можно отменить. ' +
    (m.status === 'pending' ? '«Отклонить» ничего не пишет; субтитр останется в списке отклонённых.' : '')));
  return bar;
}

// Approve: the write happens after an 8 s window with "Отменить"; closing the tab inside the window still sends it.
function approve(m) {
  pendingWrites.add(m.id); Player.stop();
  const rows = visible(); cur = rows[0] || null; drawList(); drawBench();
  toast('Одобрено. Файл ' + m.srt + ' будет записан рядом с видео.', {
    seconds: 8,
    undo: () => { pendingWrites.delete(m.id); cur = m; drawList(); drawBench(); },
    commit: async closing => {
      try {
        await post('/api/review/' + m.id, { action: 'approve' }, closing ? { keepalive: true } : {});
        if (!closing) toast('Записано рядом с видео: ' + m.srt);
      } catch (e) { if (!closing) toast('Не записано: ' + e.message, { iconName: 'warn' }); }
      pendingWrites.delete(m.id); if (!closing) reload();
    },
  });
}

async function reload() {
  DATA = await api('/api/review'); railRefresh();
  const langs = [...new Set(DATA.filter(m => m.status === status).map(m => m.lang))].sort();
  const lg = $('#lang-seg'); lg.replaceWith(Object.assign(segmented('Язык', [['', 'Все языки']].concat(langs.map(l => [l, l, DATA.filter(m => m.status === status && m.lang === l).length])), lang,
    v => { lang = v; drawList(); drawBench(); }), { id: 'lang-seg' }));
  if (cur) cur = DATA.find(m => m.id === cur.id) || null;
  drawList(); drawBench();
}
async function init() {
  const page = $('#page'); page.style.maxWidth = '1120px';
  page.append(pageHead('Проверка субтитров', 'Загружаю…'),
    h('div', { class: 'filterbar' }, h('div', { class: 'filterline' },
      searchBox('', v => { Q = v; drawList(); drawBench(); }),
      segmented('Статус', [['pending', ST.pending, 0], ['approved', ST.approved, 0], ['rejected', ST.rejected, 0]], status, v => { status = v; lang = ''; reload(); }),
      h('div', { id: 'lang-seg' }))),
    h('div', { class: 'review' }, h('nav', { class: 'qlist', id: 'qlist', 'aria-label': 'Задержанные субтитры' }), h('section', { class: 'bench', id: 'bench' }, placeholders(1))));
  try { DATA = await api('/api/review'); } catch (e) { $('#bench').replaceChildren(h('p', { class: 'err-banner' }, 'Не удалось загрузить: ' + e.message)); return; }
  const want = location.hash.slice(1); if (want) { const m = DATA.find(x => x.id === want); if (m) { cur = m; status = m.status; $$('.seg[aria-label="Статус"] button').forEach((b, i) => b.setAttribute('aria-pressed', String(['pending', 'approved', 'rejected'][i] === status))); } }
  await reload();
}
init();
