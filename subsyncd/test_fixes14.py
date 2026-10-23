"""Tests for the second round of fixes: state size and writes, detection retries, text check, one language table, hint retries.
Run: python3 test_fixes14.py"""
import json, os, sys, tempfile, time
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import main, media, missing, resolve, srtio, views, web

# languages: one table, every code named
assert set(media.LANG_NAMES_RU) == set(media.LANGS) and views.LN is media.LANG_NAMES_RU
assert 'LANG_CHOICES' not in dir(web) and not os.path.exists('pages_lang.py')

# state: pruning of gone / replaced files, compact and throttled writes
a = os.path.join(root, 'TVshows/A/a.mkv'); os.makedirs(os.path.dirname(a)); open(a, 'wb').write(b'x' * 10)
gone = os.path.join(root, 'TVshows/A/gone.mkv')
st = {'probe': {'%s|10|1' % a: {}, '%s|10|2' % a: {}, '%s|5|3' % a: {}, '%s|10|1' % gone: {}},
      'tracks': {'%s|10' % a: {}, '%s|9' % a: {}, '%s|10' % gone: {}},
      'notfound': {'%s|10|ru' % a: 1, '%s|10|ru' % gone: 1}, 'failed': {'%s|7|en' % a: 1}, 'seen': {a: 10, gone: 10}}
n = main.prune_state(st)
assert list(st['probe']) == ['%s|10|2' % a] and list(st['tracks']) == ['%s|10' % a] and list(st['notfound']) == ['%s|10|ru' % a]
assert st['failed'] == {} and list(st['seen']) == [a] and n == 8, (n, st)
import statedb
main.save_state(st); assert statedb.load(state) == st, 'a plain dict replaces the state'
st['x'] = 1; main.save_state(st, force=False); assert 'x' not in statedb.load(state), 'throttled'
main._saved[0] = 0; main.save_state(st, force=False); assert statedb.load(state)['x'] == 1
assert json.load(open(state + '/activity.json'))['beat'] >= int(time.time()) - 2

# detection: a failed comparison is tried again after RETRY_DAYS, a fresh one is kept
k = resolve.track_key(a)
tr = {k: {'lang': 'en', 'rel': None, 'sure': False, 'error': 'too few cues (12)', 'at': int(time.time())}}
assert resolve._entry(tr, a, 'en', [0, 1]) is not None
tr[k]['at'] = int(time.time()) - 8 * 86400; assert resolve._entry(tr, a, 'en', [0, 1]) is None

# text check: independent of the rewrite, catches a changed dialogue line that looks like a timing
raw = b'1\n00:00:01,000 --> 00:00:02,000\nShe said:\n00:01:02,000 --> 00:01:03,000\n\n2\n00:00:05,000 --> 00:00:06,000\nB\n'
assert len(srtio.parse_times(raw)) == 2
out = srtio.retime(raw, [(1.5, 2.5), (5.5, 6.5)]); assert b'00:01:02,000 --> 00:01:03,000' in out and srtio.text_unchanged(raw, out)
assert not srtio.text_unchanged(raw, out.replace(b'00:01:02,000', b'00:01:09,000'))
bom = b'\xef\xbb\xbf00:00:01,000 --> 00:00:02,000\nA\n'; assert srtio.retime(bom, [(3, 4)]).startswith(b'\xef\xbb\xbf00:00:03,000')

# hints: a hint newer than the empty search puts the file on the list searched within a poll
st = {'notfound': {'%s|10|ru' % a: time.time() - 100}}
assert main.hinted_files(st) == []
missing.Hints(state + '/searchhints.json').set('TVshows/A', None, 123)
assert main.hinted_files(st) == [a]
st['hints_done'] = time.time() + 5; assert main.hinted_files(st) == []
print('fixes14 ok')
