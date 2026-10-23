"""Synthetic act-by-act subtitle: common slope inside acts, jumps at act breaks."""
import random, numpy as np
import engines, drift
from engines import read_skeleton
random.seed(3); np.random.seed(3)
BREAKS = [255, 885, 1515, 1995]; P = 0.0052
# true cues with silence around act breaks
t = 20.0; true = []
while t < 2400:
    d = random.uniform(1.0, 4.0)
    if any(b - 1 < t < b + 6 for b in BREAKS):
        t = max(b + 6 for b in BREAKS if b - 1 < t < b + 6); continue
    true.append((t, t + d)); t += d + random.choice([0.3, 0.5, 0.8, 1.2, 2, 4, 8, 16])
def act_of(x): return sum(x > b for b in BREAKS)
Q = [0.0, -3.1, -6.3, -9.6, -12.3]
def lag_true(f): return -(P * f + Q[act_of(f)])      # what the subtitle needs: new = f + lag
# input times F with F + lag(F) = T  (fixed point)
F = []
for s, e in true:
    f = s
    for _ in range(20): f = s - lag_true(f)
    g = e
    for _ in range(20): g = e - lag_true(g)
    F.append((f, g))
sp = drift.activity(true, 24100) * (np.random.rand(24100) > 0.1)
engines._ffsubsync = lambda m, sk, out: open(out, 'wb').write(open(sk, 'rb').read())
drift.speech = lambda p: sp
engines._SP.clear()
res, dropped, info = engines.sync('drift', 'fake', F, None, None)
err = np.array([abs(a[0] - b[0]) for a, b in zip(res, true)]); d = info['drift']
print('ok=%s p=%+.5f acts=%d cuts_at=%s offsets=%s' % (d['ok'], d['p'], len(d['qs']), [round(c) for c in d['cut_times']], [round(q, 2) for q in d['qs']]))
print('median %.3f  p95 %.3f  max %.2f  cues off by >0.5 s: %d of %d' % (np.median(err), np.percentile(err, 95), err.max(), (err > 0.5).sum(), len(err)))
assert d['ok'] and len(d['qs']) == 5 and abs(d['p'] + P) < 0.0008 and (err > 0.5).sum() <= 6, 'piecewise fit failed'
# straight line case must stay one act
F2 = [(s * 1.004 + 3, e * 1.004 + 3) for s, e in true]; engines._SP.clear()
res2, _, i2 = engines.sync('drift', 'fake', F2, None, None); e2 = np.array([abs(a[0] - b[0]) for a, b in zip(res2, true)])
print('straight line: acts=%d median %.3f p95 %.3f' % (len(i2['drift']['qs']), np.median(e2), np.percentile(e2, 95)))
assert len(i2['drift']['qs']) == 1 and np.percentile(e2, 95) < 0.3
# noise audio -> not trusted, input unchanged
engines._SP.clear(); drift.speech = lambda p: (np.random.rand(24100) > 0.5).astype(np.float32)
res3, _, i3 = engines.sync('drift', 'fake', F, None, None); print('noise audio ok=%s' % i3['drift']['ok']); assert not i3['drift']['ok']
print('OK')

# --- reference-based: audio is useless (noise), the original-language starts are all there is
good_ref = sorted(s + random.gauss(0, 0.12) for s, e in true if random.random() < 0.9)
drift.speech = lambda p: (np.random.rand(24100) > 0.5).astype(np.float32); engines._SP.clear()
res4, _, i4 = engines.sync('drift', 'fake', F, None, good_ref)
e4 = np.array([abs(a[0] - b[0]) for a, b in zip(res4, true)])
print('ref only: %s' % i4['chain'][:170]); print('median %.3f p95 %.3f max %.2f, >0.5 s: %d' % (np.median(e4), np.percentile(e4, 95), e4.max(), (e4 > 0.5).sum()))
assert 'chain via' in i4['chain'] and np.percentile(e4, 95) < 0.35 and (e4 > 0.5).sum() <= 3
junk = sorted(random.uniform(0, 2400) for _ in range(800)); engines._SP.clear()
res5, _, i5 = engines.sync('drift', 'fake', F, None, junk); print('junk ref ->', i5['chain'][:90]); assert 'chain not used' in i5['chain']
print('OK ref')

# --- act breaks must land on the right cue (not a few cues late), reference-based
engines._SP.clear(); res6, _, i6 = engines.sync('drift', 'fake', F, None, good_ref)
fit6 = drift.fit_segments_ref(res6 if False else F, good_ref)
miss = [min(abs(c - b) for b in BREAKS) for c in fit6['cut_times']]
print('cut distance from the true break (s, input timeline):', [round(m, 1) for m in miss]); assert max(miss) < 12 and len(miss) == 4  # the first cue of an act starts after the silence of the break
e6 = np.array([abs(a[0] - b[0]) for a, b in zip(res6, true)]); print('cues off by >0.3 s:', (e6 > 0.3).sum()); assert (e6 > 0.3).sum() <= 1

# --- ffsubsync drops the cues it pushes below zero; they must not pile up at 0 once the act shift is applied
early = [(0.4, 1.8), (1.9, 3.0), (3.2, 5.0), (5.3, 8.5), (8.7, 10.0)]
true8 = early + [c for c in true if c[0] > 12]
raw8 = [(s + 8.0, e + 8.0) for s, e in true8]             # raw file is 8 s late
def ffs_over(media, sk, out):                             # over-corrects by 8 s: ffsubsync output = raw - 16, cues below zero are dropped
    got = read_skeleton(sk); engines._write_indexed({k: (s - 16.0, e - 16.0) for k, (s, e) in got.items() if s - 16.0 > 0.05}, out)
engines._ffsubsync = ffs_over; drift.speech = lambda p: np.zeros(24100, dtype=np.float32); engines._SP.clear()
res8, dropped8, i8 = engines.sync('drift', 'fake', raw8, None, [s for s, e in true8])
starts8 = [a[0] for a in res8]; same = sum(1 for a, b in zip(starts8, starts8[1:]) if abs(a - b) < 1e-6)
err8 = np.array([abs(a[0] - b[0]) for a, b in zip(res8, true8)])
print('dropped by ffsubsync:', dropped8, '| cues stacked at one time:', same, '| max error %.2f s' % err8.max(), '|', i8['chain'][:90])
assert dropped8 >= 3 and same == 0 and err8.max() < 0.5
print('OK cuts+drops')
