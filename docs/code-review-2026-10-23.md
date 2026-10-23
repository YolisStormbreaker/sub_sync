# Code review, 2026-10-23

An independent pass over the whole service, followed by fixes. The fixes were deployed to the NAS on 2026-10-23 (backup of the replaced files: `/volume1/docker/subsync-tools/bak-s16/`). Each fixed item has a test in `subsyncd/test_fixes13.py`.

## Fixed

| ID | Severity | Problem | Fix |
|---|---|---|---|
| H1 | high | `overrides.json`, `priorities.json`, `searchhints.json` and `missing.json` were written read-modify-write without a lock, through a shared temp file. Concurrent saves lost updates. A damaged file was read as `{}`, so the next save wiped every choice; a test kept 12 of 290 entries. | New `jsonstore.py`: an flock around the read-modify-write, a unique temp file, fsync and rename. A damaged file raises instead of being overwritten, and readers keep their last good copy. |
| H2 | high | A second-language subtitle (usually ru) was always held for review whenever the original-language subtitle already existed next to the video. The reason given was wrong: "measured against dubbed audio". | That existing original-language `.srt` is now the reference (`sidecar_ref`). It counts as trusted only if this service wrote it as `ok` or a person approved it; otherwise the stricter chain threshold applies. Reasons corrected: "checked only against the original audio". |
| H3 | high | `main.py plan` overwrote `state.json` with a stale copy taken before its probing. That rolled back quota counters, `last_night` and detection results, and could start a second nightly run. | `plan` merges only its probe cache into a fresh state, and only while holding the run lock. |
| H4 | high | A downloaded file with no readable cues was paid for again every night. | The file id is marked unusable (`state.badfiles`), the bytes are kept as `raw/*.bad`, and such files are skipped by `pick`. The not-found reason says so. |
| M1 | medium | The not-found record stayed after a later search succeeded. | It is cleared on success. The not-found page ignores entries whose file size changed. |
| M2 | medium | A rejected or failed sync was redone every night, including full audio extraction. | `state.failed` holds the language back for 7 days. |
| M3 | medium | `_tidy` forced cues into start order, dragging out-of-order sign or song cues to their neighbours' times. | Each cue is clamped on its own. |
| M4 | medium | The "new files arrived" check walked the whole library before every item of the nightly run. | It walks at most once per poll interval. |
| M5 | medium | A preallocated or still-copying file could count as complete. | A file must also be untouched for 10 min (`MIN_AGE`). A file still being copied no longer interrupts the nightly run. |
| M6 | medium | "Always track N" set on a folder overrode confident tags and blocked files that have fewer tracks. | A folder-wide track only fills in where the file's own tags cannot tell. A file-level choice still wins, but an out-of-range one is reported. |
| M7 | medium | Held candidates were not tied to the video version or the audio track. | The size and mtime of the video are stored. A replaced video is neither blocked nor approvable from the old candidate, and a changed track releases a pending item. The clip cache name includes the track. |
| M8 | medium | The panel listed every probe ever cached, so deleted files appeared and replaced files appeared twice. | Only the newest probe of each existing file is listed. |
| L1 | low | An empty password file let anyone in. | An empty password never matches; the file is written atomically. |
| L2 | low | A cross-site POST could carry the cached Basic credentials. | POST requires a JSON content type and a matching `Origin`. |
| L3 | low | A non-object JSON body left the request without a response. | It now gets a 400; unexpected errors get a 500. |
| L6 | low | Audio left in `/state/tmp` by a killed run was never removed. | It is removed at service start (the clip cache is kept). |
| L7 | low | A download link that failed after the quota was spent was not retried. | It is retried 3 times. |
| L11 | low | The panel text always said "English subtitles". | It names the actual language. |
| own | — | The track reason was replaced by the language source ("Определена автоматически: chosen language"). | `resolve` keeps the track reason. |
| own | — | Every loose file in `Movies` became its own "folder". | Loose files are grouped under their section. Folder-wide settings and search hints are hidden for a whole section. |
| own | — | `s11e09HDRip` was not parsed as an episode. | SxxEyy may be followed by letters. |

## Fixed in the second pass (stage 14)

- **M9, partly.** `state.json` is written compact (no indentation), routine saves during a run are throttled to one per 30 s (downloads and the end of a run still save at once), and `prune_state` drops probe keys, track results, empty searches, failures and seen marks of files that are gone or were replaced. It runs at service start and every night. Still one file, still rewritten whole.
- **L4.** A detection that ended in an error ("too few cues" included) is stored with `error` and treated as absent after `RETRY_DAYS` (7), so it is retried weekly instead of never or every night.
- **L5.** `srtio.text_unchanged` compares line by line: the same number of lines, and the only lines allowed to differ are timing lines at cue starts (after a blank line, an index line or the start of the file, with an optional BOM), both matching the strict timing pattern, with identical tails. It runs in addition to the old `strip_times` check.
- **Architecture, partly.** Russian language names live once, in `media.LANG_NAMES_RU`, checked against `media.LANGS` at import. `RETRY_DAYS` is defined once in `media`. View models moved from `web.py` to `views.py`; `web.py` is HTTP only, and the pages are static files in `static/`.

## Fixed in the third pass (stage 15)

- **M9, rest.** The state moved from `state.json` to SQLite (`statedb.py`, `state.db`, WAL). The code keeps working with a dict; a save writes only the rows that changed, in one transaction, so a save after one item writes a few rows instead of a few MB. Two writers no longer overwrite each other's state. At 5000 files (1.8 MB of JSON) a load takes about as long as parsing the old file, and a save of one change writes one row.

## Not fixed yet

- **L9.** `requalify.py` runs without the run lock.
- **L10.** `existing_langs` matches by prefix: `Film.mkv` is credited with `Film.Part2.en.srt`.
- **Architecture, rest.** Dub detection is written twice. `rel` means both a path and a track index. `engines.LAST` is module state.
