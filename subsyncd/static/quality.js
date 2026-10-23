// "Журнал качества": the latest verdict for every subtitle. Read only.
'use strict';
let D = [], Q = '', verdict = store.get('quality:v', ''), order = store.get('quality:o', 'lib');
const ACT = { written: 'Записано', held: 'Отложено на проверку', test: 'Тестовый прогон, ничего не записано', failed: 'Не синхронизировано' };

function okText(r) {     // trusted rows carry no reasons: say what the measurement saw instead
  const m = r.metrics || {}, acts = m.acts || 1;
  const how = m.mode === 'chain' ? 'сверено с субтитрами оригинала' : m.mode === 'audio' ? 'сверено со звуком' : '';
  return (acts > 1 ? 'Сдвиг меняется по сценам (' + acts + ' ' + plural(acts, 'участок', 'участка', 'участков') + '), переходы подтверждены' : 'Сдвиг ровный по всей серии') + (how ? '; ' + how : '') + '.';
}
function badge(r) {
  if (r.action === 'failed') return h('span', { class: 'badge badge--bad' }, 'Ошибка');
  if (r.action === 'test') return h('span', { class: 'badge' }, 'Тест');
  return r.verdict === 'ok' ? h('span', { class: 'badge badge--done' }, 'Надёжно') : h('span', { class: 'badge badge--need' }, 'Сомнительно');
}
function draw() {
  const lib = order === 'lib';
  const sel = D.filter(r => matchQ(r.rel, Q));
  const rows = sel.filter(r => !verdict || (verdict === 'ok' ? r.verdict === 'ok' : r.verdict !== 'ok'));
  rows.sort(lib ? (a, b) => libCmp(a.rel, b.rel) || String(a.lang).localeCompare(String(b.lang)) || b.ts - a.ts : (a, b) => b.ts - a.ts);
  const segs = $$('.seg[aria-label="Вердикт"] .n');
  if (segs.length) { segs[0].textContent = sel.length; segs[1].textContent = sel.filter(r => r.verdict !== 'ok').length; segs[2].textContent = sel.filter(r => r.verdict === 'ok').length; }
  $('#note').textContent = Q.trim() ? 'Фильтр «' + Q.trim() + '»: ' + rows.length + ' из ' + D.length : '';
  const body = $('#q-body'); body.textContent = '';
  let last = null;
  for (const r of rows) {
    if (lib && dirOf(r.rel) !== last) { last = dirOf(r.rel); body.append(h('tr', { class: 'qgroup' }, h('td', { colspan: '7' }, last.split('/').join(' / ')))); }
    const reasons = (r.reasons_ru && r.reasons_ru.length ? r.reasons_ru : r.reasons);
    const failed = r.action === 'failed';
    body.append(h('tr', null,
      h('td', { class: 'fcell', title: r.rel }, lib ? r.rel.split('/').pop() : r.rel.split('/').slice(1).join(' / ')),
      h('td', { 'data-label': 'язык' }, r.lang),
      h('td', null, badge(r)),
      h('td', null, failed ? h('span', { class: 'muted' }, '—') : h('span', { class: 'scorecell' }, h('span', { class: 'meter', 'aria-hidden': 'true' },
        h('i', { style: 'width:' + Math.round(r.score * 100) + '%' + (r.verdict === 'ok' ? '' : ';background:var(--attn)') })), h('span', { class: 'num' }, num2(r.score)))),
      h('td', null, r.action === 'held' && r.id ? h('a', { href: '/review#' + r.id }, ACT.held) : (ACT[r.action] || r.action)),
      h('td', { class: 'why-cell why-list' }, reasons.length ? reasons.join(' ') : (r.verdict === 'ok' ? okText(r) : '')),
      h('td', { class: 'ncell', 'data-label': '' }, when(r.ts, true))));
  }
  if (!rows.length) body.append(h('tr', null, h('td', { colspan: '7', class: 'muted' }, D.length ? 'По этому фильтру ничего нет.' : 'Журнал пока пуст.')));
}
async function init() {
  const page = $('#page');
  page.append(pageHead('Журнал качества', 'Последняя оценка каждого субтитра. Надёжные сервис записал сам, сомнительные отложил на проверку. Здесь ничего не меняется — это история решений.'),
    h('div', { class: 'filterbar' }, h('div', { class: 'filterline' }, searchBox('', v => { Q = v; draw(); }),
      segmented('Вердикт', [['', 'Все', 0], ['review', 'Сомнительные', 0], ['ok', 'Надёжные', 0]], verdict, v => { verdict = v; store.set('quality:v', v); draw(); }),
      segmented('Порядок', [['lib', 'По библиотеке'], ['time', 'По времени']], order, v => { order = v; store.set('quality:o', v); draw(); })),
      h('span', { class: 'filter-note', id: 'note' })),
    h('div', { class: 'tablebox' }, h('table', { class: 'ftable qtable' },
      h('thead', null, h('tr', null, ['Файл', 'Язык', 'Вердикт', 'Уверенность', 'Что сделано', 'Почему', 'Когда'].map(t => h('th', { scope: 'col' }, t)))),
      h('tbody', { id: 'q-body' }, h('tr', null, h('td', { colspan: '7' }, placeholders(1)))))));
  try { D = await api('/api/quality'); } catch (e) { $('#q-body').replaceChildren(h('tr', null, h('td', { colspan: '7' }, h('p', { class: 'err-banner' }, 'Не удалось загрузить: ' + e.message)))); return; }
  draw();
}
init();
