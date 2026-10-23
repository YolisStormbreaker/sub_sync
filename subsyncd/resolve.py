import os, time
import media


def track_key(video):
    try:
        return '%s|%d' % (video, os.path.getsize(video))
    except OSError:
        return video


def relabel(rel_path, pr, ov):
    """The probe with the audio languages a person has given to tracks of this file (overrides 'tlangs') in place of the file's own tags."""
    o = ov.lookup(rel_path) if ov else None
    tl = (o or {}).get('tlangs')
    if not tl:
        return pr
    return dict(pr, audio=[dict(a, lang=tl.get(str(a['rel']), a['lang'])) for a in pr['audio']])


def _entry(tracks, video, lang, cands=None):
    t = (tracks or {}).get(track_key(video))
    if not t or t.get('lang') != lang:  # a stored result belongs to the language it was computed for
        return None
    if t.get('error') and time.time() - (t.get('at') or 0) > media.RETRY_DAYS * 86400:
        return None  # a failed comparison (ffmpeg error, too few cues) is tried again after a while
    done = sorted(int(k) for k in (t.get('metrics') or {}))
    if cands is not None and done and done != sorted(cands):  # tracks were labelled after the comparison: the result no longer applies
        return None
    return t


def _base(rel_path, video, pr, ov, tm):
    lang, rel, why, conf = media.original_audio(pr['audio'])
    o = ov.lookup(rel_path) if ov else None
    if o and o.get('track') is not None:
        own = ov.source(rel_path, 'track') == rel_path  # chosen for this very file
        inside = o['track'] < len(pr['audio'])
        if own:
            rel, conf, why = o['track'], inside, 'chosen track' if inside else 'chosen track is not in this file'
        elif inside and not conf:  # a folder-wide choice fills in only where the file's own tags cannot tell
            rel, conf, why = o['track'], True, 'chosen track (folder)'
    # 'why' keeps describing the track; where the language came from is told by the override itself, the tags or TMDb
    if o and o.get('lang'):
        lang = o['lang']
    elif lang is None and tm is not None:
        try:
            lang = tm.original_language(media.guess(video)) or None
        except RuntimeError:
            lang = None
    return lang, rel, why, conf


def resolve(rel_path, video, pr, ov, tm, tracks=None):
    """(orig_lang, audio_rel, why, confident). Priority: a person's override, audio tags, TMDb for the language;
    when the tags cannot tell the original track, the stored sync-score detection (tracks) decides, if there is one."""
    lang, rel, why, conf = _base(rel_path, video, pr, ov, tm)
    if not conf and lang:
        t = _entry(tracks, video, lang, media.candidate_tracks(pr['audio']))
        if t:
            if t.get('sure'):
                return lang, t['rel'], 'detected by sync score (margin %.2f)' % t['margin'], True
            return lang, rel, 'track unclear after the sync-score check', False
    return lang, rel, why, conf


def pending_detect(lang, pr, conf, tracks, video):
    """True when the original track is not known yet but can be found by comparing the tracks against a subtitle."""
    return bool(lang) and not conf and tracks is not None and _entry(tracks, video, lang, media.candidate_tracks(pr['audio'])) is None \
        and len(media.candidate_tracks(pr['audio'])) >= 2
