"""What the panel shows, built from the service's files: state.db (probe cache, detection results, empty searches, quota),
overrides.json, searchhints.json, missing.json, priorities.json, the review store and the quality log.
Pure functions of (root, state_dir); the HTTP side is in web.py."""
import datetime, json, os, sqlite3, time
import jsonstore, media, missing, prio, quality, resolve, review, statedb, tmdb
from overrides import Overrides

LN = media.LANG_NAMES_RU
try:
    from trackid import MIN_MARGIN
except ImportError:  # the panel can run without numpy; the threshold is only quoted in a sentence
    MIN_MARGIN = 0.03
FIXABLE = ('unknown', 'no_guess')  # reasons a search hint can fix; the others only need waiting
STALE_AFTER = 30 * 60  # no sign of life from the service for this long: the panel says it is not responding


def load_state(state_dir, tables=None):
    try:
        return statedb.load(state_dir, tables)
    except sqlite3.Error:
        return {}  # locked for longer than the timeout or unreadable: the page shows nothing rather than an error


def group_of(rel):
    """Series or film folder ('TVshows/Doctor Who'); files lying directly in a section are grouped under the section itself."""
    parts = rel.split('/')
    return '/'.join(parts[:2]) if len(parts) > 2 else parts[0]


def group_info(gp):
    """Crumb and title of a group as the pages show them."""
    parts = gp.split('/')
    if len(parts) == 1:
        return {'section': gp, 'title': 'Отдельные фильмы' if gp == 'Movies' else 'Отдельные файлы', 'loose': True}
    return {'section': parts[0], 'title': parts[1], 'loose': False}


def current_probes(st, root):
    """(path, rel, probe) for videos that exist now, one per path: the probe cache keeps old size|mtime keys of replaced files."""
    best = {}
    for key, pr in st.get('probe', {}).items():
        path, _, mt = key.rsplit('|', 2)
        if path.startswith(root + '/') and (path not in best or int(mt) > best[path][0]):
            best[path] = (int(mt), pr)
    for path in sorted(best):
        rel = os.path.relpath(path, root)
        if rel.split('/')[0] in media.INCLUDE and not any(p in media.EXCLUDE_NAMES for p in rel.split('/')) and os.path.isfile(path):
            yield path, rel, best[path][1]


def lang_label(c):
    return '%s (%s)' % (LN.get(c, c), c)


def num(x):
    return ('%.2f' % x).replace('.', ',')


def why_ru(why):
    """Russian wording of the resolver's English reason."""
    if why.startswith('detected by sync score'):
        return 'сравнением звука каждой дорожки с субтитрами оригинала'
    return {'disposition original': 'дорожка помечена в файле как оригинальная', 'track titled original': 'в названии дорожки есть слово «оригинал»',
            'first track that is not ru/uk/dub': 'первая дорожка, которая не на русском и не дубляж', 'single audio track': 'в файле всего одна дорожка',
            'the only untagged track next to ru/uk dubs': 'единственная дорожка без языка рядом с русскими дубляжами',
            'only ru/uk audio (native or dub-only: cannot tell)': 'в файле только русская речь, оригинал от дубляжа не отличить',
            'several untagged audio tracks': 'несколько дорожек без языка', 'no audio': 'в файле нет звука',
            'chosen track (folder)': 'выбрана вами для всей папки', 'chosen track is not in this file': 'выбранной вами дорожки в этом файле нет'}.get(why, why)


def explain(rel, lang, why, conf, pend, entry, miss, ov, raw_pr, track=None):
    """The status of one file in plain Russian: where the language came from, then how the track was (or could not be) decided.
    The first sentence is the language; the page sets it in bold."""
    out, ls, ts = [], ov.source(rel, 'lang'), ov.source(rel, 'track')
    tl = (ov.lookup(rel) or {}).get('tlangs') or {}
    tag_lang = media.original_audio(raw_pr['audio'])[0]
    if lang is None:
        out.append('Язык оригинала неизвестен: в файле нет меток, а TMDb не нашёл название.')
    elif ls:
        out.append('Язык оригинала — %s, задан вами%s.' % (LN.get(lang, lang), '' if ls == rel else ' для папки %s' % ls.split('/')[-1]))
    elif lang in tl.values() and tag_lang != lang:
        out.append('Язык оригинала — %s, по языку дорожки, который указали вы.' % LN.get(lang, lang))
    elif tag_lang:
        out.append('Язык оригинала — %s, по метке в файле.' % LN.get(lang, lang))
    else:
        out.append('Язык оригинала — %s, по данным TMDb.' % LN.get(lang, lang))
    if conf:
        out.append('Оригинал — дорожка %s, %s.' % (track + 1 if track is not None else '?',
                   ('выбрана вами' + ('' if ts == rel else ' для всей папки')) if why.startswith('chosen track') else why_ru(why)))
    elif lang is None:
        out.append('Дорожку не определить, пока неизвестен язык. Укажите язык оригинала или язык дорожек: если пометить русские дубляжи, '
                   'оставшаяся дорожка станет оригиналом сама.')
    elif entry and entry.get('error'):
        out.append('Автоопределение не удалось (%s), повторится через %d дней. Послушайте дорожки и выберите оригинал.'
                   % (entry['error'][:100], media.RETRY_DAYS))
    elif entry:
        out.append('Автоопределение сравнило дорожки с субтитрами на языке «%s», но уверенного победителя нет: дорожка %d впереди на %s, '
                   'а нужно хотя бы %s. Послушайте с одного момента и выберите оригинал.'
                   % (LN.get(lang, lang), (entry.get('rel') or 0) + 1, num(entry.get('margin') or 0), num(MIN_MARGIN)))
    elif miss:
        out.append('Автоопределению не с чем сравнить: субтитры оригинала не найдены на OpenSubtitles. %s Выберите оригинал на слух.' % miss.get('ru', ''))
    elif pend:
        out.append('Автоопределение в очереди: ему нужны субтитры оригинала, а скачиваний в сутки ограниченное число. Можно не ждать и выбрать на слух.')
    else:
        out.append('По меткам и названиям дорожек оригинал не определить. Послушайте и выберите.')
    return out


def build_state(root, state_dir):
    """The language page: groups (series / film folders) with files in three sections.
    need  — the service cannot go on without the person: language unknown, track unclear, or a track deduced from the person's
            labels that they have not confirmed yet ('settled');
    queue — language known, the track waits for the automatic comparison (the person may decide by ear now);
    mine  — the person picked the track."""
    st = load_state(state_dir)
    ov, tm = Overrides(os.path.join(state_dir, 'overrides.json')), tmdb.TMDb(None, st)
    why_miss = missing.load(state_dir)
    nf = {}  # (video, lang) -> key of the empty search
    for k in st.get('notfound', {}):
        v, _, l = k.rsplit('|', 2); nf[(v, l)] = k
    groups, counts, tracks = {}, {'pending': 0, 'detected': 0, 'files': 0}, st.get('tracks', {})
    for path, rel, raw_pr in current_probes(st, root):
        counts['files'] += 1
        pr = resolve.relabel(rel, raw_pr, ov)  # tracks the person labelled count with the language they gave
        own = ov.all().get(rel) or {}
        mine = own.get('tlangs') or {}
        lang, track, why, conf = resolve.resolve(rel, path, pr, ov, tm, tracks)
        pend = resolve.pending_detect(lang, pr, conf, tracks, path)
        counts['pending'] += pend; counts['detected'] += why.startswith('detected')
        cands = media.candidate_tracks(pr['audio'])
        entry = resolve._entry(tracks, path, lang, cands) if lang else None
        miss = None
        if lang and nf.get((path, lang)):
            miss = why_miss.get(nf[(path, lang)]) or {'ru': 'Причина будет записана при следующем поиске.'}
        auto = None
        if entry:
            auto = {'best': entry.get('rel'), 'margin': entry.get('margin'), 'sure': entry.get('sure'), 'error': entry.get('error'),
                    'scores': {str(r): round(m.get('contrast', 0), 3) for r, m in (entry.get('metrics') or {}).items()}}
        chosen = own.get('track') is not None
        settled = bool(mine) and conf and not chosen and not why.startswith('chosen track')
        f = {'path': rel, 'lang': lang, 'why': why, 'conf': conf, 'pending': pend, 'own': own, 'dur': pr.get('duration') or 0,
             'tracks': [{'i': a['rel'], 'lang': a['lang'], 'mine': str(a['rel']) in mine, 'title': a['title'][:40], 'codec': (a.get('codec') or '').upper()}
                        for a in pr['audio']],
             'auto': auto, 'track': track if conf else None,
             'settled': {'track': track, 'why': why} if settled else None,
             'cands': cands if (mine and not conf) else None,
             'lines': explain(rel, lang, why, conf, pend, entry, miss, ov, raw_pr, track)}
        gp = group_of(rel)
        g = groups.setdefault(gp, dict(group_info(gp), path=gp, need=[], queue=[], mine=[], nfiles=0, layouts={},
                                       override=ov.all().get(gp) if '/' in gp else None))
        g['nfiles'] += 1
        lay = ' + '.join('%s%s' % (a['lang'], '[%s]' % a['title'][:14] if a['title'] else '') for a in raw_pr['audio']) or 'нет звука'
        g['layouts'][lay] = g['layouts'].get(lay, 0) + 1
        if chosen:
            g['mine'].append(f)
        elif lang is None or settled or (not conf and not pend):
            g['need'].append(f)
        elif pend:
            g['queue'].append(f)
    shown = []
    for g in groups.values():
        g['layouts'] = sorted(g['layouts'].items(), key=lambda kv: -kv[1])
        for k in ('need', 'queue', 'mine'):
            g[k] = g[k][:300]
        if g['need'] or g['queue'] or g['mine']:
            shown.append(g)
    shown.sort(key=lambda g: (-len(g['need']), -len(g['queue']), g['path']))
    return {'groups': shown, 'pending': counts['pending'], 'detected': counts['detected'], 'files': counts['files'],
            'need': sum(len(g['need']) for g in shown)}


def build_missing(root, state_dir):
    """Empty searches (state 'notfound') with the recorded reason; files that are gone or were replaced are left out.
    'soon': a hint was saved after the last search, so the service searches again within a poll interval."""
    st = load_state(state_dir)
    why, hints, items = missing.load(state_dir), missing.Hints(os.path.join(state_dir, 'searchhints.json')), []
    done = st.get('hints_done', 0)
    for key, ts in st.get('notfound', {}).items():
        video, size, lang = key.rsplit('|', 2)
        try:
            if not video.startswith(root + '/') or os.path.getsize(video) != int(size):
                continue
        except OSError:
            continue
        rel = os.path.relpath(video, root)
        if rel.split('/')[0] not in media.INCLUDE or any(p in media.EXCLUDE_NAMES for p in rel.split('/')):
            continue
        w, h = why.get(key) or {}, hints.lookup(rel)
        code = w.get('code') or 'old'
        items.append(dict(group_info(group_of(rel)), path=rel, group=group_of(rel), lang=lang, at=int(ts),
                          retry=int(ts) + media.RETRY_DAYS * 86400, code=code, fixable=code in FIXABLE,
                          ru=w.get('ru') or 'Причина не записана: поиск был до обновления. «Искать снова» запишет её.',
                          others=w.get('others') or {}, hint=h, soon=bool(h and h['at'] > max(ts, done))))
    return {'items': items, 'retry_days': media.RETRY_DAYS, 'fixable': sum(i['fixable'] for i in items)}


def build_prio(root, state_dir):
    """Sections, then series / film folders, each with its files, with the effective priority of every stage and where it comes from."""
    st = load_state(state_dir)
    pr = prio.Priorities(os.path.join(state_dir, 'priorities.json'))

    def eff(rel):
        out = {}
        for s in prio.STAGES:
            v, src = pr.explicit(rel, s)
            dflt = prio.DEFAULT.get(rel.split('/')[0], 9)
            out[s] = {'v': v if v is not None else dflt, 'src': src, 'dflt': dflt}
        return out
    groups, tops = {}, {}
    for path, rel, _ in current_probes(st, root):
        top = rel.split('/')[0]
        t = tops.setdefault(top, {'path': top, 'count': 0, 'files': [], 'level': 0}); t['count'] += 1
        gp = group_of(rel)
        if gp == top:  # a file lying directly in the section is listed under the section
            if len(t['files']) < 300:
                t['files'].append({'path': rel, 'eff': eff(rel)})
            continue
        g = groups.setdefault(gp, {'path': gp, 'count': 0, 'files': [], 'level': 1})
        g['count'] += 1
        if len(g['files']) < 300:
            g['files'].append({'path': rel, 'eff': eff(rel)})
    out = []
    for t in sorted(tops):
        tops[t]['eff'] = eff(t); tops[t]['files'].sort(key=lambda f: f['path']); out.append(tops[t])
        for g in sorted((g for g in groups.values() if g['path'].split('/')[0] == t), key=lambda g: g['path']):
            g['eff'] = eff(g['path']); g['files'].sort(key=lambda f: f['path']); out.append(g)
    return out


def build_review(state_dir):
    """Held subtitles with the threshold that would have let them through, in the words of the page."""
    out = []
    for m in review.items(state_dir):
        mode = (m.get('metrics') or {}).get('mode')
        m['threshold'] = {'chain': quality.CHAIN_NEAR_OK, 'audio': quality.AUDIO_COVER_OK}.get(mode)
        m['srt'] = '%s.%s.srt' % (m['stem'], m['lang'])
        out.append(m)
    return out


def build_status(root, state_dir):
    """Rail of every page: is the service alive, what it is doing, last night, today's downloads, what waits for the person."""
    st = load_state(state_dir, ('daily', 'quota', 'night'))
    try:
        act = jsonstore.read(os.path.join(state_dir, 'activity.json'))
    except jsonstore.Corrupt:
        act = {}
    now = time.time()
    d = st.get('daily') or {}
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    used = (d.get('new', 0) + d.get('backlog', 0)) if d.get('date') == today else 0
    rem = ((st.get('quota') or {}).get('keyonly') or {}).get('remaining')
    reset = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
    night = st.get('night') or None
    pending_review = sum(1 for m in review.items(state_dir) if m['status'] == 'pending')
    return {'now': int(now), 'beat': act.get('beat'), 'alive': bool(act.get('beat')) and now - act['beat'] < STALE_AFTER,
            'kind': act.get('kind'), 'since': act.get('since'), 'night': night,
            'quota': {'used': used if rem is None else max(used, 100 - rem), 'limit': 100, 'remaining': rem, 'reset': int(reset)},
            'badges': {'lang': build_state(root, state_dir)['need'], 'review': pending_review, 'missing': build_missing(root, state_dir)['fixable']}}
