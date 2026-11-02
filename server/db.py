"""Lichtspiel – Datenbank (SQLite, nur Python-Standardbibliothek)."""
import json
import os
import sqlite3
import threading
import time

DATA = os.environ.get("LS_DATA", "/var/lib/lichtspiel")
_local = threading.local()
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, pw TEXT, admin INTEGER DEFAULT 0,
  color TEXT, libs TEXT, created REAL);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id INTEGER, client TEXT, created REAL, seen REAL);
CREATE TABLE IF NOT EXISTS libraries (
  id INTEGER PRIMARY KEY, name TEXT, kind TEXT, paths TEXT, pos INTEGER DEFAULT 0,
  scanned REAL, scan_state TEXT);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, lib_id INTEGER, kind TEXT, parent_id INTEGER, show_id INTEGER,
  title TEXT, sort_title TEXT, orig_title TEXT, year INTEGER, plot TEXT, tagline TEXT,
  genres TEXT, studio TEXT, mpaa TEXT, rating REAL, runtime INTEGER,
  season INTEGER, episode INTEGER, aired TEXT, people TEXT,
  path TEXT UNIQUE, dir TEXT, size INTEGER, mtime REAL, nfo_mtime REAL,
  duration REAL, media TEXT, probed INTEGER DEFAULT 0,
  poster TEXT, backdrop TEXT, logo TEXT, thumb TEXT,
  added REAL, updated REAL, missing INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS i_items_lib ON items(lib_id, kind);
CREATE INDEX IF NOT EXISTS i_items_parent ON items(parent_id);
CREATE INDEX IF NOT EXISTS i_items_show ON items(show_id);
CREATE INDEX IF NOT EXISTS i_items_added ON items(added);
CREATE TABLE IF NOT EXISTS progress (
  user_id INTEGER, item_id INTEGER, pos REAL, dur REAL, watched INTEGER DEFAULT 0,
  plays INTEGER DEFAULT 0, updated REAL, watched_at REAL, PRIMARY KEY(user_id, item_id));
CREATE TABLE IF NOT EXISTS plays (
  id INTEGER PRIMARY KEY, user_id INTEGER, item_id INTEGER, client TEXT, mode TEXT,
  started REAL, last REAL, seconds REAL DEFAULT 0, pos REAL, title TEXT, kind TEXT);
CREATE INDEX IF NOT EXISTS i_plays_user ON plays(user_id, started);
CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, item_id INTEGER, added REAL,
  PRIMARY KEY(user_id, item_id));
"""


def path(*p):
    return os.path.join(DATA, *p)


def conn():
    c = getattr(_local, "c", None)
    if c is None:
        os.makedirs(DATA, mode=0o700, exist_ok=True)
        c = sqlite3.connect(path("lichtspiel.db"), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA foreign_keys=OFF")
        _local.c = c
    return c


def init():
    with _lock:
        c = conn()
        c.executescript(SCHEMA)
        c.commit()
    try:
        os.chmod(path("lichtspiel.db"), 0o600)
    except OSError:
        pass


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def val(sql, args=(), default=None):
    r = conn().execute(sql, args).fetchone()
    return r[0] if r and r[0] is not None else default


def ex(sql, args=()):
    with _lock:
        c = conn()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def exmany(sql, rows):
    with _lock:
        c = conn()
        c.executemany(sql, rows)
        c.commit()


DEFAULTS = {
    "server_name": "Lichtspiel",
    "transcode_preset": "veryfast",
    "transcode_crf": 21,
    "transcode_threads": 0,
    "played_pct": 90,
    "resume_min_s": 60,
    "scan_interval_h": 6,
    "probe_workers": 2,
}


def setting(key, default=None):
    v = val("SELECT value FROM settings WHERE key=?", (key,))
    if v is None:
        return DEFAULTS.get(key, default)
    try:
        return json.loads(v)
    except ValueError:
        return v


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, json.dumps(value)))


def now():
    return time.time()
