"""Small JSON documents written by more than one party (the panel's threads, the daemon, the CLI, one-off scripts).
Every change is a read-modify-write under an exclusive flock on '<file>.lock', written to a unique temp file, fsynced and renamed
into place. A file that cannot be parsed is never overwritten: a change raises, and readers keep the last copy they parsed."""
import contextlib, fcntl, json, os, tempfile


class Corrupt(ValueError):
    pass


def read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise Corrupt('%s cannot be parsed (%s); fix or remove it by hand' % (path, e))


@contextlib.contextmanager
def locked(path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path + '.lock', 'a') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def write(path, d, indent=1):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', prefix='.' + os.path.basename(path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(d, f, ensure_ascii=False, indent=indent, separators=None if indent else (',', ':')); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def update(path, fn):
    """fn(current dict) -> new dict, applied under the lock. Returns the new dict."""
    with locked(path):
        new = fn(read(path))
        write(path, new)
        return new


class Store:
    """Cached reader of one document (reloaded when the file changes) plus locked updates."""
    def __init__(self, path):
        self.path, self._sig, self._d = path, None, {}

    def all(self):
        try:
            s = os.stat(self.path); sig = (s.st_ino, s.st_mtime_ns, s.st_size)
        except OSError:
            self._sig, self._d = None, {}
            return self._d
        if sig != self._sig:
            try:
                self._d, self._sig = read(self.path), sig
            except Corrupt:
                pass  # keep serving the last good copy; the next update raises instead of wiping the file
        return self._d

    def update(self, fn):
        new = update(self.path, fn)
        self._d, self._sig = new, None  # the next read re-checks the file; until then (or if it gets damaged) this copy is served
        return new
