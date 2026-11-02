#!/usr/bin/env python3
"""Lichtspiel – eigener Medienserver. Nur Python-Standardbibliothek (+ externes ffmpeg/ffprobe)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import traceback
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402
import scanner  # noqa: E402
import stream  # noqa: E402
import extras  # noqa: E402

VERSION = "0.1.0"
PORT = int(os.environ.get("LS_PORT", "8400"))
WEB = os.path.join(HERE, "web")
COOKIE = "ls_s"
COLORS = ["#e5a00d", "#3fa7d6", "#e4572e", "#59cd90", "#a77dc2", "#f25f8c", "#29bf9f", "#f2a541", "#7d8cc4"]
_fails = {}
ROUTES = []


def route(method, pattern, auth="user"):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, auth, fn))
        return fn
    return deco


# -- Passwörter / Sitzungen --------------------------------------------------
def hash_pw(pw):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"pbkdf2${salt}${h}"


def check_pw(pw, stored):
    if not stored:
        return pw == ""
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex(), h)


def public_user(u):
    return {"id": u["id"], "name": u["name"], "admin": bool(u["admin"]), "color": u["color"],
            "has_pw": bool(u["pw"]), "libs": json.loads(u["libs"]) if u.get("libs") else None}


def user_libs(user):
    libs = db.q("SELECT * FROM libraries ORDER BY pos,id")
    allowed = json.loads(user["libs"]) if user.get("libs") else None
    if allowed is not None and not user["admin"]:
        libs = [l for l in libs if l["id"] in allowed]
    prefs = get_prefs(user["id"])
    order = prefs.get("lib_order") or []
    libs.sort(key=lambda l: (order.index(l["id"]) if l["id"] in order else 999, l["pos"], l["id"]))
    return libs


def lib_ids(user, include_hidden=True):
    libs = user_libs(user)
    if not include_hidden:
        hidden = set(get_prefs(user["id"]).get("lib_hidden") or [])
        libs = [l for l in libs if l["id"] not in hidden]
    return [l["id"] for l in libs]


PREF_DEFAULTS = {"audio_lang": "deu", "sub_lang": "deu", "sub_mode": "forced", "sub_size": 100, "sub_bg": 0,
                 "quality": 0, "autoplay": True, "skip_back": 10, "skip_fwd": 30, "lib_order": [],
                 "lib_hidden": [], "direct": True}


def get_prefs(uid):
    p = dict(PREF_DEFAULTS)
    p.update(db.setting(f"prefs:{uid}") or {})
    return p


# -- Elemente aufbereiten ----------------------------------------------------
def brief(r, uid=None, prog=None):
    d = {"id": r["id"], "kind": r["kind"], "title": r["title"], "year": r.get("year"),
         "rating": r.get("rating"), "season": r.get("season"), "episode": r.get("episode"),
         "has_poster": bool(r.get("poster")), "has_backdrop": bool(r.get("backdrop")),
         "has_thumb": bool(r.get("thumb")), "has_logo": bool(r.get("logo")),
         "duration": r.get("duration") or ((r.get("runtime") or 0) * 60) or None, "added": r.get("added")}
    if r.get("show_title"):
        d["show_title"] = r["show_title"]
    if r["kind"] in ("show", "season") and "total" in r:
        d["total"] = r["total"]
        d["unwatched"] = r["total"] - (r.get("seen") or 0)
    if prog is not None:
        p = prog.get(r["id"])
        if p:
            d["pos"], d["watched"] = p["pos"] or 0, bool(p["watched"])
    if r.get("pos") is not None and "pos" not in d:
        d["pos"], d["watched"] = r["pos"], bool(r.get("watched"))
    return d


def progress_map(uid, ids):
    if not ids:
        return {}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 800):
        part = ids[i:i + 800]
        for r in db.q(f"SELECT item_id,pos,watched FROM progress WHERE user_id=? AND item_id IN "
                      f"({','.join('?' * len(part))})", [uid] + part):
            out[r["item_id"]] = r
    return out


def counts_sql(alias="i"):
    """Spalten total/seen für Serien und Staffeln (Platzhalter: Benutzer-ID)."""
    return (f"(SELECT COUNT(*) FROM items e WHERE e.kind='episode' AND (e.show_id={alias}.id OR e.parent_id={alias}.id)"
            f" AND e.season!=0) AS total, (SELECT COUNT(*) FROM items e JOIN progress p ON p.item_id=e.id AND "
            f"p.user_id=? AND p.watched=1 WHERE e.kind='episode' AND (e.show_id={alias}.id OR e.parent_id={alias}.id)"
            f" AND e.season!=0) AS seen")


def with_show_title(rows):
    sids = {r["show_id"] for r in rows if r.get("show_id")}
    if sids:
        names = {r["id"]: r["title"] for r in db.q(
            f"SELECT id,title FROM items WHERE id IN ({','.join('?' * len(sids))})", list(sids))}
        for r in rows:
            if r.get("show_id"):
                r["show_title"] = names.get(r["show_id"])
    return rows


def can_see(user, item):
    return item and item["lib_id"] in lib_ids(user)


# -- HTTP-Handler -------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Lichtspiel"

    def log_message(self, *a):
        pass

    # Antworten
    def send_json(self, obj, status=200, headers=None):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def body(self):
        if self._body is None:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            self._raw = raw
            try:
                self._body = json.loads(raw) if raw and "json" in (self.headers.get("Content-Type") or "json") \
                    else {}
            except ValueError:
                self._body = {}
        return self._body

    def raw_body(self, limit=20 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("zu groß")
        self._body = {}
        return self.rfile.read(n)

    def ip(self):
        return self.client_address[0]

    def token(self):
        t = self.headers.get("X-Token")
        if t:
            return t
        c = SimpleCookie(self.headers.get("Cookie") or "")
        if COOKIE in c:
            return c[COOKIE].value
        return self.query.get("k", [None])[0]

    def user(self):
        if self._user is False:
            self._user = None
            t = self.token()
            if t:
                s = db.one("SELECT * FROM sessions WHERE token=?", (t,))
                if s:
                    self._user = db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))
                    if self._user and time.time() - (s["seen"] or 0) > 300:
                        db.ex("UPDATE sessions SET seen=? WHERE token=?", (time.time(), t))
                    if self._user:
                        self._user["_client"] = s["client"]
        return self._user

    def handle_any(self):
        self._body = None
        self._user = False
        u = urllib.parse.urlsplit(self.path)
        self.query = urllib.parse.parse_qs(u.query)
        p = urllib.parse.unquote(u.path)
        try:
            if not p.startswith("/api/"):
                return self.static(p)
            for method, rx, auth, fn in ROUTES:
                if method != self.command and not (method == "GET" and self.command == "HEAD"):
                    continue
                m = rx.match(p)
                if not m:
                    continue
                user = self.user()
                if auth != "none" and not user:
                    return self.send_json({"error": "Nicht angemeldet"}, 401)
                if auth == "admin" and not user["admin"]:
                    return self.send_json({"error": "Nur für Administratoren"}, 403)
                return fn(self, *m.groups())
            self.send_json({"error": "Unbekannte Adresse"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:
            traceback.print_exc()
            try:
                self.send_json({"error": str(e)}, 500)
            except OSError:
                pass
        finally:
            # nicht gelesenen Rumpf verwerfen, sonst bricht Keep-Alive
            if self._body is None and self.command in ("POST", "PUT", "DELETE"):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = handle_any

    def static(self, p):
        if p in ("/", "") or not os.path.splitext(p)[1]:
            p = "/index.html"
        fn = os.path.normpath(os.path.join(WEB, p.lstrip("/")))
        if not fn.startswith(WEB + os.sep) or not os.path.isfile(fn):
            return self.send_json({"error": "nicht gefunden"}, 404)
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                 ".json": "application/json"}.get(os.path.splitext(fn)[1], "application/octet-stream")
        with open(fn, "rb") as f:
            b = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)


# -- Anmeldung ---------------------------------------------------------------
@route("GET", "/api/state", "none")
def r_state(h):
    u = h.user()
    setup = not db.val("SELECT COUNT(*) FROM users WHERE admin=1", default=0)
    h.send_json({"setup": setup, "name": db.setting("server_name"), "version": VERSION,
                 "user": public_user(u) if u else None, "prefs": get_prefs(u["id"]) if u else None})


@route("GET", "/api/profiles", "none")
def r_profiles(h):
    h.send_json([{"id": u["id"], "name": u["name"], "color": u["color"], "has_pw": bool(u["pw"])}
                 for u in db.q("SELECT * FROM users ORDER BY id")])


def new_session(h, user):
    t = secrets.token_urlsafe(32)
    client = (h.headers.get("X-Client") or "web")[:40]
    db.ex("INSERT INTO sessions(token,user_id,client,created,seen) VALUES(?,?,?,?,?)",
          (t, user["id"], client, time.time(), time.time()))
    hdr = {"Set-Cookie": f"{COOKIE}={t}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"}
    h.send_json({"ok": True, "token": t, "user": public_user(user)}, headers=hdr)


@route("POST", "/api/setup", "none")
def r_setup(h):
    if db.val("SELECT COUNT(*) FROM users WHERE admin=1", default=0):
        return h.send_json({"error": "Bereits eingerichtet"}, 400)
    b = h.body()
    name, pw = (b.get("name") or "").strip(), b.get("password") or ""
    if not name or len(pw) < 3:
        return h.send_json({"error": "Name und Passwort (mind. 3 Zeichen) nötig"}, 400)
    uid = db.ex("INSERT INTO users(name,pw,admin,color,created) VALUES(?,?,1,?,?)",
                (name, hash_pw(pw), COLORS[0], time.time()))
    new_session(h, db.one("SELECT * FROM users WHERE id=?", (uid,)))


@route("POST", "/api/login", "none")
def r_login(h):
    ip = h.ip()
    now = time.time()
    f = [t for t in _fails.get(ip, []) if now - t < 600]
    if len(f) >= 10:
        return h.send_json({"error": "Zu viele Fehlversuche – bitte 10 Minuten warten"}, 429)
    b = h.body()
    u = db.one("SELECT * FROM users WHERE name=?", ((b.get("name") or "").strip(),))
    if not u or not check_pw(b.get("password") or "", u["pw"]):
        _fails[ip] = f + [now]
        time.sleep(0.5)
        return h.send_json({"error": "Name oder Passwort falsch"}, 401)
    _fails.pop(ip, None)
    new_session(h, u)


@route("POST", "/api/logout")
def r_logout(h):
    db.ex("DELETE FROM sessions WHERE token=?", (h.token(),))
    h.send_json({"ok": True}, headers={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})


@route("GET", "/api/me/prefs")
def r_prefs(h):
    h.send_json(get_prefs(h.user()["id"]))


@route("PUT", "/api/me/prefs")
def r_prefs_put(h):
    uid = h.user()["id"]
    p = db.setting(f"prefs:{uid}") or {}
    for k, v in h.body().items():
        if k in PREF_DEFAULTS:
            p[k] = v
    db.set_setting(f"prefs:{uid}", p)
    h.send_json(get_prefs(uid))


@route("PUT", "/api/me/password")
def r_mypw(h):
    b, u = h.body(), h.user()
    if not check_pw(b.get("old") or "", u["pw"]):
        return h.send_json({"error": "Altes Passwort falsch"}, 400)
    new = b.get("new") or ""
    if new and len(new) < 3:
        return h.send_json({"error": "Mindestens 3 Zeichen"}, 400)
    if not new and u["admin"]:
        return h.send_json({"error": "Administratoren brauchen ein Passwort"}, 400)
    db.ex("UPDATE users SET pw=? WHERE id=?", (hash_pw(new) if new else None, u["id"]))
    h.send_json({"ok": True})


# -- Benutzerverwaltung ---------------------------------------------------------
@route("GET", "/api/users", "admin")
def r_users(h):
    h.send_json([public_user(u) for u in db.q("SELECT * FROM users ORDER BY id")])


@route("POST", "/api/users", "admin")
def r_user_new(h):
    b = h.body()
    name = (b.get("name") or "").strip()
    if not name:
        return h.send_json({"error": "Name fehlt"}, 400)
    if db.one("SELECT 1 FROM users WHERE name=?", (name,)):
        return h.send_json({"error": "Name schon vergeben"}, 400)
    pw = b.get("password") or ""
    if b.get("admin") and len(pw) < 3:
        return h.send_json({"error": "Administratoren brauchen ein Passwort (mind. 3 Zeichen)"}, 400)
    n = db.val("SELECT COUNT(*) FROM users", default=0)
    uid = db.ex("INSERT INTO users(name,pw,admin,color,libs,created) VALUES(?,?,?,?,?,?)",
                (name, hash_pw(pw) if pw else None, 1 if b.get("admin") else 0, COLORS[n % len(COLORS)],
                 json.dumps(b["libs"]) if b.get("libs") is not None else None, time.time()))
    h.send_json(public_user(db.one("SELECT * FROM users WHERE id=?", (uid,))))


@route("PUT", r"/api/users/(\d+)", "admin")
def r_user_put(h, uid):
    uid = int(uid)
    u = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        return h.send_json({"error": "Unbekannt"}, 404)
    b = h.body()
    if "name" in b and b["name"].strip():
        db.ex("UPDATE users SET name=? WHERE id=?", (b["name"].strip(), uid))
    if "admin" in b:
        if not b["admin"] and u["admin"] and db.val("SELECT COUNT(*) FROM users WHERE admin=1") <= 1:
            return h.send_json({"error": "Mindestens ein Administrator muss bleiben"}, 400)
        db.ex("UPDATE users SET admin=? WHERE id=?", (1 if b["admin"] else 0, uid))
    if "password" in b:
        pw = b["password"] or ""
        db.ex("UPDATE users SET pw=? WHERE id=?", (hash_pw(pw) if pw else None, uid))
        db.ex("DELETE FROM sessions WHERE user_id=? AND token!=?", (uid, h.token() or ""))
    if "libs" in b:
        db.ex("UPDATE users SET libs=? WHERE id=?", (json.dumps(b["libs"]) if b["libs"] is not None else None, uid))
    if "color" in b:
        db.ex("UPDATE users SET color=? WHERE id=?", (b["color"], uid))
    h.send_json(public_user(db.one("SELECT * FROM users WHERE id=?", (uid,))))


@route("DELETE", r"/api/users/(\d+)", "admin")
def r_user_del(h, uid):
    uid = int(uid)
    if uid == h.user()["id"]:
        return h.send_json({"error": "Eigenes Konto kann nicht gelöscht werden"}, 400)
    for t in ("users WHERE id", "sessions WHERE user_id", "progress WHERE user_id", "favorites WHERE user_id"):
        db.ex(f"DELETE FROM {t}=?", (uid,))
    db.ex("DELETE FROM settings WHERE key=?", (f"prefs:{uid}",))
    h.send_json({"ok": True})


# -- Server-Einstellungen --------------------------------------------------------
SERVER_KEYS = ["server_name", "transcode_preset", "transcode_crf", "transcode_threads", "played_pct",
               "resume_min_s", "scan_interval_h", "probe_workers", "live_access", "channels_access"]


@route("GET", "/api/settings", "admin")
def r_settings(h):
    h.send_json({k: db.setting(k) for k in SERVER_KEYS})


@route("PUT", "/api/settings", "admin")
def r_settings_put(h):
    for k, v in h.body().items():
        if k in SERVER_KEYS:
            db.set_setting(k, v)
    r_settings(h)


# -- Bibliotheken ----------------------------------------------------------------
@route("GET", "/api/libraries")
def r_libs(h):
    u = h.user()
    out = []
    hidden = set(get_prefs(u["id"]).get("lib_hidden") or [])
    for l in user_libs(u):
        kind = "movie" if l["kind"] == "movie" else "show"
        n = db.val("SELECT COUNT(*) FROM items WHERE lib_id=? AND kind=?", (l["id"], kind), 0)
        out.append({"id": l["id"], "name": l["name"], "kind": l["kind"], "count": n, "hidden": l["id"] in hidden,
                    "paths": json.loads(l["paths"] or "[]") if u["admin"] else None, "scanned": l["scanned"]})
    h.send_json(out)


@route("POST", "/api/libraries", "admin")
def r_lib_new(h):
    b = h.body()
    name, kind = (b.get("name") or "").strip(), b.get("kind")
    paths = [p.rstrip("/") for p in b.get("paths") or [] if p.strip()]
    if not name or kind not in ("movie", "show") or not paths:
        return h.send_json({"error": "Name, Art (Filme/Serien) und mindestens ein Ordner nötig"}, 400)
    for p in paths:
        if not os.path.isdir(p):
            return h.send_json({"error": f"Ordner nicht gefunden: {p}"}, 400)
    pos = db.val("SELECT MAX(pos) FROM libraries", default=0) + 1
    lid = db.ex("INSERT INTO libraries(name,kind,paths,pos) VALUES(?,?,?,?)", (name, kind, json.dumps(paths), pos))
    scanner.scan([lid])
    h.send_json({"id": lid})


@route("PUT", r"/api/libraries/(\d+)", "admin")
def r_lib_put(h, lid):
    b = h.body()
    lid = int(lid)
    if "name" in b:
        db.ex("UPDATE libraries SET name=? WHERE id=?", (b["name"].strip(), lid))
    if "paths" in b:
        paths = [p.rstrip("/") for p in b["paths"] if p.strip()]
        db.ex("UPDATE libraries SET paths=? WHERE id=?", (json.dumps(paths), lid))
        scanner.scan([lid])
    if "pos" in b:
        db.ex("UPDATE libraries SET pos=? WHERE id=?", (int(b["pos"]), lid))
    h.send_json({"ok": True})


@route("DELETE", r"/api/libraries/(\d+)", "admin")
def r_lib_del(h, lid):
    lid = int(lid)
    db.ex("DELETE FROM items WHERE lib_id=?", (lid,))
    db.ex("DELETE FROM libraries WHERE id=?", (lid,))
    h.send_json({"ok": True})


@route("POST", r"/api/scan(?:/(\d+))?", "admin")
def r_scan(h, lid):
    full = bool(h.body().get("full"))
    ok = scanner.scan([int(lid)] if lid else None, full)
    h.send_json({"ok": ok, "running": not ok})


@route("GET", "/api/scan", "admin")
def r_scan_state(h):
    st = dict(scanner.state)
    st["unprobed"] = db.val("SELECT COUNT(*) FROM items WHERE kind IN ('movie','episode') AND probed=0", default=0)
    h.send_json(st)


@route("GET", "/api/dirs", "admin")
def r_dirs(h):
    p = h.query.get("path", ["/"])[0] or "/"
    p = os.path.normpath(p)
    try:
        ds = sorted(e.name for e in os.scandir(p) if e.is_dir() and not e.name.startswith("."))
    except OSError as e:
        return h.send_json({"error": str(e)}, 400)
    h.send_json({"path": p, "parent": os.path.dirname(p) if p != "/" else None, "dirs": ds[:2000]})


# -- Durchsuchen ------------------------------------------------------------------
SORTS = {"title": "i.sort_title COLLATE NOCASE", "year": "i.year DESC, i.sort_title", "added": "i.added DESC",
         "rating": "i.rating DESC NULLS LAST, i.sort_title", "release": "i.aired DESC, i.year DESC"}


@route("GET", r"/api/lib/(\d+)/items")
def r_lib_items(h, lid):
    u = h.user()
    lid = int(lid)
    if lid not in lib_ids(u):
        return h.send_json({"error": "Kein Zugriff"}, 403)
    lib = db.one("SELECT * FROM libraries WHERE id=?", (lid,))
    kind = "movie" if lib["kind"] == "movie" else "show"
    qv = lambda k, d=None: h.query.get(k, [d])[0]
    where, args = ["i.lib_id=?", "i.kind=?"], [lid, kind]
    if qv("genre"):
        where.append("EXISTS (SELECT 1 FROM json_each(i.genres) g WHERE g.value=?)")
        args.append(qv("genre"))
    if qv("q"):
        where.append("(i.title LIKE ? OR i.orig_title LIKE ?)")
        args += [f"%{qv('q')}%"] * 2
    if qv("year"):
        m = re.match(r"(\d{4})(?:-(\d{4}))?$", qv("year"))
        if m:
            where.append("i.year BETWEEN ? AND ?")
            args += [int(m.group(1)), int(m.group(2) or m.group(1))]
    if qv("letter"):
        where.append("i.sort_title LIKE ?")
        args.append(qv("letter").lower() + "%")
    order = SORTS.get(qv("sort", "title"), SORTS["title"])
    if kind == "show" and qv("sort") == "added":
        order = "(SELECT MAX(added) FROM items e WHERE e.show_id=i.id) DESC"
    total = db.val(f"SELECT COUNT(*) FROM items i WHERE {' AND '.join(where)}", args, 0)
    lim, off = min(int(qv("limit", 200)), 1000), int(qv("offset", 0))
    cols = "i.*" + (", " + counts_sql() if kind == "show" else "")
    cargs = [u["id"]] if kind == "show" else []
    rows = db.q(f"SELECT {cols} FROM items i WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
                cargs + args + [lim, off])
    prog = progress_map(u["id"], [r["id"] for r in rows]) if kind == "movie" else None
    items = [brief(r, prog=prog) for r in rows]
    if qv("unwatched") == "1":
        items = [i for i in items if not i.get("watched") and i.get("unwatched", 1) != 0]
    h.send_json({"total": total, "items": items, "kind": kind})


@route("GET", r"/api/lib/(\d+)/genres")
def r_lib_genres(h, lid):
    if int(lid) not in lib_ids(h.user()):
        return h.send_json([], 403)
    rows = db.q("SELECT g.value AS g, COUNT(*) AS n FROM items i, json_each(i.genres) g WHERE i.lib_id=? AND "
                "i.kind IN ('movie','show') GROUP BY g.value ORDER BY g.value", (int(lid),))
    h.send_json(rows)


def continue_rows(u, ids, limit=20):
    if not ids:
        return []
    mins = float(db.setting("resume_min_s") or 60)
    rows = db.q(f"SELECT i.*, p.pos, p.watched, p.updated AS pupd FROM progress p JOIN items i ON i.id=p.item_id "
                f"WHERE p.user_id=? AND p.watched=0 AND p.pos>? AND i.kind IN ('movie','episode') AND i.lib_id IN "
                f"({','.join('?' * len(ids))}) ORDER BY p.updated DESC LIMIT ?", [u["id"], mins] + ids + [limit])
    return with_show_title(rows)


def next_up_rows(u, ids, limit=20, exclude_shows=()):
    if not ids:
        return []
    shows = db.q(f"SELECT i.show_id, MAX(p.updated) AS t FROM progress p JOIN items i ON i.id=p.item_id "
                 f"WHERE p.user_id=? AND i.kind='episode' AND (p.watched=1 OR p.pos>0) AND i.lib_id IN "
                 f"({','.join('?' * len(ids))}) GROUP BY i.show_id ORDER BY t DESC LIMIT 60", [u["id"]] + ids)
    out = []
    for s in shows:
        if s["show_id"] in exclude_shows:
            continue
        last = db.one("SELECT i.season,i.episode FROM progress p JOIN items i ON i.id=p.item_id WHERE p.user_id=? "
                      "AND i.show_id=? AND i.season>0 AND (p.watched=1 OR p.pos>0) ORDER BY p.updated DESC LIMIT 1",
                      (u["id"], s["show_id"]))
        if not last:
            continue
        nxt = db.one("SELECT i.* FROM items i LEFT JOIN progress p ON p.item_id=i.id AND p.user_id=? "
                     "WHERE i.show_id=? AND i.kind='episode' AND i.season>0 AND COALESCE(p.watched,0)=0 AND "
                     "(i.season>? OR (i.season=? AND i.episode>?)) ORDER BY i.season,i.episode LIMIT 1",
                     (u["id"], s["show_id"], last["season"], last["season"], last["episode"]))
        if nxt:
            out.append(nxt)
        if len(out) >= limit:
            break
    return with_show_title(out)


@route("GET", "/api/home")
def r_home(h):
    u = h.user()
    ids = lib_ids(u, include_hidden=False)
    hubs = []
    cont = continue_rows(u, ids)
    if cont:
        hubs.append({"id": "continue", "title": "Weiterschauen", "wide": True, "items": [brief(r) for r in cont]})
    cont_shows = {r["show_id"] for r in cont if r.get("show_id")}
    nu = next_up_rows(u, ids, exclude_shows=cont_shows)
    if nu:
        prog = progress_map(u["id"], [r["id"] for r in nu])
        hubs.append({"id": "nextup", "title": "Nächste Folge", "wide": True, "items": [brief(r, prog=prog) for r in nu]})
    favs = db.q(f"SELECT i.* FROM favorites f JOIN items i ON i.id=f.item_id WHERE f.user_id=? AND i.lib_id IN "
                f"({','.join('?' * len(ids)) or 'NULL'}) ORDER BY f.added DESC LIMIT 30", [u["id"]] + ids)
    if favs:
        hubs.append({"id": "fav", "title": "Favoriten", "items": [brief(r) for r in with_show_title(favs)]})
    for l in [x for x in user_libs(u) if x["id"] in ids]:
        if l["kind"] == "movie":
            rows = db.q("SELECT * FROM items WHERE lib_id=? AND kind='movie' ORDER BY added DESC LIMIT 24", (l["id"],))
            prog = progress_map(u["id"], [r["id"] for r in rows])
            items = [brief(r, prog=prog) for r in rows]
        else:
            rows = db.q("SELECT i.*, " + counts_sql() + " FROM items i JOIN (SELECT show_id, MAX(added) AS t FROM items "
                        "WHERE lib_id=? AND kind='episode' GROUP BY show_id ORDER BY t DESC LIMIT 24) x "
                        "ON x.show_id=i.id ORDER BY x.t DESC", (u["id"], l["id"]))
            items = [brief(r) for r in rows]
        if items:
            hubs.append({"id": f"lib{l['id']}", "lib": l["id"], "title": f"Neu in {l['name']}", "items": items})
    h.send_json({"hubs": hubs})


@route("GET", "/api/search")
def r_search(h):
    u = h.user()
    q = (h.query.get("q", [""])[0] or "").strip()
    ids = lib_ids(u)
    if len(q) < 2 or not ids:
        return h.send_json({"items": [], "people": []})
    ph = ",".join("?" * len(ids))
    rows = db.q(f"SELECT * FROM items WHERE lib_id IN ({ph}) AND kind IN ('movie','show','episode') AND "
                f"(title LIKE ? OR orig_title LIKE ?) ORDER BY CASE kind WHEN 'episode' THEN 1 ELSE 0 END, "
                f"CASE WHEN title LIKE ? THEN 0 ELSE 1 END, sort_title LIMIT 80",
                ids + [f"%{q}%", f"%{q}%", f"{q}%"])
    people = db.q(f"SELECT * FROM items WHERE lib_id IN ({ph}) AND kind IN ('movie','show') AND people LIKE ? "
                  f"ORDER BY year DESC LIMIT 40", ids + [f'%"name": "%{q}%'])
    h.send_json({"items": [brief(r) for r in with_show_title(rows)], "people": [brief(r) for r in people]})


@route("GET", "/api/person")
def r_person(h):
    u = h.user()
    name = h.query.get("name", [""])[0]
    ids = lib_ids(u)
    if not name or not ids:
        return h.send_json({"items": []})
    rows = db.q(f"SELECT * FROM items WHERE lib_id IN ({','.join('?' * len(ids))}) AND kind IN ('movie','show') "
                f"AND people LIKE ? ORDER BY year DESC", ids + [f'%"name": {json.dumps(name, ensure_ascii=False)}%'])
    h.send_json({"name": name, "items": [brief(r) for r in rows]})


def media_summary(it):
    m = json.loads(it.get("media") or "{}")
    return {"video": m.get("video"), "audio": m.get("audio") or [], "subs": m.get("subs") or [],
            "ext_subs": [{"lang": s["lang"], "forced": s.get("forced"), "codec": s.get("codec")}
                         for s in m.get("ext_subs") or []],
            "container": m.get("container"), "bitrate": m.get("bitrate"), "size": it.get("size"),
            "file": os.path.basename(it["path"]) if it.get("path") and it["kind"] in ("movie", "episode") else None}


@route("GET", r"/api/item/(\d+)")
def r_item(h, iid):
    u = h.user()
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(u, it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    d = brief(it)
    d.update(plot=it["plot"], tagline=it["tagline"], genres=json.loads(it["genres"] or "[]"), studio=it["studio"],
             mpaa=it["mpaa"], orig_title=it["orig_title"], aired=it["aired"], lib_id=it["lib_id"],
             people=json.loads(it["people"] or "[]"), parent_id=it["parent_id"], show_id=it["show_id"],
             fav=bool(db.one("SELECT 1 FROM favorites WHERE user_id=? AND item_id=?", (u["id"], it["id"]))))
    if it["kind"] in ("movie", "episode"):
        if not it["probed"]:
            scanner.probe_item(it["id"])
            it = db.one("SELECT * FROM items WHERE id=?", (it["id"],))
            d["duration"] = it["duration"]
        d["media"] = media_summary(it)
        p = db.one("SELECT * FROM progress WHERE user_id=? AND item_id=?", (u["id"], it["id"]))
        d["pos"], d["watched"] = (p["pos"] or 0, bool(p["watched"])) if p else (0, False)
    if it["kind"] == "episode":
        show = db.one("SELECT id,title,genres,mpaa,people FROM items WHERE id=?", (it["show_id"],)) or {}
        d["show_title"] = show.get("title")
        if not d["genres"] and show.get("genres"):
            d["genres"] = json.loads(show["genres"])
        d["mpaa"] = d["mpaa"] or show.get("mpaa")
        if not d["people"] and show.get("people"):
            d["people"] = json.loads(show["people"])
        d["next"] = next_episode(it)
        prev = db.one("SELECT id FROM items WHERE show_id=? AND kind='episode' AND (season<? OR (season=? AND "
                      "episode<?)) ORDER BY season DESC, episode DESC LIMIT 1",
                      (it["show_id"], it["season"], it["season"], it["episode"]))
        d["prev"] = prev["id"] if prev else None
    if it["kind"] == "show":
        rows = db.q("SELECT i.*, " + counts_sql() + " FROM items i WHERE i.parent_id=? AND i.kind='season' "
                    "ORDER BY CASE WHEN i.season=0 THEN 9999 ELSE i.season END", (u["id"], it["id"]))
        for r in rows:  # Specials zählen in ihrer eigenen Staffel
            if r["season"] == 0:
                r["total"] = db.val("SELECT COUNT(*) FROM items WHERE parent_id=?", (r["id"],), 0)
                r["seen"] = db.val("SELECT COUNT(*) FROM items i JOIN progress p ON p.item_id=i.id AND p.user_id=? "
                                   "AND p.watched=1 WHERE i.parent_id=?", (u["id"], r["id"]), 0)
        d["children"] = [brief(r) for r in rows]
        c = db.one("SELECT " + counts_sql() + " FROM items i WHERE i.id=?", (u["id"], it["id"]))
        d["total"], d["unwatched"] = c["total"], c["total"] - c["seen"]
        d["play"] = show_play_target(u, it["id"])
    if it["kind"] == "season":
        show = db.one("SELECT id,title,plot,genres FROM items WHERE id=?", (it["show_id"],)) or {}
        d["show_title"] = show.get("title")
        d["plot"] = d["plot"] or show.get("plot")
        rows = db.q("SELECT * FROM items WHERE parent_id=? AND kind='episode' ORDER BY episode", (it["id"],))
        prog = progress_map(u["id"], [r["id"] for r in rows])
        kids = []
        for r in rows:
            b = brief(r, prog=prog)
            b["plot"] = r["plot"]
            b["aired"] = r["aired"]
            kids.append(b)
        d["children"] = kids
        d["play"] = show_play_target(u, it["show_id"], season_id=it["id"])
    h.send_json(d)


def next_episode(it):
    n = db.one("SELECT id,title,season,episode FROM items WHERE show_id=? AND kind='episode' AND (season>? OR "
               "(season=? AND episode>?)) AND (season>0 OR ?=0) ORDER BY season, episode LIMIT 1",
               (it["show_id"], it["season"], it["season"], it["episode"], it["season"]))
    return n


def show_play_target(u, show_id, season_id=None):
    """Welche Folge „Abspielen“ startet: angefangene, sonst erste ungesehene, sonst erste."""
    cond, args = ("i.parent_id=?", [season_id]) if season_id else ("i.show_id=? AND i.season>0", [show_id])
    r = db.one(f"SELECT i.id,i.season,i.episode,i.title,p.pos FROM items i JOIN progress p ON p.item_id=i.id AND "
               f"p.user_id=? WHERE {cond} AND i.kind='episode' AND p.watched=0 AND p.pos>0 ORDER BY p.updated DESC "
               f"LIMIT 1", [u["id"]] + args)
    if not r:
        r = db.one(f"SELECT i.id,i.season,i.episode,i.title,0 AS pos FROM items i LEFT JOIN progress p ON "
                   f"p.item_id=i.id AND p.user_id=? WHERE {cond} AND i.kind='episode' AND COALESCE(p.watched,0)=0 "
                   f"ORDER BY i.season,i.episode LIMIT 1", [u["id"]] + args)
    if not r:
        r = db.one(f"SELECT i.id,i.season,i.episode,i.title,0 AS pos FROM items i WHERE {cond} AND i.kind='episode' "
                   f"ORDER BY i.season,i.episode LIMIT 1", args)
    return r


# -- Gesehen / Favoriten / Fortschritt --------------------------------------------
def episode_ids(it):
    if it["kind"] == "show":
        return [r["id"] for r in db.q("SELECT id FROM items WHERE show_id=? AND kind='episode'", (it["id"],))]
    if it["kind"] == "season":
        return [r["id"] for r in db.q("SELECT id FROM items WHERE parent_id=? AND kind='episode'", (it["id"],))]
    return [it["id"]]


@route("POST", r"/api/watched/(\d+)")
def r_watched(h, iid):
    u = h.user()
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(u, it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    w = bool(h.body().get("watched", True))
    now = time.time()
    rows = [(u["id"], i, 1 if w else 0, now, now if w else None) for i in episode_ids(it)]
    db.exmany("INSERT INTO progress(user_id,item_id,pos,watched,updated,watched_at,plays) VALUES(?,?,0,?,?,?,0) "
              "ON CONFLICT(user_id,item_id) DO UPDATE SET pos=0, watched=excluded.watched, updated=excluded.updated,"
              " watched_at=excluded.watched_at", rows)
    h.send_json({"ok": True, "watched": w})


@route("POST", r"/api/fav/(\d+)")
def r_fav(h, iid):
    u = h.user()
    on = bool(h.body().get("on", True))
    if on:
        db.ex("INSERT OR IGNORE INTO favorites(user_id,item_id,added) VALUES(?,?,?)", (u["id"], int(iid), time.time()))
    else:
        db.ex("DELETE FROM favorites WHERE user_id=? AND item_id=?", (u["id"], int(iid)))
    h.send_json({"ok": True, "fav": on})


@route("POST", "/api/progress")
def r_progress(h):
    u = h.user()
    b = h.body()
    iid, pos, dur = int(b.get("id") or 0), float(b.get("pos") or 0), float(b.get("dur") or 0)
    it = db.one("SELECT id,lib_id,kind,duration,title,show_id,season,episode FROM items WHERE id=?", (iid,))
    if not can_see(u, it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    dur = dur or it["duration"] or 0
    now = time.time()
    play = db.one("SELECT * FROM plays WHERE id=? AND user_id=?", (int(b.get("play") or 0), u["id"]))
    if b.get("tv"):  # Sendermodus: nur Statistik, kein Fortschritt
        if play:
            add = min(now - (play["last"] or now), 40) if b.get("state", "playing") == "playing" else 0
            db.ex("UPDATE plays SET last=?, seconds=seconds+?, pos=? WHERE id=?", (now, max(0, add), pos, play["id"]))
        return h.send_json({"ok": True})
    pct = float(db.setting("played_pct") or 90)
    done = dur > 0 and pos >= dur * pct / 100
    old = db.one("SELECT * FROM progress WHERE user_id=? AND item_id=?", (u["id"], iid))
    if done:
        new_play = not (old and old["watched"] and play and play.get("mode", "").endswith("*"))
        db.ex("INSERT INTO progress(user_id,item_id,pos,dur,watched,plays,updated,watched_at) VALUES(?,?,0,?,1,1,?,?) "
              "ON CONFLICT(user_id,item_id) DO UPDATE SET pos=0,dur=excluded.dur,watched=1,updated=excluded.updated,"
              "watched_at=excluded.watched_at, plays=plays+?", (u["id"], iid, dur, now, now, 1 if new_play else 0))
        if play and not play["mode"].endswith("*"):
            db.ex("UPDATE plays SET mode=mode||'*' WHERE id=?", (play["id"],))
    else:
        db.ex("INSERT INTO progress(user_id,item_id,pos,dur,watched,plays,updated) VALUES(?,?,?,?,0,0,?) "
              "ON CONFLICT(user_id,item_id) DO UPDATE SET pos=excluded.pos,dur=excluded.dur,watched=0,"
              "updated=excluded.updated", (u["id"], iid, pos, dur, now))
    if play:
        add = min(now - (play["last"] or now), 40) if b.get("state", "playing") == "playing" else 0
        db.ex("UPDATE plays SET last=?, seconds=seconds+?, pos=? WHERE id=?", (now, max(0, add), pos, play["id"]))
    h.send_json({"ok": True, "watched": done})


# -- Wiedergabe --------------------------------------------------------------------
LANG_ALIASES = {"deu": {"deu", "ger", "de", "german", "deutsch"}, "eng": {"eng", "en", "english"},
                "fra": {"fra", "fre", "fr"}, "spa": {"spa", "es"}, "ita": {"ita", "it"}}


def lang_match(a, b):
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return False
    for s in LANG_ALIASES.values():
        if a in s and b in s:
            return True
    return a == b


@route("POST", r"/api/play/(\d+)")
def r_play(h, iid):
    u = h.user()
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(u, it) or it["kind"] not in ("movie", "episode"):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    if not os.path.exists(it["path"]):
        return h.send_json({"error": "Datei nicht erreichbar"}, 410)
    b = h.body()
    prefs = get_prefs(u["id"])
    media = json.loads(it["media"] or "{}")
    if it["probed"] != 1:
        media = scanner.probe_item(it["id"]) or media
        it = db.one("SELECT * FROM items WHERE id=?", (it["id"],))
    auds, subs = media.get("audio") or [], media.get("subs") or []
    audio = b.get("audio")
    if audio is None and auds:
        pref = next((a for a in auds if lang_match(a["lang"], prefs["audio_lang"])), None)
        audio = (pref or next((a for a in auds if a.get("default")), auds[0]))["i"]
    # Untertitel-Auswahl: Liste aller (eingebettet als Text, extern), Bild-Untertitel nur eingebrannt
    sublist = [{"key": f"i{s['i']}", "lang": s["lang"], "title": s["title"], "forced": s["forced"],
                "text": s["text"], "codec": s["codec"]} for s in subs]
    sublist += [{"key": f"e{n}", "lang": s["lang"], "title": "extern", "forced": s.get("forced"), "text": True,
                 "codec": s.get("codec")} for n, s in enumerate(media.get("ext_subs") or [])]
    sub = b.get("sub")
    if sub is None:
        mode_s = prefs["sub_mode"]
        cands = [s for s in sublist if s["text"] and lang_match(s["lang"], prefs["sub_lang"])]
        a_lang = next((a["lang"] for a in auds if a["i"] == audio), "")
        if mode_s == "always":
            sub = next((s["key"] for s in cands if not s["forced"]), cands[0]["key"] if cands else None)
        elif mode_s == "forced":
            sub = next((s["key"] for s in cands if s["forced"]), None)
        elif mode_s == "foreign" and a_lang and not lang_match(a_lang, prefs["audio_lang"]):
            sub = next((s["key"] for s in cands if not s["forced"]), None)
    burn = None
    if sub and sub.startswith("i"):
        s = next((x for x in subs if f"i{x['i']}" == sub), None)
        if s and not s["text"]:
            burn, sub = s["i"], None
    caps = b.get("caps") or {"vc": ["h264"], "ac": ["aac", "mp3"], "ct": ["mp4"]}
    height = int(b.get("height") or prefs.get("quality") or 0) or None
    mode, a = decide(it, media, caps, audio, height, burn) if prefs.get("direct", True) or b.get("height") \
        else ("transcode", None)
    if mode == "transcode" and a is None and auds:
        a = next((x for x in auds if x["i"] == audio), auds[0])
    if b.get("force") in ("remux", "transcode"):
        mode = b["force"] if not (b["force"] == "remux" and mode == "transcode") else mode
    start = b.get("start")
    if start is None:
        p = db.one("SELECT pos,watched FROM progress WHERE user_id=? AND item_id=?", (u["id"], it["id"]))
        start = p["pos"] if p and not p["watched"] and (p["pos"] or 0) > float(db.setting("resume_min_s") or 60) \
            else 0
    now = time.time()
    title = it["title"]
    show = None
    if it["kind"] == "episode":
        show = db.one("SELECT title FROM items WHERE id=?", (it["show_id"],))
        title = f"{show['title'] if show else ''} – S{it['season']:02d}E{it['episode']:02d} – {it['title']}"
    play_id = db.ex("INSERT INTO plays(user_id,item_id,client,mode,started,last,seconds,pos,title,kind) "
                    "VALUES(?,?,?,?,?,?,0,?,?,?)", (u["id"], it["id"], u.get("_client") or "web", mode, now, now,
                                                     start, title, it["kind"]))
    k = h.token() or ""
    if mode == "direct":
        url = f"/api/stream/{it['id']}/file"
    else:
        qs = {"mode": mode, "sid": play_id}
        if a is not None:
            qs["a"] = a["i"]
        if height:
            qs["h"] = height
        if burn is not None:
            qs["burn"] = burn
        qs["ac"] = ",".join(caps.get("ac") or [])
        url = f"/api/stream/{it['id']}/fmp4?" + urllib.parse.urlencode(qs)
    v = media.get("video") or {}
    h.send_json({
        "play": play_id, "id": it["id"], "mode": mode, "url": url, "token": k, "start": start,
        "duration": it["duration"] or media.get("duration") or 0, "kind": it["kind"], "title": it["title"],
        "show_title": show["title"] if show else None, "season": it["season"], "episode": it["episode"],
        "year": it["year"], "audio": auds, "audio_sel": a["i"] if a else None, "subs": sublist, "sub_sel": sub,
        "burn": burn, "video": v, "bitrate": media.get("bitrate"), "size": it["size"],
        "next": next_episode(it) if it["kind"] == "episode" else None,
        "markers": extras.markers(it["id"]),
    })


@route("GET", r"/api/stream/(\d+)/file")
def r_stream_file(h, iid):
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(h.user(), it) or it["kind"] not in ("movie", "episode"):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    stream.send_file(h, it["path"])


@route("GET", r"/api/stream/(\d+)/fmp4")
def r_stream_fmp4(h, iid):
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(h.user(), it) or it["kind"] not in ("movie", "episode"):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    qv = lambda k, d=None: h.query.get(k, [d])[0]
    media = json.loads(it["media"] or "{}")
    auds = media.get("audio") or []
    ai = int(qv("a")) if qv("a") not in (None, "") else (auds[0]["i"] if auds else None)
    acodec = next((x["codec"] for x in auds if x["i"] == ai), None)
    mode = qv("mode") if qv("mode") in ("remux", "transcode") else "transcode"
    cmd = stream.fmp4_cmd(it["path"], float(qv("t") or 0), mode, ai, acodec, (qv("ac") or "aac").split(","),
                          int(qv("h")) if qv("h") else None, qv("burn"), (media.get("video") or {}).get("codec"))
    stream.run_fmp4(h, f"{h.user()['id']}:{qv('sid') or iid}", cmd)


@route("GET", r"/api/sub/(\d+)/([ie]\d+)(?:\.vtt)?")
def r_sub(h, iid, key):
    it = db.one("SELECT * FROM items WHERE id=?", (int(iid),))
    if not can_see(h.user(), it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    fn = stream.subtitle_vtt(it, key)
    if not fn:
        return h.send_json({"error": "Untertitel nicht lesbar"}, 422)
    stream.send_file(h, fn, "text/vtt; charset=utf-8", "private, max-age=86400")


IMG_FIELDS = {"poster": ("poster",), "backdrop": ("backdrop",), "logo": ("logo",), "thumb": ("thumb",)}


@route("GET", r"/api/img/(\d+)/(poster|backdrop|logo|thumb|cover)")
def r_img(h, iid, typ):
    it = db.one("SELECT id,kind,lib_id,parent_id,show_id,poster,backdrop,logo,thumb,path,duration FROM items "
                "WHERE id=?", (int(iid),))
    if not can_see(h.user(), it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    w = h.query.get("w", [None])[0]
    src = None
    chain = [it]
    if it["parent_id"]:
        chain.append(db.one("SELECT * FROM items WHERE id=?", (it["parent_id"],)))
    if it["show_id"] and it["show_id"] != it["parent_id"]:
        chain.append(db.one("SELECT * FROM items WHERE id=?", (it["show_id"],)))
    chain = [c for c in chain if c]
    if typ == "cover":  # Hochformat: Folge -> Staffel -> Serie
        src = next((c["poster"] for c in chain if c["poster"]), None)
    elif typ == "thumb":
        src = it["thumb"] or it["backdrop"]
        if not src and it["kind"] == "episode":
            src = stream.snapshot(it["path"], max(30, (it["duration"] or 600) * 0.2))
        src = src or next((c["backdrop"] for c in chain if c["backdrop"]), None)
    elif typ == "poster":
        src = it["poster"] or (next((c["poster"] for c in chain[1:] if c["poster"]), None)
                               if it["kind"] == "season" else None)
    elif typ == "logo":
        src = next((c["logo"] for c in chain if c["logo"]), None)
    else:
        src = next((c["backdrop"] for c in chain if c["backdrop"]), None)
    fn = stream.image(src, w)
    if not fn:
        return h.send_json({"error": "kein Bild"}, 404)
    stream.send_file(h, fn, cache="private, max-age=604800")


@route("GET", r"/api/actor")
def r_actor(h):
    """Darstellerbild aus .actors im Medienordner (Kodi-Konvention)."""
    it = db.one("SELECT * FROM items WHERE id=?", (int(h.query.get("id", ["0"])[0]),))
    if not can_see(h.user(), it):
        return h.send_json({"error": "Nicht gefunden"}, 404)
    name = h.query.get("name", [""])[0].replace(" ", "_")
    d = it["dir"] if it["kind"] != "show" else it["path"]
    for base in (d, os.path.dirname(d or "")):
        for ext in (".jpg", ".png"):
            fn = os.path.join(base or "", ".actors", name + ext)
            if os.path.isfile(fn):
                return stream.send_file(h, stream.image(fn, h.query.get("w", [200])[0]),
                                        cache="private, max-age=604800")
    h.send_json({"error": "kein Bild"}, 404)


# -- Start --------------------------------------------------------------------------
def main():
    db.init()
    db.ex("DELETE FROM sessions WHERE seen < ?", (time.time() - 365 * 86400,))
    extras.init(route, H)
    scanner.prober.kick()
    scanner.scheduler()
    scanner.resume_open_scans()
    threading.Thread(target=stream.cleanup_loop, daemon=True).start()
    stream.warm_images()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    srv.daemon_threads = True
    print(f"Lichtspiel {VERSION} auf Port {PORT}, Daten in {db.DATA}", flush=True)
    srv.serve_forever()


decide = stream.decide

if __name__ == "__main__":
    main()
