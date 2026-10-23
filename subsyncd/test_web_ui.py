"""Drives the redesigned panel in headless Chromium against a server with fake state. Run: python3 test_web_ui.py [shots_dir]"""
import array, base64, json, os, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
sys.path.insert(0, '.')
root = tempfile.mkdtemp(); state = tempfile.mkdtemp(); shots = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.environ['SUBSYNC_ROOT'] = root; os.environ['SUBSYNC_STATE'] = state
import quality, review, prio, web, missing
from overrides import Overrides

probe = {}
def vid(rel, langs, dur=100, sine=False):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    if sine:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=300:d=%d' % dur, '-f', 'lavfi', '-i', 'sine=f=700:d=%d' % dur,
                        '-map', '0', '-map', '1', '-c:a', 'aac', p], check=True)
    else:
        open(p, 'wb').write(b'x' * 3000)
    probe['%s|%d|%d' % (p, os.path.getsize(p), os.path.getmtime(p))] = {
        'audio': [{'index': i, 'rel': i, 'lang': l, 'title': '', 'original': False, 'codec': 'aac'} for i, l in enumerate(langs)], 'subs': [], 'duration': dur}
    return p
odd = vid('Movies/Odd (2019)/Odd.mkv', ['und', 'und'], 100, sine=True)
ment = vid('TVshows/The Mentalist/The.Mentalist.s06/The.Mentalist.s06e07.WEB-DL.mkv', ['ru', 'en'], 120, sine=True)
many = vid('Movies/Many (2018)/Many.mkv', ['und'] * 4)
for i in range(1, 9):
    vid('TVshows/Show/S01/Show.S01E%02d.mkv' % i, ['und', 'und'], 2400)
loose = vid('Movies/Loose.Film.2001.mkv', ['und'], 5000)
nf = {}
ab = [vid('TVshows/Abbott Elementary/S05/Abbott.Elementary.S05E%02d.mkv' % i, ['en']) for i in (10, 11)]
for p in ab:
    k = '%s|%d|ru' % (p, os.path.getsize(p)); nf[k] = time.time() - 3600
    missing.record(state, k, {'at': 1, 'lang': 'ru', 'code': 'other_langs', 'ru': 'Есть только на en.', 'en': '', 'query': '', 'others': {'en': 2, 'es': 1}})
lou = vid('TVshows/Louie/Season 1/louie.s01e01.mkv', ['en'])
k = '%s|%d|ru' % (lou, os.path.getsize(lou)); nf[k] = time.time() - 3600
missing.record(state, k, {'at': 1, 'lang': 'ru', 'code': 'unknown', 'ru': 'OpenSubtitles не знает такую серию.', 'en': '', 'query': '', 'others': {}})
json.dump({'probe': probe, 'notfound': nf, 'daily': {}, 'quota': {}}, open(state + '/state.json', 'w'))
json.dump({'beat': int(time.time())}, open(state + '/activity.json', 'w'))
import shutil; FONT = os.environ.get('GOLOS_TTF', '')  # optional; without it the font request 404s and is not counted as an error
if FONT: os.makedirs(state + '/fonts'); shutil.copy(FONT, state + '/fonts/GolosText.ttf')
srt = ''.join('%d\n00:00:%02d,000 --> 00:00:%02d,500\nLine %d <i>x</i>\n\n' % (i + 1, 10 + 4 * i, 12 + 4 * i, i + 1) for i in range(12)).encode()
rel_m = os.path.relpath(ment, root)
q = quality.assess({'chain_q': {'acts': 5, 'windows': 150, 'inliers': 110, 'near': 0.66, 'resid_med': 0.3, 'p': 0.0, 'cuts': [3]}}, 'ok', True)
ids = {}
for lang in ('ru', 'en'):
    ids[lang] = review.hold(state, rel_m, lang, 'The.Mentalist.s06e07.WEB-DL', 1, srt, q, [0.0, 8.0, 60.0], 120, ment)
    quality.record(state, rel_m, lang, 'drift', q, 'held', {'id': ids[lang]})
quality.record(state, 'TVshows/Show/S01/Show.S01E01.mkv', 'ru', 'drift', quality.assess({'drift': {'ok': True, 'inliers': 9, 'windows': 9, 'qs': [0], 'p': 0, 'resid_med': 0.1}}), 'written')
OV = lambda: Overrides(state + '/overrides.json')
OV().set('TVshows/Show', 'en', None)
threading.Thread(target=web.serve, args=(18745, root, state), daemon=True).start(); time.sleep(0.5)
pw = open(state + '/web_password').read().strip()
U = 'http://127.0.0.1:18745'
AUTH = 'Basic ' + base64.b64encode(('u:' + pw).encode()).decode()

def get(path):
    rq = urllib.request.Request(U + path); rq.add_header('Authorization', AUTH)
    try:
        r = urllib.request.urlopen(rq); return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# server side: static files, status, clip safety
assert get('/static/app.js')[0] == 200 and get('/static/subsync.css')[0] == 200 and get('/static/../web.py')[0] == 404 and get('/static/web.py')[0] == 404
s = json.loads(get('/api/status')[1]); print('status', s); assert s['alive'] and s['badges']['review'] == 2 and s['badges']['missing'] == 1 and s['badges']['lang'] >= 3
for bad in ('../x', 'Movies/../../etc/passwd', '/etc/passwd', 'Others/a.mkv', 'Movies/Plex%20Versions/a.mkv', 'Movies', 'Movies/nonexistent.mkv', ''):
    assert get('/api/clip?path=' + bad + '&track=0&t=0&len=5')[0] == 400, bad
def hz(track):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', '-', '-f', 's16le', '-ac', '1', '-ar', '8000', '-'],
                         input=get('/api/clip?path=Movies/Odd%20(2019)/Odd.mkv&track=' + str(track) + '&t=10&len=5')[1], capture_output=True).stdout
    x = array.array('h'); x.frombytes(raw[:len(raw) // 2 * 2]); x = x[4000:]
    return sum(1 for i in range(1, len(x)) if (x[i - 1] < 0) != (x[i] < 0)) / 2 / (len(x) / 8000)
h0, h1 = hz(0), hz(1); assert abs(h0 - 300) < 20 and abs(h1 - 700) < 30, (h0, h1)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(http_credentials={'username': 'u', 'password': pw}, viewport={'width': 1280, 'height': 900}, color_scheme='dark')
    pg = ctx.new_page(); errs = []
    pg.on('response', lambda r: errs.append('HTTP %d %s' % (r.status, r.url)) if r.status >= 400 and not (r.status == 404 and not FONT and r.url.endswith('golos.ttf')) else None); pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'favicon' not in m.text and not (not FONT and '404' in m.text) else None)
    card = lambda name: pg.locator('article.card', has=pg.locator('h3.fname', has_text=name))

    # ---------- language page
    pg.goto(U + '/'); pg.wait_for_selector('article.card')
    assert pg.locator('.nav a[aria-current="page"] .count').inner_text() == str(s['badges']['lang'])
    assert pg.locator('section.group', has_text='Отдельные фильмы').count() == 1, 'loose files sit under their section'
    pg.fill('.search input', 'odd'); pg.wait_for_selector('article.card')
    c = card('Odd.mkv'); assert c.locator('li.track').count() == 2 and c.locator('li.track .btn', has_text='Это оригинал').count() == 2
    c.locator('li.track').nth(1).locator('button.play').click()
    pg.wait_for_function("Player.a && Player.a.src.includes('track=1') && Player.a.src.includes('t=50') && Player.a.readyState >= 2", timeout=20000)
    pg.wait_for_selector('li.track.is-playing .playtime'); assert 'Играет' in c.locator('li.track').nth(1).inner_text()
    c.locator('button', has_text='Другой фрагмент').click()
    pg.wait_for_function("Player.a.src.includes('t=30') && Player.a.src.includes('track=1')")
    assert '0:30' in c.locator('.moment-label').inner_text()
    pg.screenshot(path=shots + '/lang_playing.png')
    # folder language: saves on change, says when it applies
    g = pg.locator('section.group', has_text='Odd (2019)')
    g.locator('.folder-set select').first.select_option('en'); g.locator('.feedback--saved').first.wait_for()
    assert OV().lookup('Movies/Odd (2019)/Odd.mkv')['lang'] == 'en'
    # label track 1 Russian: the original is deduced, the card stays and asks to confirm
    pg.fill('.search input', 'odd'); pg.wait_for_selector('article.card')
    card('Odd.mkv').locator('li.track').nth(0).locator('select').select_option('ru')
    pg.wait_for_selector('article.card--settled'); time.sleep(0.3)
    c = card('Odd.mkv'); assert 'Оригинал — дорожка 2' in c.locator('.verdict').inner_text(), c.inner_text()
    assert 'Оригинал теперь определён сам: дорожка 2' in pg.locator('.toasts').inner_text()
    assert OV().all()['Movies/Odd (2019)/Odd.mkv'] == {'lang': None, 'track': None, 'tlangs': {'0': 'ru'}}
    pg.screenshot(path=shots + '/lang_settled.png')
    c.locator('.verdict .btn--primary').click(); pg.wait_for_selector('.collapsed-stub')
    assert OV().lookup('Movies/Odd (2019)/Odd.mkv')['track'] == 1 and 'дорожка 2' in pg.locator('.collapsed-stub').inner_text()
    pg.locator('.collapsed-stub button', has_text='Отменить').click(); pg.wait_for_selector('article.card'); time.sleep(0.3)
    assert OV().lookup('Movies/Odd (2019)/Odd.mkv').get('track') is None, OV().all()
    # six-voice style: two labels leave two candidates
    pg.fill('.search input', 'many'); pg.wait_for_selector('article.card')
    card('Many.mkv').locator('li.track').nth(0).locator('select').select_option('ru'); time.sleep(0.8)
    card('Many.mkv').locator('li.track').nth(1).locator('select').select_option('uk'); time.sleep(0.8)
    assert 'Осталось 2 кандидата: дорожки 3 и 4' in card('Many.mkv').locator('.cands').inner_text()
    assert card('Many.mkv').locator('li.track.is-candidate').count() == 2
    pg.screenshot(path=shots + '/lang_cands.png')
    # no jump: pick the original on a card in the middle of a long list; the next card keeps its place and gets the focus
    pg.fill('.search input', 'show'); pg.wait_for_selector('article.card'); pg.set_viewport_size({'width': 1280, 'height': 700})
    cards = pg.locator('article.card'); assert cards.count() == 8, cards.count()
    pg.evaluate("document.querySelectorAll('article.card')[3].scrollIntoView({block:'start'})"); time.sleep(0.2)
    nxt = pg.evaluate("document.querySelectorAll('article.card')[4].dataset.path"); top0 = pg.evaluate("document.querySelectorAll('article.card')[4].getBoundingClientRect().top")
    y0 = pg.evaluate('scrollY')
    cards.nth(3).locator('li.track').nth(0).locator('.btn', has_text='Это оригинал').click(); pg.wait_for_selector('.collapsed-stub'); time.sleep(0.5)
    top1 = pg.evaluate("p => [...document.querySelectorAll('article.card')].find(e => e.dataset.path === p).getBoundingClientRect().top", nxt)
    y1 = pg.evaluate('scrollY'); print('scroll', y0, y1, 'next card', round(top0), round(top1))
    assert y1 == y0 and top1 < top0 and top0 - top1 < 600, 'the page did not jump, the next card moved up under the stub'
    assert pg.evaluate("document.activeElement.closest('article.card') && document.activeElement.closest('article.card').dataset.path") == nxt, 'focus moved to the next card'
    pg.set_viewport_size({'width': 1280, 'height': 900})
    # folder-wide track asks first, inline
    pg.fill('.search input', 'show'); pg.wait_for_selector('article.card')
    g = pg.locator('section.group', has_text='Show'); g.locator('.folder-set select').nth(1).select_option('1')
    pg.wait_for_selector('.confirm'); assert OV().lookup('TVshows/Show/S01/Show.S01E08.mkv').get('track') is None
    pg.locator('.confirm .btn', has_text='Отмена').click(); assert pg.locator('.confirm').count() == 0
    pg.fill('.search input', ''); time.sleep(0.2); pg.screenshot(path=shots + '/lang.png', full_page=True)

    # ---------- not found
    pg.goto(U + '/missing'); pg.wait_for_selector('section.group')
    assert pg.locator('.reasons-row', has_text='Можно исправить').locator('.chip').count() == 1
    lg = pg.locator('section.group', has_text='Louie'); assert lg.locator('form.hintform').count() == 1
    ag = pg.locator('section.group', has_text='Abbott Elementary'); assert ag.locator('.wait-note').count() == 1 and ag.locator('details.mini', has_text='Всё равно указать подсказку').count() == 1
    lg.locator('input').nth(1).fill('https://www.themoviedb.org/tv/24009-louie'); lg.locator('button[type=submit]').click(); time.sleep(0.3)
    assert '24009' in lg.locator('.feedback--error').inner_text() and missing.Hints(state + '/searchhints.json').lookup('TVshows/Louie/Season 1/louie.s01e01.mkv') is None
    lg.locator('input').nth(1).fill('24009'); lg.locator('button[type=submit]').click(); time.sleep(0.8)
    h_ = missing.Hints(state + '/searchhints.json').lookup('TVshows/Louie/Season 1/louie.s01e01.mkv'); assert h_ and h_['tmdb'] == 24009, h_
    assert 'в течение 2 мин' in pg.locator('section.group', has_text='Louie').inner_text()
    pg.screenshot(path=shots + '/missing.png', full_page=True)

    # ---------- review: approve with an 8 s undo window
    pg.goto(U + '/review'); pg.wait_for_selector('.qitem')
    # every spinner turns, including the big play button of a review item (it used to stay still while the clip loaded)
    assert pg.evaluate("() => { const b = document.querySelector('.bigplay'); b.replaceChildren(icon('spin')); return getComputedStyle(b.firstChild).animationName }") == 'ss-spin'
    pg.reload(); pg.wait_for_selector('.qitem')
    assert pg.locator('.qitem').count() == 2
    pg.locator('.points .chip', has_text='0:08').click()
    pg.wait_for_function("Player.a && Player.a.readyState >= 2 && Player.a.currentTime > 2.5", timeout=20000)
    assert 'Line' in pg.locator('.sub-now').inner_text() and pg.locator('.ruler .cue').count() > 3
    pg.screenshot(path=shots + '/review.png')
    out = os.path.join(os.path.dirname(ment), 'The.Mentalist.s06e07.WEB-DL.%s.srt')
    first = pg.locator('.bench h2').inner_text(); lang1 = 'en' if 'английские' in pg.locator('.bench .badges').inner_text() else 'ru'
    pg.locator('.decide .btn--primary').click(); pg.wait_for_selector('.toast .toast-timer')
    pg.locator('.toast .btn', has_text='Отменить').click(); time.sleep(1)
    assert not os.path.exists(out % lang1), 'undone inside the window: nothing written'
    pg.locator('.decide .btn--primary').click(); time.sleep(9.5)
    assert open(out % lang1, 'rb').read() == srt, 'written byte for byte after the window'
    assert pg.locator('.qitem').count() == 1
    pg.locator('.decide .btn--quiet', has_text='Сделать заново').click(); pg.wait_for_selector('.confirm')
    pg.locator('.confirm .btn', has_text='Оставить как есть').click()
    pg.locator('.decide .btn--danger').click(); time.sleep(0.8)
    other = 'ru' if lang1 == 'en' else 'en'
    assert review.get(state, ids[other])['status'] == 'rejected'

    # ---------- priorities: saves on change, inherited notes follow
    pg.goto(U + '/prio'); pg.wait_for_selector('tr.lvl-1')
    row = pg.locator('tr.lvl-1', has_text='Show'); row.locator('select').nth(1).select_option('2'); row.locator('.feedback--saved').wait_for()
    assert prio.Priorities(state + '/priorities.json').get('TVshows/Show', 'download') == 2
    row.locator('button[aria-label="Показать файлы"]').click(); time.sleep(0.3)
    assert 'сейчас 2, от TVshows/Show' in pg.locator('tr.lvl-2').first.inner_text()
    pg.screenshot(path=shots + '/prio.png', full_page=True)

    # ---------- quality log
    pg.goto(U + '/quality'); pg.wait_for_selector('tbody tr')
    pg.locator('.seg[aria-label="Вердикт"] button', has_text='Надёжные').click(); time.sleep(0.2)
    assert pg.locator('tbody tr:not(.qgroup)').count() == 1
    pg.screenshot(path=shots + '/quality.png', full_page=True)

    # ---------- phone width: no horizontal scroll on any page
    pg.set_viewport_size({'width': 390, 'height': 844})
    for path in ('/', '/review', '/missing', '/prio', '/quality'):
        pg.goto(U + path); pg.wait_for_load_state('networkidle'); time.sleep(0.4)
        w = pg.evaluate('document.documentElement.scrollWidth'); assert w <= 392, (path, w)
    print('page errors:', errs); assert not errs, errs
    b.close()
print('web ui ok', shots)
