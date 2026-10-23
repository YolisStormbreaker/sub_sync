"""Scanning rules, ffprobe, original-audio detection, existing-subtitle detection, filename parsing."""
import json, os, re, subprocess

INCLUDE = ('Animation', 'Anime', 'Movies', 'TVshows')
EXCLUDE_NAMES = frozenset({'Others', '#recycle', '@eaDir', 'Plex Versions'})


def check_rel(rel):
    """'Section/folder/file' inside the scanned sections, normalised; ValueError for anything else (.., excluded names, other folders)."""
    parts = [p for p in str(rel).split('/') if p]
    if not parts or '..' in parts or '.' in parts or parts[0] not in INCLUDE or any(p in EXCLUDE_NAMES for p in parts) or '\0' in str(rel):
        raise ValueError('path is outside the scanned folders')
    return '/'.join(parts)


VIDEO_EXT = frozenset({'.mkv', '.mp4', '.avi', '.m4v', '.mov', '.ts', '.m2ts', '.wmv'})
SUB_EXT = frozenset({'.srt', '.ass', '.ssa', '.sub', '.vtt', '.sup', '.idx', '.smi'})

LANGS = {
    'ru': 'ru rus russian рус русский', 'en': 'en eng english анг английский', 'ja': 'ja jpn jap japanese',
    'fr': 'fr fre fra french', 'de': 'de ger deu german', 'es': 'es spa spanish', 'it': 'it ita italian',
    'ko': 'ko kor korean', 'zh': 'zh chi zho chinese', 'pt': 'pt por portuguese', 'uk': 'uk ukr ukrainian',
    'pl': 'pl pol polish', 'tr': 'tr tur turkish', 'cs': 'cs cze ces czech', 'nl': 'nl dut nld dutch',
    'sr': 'sr srp serbian', 'da': 'da dan danish', 'sv': 'sv swe swedish', 'no': 'no nor norwegian', 'fi': 'fi fin finnish',
    'hu': 'hu hun hungarian', 'ro': 'ro rum ron romanian', 'el': 'el gre ell greek', 'he': 'he heb hebrew', 'hi': 'hi hin hindi',
    'th': 'th tha thai', 'vi': 'vi vie vietnamese', 'ar': 'ar ara arabic', 'id': 'id ind indonesian', 'bg': 'bg bul bulgarian',
    'hr': 'hr hrv croatian', 'fa': 'fa per fas persian', 'ca': 'ca cat catalan',
}
# Russian names for the panel, in the order the language pickers offer them (the most likely originals first).
LANG_NAMES_RU = {
    'en': 'английский', 'ja': 'японский', 'fr': 'французский', 'de': 'немецкий', 'es': 'испанский', 'it': 'итальянский', 'ko': 'корейский',
    'zh': 'китайский', 'ru': 'русский', 'uk': 'украинский', 'pl': 'польский', 'tr': 'турецкий', 'nl': 'нидерландский', 'sv': 'шведский',
    'da': 'датский', 'no': 'норвежский', 'fi': 'финский', 'pt': 'португальский', 'cs': 'чешский', 'sr': 'сербский', 'hu': 'венгерский',
    'ro': 'румынский', 'el': 'греческий', 'he': 'иврит', 'hi': 'хинди', 'th': 'тайский', 'vi': 'вьетнамский', 'ar': 'арабский',
    'id': 'индонезийский', 'bg': 'болгарский', 'hr': 'хорватский', 'fa': 'персидский', 'ca': 'каталанский'}
assert set(LANG_NAMES_RU) == set(LANGS)
RETRY_DAYS = 7  # empty searches, rejected syncs, failed track detections and TMDb misses are tried again after this
DUB_LANGS = ('ru', 'uk')  # dub languages in this library: Russian and Ukrainian voice-overs of foreign originals
LANG_OF = {tok: code for code, toks in LANGS.items() for tok in toks.split()}
DUB_WORDS = ('dub', 'дубл', 'закадр', 'многогол', 'одногол', 'двухгол', 'overdub', 'voice', 'lostfilm', 'newstudio',
             'baibako', 'tv3', 'amedia', 'hdrezka', 'jaskier', 'кубик', 'mvo', 'dvo', 'avo', '1+1', 'озвуч', 'студия', 'studio',
             'tvshows', 'sound', '1win', 'синхрон')


def is_excluded(path, root):
    """True for anything under an excluded name, or whose real location is under one (symlinks)."""
    for p in (path, os.path.realpath(path)):
        rel = os.path.relpath(p, root) if p.startswith(root.rstrip('/') + '/') else None
        if rel is not None and any(part in EXCLUDE_NAMES for part in rel.split(os.sep)):
            return True
    return False


def scan(root):
    """Yield video files below the included top-level folders; excluded folders are pruned, symlinks not followed."""
    for top in INCLUDE:
        base = os.path.join(root, top)
        for d, dirs, files in os.walk(base):
            dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_NAMES)
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in VIDEO_EXT and not f.startswith('.'):
                    p = os.path.join(d, f)
                    if not is_excluded(p, root):
                        yield p


def lang_code(token):
    return LANG_OF.get(token.strip().lower())


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', '--', path],
                       capture_output=True, timeout=120)
    if r.returncode:
        raise RuntimeError('ffprobe: ' + r.stderr.decode('utf-8', 'replace')[:200])
    j = json.loads(r.stdout)
    audio, subs = [], []
    for s in j.get('streams', []):
        tags = {k.lower(): v for k, v in (s.get('tags') or {}).items()}
        item = {'index': s['index'], 'lang': lang_code(tags.get('language', '')) or tags.get('language', 'und'),
                'title': tags.get('title', ''), 'original': bool((s.get('disposition') or {}).get('original')),
                'codec': s.get('codec_name')}
        if s.get('codec_type') == 'audio':
            item['rel'] = len(audio); audio.append(item)
        elif s.get('codec_type') == 'subtitle':
            subs.append(item)
    return {'audio': audio, 'subs': subs, 'duration': float(j.get('format', {}).get('duration') or 0)}


def is_dub(a):
    return any(w in a['title'].lower() for w in DUB_WORDS)


def candidate_tracks(audio):
    """Untagged tracks that are not named like a dub: the original is one of them when the tags cannot tell."""
    return [a['rel'] for a in audio if a['lang'] == 'und' and not is_dub(a)]


def original_audio(audio):
    """(lang, audio-relative index, reason, confident). lang None = language untagged; confident False = the original
    track cannot be told from the dubs, so nothing may be synced against it until a person picks the track."""
    if not audio:
        return None, None, 'no audio', False
    dub = lambda a: any(w in a['title'].lower() for w in DUB_WORDS)
    lang = lambda a: a['lang'] if a['lang'] in LANGS else None
    for a in audio:
        if a['original']:
            return lang(a), a['rel'], 'disposition original', True
    for a in audio:
        if re.search(r'orig|оригинал', a['title'], re.I):
            return lang(a), a['rel'], 'track titled original' + ('' if lang(a) else ' (language untagged)'), True
    foreign = [a for a in audio if a['lang'] not in DUB_LANGS + ('und',) and not dub(a)]
    if foreign:
        return lang(foreign[0]), foreign[0]['rel'], 'first track that is not ru/uk/dub', True
    if len(audio) == 1:
        return lang(audio[0]), audio[0]['rel'], 'single audio track', True
    und = [a for a in audio if a['lang'] == 'und' and not dub(a)]
    if len(und) == 1 and all(a['lang'] in DUB_LANGS + ('und',) for a in audio):
        return None, und[0]['rel'], 'the only untagged track next to ru/uk dubs', True
    if all(a['lang'] in DUB_LANGS for a in audio):
        return audio[0]['lang'], audio[0]['rel'], 'only ru/uk audio (native or dub-only: cannot tell)', True
    return None, audio[0]['rel'], 'several untagged audio tracks', False


def existing_langs(video, pr):
    """Languages already available: sidecar files next to the video (any token that names a language) and embedded streams."""
    d, stem = os.path.split(video)[0], os.path.splitext(os.path.basename(video))[0]
    have = {}
    for f in os.listdir(d):
        base, ext = os.path.splitext(f)
        if ext.lower() in SUB_EXT and base.startswith(stem + '.'):
            for tok in re.split(r'[.\s_-]+', base[len(stem) + 1:]):
                c = lang_code(tok)
                if c:
                    have.setdefault(c, []).append(f)
    for s in pr['subs']:
        if s['lang'] in LANGS:
            have.setdefault(s['lang'], []).append('embedded #%d' % s['index'])
    return have


def wanted_langs(orig):
    return ['ru'] + ([orig] if orig and orig != 'ru' else [])


NOISE = re.compile(r'\b(480p|576p|720p|1080p|2160p|4k|web[- ]?dl|web[- ]?rip|bluray|bdrip|hdtv|x264|x265|h\.?264|hevc|rus|eng|dub)\b.*', re.I)


def guess(video):
    """{'type','title','season','episode'} or {'type':'movie','title','year'}; None when nothing usable."""
    stem = re.sub(r'[._]+', ' ', os.path.splitext(os.path.basename(video))[0])
    m = re.search(r'\bS(\d{1,2})\s?E(\d{1,3})(?!\d)', stem, re.I) or re.search(r'\b(\d{1,2})x(\d{2,3})\b', stem)
    if m:
        title = stem[:m.start()].strip(' -')
        if len(title) < 2:  # file named only SxxEyy: take the show name from the folders above
            for part in reversed(os.path.dirname(video).split(os.sep)):
                if not re.match(r'(season|сезон|s\d+)\b', part, re.I) and part not in INCLUDE:
                    title = re.sub(r'[._]+', ' ', re.sub(r'\bs\d+\b.*', '', part, flags=re.I)).strip(); break
        return {'type': 'episode', 'title': title, 'season': int(m.group(1)), 'episode': int(m.group(2))}
    m = re.search(r'\b(19\d\d|20\d\d)\b', stem)
    if m and m.start() > 1:
        return {'type': 'movie', 'title': stem[:m.start()].strip(' ([-'), 'year': int(m.group(1))}
    return None


def tokens(name):
    return set(re.findall(r'[a-z0-9]+', name.lower()))
