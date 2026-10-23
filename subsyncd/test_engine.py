"""Synthetic check of the 'drift' engine: ffsubsync and the audio VAD are replaced by fakes, everything else is real code."""
import sys, os, random
import numpy as np
import engines, drift
from engines import skeleton, read_skeleton

random.seed(7); np.random.seed(7)
# true timeline: dialogue cues over ~40 min
t = 20.0; true = []
while t < 2400:
    d = random.uniform(1.0, 4.0); true.append((t, t + d)); t += d + random.choice([0.4, 0.8, 1.5, 3, 6, 12, 25])
n_ = len(true)
SCALE, OFFS = 0.95392, 0.62            # the real e03 relation: true = SCALE*raw + OFFS
raw = [((s - OFFS) / SCALE, (e - OFFS) / SCALE) for s, e in true]
speech_arr = drift.activity(true, 24100) * (np.random.rand(24100) > 0.1)   # speech activity of the audio, 10 % dropout

def fake_ffsubsync(media, sk, out):         # standard ratio only, as ffsubsync does
    got = read_skeleton(sk); engines._write_indexed({k: (s * 0.95903, e * 0.95903) for k, (s, e) in got.items()}, out)
engines._ffsubsync = fake_ffsubsync

def run(sp, ref=None, name=''):
    engines._SP.clear(); drift.speech = lambda p: sp
    res, dropped, info = engines.sync('drift', 'fake', raw, None, ref)
    err = np.array([abs(a[0] - b[0]) for a, b in zip(res, true)])
    print('%-22s median %.2f  p95 %.2f  max %.2f   drift ok=%s  chain=%s' % (name, np.median(err), np.percentile(err, 95), err.max(),
          (info.get('drift') or {}).get('ok'), (info.get('chain') or '-')[:70]))
    return err, info

e1, i1 = run(speech_arr, None, 'audio only')
assert i1['drift']['ok'] and np.percentile(e1, 95) < 0.6, 'audio-only fit failed'
good_ref = [s + random.gauss(0, 0.15) for s, e in true if random.random() < 0.9]
e2, i2 = run(speech_arr, good_ref, 'audio + good chain')
assert 'chain via' in i2['chain'] and np.percentile(e2, 95) < 0.4, 'chain failed'
junk = sorted(random.uniform(0, 2400) for _ in range(800))
e3, i3 = run(speech_arr, junk, 'audio + junk reference')
assert 'chain not used' in i3['chain'] and np.percentile(e3, 95) < 0.6, 'junk reference not rejected'
noise = (np.random.rand(24100) > 0.5).astype(np.float32)
e4, i4 = run(noise, None, 'no usable audio')
assert not i4['drift']['ok'], 'noise must not give a trusted fit'
e5, i5 = run(noise, good_ref, 'noise audio + good chain'); assert 'chain via' in i5['chain'] and np.percentile(e5, 95) < 0.4
print('OK')
