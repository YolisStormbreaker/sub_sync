# Subsync panel — redesign handoff

Design for the brief in `docs/subsync-panel-design-brief.md`. This folder is the source of truth for the code redesign; the same files are published as a Design canvas on claude.ai (private to the owner).

## 1. Direction

**"Монтажный стол" (flatbed editing bench).** Olive-enamel surfaces, a sage green for "this is the original / write it", an amber cue light for "needs your decision", blue for "the service is still working on it", red for reject. One dark playback screen (review workbench) stays dark in both themes. Boldness is spent in one place: the review screen with the large subtitle line and the cue ruler. Everything else is quiet and dense.

## 2. Files

| File | What it is |
|---|---|
| `subsync.css` | Tokens (both themes) and every component class. Written to be lifted into the Python-served pages almost as is. No framework, no build step. |
| `icon.svg` | App icon. Same shape as the current one; only colours changed (frame and lines `#7DCE9B`, tile `#161D19`, waveform `#F2F5F0`). Also used inline in the rail. |
| `Main.dc.html` | Direction, palette for both themes, type scale, spacing, radii, principles. |
| `Components.dc.html` | Component sheet: track row in all states, audio control, save feedback, error, confirmation, undo toast, collapsed card stub, filter bar, reason chips, segmented control, tree node, status badges, service status (desktop and phone). |
| `Language.dc.html` | `/` — language and track queue. Group expanded with collapsed and expanded sections, two-track card (track 1 playing), card after a label settled the original, six-track card with 2 candidates left, language-unknown card, collapsed groups. |
| `Empty.dc.html` | `/` empty state. |
| `Review.dc.html` | `/review` — list + workbench, clip playing, current line shown. |
| `Missing.dc.html` | `/missing` — reason filter "Название не найдено в базе" active, two groups with hint forms (one with a TMDb validation error). |
| `Priorities.dc.html` | `/prio` — table with inheritance, per-control save feedback and a save error. |
| `Quality.dc.html` | `/quality` — grouped by library, filtered. |
| `*-light.dc.html`, `*-phone.dc.html` | Canvas wrappers that mount the screen above with `theme="light"` or at 390 px. They only work inside the canvas; open the main file instead. |
| `canvas.json` | Canvas layout. Not needed for code. |

**How to read a `.dc.html` file.** It is plain HTML. Ignore the `<script src="./support.js">` line, the `<x-dc>` / `<helmet>` wrappers and the trailing `<script type="text/x-dc">` block — they belong to the canvas runtime. The markup inside `<x-dc>` is the reference markup, using classes from `subsync.css`. Opening the file directly in a browser works: `data-theme="{{theme}}"` matches neither theme, so the page follows `prefers-color-scheme`.

Mock data is representative, not real; the shapes follow the API fields listed in the brief.

## 3. Tokens

All tokens are CSS custom properties on `.ss` (the page root). `data-theme="light"` / `"dark"` forces a theme; no attribute follows the OS. Values are in `subsync.css` and on `Main.dc.html`.

- Neutrals: `--ground` (page), `--surface` (rail, group), `--raised` (card, input), `--sunken` (wells, bars, hover), `--ink`, `--ink-2`, `--ink-3`, `--rule`, `--rule-strong`.
- Meaning: `--accent` (+ `-hover`, `-soft`, `-ink`, `--on-accent`) original / approve / primary; `--attn` (+ `-soft`) needs your decision; `--info` (+ `-soft`) queued, waiting on the service; `--danger` (+ `-soft`) reject, destructive, errors.
- Playback screen, theme-independent: `--screen`, `--screen-ink`, `--screen-ink-2`, `--screen-cue`, `--screen-cue-now`.
- Radii: `--r-control` 3 px (inputs, buttons), `--r-card` 6 px (cards, groups), `--r-pill` (chips, badges). Round play buttons are 44 px circles.
- Spacing: 4 · 8 · 12 · 16 · 24 · 32 · 48.
- No shadows except the toast and the settled-card ring. Depth comes from surface tone plus a 1 px rule.
- **CSS specificity rule:** element resets (`button`, `input`, `select`, `a`) are wrapped in `:where(.ss)` so they have zero specificity. Never write them as `.ss button`: that beats `.btn--primary` and turns the button text into the inherited ink colour (white on mint in dark, black on green in light).
- Light `--ink` is `#24302A` and `--accent` is `#217A50` (white text on it 5,3:1); pure near-black read too harsh on the green-grey ground.
- Contrast: `--ink-3` is ≥ 5.3:1 on `--surface` in both themes; badge text on its soft fill is ≥ 4.5:1. Recheck if you change a value.

**Type.** One family: **Golos Text** (OFL, has Cyrillic), weights 400/500/600/700. Fallback stack `"PT Root UI", "PT Sans", system-ui, …`. The NAS page may be opened offline, so embed it: subset to Latin + Cyrillic + punctuation (`pyftsubset … --unicodes="U+0000-00FF,U+0400-045F,U+2010-2027,U+2116" --flavor=woff2`), base64 it into one `@font-face` per weight, or serve the woff2 from the same Python server. The canvas uses a Google Fonts link only for preview. Scale (px, line-height): display 36/40, h1 30/34, h2 23/28, h3 18/24, body 16/23, small 14/20, caption 13/18, subtitle line 32/40 (24 on phone). Times and counters use `font-variant-numeric: tabular-nums` (`.num`). No all-caps labels.

## 4. Shell and navigation

- Desktop: left rail 272 px (brand, nav with badges, service status) + content column, max 1080 px (review 1120 px).
- Nav order follows the work: Язык и дорожка, Проверка, Не найдено, Приоритеты, Журнал качества.
- Badges (`.count`, amber) count only what waits for the user: language page = files needing a choice; review = pending items; not found = fixable entries only (title unknown + name unparseable). Pages with nothing to do show no badge.
- Service status (missing today): running / not responding; last nightly run (start time, duration, written / held / not found); downloads used today of 100 with a meter and the reset time. Source: `daily`, `quota` in `/api/state` — it is needed on every page, so expose it from a small shared endpoint or include it in each page's payload.
- **Times are shown in the browser's local time.** 00:05 UTC is displayed as 03:05 and the quota reset as 03:00 for Moscow. Assumption: the owner reads local time; UTC is not mentioned in the UI.
- Phone (≤ 720 px, via container query on `.ss`): rail becomes a header with the icon, a one-line status (`.status-mini`) and a horizontally scrolling tab row. The tabs sit on the header's bottom edge; the selected tab's fill (`--accent-soft`, 8 px top corners, square bottom) runs down to that edge. Edges fade with a mask to hint at scrolling, and on load the current tab is scrolled into view (`nav.scrollLeft = current.offsetLeft - 16`, or `scrollIntoView({inline: 'nearest'})`). Tables turn into stacked rows. Track rows go to three lines (play + name / score / language + action).

## 5. Screens → data

### Language (`/`)

- Top segmented control switches between the three sections across all groups (Нужен выбор / В очереди / Выбрано вами) with counts; inside each group the three sections are also present as `<details>` (needs-choice open by default).
- Group header: section as a crumb, group name as title, status badges. Loose files directly in `Movies` are grouped as **"Movies / Отдельные фильмы"**, and that group has no folder-level settings (per brief this is allowed).
- Folder settings: language select and track select, each saves on change and shows the feedback line underneath. Under the track select, the layouts from `layouts[]` in words ("2 без языка — 58 файлов"). Choosing "Всегда дорожка N" opens the confirmation pattern ("Вы послушали несколько серий? …") before saving.
- Season folders are tree nodes (`.node`) with counts; open state persisted per tree in `localStorage`.
- File card: `fname` with full path in `title`; meta (duration, track count); one plain-Russian sentence from `lines[]` (`.why`); the A/B moment strip; track rows; collapsed "Другой язык оригинала для этого файла" (open when `lang` is unknown).
- **A/B moment strip** (`.moment`): one shared position for all tracks of the file, shown as a time and on a little scale with the five fragment positions (15, 30, 50, 70, 85 %). Play on any track plays from that moment; switching tracks keeps the moment. "Другой фрагмент" advances to the next position for all tracks.
- Track row: play button, "Дорожка N" (1-based) + codec/channels + tag or label source, speech-match score bar from `auto.scores` (best one in accent, with "лучшая, но не уверенно" when margin < 0,03), track-language select (only when the file has ≥ 2 tracks; saves immediately), "Это оригинал" (saves immediately). Render exactly `tracks.length` rows.
- After a label: if the service deduces the original, the card gets `.card--settled` and the green `.verdict` block naming the conclusion and why, with "Подтвердить: оригинал — дорожка N" and "Выбрать другую". It leaves the queue only after confirmation. If nothing is settled, show the blue `.cands` line ("Осталось 2 кандидата: дорожки 3 и 5 …") and mark candidate rows (`.is-candidate`); labelled rows are dimmed (`.is-labelled`).

### Review (`/review`)

- Desktop: list on the left (grouped by path, current item outlined), workbench on the right. Phone: list hidden, the workbench has "Назад / 1 из 17 / Дальше".
- Workbench: crumb + file name, language and status badges; reasons from `reasons_ru` as a list; confidence meter with the auto-write threshold in words; start points from `points` as chips.
- Screen: current line large and centred, next line with the time until it, ruler for the 40 s window (`/cues?t=&len=`): one block per cue, the current cue in bright green, white playhead, five time ticks. Clicking the ruler seeks. Transport: play/pause, time, "Назад на 5 с", "Повторить строку".
- Decision bar: "Одобрить и записать рядом с видео" (primary), "Отклонить", "Сделать заново…" (quiet, opens confirmation). On phone the bar is sticky at the bottom so the thumb reaches it. Note under the buttons names the exact file that will be written.
- For approved items the quiet action is "Убрать из списка".

### Not found (`/missing`)

- Reason chips split into two labelled rows: **Можно исправить** (title unknown, name unparseable) and **Нужно только ждать** (other languages only, everything filtered, special episode 0, reason not recorded). One chip active at a time; clicking the active one clears it.
- Fixable groups: reason sentence, current hint (with "Убрать подсказку"), form with title + TMDb number. Validate the number client-side (`^\d+$`); on a URL or "tv/123" paste, show the error under the field naming the digits to keep. Buttons: "Сохранить и искать снова", "Искать снова без изменений".
- Waiting groups: no form as the main action. Show the blue `.wait-note` ("… русских субтитров пока никто не загрузил. Подсказка тут не поможет. Сервис повторит поиск сам 30 октября.") and keep the hint form behind a collapsed "Всё равно указать подсказку".
- File table: file, language, last search, next search (`retry`). Dates in Russian ("21 октября", "сегодня, 03:41").

### Priorities (`/prio`)

- Three columns: Сканирование, Скачивание (тратит дневную квоту), Синхронизация (нагружает процессор NAS). Options: По умолчанию / Как у раздела / Как у папки, 1 — первым … 9 — последним, Пауза.
- A value set on this row has a solid border; an inherited one has a dashed border (`.is-inherited`) and a line under it: "сейчас 3, от TVshows" (`v` and `src`).
- Each select saves on change and shows feedback in place (saving → saved → fades after 4 s; errors stay until the next change). No row-level OK button.

### Quality log (`/quality`)

- Segmented filters: verdict (Все / Сомнительные / Надёжные, with counts) and order (По библиотеке / По времени). Library order groups rows under folder header rows; time order drops the headers and sorts by `ts` descending.
- Columns: file, language, verdict badge, confidence (meter + number), action, reasons, time. On phone each row is a wrapping flex line with one left edge: file name, then language, verdict, score and action inline, then reasons and time on their own lines — so badges in different rows start at the same x. "Отложено на проверку" links to the item on `/review`.

## 6. Behaviour

- **Every save confirms what changed and when it takes effect**, next to the control: "Сохранено. Применится на следующем проходе: новые файлы — в течение 2 минут, старая библиотека — сегодня ночью." Saving shows "Сохраняю…" with the spinner; the control stays enabled.
- **No viewport jumps.** Never re-render the page after a save. Mutate the affected card only. Before removing a card, pin its height, replace the content with the one-line `.collapsed-stub` ("doctor.who.s03e03.avi: оригинал — дорожка 2. Перенесено в «Выбрано вами». [Отменить]"), then animate the stub's height to 44 px over 180 ms. Keep the stub until the group is re-rendered on the next page load. If the removed card is above the viewport, compensate `scrollTop` by the height delta.
- **Focus moves to the next card**: after "Это оригинал" or "Подтвердить", focus goes to the first play button of the next card in the same section (or the section summary when it was the last). With `prefers-reduced-motion`, skip the height animation.
- **Undo.** "Approve" in review starts an 8-second toast ("Одобрено. Файл … будет записан рядом с видео. через 8 с [Отменить]") and only then calls the API — the file is written after the window. This is a deferred client-side commit; if the tab closes inside the window, send the request on `pagehide` via `fetch(..., {keepalive: true})`. Track choices are undone from the collapsed stub or from "Выбрано вами".
- **Confirmation** is inline (`.confirm`), never `confirm()`: "Сделать заново" and "Всегда дорожка N для папки". "Отклонить" writes nothing, so it needs no confirmation.
- **Errors**: HTTP 400 text is shown under the control that caused it (`.feedback--error`), value reverted, never `alert()`.
- **Audio.** One shared `<audio>` element for the whole page. Clicking play on a row: the button becomes a spinner and the row says "Готовлю фрагмент, 1–3 секунды…"; on `canplay` it switches to pause, the row shows "Играет 0:07 из 0:20" and a progress line along the bottom edge. Starting another clip stops the current one. Keyboard: Space toggles the focused play button (native button behaviour, no global handlers).
- **Page loading**: keep the shell and rail, show the page header and three grey placeholder groups with fixed heights; never a blank page.
- **Long names** wrap (`overflow-wrap: anywhere`) in titles and tables, and carry the full path in `title`.
- **Numbers**: decimal comma (0,87), dates like "23 октября", "сегодня, 03:12".
- **Accessibility**: real buttons, labels and `aria-pressed` on toggles; status never by colour alone (badges carry words); focus ring is 2 px `--accent`; targets ≥ 44 px on phone.

## 7. Copy

Keys are suggestions. Placeholders in braces.

| Key | Russian |
|---|---|
| nav.language | Язык и дорожка |
| nav.review | Проверка |
| nav.missing | Не найдено |
| nav.prio | Приоритеты |
| nav.quality | Журнал качества |
| brand.tagline | Субтитры для домашней библиотеки |
| status.running | Сервис работает |
| status.running.short | Работает |
| status.down | Сервис не отвечает с {time}. Решения сохраняются, но применятся после перезапуска. |
| status.night.title | Ночной проход |
| status.night.when | сегодня в {time}, занял {duration} |
| status.night.written | записано |
| status.night.held | отложено на проверку |
| status.night.missing | не найдено |
| status.quota | Скачивания сегодня: {used} из {limit} |
| status.quota.note | Счётчик обнулится в {time}. Новые файлы проверяются каждые 2 минуты. |
| filter.placeholder | Название или серия: s06e05, 6x05, s06, e05 |
| filter.result | Найдено {n} файлов в {m} папках |
| lang.title | Язык оригинала и дорожка |
| lang.lead | {n} файлов в {m} папках ждут вашего решения. Чтобы синхронизировать субтитры, сервису нужно знать язык оригинала и дорожку с оригинальной речью. Решение применяется на следующем проходе: новые файлы — в течение 2 минут, старая библиотека — сегодня ночью. |
| lang.sect.need | Нужен ваш выбор |
| lang.sect.queue | В очереди на автоопределение |
| lang.sect.queue.hint | можно не ждать и выбрать на слух |
| lang.sect.mine | Выбрано вами |
| lang.sect.mine.hint | здесь можно отменить выбор |
| lang.folder.lang | Язык оригинала для всей папки |
| lang.folder.lang.auto | Не задан: определять автоматически |
| lang.folder.lang.saved | Указан вами. Действует на все {n} файлов папки, кроме тех, где язык задан отдельно. |
| lang.folder.track | Дорожка оригинала для всей папки |
| lang.folder.track.perfile | Решать по каждому файлу |
| lang.folder.track.always | Всегда дорожка {n} |
| lang.folder.track.help | «Всегда дорожка N» подходит, только если оригинал во всех сериях на одном месте; перед сохранением попросим подтвердить, что вы послушали несколько серий. |
| lang.folder.track.confirm.title | Дорожка {n} для всех {count} файлов папки? |
| lang.folder.track.confirm.body | Выбирайте так, только если послушали несколько серий и везде оригинал на этом месте. Уже выбранные вами файлы не изменятся. |
| lang.folder.track.confirm.yes | Да, всегда дорожка {n} |
| lang.loose.title | Отдельные фильмы |
| lang.loose.help | Файлы, лежащие прямо в Movies. У каждого свой язык и свои дорожки, поэтому общих настроек папки здесь нет. |
| lang.moment | Обе дорожки играют с {time}, {where} |
| lang.moment.many | Все дорожки играют с {time}, {where} |
| lang.moment.where.50 | середина серии / середина фильма |
| lang.moment.next | Другой фрагмент |
| track.name | Дорожка {n} |
| track.untagged | язык не указан |
| track.labelled | {lang} — указали вы |
| track.score | Совпадение речи |
| track.score.best | лучшая, но не уверенно |
| track.score.none | Ещё не сравнивали |
| track.score.excluded | Не участвует в сравнении |
| track.lang | Язык: {lang} |
| track.lang.none | Язык: не указан |
| track.original | Это оригинал |
| track.loading | Готовлю фрагмент, 1–3 секунды… |
| track.playing | Играет {pos} из {len} |
| verdict.title | Оригинал — дорожка {n} |
| verdict.reason.lastUnlabelled | Вы указали: {labels}. Других дорожек без языка, кроме {nth}, нет, поэтому оригинал — она. |
| verdict.reason.foreignLabel | Вы указали: дорожка {n} — {lang}. Это первая дорожка не на русском, поэтому оригинал — она. |
| verdict.confirm | Подтвердить: оригинал — дорожка {n} |
| verdict.other | Выбрать другую |
| verdict.after | После подтверждения файл перейдёт в «Выбрано вами», субтитры синхронизируются на следующем проходе. |
| cands | Осталось {n} кандидата: дорожки {list}. |
| cands.body | Автоопределение сравнит только их, когда дойдёт очередь, — или выберите на слух сейчас. |
| file.lang.toggle | Другой язык оригинала для этого файла |
| file.lang.toggle.unknown | Язык оригинала для этого файла |
| file.lang.saved | Сохраняется сразу. Сервис скачает субтитры на этом языке на следующем проходе. |
| stub.decided | {file}: оригинал — дорожка {n}. Перенесено в «Выбрано вами». |
| undo | Отменить |
| empty.lang.title | Всё решено, сервису от вас ничего не нужно |
| empty.lang.body | У всех {n} файлов известны язык оригинала и дорожка. {q} файлов ждут автоопределения — оно идёт само, пока хватает скачиваний. Новые файлы появятся здесь, только если сервис не сможет решить сам. |
| save.saving | Сохраняю… |
| save.saved | Сохранено |
| save.when | Применится на следующем проходе: новые файлы — в течение 2 минут, старая библиотека — сегодня ночью. |
| save.failed | Не сохранилось: {server message}. Значение прежнее. |
| save.unreachable | Не сохранилось: сервис не ответил. Значение прежнее. |
| review.title | Проверка субтитров |
| review.lead | {n} субтитров задержаны: сервис не уверен, что время подогнано точно. Послушайте оригинальную дорожку и посмотрите, появляются ли строки вместе с речью. Текст субтитров не меняется, только время. |
| review.status.pending / approved / rejected | Ждут проверки / Одобрено / Отклонено |
| review.confidence | {score} из 1, автоматически пишется от {threshold} |
| review.points | Слушать с точки, где сервис сомневается: |
| review.next | Следующая строка через {sec} с: «{text}» |
| review.idle | Выберите точку и нажмите «Слушать» |
| review.back5 | Назад на 5 с |
| review.repeat | Повторить строку |
| review.approve | Одобрить и записать рядом с видео |
| review.reject | Отклонить |
| review.retry | Сделать заново… |
| review.remove | Убрать из списка |
| review.note | «Одобрить» записывает {srt} рядом с видео — текст байт в байт как скачан. 8 секунд можно отменить. «Отклонить» ничего не пишет; субтитр останется в списке отклонённых. |
| review.toast.approved | Одобрено. Файл {srt} будет записан рядом с видео. |
| review.toast.written | Записано рядом с видео: {srt} |
| review.toast.rejected | Отклонено. Рядом с видео ничего не записано. |
| review.retry.title | Сделать субтитр заново? |
| review.retry.body | Текущий результат удалится. Сервис соберёт субтитр заново на следующем проходе, сегодня ночью. Рядом с видео ничего не меняется. |
| review.retry.yes | Да, сделать заново |
| review.retry.no | Оставить как есть |
| missing.title | Не найдено |
| missing.lead | {n} поисков на OpenSubtitles ничего не дали. {f} из них можно исправить подсказкой: названием или номером в TMDb. Остальные сервис повторит сам через 7 дней после последнего поиска. |
| missing.kind.fix | Можно исправить |
| missing.kind.wait | Нужно только ждать |
| missing.reason.unknown_title | Название не найдено в базе |
| missing.reason.unparsed | Не разобрано имя файла |
| missing.reason.other_langs | Есть только на других языках |
| missing.reason.filtered | Всё отсеяно фильтрами |
| missing.reason.special | Спецвыпуск, серия 0 |
| missing.reason.unknown | Причина не записана |
| missing.hint.none | Подсказки пока нет. |
| missing.hint.current | Ваша подсказка от {date}: «{hint}». |
| missing.hint.title | Название, как в TMDb |
| missing.hint.title.help | Можно на любом языке, на котором его знает TMDb. |
| missing.hint.id | Номер в TMDb |
| missing.hint.id.help | Число из адреса themoviedb.org/movie/… или /tv/… |
| missing.hint.id.error | Нужны только цифры. Номер — это число в адресе страницы: themoviedb.org/tv/{digits}. |
| missing.hint.save | Сохранить и искать снова |
| missing.hint.retry | Искать снова без изменений |
| missing.hint.remove | Убрать подсказку |
| missing.hint.after | Поиск по этой папке начнётся в течение 2 минут, не дожидаясь 7 дней. |
| missing.wait.other_langs | {n} файлов: эти серии есть на {langs}, но {lang} субтитров пока никто не загрузил. Подсказка тут не поможет. Сервис повторит поиск сам {date}. |
| missing.wait.hintAnyway | Всё равно указать подсказку |
| missing.col.file / lang / last / next | Файл / Язык / Последний поиск / Следующий |
| prio.title | Приоритеты |
| prio.lead | В каком порядке сервис обходит библиотеку на трёх этапах. 1 — первым, 9 — последним, «Пауза» — не трогать. Более точный путь важнее: настройка файла перекрывает папку, папка — раздел. Каждое поле сохраняется сразу и действует со следующего прохода. |
| prio.col.scan | Сканирование — поиск новых и изменённых файлов |
| prio.col.download | Скачивание — тратит дневную квоту |
| prio.col.sync | Синхронизация — нагружает процессор NAS |
| prio.opt.default / section / folder | По умолчанию / Как у раздела / Как у папки |
| prio.opt.first / last / pause | 1 — первым / 9 — последним / Пауза |
| prio.inherit | сейчас {v}, от {src} |
| prio.inherit.default | сейчас {v}, общее значение |
| prio.own | задано здесь, по умолчанию {dflt} |
| prio.saved.pause | Сохранено. {stage} папки остановится со следующего прохода. |
| quality.title | Журнал качества |
| quality.lead | Последняя оценка каждого субтитра. Надёжные сервис записал сам, сомнительные отложил на проверку. Здесь ничего не меняется — это история решений. |
| quality.verdict.ok / review | Надёжно / Сомнительно |
| quality.action.written / held / test / failure | Записано / Отложено на проверку / Тестовый прогон, ничего не записано / Не синхронизировано |
| quality.order.library / time | По библиотеке / По времени |

## 8. Assumptions and open points

- **Decided by the owner (2026-10-23):** times are shown in local time (see §4), and "Approve" is a deferred 8-second client-side write with a visible "Отменить" button in the toast for the whole window. The server API does not change.
- The speech-match score bar uses `auto.scores` directly (0–1). The service's "sure" rule (two scores agree, lead ≥ 0,03) is explained in the card sentence, not drawn.
- The review ruler shows subtitle cues only; the API has no speech-activity data, so nothing pretends to be a waveform.
- The tree open/closed state and the last active filter chip live in `localStorage`; everything else is server state.
