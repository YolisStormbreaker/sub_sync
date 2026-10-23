"""Original language of a title from TMDb (used only when the audio tags do not say). Bearer read-access token preferred."""
import json, re, time, urllib.error, urllib.parse, urllib.request
import media

BASE = 'https://api.themoviedb.org/3'
FIX = {'cn': 'zh'}  # TMDb uses 'cn' for Cantonese; 'xx' means no language


def norm(s):
    return re.sub(r'[\W_]+', ' ', (s or '').lower()).strip()


class TMDb:
    def __init__(self, creds_path, state):
        self.st, self.c, self.last = state.setdefault('tmdb', {}), {}, 0.0
        if creds_path:
            try:
                for ln in open(creds_path, encoding='utf-8-sig'):
                    if '=' in ln:
                        k, v = ln.split('=', 1); self.c[k.strip().lower()] = v.strip().strip('"\'')
            except OSError:
                pass
        self.online = bool(self.c.get('read_token') or self.c.get('api_key'))

    def _get(self, path, q):
        time.sleep(max(0.0, self.last + 0.1 - time.time()))
        h = {'Accept': 'application/json', 'User-Agent': 'subsync-wrapper v0.1'}
        if self.c.get('read_token'):
            h['Authorization'] = 'Bearer ' + self.c['read_token']
        else:
            q = dict(q, api_key=self.c['api_key'])
        for attempt in range(3):
            try:
                r = urllib.request.urlopen(urllib.request.Request(BASE + path + '?' + urllib.parse.urlencode(sorted(q.items())), headers=h), timeout=30)
                self.last = time.time(); return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 ** attempt * 2); continue
                raise RuntimeError('TMDb HTTP %d' % e.code)
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt * 2)
        raise RuntimeError('TMDb unreachable')

    def original_language(self, guess):
        """Two-letter code, or None when there is no confident match. Cached; misses are retried after 7 days."""
        if not guess:
            return None
        key = '%s|%s|%s' % (guess['type'], norm(guess['title']), guess.get('year', ''))
        hit = self.st.get(key)
        if hit and (hit.get('lang') or time.time() - hit['t'] < media.RETRY_DAYS * 86400):
            return hit.get('lang')
        if not self.online:
            return None
        kind = 'tv' if guess['type'] == 'episode' else 'movie'
        q = {'query': guess['title'], 'language': 'ru-RU', 'include_adult': 'false'}
        if kind == 'movie' and guess.get('year'):
            q['year'] = guess['year']
        lang = None
        for r in self._get('/search/' + kind, q).get('results', []):
            if norm(guess['title']) in (norm(r.get('name') or r.get('title')), norm(r.get('original_name') or r.get('original_title'))):
                lang = FIX.get(r.get('original_language'), r.get('original_language')); lang = None if lang == 'xx' else lang
                break
        self.st[key] = {'lang': lang, 't': time.time()}
        return lang
