// "Приоритеты": order of the three stages per section, folder and file. Each select saves on change; a value set on the row
// has a solid border, an inherited one a dashed border with "сейчас N, от …" under it.
'use strict';
const STAGES = [['scan', 'Сканирование', 'поиск новых и изменённых файлов'], ['download', 'Скачивание', 'тратит дневную квоту'], ['sync', 'Синхронизация', 'нагружает процессор NAS']];
let D = [], Q = '', onlyMine = false;
const open = store.get('prio:open', {});
const optsFor = level => [['', ['По умолчанию', 'Как у раздела', 'Как у папки'][level]], ['1', '1 — первым'], ['2', '2'], ['3', '3'], ['4', '4'], ['5', '5'], ['6', '6'], ['7', '7'], ['8', '8'], ['9', '9 — последним'], ['0', 'Пауза']];
const show = v => v === 0 ? 'пауза' : String(v);
const mineOf = x => STAGES.some(([s]) => x.eff[s].src === x.path);

function inheritText(x, s, level) {
  const e = x.eff[s];
  if (e.src === x.path) return 'задано здесь' + (level === 0 ? ', по умолчанию ' + e.dflt : '');
  if (e.src) return 'сейчас ' + show(e.v) + ', от ' + e.src;
  return 'сейчас ' + show(e.v) + ', общее значение';
}
function cell(x, s, label, level) {
  const own = x.eff[s].src === x.path;
  const wrap = selectBox(optsFor(level), own ? x.eff[s].v : '', { class: 'select select--sm' + (own ? '' : ' is-inherited'), 'aria-label': label + ', ' + x.path.split('/').pop() });
  const sel = wrap.querySelector('select'), note = h('span', { class: 'inherit' }, inheritText(x, s, level)), fb = fbEl();
  sel.addEventListener('change', async () => {
    const v = sel.value === '' ? null : +sel.value;
    const ok = await save(fb, () => post('/api/prio', { path: x.path, [s]: v }),
      v === 0 ? label + ' здесь остановится со следующего прохода.' : 'Действует со следующего прохода.');
    await reload(ok ? null : { x, s, sel });
  });
  return h('td', null, h('div', { class: 'pcell', 'data-stage': label, 'data-path': x.path, 'data-s': s }, wrap, note, fb));
}
function row(x, level, hasKids) {
  const name = level === 2 ? h('span', { title: x.path }, x.path.split('/').pop()) : h('b', null, x.path.split('/').pop());
  let tog = null;
  if (hasKids) {
    tog = h('button', { class: 'btn btn--quiet', type: 'button', 'aria-expanded': String(!!open[x.path]), style: 'padding:0 6px;min-height:32px', 'aria-label': 'Показать файлы' }, icon('chev'));
    if (open[x.path]) tog.firstChild.style.transform = 'rotate(90deg)';
    tog.addEventListener('click', () => { open[x.path] = !open[x.path]; store.set('prio:open', open); draw(); });
  }
  const tally = level === 0 ? 'раздел, ' + nfiles(x.count) : level === 1 ? nfiles(x.count) : null;
  return h('tr', { class: 'lvl-' + level }, h('td', { class: 'pname' }, h('div', { class: 'pname-in' }, tog, name, tally ? h('span', { class: 'tally' }, tally) : null)),
    STAGES.map(([s, label]) => cell(x, s, label, level)));
}
function draw() {
  const body = $('#prio-body'); body.textContent = '';
  const q = Q.trim();
  for (const x of D) {
    const level = x.level, files = (x.files || []).filter(f => matchQ(f.path, Q) && (!onlyMine || mineOf(f)));
    const self = (!q || matchQ(x.path, Q) || files.length) && (!onlyMine || mineOf(x) || files.length);
    if (!self) continue;
    body.append(row(x, level, (x.files || []).length > 0));
    if (open[x.path] || q || onlyMine) files.sort((a, b) => libCmp(a.path, b.path)).forEach(f => body.append(row(f, 2, false)));
  }
  const n = D.filter(mineOf).length + D.reduce((k, x) => k + (x.files || []).filter(mineOf).length, 0);
  const b = $$('.seg[aria-label="Показать"] button')[1]; if (b) $('.n', b).textContent = n;
  if (!body.childNodes.length) body.append(h('tr', null, h('td', { colspan: '4', class: 'muted' }, 'По этому фильтру ничего нет.')));
}
// After a save the inheritance of other rows may change: refresh the notes and borders in place, keep the rows and the feedback.
async function reload(revert) {
  try { D = await api('/api/prio'); } catch (e) { return; }
  const all = new Map(); D.forEach(x => { all.set(x.path, [x, x.level]); (x.files || []).forEach(f => all.set(f.path, [f, 2])); });
  for (const c of $$('.pcell')) {
    const [x, level] = all.get(c.dataset.path) || []; if (!x) continue;
    const s = c.dataset.s, own = x.eff[s].src === x.path, sel = $('select', c);
    sel.classList.toggle('is-inherited', !own); if (document.activeElement !== sel || revert) sel.value = own ? String(x.eff[s].v) : '';
    $('.inherit', c).textContent = inheritText(x, s, level);
  }
}
async function init() {
  const page = $('#page');
  page.append(pageHead('Приоритеты', 'В каком порядке сервис обходит библиотеку на трёх этапах. 1 — первым, 9 — последним, «Пауза» — не трогать. Более точный путь важнее: настройка файла перекрывает папку, папка — раздел. Каждое поле сохраняется сразу и действует со следующего прохода.'),
    h('div', { class: 'filterbar' }, h('div', { class: 'filterline' }, searchBox('', v => { Q = v; draw(); }),
      segmented('Показать', [['all', 'Всё'], ['mine', 'Только изменённые', 0]], 'all', v => { onlyMine = v === 'mine'; draw(); }))),
    h('div', { class: 'legend' }, h('span', null, h('b', null, 'Сплошная рамка'), ' — значение задано здесь.'), h('span', null, h('b', null, 'Пунктир'), ' — унаследовано; под полем указано откуда.')),
    h('div', { class: 'tablebox' }, h('table', { class: 'ptable' },
      h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Раздел, папка или файл'), STAGES.map(([, t, sub]) => h('th', { scope: 'col' }, t, h('small', null, sub))))),
      h('tbody', { id: 'prio-body' }, h('tr', null, h('td', { colspan: '4' }, placeholders(1)))))));
  try { D = await api('/api/prio'); } catch (e) { $('#prio-body').replaceChildren(h('tr', null, h('td', { colspan: '4' }, h('p', { class: 'err-banner' }, 'Не удалось загрузить: ' + e.message)))); return; }
  draw();
}
init();
