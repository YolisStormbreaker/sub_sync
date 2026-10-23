"""OpenSubtitles.com REST client. Key-only mode first (separate, larger quota), login+token as fallback.
Never logs the key, password or token."""
import json, time, datetime, urllib.request, urllib.error, urllib.parse
from media import tokens

UA = 'subsync-wrapper v0.1'
BASE = 'https://api.opensubtitles.com/api/v1'


def load_creds(path):
    c = {}
    for ln in open(path, encoding='utf-8-sig'):
        if '=' in ln:
            k, v = ln.split('=', 1); c[k.strip().lower()] = v.strip().strip('"\'')
    for need in ('api_key', 'login', 'pass'):
        if not c.get(need):
            raise SystemExit('credentials file lacks ' + need)
    return c


def next_reset(now=None):
    """Quota renews at 00:00 UTC (observed in the API's reset_time_utc)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0).timestamp()


class QuotaExhausted(Exception):
    pass


class OS:
    def __init__(self, creds, state):
        self.c, self.st, self.base, self.last = creds, state, BASE, 0.0

    def _call(self, method, path, body=None, token=None, gap=0.25):
        time.sleep(max(0.0, self.last + gap - time.time()))
        h = {'Api-Key': self.c['api_key'], 'User-Agent': UA, 'Accept': 'application/json', 'Content-Type': 'application/json'}
        if token:
            h['Authorization'] = 'Bearer ' + token
        for attempt in range(4):
            req = urllib.request.Request(self.base + path, headers=h, method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                r = urllib.request.urlopen(req, timeout=60); code, raw = r.status, r.read()
            except urllib.error.HTTPError as e:
                code, raw = e.code, e.read()
            except (urllib.error.URLError, TimeoutError) as e:
                code, raw = 0, str(e).encode()
            self.last = time.time()
            if code in (0, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 1.5); continue
            try: j = json.loads(raw)
            except ValueError: j = {'raw': raw[:200].decode('utf-8', 'replace')}
            return code, j
        return code, j

    def token(self):
        t = self.st.setdefault('token', {})
        if t.get('value') and t.get('exp', 0) > time.time() + 300:
            return t['value']
        code, j = self._call('POST', '/login', {'username': self.c['login'], 'password': self.c['pass']}, gap=1.1)
        if code != 200 or not j.get('token'):
            raise RuntimeError('login failed: HTTP %s' % code)
        self.st['token'] = {'value': j['token'], 'exp': time.time() + 23 * 3600}
        return j['token']

    @staticmethod
    def build_query(lang, video_hash=None, guess=None, hint=None):
        """Query parameters of one search; lang None = every language. hint = {'title': ..., 'tmdb': ...} typed in by a person:
        a TMDb id of the series (or film) replaces the title, which is what tells the 1963 and 2005 'Doctor Who' apart."""
        q = {'ai_translated': 'exclude', 'machine_translated': 'exclude', 'foreign_parts_only': 'exclude'}
        hint = hint or {}
        if lang:
            q['languages'] = lang
        if video_hash:
            q['moviehash'] = video_hash
        if guess:
            title = (hint.get('title') or guess['title']).lower()
            if guess['type'] == 'episode':
                q.update(type='episode', season_number=guess['season'], episode_number=guess['episode'])
                if hint.get('tmdb'):
                    q['parent_tmdb_id'] = int(hint['tmdb'])
                else:
                    q['query'] = title
            else:
                q.update(type='movie', year=guess['year'])
                if hint.get('tmdb'):
                    q['tmdb_id'] = int(hint['tmdb'])
                else:
                    q['query'] = title
        elif video_hash:
            q['moviehash_match'] = 'only'
        else:
            return None
        return q

    def _find(self, q):
        code, j = self._call('GET', '/subtitles?' + urllib.parse.urlencode(sorted(q.items())))
        if code != 200:
            raise RuntimeError('search failed: HTTP %s' % code)
        return [x['attributes'] for x in j.get('data', []) if x['attributes'].get('files')]

    def search(self, lang, video_hash=None, guess=None, hint=None):
        q = self.build_query(lang, video_hash, guess, hint)
        return self._find(q) if q else []

    def languages_found(self, video_hash=None, guess=None, hint=None):
        """{language: count} of the subtitles of the same query without the language filter (first page): tells 'nothing exists'
        from 'exists, but not in this language'. Searching does not use up the download quota."""
        q = self.build_query(None, video_hash, guess, hint)
        out = {}
        for a in (self._find(q) if q else []):
            out[a.get('language') or '?'] = out.get(a.get('language') or '?', 0) + 1
        return out

    @staticmethod
    def pick(cands, video_name, fps=None):
        """Best candidate: exact hash match, then release-name similarity, matching fps, not hearing-impaired."""
        vt = tokens(video_name)
        def score(a):
            rt = tokens(a.get('release') or '')
            sim = len(vt & rt) / max(1, len(vt | rt))
            return (1000 if a.get('moviehash_match') else 0) + 100 * sim + (10 if fps and a.get('fps') and abs(a['fps'] - fps) < 0.01 else 0) \
                   - (5 if a.get('hearing_impaired') else 0) + min(a.get('download_count') or 0, 1e6) / 1e6
        return max(cands, key=score) if cands else None

    def download(self, file_id):
        """Returns (bytes, info). Tries key-only unless known exhausted, then login. Raises QuotaExhausted."""
        q = self.st.setdefault('quota', {})
        for mode in ('keyonly', 'login'):
            m = q.setdefault(mode, {})
            if m.get('blocked_until', 0) > time.time():
                continue
            code, j = self._call('POST', '/download', {'file_id': file_id, 'sub_format': 'srt'},
                                 token=self.token() if mode == 'login' else None)
            if code == 200 and j.get('link'):
                m['remaining'] = j.get('remaining')
                if j.get('remaining') == 0:
                    m['blocked_until'] = next_reset()
                for attempt in range(3):  # the quota is already spent once /download answered: try hard to get the file
                    try:
                        data = urllib.request.urlopen(urllib.request.Request(j['link'], headers={'User-Agent': UA}), timeout=60).read(); break
                    except OSError:
                        if attempt == 2:
                            raise
                        time.sleep(5 * (attempt + 1))
                return data, {'mode': mode, 'remaining': j.get('remaining'), 'name': j.get('file_name')}
            if code in (401, 406, 403):  # no anonymous downloads / quota used up
                m['blocked_until'] = next_reset() if code == 406 else time.time() + 3600
                continue
            raise RuntimeError('download failed: HTTP %s %s' % (code, str(j)[:120]))
        raise QuotaExhausted()
