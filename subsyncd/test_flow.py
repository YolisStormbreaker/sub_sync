import os, sys, tempfile, json
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import main, media, engines, osapi
v = os.path.join(root, 'TVshows/Show/Show.S01E02.720p.mkv'); os.makedirs(os.path.dirname(v)); open(v, 'wb').write(b'x' * 200000)
o = os.path.join(root, 'Others/x/Show.S01E02.mkv'); os.makedirs(os.path.dirname(o)); open(o, 'wb').write(b'x')
media.probe = lambda p: {'audio': [{'index': 1, 'lang': 'ru', 'title': 'Dub', 'original': False, 'rel': 0}, {'index': 2, 'lang': 'en', 'title': '', 'original': False, 'rel': 1}], 'subs': [], 'duration': 1}
raw = '﻿1\r\n00:00:01,000 --> 00:00:02,000\r\n<i>Он сказал</i>\r\n\r\n2\r\n00:00:10,000 --> 00:00:12,000 X1:5\r\nОна.\r\n\r\n'.encode()
class FakeOS:
    def __init__(s, *a): pass
    def search(s, lang, h, g, hint=None): print('   search', lang, g); return [{'files': [{'file_id': 7}], 'release': 'Show.S01E02.720p', 'fps': 25.0, 'download_count': 5}]
    pick = staticmethod(osapi.OS.pick)
    def download(s, fid): return raw, {'mode': 'keyonly', 'remaining': 99}
main.osapi.OS = FakeOS; main.osapi.load_creds = lambda p: {}
engines._extract = lambda m, rel, dst: open(dst, 'wb').write(b'a')
refs = []
def fake_sync(eng, m, rel, t, ref=None):
    refs.append(ref)
    cq = {'acts': 5, 'windows': 100, 'inliers': 95, 'near': 0.9, 'resid_med': 0.2, 'p': 0.0, 'cuts': [1]} if ref is not None else None
    return [(1.5, 2.5), (10.5, 12.5)], 1, {'chain': 'chain test', 'chain_q': cq, 'drift': {'ok': True, 'inliers': 40, 'windows': 40, 'qs': [0.1], 'p': 0.0, 'resid_med': 0.1, 'cuts': [], 'cut_times': []}}
engines.sync = fake_sync
a = type('A', (), dict(files=[v, o], dest=None, apply=True, engine='drift', dry=False, force=False, only=None))
main.cmd_plan(type('A', (), dict(files=[])))
main.cmd_fetch(a)
out = open(os.path.join(os.path.dirname(v), 'Show.S01E02.720p.ru.srt'), 'rb').read(); print(out)
main.cmd_plan(type('A', (), dict(files=[])))
import statedb; print(statedb.load(state).get('quota'), os.listdir(state))

print('refs seen by sync (en first, then ru):', refs); assert refs == [None, [1.5, 10.5]], refs
