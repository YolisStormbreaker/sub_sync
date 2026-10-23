"""Quality gate, review store, priorities and the three-stage order of work(). Run: python3 test_gate.py"""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import main, media, engines, osapi, quality, review, prio

# ---- quality.assess
good = {'chain_q': {'acts': 5, 'windows': 150, 'inliers': 145, 'near': 0.91, 'resid_med': 0.2, 'p': -0.00003, 'cuts': [10, 20]}}
q = quality.assess(good, 'ok', True); assert q['verdict'] == 'ok' and q['metrics']['mode'] == 'chain', q
assert quality.assess(good, 'review', True)['verdict'] == 'ok'                           # unconfirmed reference, but near06 0.91 >= 0.90
mid = {'chain_q': dict(good['chain_q'], near=0.88)}
assert quality.assess(mid, 'ok', True)['verdict'] == 'ok' and quality.assess(mid, 'review', True)['verdict'] == 'review'   # 0.88 passes only with a confirmed reference
low = {'chain_q': dict(good['chain_q'], near=0.62)}; q = quality.assess(low, 'ok'); assert q['verdict'] == 'review' and 'within 0.6 s' in q['reasons'][0]
few = {'chain_q': dict(good['chain_q'], inliers=100)}; assert quality.assess(few, 'ok')['verdict'] == 'review'
aud = {'drift': {'ok': True, 'inliers': 90, 'windows': 100, 'qs': [0.0], 'p': 0.0001, 'resid_med': 0.2}}
assert quality.assess(aud)['verdict'] == 'ok'                                            # the original language, one act
assert quality.assess(aud, None, True)['verdict'] == 'review' and 'original audio' in quality.assess(aud, None, True)['reasons'][0]   # a reference existed but the chain fit failed
assert quality.assess(aud, None, False, True)['verdict'] == 'review' and 'no original-language subtitle' in quality.assess(aud, None, False, True)['reasons'][0]
assert quality.assess({'drift': dict(aud['drift'], resid_med=0.6)})['verdict'] == 'review'
assert quality.assess({'drift': dict(aud['drift'], inliers=50)})['verdict'] == 'review'
assert quality.assess({'drift': {'ok': False, 'windows': 40}})['verdict'] == 'review'    # plain ffsubsync
assert quality.assess({'drift': dict(aud['drift'], qs=[0] * 9)})['verdict'] == 'review'  # too many acts
assert quality.assess({'chain_q': dict(good['chain_q'], p=0.02)}, 'ok')['verdict'] == 'review'
print('quality ok')

# ---- priorities
pr = prio.Priorities(os.path.join(state, 'p.json'))
assert pr.get('TVshows/A/x.mkv', 'sync') == 1 and pr.get('Movies/m.mkv', 'download') == 3
pr.set('TVshows/A', {'download': 5, 'sync': 0}); pr.set('TVshows/A/S01/x.mkv', {'sync': 2})
assert pr.get('TVshows/A/S01/x.mkv', 'sync') == 2 and pr.get('TVshows/A/S01/y.mkv', 'sync') == 0     # file beats folder, per stage
assert pr.get('TVshows/A/S01/x.mkv', 'download') == 5 and pr.get('TVshows/A/S01/x.mkv', 'scan') == 1
for bad in (('Others/x', {'sync': 1}), ('TVshows/A', {'sync': 10}), ('TVshows/A', {'bogus': 1}), ('TVshows/../x', {'sync': 1}), ('TVshows/A', {'sync': True})):
    try: pr.set(*bad); raise SystemExit('accepted %r' % (bad,))
    except ValueError: pass
pr.set('TVshows/A', {'download': None, 'sync': None}); assert 'TVshows/A' not in pr.all()
print('prio ok')

# ---- review store
v = os.path.join(root, 'TVshows/Show/Show.S01E02.720p.mkv'); os.makedirs(os.path.dirname(v)); open(v, 'wb').write(b'x' * 200000)
nt = [(float(i * 10), float(i * 10 + 3)) for i in range(100)]
pts = review.check_points(nt, [30, 60], 1000.0); print('points', pts)
assert pts == [0.0, 296.0, 496.0, 596.0, 846.0], pts      # start, 6 s before each break (cue 30 at 300 s, cue 60 at 600 s), middle, late; each 4 s before a cue
data = '1\n00:00:01,000 --> 00:00:03,000\nПривет\nмир\n\n2\n00:02:00,500 --> 00:02:02,000\n<i>Дальше</i>\n'.encode()
qq = quality.assess({'drift': {'ok': False, 'windows': 3}})
iid = review.hold(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'ru', 'Show.S01E02.720p', 0, data, qq, [0.0, 118.0], 3000)
assert review.blocked(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'ru') and not review.blocked(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'en')
c = review.cues(state, iid, 100, 40); assert len(c) == 1 and c[0]['text'] == '<i>Дальше</i>' and abs(c[0]['s'] - 20.5) < 1e-6, c
c = review.cues(state, iid, 0, 40); assert c[0]['text'] == 'Привет\nмир', c
try: review.decide(state, root, '../../etc', 'approve'); raise SystemExit('bad id accepted')
except ValueError: pass
print(review.decide(state, root, iid, 'reject')); assert review.blocked(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'ru')
print(review.decide(state, root, iid, 'approve'))
dest = os.path.join(os.path.dirname(v), 'Show.S01E02.720p.ru.srt'); assert open(dest, 'rb').read() == data     # byte-identical copy
assert not review.blocked(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'ru')
try: review.decide(state, root, iid, 'retry'); review.hold(state, 'TVshows/Show/Show.S01E02.720p.mkv', 'ru', 'Show.S01E02.720p', 0, data, qq, [0.0], 1); review.decide(state, root, iid, 'approve'); raise SystemExit('overwrote')
except ValueError as e: print('refused:', e)
os.remove(dest); review.decide(state, root, iid, 'retry')
print('review ok')

# ---- real audio clip (ffmpeg): two tracks, the clip must come from the chosen one
if subprocess.run(['which', 'ffmpeg'], capture_output=True).returncode == 0:
    vf = os.path.join(root, 'TVshows/Show/Show.S01E03.720p.mkv')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=440:d=60', '-f', 'lavfi', '-i', 'sine=f=880:d=60', '-map', '0', '-map', '1', '-c:a', 'aac', vf], check=True)
    i2 = review.hold(state, 'TVshows/Show/Show.S01E03.720p.mkv', 'en', 'Show.S01E03.720p', 1, data, qq, [0.0], 60)
    p = review.clip(state, root, i2, 10, 20)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], capture_output=True, text=True).stdout)
    assert 19.5 < dur < 20.6, dur
    print('clip ok', round(dur, 2), os.path.getsize(p)); review.decide(state, root, i2, 'retry')

# ---- three stages in their own order
for n in ('A', 'B', 'C'):
    p = os.path.join(root, 'TVshows/%s/%s.S01E01.mkv' % (n, n)); os.makedirs(os.path.dirname(p)); open(p, 'wb').write(b'x' * 200000)
    os.utime(p, (1000, 1000))
pr = prio.Priorities(os.path.join(state, 'priorities.json'))
pr.set('TVshows/A', {'download': 3, 'sync': 1}); pr.set('TVshows/B', {'download': 1, 'sync': 3}); pr.set('TVshows/C', {'sync': 0})
ctx = main.Ctx(network=False)
calls = []
main.get_raw = lambda video, lang, ctx, dry=False: (calls.append(('dl', os.path.basename(video)[0], lang)) or (b'1\n00:00:01,000 --> 00:00:02,000\nx\n', 'm', False, {'mode': 'cache', 'remaining': 5}))
main.LazyAudio = lambda video, rel: type('L', (), {'path': lambda s: 'a', 'close': lambda s: None})()
engines.sync = lambda eng, a, raw, tmp=None, ref=None: ([(1.0, 2.0)], 0, {'drift': {'ok': True, 'inliers': 9, 'windows': 9, 'qs': [0], 'p': 0, 'resid_med': 0.1, 'cuts': [], 'cut_times': []}})
orig_process = main.process
def spy(video, lang, *a, **k):
    calls.append(('sync', os.path.basename(video)[0], lang)); return orig_process(video, lang, *a, **k)
main.process = spy
def d(v): return {'orig': 'en', 'rel': 0, 'why': 't', 'conf': True, 'detect': False, 'todo': ['en'], 'missing': ['en'], 'held': []}
vids = [os.path.join(root, 'TVshows/%s/%s.S01E01.mkv' % (n, n)) for n in 'ABC']
main.work(ctx, [(x, d(x)) for x in vids], 'drift', None, 'backlog', mode='gate')
print(calls)
assert [c[1] for c in calls if c[0] == 'dl'] == ['B', 'C', 'A'], calls        # download: B(1) and C(default 1, same age: by path) before A(3)
assert [c[1] for c in calls if c[0] == 'sync'] == ['A', 'B'], calls            # sync: A(1) B(3), C paused
print('stages ok')
rows = quality.latest(state); assert any(r['rel'].endswith('A.S01E01.mkv') and r['action'] == 'written' for r in rows)
print('all ok')
