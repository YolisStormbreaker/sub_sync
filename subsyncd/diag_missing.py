"""Back-fills missing.json for the empty searches recorded before reasons were kept (state.json 'notfound').
Searches only (no download quota). Run inside the container while the service is idle:  python3 diag_missing.py [--limit N]"""
import os, sys, time
import main, media, missing

ctx = main.Ctx(); st = ctx.st
have = missing.load(main.STATE); done = skipped = 0
limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9
for key in list(st.get('notfound', {})):
    video, _, lang = key.rsplit('|', 2)
    if key in have or not os.path.exists(video) or not video.startswith(main.ROOT + '/'):
        skipped += 1; continue
    rel = os.path.relpath(video, main.ROOT)
    if rel.split('/')[0] not in media.INCLUDE or any(p in media.EXCLUDE_NAMES for p in rel.split('/')):
        skipped += 1; continue
    if done >= limit:
        break
    info = missing.diagnose(ctx.osc, lang, main.osdb_hash(video), media.guess(video), ctx.hints.lookup(rel))
    missing.record(main.STATE, key, info); done += 1
    print('%-9s %s | %s' % (info['code'], rel, info['en']), flush=True); time.sleep(1.2)
print('diagnosed', done, 'skipped', skipped)
