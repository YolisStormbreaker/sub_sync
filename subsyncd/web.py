"""Admin panel: HTTP Basic auth (password in <state>/web_password), pages built in the browser from JSON.
  /          original language and audio track of each file or folder (writes overrides.json)
  /review    subtitles the quality gate held back: listen against the original audio, approve or reject
  /missing   searches that found nothing: the reason, and a title / TMDb id hint that fixes the search (writes searchhints.json)
  /prio      priorities of sections, folders and files for the scan, download and sync stages (writes priorities.json)
  /quality   what the gate decided for every file
The page shell is rendered here; layout and styles are static files in static/ (design: static/subsync.css from design/),
the data comes from views.py. Fonts: <state>/fonts/GolosText.ttf if present, else the system fonts."""
import hmac, json, os, re, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import media, missing, prio, quality, review, views
from overrides import Overrides

CLIP_LOCK = threading.Lock()  # one ffmpeg at a time: the NAS has other work to do
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
TYPES = {'.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml'}
PAGES = {'/': ('lang', 'Язык и дорожка'), '/review': ('review', 'Проверка'), '/missing': ('missing', 'Не найдено'),
         '/prio': ('prio', 'Приоритеты'), '/quality': ('quality', 'Журнал качества')}
NAV = ['/', '/review', '/missing', '/prio', '/quality']
ICON = ('<svg viewBox="0 0 512 512" aria-hidden="true"><rect x="16" y="16" width="480" height="480" rx="104" fill="#161D19" stroke="#7DCE9B" '
        'stroke-width="16"/><g fill="#F2F5F0">' + ''.join('<rect x="%d" y="%d" width="10" height="%d" rx="5"/>' % (91 + 20 * i, 200 - h // 2, h) for i, h in
        enumerate((36, 64, 48, 92, 120, 80, 136, 104, 150, 104, 136, 80, 120, 92, 48, 64, 36))) +
        '</g><rect x="136" y="318" width="240" height="24" rx="12" fill="#7DCE9B"/><rect x="188" y="370" width="136" height="24" rx="12" fill="#7DCE9B"/></svg>')


def page_html(path, version):
    """Shell of one page: rail with brand, navigation (badges filled by app.js) and service status, an empty main column."""
    key, title = PAGES[path]
    nav = ''.join('<a href="%s"%s data-badge="%s"><span>%s</span></a>' % (u, ' aria-current="page"' if u == path else '', PAGES[u][0], PAGES[u][1]) for u in NAV)
    meta = json.dumps({'page': key, 'langs': [[c, n] for c, n in media.LANG_NAMES_RU.items()], 'retryDays': media.RETRY_DAYS}, ensure_ascii=False)
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Subsync — %s</title><link rel="icon" href="/static/icon.svg">'
            '<link rel="stylesheet" href="/static/subsync.css?v=%s"><link rel="stylesheet" href="/static/app.css?v=%s"></head>'
            '<body><div class="ss" id="ss"><div class="shell"><aside class="rail">'
            '<div class="brand">%s<b>Subsync</b><span>Субтитры для домашней библиотеки</span></div>'
            '<div class="status-mini" id="status-mini"></div><nav class="nav" aria-label="Разделы">%s</nav>'
            '<div class="status" id="status"></div></aside><main class="main"><div class="page" id="page"></div></main></div></div>'
            '<script>window.SS=%s</script><script src="/static/app.js?v=%s"></script><script src="/static/%s.js?v=%s"></script></body></html>'
            % (title, version, version, ICON, nav, meta, version, key, version))


def static_version():
    """Changes whenever a static file changes, so browsers do not keep an old script after an update."""
    try:
        return '%x' % int(max(os.path.getmtime(os.path.join(STATIC, f)) for f in os.listdir(STATIC)))
    except (OSError, ValueError):
        return '0'


def send_file(h, path, ctype, cache=False):
    """Whole file or one byte range (browsers seek audio with Range)."""
    size = os.path.getsize(path); a, b, code = 0, size - 1, 200
    m = re.match(r'bytes=(\d*)-(\d*)$', h.headers.get('Range', ''))
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else size - 1
        else:
            a = max(0, size - int(m.group(2)))
        if a > b or a >= size:
            h.send_response(416); h.send_header('Content-Range', 'bytes */%d' % size); h.end_headers(); return
        b = min(b, size - 1); code = 206
    h.send_response(code); h.send_header('Content-Type', ctype); h.send_header('Accept-Ranges', 'bytes')
    h.send_header('Content-Length', str(b - a + 1)); h.send_header('Cache-Control', 'max-age=31536000, immutable' if cache else 'no-store')
    if code == 206:
        h.send_header('Content-Range', 'bytes %d-%d/%d' % (a, b, size))
    h.end_headers()
    with open(path, 'rb') as f:
        f.seek(a); left = b - a + 1
        while left > 0:
            chunk = f.read(min(65536, left))
            if not chunk:
                break
            h.wfile.write(chunk); left -= len(chunk)


def serve(port, root, state_dir):
    pw_path = os.path.join(state_dir, 'web_password')
    if not os.path.exists(pw_path) or not open(pw_path).read().strip():
        tmp = pw_path + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, (secrets.token_urlsafe(9) + '\n').encode()); os.fsync(fd); os.close(fd); os.replace(tmp, pw_path)
    ov = Overrides(os.path.join(state_dir, 'overrides.json'))
    pri = prio.Priorities(os.path.join(state_dir, 'priorities.json'))
    hints = missing.Hints(os.path.join(state_dir, 'searchhints.json'))

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def authed(self):
            import base64
            h = self.headers.get('Authorization', '')
            try:
                given = base64.b64decode(h.split(' ', 1)[1]).decode().split(':', 1)[1] if h.startswith('Basic ') else ''
            except Exception:
                given = ''
            try:
                want = open(pw_path).read().strip()
            except OSError:
                want = ''
            if want and hmac.compare_digest(given.encode(), want.encode()):  # an emptied password file locks the panel, never opens it
                return True
            self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="subsync"'); self.end_headers()
            return False

        def reply(self, code, body, ctype='text/plain; charset=utf-8'):
            b = body.encode(); self.send_response(code)
            self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if not self.authed():
                return
            u = urlsplit(self.path); q = parse_qs(u.query); p = u.path
            js = lambda o: self.reply(200, json.dumps(o, ensure_ascii=False), 'application/json')
            try:
                if p in PAGES:
                    self.reply(200, page_html(p, static_version()), 'text/html; charset=utf-8')
                elif p.startswith('/static/'):
                    name = p[len('/static/'):]
                    if name == 'golos.ttf':
                        f = os.path.join(state_dir, 'fonts', 'GolosText.ttf')
                        if os.path.isfile(f):
                            send_file(self, f, 'font/ttf', cache=True)
                        else:  # not downloaded yet: the pages fall back to the system fonts
                            self.reply(404, 'no font')
                    elif re.fullmatch(r'[a-z0-9_-]+\.(css|js|svg)', name) and os.path.isfile(os.path.join(STATIC, name)):
                        send_file(self, os.path.join(STATIC, name), TYPES[os.path.splitext(name)[1]], cache=True)
                    else:
                        self.reply(404, 'not found')
                elif p == '/api/status':
                    js(views.build_status(root, state_dir))
                elif p == '/api/state':
                    js(views.build_state(root, state_dir))
                elif p == '/api/prio':
                    js(views.build_prio(root, state_dir))
                elif p == '/api/missing':
                    js(views.build_missing(root, state_dir))
                elif p == '/api/quality':
                    js(quality.latest(state_dir, 2000))
                elif p == '/api/review':
                    js(views.build_review(state_dir))
                elif re.fullmatch(r'/api/review/[0-9a-f]{12}/cues', p):
                    js(review.cues(state_dir, p.split('/')[3], float(q.get('t', ['0'])[0]), float(q.get('len', ['40'])[0])))
                elif re.fullmatch(r'/api/review/[0-9a-f]{12}/clip', p):
                    with CLIP_LOCK:
                        f = review.clip(state_dir, root, p.split('/')[3], float(q.get('t', ['0'])[0]), float(q.get('len', ['40'])[0]))
                    send_file(self, f, 'audio/mpeg')
                elif p == '/api/clip':
                    with CLIP_LOCK:
                        f = review.file_clip(state_dir, root, q.get('path', [''])[0], q.get('track', ['0'])[0], float(q.get('t', ['0'])[0]),
                                             float(q.get('len', ['20'])[0]), media.INCLUDE, media.EXCLUDE_NAMES)
                    send_file(self, f, 'audio/mpeg')
                else:
                    self.reply(404, 'not found')
            except (ValueError, OSError) as e:
                self.reply(400, str(e))
            except Exception as e:  # ffmpeg failure and the like: the page shows the text
                self.reply(500, str(e))

        def do_POST(self):
            if not self.authed():
                return
            origin = self.headers.get('Origin')
            if 'application/json' not in (self.headers.get('Content-Type') or '') or (origin and urlsplit(origin).netloc != self.headers.get('Host')):
                self.reply(403, 'forbidden'); return
            try:
                j = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                if not isinstance(j, dict):
                    raise ValueError('a JSON object is expected')
                if self.path == '/api/override':
                    ov.set(str(j['path']), j.get('lang'), j.get('track'), j['tlangs'] if 'tlangs' in j else Overrides.KEEP)
                    self.reply(200, 'ok')
                elif self.path == '/api/hint':
                    if j.get('remove'):
                        hints.remove(str(j['path']))
                    else:
                        t = j.get('tmdb')
                        hints.set(str(j['path']), j.get('title'), None if t in (None, '') else int(t))
                    self.reply(200, 'ok')
                elif self.path == '/api/prio':
                    pri.set(str(j['path']), {s: j[s] for s in prio.STAGES if s in j})
                    self.reply(200, 'ok')
                elif re.fullmatch(r'/api/review/[0-9a-f]{12}', self.path):
                    self.reply(200, review.decide(state_dir, root, self.path.rsplit('/', 1)[1], str(j['action'])))
                else:
                    self.reply(404, 'not found')
            except (ValueError, KeyError, TypeError, OSError) as e:
                self.reply(400, str(e))
            except Exception as e:  # never leave the browser without an answer
                self.reply(500, str(e))

    srv = ThreadingHTTPServer(('0.0.0.0', port), H); srv.daemon_threads = True
    srv.serve_forever()
