"""Screenshots of every panel page with representative fake data, for the design brief. Run: python3 make_shots.py out_dir"""
import json, os, subprocess, sys, tempfile, threading, time
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp(); out = sys.argv[1]; os.makedirs(out, exist_ok=True)
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import quality, review, prio, web, missing
from overrides import Overrides
probe, nf = {}, {}
def vid(rel, tracks, dur=2700, real=False):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    if real:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=300:d=120', '-f', 'lavfi', '-i', 'sine=f=700:d=120', '-map', '0', '-map', '1', '-c:a', 'aac', p], check=True)
    else:
        open(p, 'wb').write(b'x' * 4000)
    probe['%s|%d|%d' % (p, os.path.getsize(p), os.path.getmtime(p))] = {'audio': [dict(index=i, rel=i, lang=l, title=t, original=False, codec=c) for i, (l, t, c) in enumerate(tracks)], 'subs': [], 'duration': dur}
    return p
und2 = [('und', '', 'ac3'), ('und', '', 'ac3')]
tracks = {}
for s, e in [(1, 3), (1, 5), (2, 6), (3, 2), (3, 4)]:
    p = vid('TVshows/Doctor Who/Doctor.Who_S%02d/doctor.who.s%02de%02d.HDRip.avi' % (s, s, e), und2)
    tracks['%s|%d' % (p, 4000)] = {'lang': 'en', 'rel': 1, 'margin': 0.023, 'sure': False, 'metrics': {'0': {'contrast': 0.195}, '1': {'contrast': 0.218}}}
for e in range(1, 4):
    vid('TVshows/Black Mirror/Black.Mirror.s01e%02d.avi' % e, [('und', '', 'mp3'), ('und', '', 'mp3')])
vid('Movies/Goodfellas.mkv', [('und', '', 'ac3')] * 6, 8700)
vid('Movies/Aviator.2004.BDRip.avi', [('und', '', 'mp3')], 9900)
vid('Anime/Frieren/Frieren - 05.mkv', [('ja', '', 'aac'), ('ru', 'AniLibria', 'aac'), ('und', '', 'aac')], 1440)
vid('Anime/Frieren/Frieren - 06.mkv', [('ja', '', 'aac'), ('ru', 'AniLibria', 'aac'), ('und', '', 'aac')], 1440)
mentalist = vid('TVshows/The Mentalist/The.Mentalist.s06/The.Mentalist.s06e07.WEB-DL.mkv', [('ru', 'Dub', 'aac'), ('en', '', 'aac')], 120, real=True)
ab = [vid('TVshows/Abbott Elementary/S05/Abbott.Elementary.S05E%02d.1080p.mkv' % i, [('en', '', 'eac3')]) for i in range(10, 20)]
sp = vid('TVshows/Doctor Who/Doctor.Who_S12/doctor.who.s12e00.HDRip.avi', und2)
bs = vid('TVshows/Black Mirror/Black.Mirror.Bandersnatch.avi', und2)
now = time.time()
for p in ab: nf['%s|4000|ru' % p] = now - 3600; missing.record(state, '%s|4000|ru' % p, {'at': int(now), 'lang': 'ru', 'code': 'other_langs', 'ru': 'Эта серия в базе есть (es: 3, en: 2, tr: 2, ja: 1), но субтитров на языке «ru» никто не загрузил. Остаётся ждать: поиск повторится сам.', 'en': '', 'query': '', 'others': {'es': 3, 'en': 2}})
nf['%s|4000|en' % sp] = now - 7200; missing.record(state, '%s|4000|en' % sp, {'at': int(now), 'lang': 'en', 'code': 'special', 'ru': 'Серия с номером 0 — спецвыпуск. На OpenSubtitles спецвыпуски лежат в «сезоне 0» под другими номерами, поэтому поиск по 0-й серии пуст.', 'en': '', 'query': '', 'others': {}})
nf['%s|4000|en' % bs] = now - 7200; missing.record(state, '%s|4000|en' % bs, {'at': int(now), 'lang': 'en', 'code': 'no_guess', 'ru': 'Не удалось понять по имени файла, что это за серия или фильм (нужно «Название SxxEyy» или «Название год»), поэтому искал только по хеш-сумме файла, и такого файла в базе нет.', 'en': '', 'query': '', 'others': {}})
json.dump({'probe': probe, 'tracks': tracks, 'notfound': nf, 'daily': {'new': 3, 'backlog': 41}, 'quota': {'keyonly': {'remaining': 56}}}, open(state + '/state.json', 'w'))
ov = Overrides(state + '/overrides.json')
for f in ('TVshows/Doctor Who', 'TVshows/Black Mirror', 'TVshows/The Mentalist'): ov.set(f, 'en', None)
ov.set('TVshows/Doctor Who/Doctor.Who_S01/doctor.who.s01e05.HDRip.avi', None, 1)
ov.set('TVshows/Black Mirror/Black.Mirror.s01e02.avi', None, None, {'0': 'ru'})
srt = ''.join('%d\n00:00:%02d,000 --> 00:00:%02d,500\nLine %d of the dialogue\n\n' % (i + 1, 10 + 4 * i, 12 + 4 * i, i + 1) for i in range(12)).encode()
rel = os.path.relpath(mentalist, root)
for lang, near in (('ru', 0.875), ('en', 0.871)):
    q = quality.assess({'chain_q': {'acts': 5, 'windows': 150, 'inliers': 110, 'near': near, 'resid_med': 0.3, 'p': 0.0, 'cuts': [3]}}, 'ok', True)
    iid = review.hold(state, rel, lang, 'The.Mentalist.s06e07.WEB-DL', 1, srt, q, [0.0, 8.0, 60.0], 120)
    quality.record(state, rel, lang, 'drift', q, 'held', {'id': iid})
for e in (9, 12, 13, 21):
    quality.record(state, 'TVshows/The Mentalist/The.Mentalist.s06/The.Mentalist.s06e%02d.WEB-DL.mkv' % e, 'ru', 'drift', quality.assess({'drift': {'ok': True, 'inliers': 9, 'windows': 9, 'qs': [0], 'p': 0, 'resid_med': 0.1}}), 'written')
prio.Priorities(state + '/priorities.json').set('TVshows/The Mentalist', {'download': 1, 'sync': 4})
missing.Hints(state + '/searchhints.json').set('TVshows/Doctor Who', None, 57243)
threading.Thread(target=web.serve, args=(18744, root, state), daemon=True).start(); time.sleep(0.6)
pw = open(state + '/web_password').read().strip()
import shutil; FONT = os.environ.get('GOLOS_TTF', '')  # optional: without it the panel falls back to system fonts
if FONT: os.makedirs(state + '/fonts', exist_ok=True); shutil.copy(FONT, state + '/fonts/GolosText.ttf')
import json as _j, time as _t; _j.dump({'beat': int(_t.time()), 'kind': None}, open(state + '/activity.json', 'w'))
import statedb; st_ = statedb.load(state); st_['night'] = {'date': 'x', 'start': int(_t.time()) - 20000, 'end': int(_t.time()) - 12000, 'busy': 8040, 'written': 37, 'held': 4, 'notfound': 12, 'finished': True}
st_['daily'] = {'date': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d'), 'new': 3, 'backlog': 41}; statedb.save(state, st_)
from playwright.sync_api import sync_playwright
U = 'http://127.0.0.1:18744'
errs = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme, w, hgt, tag in (('dark', 1280, 900, 'desktop-dark'), ('light', 1280, 900, 'desktop-light'), ('dark', 390, 844, 'mobile-dark')):
        ctx = b.new_context(http_credentials={'username': 'u', 'password': pw}, viewport={'width': w, 'height': hgt}, color_scheme=scheme, device_scale_factor=1)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        for path, name in (('/', '1-language'), ('/missing', '2-not-found'), ('/review', '3-review'), ('/prio', '4-priorities'), ('/quality', '5-quality-log')):
            pg.goto(U + path); pg.wait_for_load_state('networkidle'); time.sleep(0.6)
            if path == '/review':
                c = pg.locator('.points .chip').nth(1)
                if c.count(): c.click(); time.sleep(2.5); pg.evaluate("Player.a && Player.a.pause()")
            if path == '/prio':
                pg.locator('tr.lvl-1', has_text='The Mentalist').locator('button').first.click(); time.sleep(0.3)
            pg.screenshot(path='%s/%s-%s.png' % (out, name, tag), full_page=True)
        ctx.close()
    b.close()
print('page errors:', errs)
print('shots in', out)
