"""Reasons for empty searches, search hints, merged overrides. Run: python3 test_missing.py"""
import os, sys, tempfile, json, time
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import main, media, missing, osapi
from overrides import Overrides

# 1. the query without a hint is exactly what the service always sent
g = {'type': 'episode', 'title': 'Doctor Who', 'season': 1, 'episode': 3}
q = osapi.OS.build_query('en', 'abc', g)
assert q == {'languages': 'en', 'ai_translated': 'exclude', 'machine_translated': 'exclude', 'foreign_parts_only': 'exclude', 'moviehash': 'abc',
             'query': 'doctor who', 'type': 'episode', 'season_number': 1, 'episode_number': 3}, q
q = osapi.OS.build_query('en', None, g, {'tmdb': 57243})
assert q['parent_tmdb_id'] == 57243 and 'query' not in q and q['season_number'] == 1, q
assert osapi.OS.build_query('en', None, g, {'title': 'Doctor Who 2005'})['query'] == 'doctor who 2005'
m = {'type': 'movie', 'title': 'Film', 'year': 2020}
assert osapi.OS.build_query('ru', None, m, {'tmdb': 5})['tmdb_id'] == 5
assert osapi.OS.build_query(None, None, g).get('languages') is None
assert osapi.OS.build_query('en', None, None) is None and osapi.OS.build_query('en', 'h', None)['moviehash_match'] == 'only'

# 2. reasons
c = lambda lang, guess, others: missing.classify(lang, guess, others)[0]
assert c('en', None, {}) == 'no_guess'
assert c('en', dict(g, episode=0), {}) == 'special'
assert c('ru', g, {'en': 2}) == 'other_langs' and 'en: 2' in missing.classify('ru', g, {'en': 2})[1]
assert c('ru', g, {}) == 'unknown' and 'Doctor Who' in missing.classify('ru', g, {})[1]
assert c('ru', g, {'ru': 1}) == 'filtered'

# 3. get_raw: record, wait, a hint lifts the wait, a hit clears the reason
v = os.path.join(root, 'TVshows/Doctor Who/Doctor.Who_S01/doctor.who.s01e03.HDRip.avi'); os.makedirs(os.path.dirname(v)); open(v, 'wb').write(b'x' * 200000)
calls = []
class Fake:
    hit = False
    def search(s, lang, h, g, hint=None):
        calls.append(('search', lang, hint)); return [{'files': [{'file_id': 7}], 'release': 'doctor.who.s01e03', 'fps': 25.0, 'download_count': 1}] if s.hit else []
    def languages_found(s, h, g, hint=None): calls.append(('census',)); return {'ru': 3}
    def pick(s, cands, stem): return cands[0] if cands else None
    def download(s, fid): return b'1\n00:00:01,000 --> 00:00:02,000\nHi\n\n', {'mode': 'keyonly', 'remaining': 9}
ctx = main.Ctx(network=False); ctx.osc = Fake()
r = main.get_raw(v, 'en', ctx)
assert r[0] is None and r[1].startswith('not found on OpenSubtitles: episode exists in ru: 3 but not in en'), r
key = '%s|%d|en' % (v, os.path.getsize(v)); w = missing.load(state)[key]
assert w['code'] == 'other_langs' and w['others'] == {'ru': 3} and 'сезон 1, серия 3' in w['query'], w
n = len(calls); r = main.get_raw(v, 'en', ctx); assert r[1].startswith('skipped') and len(calls) == n   # still waiting 7 days
ctx.hints.set('TVshows/Doctor Who', None, 57243)                                                       # a hint: search again now
Fake.hit = True; r = main.get_raw(v, 'en', ctx)
assert r[0] is not None and calls[-1][2]['tmdb'] == 57243, (r, calls[-1])
assert key not in missing.load(state), 'a found subtitle must clear its reason'
try: ctx.hints.set('Others/x', 'x', None); assert 0
except ValueError: pass
try: ctx.hints.set('TVshows/x', 'x', 'abc'); assert 0
except ValueError: pass

# 4. a track chosen for a file keeps the language chosen for its folder
o = Overrides(os.path.join(state, 'o.json'))
o.set('TVshows/Doctor Who', 'en', None); o.set('TVshows/Doctor Who/S01/a.mkv', None, 1)
assert o.lookup('TVshows/Doctor Who/S01/a.mkv') == {'lang': 'en', 'track': 1}, o.lookup('TVshows/Doctor Who/S01/a.mkv')
assert o.lookup('TVshows/Doctor Who/S01/b.mkv') == {'lang': 'en', 'track': None}
assert o.source('TVshows/Doctor Who/S01/a.mkv', 'lang') == 'TVshows/Doctor Who' and o.source('TVshows/Doctor Who/S01/a.mkv', 'track') == 'TVshows/Doctor Who/S01/a.mkv'
o.set('TVshows/Doctor Who/S01/a.mkv', None, None); assert o.lookup('TVshows/Doctor Who/S01/a.mkv')['track'] is None
assert o.lookup('Movies/x.mkv') is None
print('missing ok')
import media as _m
assert _m.guess('/v/TVshows/Doctor Who/doctor.who.s11e09HDRip.avi') == {'type': 'episode', 'title': 'doctor who', 'season': 11, 'episode': 9}
assert _m.guess('/v/TVshows/S/Show.S01E02.mkv')['episode'] == 2 and _m.guess('/v/TVshows/S/Show.S01E0001.mkv') is None
print('guess ok')

# ---- languages given to tracks of one file
import resolve
o = Overrides(os.path.join(state, 'o2.json')); F = 'Movies/Many/Many.mkv'
o.set(F, None, None, {'1': 'ru', '2': 'ru', '3': 'ru'}); assert o.lookup(F) == {'lang': None, 'track': None, 'tlangs': {'1': 'ru', '2': 'ru', '3': 'ru'}}
o.set(F, 'en', None); assert o.lookup(F)['tlangs'] == {'1': 'ru', '2': 'ru', '3': 'ru'} and o.lookup(F)['lang'] == 'en', 'KEEP'
o.set(F, 'en', 2, {}); assert 'tlangs' not in o.lookup(F) and o.lookup(F) == {'lang': 'en', 'track': 2}
o.set(F, None, None, {'0': ''}); assert o.lookup(F) is None and o.all() == {}, o.all()
for bad in ({'x': 'en'}, {'99': 'en'}, {'1': 'xx'}, 'en'):
    try: o.set(F, None, None, bad); assert 0, bad
    except ValueError: pass
au = lambda *ls: {'audio': [{'rel': i, 'index': i + 1, 'lang': l, 'title': '', 'original': False} for i, l in enumerate(ls)], 'subs': []}
pr6 = au(*['und'] * 6)
assert media.original_audio(pr6['audio'])[3] is False
o.set(F, None, None, {'1': 'ru', '2': 'ru', '3': 'ru', '4': 'ru', '5': 'ru'})
p2 = resolve.relabel(F, pr6, o); assert [a['lang'] for a in p2['audio']] == ['und'] + ['ru'] * 5 and pr6['audio'][1]['lang'] == 'und', 'input untouched'
lang, rel, why, conf = resolve.resolve(F, '/x/Many.mkv', p2, o, None); assert (lang, rel, conf) == (None, 0, True), (lang, rel, why, conf)   # one untagged track next to dubs
o.set(F, None, None, {'0': 'en'}); lang, rel, why, conf = resolve.resolve(F, '/x/Many.mkv', resolve.relabel(F, pr6, o), o, None); assert (lang, rel, conf) == ('en', 0, True), (lang, rel, why)
assert resolve.relabel('Movies/Other.mkv', pr6, o) is pr6
# a comparison made before the tracks were labelled no longer applies to the changed candidates
v = os.path.join(root, 'Movies/Many/Many.mkv'); os.makedirs(os.path.dirname(v)); open(v, 'wb').write(b'x' * 10)
tr = {resolve.track_key(v): {'lang': 'en', 'rel': 1, 'margin': 0.0, 'sure': False, 'metrics': {'0': {}, '1': {}, '2': {}}}}
assert resolve._entry(tr, v, 'en', [0, 1, 2]) is not None and resolve._entry(tr, v, 'en', [0, 1]) is None and resolve._entry(tr, v, 'en') is not None
print('tlangs ok')
