"""Subtitles the quality gate did not trust. They are kept outside the library until a person has listened and approved them.
Layout: <state>/review/<id>/{sub.srt, meta.json}. The candidate is the finished synced file, byte-identical to what would have been
written next to the video; approving copies it there, rejecting keeps the verdict so the file is not produced again."""
import hashlib, json, os, re, shutil, subprocess, time
from srtio import parse_times

CLIP_LEN = 40.0


def item_id(rel, lang):
    return hashlib.sha1(('%s|%s' % (rel, lang)).encode()).hexdigest()[:12]


def _dir(state_dir, iid):
    if not re.fullmatch(r'[0-9a-f]{12}', iid or ''):
        raise ValueError('bad id')
    return os.path.join(state_dir, 'review', iid)


def check_points(new_times, cuts, duration):
    """Where a person should listen: the start, just before every act break, the middle and the late part. Each point is moved
    to a few seconds before the nearest cue so that the clip contains speech."""
    if not new_times:
        return [0.0]
    end = duration or new_times[-1][1]
    want = [0.0] + [new_times[min(k, len(new_times) - 1)][0] - 6 for k in cuts] + [0.5 * end, 0.85 * end]
    pts = []
    for t in want:
        t = max(0.0, t)
        nxt = next((s for s, _ in new_times if s >= t), new_times[-1][0])
        p = round(max(0.0, nxt - 4.0), 1)
        if all(abs(p - q) > CLIP_LEN / 2 for q in pts):
            pts.append(p)
    return sorted(pts)


def video_sig(video):
    """Size and mtime of the video: a held candidate belongs to this exact file, not to a later release under the same name."""
    try:
        s = os.stat(video)
        return '%d|%d' % (s.st_size, int(s.st_mtime))
    except OSError:
        return None


def hold(state_dir, rel, lang, stem, track, data, q, points, duration, video=None):
    iid = item_id(rel, lang); d = _dir(state_dir, iid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'sub.srt.tmp'), 'wb') as f:
        f.write(data)
    os.replace(os.path.join(d, 'sub.srt.tmp'), os.path.join(d, 'sub.srt'))
    meta = {'id': iid, 'rel': rel, 'lang': lang, 'stem': stem, 'track': track, 'status': 'pending', 'created': int(time.time()),
            'verdict': q['verdict'], 'score': q['score'], 'reasons': q['reasons'], 'reasons_ru': q.get('reasons_ru', []), 'metrics': q['metrics'], 'points': points,
            'duration': duration, 'video': video_sig(video) if video else None}
    json.dump(meta, open(os.path.join(d, 'meta.json.tmp'), 'w'), ensure_ascii=False, indent=1)
    os.replace(os.path.join(d, 'meta.json.tmp'), os.path.join(d, 'meta.json'))
    return iid


def get(state_dir, iid):
    return json.load(open(os.path.join(_dir(state_dir, iid), 'meta.json')))


def items(state_dir):
    base, out = os.path.join(state_dir, 'review'), []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for n in names:
        try:
            out.append(get(state_dir, n))
        except (OSError, ValueError):
            pass
    out.sort(key=lambda m: ({'pending': 0, 'rejected': 1, 'approved': 2}.get(m['status'], 3), m['score'], m['rel']))
    return out


def status(state_dir, rel, lang):
    try:
        return get(state_dir, item_id(rel, lang))['status']
    except (OSError, ValueError):
        return None


def blocked(state_dir, rel, lang, video=None, track=None):
    """True while a candidate waits for a person or was rejected by one: the file is not produced again. A candidate made for an
    earlier version of the video, or (still pending) against an audio track that is no longer the original, does not block."""
    try:
        m = get(state_dir, item_id(rel, lang))
    except (OSError, ValueError):
        return False
    if m['status'] not in ('pending', 'rejected'):
        return False
    if video and m.get('video') and m['video'] != video_sig(video):
        return False
    if m['status'] == 'pending' and track is not None and m.get('track') is not None and m['track'] != track:
        return False
    return True


def _set(state_dir, iid, **kw):
    m = get(state_dir, iid); m.update(kw)
    p = os.path.join(_dir(state_dir, iid), 'meta.json')
    json.dump(m, open(p + '.tmp', 'w'), ensure_ascii=False, indent=1); os.replace(p + '.tmp', p)
    return m


def decide(state_dir, root, iid, action):
    """approve: copy the candidate next to the video (never over an existing file); reject: keep it, mark it; retry: forget it."""
    m = get(state_dir, iid); d = _dir(state_dir, iid)
    if action == 'retry':
        shutil.rmtree(d); return 'removed, the file will be produced again'
    if m['status'] == 'approved':
        return 'already approved'
    if action == 'reject':
        _set(state_dir, iid, status='rejected', decided=int(time.time())); return 'rejected'
    if action != 'approve':
        raise ValueError('unknown action')
    video = os.path.join(root, m['rel'])
    if not os.path.isfile(video):
        raise ValueError('the video is gone')
    if m.get('video') and m['video'] != video_sig(video):
        raise ValueError('the video was replaced after this subtitle was made; press "retry" to make it again')
    dest = os.path.join(os.path.dirname(video), '%s.%s.srt' % (m['stem'], m['lang']))
    if os.path.exists(dest):
        raise ValueError('%s already exists' % os.path.basename(dest))
    shutil.copyfile(os.path.join(d, 'sub.srt'), dest + '.tmp'); os.replace(dest + '.tmp', dest)
    _set(state_dir, iid, status='approved', decided=int(time.time()))
    return 'written ' + os.path.basename(dest)


def cues(state_dir, iid, t0, length):
    """Cues of the candidate inside [t0, t0+length] with times relative to the clip start. Text is returned as stored."""
    raw = open(os.path.join(_dir(state_dir, iid), 'sub.srt'), 'rb').read()
    txt = raw.decode('utf-8-sig', 'replace').replace('\r', '')
    out = []
    for blk in re.split(r'\n\s*\n', txt):
        ln = blk.strip('\n').split('\n')
        for i, l in enumerate(ln[:3]):
            m = re.match(r'\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})', l)
            if m:
                a = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4].ljust(3, '0')) / 1000
                b = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + int(m[8].ljust(3, '0')) / 1000
                if b >= t0 and a <= t0 + length:
                    out.append({'s': round(a - t0, 3), 'e': round(b - t0, 3), 'text': '\n'.join(ln[i + 1:])})
                break
    return out


def _clip_dir(state_dir):
    d = os.path.join(state_dir, 'tmp', 'clips'); os.makedirs(d, exist_ok=True)
    now = time.time()
    for f in os.listdir(d):  # clips are cheap to make again
        try:
            if now - os.path.getmtime(os.path.join(d, f)) > 86400:
                os.remove(os.path.join(d, f))
        except OSError:
            pass
    return d


def _cut(video, track, t0, length, out):
    """Audio track `track` (audio-relative index) of the video as constant-bitrate MP3 into `out`, atomically."""
    r = subprocess.run(['nice', '-n', '19', 'ffmpeg', '-v', 'error', '-y', '-ss', '%.3f' % t0, '-i', video, '-t', '%.3f' % length,
                        '-map', '0:a:%d' % int(track), '-vn', '-sn', '-dn', '-ac', '2', '-c:a', 'libmp3lame', '-b:a', '96k',
                        '-f', 'mp3', out + '.tmp.mp3'], capture_output=True, timeout=300)
    if r.returncode:
        try:
            os.remove(out + '.tmp.mp3')
        except OSError:
            pass
        raise RuntimeError('ffmpeg: ' + r.stderr.decode('utf-8', 'replace')[-200:])
    os.replace(out + '.tmp.mp3', out)


def clip(state_dir, root, iid, t0, length=CLIP_LEN):
    """Original-audio excerpt as constant-bitrate MP3 (decodes in every browser, even open-source builds, and seeks exactly). Cached; returns the file path."""
    m = get(state_dir, iid)
    t0 = max(0.0, float(t0)); length = min(max(5.0, float(length)), 120.0)
    video = os.path.join(root, m['rel'])
    if not os.path.isfile(video):
        raise ValueError('the video is gone')
    out = os.path.join(_clip_dir(state_dir), '%s_%s_%d_%d_%d.mp3' % (iid, m['track'], round(t0 * 10), round(length), m.get('created', 0)))
    if not os.path.exists(out):
        _cut(video, m['track'], t0, length, out)
    return out


def file_clip(state_dir, root, rel, track, t0, length, include, exclude):
    """A short excerpt of one audio track of a library file, for judging by ear which track is the original. `rel` comes from the
    browser: it must be a plain relative path inside one of the scanned top folders and a real file under `root`."""
    parts = rel.split('/')
    if (not rel or rel.startswith('/') or '\\' in rel or '\0' in rel or any(p in ('', '.', '..') for p in parts)
            or parts[0] not in include or any(p in exclude for p in parts)):
        raise ValueError('bad path')
    track = int(track)
    if not 0 <= track < 32:
        raise ValueError('bad track')
    base = os.path.realpath(root); video = os.path.realpath(os.path.join(root, rel))
    if not video.startswith(base + os.sep) or not os.path.isfile(video):
        raise ValueError('no such file')
    t0 = max(0.0, float(t0)); length = min(max(5.0, float(length)), 60.0)
    key = hashlib.sha1(('%s|%d|%d|%d|%d' % (rel, track, round(t0 * 10), round(length), os.path.getmtime(video))).encode()).hexdigest()[:16]
    out = os.path.join(_clip_dir(state_dir), 'f_%s.mp3' % key)
    if not os.path.exists(out):
        _cut(video, track, t0, length, out)
    return out
