# sub_sync

Working copy of **subsyncd**, the subtitle service on the Synology NAS (192.168.1.52, DSM 7.4.1). It finds videos without Russian or original-language subtitles, downloads them from OpenSubtitles, matches **only the timing** to the video's audio (the text stays byte-identical), and writes the result next to the video. Results the quality gate does not trust are held for review in the web panel, which runs on port 8742.

`subsyncd/` holds stage 14: the review fixes, the second-pass backend fixes (see `docs/code-review-2026-10-23.md`) and the panel redesign from `design/`. Tests are not deployed to the NAS.

## Layout

| Path | What it is | Where it lives on the NAS |
|---|---|---|
| `subsyncd/*.py` | Service, web panel, tests | `/volume1/docker/subsync-tools/subsyncd/` (mounted as `/t/subsyncd` in the container) |
| `subsyncd/service.sh` | Starts the always-on container `subsyncd` | same folder |
| `subsyncd/run.sh` | One-off runs of `main.py` in a throwaway container | same folder |
| `nas/watchdog.sh` | Hourly DSM task (id 14): starts the container if it is down | `/volume1/docker/subsync-tools/watchdog.sh` |
| `nas/dsm-icon/` | PNG renders of the panel icon for the DSM package shortcut and main menu | `/var/packages/Subsync/target/ui/images/` |
| `tools/applydiff.py` | Applies a header-less unified diff with exact-match checks. Used for deploys, because the NAS has no `patch` | copied to the NAS for each deploy |
| `docs/subsync-nas-wrapper.md` | Running notes: state, decisions, findings (in Russian) | — |
| `subsyncd/static/` | Panel front end: `subsync.css` (design tokens and components from `design/`), `app.css`, `app.js` (shared helpers), one script per page | same folder, served at `/static/` |
| `design/` | The design handed over for the redesign: `DESIGN.md`, `subsync.css`, page mock-ups | — |
| `docs/subsync-panel-design-brief.md` | Redesign brief for the panel; `docs/screenshots/` shows the current panel with test data | — |

State lives outside the code, in `/volume1/docker/subsync/` (`/state` in the container): `state.db` (SQLite: probe cache, detection results, not-found log, quota; see `statedb.py`), `overrides.json` (language and track choices), `searchhints.json`, `missing.json`, `priorities.json`, `quality.jsonl`, the review store, `raw/` (untouched downloaded subtitles), `web_password`, and API credentials.

## Modules

- `main.py`: daemon (`service`). It runs the new-file watcher every 120 s and the nightly backlog run after 00:05 UTC (90 downloads per night), plus CLI subcommands.
- `media.py`: scanning rules, ffprobe, filename parsing, original-audio rules.
- `resolve.py`: original language and track (person's override, then tags, then TMDb, then stored detection). `relabel` applies track language labels.
- `trackid.py`: tells the original track apart by aligning each candidate against the original-language subtitle.
- `engines.py`, `drift.py`: timing engines (piecewise "act staircase" lag model).
- `srtio.py`: timing-only rewrite; the text bytes are never touched.
- `quality.py`: quality gate and log. `review.py`: held items, clips, approve, reject, retry. `requalify.py`: re-gates held items from stored metrics.
- `osapi.py`: OpenSubtitles REST client. `tmdb.py`: TMDb lookups. `missing.py`: reasons for empty searches and search hints.
- `statedb.py`: the working state in SQLite (WAL). The code still sees one dict; a save writes only the rows that changed. The first start imports `state.json` and keeps it as `state.json.pre-sqlite`.
- `overrides.py`, `prio.py`: the person's choices. They are built on `jsonstore.py`: a read-modify-write under an flock on `<file>.lock`, a unique temp file, fsync and an atomic rename. A file that cannot be parsed is never overwritten.
- `web.py`: admin panel HTTP layer (stdlib server, Basic auth, page shell, `/static/`, JSON API). `views.py`: the view models behind the API, including `/api/status` for the rail (service activity from `<state>/activity.json`, last night's summary, quota, badge counts).
- The panel font is Golos Text, served from `<state>/fonts/GolosText.ttf`; without the file the panel falls back to system fonts.

## Tests

The tests need Python 3.10+, ffmpeg, numpy, webrtcvad and ffsubsync. `test_web_ui.py` and `make_shots.py` also need Playwright with Chromium.

```sh
cd subsyncd
python3 test_gate.py && python3 test_flow.py && python3 test_missing.py && python3 test_all.py && python3 test_fixes13.py && python3 test_fixes14.py && python3 test_statedb.py
python3 test_engine.py && python3 test_saw.py
GOLOS_TTF=path/to/GolosText.ttf python3 test_web_ui.py /tmp/shots   # drives every page in headless Chromium; the font is optional
python3 make_shots.py /tmp/shots      # screenshots of all pages with test data
```

## Deploying

The NAS is reachable only through a web terminal; there is no scp or git on its side, but it can reach GitHub over HTTPS. The simplest route is to download this repository at a given commit and compare hashes:

```sh
C=<commit sha>; mkdir -p /volume1/docker/subsync-tools/in/$C && cd /volume1/docker/subsync-tools/in/$C
curl -fsSL https://codeload.github.com/YolisStormbreaker/sub_sync/tar.gz/$C | tar xz --strip-components=1
sha256sum subsyncd/*.py subsyncd/static/*
```

Then continue from step 2 below, copying files instead of applying diffs. The diff procedure that worked before GitHub:

1. Check that the deployed files are what the change was made against: `sha256sum *.py` on the NAS against this copy.
2. Back up the files to be changed into `/volume1/docker/subsync-tools/bak-sNN/`.
3. Transfer header-less diffs (or whole new files) through heredocs into `/volume1/docker/subsync-tools/in/sNN/`. Check every part by sha256.
4. Apply them with `python3 applydiff.py <file> <diff>` to copies in `in/sNN/new/`. Compare the result hashes with this copy, then copy the files into `subsyncd/`.
5. Check that the new code imports: `docker exec subsyncd sh -c 'cd /t/subsyncd && /home/node/.local/pipx/venvs/ffsubsync/bin/python -c "import web, main"'`.
6. Save the log first (`docker rm` deletes it), then restart:
   `docker logs subsyncd > in/subsyncd-before-sNN.log 2>&1; docker rm -f subsyncd; sh subsyncd/service.sh`.
7. Smoke test: `curl -u u:$(cat /volume1/docker/subsync/web_password) http://127.0.0.1:8742/api/state`.

## Panel security

The panel uses HTTP Basic auth; the password is in `/state/web_password`, and an empty file locks the panel. POST requests must have `Content-Type: application/json`. When an `Origin` header is present, it must match `Host`. A reverse proxy that rewrites `Host` therefore needs to pass the original header through.

## Hard rules

- Subtitle text is never changed, only the timing.
- The Mentalist s06 e01 and e02 are not to be replaced.
- New deletions on the NAS, and new permanent tasks there, need the owner's explicit "yes".
- The original language is English for Doctor Who, The Mentalist, «Жизнь с Луи» and Black Mirror; TMDb decides for everything else, and the panel can override it.
