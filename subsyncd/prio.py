"""Priorities per folder or file for the three stages of the pipeline. 1 = first ... 9 = last, 0 = paused (the stage skips it).
  scan      probing the file and finding the original audio track (the slow, audio-reading part of discovery)
  download  fetching the subtitle from OpenSubtitles (spends the daily quota)
  sync      extracting the audio and aligning the subtitle (spends CPU)
Stored as {"TVshows/Doctor Who": {"download": 1}, "TVshows/Doctor Who/S01/a.mkv": {"sync": 9}}; for each stage the longest
matching path wins, so one file can override its folder in one stage and inherit the others. Without a setting the default is
the class of the top-level folder: TVshows 1, Anime 2, Animation and Movies 3."""
import media
from jsonstore import Store

STAGES = ('scan', 'download', 'sync')
DEFAULT = {'TVshows': 1, 'Anime': 2, 'Animation': 3, 'Movies': 3}


class Priorities(Store):

    def explicit(self, rel, stage):
        """(value, path it came from) or (None, None)."""
        d, parts = self.all(), rel.split('/')
        for n in range(len(parts), 0, -1):
            v = (d.get('/'.join(parts[:n])) or {}).get(stage)
            if isinstance(v, int):
                return v, '/'.join(parts[:n])
        return None, None

    def get(self, rel, stage):
        v, _ = self.explicit(rel, stage)
        return v if v is not None else DEFAULT.get(rel.split('/')[0], 9)

    def set(self, rel, values):
        """values: {stage: int 0..9 or None to clear the stage}."""
        key = media.check_rel(rel)
        for st, v in values.items():
            if st not in STAGES:
                raise ValueError('unknown stage')
            if v is not None and not (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 9):
                raise ValueError('priority must be 0..9')

        def change(d):
            cur = dict(d.get(key) or {})
            for st, v in values.items():
                if v is None:
                    cur.pop(st, None)
                else:
                    cur[st] = v
            if cur:
                d[key] = cur
            else:
                d.pop(key, None)
            return d
        self.update(change)
