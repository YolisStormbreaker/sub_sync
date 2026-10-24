// "Не найдено": searches on OpenSubtitles that came back empty, grouped by series / film folder, with the recorded reason.
// Reasons a search hint can fix (title unknown, file name not understood) get the hint form; the rest only need waiting.
'use strict';
const R = {
  unknown: 'Название не найдено в базе', no_guess: 'Не разобрано имя файла',
  other_langs: 'Есть только на других языках', filtered: 'Всё отсеяно фильтрами', special: 'Спецвыпуск, серия 0', old: 'Причина не записана',
};
const FIX = ['unknown', 'no_guess'], WAIT = ['other_langs', 'filtered', 'special', 'old'];
let D = null, Q = '', chip = store.get('missing:chip', '');

const rows = () => D.items.filter(i => (!chip || i.code === chip) && matchQ(i.path, Q));
function groupsOf(items) {
  const m = new Map();
  for (const i of items) { if (!m.has(i.group)) m.set(i.group, []); m.get(i.group).push(i); }
  return [...m.entries()].sort((a, b) => (b[1].some(i => i.fixable) - a[1].some(i => i.fixable)) || natcmp(a[0], b[0]));
}

function hintForm(path, items) {
  const cur = items.find(i => i.hint)?.hint || null;
  const id = 'h' + Math.random().toString(36).slice(2, 8);
  const title = h('input', { class: 'input', id: id + 't', value: cur && cur.title || '' });
  const tmdb = h('input', { class: 'input num', id: id + 'n', inputmode: 'numeric', value: cur && cur.tmdb || '', placeholder: 'например, 57243' });
  const err = h('span', { class: 'feedback feedback--error', id: id + 'e', hidden: true });
  const fb = fbEl();
  const ep = items.some(i => epInfo(i.path).e != null);
  const check = () => {
    const v = tmdb.value.trim(); err.hidden = true; tmdb.removeAttribute('aria-invalid');
    if (v === '' || /^\d{1,9}$/.test(v)) return v === '' ? '' : +v;
    const d = (v.match(/\d+/g) || []).pop();
    err.replaceChildren(icon('warn'), h('span', null, 'Нужны только цифры. Номер — это число в адресе страницы: themoviedb.org/' + (ep ? 'tv' : 'movie') + '/', h('b', null, d || '…'), '.'));
    err.hidden = false; tmdb.setAttribute('aria-invalid', 'true'); tmdb.setAttribute('aria-describedby', err.id);
    return null;
  };
  tmdb.addEventListener('input', () => { if (!err.hidden) check(); });
  const send = async (t, n, note) => {
    if (await save(fb, () => post('/api/hint', { path, title: t || null, tmdb: n === '' ? null : n }), note)) { await reload(); redraw(path); }
  };
  const form = h('form', { class: 'hintform', 'aria-label': 'Подсказка для поиска: ' + path.split('/').pop() });
  const scope = h('p', { class: 'help' }, /\.[a-z0-9]{2,4}$/i.test(path) ? 'Подсказка действует только на файл ' + path.split('/').pop() + '.' : 'Подсказка действует на всю папку ' + path.split('/').slice(1).join(' / ') + '.');
  form.addEventListener('submit', e => { e.preventDefault(); const n = check(); if (n === null) { tmdb.focus(); return; }
    send(title.value.trim(), n, 'Поиск по этой папке начнётся в течение 2 минут, не дожидаясь ' + SS.retryDays + ' дней.'); });
  const now = h('div', { class: 'hint-now' });
  if (cur && (cur.title || cur.tmdb)) {
    now.append(h('span', null, 'Ваша подсказка от ' + when(cur.at) + ': ' + (cur.tmdb ? 'TMDb ' + cur.tmdb : '') + (cur.tmdb && cur.title ? ', ' : '') + (cur.title ? '«' + cur.title + '»' : '') + '.'),
      h('button', { class: 'btn btn--quiet', type: 'button', onclick: async () => { if (await save(fb, () => post('/api/hint', { path, remove: true }), 'Подсказка убрана.')) { await reload(); redraw(path); } } }, 'Убрать подсказку'));
  } else now.textContent = 'Подсказки пока нет.';
  form.append(now, scope,
    h('div', { class: 'field' }, h('label', { for: title.id }, 'Название, как в TMDb'), title, h('span', { class: 'help' }, 'Можно на любом языке, на котором его знает TMDb.')),
    h('div', { class: 'field' }, h('label', { for: tmdb.id }, 'Номер в TMDb'), tmdb, err, h('span', { class: 'help' }, 'Число из адреса themoviedb.org/' + (ep ? 'tv' : 'movie') + '/…')),
    h('div', { class: 'actions' }, h('button', { class: 'btn btn--primary', type: 'submit' }, 'Сохранить и искать снова'),
      h('button', { class: 'btn', type: 'button', onclick: () => send(cur && cur.title, cur && cur.tmdb ? cur.tmdb : '', 'Поставлено в очередь, поиск в течение 2 минут.') }, 'Искать снова без изменений'), fb));
  return form;
}

function waitNote(items) {
  const byCode = {}; items.forEach(i => (byCode[i.code] = byCode[i.code] || []).push(i));
  const out = [];
  for (const [code, list] of Object.entries(byCode)) {
    const date = when(Math.min(...list.map(i => i.retry)));
    let text;
    if (code === 'other_langs') {
      const langs = {}; list.forEach(i => Object.keys(i.others).forEach(l => langs[l] = (langs[l] || 0) + i.others[l]));
      const top = Object.entries(langs).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([l]) => l).join(', ');
      const want = [...new Set(list.map(i => i.lang))].map(l => ({ ru: 'русских', en: 'английских' }[l] || lname(l))).join(' и ');
      text = nfiles(list.length) + ': ' + (list.some(i => epInfo(i.path).e != null) ? 'эти серии есть' : 'субтитры есть') + ' на ' + top + ', но ' + want + ' субтитров пока никто не загрузил. Подсказка тут не поможет. Сервис повторит поиск сам ' + date + '.';
    } else text = nfiles(list.length) + ': ' + list[0].ru + ' Сервис повторит поиск сам ' + date + '.';
    out.push(h('div', { class: 'wait-note' }, icon('clock'), h('span', null, text)));
  }
  return out;
}

function table(items) {
  const body = h('tbody'), LIMIT = 5;
  const sorted = items.slice().sort((a, b) => relCmp(a.path, b.path) || a.lang.localeCompare(b.lang));
  const row = i => h('tr', null, h('td', { class: 'fcell', title: i.path }, i.loose ? i.path.split('/').pop() : i.path.split('/').slice(2).join(' / ')),
    h('td', { 'data-label': 'язык' }, i.lang), h('td', { class: 'ncell', 'data-label': 'искали' }, when(i.at, true)),
    h('td', { class: 'ncell', 'data-label': 'снова' }, i.soon ? 'в течение 2 мин' : when(i.retry)));
  sorted.slice(0, LIMIT).forEach(i => body.append(row(i)));
  if (sorted.length > LIMIT) {
    const more = h('tr', null, h('td', { class: 'fcell', colspan: '4' }, h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => { more.remove(); sorted.slice(LIMIT).forEach(i => body.append(row(i))); } },
      'Показать ещё ' + nfiles(sorted.length - LIMIT))));
    body.append(more);
  }
  return h('div', { class: 'tablebox', style: 'padding:0 12px 12px' }, h('table', { class: 'ftable' },
    h('thead', null, h('tr', null, ['Файл', 'Язык', 'Последний поиск', 'Следующий'].map(t => h('th', { scope: 'col' }, t)))), body));
}

function groupEl(path, items) {
  const fix = items.filter(i => i.fixable), first = items[0];
  const sec = h('section', { class: 'group', 'data-group': path },
    h('div', { class: 'group-head' }, h('div', { class: 'group-name' }, h('span', { class: 'crumb' }, first.section), h('h2', { class: 'group-title' }, first.loose ? first.title : first.title)),
      h('div', { class: 'badges' }, fix.length ? h('span', { class: 'badge badge--need' }, nfiles(fix.length) + ', можно исправить') : null,
        items.length > fix.length ? h('span', { class: 'badge badge--queue' }, nfiles(items.length - fix.length) + ', ждать') : null)));
  if (fix.length) {
    const sum = h('div', { class: 'reason-sum' });
    const seen = new Set(); fix.forEach(i => { if (!seen.has(i.code)) { seen.add(i.code); sum.append(h('p', { class: 'why' }, h('b', null, R[i.code] + '.'), ' ' + i.ru)); } });
    sec.append(sum);
    sec.append(first.loose ? h('p', { class: 'help', style: 'padding:0 24px 16px' }, 'Это отдельные файлы в разделе ' + first.section + ': подсказка здесь задела бы весь раздел. Переименуйте файл по схеме «Название год» или положите его в свою папку.')
      : hintForm(fix.length === 1 ? fix[0].path : path, fix.length === 1 ? fix : items));
  }
  const waiting = items.filter(i => !i.fixable);
  if (waiting.length) {
    sec.append(...waitNote(waiting));
    if (!fix.length && !first.loose) {
      const d = h('details', { class: 'mini', style: 'margin:0 24px 16px' }, h('summary', null, icon('chev'), 'Всё равно указать подсказку'));
      d.append(hintForm(path, items)); sec.append(d);
    }
  }
  sec.append(table(items));
  return sec;
}
function redraw(path) {
  const old = $('[data-group="' + CSS.escape(path) + '"]'); if (!old) return;
  const items = rows().filter(i => i.group === path);
  if (!items.length) old.remove(); else old.replaceWith(groupEl(path, items));
}
function drawChips() {
  const box = $('#reasons'); box.textContent = '';
  const cnt = {}; D.items.filter(i => matchQ(i.path, Q)).forEach(i => cnt[i.code] = (cnt[i.code] || 0) + 1);
  for (const [kind, codes] of [['Можно исправить', FIX], ['Нужно только ждать', WAIT]]) {
    const r = h('div', { class: 'reasons-row' }, h('span', { class: 'reasons-kind' }, kind));
    for (const c of codes) {
      if (!cnt[c]) continue;
      r.append(h('button', { class: 'chip', type: 'button', 'aria-pressed': String(chip === c), onclick: () => { chip = chip === c ? '' : c; store.set('missing:chip', chip); draw(); } },
        R[c] + ' ', h('span', { class: 'n' }, cnt[c])));
    }
    if (r.childNodes.length > 1) box.append(r);
  }
}
function draw() {
  drawChips();
  const list = $('#groups'); list.textContent = '';
  const g = groupsOf(rows());
  g.forEach(([p, items]) => list.append(groupEl(p, items)));
  const all = D.items.length, fx = D.items.filter(i => i.fixable).length;
  $('#lead').textContent = all ? all + ' ' + plural(all, 'поиск', 'поиска', 'поисков') + ' на OpenSubtitles ничего не дали. ' + (fx ? fx + ' из них можно исправить подсказкой: названием или номером в TMDb. ' : '') +
    'Остальные сервис повторит сам через ' + SS.retryDays + ' дней после последнего поиска.' : 'Все поиски что-то нашли — исправлять нечего.';
  if (!g.length && all) list.append(h('div', { class: 'collapsed-stub' }, h('span', { style: 'flex:1' }, 'По этому фильтру ничего нет.'),
    h('button', { class: 'btn btn--quiet', type: 'button', onclick: () => { chip = ''; store.set('missing:chip', ''); draw(); } }, 'Показать все причины')));
}
async function reload() { D = await api('/api/missing'); railRefresh(); }
async function init() {
  const page = $('#page');
  page.append(pageHead('Не найдено', 'Загружаю…'),
    h('div', { class: 'filterbar' }, h('div', { class: 'filterline' }, searchBox('', v => { Q = v; draw(); })), h('div', { class: 'reasons', id: 'reasons' })),
    h('div', { id: 'groups', class: 'stack', style: 'gap:24px' }, placeholders(2)));
  try { D = await api('/api/missing'); } catch (e) { $('#groups').replaceChildren(h('p', { class: 'err-banner' }, 'Не удалось загрузить: ' + e.message)); return; }
  if (chip && !D.items.some(i => i.code === chip)) chip = '';
  draw();
}
init();
