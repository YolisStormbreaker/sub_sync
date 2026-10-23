"""subsyncd: find videos that lack ru/original-language subtitles, fetch them from OpenSubtitles, fix only their timing.
  main.py plan  [FILE ...]                       what is missing (no network, no writes)
  main.py fetch FILE ... (--dest DIR | --apply)  one-off download + sync of given files
  main.py run   (--dest DIR | --apply)           backlog by priority (TVshows first), capped per day
  main.py service --apply                        web page + new-file watcher + nightly backlog run
  main.py override list | set PATH LANG [--track N] | rm PATH
  main.py prio list | set PATH [--scan N] [--download N] [--sync N] | rm PATH [STAGE]   priorities, 1 first .. 9 last, 0 paused
  main.py review list | approve ID | reject ID | retry ID        subtitles the quality gate held back
  main.py quality [--limit N]                                    latest quality verdict per file
  main.py quota
The subtitle text is never altered: engines see a timing skeleton and the result is written back into the original bytes."""
import argparse, contextlib, datetime, fcntl, json, os, shutil, struct, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engines, jsonstore, media, missing, osapi, prio, quality, resolve, review, tmdb
from resolve import track_key
from overrides import Overrides
from srtio import parse_times, retime, strip_times, text_unchanged

ROOT = os.environ.get('SUBSYNC_ROOT', '/video')
STATE = os.environ.get('SUBSYNC_STATE', '/state')
RETRY_DAYS = media.RETRY_DAYS
# Sanity gate, not an accuracy measure. A frame-rate difference legitimately moves late cues by minutes (23.976 vs 25 fps
# is ~4%), so the gate looks at the fitted scale and at the jumps left after removing that linear trend.
MAX_SCALE = 0.25
MAX_RESID = 40.0  # seconds
BACKLOG_CAP = 90  # downloads per UTC day for the old library; the rest of the quota stays free for new files
# Order inside a stage: the priority from prio.py (default by top folder: TVshows 1 > Anime 2 > Animation = Movies 3), then the newest
# file first. New files always go before any backlog.
POLL_SECONDS = 120
MIN_AGE = 600  # a new file counts as complete only when it has not been written to for 10 min (downloaders preallocate the full size)
STATE_LOCK = threading.Lock()


def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def load_state():
    try:
        return json.load(open(os.path.join(STATE, 'state.json')))
    except (OSError, ValueError):
        return {}


SAVE_EVERY = 30  # seconds between routine saves during a run; downloads and the end of a run always save at once
_saved = [0.0]
ACTIVITY = {'kind': None, 'since': None}


def save_state(st, force=True):
    """Compact JSON, fsynced and renamed into place. force=False skips the write if the last one was less than SAVE_EVERY ago:
    the file is a few MB, and rewriting it after every item of an 800-file night is most of the disk traffic."""
    if not force and time.time() - _saved[0] < SAVE_EVERY:
        return
    with STATE_LOCK:
        jsonstore.write(os.path.join(STATE, 'state.json'), st, indent=None)
        _saved[0] = time.time()
    beat()


def beat(kind=False):
    """<state>/activity.json: what the service is doing and when it last showed signs of life (read by the panel's status)."""
    if kind is not False:
        ACTIVITY.update(kind=kind, since=int(time.time()) if kind else None)
    try:
        jsonstore.write(os.path.join(STATE, 'activity.json'), dict(ACTIVITY, beat=int(time.time())), indent=None)
    except OSError:
        pass


def prune_state(st):
    """Forget what belongs to files that are gone or were replaced: old probe keys, track results, empty searches, failures.
    Returns the number of entries dropped."""
    sizes, n = {}, 0

    def size(p):
        if p not in sizes:
            try:
                sizes[p] = os.path.getsize(p)
            except OSError:
                sizes[p] = None
        return sizes[p]
    newest = {}
    for k in st.get('probe', {}):
        p, sz, mt = k.rsplit('|', 2)
        if size(p) == int(sz) and (p not in newest or int(mt) > newest[p][0]):
            newest[p] = (int(mt), k)
    keep = {k for _, k in newest.values()}
    for table, ok in (('probe', lambda k: k in keep),
                      ('tracks', lambda k: size(k.rsplit('|', 1)[0]) == int(k.rsplit('|', 1)[1])),
                      ('notfound', lambda k: size(k.rsplit('|', 2)[0]) == int(k.rsplit('|', 2)[1])),
                      ('failed', lambda k: size(k.rsplit('|', 2)[0]) == int(k.rsplit('|', 2)[1])),
                      ('seen', lambda k: size(k) is not None)):
        d = st.get(table) or {}
        for k in [k for k in d if not ok(k)]:
            del d[k]; n += 1
    return n


@contextlib.contextmanager
def run_lock():
    os.makedirs(STATE, exist_ok=True)
    f = open(os.path.join(STATE, 'lock'), 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close(); yield False; return
    try:
        yield True
    finally:
        f.close()


class Ctx:
    def __init__(self, network=True):
        self.st = load_state()
        self.ov = Overrides(os.path.join(STATE, 'overrides.json'))
        self.pr = prio.Priorities(os.path.join(STATE, 'priorities.json'))
        self.hints = missing.Hints(os.path.join(STATE, 'searchhints.json'))
        self.rawmem = {}  # (video, lang) -> get_raw result of the download stage, consumed by the sync stage
        self.stats = {}  # written / held / notfound in this run, for the panel's summary of the night
        tp = os.path.join(STATE, 'tmdb_creds')
        self.tm = tmdb.TMDb(tp if os.path.exists(tp) else None, self.st)
        self.osc = osapi.OS(osapi.load_creds(os.path.join(STATE, 'opensubtitles_creds')), self.st) if network else None


def fit_check(new, raw):
    t = [r[0] for r in raw]; d = [n[0] - r[0] for n, r in zip(new, raw)]
    mt, md = sum(t) / len(t), sum(d) / len(d)
    var = sum((x - mt) ** 2 for x in t) or 1.0
    b = sum((x - mt) * (y - md) for x, y in zip(t, d)) / var
    a = md - b * mt
    return b, max(abs(y - (a + b * x)) for x, y in zip(t, d))


def osdb_hash(path):
    size = os.path.getsize(path)
    if size < 131072:
        return None
    h = size
    with open(path, 'rb') as f:
        for off in (0, size - 65536):
            f.seek(off)
            for (v,) in struct.iter_unpack('<Q', f.read(65536)):
                h = (h + v) & 0xFFFFFFFFFFFFFFFF
    return '%016x' % h


def cached_probe(video, st):
    key = '%s|%d|%d' % (video, os.path.getsize(video), os.path.getmtime(video))
    c = st.setdefault('probe', {})
    if key not in c:
        c[key] = media.probe(video)
    return c[key]


def lang_key(video, lang):
    return '%s|%d|%s' % (video, os.path.getsize(video), lang)


def recently(st, table, key):
    return time.time() - (st.get(table) or {}).get(key, 0) < RETRY_DAYS * 86400


def decide(video, ctx):
    pr = resolve.relabel(os.path.relpath(video, ROOT), cached_probe(video, ctx.st), ctx.ov)
    tracks = ctx.st.setdefault('tracks', {})
    orig, rel, why, conf = resolve.resolve(os.path.relpath(video, ROOT), video, pr, ctx.ov, ctx.tm, tracks)
    have = media.existing_langs(video, pr)
    want = media.wanted_langs(orig)
    missing = [l for l in want if l not in have]
    rel_path = os.path.relpath(video, ROOT)
    held = [l for l in missing if review.blocked(STATE, rel_path, l, video, rel)]  # waiting for a person, or rejected by one
    failed = [l for l in missing if recently(ctx.st, 'failed', lang_key(video, l))]  # the sync was rejected lately: wait before trying again
    detect = resolve.pending_detect(orig, pr, conf, tracks, video)
    return {'orig': orig, 'rel': rel, 'why': why, 'conf': conf, 'have': sorted(have), 'want': want, 'missing': missing,
            'detect': detect, 'held': held, 'failed': failed, 'todo': [l for l in missing if l not in held and l not in failed] if (conf or detect) else []}


def allowed(video):
    top = os.path.relpath(video, ROOT).split(os.sep)[0]
    return top in media.INCLUDE and not media.is_excluded(video, ROOT)


class LazyAudio:
    """The original track is extracted on first use and only once per video."""
    def __init__(self, video, rel):
        self.video, self.rel, self.cm, self.p = video, rel, None, None

    def path(self):
        if self.p is None:
            tmp = os.path.join(STATE, 'tmp'); os.makedirs(tmp, exist_ok=True)
            self.cm = engines.prepare(self.video, self.rel, tmp); self.p = self.cm.__enter__()
        return self.p

    def close(self):
        if self.cm:
            self.cm.__exit__(None, None, None); self.cm = self.p = None


def get_raw(video, lang, ctx, dry=False):
    """The untouched subtitle for video+lang, from state/raw or from OpenSubtitles.
    Returns (data or None, message, downloaded, info)."""
    st, osc = ctx.st, ctx.osc
    stem = os.path.splitext(os.path.basename(video))[0]
    nf = st.setdefault('notfound', {})
    key = '%s|%d|%s' % (video, os.path.getsize(video), lang)
    rel_path = os.path.relpath(video, ROOT); hint = ctx.hints.lookup(rel_path); guess = media.guess(video)
    # a hint saved after the last empty search lifts the waiting period
    if time.time() - nf.get(key, 0) < RETRY_DAYS * 86400 and not (hint and hint.get('at', 0) > nf.get(key, 0)):
        return None, 'skipped: nothing found less than %d days ago' % RETRY_DAYS, False, None
    vhash = osdb_hash(video)
    bad = st.setdefault('badfiles', {})  # OpenSubtitles files that turned out unusable: never downloaded again
    cands = osc.search(lang, vhash, guess, hint)
    usable = [c for c in cands if str(c['files'][0]['file_id']) not in bad]
    best = osc.pick(usable, stem)
    if not best:
        nf[key] = time.time()
        if cands:
            info = {'at': int(time.time()), 'lang': lang, 'code': 'filtered', 'ru': 'Найденные файлы (%d) уже скачивались и оказались пустыми или нечитаемыми; '
                    'поиск повторится через %d дней.' % (len(cands), RETRY_DAYS), 'en': 'only unusable files (%d)' % len(cands),
                    'query': missing.describe_query(guess, hint), 'others': {}, 'hint': hint or None}
        else:
            info = missing.diagnose(osc, lang, vhash, guess, hint)
        missing.record(STATE, key, info); ctx.stats['notfound'] = ctx.stats.get('notfound', 0) + 1
        return None, 'not found on OpenSubtitles: ' + info['en'], False, None
    nf.pop(key, None); missing.clear(STATE, key)  # found: the file leaves the "not found" list
    fid = best['files'][0]['file_id']
    desc = 'file %s | %s | fps %s | hash match %s' % (fid, best.get('release'), best.get('fps'), bool(best.get('moviehash_match')))
    if dry:
        return None, 'would download ' + desc, False, None
    rawp = os.path.join(STATE, 'raw', '%s.%s.%s.srt' % (stem, lang, fid))
    downloaded = False
    if os.path.exists(rawp):  # a rerun after a rejected sync must not spend quota again
        data, info = open(rawp, 'rb').read(), {'mode': 'cache', 'remaining': None}
    else:
        data, info = osc.download(fid); downloaded = True
        os.makedirs(os.path.dirname(rawp), exist_ok=True)
        if not parse_times(data):  # kept for a look, and marked so the same file is never paid for again
            open(rawp + '.bad', 'wb').write(data); bad[str(fid)] = int(time.time())
            return None, 'downloaded file has no cues (marked unusable): ' + desc, True, None
        open(rawp, 'wb').write(data)  # untouched original, outside the library
    return data, desc, downloaded, info


def describe(si):
    parts = []
    d = si.get('drift')
    if d:
        if d['ok']:
            cuts = ', '.join('%d:%02d' % divmod(int(t), 60) for t in d['cut_times'])
            parts.append('drift fit p=%+.5f, %d act%s%s, offsets %s s, %d of %d windows' % (
                d['p'], len(d['qs']), '' if len(d['qs']) == 1 else 's', ' (breaks at %s)' % cuts if cuts else '',
                '/'.join('%+.1f' % q for q in d['qs']), d.get('inliers', 0), d['windows']))
        else:
            parts.append('drift fit not trusted (%d windows), plain ffsubsync result kept' % d['windows'])
    if si.get('chain'):
        parts.append(si['chain'])
    return ''.join(', ' + p for p in parts)


def sidecar_ref(video, d):
    """Cue starts of an original-language .srt already next to the video, and how far it is trusted: 'ok' when this service wrote
    it after a trusted sync or a person approved it, else 'review' (somebody else's timing, so the stricter chain threshold applies)."""
    for f in media.existing_langs(video, {'subs': []}).get(d['orig'], []):
        if not f.lower().endswith('.srt'):
            continue
        try:
            times = parse_times(open(os.path.join(os.path.dirname(video), f), 'rb').read())
        except OSError:
            continue
        if len(times) >= 50:
            rel_path = os.path.relpath(video, ROOT)
            mine = [r for r in quality.latest(STATE) if r['rel'] == rel_path and r['lang'] == d['orig']]
            trusted = (mine and mine[0]['action'] == 'written' and mine[0]['verdict'] == 'ok') or \
                review.status(STATE, rel_path, d['orig']) == 'approved'
            return [t[0] for t in times], 'ok' if trusted else 'review'
    return None, None


def process(video, lang, audio, ctx, engine, dest_dir, dry=False, ref=None, mode='write', d=None, ref_verdict=None):
    """Returns (message, downloaded, written times or None, quality verdict or None).
    ref: start times of the already synced original-language subtitle; ref_verdict: its quality verdict.
    mode 'write': the result goes to dest_dir whatever its quality (tests); 'gate': only a trusted result goes there and the rest is
    held for review; 'hold': everything is held for review. Every finished sync is recorded in the quality log."""
    stem = os.path.splitext(os.path.basename(video))[0]; rel_path = os.path.relpath(video, ROOT)
    res = ctx.rawmem.pop((video, lang), None) or get_raw(video, lang, ctx, dry)
    data, msg, downloaded, info = res
    if data is None:
        return msg, downloaded, None, None
    raw = parse_times(data)
    new, dropped, si = engines.sync(engine, audio.path(), raw, os.path.join(STATE, 'tmp'), ref)
    slope, resid = fit_check(new, raw)
    if abs(slope) > MAX_SCALE or resid > MAX_RESID:
        why = 'sync rejected: scale %+.4f, max residual %.0f s; raw file kept in state/raw, retried in %d days' % (slope, resid, RETRY_DAYS)
        ctx.st.setdefault('failed', {})[lang_key(video, lang)] = int(time.time())
        quality.record(STATE, rel_path, lang, engine, {'verdict': 'review', 'score': 0.0, 'reasons': [why], 'metrics': {}}, 'failed')
        return why, downloaded, None, 'review'
    out = retime(data, new)
    if strip_times(out) != strip_times(data) or not text_unchanged(data, out):
        raise RuntimeError('text integrity check failed')
    q = quality.assess(si, ref_verdict, expect_chain=ref is not None and not si.get('chain_q'), no_ref=bool(d) and lang != d['orig'] and ref is None)
    (ctx.st.get('failed') or {}).pop(lang_key(video, lang), None)
    tail = ', quality %s %.2f%s' % (q['verdict'], q['score'], ' (' + '; '.join(q['reasons']) + ')' if q['reasons'] else '')
    detail = '%d cues, %d dropped by engine and restored, scale %+.4f, max residual %.1f s, quota left %s%s%s' % (
        len(raw), dropped, slope, resid, info['remaining'], describe(si), tail)
    if mode == 'hold' or (mode == 'gate' and q['verdict'] != 'ok'):
        pr = cached_probe(video, ctx.st); cuts = (si.get('chain_q') or si.get('drift') or {}).get('cuts', [])
        pts = review.check_points(new, cuts if (si.get('chain_q') or (si.get('drift') or {}).get('ok')) else [], pr.get('duration') or 0)
        iid = review.hold(STATE, rel_path, lang, stem, d['rel'] if d else 0, out, q, pts, pr.get('duration') or 0, video)
        quality.record(STATE, rel_path, lang, engine, q, 'held', {'id': iid}); ctx.stats['held'] = ctx.stats.get('held', 0) + 1
        return 'HELD for review as %s via %s (%s; %s)' % (iid, info['mode'], engine, detail), downloaded, new, q['verdict']
    dest = os.path.join(dest_dir, '%s.%s.srt' % (stem, lang))
    if os.path.exists(dest):
        return 'not written: %s appeared meanwhile' % os.path.basename(dest), downloaded, None, None
    open(dest + '.tmp', 'wb').write(out); os.replace(dest + '.tmp', dest)
    ctx.stats['written'] = ctx.stats.get('written', 0) + (mode == 'gate')
    quality.record(STATE, rel_path, lang, engine, q, 'written' if mode == 'gate' else 'test')
    return 'written %s via %s (%s; %s)' % (os.path.basename(dest), info['mode'], engine, detail), downloaded, new, q['verdict']


def detect_track(video, d, ctx, dry=False):
    """Find the original track among the untagged ones by comparing each against the original-language subtitle.
    Returns (rel or None, message, downloaded). Every outcome, a doubtful one too, is stored so it is not recomputed."""
    import trackid
    pr = resolve.relabel(os.path.relpath(video, ROOT), cached_probe(video, ctx.st), ctx.ov); cands = media.candidate_tracks(pr['audio']); lang = d['orig']
    downloaded = False
    if lang in d['missing']:
        data, msg, downloaded, _ = get_raw(video, lang, ctx, dry)
    else:  # the subtitle in the original language is already there: use a sidecar .srt, embedded streams are not read
        data, msg = None, 'no sidecar .srt in the original language to compare the tracks with'
        for f in media.existing_langs(video, pr).get(lang, []):
            if f.lower().endswith('.srt'):
                data = open(os.path.join(os.path.dirname(video), f), 'rb').read(); break
    if data is None:
        return None, msg, downloaded
    times = parse_times(data)
    if len(times) < 100:
        ctx.st.setdefault('tracks', {})[track_key(video)] = {'lang': lang, 'rel': None, 'margin': 0.0, 'sure': False, 'at': int(time.time()),
                                                            'error': 'too few cues (%d) to tell the tracks apart' % len(times)}
        return None, 'too few cues (%d) to tell the tracks apart, retried in %d days' % (len(times), RETRY_DAYS), downloaded
    tmp = os.path.join(STATE, 'tmp'); os.makedirs(tmp, exist_ok=True)
    entry = {'lang': lang, 'rel': None, 'margin': 0.0, 'sure': False, 'at': int(time.time())}
    try:
        res = trackid.analyze(video, cands, times, tmp)
        rel, margin, sure = trackid.choose(res)
        entry.update(rel=rel, margin=round(margin, 3), sure=sure, metrics=res)
    except Exception as e:  # stored as unclear so a failing file is not retried every night
        entry['error'] = str(e)[:200]
        ctx.st.setdefault('tracks', {})[track_key(video)] = entry
        return None, 'detection failed (%s), left for manual choice' % entry['error'][:80], downloaded
    ctx.st.setdefault('tracks', {})[track_key(video)] = entry
    if sure:
        return rel, 'original is audio track %d (margin %.3f among %s)' % (rel, margin, cands), downloaded
    return None, 'unclear (best track %d, margin %.3f), left for manual choice' % (rel, margin), downloaded


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def daily(st):
    d = st.setdefault('daily', {})
    if d.get('date') != today():
        d.clear(); d.update(date=today(), backlog=0, new=0)
    return d


def _mtime(v):
    try:
        return os.path.getmtime(v)
    except OSError:
        return 0


def _rel(v):
    return os.path.relpath(v, ROOT)


def work(ctx, items, engine, dest, kind, dry=False, limit=None, should_stop=None, mode='write', keep_order=False):
    """items: [(video, decision)]. kind 'new' is never capped by BACKLOG_CAP; 'backlog' stops at it.
    should_stop() is polled between videos; True pauses the run and returns 'interrupted'.
    Three stages, each in its own order (prio.py): scan (find the original track), download (raw subtitles into the cache, spends
    quota), sync (audio extraction and alignment, spends CPU). A priority of 0 skips the stage for that file.
    keep_order: use the order of items instead of the priorities (explicit one-off fetches)."""
    dl = daily(ctx.st); pr = ctx.pr
    items = [(v, d) for v, d in items if allowed(v)]

    def order(stage):
        it = [x for x in items if pr.get(_rel(x[0]), stage) != 0]
        return it if keep_order else sorted(it, key=lambda x: (pr.get(_rel(x[0]), stage), -_mtime(x[0]), x[0]))

    ready = []
    for video, d in order('scan'):  # stage 1: scan
        if should_stop and should_stop():
            log('new files arrived, backlog paused'); return 'interrupted'
        if d.get('detect'):
            if kind == 'backlog' and dl.get('backlog', 0) >= BACKLOG_CAP:
                continue
            log('%s | orig=%s (%s) | detecting the original track' % (_rel(video), d['orig'], d['why']))
            try:
                rel, msg, dwn = detect_track(video, d, ctx, dry)
            except osapi.QuotaExhausted:
                log('quota exhausted in both modes, resumes after 00:00 UTC'); return
            except Exception as e:
                rel, msg, dwn = None, 'FAILED %s' % e, False
            if dwn:
                dl[kind] = dl.get(kind, 0) + 1
            log('  track: %s' % msg); save_state(ctx.st, force=bool(dwn))
            if rel is None:
                continue
            d = dict(d, rel=rel)
        ready.append((video, d))
    byvideo = dict((v, d) for v, d in ready)

    n = 0; out_of_quota = False  # stage 2: download
    for video, d in [x for x in order('download') if x[0] in byvideo]:
        if limit is not None and n >= limit:
            break
        if should_stop and should_stop():
            log('new files arrived, backlog paused'); return 'interrupted'
        if kind == 'backlog' and dl.get('backlog', 0) >= BACKLOG_CAP:
            log('backlog cap of %d downloads reached for today' % BACKLOG_CAP); break
        for lang in byvideo[video]['todo']:
            try:
                res = get_raw(video, lang, ctx, dry)
            except osapi.QuotaExhausted:
                log('quota exhausted in both modes, resumes after 00:00 UTC'); out_of_quota = True; break
            except Exception as e:
                res = (None, 'FAILED %s' % e, False, None)
            ctx.rawmem[(video, lang)] = res
            if res[2]:
                dl[kind] = dl.get(kind, 0) + 1
        save_state(ctx.st); n += 1
        if out_of_quota:
            break

    for video, d in [x for x in order('sync') if x[0] in byvideo]:  # stage 3: sync
        d = byvideo[video]
        if not any(ctx.rawmem.get((video, l)) for l in d['todo']):
            continue  # not reached by the download stage (cap, quota, limit): next run
        if should_stop and should_stop():
            log('new files arrived, backlog paused'); return 'interrupted'
        log('%s | orig=%s (%s) | todo=%s' % (_rel(video), d['orig'], d['why'], ','.join(d['todo'])))
        audio = LazyAudio(video, d['rel'])
        try:
            ref, ref_v = sidecar_ref(video, d) if d['orig'] not in d['todo'] else (None, None)
            for lang in sorted(d['todo'], key=lambda l: l != d['orig']):  # the original language goes first: it is the reference for the others
                if (video, lang) not in ctx.rawmem:
                    continue
                try:
                    msg, downloaded, tms, verdict = process(video, lang, audio, ctx, engine, dest or os.path.dirname(video), dry,
                                                            None if lang == d['orig'] else ref, mode, d, None if lang == d['orig'] else ref_v)
                    if lang == d['orig'] and tms:
                        ref, ref_v = [t[0] for t in tms], verdict
                except Exception as e:
                    msg, downloaded = 'FAILED %s (retried in %d days)' % (e, RETRY_DAYS), False
                    ctx.st.setdefault('failed', {})[lang_key(video, lang)] = int(time.time())
                log('  %s: %s' % (lang, msg))
                save_state(ctx.st, force=False)
        finally:
            audio.close()
            for l in d['todo']:
                ctx.rawmem.pop((video, l), None)


def queue(ctx, only=None):
    """Everything that is missing. Files whose original track is ambiguous are listed, not queued; files with scan priority 0 are skipped.
    The order of the result is irrelevant: work() orders every stage itself."""
    items, stuck = [], []
    vids = [v for v in (only or media.scan(ROOT)) if ctx.pr.get(_rel(v), 'scan') != 0]
    vids.sort(key=lambda v: (ctx.pr.get(_rel(v), 'scan'), -_mtime(v), v))  # the first-ever pass over a big library probes in this order
    for v in vids:
        try:
            d = decide(v, ctx)
        except Exception as e:
            log('ERROR', _rel(v), e); continue
        if d['missing'] and not d['conf'] and not d['detect']:
            stuck.append(v)
        elif d['todo']:
            items.append((v, d))
    return items, stuck


def cmd_plan(a):
    ctx = Ctx(network=False); n = need = stuck = detect = 0
    for v in (os.path.abspath(f) for f in a.files) if a.files else media.scan(ROOT):
        if not allowed(v):
            print('IGNORED (excluded or outside the scanned folders):', v); continue
        n += 1
        try:
            d = decide(v, ctx)
        except Exception as e:
            print('ERROR', os.path.relpath(v, ROOT), e); continue
        need += bool(d['todo']); stuck += bool(d['missing'] and not d['conf'] and not d['detect']); detect += bool(d['detect'] and d['missing'])
        print('%s | orig=%s (%s) | have=%s | missing=%s%s' % (os.path.relpath(v, ROOT), d['orig'], d['why'], ','.join(d['have']) or '-',
              ','.join(d['missing']) or '-', ' | WILL DETECT THE ORIGINAL TRACK' if d['detect'] and d['missing'] else '' if d['conf'] or not d['missing'] else ' | NEEDS CHOICE: which audio track is the original'))
    with run_lock() as ok:  # the probe cache is worth keeping, but only when no run is changing the state meanwhile
        if ok:
            fresh = load_state(); fresh.setdefault('probe', {}).update(ctx.st.get('probe', {})); save_state(fresh)
    print('videos %d, ready to process %d (of them %d need the original track detected first), waiting for a track/language choice %d' % (n, need, detect, stuck))


def need_target(a):
    if not (a.dest or a.apply or getattr(a, 'hold', False)):
        sys.exit('refusing to run without --dest DIR, --apply or --hold')


def run_mode(a):
    """hold: every result goes to the review store. gate (--apply, no --dest): next to the video if trusted, else review store.
    write (--dest DIR): everything to DIR, for tests."""
    if getattr(a, 'hold', False):
        return 'hold'
    return 'gate' if (a.apply and not a.dest) else 'write'


def cmd_fetch(a):
    need_target(a)
    with run_lock() as ok:
        if not ok:
            sys.exit('another run is active')
        ctx = Ctx(); items = []
        for v in (os.path.abspath(f) for f in a.files):
            if not allowed(v):
                print('IGNORED (excluded or outside the scanned folders):', v); continue
            d = decide(v, ctx)
            if a.force:
                d['todo'] = [l for l in d['want'] if not a.only or l == a.only]
            items.append((v, d))
        work(ctx, items, a.engine, a.dest, 'new', a.dry, mode=run_mode(a), keep_order=True)
        save_state(ctx.st)


def cmd_run(a):
    need_target(a)
    with run_lock() as ok:
        if not ok:
            sys.exit('another run is active')
        ctx = Ctx(); items, stuck = queue(ctx)
        log('queue: %d videos, %d waiting for a track/language choice' % (len(items), len(stuck)))
        work(ctx, items, a.engine, a.dest, 'backlog', a.dry, a.limit, mode=run_mode(a))
        save_state(ctx.st)


def snapshot():
    out = {}
    for p in media.scan(ROOT):
        try:
            out[p] = os.path.getsize(p)
        except OSError:
            pass
    return out


def hinted_files(st):
    """Videos with an empty search older than a search hint that covers them (the hint was saved after that search)."""
    hints = missing.Hints(os.path.join(STATE, 'searchhints.json'))
    done = st.get('hints_done', 0)
    if not any((h.get('at') or 0) > done for h in hints.all().values()):
        return []
    out = set()
    for key, t in (st.get('notfound') or {}).items():
        v = key.rsplit('|', 2)[0]
        h = hints.lookup(os.path.relpath(v, ROOT)) if v.startswith(ROOT + '/') else None
        if h and h['at'] > max(t, done):
            out.add(v)
    return sorted(out)


def aged(p):
    try:
        return time.time() - os.path.getmtime(p) >= MIN_AGE
    except OSError:
        return False


def new_files_check(seen):
    """should_stop for the nightly run: true when a complete new file is waiting. The library walk runs at most once per poll
    interval, not before every item, and a file still being copied does not interrupt the run."""
    last = [time.time()]

    def stop():
        if time.time() - last[0] < POLL_SECONDS:
            return False
        last[0] = time.time()
        return any(p not in seen and aged(p) for p in snapshot())
    return stop


def cmd_service(a):
    need_target(a)
    import web
    threading.Thread(target=web.serve, args=(a.port, ROOT, STATE), daemon=True).start()
    tmp = os.path.join(STATE, 'tmp')  # audio extracted by a run that was killed: hundreds of MB each, never reused
    for n in (os.listdir(tmp) if os.path.isdir(tmp) else []):
        if n != 'clips':
            shutil.rmtree(os.path.join(tmp, n), ignore_errors=True)
    st = load_state()
    if 'seen' not in st:  # the existing library is backlog, not "new"
        st['seen'] = snapshot()
    with run_lock() as ok:
        if ok:
            log('state: dropped %d entries of files that are gone or were replaced' % prune_state(st))
            save_state(st)
    pending = {}
    log('service started: web on port %d, polling every %d s, nightly run after 00:05 UTC' % (a.port, POLL_SECONDS))
    while True:
        try:
            beat()
            snap, ready = snapshot(), []
            st = load_state()
            if 'seen' not in st:  # state lost while running: what is there now is backlog, like on the first start
                st['seen'] = snap; save_state(st)
            seen = st['seen']
            for p, sz in snap.items():  # complete = same size for two polls and not written to for MIN_AGE
                if p in seen:
                    continue
                prev = pending.get(p)
                pending[p] = (sz, prev[1] + 1 if prev and prev[0] == sz else 0)
                if pending[p][1] >= 2 and aged(p):
                    ready.append(p)
            for p in [p for p in pending if p not in snap]:
                del pending[p]
            if ready:
                with run_lock() as ok:
                    if ok:
                        ctx = Ctx(); items, _ = queue(ctx, ready); beat('new')
                        log('new files: %d' % len(ready)); work(ctx, items, a.engine, a.dest, 'new', mode=run_mode(a))
                        ctx.st['seen'].update({p: snap[p] for p in ready}); save_state(ctx.st); beat(None)
                        for p in ready:
                            pending.pop(p, None)
            hinted = hinted_files(load_state())
            if hinted:  # a search hint saved in the panel: search those files now instead of waiting for the night
                with run_lock() as ok:
                    if ok:
                        ctx = Ctx(); items, _ = queue(ctx, [v for v in hinted if os.path.isfile(v)]); beat('hint')
                        log('search hints: %d files to search again' % len(items)); work(ctx, items, a.engine, a.dest, 'new', mode=run_mode(a))
                        ctx.st['hints_done'] = max(h.get('at') or 0 for h in ctx.hints.all().values()); save_state(ctx.st); beat(None)
            now = datetime.datetime.now(datetime.timezone.utc)
            st = load_state()
            if st.get('last_night') != today() and (now.hour, now.minute) >= (0, 5):
                with run_lock() as ok:
                    if ok:
                        ctx = Ctx(); log('nightly run: dropped %d stale state entries' % prune_state(ctx.st))
                        items, stuck = queue(ctx); beat('night')
                        log('nightly run: %d videos queued, %d waiting for a choice' % (len(items), len(stuck)))
                        seen = ctx.st['seen']; t0 = time.time()
                        res = work(ctx, items, a.engine, a.dest, 'backlog', should_stop=new_files_check(seen), mode=run_mode(a))
                        night = ctx.st.get('night') if (ctx.st.get('night') or {}).get('date') == today() else {'date': today(), 'start': int(t0), 'busy': 0}
                        night['busy'] = night.get('busy', 0) + int(time.time() - t0)  # resumed parts of an interrupted night add up
                        for k in ('written', 'held', 'notfound'):
                            night[k] = night.get(k, 0) + ctx.stats.get(k, 0)
                        night.update(end=int(time.time()), finished=res != 'interrupted', queued=len(items), waiting=len(stuck))
                        ctx.st['night'] = night
                        if res != 'interrupted':  # an interrupted run resumes after the new files are done
                            ctx.st['last_night'] = today()
                        save_state(ctx.st); beat(None)
        except Exception as e:
            log('service loop error:', e)
        time.sleep(POLL_SECONDS)


def cmd_override(a):
    ov = Overrides(os.path.join(STATE, 'overrides.json'))
    if a.action == 'list':
        print(json.dumps(ov.all(), ensure_ascii=False, indent=1))
    elif a.action == 'set':
        ov.set(a.path, a.lang, a.track); print('ok')
    else:
        ov.set(a.path, None, None); print('removed')


def cmd_prio(a):
    pr = prio.Priorities(os.path.join(STATE, 'priorities.json'))
    if a.action == 'list':
        print(json.dumps(pr.all(), ensure_ascii=False, indent=1))
    elif a.action == 'set':
        vals = {st: getattr(a, st) for st in prio.STAGES if getattr(a, st) is not None}
        if not vals:
            sys.exit('give at least one of --scan --download --sync')
        pr.set(a.path, vals); print('ok')
    else:
        pr.set(a.path, {st: None for st in prio.STAGES}); print('removed')


def cmd_review(a):
    if a.action == 'list':
        for m in review.items(STATE):
            print('%s %-8s %s %s | %.2f | %s' % (m['id'], m['status'], m['lang'], m['rel'], m['score'], '; '.join(m['reasons']) or 'trusted, held by --hold'))
    else:
        print(review.decide(STATE, ROOT, a.id, a.action))


def cmd_quality(a):
    rows = quality.latest(STATE, a.limit)
    for r in rows:
        print('%s %-6s %-7s %.2f %s %s | %s' % (datetime.datetime.fromtimestamp(r['ts']).strftime('%m-%d %H:%M'), r['lang'], r['verdict'], r['score'],
              r['action'], r['rel'], '; '.join(r['reasons'])))
    print('%d files: %d ok, %d to review' % (len(rows), sum(r['verdict'] == 'ok' for r in rows), sum(r['verdict'] != 'ok' for r in rows)))


def cmd_rawget(a):
    with run_lock() as ok:
        if not ok:
            sys.exit('another run is active')
        ctx = Ctx()
        data, msg, dl, _ = get_raw(os.path.abspath(a.file), a.lang, ctx)
        print(msg, '| downloaded now' if dl else '', '| cues', len(parse_times(data)) if data else 0)
        save_state(ctx.st)


def cmd_quota(a):
    st = load_state(); print(json.dumps({'quota': st.get('quota', {}), 'daily': st.get('daily', {})}, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    eng = lambda s: s.add_argument('--engine', default='drift', choices=sorted(engines.ENGINES))
    s = sub.add_parser('plan'); s.add_argument('files', nargs='*'); s.set_defaults(f=cmd_plan)
    s = sub.add_parser('fetch'); s.add_argument('files', nargs='+'); s.add_argument('--dest'); s.add_argument('--apply', action='store_true'); eng(s)
    s.add_argument('--dry', action='store_true'); s.add_argument('--force', action='store_true', help='test only: ignore existing subtitles')
    s.add_argument('--hold', action='store_true', help='send every result to the review store instead of the library')
    s.add_argument('--only'); s.set_defaults(f=cmd_fetch)
    s = sub.add_parser('run'); s.add_argument('--dest'); s.add_argument('--apply', action='store_true'); eng(s)
    s.add_argument('--dry', action='store_true'); s.add_argument('--limit', type=int)
    s.add_argument('--hold', action='store_true'); s.set_defaults(f=cmd_run)
    s = sub.add_parser('service'); s.add_argument('--dest'); s.add_argument('--apply', action='store_true'); eng(s)
    s.add_argument('--port', type=int, default=8742); s.set_defaults(f=cmd_service)
    s = sub.add_parser('override'); s.add_argument('action', choices=['list', 'set', 'rm']); s.add_argument('path', nargs='?')
    s.add_argument('lang', nargs='?'); s.add_argument('--track', type=int); s.set_defaults(f=cmd_override)
    s = sub.add_parser('prio'); s.add_argument('action', choices=['list', 'set', 'rm']); s.add_argument('path', nargs='?')
    for st in prio.STAGES:
        s.add_argument('--' + st, type=int, choices=range(10))
    s.set_defaults(f=cmd_prio)
    s = sub.add_parser('review'); s.add_argument('action', choices=['list', 'approve', 'reject', 'retry']); s.add_argument('id', nargs='?')
    s.set_defaults(f=cmd_review)
    s = sub.add_parser('quality'); s.add_argument('--limit', type=int, default=50); s.set_defaults(f=cmd_quality)
    s = sub.add_parser('rawget'); s.add_argument('file'); s.add_argument('lang'); s.set_defaults(f=cmd_rawget)
    s = sub.add_parser('quota'); s.set_defaults(f=cmd_quota)
    a = p.parse_args(); a.f(a)
