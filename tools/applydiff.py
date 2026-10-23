import sys
def apply(path, dpath):
    src = open(path).read(); hunks = []; cur = None
    for ln in open(dpath).read().split('\n'):
        if ln.startswith('@@'):
            cur = ([], []); hunks.append(cur)
        elif cur is not None and ln and ln[0] in ' -+':
            if ln[0] in ' -': cur[0].append(ln[1:])
            if ln[0] in ' +': cur[1].append(ln[1:])
    for old, new in hunks:
        o = '\n'.join(old) + '\n'; assert src.count(o) == 1, (path, o[:60], src.count(o))
        src = src.replace(o, '\n'.join(new) + '\n')
    open(path, 'w').write(src)
apply(sys.argv[1], sys.argv[2])
