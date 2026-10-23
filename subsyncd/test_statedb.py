"""statedb: import of state.json, saves that write only what changed, two writers, partial read-only loads, speed.
Run: python3 test_statedb.py"""
import json, os, sqlite3, sys, tempfile, time
sys.path.insert(0, '.')
import statedb

d = tempfile.mkdtemp()
old = {'probe': {'/v/a.mkv|10|1': {'audio': [{'rel': 0, 'lang': 'eng'}], 'duration': 9.5}}, 'seen': {}, 'quota': {'keyonly': {'remaining': 56}},
       'last_night': '2026-10-22', 'hints_done': 0, 'night': None, 'token': {'value': 'x', 'exp': 1}}
json.dump(old, open(d + '/state.json', 'w'))

# import: same dict back, empty tables and None kept, state.json renamed
st = statedb.load(d)
assert st == old, st
assert not os.path.exists(d + '/state.json') and os.path.exists(d + '/state.json.pre-sqlite')

def rows():
    db = sqlite3.connect(d + '/' + statedb.NAME); n = db.execute('SELECT count(*) FROM kv').fetchone()[0]; db.close(); return n

# a save writes only the changed rows; an in-place change of a nested value counts
assert statedb.save(d, st) == 0
st['probe']['/v/a.mkv|10|1']['duration'] = 10.0
st['probe']['/v/b.mkv|5|2'] = {'audio': [], 'duration': 1}
st['seen']['/v/a.mkv'] = 10
assert statedb.save(d, st) == 3
assert statedb.load(d)['probe']['/v/a.mkv|10|1']['duration'] == 10.0

# deletions: an entry, a whole table, a scalar
del st['probe']['/v/b.mkv|5|2']; del st['token']; st.pop('hints_done')
assert statedb.save(d, st) == 1 + 3 + 1
assert statedb.load(d) == st and rows() == len(statedb._flat(st))

# a table replaced by a scalar and back
st['night'] = {'date': '2026-10-23', 'written': 3}; statedb.save(d, st); assert statedb.load(d)['night'] == {'date': '2026-10-23', 'written': 3}
st['night'] = None; statedb.save(d, st); assert statedb.load(d)['night'] is None and rows() == len(statedb._flat(st))

# two writers that loaded the same state keep each other's changes (state.json used to be overwritten whole)
a = statedb.load(d); b = statedb.load(d)
a['probe']['/v/c.mkv|1|1'] = {'duration': 3}; statedb.save(d, a)
b['seen']['/v/c.mkv'] = 1; statedb.save(d, b)
both = statedb.load(d); assert '/v/c.mkv|1|1' in both['probe'] and both['seen']['/v/c.mkv'] == 1

# a plain dict replaces everything
statedb.save(d, {'quota': {}}); assert statedb.load(d) == {'quota': {}}

# partial load: only the named keys, and it cannot be saved
statedb.save(d, {'quota': {'keyonly': {'remaining': 5}}, 'daily': {'new': 1}, 'probe': {'x': 1}, 'night': None})
p = statedb.load(d, ('quota', 'night'))
assert p == {'quota': {'keyonly': {'remaining': 5}}, 'night': None}, p
try:
    statedb.save(d, p); assert 0
except ValueError:
    pass

# a corrupt state.json is not imported and not moved
e = tempfile.mkdtemp(); open(e + '/state.json', 'w').write('{"probe": ')
assert statedb.load(e) == {} and os.path.exists(e + '/state.json')

# speed at library scale: 5000 files, ~2 MB of state
big = {'probe': {'/volume1/video/TVshows/Show %d/Season 1/Show.S01E%02d.mkv|%d|%d' % (i // 20, i % 20, 10 ** 9 + i, 1.7e9 + i):
                 {'audio': [{'rel': 0, 'index': 1, 'lang': 'eng', 'title': 'English 5.1', 'original': True}, {'rel': 1, 'index': 2, 'lang': 'rus', 'title': 'Dub', 'original': False}],
                  'subs': [{'lang': 'eng', 'codec': 'subrip'}], 'duration': 2600.5} for i in range(5000)},
       'seen': {'/volume1/video/f%d.mkv' % i: 10 ** 9 + i for i in range(5000)}}
f = tempfile.mkdtemp(); json.dump(big, open(f + '/state.json', 'w')); size = os.path.getsize(f + '/state.json')
statedb.load(f)  # the first load imports state.json
t = time.time(); s = statedb.load(f); t_load = time.time() - t
s['seen']['/volume1/video/new.mkv'] = 1
t = time.time(); n = statedb.save(f, s); t_save = time.time() - t
t = time.time(); json.loads(open(f + '/state.json.pre-sqlite').read()); t_json = time.time() - t
print('state %.1f MB: load %.2f s (json.load %.2f s), save of one change %.3f s, rows written %d' % (size / 1e6, t_load, t_json, t_save, n))
assert t_load < 10 * t_json + 0.2, 'load should stay close to parsing the old file'
assert n == 1
print('statedb ok')
