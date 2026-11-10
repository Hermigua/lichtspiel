"""Radio: selbst eingetragene Sender (von Hand oder als M3U/M3U8/PLS-Liste). Kein Online-Verzeichnis.

Der Browser bekommt den Ton immer als MP3 über den Server (ffmpeg als eigenständiges Programm) – so laufen auch
HLS-Sender überall. „Läuft gerade“ liest der Server selbst aus den ICY-Metadaten des Streams.
"""
import os
import re
import subprocess
import threading
import time
import urllib.request

import db
import live
import stream

SCHEMA = """
CREATE TABLE IF NOT EXISTS radio (id INTEGER PRIMARY KEY, name TEXT, url TEXT, logo TEXT, grp TEXT,
  pos INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1, added REAL);
"""
UA = "Lichtspiel/0.2"
_now = {}            # Sender-ID -> (Zeit, Titel)


def allowed(user):
    acc = db.setting("radio_access")
    return bool(user["admin"] or acc is None or user["id"] in (acc or []))


def pub(r):
    return {"id": r["id"], "name": r["name"], "group": r["grp"] or "", "has_logo": bool(r["logo"]),
            "enabled": bool(r["enabled"])}


def parse_list(text):
    """M3U/M3U8 (mit #EXTINF und tvg-logo/group-title), PLS oder einfache Adressliste → [(Name, Adresse, Logo, Gruppe)]"""
    out = []
    if "[playlist]" in text[:200].lower():           # PLS
        f, t = {}, {}
        for ln in text.splitlines():
            m = re.match(r"\s*(File|Title)(\d+)\s*=\s*(.*)", ln, re.I)
            if m:
                (f if m[1].lower() == "file" else t)[m[2]] = m[3].strip()
        for k in sorted(f, key=lambda x: int(x)):
            out.append((t.get(k) or f[k], f[k], "", ""))
        return out
    name, logo, grp = None, "", ""
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.upper().startswith("#EXTINF"):
            a = dict(live.ATTR.findall(ln))
            name, logo, grp = ln.rsplit(",", 1)[-1].strip() or None, a.get("tvg-logo", ""), a.get("group-title", "")
        elif ln and not ln.startswith("#") and re.match(r"https?://", ln):
            out.append((name or ln.split("/")[2], ln, logo, grp))
            name, logo, grp = None, "", ""
    return out


def now_playing(r):
    """Titel aus den ICY-Metadaten (höchstens alle 20 s neu gelesen)."""
    t, title = _now.get(r["id"], (0, None))
    if time.time() - t < 20:
        return title
    title = None
    try:
        req = urllib.request.Request(r["url"], headers={"User-Agent": UA, "Icy-MetaData": "1"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            mi = int(resp.headers.get("icy-metaint") or 0)
            if mi and mi < 256 * 1024:
                resp.read(mi)
                n = resp.read(1)
                if n:
                    meta = resp.read(n[0] * 16).decode("utf-8", "replace")
                    m = re.search(r"StreamTitle='(.*?)';", meta)
                    title = (m[1].strip() if m else None) or None
    except Exception:
        title = None
    _now[r["id"]] = (time.time(), title)
    return title


def logo_file(r):
    if not r["logo"]:
        return None
    if r["logo"].startswith("/"):
        return r["logo"] if os.path.exists(r["logo"]) else None
    return live.logo_file({"logo": r["logo"]})


def init(route, H):
    with db._lock:
        db.conn().executescript(SCHEMA)
        db.conn().commit()

    @route("GET", "/api/radio")
    def r_list(h):
        u = h.user()
        if not allowed(u):
            return h.send_json([])
        rows = db.q("SELECT * FROM radio " + ("" if u["admin"] else "WHERE enabled=1 ") + "ORDER BY pos, id")
        h.send_json([pub(r) for r in rows])

    @route("GET", r"/api/radio/(\d+)/now")
    def r_now(h, rid):
        r = db.one("SELECT * FROM radio WHERE id=?", (int(rid),))
        if not r or not allowed(h.user()):
            return h.send_json({"error": "Nicht gefunden"}, 404)
        h.send_json({"title": now_playing(r)})

    @route("GET", r"/api/radio/(\d+)/logo")
    def r_logo(h, rid):
        r = db.one("SELECT * FROM radio WHERE id=?", (int(rid),))
        fn = logo_file(r) if r else None
        if not fn:
            return h.send_json({"error": "kein Logo"}, 404)
        stream.send_file(h, fn, cache="private, max-age=86400")

    @route("GET", r"/api/radio/(\d+)/url")
    def r_url(h, rid):
        """Original-Adresse (für die TV-App, die Streams selbst abspielt)."""
        r = db.one("SELECT url FROM radio WHERE id=?", (int(rid),))
        if not r or not allowed(h.user()):
            return h.send_json({"error": "Nicht gefunden"}, 404)
        h.send_json({"url": r["url"]})

    @route("GET", r"/api/radio/(\d+)/stream")
    def r_stream(h, rid):
        u = h.user()
        r = db.one("SELECT * FROM radio WHERE id=?", (int(rid),))
        if not r or not allowed(u):
            return h.send_json({"error": "Nicht gefunden"}, 404)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-user_agent", UA,
               "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
               "-i", r["url"], "-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "pipe:1"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, bufsize=0)
        first = p.stdout.read(16 * 1024)
        if not first:
            p.kill()
            return h.send_json({"error": "Sender nicht erreichbar"}, 502)
        h.close_connection = True
        h.send_response(200)
        h.send_header("Content-Type", "audio/mpeg")
        h.send_header("Cache-Control", "no-store")
        h.send_header("Connection", "close")
        h.end_headers()
        try:
            h.wfile.write(first)
            while True:
                b = p.stdout.read(32 * 1024)
                if not b:
                    break
                h.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            if p.poll() is None:
                p.kill()

    # -- Verwaltung ---------------------------------------------------------------
    @route("POST", "/api/radio", "admin")
    def r_add(h):
        b = h.body()
        name, url = (b.get("name") or "").strip(), (b.get("url") or "").strip()
        if not re.match(r"https?://", url):
            return h.send_json({"error": "Adresse muss mit http:// oder https:// beginnen"}, 400)
        rid = db.ex("INSERT INTO radio(name,url,logo,grp,pos,added) VALUES(?,?,?,?,?,?)",
                    (name or url.split("/")[2], url, (b.get("logo") or "").strip(), (b.get("group") or "").strip(),
                     (db.one("SELECT MAX(pos) AS m FROM radio") or {}).get("m") or 0, time.time()))
        h.send_json({"id": rid})

    @route("POST", "/api/radio/import", "admin")
    def r_import(h):
        """Liste (M3U/M3U8/PLS) als Datei-Inhalt oder Adresse übernehmen."""
        b = h.body()
        text = b.get("text") or ""
        if not text and b.get("url"):
            try:
                text = live.fetch(b["url"], 5 * 1024 * 1024).decode("utf-8", "replace")
            except Exception as e:
                return h.send_json({"error": f"Liste nicht ladbar: {e}"}, 400)
        rows = parse_list(text)
        have = {r["url"] for r in db.q("SELECT url FROM radio")}
        pos = (db.one("SELECT MAX(pos) AS m FROM radio") or {}).get("m") or 0
        n = 0
        for name, url, logo, grp in rows:
            if url in have:
                continue
            pos += 1
            n += 1
            db.ex("INSERT INTO radio(name,url,logo,grp,pos,added) VALUES(?,?,?,?,?,?)", (name, url, logo, grp, pos, time.time()))
        h.send_json({"added": n, "found": len(rows)})

    @route("PUT", r"/api/radio/(\d+)", "admin")
    def r_put(h, rid):
        b = h.body()
        for k, col in (("name", "name"), ("url", "url"), ("logo", "logo"), ("group", "grp"), ("enabled", "enabled"), ("pos", "pos")):
            if k in b:
                db.ex(f"UPDATE radio SET {col}=? WHERE id=?", (b[k], int(rid)))
        _now.pop(int(rid), None)
        h.send_json({"ok": True})

    @route("DELETE", r"/api/radio/(\d+)", "admin")
    def r_del(h, rid):
        db.ex("DELETE FROM radio WHERE id=?", (int(rid),))
        h.send_json({"ok": True})

    @route("GET", "/api/radio/admin", "admin")
    def r_admin(h):
        rows = db.q("SELECT * FROM radio ORDER BY pos, id")
        h.send_json({"stations": [dict(pub(r), url=r["url"], logo=r["logo"] or "") for r in rows],
                     "access": db.setting("radio_access")})

    @route("PUT", "/api/radio/access", "admin")
    def r_access(h):
        db.set_setting("radio_access", h.body().get("users"))
        h.send_json({"ok": True})
