import os, sys, json, tempfile, subprocess, threading, time, urllib.request, base64
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
env = dict(os.environ, SUBSYNC_ROOT=root, SUBSYNC_STATE=state)
def mk(rel):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'wb').write(b'x' * 200000); return p
A = lambda *t: [{'index': i + 1, 'lang': l, 'title': ti, 'original': False, 'rel': i, 'codec': 'ac3'} for i, (l, ti) in enumerate(t)]
files = {
 'TVshows/Doctor Who/S01/a.S01E01.mkv': A(('und', 'Sony'), ('und', 'Original')),
 'TVshows/Doctor Who/S01/a.S01E02.mkv': A(('und', 'Sony'), ('und', 'Original')),
 'TVshows/Friends/Friends.S01E01.mkv': A(('ru', 'MVO'), ('uk', '1+1'), ('en', '')),
 'Movies/Film.2020.mkv': A(('und', ''), ('und', '')),
 'Anime/Show/Show - S01E01.mkv': A(('ja', ''), ('ru', 'AniLibria')),
 'Others/x/Other.S01E01.mkv': A(('und', ''), ('und', '')),
}
probe = {}
for rel, au in files.items():
    p = mk(rel); probe['%s|%d|%d' % (p, os.path.getsize(p), os.path.getmtime(p))] = {'audio': au, 'subs': [], 'duration': 1}
json.dump({'probe': probe}, open(state + '/state.json', 'w'))
open(state + '/opensubtitles_creds', 'w').write('login=a\npass=b\napi_key=c\n')
def run(*args, **kw):
    r = subprocess.run([sys.executable, 'main.py', *args], env=env, capture_output=True, text=True, **kw); return r.stdout + r.stderr
print(run('plan'))
print(run('override', 'set', 'TVshows/Doctor Who', 'en')); print(run('override', 'set', 'Others/x', 'en'))
print(run('override', 'set', 'Movies/Film.2020.mkv', 'fr', '--track', '1'))
print(run('plan'))
print(run('fetch', root + '/Others/x/Other.S01E01.mkv', '--apply'))
print(run('run'))
# web
import web
t = threading.Thread(target=web.serve, args=(18742, root, state), daemon=True); t.start(); time.sleep(0.5)
req = lambda path, data=None: urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18742' + path, data=data, headers={'Authorization': 'Basic ' + base64.b64encode(b'u:' + open(state + '/web_password').read().strip().encode()).decode(), 'Content-Type': 'application/json'}))
print(json.dumps(json.load(req('/api/state')), ensure_ascii=False)[:600])
print(req('/api/override', json.dumps({'path': 'TVshows/Friends', 'lang': 'en', 'track': 2}).encode()).read())
try: req('/api/override', json.dumps({'path': 'Others/x', 'lang': 'en'}).encode())
except urllib.error.HTTPError as e: print('rejected', e.code, e.read())
try: urllib.request.urlopen('http://127.0.0.1:18742/')
except urllib.error.HTTPError as e: print('no auth ->', e.code)
print(len(req('/').read()), 'bytes page', oct(os.stat(state + '/web_password').st_mode)[-3:])
print(open(state + '/overrides.json').read())
