"""<state>/state.db: the service's working state (probe cache, detection results, empty searches, failures, quota, ...)
in SQLite instead of one state.json.

The rest of the code keeps using a plain dict: load() returns a State (a dict that remembers what it was loaded with) and
save() writes only the rows that changed since then, in one transaction. With a library of a few thousand files the old
file was several MB and was rewritten whole on every save; now a save after one item writes a handful of rows.

Layout: one table kv(t, k, v). A top-level key whose value is a dict is a "table": a row ('', name, '{}') marks it, and
each of its entries is a row (name, key, json). Any other top-level value is one row ('', name, json). Values are JSON,
so what comes back is exactly what json.load used to return (dict keys are strings).

Two writers (the service and a one-off run) no longer overwrite each other's whole state: each writes only its own
changes. WAL mode lets the panel read while the service writes.
On first use an existing state.json is imported and renamed to state.json.pre-sqlite (kept as a backup)."""
import json, os, sqlite3

NAME = 'state.db'
TABLE = '{}'  # meta value that marks a top-level dict


class State(dict):
    """The loaded state. _snap maps (t, k) to the JSON text loaded or last saved; None for a read-only partial load."""
    _snap = None


def _enc(v):
    return json.dumps(v, separators=(',', ':'), ensure_ascii=False, sort_keys=True)


def _flat(st):
    out = {}
    for name, val in st.items():
        name = str(name)
        if isinstance(val, dict):
            out[('', name)] = TABLE
            for k, v in val.items():
                out[(name, str(k))] = _enc(v)
        else:
            out[('', name)] = _enc(val)
    return out


def connect(state_dir):
    db = sqlite3.connect(os.path.join(state_dir, NAME), timeout=60, isolation_level=None)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=NORMAL')  # WAL + NORMAL: a power cut can lose the last commits, never corrupt the file
    db.execute('CREATE TABLE IF NOT EXISTS kv (t TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY (t, k)) WITHOUT ROWID')
    return db


def _migrate(db, state_dir):
    """Import state.json once. Runs under BEGIN IMMEDIATE, so two processes starting together import it only once."""
    src = os.path.join(state_dir, 'state.json')
    if not os.path.exists(src):
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('SELECT 1 FROM kv LIMIT 1').fetchone() is None:
            try:
                data = json.load(open(src, encoding='utf-8'))
            except ValueError:
                data = None  # an unreadable state.json is left where it is; the service starts from an empty state
            if isinstance(data, dict):
                db.executemany('INSERT INTO kv (t, k, v) VALUES (?, ?, ?)', [(t, k, v) for (t, k), v in _flat(data).items()])
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
    if db.execute('SELECT 1 FROM kv LIMIT 1').fetchone() is not None and os.path.exists(src):
        os.replace(src, src + '.pre-sqlite')


def load(state_dir, tables=None):
    """The whole state, or only the named top-level keys (read-only: such a partial State cannot be saved)."""
    db = connect(state_dir)
    try:
        _migrate(db, state_dir)
        if tables is None:
            rows = db.execute('SELECT t, k, v FROM kv').fetchall()
        else:
            names = [str(n) for n in tables]
            marks = ','.join('?' * len(names))
            rows = db.execute('SELECT t, k, v FROM kv WHERE (t = \'\' AND k IN (%s)) OR t IN (%s)' % (marks, marks), names + names).fetchall()
    finally:
        db.close()
    # Rebuilt as one JSON text and parsed once: a json.loads per row is several times slower for thousands of rows.
    meta, parts = {}, {}
    for t, k, v in rows:
        if t == '':
            meta[k] = v
        else:
            parts.setdefault(t, []).append(json.dumps(k) + ':' + v)
    text = ','.join(json.dumps(name) + ':' + ('{%s}' % ','.join(parts.get(name, ())) if v == TABLE else v) for name, v in meta.items())
    st = State(json.loads('{' + text + '}'))
    if tables is None:
        st._snap = {(t, k): v for t, k, v in rows}
    return st


def save(state_dir, st):
    """Write what changed since load (or the last save) in one transaction; returns the number of rows written or deleted.
    A plain dict (not loaded from here) replaces the whole state."""
    if isinstance(st, State) and st._snap is None:
        raise ValueError('a partial state was loaded read-only and cannot be saved')
    now = _flat(st)
    db = connect(state_dir)
    try:
        _migrate(db, state_dir)
        snap = st._snap if isinstance(st, State) else {(t, k): v for t, k, v in db.execute('SELECT t, k, v FROM kv')}
        put = [(t, k, v) for (t, k), v in now.items() if snap.get((t, k)) != v]
        gone = [key for key in snap if key not in now]
        if put or gone:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.executemany('INSERT OR REPLACE INTO kv (t, k, v) VALUES (?, ?, ?)', put)
                db.executemany('DELETE FROM kv WHERE t = ? AND k = ?', gone)
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
    finally:
        db.close()
    if isinstance(st, State):
        st._snap = now
    return len(put) + len(gone)


def export(state_dir):
    """The whole state as one dict, for inspection: python3 -c 'import statedb,json;print(json.dumps(statedb.export(".")))'."""
    return dict(load(state_dir))
