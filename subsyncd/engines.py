"""Sync engines. Every engine sees only a timing skeleton of the subtitle (text replaced by 'c<index>'), so it can neither
read nor change the real text; the result is a list of (start, end) per original cue, applied by srtio.retime."""
import contextlib, hashlib, os, re, subprocess, tempfile
from srtio import parse_times, clamp

PY = '/home/node/.local/pipx/venvs/ffsubsync/bin/python'
FFSUBSYNC = '/home/node/.local/bin/ffsubsync'
ALIGN = '/t/align.py'
LAST = {}    # facts the last sync step found out (drift fit), returned to the caller as info
_SP = {}     # speech activity per extracted audio file, computed once and shared by the languages of one video
TS = re.compile(rb'(\d+:\d\d:\d\d[,.]\d+)\s*-->\s*(\d+:\d\d:\d\d[,.]\d+)[^\n]*\n\s*c(\d+)\s*\n')


def _fmt(t):
    ms = max(0, round(t * 1000)); h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, ms = divmod(r, 1000)
    return '%02d:%02d:%02d,%03d' % (h, m, s, ms)


def skeleton(times, path):
    with open(path, 'w') as f:
        for k, (s, e) in enumerate(times):
            f.write('%d\n%s --> %s\nc%d\n\n' % (k + 1, _fmt(s), _fmt(e), k))


def read_skeleton(path):
    out = {}
    for m in TS.finditer(open(path, 'rb').read().replace(b'\r', b'')):
        a, b = m.group(1).split(b':'), m.group(2).split(b':')
        sec = lambda p: int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2].replace(b',', b'.').split(b'.')[0]) + int((p[2].replace(b',', b'.').split(b'.') + [b'0'])[1].ljust(3, b'0')) / 1000
        out[int(m.group(3))] = (sec(a), sec(b))
    return out


def _run(cmd, timeout=3600):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError('%s failed: %s' % (os.path.basename(cmd[0]), r.stderr.decode('utf-8', 'replace')[-300:]))


def _extract(media, rel, dst):
    """Audio-only copy of the original track: alass cannot choose a stream and ffsubsync would otherwise pick the first one."""
    _run(['ffmpeg', '-v', 'error', '-y', '-i', media, '-map', '0:a:%d' % rel, '-vn', '-sn', '-dn', '-c:a', 'copy', dst])


def _ffsubsync(media, sk, out):
    _run([FFSUBSYNC, media, '-i', sk, '-o', out])


def _alass(media, sk, out, split_penalty=3):
    _run(['alass', '-g', '-p', str(split_penalty), media, sk, out])


def _viterbi(media, sk, out, lam=12):
    _run([PY, ALIGN, media, '0:a:0', sk, out, str(lam)])


def _write_indexed(got, path):
    """Skeleton with the original cue numbers kept in the placeholders (cues an earlier step dropped stay missing)."""
    with open(path, 'w') as f:
        for n, k in enumerate(sorted(got)):
            s, e = got[k]
            f.write('%d\n%s --> %s\nc%d\n\n' % (n + 1, _fmt(s), _fmt(e), k))


def _drift(media, sk, out):
    """Free-scale straight-line correction against the speech in the audio (drift.py). ffsubsync only knows the standard
    frame-rate ratios, so a subtitle timed for another rate keeps a straight-line drift; this step removes it. When the fit is
    not well supported the input passes through unchanged."""
    import drift
    got = read_skeleton(sk); keys = sorted(got); times = [got[k] for k in keys]
    if media not in _SP:
        if len(_SP) > 3:
            _SP.clear()
        _SP[media] = drift.speech(media)
    fit = drift.fit_segments(times, _SP[media])
    if fit['ok']:
        times = drift.apply_segments(times, fit['p'], fit['qs'], fit['cuts'])
    LAST['drift'] = fit
    _write_indexed(dict(zip(keys, times)), out)


def _chain(base, ref):
    """Second-language subtitle against an already synced original-language one: cue starts alone (no text) are compared, and
    the same act-by-act model is fitted (drift.fit_segments_ref). Used only when the fit is well supported. (times or None, info)"""
    import drift
    import numpy as np
    fit = drift.fit_segments_ref(base, ref)
    if not fit['ok']:
        return None, {'text': 'chain not used (%d windows agree with the original-language subtitle, fit not trusted)' % fit['windows']}
    new = drift.apply_segments(base, fit['p'], fit['qs'], fit['cuts'])
    r = np.sort(np.asarray(ref, float)); m = np.array([s for s, _ in new]); i = np.clip(np.searchsorted(r, m), 1, len(r) - 1)
    near = float((np.minimum(np.abs(r[i - 1] - m), np.abs(r[i] - m)) < 0.6).mean())
    cuts = ', '.join('%d:%02d' % divmod(int(t), 60) for t in fit['cut_times'])
    q = {'acts': len(fit['qs']), 'windows': fit['windows'], 'inliers': fit['inliers'], 'near': near, 'resid_med': fit['resid_med'],
         'p': fit['p'], 'cuts': fit['cuts']}
    return new, {'q': q, 'text': 'chain via the original-language subtitle: p=%+.5f, %d act%s%s, offsets %s s, %d of %d windows, %.0f%% of cue starts within 0.6 s of it' % (
        fit['p'], len(fit['qs']), '' if len(fit['qs']) == 1 else 's', ' (breaks at %s)' % cuts if cuts else '',
        '/'.join('%+.1f' % q for q in fit['qs']), fit['inliers'], fit['windows'], 100 * near)}


ENGINES = {'ffsubsync': ['ffsubsync'], 'viterbi': ['ffsubsync', 'viterbi'], 'alass': ['ffsubsync', 'alass'], 'drift': ['ffsubsync', 'drift']}


@contextlib.contextmanager
def prepare(media, rel, tmp=None):
    """Extracts the original audio track once per video; every language of that video is synced against the same file."""
    with tempfile.TemporaryDirectory(dir=tmp) as w:
        key = hashlib.sha1(('%s|%d|%d' % (media, os.path.getsize(media), os.path.getmtime(media))).encode()).hexdigest()[:16]
        audio = os.path.join(w, key + '.mkv'); _extract(media, rel, audio)  # unique name: align.py caches its VAD by file name
        yield audio


def _tidy(out):
    """Each cue on its own: start >= 0, end after start. Cues are not forced into start order: a sign or song cue stored out of
    order in the file must keep its own time instead of being dragged to its neighbour's."""
    return [clamp(s, e) for s, e in out]


def sync(engine, audio, raw_times, tmp=None, ref=None):
    """Return (new (start, end) for every cue of the raw file in order, number of cues the engine dropped, info).
    ref: start times of an already synced subtitle in the original language; only the 'drift' engine uses it."""
    n = len(raw_times); LAST.clear()
    with tempfile.TemporaryDirectory(dir=tmp) as w:
        cur = os.path.join(w, 'in.srt'); skeleton(raw_times, cur)
        for i, step in enumerate(ENGINES[engine]):
            nxt = os.path.join(w, 'step%d.srt' % i)
            {'ffsubsync': _ffsubsync, 'viterbi': _viterbi, 'alass': _alass, 'drift': _drift}[step](audio, cur, nxt)
            cur = nxt
        got = read_skeleton(cur)
    if not got:
        raise RuntimeError('engine returned no cues')
    # cues an engine dropped (ffsubsync drops cues shifted below 0) keep the shift of the nearest surviving cue
    keys = sorted(got)
    out = []
    for k in range(n):
        if k in got:
            out.append(got[k]); continue
        j = min(keys, key=lambda x: abs(x - k))
        d = got[j][0] - raw_times[j][0]
        out.append((raw_times[k][0] + d, raw_times[k][1] + d))
    info = dict(LAST)
    res = None
    if engine == 'drift' and ref is not None and len(ref) >= 50:
        # on the unclamped times: cues that ffsubsync pushed below zero must not be piled up at 0 before the shift is applied
        ch, cinfo = _chain(out, ref)
        info['chain'] = cinfo['text']; info['chain_q'] = cinfo.get('q')
        if ch:
            res = _tidy(ch)
    if res is None:
        res = _tidy(out)
    return res, n - len(got), info
