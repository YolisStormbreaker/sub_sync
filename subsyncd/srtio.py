"""Timing-only SRT access. The subtitle text is never parsed or re-encoded: the file is handled as bytes
and only the digits of cue timing lines are replaced, so BOM, encoding, line endings, tags and cue numbers survive.
A timing line counts only where a cue starts: at the top of the file, after a blank line or after a cue number. A line of
dialogue that happens to look like '00:01:02,000 --> ...' is text and is left alone."""
import re

TIMING = re.compile(rb'(?m)^((?:\xef\xbb\xbf)?[ \t]*)(\d+):(\d\d):(\d\d)[,.](\d{1,3})([ \t]*-->[ \t]*)(\d+):(\d\d):(\d\d)[,.](\d{1,3})')
_LINE = re.compile(rb'[^\n]*\n?')


def _sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, b'0')) / 1000


def _fmt(t):
    ms = max(0, round(t * 1000))
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return b'%02d:%02d:%02d,%03d' % (h, m, s, ms)


def _bare(line):
    return line.replace(b'\xef\xbb\xbf', b'').strip()


def _cue_lines(raw):
    """Offsets of the lines where a cue's timing may stand: first line, after a blank line, or after a cue number."""
    ok, prev = set(), None
    for m in _LINE.finditer(raw):
        if m.start() == m.end():
            break
        if prev is None or not _bare(prev) or _bare(prev).isdigit():
            ok.add(m.start())
        prev = m.group()
    return ok


def _matches(raw):
    starts = _cue_lines(raw)
    return [m for m in TIMING.finditer(raw) if m.start() in starts]


def parse_times(raw):
    """[(start, end)] in seconds, in file order."""
    return [(_sec(*m.group(2, 3, 4, 5)), _sec(*m.group(7, 8, 9, 10))) for m in _matches(raw)]


def retime(raw, times):
    """Replace every cue timing with times[k]; everything else is copied byte for byte."""
    ms = _matches(raw)
    if len(ms) != len(times):
        raise ValueError('cue count mismatch: %d in file, %d new times' % (len(ms), len(times)))
    out, pos = [], 0
    for m, (s, e) in zip(ms, times):
        out += [raw[pos:m.start()], m.group(1), _fmt(s), m.group(6), _fmt(e)]
        pos = m.end()
    out.append(raw[pos:])
    return b''.join(out)


def strip_times(raw):
    """The file with the digits of all cue timings removed."""
    out, pos = [], 0
    for m in _matches(raw):
        out += [raw[pos:m.start()], m.group(1), b'T', m.group(6), b'T']
        pos = m.end()
    out.append(raw[pos:])
    return b''.join(out)


_STRICT = re.compile(rb'^(?:\xef\xbb\xbf)?[ \t]*\d+:\d\d:\d\d[,.]\d{1,3}[ \t]*-->[ \t]*\d+:\d\d:\d\d[,.]\d{1,3}')


def text_unchanged(before, after):
    """Independent of retime(): the two files have the same lines, and a line may differ only where both versions are a
    timing line standing at a cue start in the original, and only in its leading timestamp pair (whatever follows the pair, such
    as position coordinates, must be byte-identical)."""
    a, b = before.split(b'\n'), after.split(b'\n')
    if len(a) != len(b):
        return False
    starts, off = _cue_lines(before), 0
    for x, y in zip(a, b):
        if x != y:
            mx, my = _STRICT.match(x), _STRICT.match(y)
            if off not in starts or not mx or not my or x[mx.end():] != y[my.end():]:
                return False
        off += len(x) + 1
    return True


def clamp(s, e):
    s = max(0.0, s)
    return s, max(s + 0.001, e)
