"""Confidence of a finished sync. A file is 'ok' (written next to the video) or 'review' (held for a person to listen to).
The thresholds are deliberately strict: a held file costs one listen, a wrong subtitle written silently costs trust."""
import json, os, time

# Against the original-language subtitle (chain): share of cue starts within 0.6 s of it, share of windows that agreed with the fit.
CHAIN_NEAR_OK = 0.80
CHAIN_COVER_OK = 0.85
# When the original-language subtitle it was aligned to is itself unconfirmed, a stricter share is required (relaxed 2026-10-20 from
# 'always review' after the user's listening tests: a high chain score meant the subtitles really worked).
CHAIN_NEAR_UNCONFIRMED_REF = 0.90
# Against the audio itself: share of windows that agree with the fit, median residual in seconds.
AUDIO_COVER_OK = 0.75
AUDIO_RESID_OK = 0.40
MAX_ACTS = 8        # more acts than this is a fit chasing noise, not ad breaks
MAX_SLOPE = 0.01    # after ffsubsync a residual drift above 1% is not a frame-rate fix any more


def assess(info, ref_verdict=None, expect_chain=False, no_ref=False):
    """info: the dict returned by engines.sync. ref_verdict: verdict of the original-language subtitle this one was aligned to
    (None for the original language itself). expect_chain: a reference existed but could not be used. no_ref: a second language
    for which no original-language subtitle was available to cross-check against.
    Returns {'verdict': 'ok'|'review', 'score': 0..1, 'reasons': [English], 'reasons_ru': [the same in Russian, for the panel], 'metrics': {...}}."""
    d, cq = info.get('drift'), info.get('chain_q')
    why, m = [], {}
    if cq:
        cover = cq['inliers'] / max(1, cq['windows'])
        m.update(mode='chain', acts=cq['acts'], near06=round(cq['near'], 3), cover=round(cover, 3), resid=round(cq['resid_med'], 2),
                 slope=round(cq['p'], 5))
        score, acts, slope = cq['near'], cq['acts'], cq['p']
        if cq['near'] < CHAIN_NEAR_OK:
            why.append(('only %.0f%% of cue starts are within 0.6 s of the original-language subtitle (need %.0f%%)' % (100 * cq['near'], 100 * CHAIN_NEAR_OK),
                        'только %.0f%% начал реплик в пределах 0,6 с от субтитров оригинала (нужно %.0f%%)' % (100 * cq['near'], 100 * CHAIN_NEAR_OK)))
        if cover < CHAIN_COVER_OK:
            why.append(('only %.0f%% of the windows agree with the act model (need %.0f%%)' % (100 * cover, 100 * CHAIN_COVER_OK),
                        'только %.0f%% окон согласуются с моделью актов (нужно %.0f%%)' % (100 * cover, 100 * CHAIN_COVER_OK)))
        if ref_verdict is not None and ref_verdict != 'ok' and cq['near'] < CHAIN_NEAR_UNCONFIRMED_REF:
            why.append(('the original-language subtitle it is aligned to is itself not confirmed and only %.0f%% of cue starts match it (need %.0f%% then)' % (100 * cq['near'], 100 * CHAIN_NEAR_UNCONFIRMED_REF),
                        'субтитры оригинала, по которым выровнено, сами не подтверждены, а совпадает только %.0f%% начал реплик (в этом случае нужно %.0f%%)' % (100 * cq['near'], 100 * CHAIN_NEAR_UNCONFIRMED_REF)))
    elif d and d.get('ok'):
        cover = d['inliers'] / max(1, d['windows'])
        m.update(mode='audio', acts=len(d['qs']), cover=round(cover, 3), resid=round(d['resid_med'], 2), slope=round(d['p'], 5))
        score, acts, slope = cover, len(d['qs']), d['p']
        if cover < AUDIO_COVER_OK:
            why.append(('only %.0f%% of the audio windows agree with the fit (need %.0f%%)' % (100 * cover, 100 * AUDIO_COVER_OK),
                        'только %.0f%% окон звука согласуются с моделью (нужно %.0f%%)' % (100 * cover, 100 * AUDIO_COVER_OK)))
        if d['resid_med'] > AUDIO_RESID_OK:
            why.append(('median residual against the audio is %.2f s (limit %.2f s)' % (d['resid_med'], AUDIO_RESID_OK),
                        'медианное расхождение со звуком %.2f с (предел %.2f с)' % (d['resid_med'], AUDIO_RESID_OK)))
        if expect_chain:
            why.append(('could not be aligned to the original-language subtitle, checked only against the original audio',
                        'не удалось выровнять по субтитрам оригинала, проверено только по оригинальному звуку'))
        elif no_ref:
            why.append(('no original-language subtitle to cross-check with, checked only against the original audio',
                        'нет субтитров оригинала для сверки, проверено только по оригинальному звуку'))
    else:
        m.update(mode='plain'); score, acts, slope = 0.0, 1, 0.0
        why.append(('no consistent fit against the audio or the original-language subtitle, plain ffsubsync result',
                    'нет согласованной модели ни по звуку, ни по субтитрам оригинала, результат обычного ffsubsync'))
    if acts > MAX_ACTS:
        why.append(('%d acts found (more than %d)' % (acts, MAX_ACTS), 'найдено актов: %d (больше %d)' % (acts, MAX_ACTS)))
    if abs(slope) > MAX_SLOPE:
        why.append(('residual drift %+.4f is larger than a frame-rate fix' % slope, 'остаточный дрейф %+.4f больше, чем у смены частоты кадров' % slope))
    return {'verdict': 'review' if why else 'ok', 'score': round(float(score), 3), 'reasons': [w[0] for w in why],
            'reasons_ru': [w[1] for w in why], 'metrics': m}


def log_path(state_dir):
    return os.path.join(state_dir, 'quality.jsonl')


def record(state_dir, rel, lang, engine, q, action, extra=None):
    """One line per finished file, appended; never rewritten, so it doubles as an audit trail."""
    row = {'ts': int(time.time()), 'rel': rel, 'lang': lang, 'engine': engine, 'verdict': q['verdict'], 'score': q['score'],
           'reasons': q['reasons'], 'reasons_ru': q.get('reasons_ru', []), 'metrics': q['metrics'], 'action': action}
    if extra:
        row.update(extra)
    os.makedirs(state_dir, exist_ok=True)
    with open(log_path(state_dir), 'a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def latest(state_dir, limit=2000):
    """Latest row per (rel, lang), newest first."""
    rows = {}
    try:
        with open(log_path(state_dir)) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                rows[(r['rel'], r['lang'])] = r
    except OSError:
        return []
    return sorted(rows.values(), key=lambda r: -r['ts'])[:limit]
