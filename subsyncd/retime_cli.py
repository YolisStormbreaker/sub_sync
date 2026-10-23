"""retime_cli.py RAW ENGINE_OUT OUT [--head N] [--label TEXT]
Takes the cue times from ENGINE_OUT (index-aligned, first N raw cues missing from it) and writes them into the
untouched text of RAW. The missing head cues keep the shift of the first surviving cue, clamped at 0."""
import sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from srtio import parse_times, retime, strip_times, clamp
a = sys.argv[1:]
raw_p, eng_p, out_p = a[0], a[1], a[2]
head = int(a[a.index('--head') + 1]) if '--head' in a else 0
label = a[a.index('--label') + 1] if '--label' in a else None
raw = open(raw_p, 'rb').read(); eng = parse_times(open(eng_p, 'rb').read()); rt = parse_times(raw)
if len(eng) + head != len(rt):
    sys.exit('cue count: raw %d, engine %d, head %d' % (len(rt), len(eng), head))
shift = eng[0][0] - rt[head][0]
new = [clamp(rt[k][0] + shift, rt[k][1] + shift) for k in range(head)] + [clamp(*t) for t in eng]
out = retime(raw, new)
assert strip_times(out) == strip_times(raw), 'text changed'
assert all(new[i][0] <= new[i + 1][0] + 1e-9 for i in range(len(new) - 1)), 'cues out of order'
if label:
    nl = b'\r\n' if b'\r\n' in raw else b'\n'
    out = b'0' + nl + b'00:00:00,100 --> 00:00:04,000' + nl + label.encode() + nl + nl + out
open(out_p, 'wb').write(out)
print('ok', out_p.split('/')[-1], 'cues', len(new), 'head shift %+.2f' % shift, 'clamped', sum(1 for i in range(head) if new[i][1] - new[i][0] < 0.01))
