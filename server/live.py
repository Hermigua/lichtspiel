"""Live-TV aus eigenen Senderlisten (M3U/M3U8) mit Programmführer (XMLTV)."""
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import db
import stream

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_sources (id INTEGER PRIMARY KEY, name TEXT, m3u_url TEXT, xmltv_url TEXT,
  enabled INTEGER DEFAULT 1, updated REAL, msg TEXT);
CREATE TABLE IF NOT EXISTS live_channels (id INTEGER PRIMARY KEY, source_id INTEGER, key TEXT, tvg_id TEXT, name TEXT,
  number INTEGER, logo TEXT, url TEXT, grp TEXT, ua TEXT, enabled INTEGER DEFAULT 1, pos INTEGER,
  UNIQUE(source_id, key));
CREATE TABLE IF NOT EXISTS epg (chan TEXT, start REAL, stop REAL, title TEXT, sub TEXT, descr TEXT,
  PRIMARY KEY(chan, start));
CREATE INDEX IF NOT EXISTS i_epg_stop ON epg(stop);
"""
UA = "Lichtspiel/0.1"
_refresh_lock = threading.Lock()


def fetch(url, limit=200 * 1024 * 1024):
    if url.startswith("file:"):
        with open(url[5:], "rb") as f:
            raw = f.read(limit)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(limit)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text):
    out, cur, ua = [], None, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            head, _, name = line.partition(",")
            a = dict(ATTR.findall(head))
            cur = {"name": name.strip() or a.get("tvg-name") or "Sender", "tvg_id": a.get("tvg-id") or "",
                   "logo": a.get("tvg-logo") or "", "grp": a.get("group-title") or "",
                   "number": int(a["tvg-chno"]) if a.get("tvg-chno", "").isdigit() else None}
            ua = None
        elif line.startswith("#EXTVLCOPT:http-user-agent="):
            ua = line.split("=", 1)[1]
        elif line.startswith("#"):
            continue
        elif cur is not None:
            cur["url"], cur["ua"] = line, ua
            out.append(cur)
            cur = None
    return out


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("hd", ""))


def xmltv_time(s):
    s = (s or "").strip()
    try:
        if " " in s:
            return datetime.strptime(s, "%Y%m%d%H%M%S %z").timestamp()
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S").timestamp()
    except ValueError:
        return None


def refresh(source_id=None):
    with _refresh_lock:
        for src in db.q("SELECT * FROM live_sources" + (" WHERE id=?" if source_id else " WHERE enabled=1"),
                        (source_id,) if source_id else ()):
            msg = []
            try:
                url = src["m3u_url"] or ""
                if url:
                    chans = parse_m3u(fetch(url).decode("utf-8", "replace"))
                    keys = set()
                    old = {r["key"]: r for r in db.q("SELECT * FROM live_channels WHERE source_id=?", (src["id"],))}
                    for n, c in enumerate(chans):
                        key = c["tvg_id"] or norm(c["name"]) or c["url"]
                        if key in keys:
                            key = f"{key}#{n}"
                        keys.add(key)
                        if key in old:
                            db.ex("UPDATE live_channels SET name=?,tvg_id=?,logo=?,url=?,grp=?,ua=? WHERE id=?",
                                  (c["name"], c["tvg_id"], c["logo"], c["url"], c["grp"], c["ua"], old[key]["id"]))
                        else:
                            db.ex("INSERT INTO live_channels(source_id,key,tvg_id,name,number,logo,url,grp,ua,enabled,pos)"
                                  " VALUES(?,?,?,?,?,?,?,?,?,1,?)", (src["id"], key, c["tvg_id"], c["name"], c["number"],
                                                                     c["logo"], c["url"], c["grp"], c["ua"], n))
                    for k, r in old.items():
                        if k not in keys:
                            db.ex("DELETE FROM live_channels WHERE id=?", (r["id"],))
                    msg.append(f"{len(chans)} Sender")
                if src["xmltv_url"]:
                    msg.append(f"{load_xmltv(src)} Sendungen")
            except Exception as e:
                msg.append("Fehler: " + str(e)[:200])
            db.ex("UPDATE live_sources SET updated=?, msg=? WHERE id=?", (time.time(), ", ".join(msg), src["id"]))
        db.ex("DELETE FROM epg WHERE stop < ?", (time.time() - 6 * 3600,))


def load_xmltv(src):
    raw = fetch(src["xmltv_url"])
    chans = db.q("SELECT id,tvg_id,name FROM live_channels WHERE source_id=?", (src["id"],))
    by_id = {}
    for c in chans:
        if c["tvg_id"]:
            by_id.setdefault(c["tvg_id"].lower(), []).append(c["id"])
    by_name = {}
    for c in chans:
        by_name.setdefault(norm(c["name"]), []).append(c["id"])
    xml_map = {}
    rows = []
    lo, hi = time.time() - 6 * 3600, time.time() + 8 * 86400
    for ev, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag == "channel":
            cid = el.get("id") or ""
            ids = by_id.get(cid.lower(), [])
            if not ids:
                for dn in el.findall("display-name"):
                    ids = by_name.get(norm(dn.text), [])
                    if ids:
                        break
            if ids:
                xml_map[cid] = ids
            el.clear()
        elif el.tag == "programme":
            cid = el.get("channel")
            targets = xml_map.get(cid) or by_id.get((cid or "").lower())
            if targets:
                st, sp = xmltv_time(el.get("start")), xmltv_time(el.get("stop"))
                if st and sp and sp > lo and st < hi:
                    t = el.findtext("title") or ""
                    sub = el.findtext("sub-title") or ""
                    d = (el.findtext("desc") or "")[:2000]
                    for ch in targets:
                        rows.append((f"l{ch}", st, sp, t, sub, d))
            el.clear()
    keys = {r[0] for r in rows}
    for k in keys:
        db.ex("DELETE FROM epg WHERE chan=? AND start >= ?", (k, lo))
    db.exmany("INSERT OR REPLACE INTO epg(chan,start,stop,title,sub,descr) VALUES(?,?,?,?,?,?)", rows)
    return len(rows)


def best_variant(url, ua=None, max_h=1080):
    """Bei HLS-Masterlisten die beste Stufe bis max_h wählen (ffmpeg nähme sonst die erste).
    Liefert die Eingangsoptionen für ffmpeg: (Adresse, Map-Liste)."""
    plain = (url, ["-map", "0:v:0?", "-map", "0:a:0?"])
    if not url.split("?")[0].lower().endswith((".m3u8", ".m3u")):
        return plain
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua or UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            base = r.geturl()
            text = r.read(512 * 1024).decode("utf-8", "replace")
    except Exception:
        return plain
    if "#EXT-X-STREAM-INF" not in text:
        return plain
    best, best_key, best_n, n = None, None, 0, -1
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        n += 1
        a = dict(re.findall(r'([A-Z-]+)=("[^"]*"|[^,]*)', line))
        bw = int(a.get("BANDWIDTH", "0").strip('"') or 0)
        res = a.get("RESOLUTION", "").strip('"')
        h = int(res.split("x")[1]) if "x" in res else 0
        nxt = next((l.strip() for l in lines[i + 1:] if l.strip() and not l.startswith("#")), None)
        if not nxt or (h and h > max_h):
            continue
        key = (h, bw)
        if best_key is None or key > best_key:
            best, best_key, best_n = urllib.parse.urljoin(base, nxt), key, n
    if not best:
        return plain
    if "TYPE=AUDIO" in text:  # Ton getrennt -> Programm aus der Masterliste wählen
        return url, ["-map", f"0:p:{best_n}:v:0?", "-map", f"0:p:{best_n}:a:0?"]
    return best, ["-map", "0:v:0?", "-map", "0:a:0?"]


def allowed(user):
    acc = db.setting("live_access")
    return bool(user["admin"] or acc is None or user["id"] in (acc or []))


def now_next(chan_key, now=None):
    now = now or time.time()
    rows = db.q("SELECT start,stop,title,sub,descr FROM epg WHERE chan=? AND stop>? ORDER BY start LIMIT 2",
                (chan_key, now))
    return rows


def chan_public(c):
    nn = now_next(f"l{c['id']}")
    return {"id": c["id"], "name": c["name"], "number": c["number"], "group": c["grp"],
            "has_logo": bool(c["logo"]), "now": nn[0] if nn else None, "next": nn[1] if len(nn) > 1 else None}


def logo_file(c):
    url = c["logo"]
    if not url:
        return None
    d = db.path("livelogos")
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, hashlib.sha1(url.encode()).hexdigest() + os.path.splitext(url.split("?")[0])[1][:5])
    if not os.path.exists(fn) or time.time() - os.path.getmtime(fn) > 30 * 86400:
        try:
            data = fetch(url, 5 * 1024 * 1024)
            with open(fn + ".tmp", "wb") as f:
                f.write(data)
            os.replace(fn + ".tmp", fn)
        except Exception:
            return fn if os.path.exists(fn) else None
    return fn


_SNAP_SEM = threading.Semaphore(2)          # höchstens zwei ffmpeg-Aufrufe für Standbilder gleichzeitig
_SNAP_LOCKS = {}


def snapshot(c):
    """Ein Bild aus dem laufenden Stream holen (ffmpeg als eigenständiges Programm). Ergebnis bzw. Fehlschlag gilt 5 Minuten."""
    d = db.path("livesnaps")
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, f"{c['id']}.jpg")
    fail = fn + ".fail"
    fresh = lambda: any(os.path.exists(x) and time.time() - os.path.getmtime(x) < 300 for x in (fn, fail))
    lock = _SNAP_LOCKS.setdefault(c["id"], threading.Lock())
    if not fresh():
        with lock:
            if not fresh() and _SNAP_SEM.acquire(timeout=20):
                try:
                    src, maps = best_variant(c["url"], c["ua"], max_h=720)
                    tmp = fn + ".tmp.jpg"
                    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-nostdin", "-user_agent", c["ua"] or UA,
                                        "-rw_timeout", "8000000", "-i", src, "-map", "0:v:0", "-an", "-sn",
                                        "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "5", tmp],
                                       timeout=25, stdin=subprocess.DEVNULL, capture_output=True)
                    if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
                        os.replace(tmp, fn)
                        if os.path.exists(fail):
                            os.remove(fail)
                    else:
                        open(fail, "w").close()
                except Exception:
                    open(fail, "w").close()
                finally:
                    _SNAP_SEM.release()
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 1800:      # älter als 30 Minuten: lieber keins
        return fn
    return None


def init(route, H):
    with db._lock:
        db.conn().executescript(SCHEMA)
        db.conn().commit()

    def timer():
        time.sleep(20)
        while True:
            try:
                refresh()
            except Exception as e:
                print("[live]", e, flush=True)
            time.sleep(6 * 3600)
    threading.Thread(target=timer, name="live-refresh", daemon=True).start()

    def channels_for(u):
        rows = db.q("SELECT c.* FROM live_channels c JOIN live_sources s ON s.id=c.source_id WHERE s.enabled=1 "
                    "AND c.enabled=1 ORDER BY COALESCE(c.number, 99999), s.id, c.pos")
        p = db.setting(f"prefs:{u['id']}") or {}
        order, hidden = p.get("live_order") or [], set(p.get("live_hidden") or [])
        rows.sort(key=lambda c: order.index(c["id"]) if c["id"] in order else 10 ** 6)
        return [c for c in rows if c["id"] not in hidden]

    @route("GET", "/api/live")
    def r_live(h):
        u = h.user()
        if not allowed(u):
            return h.send_json([])
        h.send_json([chan_public(c) for c in channels_for(u)])

    @route("GET", "/api/live/epg")
    def r_live_epg(h):
        u = h.user()
        if not allowed(u):
            return h.send_json({})
        frm = float(h.query.get("from", [time.time() - 1800])[0])
        to = float(h.query.get("to", [frm + 6 * 3600])[0])
        cid = h.query.get("id", [None])[0]
        keys = [f"l{cid}"] if cid else [f"l{c['id']}" for c in channels_for(u)]
        out = {}
        for k in keys:
            out[k[1:]] = db.q("SELECT start,stop,title,sub,descr FROM epg WHERE chan=? AND stop>? AND start<? "
                              "ORDER BY start", (k, frm, to))
        h.send_json(out)

    @route("GET", r"/api/live/(\d+)/logo")
    def r_live_logo(h, cid):
        c = db.one("SELECT * FROM live_channels WHERE id=?", (int(cid),))
        fn = logo_file(c) if c else None
        if not fn:
            return h.send_json({"error": "kein Logo"}, 404)
        stream.send_file(h, fn, cache="private, max-age=86400")

    @route("GET", r"/api/live/(\d+)/snap")
    def r_live_snap(h, cid):
        """Standbild des laufenden Streams (480 px breit) für die Senderübersicht – höchstens alle 5 Minuten neu."""
        if not allowed(h.user()):
            return h.send_json({"error": "Kein Zugriff"}, 403)
        c = db.one("SELECT * FROM live_channels WHERE id=?", (int(cid),))
        if not c:
            return h.send_json({"error": "Unbekannter Sender"}, 404)
        fn = snapshot(c)
        if not fn:
            return h.send_json({"error": "Kein Standbild"}, 404)
        stream.send_file(h, fn, cache="private, max-age=240")

    @route("GET", r"/api/live/(\d+)/url")
    def r_live_url(h, cid):
        """Original-Adresse (für Geräte, die HLS selbst abspielen)."""
        if not allowed(h.user()):
            return h.send_json({"error": "Kein Zugriff"}, 403)
        c = db.one("SELECT url,ua FROM live_channels WHERE id=?", (int(cid),))
        h.send_json(c or {})

    @route("GET", r"/api/live/(\d+)/stream")
    def r_live_stream(h, cid):
        u = h.user()
        if not allowed(u):
            return h.send_json({"error": "Kein Zugriff"}, 403)
        c = db.one("SELECT * FROM live_channels WHERE id=?", (int(cid),))
        if not c:
            return h.send_json({"error": "Unbekannter Sender"}, 404)
        mode = h.query.get("mode", ["copy"])[0]
        src, maps = best_variant(c["url"], c["ua"])
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-user_agent", c["ua"] or UA,
               "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
               "-i", src, *maps]
        if mode == "transcode":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-vf", "yadif=0:-1:1,format=yuv420p",
                    "-g", "50"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "160k", "-sn", "-dn",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-frag_duration", "1000000",
                "-f", "mp4", "pipe:1"]
        pid = db.ex("INSERT INTO plays(user_id,item_id,client,mode,started,last,seconds,pos,title,kind) "
                    "VALUES(?,?,?,?,?,?,0,0,?,?)", (u["id"], -int(cid), u.get("_client") or "web", "live",
                                                    time.time(), time.time(), c["name"], "live"))
        start = time.time()
        try:
            stream.run_fmp4(h, f"{u['id']}:live", cmd)
        finally:
            db.ex("UPDATE plays SET last=?, seconds=? WHERE id=?", (time.time(), time.time() - start, pid))

    # -- Verwaltung -------------------------------------------------------------
    @route("GET", "/api/live/sources", "admin")
    def r_sources(h):
        srcs = db.q("SELECT * FROM live_sources ORDER BY id")
        for s in srcs:
            s["channels"] = db.q("SELECT id,name,number,grp,enabled,tvg_id,(SELECT COUNT(*) FROM epg WHERE "
                                 "chan='l'||live_channels.id AND stop>?) AS epg FROM live_channels WHERE source_id=? "
                                 "ORDER BY COALESCE(number,99999),pos", (time.time(), s["id"]))
        h.send_json({"sources": srcs, "access": db.setting("live_access")})

    @route("POST", "/api/live/sources", "admin")
    def r_source_new(h):
        b = h.body()
        if not (b.get("m3u_url") or "").strip():
            return h.send_json({"error": "Adresse der Senderliste fehlt"}, 400)
        sid = db.ex("INSERT INTO live_sources(name,m3u_url,xmltv_url,enabled) VALUES(?,?,?,1)",
                    ((b.get("name") or "Senderliste").strip(), b["m3u_url"].strip(), (b.get("xmltv_url") or "").strip()))
        threading.Thread(target=refresh, args=(sid,), daemon=True).start()
        h.send_json({"id": sid})

    @route("PUT", r"/api/live/sources/(\d+)", "admin")
    def r_source_put(h, sid):
        b = h.body()
        for k in ("name", "m3u_url", "xmltv_url", "enabled"):
            if k in b:
                db.ex(f"UPDATE live_sources SET {k}=? WHERE id=?", (b[k], int(sid)))
        threading.Thread(target=refresh, args=(int(sid),), daemon=True).start()
        h.send_json({"ok": True})

    @route("DELETE", r"/api/live/sources/(\d+)", "admin")
    def r_source_del(h, sid):
        for c in db.q("SELECT id FROM live_channels WHERE source_id=?", (int(sid),)):
            db.ex("DELETE FROM epg WHERE chan=?", (f"l{c['id']}",))
        db.ex("DELETE FROM live_channels WHERE source_id=?", (int(sid),))
        db.ex("DELETE FROM live_sources WHERE id=?", (int(sid),))
        h.send_json({"ok": True})

    @route("POST", r"/api/live/sources/(\d+)/refresh", "admin")
    def r_source_refresh(h, sid):
        refresh(int(sid))
        h.send_json(db.one("SELECT * FROM live_sources WHERE id=?", (int(sid),)))

    @route("POST", r"/api/live/sources/(\d+)/upload/(m3u|xmltv)", "admin")
    def r_source_upload(h, sid, kind):
        data = h.raw_body(200 * 1024 * 1024)
        d = db.path("live")
        os.makedirs(d, exist_ok=True)
        fn = os.path.join(d, f"{int(sid)}.{kind}")
        with open(fn, "wb") as f:
            f.write(data)
        db.ex(f"UPDATE live_sources SET {'m3u_url' if kind == 'm3u' else 'xmltv_url'}=? WHERE id=?",
              ("file:" + fn, int(sid)))
        refresh(int(sid))
        h.send_json(db.one("SELECT * FROM live_sources WHERE id=?", (int(sid),)))

    @route("PUT", r"/api/live/channels/(\d+)", "admin")
    def r_chan_put(h, cid):
        b = h.body()
        if "enabled" in b:
            db.ex("UPDATE live_channels SET enabled=? WHERE id=?", (1 if b["enabled"] else 0, int(cid)))
        if "number" in b:
            db.ex("UPDATE live_channels SET number=? WHERE id=?", (b["number"] or None, int(cid)))
        h.send_json({"ok": True})

    @route("PUT", "/api/live/access", "admin")
    def r_access(h):
        db.set_setting("live_access", h.body().get("users"))
        h.send_json({"ok": True})
