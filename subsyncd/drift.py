"""Free-scale linear correction of a roughly aligned subtitle against the speech activity of the audio.
ffsubsync can only pick a standard frame-rate ratio (23.976/25 and the like). A subtitle timed for any other rate keeps a
straight-line drift of its own, up to several seconds over an episode. This module measures that drift on windows of the
episode, fits a line through the trustworthy windows and moves every cue along it. Timing only; text is never touched."""
import subprocess
import numpy as np

DT = 0.1          # seconds per activity sample
HALF = 45.0       # half-width of a measurement window
STEP = 30.0
MAXLAG = 15.0     # the input is already roughly aligned; the residual drift of the standard ratios stays well below this
MIN_CORR, MIN_MARGIN = 0.15, 0.03
INLIER = 1.0      # seconds


def speech(audio_path):
    """Share of speech per DT in the first audio stream of the file (webrtcvad, 20 ms frames)."""
    import webrtcvad
    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', audio_path, '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    v = webrtcvad.Vad(2); n = len(pcm) // 640
    m = np.fromiter((v.is_speech(pcm[i * 640:(i + 1) * 640], 16000) for i in range(n)), dtype=np.float32, count=n)
    k = int(round(DT / 0.02)); n2 = len(m) // k
    return m[:n2 * k].reshape(n2, k).mean(axis=1)


def activity(times, n):
    a = np.zeros(n, dtype=np.float32)
    for s, e in times:
        i, j = int(round(s / DT)), int(round(e / DT))
        if j >= 0 and i < n:
            a[max(i, 0):min(j + 1, n)] = 1
    return a


def _lag(a, b, t):
    """Window of a centred on t; L maximising corr(a[x], b[x+L]); b later than a gives L > 0. (L, corr, runner-up) or None."""
    i0, i1 = max(0, int((t - HALF) / DT)), min(len(a), int((t + HALF) / DT))
    if i1 - i0 < 300:
        return None
    wa = a[i0:i1]
    if not 0.15 < wa.mean() < 0.9:
        return None
    wa = wa - wa.mean(); na = np.sqrt((wa ** 2).sum())
    L = int(MAXLAG / DT); res = np.full(2 * L + 1, -1.0)
    for k, l in enumerate(range(-L, L + 1)):
        j0, j1 = i0 + l, i1 + l
        if j0 < 0 or j1 > len(b):
            continue
        wb = b[j0:j1] - b[j0:j1].mean(); nb = np.sqrt((wb ** 2).sum())
        if nb > 1e-6:
            res[k] = float((wa * wb).sum() / (na * nb))
    k = int(res.argmax()); far = res.copy(); far[max(0, k - 30):k + 31] = -1
    return (k - L) * DT, float(res[k]), float(far.max())


def _theil_sen(x, y):
    """Median pairwise slope over pairs at least 120 s apart; robust against the windows that locked onto the wrong peak."""
    i, j = np.triu_indices(len(x), 1)
    far = (x[j] - x[i]) >= 120
    if not far.any():
        return 0.0, float(np.median(y))
    p = float(np.median((y[j] - y[i])[far] / (x[j] - x[i])[far]))
    return p, float(np.median(y - p * x))


def fit_drift(times, sp):
    """times: roughly aligned [(start, end)]. Returns dict(ok, p, q, ...) with lag(t) = p*t + q: move a cue at t to t + lag(t)."""
    n = len(sp); act = activity(times, n)
    end = min(times[-1][1], n * DT)
    pts = []
    for t in np.arange(HALF, end - HALF + 1, STEP):
        r = _lag(act, sp, float(t))
        if r and r[1] >= MIN_CORR and r[1] - r[2] >= MIN_MARGIN:
            pts.append((float(t), r[0]))
    out = {'ok': False, 'windows': len(pts), 'p': 0.0, 'q': 0.0}
    if len(pts) < 8:
        return out
    x, y = np.array(pts).T
    p, q = _theil_sen(x, y)
    tol = 2.0
    for _ in range(4):
        ok = np.abs(y - (p * x + q)) <= tol
        if ok.sum() < 6:
            return out
        p, q = np.polyfit(x[ok], y[ok], 1)
        tol = INLIER
    ok = np.abs(y - (p * x + q)) <= INLIER
    res = np.abs(y - (p * x + q))[ok]
    out.update(p=float(p), q=float(q), inliers=int(ok.sum()), span=float(x[ok].max() - x[ok].min()), resid_med=float(np.median(res)),
               resid_max=float(res.max()))
    out['ok'] = bool(ok.sum() >= 8 and out['span'] >= 0.5 * (end - 2 * HALF) and out['resid_med'] <= 0.6)
    return out


def apply(times, p, q):
    return [(s + p * s + q, e + p * e + q) for s, e in times]


# ---------------------------------------------------------------------------------------------------------------------------
# Piecewise model. Many releases are timed act by act: inside an act the subtitle runs at a slightly wrong rate (a straight
# line), at an act break it jumps back by a few seconds. Seen on The Mentalist s06e03: slope 0.5 % per act, jumps of 3-4 s.
# One straight line cannot follow that, so lag(t) = p*t + q_k with one common slope p and one offset q_k per act.
STEP2 = 20.0


def _series(times, sp):
    n = len(sp); act = activity(times, n); end = min(times[-1][1], n * DT); pts = []
    for t in np.arange(HALF, end - HALF + 1, STEP2):
        r = _lag(act, sp, float(t))
        if r and r[1] >= MIN_CORR and r[1] - r[2] >= MIN_MARGIN:
            pts.append((float(t), r[0]))
    return np.array(pts, dtype=float).reshape(-1, 2), end


def _local_slope(x, y):
    """Median slope over pairs 1-5 minutes apart: a jump spoils only the pairs that straddle it."""
    i, j = np.triu_indices(len(x), 1)
    d = x[j] - x[i]; m = (d >= 60) & (d <= 300)
    return float(np.median((y[j] - y[i])[m] / d[m])) if m.sum() >= 20 else None


def _segment(yd, c=0.8, lam=6.0, minlen=8):
    """Piecewise-constant segmentation of the detrended lags (truncated squared loss, penalty per break)."""
    n = len(yd); INF = float('inf')
    if n < minlen:
        return [(0, n)]
    cost = {}
    def seg_cost(i, j):
        if (i, j) not in cost:
            v = yd[i:j]; cost[(i, j)] = float(np.minimum((v - np.median(v)) ** 2, c * c).sum())
        return cost[(i, j)]
    best = [INF] * (n + 1); best[0] = 0.0; prev = [0] * (n + 1)
    for j in range(minlen, n + 1):
        for i in range(0, j - minlen + 1):
            if best[i] == INF:
                continue
            v = best[i] + seg_cost(i, j) + (lam if i > 0 else 0.0)
            if v < best[j]:
                best[j], prev[j] = v, i
    segs, j = [], n
    while j > 0:
        segs.append((prev[j], j)); j = prev[j]
    return segs[::-1]


def _refine(x, y, lab, k):
    """Common slope and one offset per segment from the points that agree with the model (|residual| <= 0.7 s)."""
    p = _local_slope(x, y) or 0.0
    q = np.array([np.median((y - p * x)[lab == s]) for s in range(k)])
    for _ in range(4):
        inl = np.abs(y - (p * x + q[lab])) <= 0.7
        xs, ys = x.copy(), y.copy()
        for s in range(k):
            m = inl & (lab == s)
            if m.sum():
                xs[lab == s] -= x[m].mean(); ys[lab == s] -= y[m].mean()
        d = (xs[inl] ** 2).sum()
        if d > 0:
            p = float((xs[inl] * ys[inl]).sum() / d)
        q = np.array([np.median((y - p * x)[inl & (lab == s)]) if (inl & (lab == s)).any() else 0.0 for s in range(k)])
    inl = np.abs(y - (p * x + q[lab])) <= 0.7
    return p, q, inl


def _place_cut(times, sp, p, ql, qr, lo, hi):
    """Cue index where the next act starts: the candidate that makes the shifted cues best follow the speech around it."""
    n = len(sp); starts = np.array([s for s, _ in times])
    cand = [k for k in range(len(times)) if lo <= starts[k] <= hi]
    if not cand:
        return int(np.searchsorted(starts, (lo + hi) / 2))
    a0, a1 = int((lo - 60) / DT), int((hi + 60) / DT); a0 = max(a0, 0); a1 = min(a1, n)
    near = [k for k in range(len(times)) if lo - 80 <= starts[k] <= hi + 80]
    top, topk = -2.0, cand[0]
    for c in cand + [cand[-1] + 1]:
        mapped = [(times[k][0] + p * times[k][0] + (ql if k < c else qr), times[k][1] + p * times[k][1] + (ql if k < c else qr)) for k in near]
        a = activity(mapped, n)[a0:a1]; b = sp[a0:a1]
        if a.std() < 1e-6 or b.std() < 1e-6:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > top:
            top, topk = r, c
    return topk


MINJUMP = 1.2     # an act break shows as a jump of seconds; smaller steps are measurement noise, not a break


def _series_ref(times, ref, maxlag=12.0, half=45.0, step=15.0):
    """Same series as _series, but measured against the cue starts of a subtitle that is already synced (no text involved):
    best shift of the window's starts onto the reference starts, kept only when it clearly beats every other shift."""
    ref = np.sort(np.asarray(ref, float)); starts = np.array([s for s, _ in times]); end = float(times[-1][1])
    D = np.arange(-maxlag, maxlag + 1e-9, 0.05); pts = []
    for t in np.arange(half, end - half + 1, step):
        w = starts[(starts >= t - half) & (starts <= t + half)]
        if len(w) < 12:
            continue
        X = w[:, None] + D[None, :]; i = np.clip(np.searchsorted(ref, X), 1, len(ref) - 1)
        f = (np.minimum(np.abs(ref[i - 1] - X), np.abs(ref[i] - X)) < 0.35).mean(axis=0)
        top = np.flatnonzero(f >= f.max() - 1e-9); k = int(top[len(top) // 2])
        far = f.copy(); far[max(0, k - 20):k + 21] = 0
        if f[k] >= 0.5 and f[k] - far.max() >= 0.15:
            pts.append((float(t), float(D[k])))
    return np.array(pts, dtype=float).reshape(-1, 2), end, half


def _place_cut_ref(times, ref, p, ql, qr, lo, hi):
    ref = np.sort(np.asarray(ref, float)); starts = np.array([s for s, _ in times])
    cand = [k for k in range(len(times)) if lo <= starts[k] <= hi]
    if not cand:
        return int(np.searchsorted(starts, (lo + hi) / 2))
    near = [k for k in range(len(times)) if lo - 80 <= starts[k] <= hi + 80]
    best, bk = float('inf'), cand[0]
    for c in cand + [cand[-1] + 1]:
        m = np.array([times[k][0] + p * times[k][0] + (ql if k < c else qr) for k in near])
        i = np.clip(np.searchsorted(ref, m), 1, len(ref) - 1)
        cost = float(np.minimum(np.minimum(np.abs(ref[i - 1] - m), np.abs(ref[i] - m)), 1.0).sum())
        if cost < best:
            best, bk = cost, c
    return bk


def _fit_pts(pts, end, times, cutter, half=HALF, minlen=8, lam=6.0, support=5):
    out = {'ok': False, 'windows': int(len(pts)), 'p': 0.0, 'qs': [0.0], 'cuts': [], 'cut_times': []}
    if len(pts) < 12:
        return out
    x, y = pts.T; p0 = _local_slope(x, y)
    if p0 is None:
        return out
    segs = _segment(y - p0 * x, lam=lam, minlen=minlen)
    while True:
        lab = np.zeros(len(x), int)
        for s, (i, j) in enumerate(segs):
            lab[i:j] = s
        p, q, inl = _refine(x, y, lab, len(segs))
        if len(segs) == 1:
            break
        weak = [s for s in range(len(segs)) if (inl & (lab == s)).sum() < support]
        if weak:  # a segment without support is merged into its longer neighbour
            s = weak[0]
            nb = s - 1 if s == len(segs) - 1 or (s > 0 and segs[s - 1][1] - segs[s - 1][0] >= segs[s + 1][1] - segs[s + 1][0]) else s + 1
            a, b = sorted((s, nb))
        else:  # a step too small to be an act break is merged away
            steps = [abs(q[s + 1] - q[s]) for s in range(len(segs) - 1)]
            a = int(np.argmin(steps))
            if steps[a] >= MINJUMP:
                break
            b = a + 1
        segs = segs[:a] + [(segs[a][0], segs[b][1])] + segs[b + 1:]
    res = np.abs(y - (p * x + q[lab]))[inl]
    if inl.sum() < 8:
        return out
    cuts, cut_times = [], []
    for s in range(len(segs) - 1):
        tl = x[inl & (lab == s)].max(); tr = x[inl & (lab == s + 1)].min()
        # a window stays a clean member of its act while the act still holds most of its cues, so the break lies between the
        # centres of the last window of one act and the first of the next, not further out
        lo, hi = tl - 10, tr + 10
        k = cutter(p, float(q[s]), float(q[s + 1]), lo, hi)
        cuts.append(int(k)); cut_times.append(float(times[min(k, len(times) - 1)][0]))
    span = float(x[inl].max() - x[inl].min())
    out.update(p=float(p), qs=[float(v) for v in q], cuts=cuts, cut_times=cut_times, inliers=int(inl.sum()), span=span,
               resid_med=float(np.median(res)), resid_max=float(res.max()))
    out['ok'] = bool(inl.mean() >= 0.6 and span >= 0.6 * (end - 2 * half) and out['resid_med'] <= 0.5 and cuts == sorted(set(cuts)))
    return out


def fit_segments(times, sp):
    """Returns dict(ok, p, qs, cuts, cut_times, windows, inliers, span, resid_med, resid_max); a cue with index >= cuts[i] belongs to
    act i+1 and moves by p*t + qs[i+1]. One act (no cuts) is the plain straight-line case. Measured against the speech in the audio."""
    pts, end = _series(times, sp)
    return _fit_pts(pts, end, times, lambda p, ql, qr, lo, hi: _place_cut(times, sp, p, ql, qr, lo, hi))


def fit_segments_ref(times, ref):
    """Same model, measured against the cue starts of an already synced subtitle in the original language."""
    pts, end, half = _series_ref(times, ref)
    return _fit_pts(pts, end, times, lambda p, ql, qr, lo, hi: _place_cut_ref(times, ref, p, ql, qr, lo, hi), half, 4, 2.5, 4)


def apply_segments(times, p, qs, cuts):
    out, seg = [], 0
    for k, (s, e) in enumerate(times):
        while seg < len(cuts) and k >= cuts[seg]:
            seg += 1
        out.append((s + p * s + qs[seg], e + p * e + qs[seg]))
    return out
