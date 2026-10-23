"""Original-track detection for videos whose audio tracks carry no usable tags (two or more 'und' tracks).
The subtitle in the ORIGINAL language is globally aligned (ffsubsync, timing skeleton only) against every candidate
track separately; the track whose speech activity matches the cues best is the original, a dub matches worse because
its phrases start later and break differently. Nothing here reads or writes subtitle text."""
import json, os, subprocess, sys, tempfile
import numpy as np, webrtcvad
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engines
from srtio import parse_times

FR = 0.02          # webrtcvad frame, seconds
ONSET_CAP = 1.5    # an onset farther than this from a cue start counts as a miss


def speech_mask(path):
    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    v = webrtcvad.Vad(2); n = len(pcm) // 640
    return np.fromiter((v.is_speech(pcm[i * 640:(i + 1) * 640], 16000) for i in range(n)), dtype=bool, count=n)


def metrics(times, m):
    """times: aligned (start, end) per cue; m: boolean speech mask. Returns plain floats."""
    n = len(m); C = np.concatenate([[0], np.cumsum(m.astype(np.int32))])
    idx = lambda t: np.clip(np.round(np.asarray(t) / FR).astype(int), 0, n)
    A = np.array([t[0] for t in times]); B = np.array([t[1] for t in times])
    a, b = idx(A), idx(B)
    ok = b - a >= 5
    inside = (C[b] - C[a])[ok] / (b - a)[ok]
    nxt = np.append(A[1:], B[-1] + 2.0)
    c = idx(nxt); gap = c - b; g = gap > 5
    outside = (C[c] - C[b])[g & ok[:len(g)]] / gap[g & ok[:len(g)]] if g.any() else np.array([0.0])
    on = np.where(m[1:] & ~m[:-1])[0] + 1
    on_t = on * FR
    pos = np.searchsorted(on_t, A)
    left = np.where(pos > 0, np.abs(A - on_t[np.clip(pos - 1, 0, len(on_t) - 1)]), 1e9)
    right = np.where(pos < len(on_t), np.abs(on_t[np.clip(pos, 0, len(on_t) - 1)] - A), 1e9)
    err = np.minimum(np.minimum(left, right), ONSET_CAP)
    return {'inside': float(inside.mean()), 'outside': float(outside.mean()), 'contrast': float(inside.mean() - outside.mean()),
            'onset_med': float(np.median(err)), 'onset_mean': float(err.mean()), 'speech_share': float(m.mean())}


# Thresholds fitted on 23 videos with a known original track (see the validation notes): both metrics must name the same
# track, the contrast gap must reach MIN_MARGIN and the onset-error gap MIN_ONSET_GAP seconds. Anything weaker is left to a person.
MIN_MARGIN = 0.03
MIN_ONSET_GAP = 0.10


def choose(res):
    """(rel, margin, sure). margin = contrast gap between the best track and the runner-up."""
    by_c = sorted(res, key=lambda r: -res[r]['contrast'])
    by_o = sorted(res, key=lambda r: res[r]['onset_mean'])
    margin = res[by_c[0]]['contrast'] - res[by_c[1]]['contrast']
    gap = res[by_o[1]]['onset_mean'] - res[by_o[0]]['onset_mean']
    return by_c[0], margin, bool(by_c[0] == by_o[0] and margin >= MIN_MARGIN and gap >= MIN_ONSET_GAP)


def analyze(video, rels, raw_times, tmp):
    """{rel: metrics} for each candidate audio track."""
    res = {}
    for rel in rels:
        with tempfile.TemporaryDirectory(dir=tmp) as w:
            audio = os.path.join(w, 'a%d.mkv' % rel)
            engines._extract(video, rel, audio)
            sk, out = os.path.join(w, 'sk.srt'), os.path.join(w, 'out.srt')
            engines.skeleton(raw_times, sk)
            engines._ffsubsync(audio, sk, out)
            got = engines.read_skeleton(out)
            t = [got[k] for k in sorted(got)]
            res[rel] = metrics(t, speech_mask(audio)); res[rel]['cues_kept'] = len(t)
    return res


if __name__ == '__main__':
    video, srt = sys.argv[1], sys.argv[2]
    rels = [int(x) for x in sys.argv[3:]]
    print(json.dumps(analyze(video, rels, parse_times(open(srt, 'rb').read()), os.environ.get('TMPDIR')), indent=1))
