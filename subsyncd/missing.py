"""Why a subtitle search found nothing, and the search hints (title / TMDb id) a person can give to fix it.
missing.json  {"<video>|<size>|<lang>": {"at", "lang", "code", "ru", "en", "query", "others", "hint"}}  reasons, kept next to state.json's 'notfound'
searchhints.json  {"TVshows/Doctor Who": {"title": "...", "tmdb": 57243, "at": ts}}  longest matching path wins; 'at' makes the next run search again."""
import os, time
import media

import jsonstore


def load(state_dir):
    try:
        return jsonstore.read(os.path.join(state_dir, 'missing.json'))
    except jsonstore.Corrupt:
        return {}


def record(state_dir, key, info):
    jsonstore.update(os.path.join(state_dir, 'missing.json'), lambda d: dict(d, **{key: info}))


def clear(state_dir, key):
    p = os.path.join(state_dir, 'missing.json')
    if key in load(state_dir):
        jsonstore.update(p, lambda d: {k: v for k, v in d.items() if k != key})


def describe_query(guess, hint):
    if not guess:
        return 'по хеш-сумме файла'
    hint = hint or {}
    what = ('TMDb %s' % hint['tmdb']) if hint.get('tmdb') else '«%s»' % (hint.get('title') or guess['title'])
    if guess['type'] == 'episode':
        return '%s, сезон %d, серия %d' % (what, guess['season'], guess['episode'])
    return '%s, %d год' % (what, guess['year'])


def classify(lang, guess, others, hint=None):
    """The reason a search came back empty, in Russian for the panel and in English for the log. `others` = languages found without the filter."""
    q = describe_query(guess, hint)
    if not guess:
        return ('no_guess', 'Не удалось понять по имени файла, что это за серия или фильм (нужно «Название SxxEyy» или «Название год»), '
                'поэтому искал только по хеш-сумме файла, и такого файла в базе нет.', 'file name has no SxxEyy / year, hash-only search found nothing')
    if guess['type'] == 'episode' and guess['episode'] == 0:
        return ('special', 'Серия с номером 0 — спецвыпуск. На OpenSubtitles спецвыпуски лежат в «сезоне 0» под другими номерами, поэтому поиск по 0-й серии пуст.',
                'episode 0 (special): not indexed under that number')
    if others and lang not in others:
        have = ', '.join('%s: %d' % kv for kv in sorted(others.items(), key=lambda kv: -kv[1]))
        return ('other_langs', 'Эта серия в базе есть (%s), но субтитров на языке «%s» никто не загрузил. Остаётся ждать: поиск повторится сам.' % (have, lang),
                'episode exists in %s but not in %s' % (have, lang))
    if others:
        return ('filtered', 'Субтитры на «%s» в базе есть, но все отброшены фильтром (машинный перевод или только иностранная речь).' % lang,
                'results exist but all were filtered out')
    return ('unknown', 'OpenSubtitles не знает такую серию или фильм вообще, ни на одном языке (запрос: %s). Скорее всего, название в базе написано иначе: '
            'задайте своё название для поиска или TMDb id.' % q, 'nothing under any language for this query')


def diagnose(osc, lang, video_hash, guess, hint=None):
    """Runs the language census and returns the record to store."""
    others = {}
    if guess and not (guess['type'] == 'episode' and guess['episode'] == 0):
        try:
            others = osc.languages_found(video_hash, guess, hint)
        except RuntimeError:
            others = {}
    code, ru, en = classify(lang, guess, others, hint)
    return {'at': int(time.time()), 'lang': lang, 'code': code, 'ru': ru, 'en': en, 'query': describe_query(guess, hint), 'others': others,
            'hint': hint or None}


class Hints(jsonstore.Store):
    """Search hints per file or folder, set in the panel. The nearest path wins, field by field, like the language overrides:
    a file-level 'search again' (no title, no id) keeps the TMDb id given for its folder."""

    def lookup(self, rel):
        d, parts, out, at = self.all(), rel.split('/'), {'title': None, 'tmdb': None}, 0
        for n in range(len(parts), 0, -1):
            v = d.get('/'.join(parts[:n]))
            if v:
                at = max(at, v.get('at') or 0)
                for k in out:
                    if out[k] is None and v.get(k) is not None:
                        out[k] = v[k]
        return dict(out, at=at) if at else None

    def set(self, rel, title, tmdb):
        """title / tmdb None = 'search again' without changing how the search is made."""
        key = media.check_rel(rel)
        title = (title or '').strip() or None
        if title and len(title) > 120:
            raise ValueError('title is too long')
        if tmdb is not None and not (isinstance(tmdb, int) and not isinstance(tmdb, bool) and 0 < tmdb < 10 ** 9):
            raise ValueError('bad TMDb id')
        self.update(lambda d: dict(d, **{key: {'title': title, 'tmdb': tmdb, 'at': time.time()}}))

    def remove(self, rel):
        key = media.check_rel(rel)
        self.update(lambda d: {k: v for k, v in d.items() if k != key})
