"""Per-file / per-folder choices made in the web page: original language and (optionally) which audio track is the original.
Stored as {"TVshows/Doctor Who": {"lang": "en", "track": null}, ...}; the longest matching path wins."""
import media
from jsonstore import Store


KEEP = object()  # set(): leave the stored track languages as they are


def clean_tlangs(tl):
    """{'1': 'en', ...}: the language a person gave to audio tracks of one file ('' / None removes a label)."""
    if not tl:
        return None
    if not isinstance(tl, dict):
        raise ValueError('bad track languages')
    out = {}
    for k, v in tl.items():
        if not str(k).isdigit() or not 0 <= int(k) < 16:
            raise ValueError('bad track')
        if v:
            if v not in media.LANGS:
                raise ValueError('unknown language')
            out[str(int(k))] = v
    return out or None


class Overrides(Store):
    KEEP = KEEP

    def lookup(self, rel):
        """Language and track choices that apply to `rel`: each field comes from the nearest path that sets it, so a track chosen for one
        file does not hide the language chosen for its folder. None when nothing applies."""
        d, parts, out = self.all(), rel.split('/'), {'lang': None, 'track': None, 'tlangs': None}
        for n in range(len(parts), 0, -1):
            v = d.get('/'.join(parts[:n]))
            for k in out:
                if v and out[k] is None and v.get(k) is not None:
                    out[k] = v[k]
        if out['tlangs'] is None:
            del out['tlangs']  # kept out of the answer when nobody labelled tracks
        return out if any(x is not None for x in out.values()) else None

    def source(self, rel, field):
        """The path whose entry supplies `field` ('lang' or 'track') for `rel`, or None."""
        d, parts = self.all(), rel.split('/')
        for n in range(len(parts), 0, -1):
            v = d.get('/'.join(parts[:n]))
            if v and v.get(field) is not None:
                return '/'.join(parts[:n])
        return None

    def set(self, rel, lang, track, tlangs=KEEP):
        key = media.check_rel(rel)
        if lang is not None and lang not in media.LANGS:
            raise ValueError('unknown language')
        if track is not None and not (isinstance(track, int) and not isinstance(track, bool) and 0 <= track < 16):
            raise ValueError('bad track')
        new_tl = None if tlangs is KEEP else clean_tlangs(tlangs)

        def change(d):
            tl = (d.get(key) or {}).get('tlangs') if tlangs is KEEP else new_tl
            if lang is None and track is None and not tl:
                d.pop(key, None)
            else:
                d[key] = {'lang': lang, 'track': track}
                if tl:
                    d[key]['tlangs'] = tl
            return d
        self.update(change)
