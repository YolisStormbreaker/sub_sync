# Subsync panel: redesign brief

Version 1, 2026-10-23. Written for a design agent. A full redesign is allowed: information architecture, navigation, layout, components and visual style may all change. What must stay is every capability listed in section 5 and the constraints in section 3.

Screenshots of the current panel come with this brief (see section 9). They show every page in light and dark mode on desktop, and in dark mode on a phone, all populated with representative test data.

## 1. Product in one paragraph

Subsync is a small, always-on service on a home NAS. It watches a video library (cartoons, anime, films, TV series) and fills in missing subtitles. For every video it needs a Russian subtitle and a subtitle in the language of the original soundtrack. It downloads them from OpenSubtitles, shifts their timing so they match the video's audio, and writes them next to the video file, where the media player picks them up. **The subtitle text is never changed, only the timing.** The admin panel is a web page served by the same service. In it the owner answers the questions the automation cannot answer by itself, and checks the results the automation is not sure about.

## 2. User and context

- **One user, the owner.** He is a senior mobile engineer (Android and iOS), technically fluent, impatient with vague UI. He reads Russian; the UI language is Russian.
- **Typical sessions.** Ten minutes in the evening, working through a queue: listen to two audio tracks, pick one, move on; approve or reject a held subtitle after listening to it. Occasionally a quick check from the phone ("did last night's run do anything?").
- **Volumes on the real library.** About 800 videos. 30–60 files waiting for a language or track decision. 10–40 subtitles held for review. 30–100 "not found" entries. A quality log of hundreds of rows. Series have 5–200 episodes in nested folders (`TVshows/Doctor Who/Doctor.Who_S03/doctor.who.s03e04.avi`). Film folders are flat (`Movies/Goodfellas.mkv`).
- **What he complained about in the current UI** (each is a design requirement):
  - It was not clear what a button does ("What does OK do?"), or what a value means ("what does *auto* mean, which track will it pick?"). Each control has to say what it changes and when the change takes effect.
  - Labels mixed English internals with Russian ("track unclear after the sync-score check").
  - A track selector listed tracks 0–5 when the file had two.
  - The layout broke: buttons wrapped under the track name.
  - After saving a decision the page jumped to the top. Saving must not move the viewport; ideally the next item is right under the cursor.
  - After labelling one track, the card disappeared without saying what had been decided. Any automatic conclusion drawn from the user's input must be shown before the item leaves the queue.

## 3. Hard constraints

- **Delivery format.** One self-contained HTML page per screen, served by a Python stdlib HTTP server with HTTP Basic auth, on a LAN, with no build step. Vanilla JS and CSS only; no frameworks, no CDN dependencies. The page may be opened when the NAS has no internet, so fonts must be system fonts or embedded (a Cyrillic subset is mandatory). Design so it can be built from plain DOM code: no complex canvas or WebGL.
- **Themes.** Light and dark, following `prefers-color-scheme`. The owner mostly uses dark mode.
- **Widths.** Desktop 1280 px and up; usable on a 390 px phone (one-handed review of a held subtitle is a real use case).
- **Language.** All user-facing copy is in Russian. File and folder names appear as they are on disk (Latin, Cyrillic, dots, brackets). Long names must wrap or truncate with a full-name tooltip, never break the layout.
- **Audio.** Playback uses the native `<audio>` element fed by MP3 clips the server cuts on demand. A clip takes 1–3 s to prepare on the NAS, so a loading state is needed. Only one clip plays at a time.
- **Trust.** Nothing destructive happens without the user's explicit action. Approving writes a file next to the video. "Retry" discards a held result. These two need clear confirmation or undo.
- **Current visual direction**, free to replace: warm paper-and-ink palette (paper `#f6f4ef`, ink `#1d1b16`, rust accent `#8a3b12`; dark: `#1a1814` / `#ece7da` / `#e08a55`), small radii, dense cards. Do not fall back to a generic SaaS look (grey cards, teal accent, Inter). Name your chosen direction in one line and keep it consistent across pages.

## 4. Concepts the UI must make understandable

| Concept | Meaning | Where it shows |
|---|---|---|
| Section | Top-level library folder: `Animation`, `Anime`, `Movies`, `TVshows`. Only these are scanned. | Everywhere |
| Group | A series or film folder: the first two path levels, e.g. `TVshows/Doctor Who`. A loose film file directly in `Movies` currently becomes its own group; this looks odd, and the redesign may group loose files under `Movies`. | Language, not-found and priority pages |
| Original language | Language the film was shot in. Needed to download the "original" subtitle. Comes from file tags, the TMDb film database, or the user (per folder or per file). | Language page |
| Audio track | Files may carry 1–6 audio tracks: the original plus Russian dubs or voice-overs. Often none is tagged with a language. Tracks are numbered from 1 in the UI. | Language page |
| Original track | The track with the original speech. Timing is matched against it; a dub has different pauses and spoils the match. | Language page |
| Track language label | The user can say which language a single track is in (e.g. "track 1 is Russian"). The service then deduces the original track. | Language page |
| Automatic track detection | When tags cannot tell, the service downloads the original-language subtitle and compares the speech in each track against its lines. It is "sure" only if two independent scores agree and the lead over the runner-up is at least 0.03. Otherwise the user decides by ear. | Language page, per track: "speech match" score |
| Queue for detection | Files whose language is known but whose track still awaits the automatic comparison. The comparison spends a download from a daily quota, so it can take days. The user may decide by ear instead of waiting. | Language page |
| Held subtitle (review item) | A synced subtitle the quality gate did not trust enough to write automatically. Statuses: waiting, approved (written next to the video), rejected. | Review page |
| Quality verdict | `ok` (written automatically) or `review` (held), with a 0–1 confidence and reasons in Russian. | Review and quality log |
| Not found | A search that returned nothing, with a recorded reason. Reason codes: exists only in other languages (wait); title unknown to the database (fix with a hint); file name not parseable (rename or hint); special episode 0; everything filtered out; reason not recorded (older entries). Retried automatically after 7 days. | Not-found page |
| Search hint | A title or TMDb id the user gives for a folder or file to fix the search. Saving a hint lifts the 7-day wait. | Not-found page |
| Priorities | Per section, folder or file, for three stages: scanning, downloading (spends quota), syncing (spends CPU). Values 1 (first) to 9 (last), 0 = paused, or "default". The more specific path wins. | Priorities page |
| Quotas and schedule | 100 downloads per day (resets 00:00 UTC). New files are handled within about 2 minutes. The old library is processed nightly after 00:05 UTC, up to 90 downloads per night. | A global status area; today a line of text on one page |

## 5. Functional inventory, per screen

The current screens follow; a redesign may merge or split them. "Endpoint" lists the data the screen receives today, so mock data in the designs should be realistic.

### 5.1 Global

- Navigation between the screens.
- **Missing today:** a status area visible everywhere: service running or not, last nightly run and what it did, downloads used today / quota left, the number of items waiting for the user on each screen (badges). The data exists (`daily`, `quota` in `/api/state`); the presentation is new.
- A shared library filter used on every list. It understands words from the title plus `s06e05`, `6x05`, `s06` and `e05`. It matches natural episode order: s06e02 sorts before s06e10.
- Library tree: section, then series, then season folder, then episodes, with counts. Collapse state is remembered per tree.

### 5.2 Original language and track (main work queue, `/`)

Data: `GET /api/state` returns `groups[]`, each with `path`, `files[]` (needs a decision), `queued[]` (waiting for automatic detection), `decided[]` (the user chose), `nolang` (count without a language), `ntracks` (most tracks in any file), `layouts[]` (track layout and how many files have it, e.g. `und + und` × 17), and `override` (folder-level choice). Each file has `path`, `lang`, `conf`, `pending`, `own` (the user's file-level choice: `lang`, `track`, `tlangs`), `tracks[]` (`i`, `lang`, `mine`, `title`, `codec`), `dur`, `auto` (`best`, `margin`, `scores` per track), `track`, and `lines[]`: plain-Russian status sentences ("Language: English, chosen by you for TVshows/Doctor Who." / "Automatic detection compared each track with the English subtitles but found no confident winner: track 2 scored best, lead 0.02 with threshold 0.03…").

Actions:

1. **Folder level:** set the original language for a whole folder (or "not set: detect automatically"). Set the original track for the whole folder ("always track N", or "decide per file"); this asks for confirmation that the user listened to a few episodes.
2. **File level, per track row:**
   - Listen: plays 20 s of that track from the middle of the film. "Another fragment" moves to 30, 70, 15 or 85 % of the duration; switching tracks plays the same moment, so they can be compared by ear.
   - Label the track's language (files with 2 or more tracks). This saves immediately.
   - "This is the original" saves immediately.
   - Show the automatic detection score per track and mark which track the automation considered best.
3. Set the original language for this file only (collapsed by default; open when the language is unknown).
4. Undo the user's track choice (in "chosen by you").
5. Sections per group: **needs your choice**, **queued for automatic detection** (may be decided by ear now), **chosen by you**.

Behaviours to design for:

- After "This is the original", the card leaves the queue, the viewport must not jump, and the next card takes its place.
- After a track label, the service may deduce the original at once. The card must stay, show the conclusion ("original is now track 2, confirm or choose another") and leave only after confirmation.
- Two tracks with identical metadata are the common case. The UI must make "listen to both at the same moment, then pick" the obvious flow.
- A file can have six tracks with no tags (multi-voice-over releases).
- Empty state: "Everything is decided, the service needs nothing from you."

**What happens with more tracks after labelling.** Labels can settle the original by themselves. If exactly one unlabelled track remains next to Russian or Ukrainian tracks, it becomes the original. If the user labels any track with a non-Russian language, the first such track becomes the original. If two or more unlabelled tracks remain, nothing is settled: the automatic comparison runs only among the remaining unlabelled tracks, or the user picks by ear. The UI should show how many candidates remain ("2 candidates left: tracks 3 and 5").

### 5.3 Not found (`/missing`)

Data: `GET /api/missing` returns `items[]`: `path`, `lang`, `at` (last search), `retry` (automatic retry date), `code`, `ru` (reason sentence), `query`, `others` (languages that do exist, with counts), `hint`.

Actions:

- Filter by reason (chips with counts) and by the library filter.
- Per group: the reasons aggregated ("32 files: this episode exists in es, en, tr… but nobody uploaded Russian"); the current hint; a form with a title and a numeric TMDb id; "Save and search again", "Search again without changes", "Remove hint". The TMDb id must be validated as a number, with an example of where to find it (the number in the themoviedb.org URL).
- A file list with language, reason, and the last and next search dates.
- Make clear which reasons the user can fix (title unknown, name unparseable) and which only need waiting (other languages only). A hint cannot help with the "waiting" ones; the UI should not offer it there as the main action.

### 5.4 Review (`/review`)

Data: `GET /api/review` returns items with `id`, `rel`, `lang`, `status` (pending / approved / rejected), `score`, `reasons` / `reasons_ru`, and `points` (suggested listening start times). `GET /api/review/{id}/cues?t=&len=` returns the subtitle lines in a 40 s window. `GET /api/review/{id}/clip?t=&len=` returns 40 s of the original track as MP3.

Actions:

- Filter by status and language, plus the library filter. Counts per status.
- Per item: why it was held (reasons), confidence.
- Listening workbench: pick a start point; the clip plays; the current subtitle line is shown large, in sync with playback, with the next line and the time until it; a ruler shows where the lines fall in the window, with a moving playhead. The user judges whether the lines appear when the speech starts.
- "Approve and write next to the video" (writes the file, byte-identical text), "Reject", "Reset: make again" (removes the item; it is rebuilt on the next run; confirmation required), "Remove from list" (for approved items).
- Must work one-handed on a phone.

### 5.5 Priorities (`/prio`)

Data: `GET /api/prio` returns sections and groups with the effective value per stage (`v`), where it comes from (`src`), the default (`dflt`), and `files[]` with the same fields.

Actions: set scanning, downloading and syncing priority (default, 1–9, pause) for a section, folder or file. Show when a value is inherited and from which path. Today there is one "OK" per row; per-control saving with feedback is preferred.

### 5.6 Quality log (`/quality`)

Data: `GET /api/quality` returns the latest record per file and language: `ts`, `rel`, `lang`, `verdict`, `score`, `action` (written, held, test, failure), `reasons` / `reasons_ru`.

Actions: filter by verdict (all, doubtful, trusted) and by the library filter; order by library (grouped by folder) or by time; counts. A wide table today; needs a phone layout.

## 6. Cross-cutting interaction rules

- Every save shows a short confirmation naming what changed and when the service will act on it ("on the next pass: new files within 2 minutes, the old library tonight").
- Saving never scrolls the page; removed items collapse in place.
- Errors from the server (HTTP 400 with a plain-text message) are shown next to the control that caused them, not in `alert()`.
- Loading states for: the whole page, a clip being cut (1–3 s), a save in progress.
- Number formatting uses Russian conventions: decimal comma, dates like "23 октября".
- Track numbering in the UI starts at 1 everywhere.
- Accessibility: keyboard reachable, visible focus, colour is never the only carrier of meaning (status also as text or icon), contrast AA in both themes.

## 7. What to deliver

1. One-line design direction and the token set (colours for both themes, type scale with a Cyrillic-capable system or embeddable font stack, spacing, radii).
2. High-fidelity screens, light and dark, desktop and phone, for:
   - the language/track queue: a group with collapsed and expanded sections; a two-track card; a six-track card; a card after a label settled the original; the empty state;
   - not found, with a reason filter active;
   - review, with a clip playing and a line shown;
   - priorities;
   - quality log;
   - the global status area.
3. A component sheet: track row, audio control with loading state, save feedback, filter bar, tree node, reason chip, status badge, confirmation pattern.
4. Notes on behaviour wherever a static picture cannot show it: what happens on save, collapse animation, and focus moving to the next card.
5. Copy: all Russian strings that change, as a table of key and Russian text.

## 8. Out of scope

Authentication UI (the browser's Basic auth dialog stays), editing subtitle text (forbidden by design), multi-user features, settings for quotas or schedule (fixed in code).

## 9. Screenshots of the current panel

Files are named `<n>-<page>-<variant>.png`. Variants: `desktop-light`, `desktop-dark` (1280 px wide), `mobile-dark` (390 px wide). All are full-page captures with test data.

| File prefix | Page |
|---|---|
| `1-language` | Original language and track, with all sections expanded |
| `2-not-found` | Not found, with search hints |
| `3-review` | Review, with a clip playing |
| `4-priorities` | Priorities, with one folder's files expanded |
| `5-quality-log` | Quality log |
