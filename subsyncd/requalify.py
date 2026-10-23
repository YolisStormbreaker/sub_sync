"""Re-judges the held (pending) candidates with the current gate rules, using the metrics stored with them; no download, no sync.
Those that now pass are approved exactly as the panel's "approve" does (the stored file is copied next to the video, never over an
existing file, text untouched). Dry run unless --apply.
usage: python3 requalify.py STATE_DIR VIDEO_ROOT [--apply]"""
import sys
import os
import quality, review


def rebuild(m):
    """The chain_q dict that assess() reads, from the metrics saved in the item (inliers/windows only matter as a ratio)."""
    mt = m['metrics']
    return {'chain_q': {'acts': mt['acts'], 'windows': 1000, 'inliers': int(round(mt['cover'] * 1000)), 'near': mt['near06'],
                        'resid_med': mt['resid'], 'p': mt['slope']}}


def main(state, root, apply):
    out = {'approved': [], 'kept': [], 'skipped': []}
    for m in review.items(state):
        if m['status'] != 'pending':
            continue
        mt = m.get('metrics') or {}
        if mt.get('mode') != 'chain':
            out['skipped'].append((m['rel'], m['lang'], 'not a chain result'))
            continue
        unconfirmed = any('not confirmed' in r for r in m['reasons'])
        q = quality.assess(rebuild(m), 'review' if unconfirmed else 'ok')
        if q['verdict'] != 'ok':
            out['kept'].append((m['rel'], m['lang'], m['score'], q['reasons'][0] if q['reasons'] else ''))
            continue
        if apply:
            try:
                msg = review.decide(state, root, m['id'], 'approve')
            except ValueError as e:
                out['skipped'].append((m['rel'], m['lang'], str(e))); continue
            quality.record(state, m['rel'], m['lang'], 'requalify', q, 'written', {'id': m['id']})
        else:
            msg = 'would approve'
        out['approved'].append((m['rel'], m['lang'], m['score'], msg))
    for k, rows in out.items():
        print('==', k, len(rows))
        for r in rows:
            print('  ', r[1], r[2] if isinstance(r[2], float) else '', os.path.basename(r[0])[-48:], '|', r[-1][:110])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], '--apply' in sys.argv)
