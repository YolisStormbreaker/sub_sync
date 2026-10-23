"""Regression tests for the findings of the 2026-10-23 code review. Run: python3 test_fixes13.py"""
import json, os, sys, tempfile, threading, time, multiprocessing, base64, urllib.request, urllib.error
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import main, media, engines, osapi, quality, review, resolve, web, jsonstore, missing, prio
from overrides import Overrides

# H1: concurrent writers (threads and processes) lose nothing, a corrupt file is never wiped
OP = os.path.join(state, 'overrides.json'); o = Overrides(OP)
for i in range(50): o.set('TVshows/Old/%d.mkv' % i, 'en', None)
def burst(tag):
    oo = Overrides(OP)
    for i in range(30): oo.set('TVshows/T%s/%d.mkv' % (tag, i), 'en', i % 3)
ths = [threading.Thread(target=burst, args=('t%d' % k,)) for k in range(6)]
prs = [multiprocessing.Process(target=burst, args=('p%d' % k,)) for k in range(3)]
for x in ths + prs: x.start()
for x in ths + prs: x.join()
n = len(json.load(open(OP))); assert n == 50 + 9 * 30, n
assert not [f for f in os.listdir(state) if f.endswith('.tmp')], os.listdir(state)
open(OP, 'w').write('{"TVshows/Old/1.mkv": {"lang": "en"'); o2 = Overrides(OP)
try: o2.set('TVshows/X/y.mkv', 'en', None); assert 0, 'a corrupt file must not be overwritten'
except jsonstore.Corrupt: pass
assert open(OP).read().startswith('{"TVshows/Old/1.mkv"'), 'corrupt file untouched'
assert o.lookup('TVshows/Old/1.mkv') == {'lang': 'en', 'track': None}, 'a reader keeps the last good copy'
os.remove(OP)
pp = prio.Priorities(os.path.join(state, 'p.json')); pp.set('TVshows/A', {'sync': 3}); pp.set('TVshows/A', {'scan': 2}); assert pp.all()['TVshows/A'] == {'sync': 3, 'scan': 2}
try: pp.set('Others/x', {'sync': 1}); assert 0
except ValueError: pass
print('H1 ok')

# M6 + why: a folder-wide track fills in only where tags cannot tell; the track reason is not replaced by the language source
o = Overrides(OP); o.set('TVshows/DW', 'en', 1)
au = lambda *ls: {'audio': [{'rel': i, 'index': i + 1, 'lang': l, 'title': '', 'original': False} for i, l in enumerate(ls)], 'subs': []}
assert resolve.resolve('TVshows/DW/s1/a.mkv', '/x', au('und'), o, None)[:4] == ('en', 0, 'single audio track', True)
assert resolve.resolve('TVshows/DW/s1/a.mkv', '/x', au('und', 'und'), o, None)[:4] == ('en', 1, 'chosen track (folder)', True)
assert resolve.resolve('TVshows/DW/s1/a.mkv', '/x', au('ru', 'en'), o, None)[1:3] == (1, 'first track that is not ru/uk/dub')
o.set('TVshows/DW/s1/b.mkv', None, 4)
r = resolve.resolve('TVshows/DW/s1/b.mkv', '/x', au('und', 'und'), o, None); assert r == ('en', 4, 'chosen track is not in this file', False), r
o.set('TVshows/BM', 'en', None); r = resolve.resolve('TVshows/BM/e1.avi', '/x', au('und', 'und'), o, None); assert r[2] == 'several untagged audio tracks', r
os.remove(OP); print('M6 ok')

# M3: out-of-order cues keep their own times
assert engines._tidy([(10, 12), (20, 22), (3000, 3002), (30, 31)]) == [(10, 12), (20, 22), (3000, 3002), (30, 31)]
assert engines._tidy([(-1, 2), (5, 4)])[0][0] == 0
print('M3 ok')

# H4, M1, M2 through get_raw / decide with a fake OpenSubtitles
v = os.path.join(root, 'TVshows/Show/Show.S01E02.mkv'); os.makedirs(os.path.dirname(v)); open(v, 'wb').write(b'x' * 200000)
media.probe = lambda p: {'audio': [{'index': 1, 'lang': 'ru', 'title': 'Dub', 'original': False, 'rel': 0}, {'index': 2, 'lang': 'en', 'title': '', 'original': False, 'rel': 1}], 'subs': [], 'duration': 1}
good = b'1\n00:00:01,000 --> 00:00:02,000\nHi\n\n'
class Fake:
    files, dl = [7], 0
    def search(s, lang, h, g, hint=None): return [{'files': [{'file_id': f}], 'release': 'Show.S01E02', 'fps': 25.0, 'download_count': 1} for f in s.files]
    def languages_found(s, h, g, hint=None): return {}
    pick = staticmethod(osapi.OS.pick)
    def download(s, fid): s.dl += 1; return (b'' if fid == 7 else good), {'mode': 'keyonly', 'remaining': 50}
ctx = main.Ctx(network=False); ctx.osc = Fake()
r = main.get_raw(v, 'ru', ctx); assert r[0] is None and 'marked unusable' in r[1] and r[2], r
r = main.get_raw(v, 'ru', ctx); assert ctx.osc.dl == 1 and r[0] is None and 'only unusable' in r[1], (ctx.osc.dl, r)   # not paid again
key = main.lang_key(v, 'ru'); assert key in ctx.st['notfound'] and missing.load(state)[key]['code'] == 'filtered'
ctx.osc.files = [7, 8]; ctx.st['notfound'][key] = 0   # later a usable file appears
r = main.get_raw(v, 'ru', ctx); assert r[0] == good and key not in ctx.st['notfound'] and key not in missing.load(state), r
d = main.decide(v, ctx); assert 'ru' in d['todo'], d
ctx.st.setdefault('failed', {})[key] = int(time.time()); d = main.decide(v, ctx); assert 'ru' not in d['todo'] and d['failed'] == ['ru'], d
ctx.st['failed'][key] = int(time.time()) - 8 * 86400; assert 'ru' in main.decide(v, ctx)['todo']
print('H4 M1 M2 ok')

# H2: the original-language subtitle already next to the video is the reference, trusted only if this service wrote it
srt = ''.join('%d\n00:%02d:%02d,000 --> 00:%02d:%02d,500\nLine\n\n' % (i + 1, i // 60, i % 60, i // 60, i % 60) for i in range(80)).encode()
open(os.path.join(os.path.dirname(v), 'Show.S01E02.en.srt'), 'wb').write(srt)
ref, rv = main.sidecar_ref(v, {'orig': 'en'}); assert len(ref) == 80 and rv == 'review', rv
quality.record(state, 'TVshows/Show/Show.S01E02.mkv', 'en', 'drift', {'verdict': 'ok', 'score': 1, 'reasons': [], 'metrics': {}}, 'written')
assert main.sidecar_ref(v, {'orig': 'en'})[1] == 'ok'
seen = []
engines.sync = lambda eng, m, raw, t, ref=None: (seen.append(ref) or ([(1.2, 2.2)], 0, {'drift': {'ok': True, 'inliers': 40, 'windows': 40, 'qs': [0.1], 'p': 0.0, 'resid_med': 0.1, 'cuts': [], 'cut_times': []},
                                                         'chain_q': {'acts': 1, 'windows': 100, 'inliers': 95, 'near': 0.95, 'resid_med': 0.1, 'p': 0.0, 'cuts': []} if ref else None}))
engines._extract = lambda m, rel, dst: open(dst, 'wb').write(b'a')
items = [(v, main.decide(v, ctx))]; assert items[0][1]['todo'] == ['ru']
main.work(ctx, items, 'drift', None, 'new', mode='gate')
assert seen and seen[0] is not None and len(seen[0]) == 80, 'ru was aligned to the sidecar English subtitle'
assert os.path.exists(os.path.join(os.path.dirname(v), 'Show.S01E02.ru.srt')), 'trusted chain result is written, not held'
assert quality.assess({'drift': {'ok': True, 'inliers': 40, 'windows': 40, 'qs': [0], 'p': 0, 'resid_med': 0.1}}, None, False, True)['reasons_ru'][0].startswith('нет субтитров оригинала')
print('H2 ok')

# M7: a held candidate belongs to one version of the video and (while pending) one track
rel = 'TVshows/Show/Show.S01E02.mkv'
q = {'verdict': 'review', 'score': 0.5, 'reasons': [], 'metrics': {}}
iid = review.hold(state, rel, 'de', 'Show.S01E02', 1, good, q, [0.0], 60, v)
assert review.blocked(state, rel, 'de', v, 1) and not review.blocked(state, rel, 'de', v, 0)
open(v, 'ab').write(b'y' * 10); os.utime(v, (time.time() + 5, time.time() + 5))
assert not review.blocked(state, rel, 'de', v, 1), 'a replaced video is not blocked by the old candidate'
try: review.decide(state, root, iid, 'approve'); assert 0
except ValueError as e: assert 'replaced' in str(e)
print('M7 ok')

# M8 + grouping: the panel lists one card per existing file; loose files sit under their section
st = json.load(open(state + '/state.json')) if os.path.exists(state + '/state.json') else {}
g1 = os.path.join(root, 'Movies/Gone.mkv'); m1 = os.path.join(root, 'Movies/Loose.mkv'); os.makedirs(os.path.dirname(m1), exist_ok=True); open(m1, 'wb').write(b'x')
two = {'audio': [{'rel': 0, 'index': 1, 'lang': 'und', 'title': '', 'original': False}, {'rel': 1, 'index': 2, 'lang': 'und', 'title': '', 'original': False}], 'subs': [], 'duration': 9}
st['probe'] = {'%s|1|%d' % (m1, 100): two, '%s|1|%d' % (m1, 200): dict(two, audio=two['audio'] * 1 + [dict(two['audio'][0], rel=2)]), '%s|1|5' % g1: two}
json.dump(st, open(state + '/state.json', 'w'))
import views; s_ = views.build_state(root, state); paths = [f['path'] for g in s_['groups'] for k in ('need', 'queue', 'mine') for f in g[k]]
assert paths.count('Movies/Loose.mkv') == 1 and 'Movies/Gone.mkv' not in paths, paths
g = [g for g in s_['groups'] if any(f['path'] == 'Movies/Loose.mkv' for f in g['need'])][0]; assert g['path'] == 'Movies' and g['loose'] and len(g['need'][0]['tracks']) == 3
pr_ = views.build_prio(root, state); assert [x['path'] for x in pr_].count('Movies') == 1 and any(f['path'] == 'Movies/Loose.mkv' for f in pr_[0]['files'] if pr_[0]['path'] == 'Movies')
print('M8 ok')

# L1 / L3 / cross-site POST
threading.Thread(target=web.serve, args=(18761, root, state), daemon=True).start(); time.sleep(0.5)
pw = open(state + '/web_password').read().strip()
def call(path, body=None, ctype='application/json', auth=True, origin=None):
    rq = urllib.request.Request('http://127.0.0.1:18761' + path, data=body)
    if auth: rq.add_header('Authorization', 'Basic ' + base64.b64encode(('u:' + pw).encode()).decode())
    if ctype: rq.add_header('Content-Type', ctype)
    if origin: rq.add_header('Origin', origin)
    try: return urllib.request.urlopen(rq).status
    except urllib.error.HTTPError as e: return e.code
assert call('/api/override', b'[1]') == 400 and call('/api/override', b'"x"') == 400
assert call('/api/override', b'{"path":"Movies/Loose.mkv","lang":"en","track":null}', ctype='text/plain') == 403
assert call('/api/override', b'{"path":"Movies/Loose.mkv","lang":"en","track":null}', origin='http://evil.example') == 403
assert call('/api/override', b'{"path":"Movies/Loose.mkv","lang":"en","track":null}', origin='http://127.0.0.1:18761') == 200
open(state + '/web_password', 'w').write('')
assert call('/api/state', auth=False, ctype=None) == 401, 'an empty password file must not open the panel'
print('L1 L3 ok')

# M4/M5: the interrupt check walks the library at most once per poll and ignores files still being written
calls = [0]; real = main.snapshot
main.snapshot = lambda: (calls.__setitem__(0, calls[0] + 1) or real())
stop = main.new_files_check({}); assert not stop() and calls[0] == 0, 'no walk right after the start'
nf_ = os.path.join(root, 'TVshows/Show/New.S01E03.mkv'); open(nf_, 'wb').write(b'x')
main.POLL_SECONDS = 0; assert not stop(), 'a file written just now does not interrupt'
os.utime(nf_, (time.time() - 3600, time.time() - 3600)); assert stop()
print('M4 M5 ok')
print('fixes13 ok')
