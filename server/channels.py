"""Eigene TV-Sender: Filme und Folgen aus den Bibliotheken laufen als Endlos-Programm (ersetzt den TV Manager)."""
import os
import random
import time

import db
import stream

SCHEMA = """
CREATE TABLE IF NOT EXISTS vchannels (id INTEGER PRIMARY KEY, name TEXT, number INTEGER, logo TEXT,
  enabled INTEGER DEFAULT 1, anchor REAL, created REAL);
CREATE TABLE IF NOT EXISTS vchannel_items (id INTEGER PRIMARY KEY, channel_id INTEGER, item_id INTEGER, pos INTEGER);
CREATE INDEX IF NOT EXISTS i_vci ON vchannel_items(channel_id, pos);
"""
FALLBACK_S = 45 * 60


def playlist(cid):
    rows = db.q("SELECT v.id AS row, i.id, i.kind, i.title, i.season, i.episode, i.year, i.duration, i.runtime, "
                "i.show_id, i.plot, (SELECT title FROM items s WHERE s.id=i.show_id) AS show_title "
                "FROM vchannel_items v JOIN items i ON i.id=v.item_id WHERE v.channel_id=? ORDER BY v.pos, v.id",
                (cid,))
    for r in rows:
        r["len"] = float(r["duration"] or (r["runtime"] or 0) * 60 or FALLBACK_S)
    return rows


def position(ch, pl, t=None):
    """Welcher Eintrag läuft zur Zeit t und an welcher Stelle?"""
    t = t or time.time()
    total = sum(r["len"] for r in pl)
    if not pl or total <= 0:
        return None, 0, 0
    k = (t - (ch["anchor"] or ch["created"] or 0)) % total
    for n, r in enumerate(pl):
        if k < r["len"]:
            return n, k, t - k
        k -= r["len"]
    return 0, 0, t


def schedule(ch, pl, frm, to):
    n, off, start = position(ch, pl, frm)
    out = []
    if n is None:
        return out
    t = start
    while t < to and len(out) < 2000:
        r = pl[n]
        out.append({"start": t, "stop": t + r["len"], "id": r["id"], "title": label(r), "descr": r["plot"] or ""})
        t += r["len"]
        n = (n + 1) % len(pl)
    return out


def label(r):
    if r["kind"] == "episode":
        return f"{r['show_title']} – S{r['season']:02d}E{r['episode']:02d} {r['title']}"
    return f"{r['title']}" + (f" ({r['year']})" if r["year"] else "")


def allowed(user):
    acc = db.setting("channels_access")
    return bool(user["admin"] or acc is None or user["id"] in (acc or []))


def init(route, H):
    with db._lock:
        db.conn().executescript(SCHEMA)
        db.conn().commit()

    def pub(ch, with_now=True):
        d = {"id": ch["id"], "name": ch["name"], "number": ch["number"], "enabled": bool(ch["enabled"]),
             "has_logo": bool(ch["logo"])}
        if with_now:
            pl = playlist(ch["id"])
            d["count"] = len(pl)
            sc = schedule(ch, pl, time.time(), time.time() + 1)
            nxt = schedule(ch, pl, sc[0]["stop"] + 1, sc[0]["stop"] + 2) if sc else []
            d["now"] = sc[0] if sc else None
            d["next"] = nxt[0] if nxt else None
        return d

    @route("GET", "/api/channels")
    def r_list(h):
        u = h.user()
        if not allowed(u):
            return h.send_json([])
        rows = db.q("SELECT * FROM vchannels " + ("" if u["admin"] else "WHERE enabled=1 ") +
                    "ORDER BY COALESCE(number, 99999), id")
        h.send_json([pub(c) for c in rows])

    @route("GET", r"/api/channels/(\d+)/epg")
    def r_epg(h, cid):
        if not allowed(h.user()):
            return h.send_json([], 403)
        ch = db.one("SELECT * FROM vchannels WHERE id=?", (int(cid),))
        if not ch:
            return h.send_json([], 404)
        frm = float(h.query.get("from", [time.time()])[0])
        to = float(h.query.get("to", [frm + 24 * 3600])[0])
        h.send_json(schedule(ch, playlist(ch["id"]), frm, min(to, frm + 8 * 86400)))

    @route("GET", r"/api/channels/(\d+)/tune")
    def r_tune(h, cid):
        if not allowed(h.user()):
            return h.send_json({"error": "Kein Zugriff"}, 403)
        ch = db.one("SELECT * FROM vchannels WHERE id=?", (int(cid),))
        pl = playlist(int(cid)) if ch else []
        n, off, start = position(ch, pl) if pl else (None, 0, 0)
        if n is None:
            return h.send_json({"error": "Sender ist leer"}, 404)
        r = pl[n]
        if r["len"] - off < 20:  # kurz vor Schluss -> gleich den nächsten
            r, off = pl[(n + 1) % len(pl)], 0
        h.send_json({"item": r["id"], "offset": off, "title": label(r), "channel": pub(ch, False)})

    @route("GET", r"/api/channels/(\d+)/logo")
    def r_logo(h, cid):
        ch = db.one("SELECT logo FROM vchannels WHERE id=?", (int(cid),))
        if not ch or not ch["logo"] or not os.path.exists(ch["logo"]):
            return h.send_json({"error": "kein Logo"}, 404)
        stream.send_file(h, ch["logo"], cache="private, max-age=3600")

    # -- Verwaltung --------------------------------------------------------------
    @route("POST", "/api/channels", "admin")
    def r_new(h):
        b = h.body()
        name = (b.get("name") or "").strip()
        if not name:
            return h.send_json({"error": "Name fehlt"}, 400)
        num = b.get("number") or (db.val("SELECT MAX(number) FROM vchannels", default=0) + 1)
        cid = db.ex("INSERT INTO vchannels(name,number,enabled,anchor,created) VALUES(?,?,1,?,?)",
                    (name, num, time.time(), time.time()))
        h.send_json({"id": cid})

    @route("PUT", r"/api/channels/(\d+)", "admin")
    def r_put(h, cid):
        b = h.body()
        for k in ("name", "number", "enabled"):
            if k in b:
                db.ex(f"UPDATE vchannels SET {k}=? WHERE id=?", (b[k], int(cid)))
        if b.get("restart"):
            db.ex("UPDATE vchannels SET anchor=? WHERE id=?", (time.time(), int(cid)))
        h.send_json({"ok": True})

    @route("DELETE", r"/api/channels/(\d+)", "admin")
    def r_del(h, cid):
        ch = db.one("SELECT logo FROM vchannels WHERE id=?", (int(cid),))
        if ch and ch["logo"] and os.path.exists(ch["logo"]):
            os.remove(ch["logo"])
        db.ex("DELETE FROM vchannel_items WHERE channel_id=?", (int(cid),))
        db.ex("DELETE FROM vchannels WHERE id=?", (int(cid),))
        h.send_json({"ok": True})

    @route("GET", r"/api/channels/(\d+)/items", "admin")
    def r_items(h, cid):
        pl = playlist(int(cid))
        h.send_json([{"row": r["row"], "id": r["id"], "kind": r["kind"], "title": label(r), "len": r["len"]}
                     for r in pl])

    @route("POST", r"/api/channels/(\d+)/items", "admin")
    def r_add(h, cid):
        """Fügt Filme/Folgen hinzu; Serien und Staffeln werden in ihre Folgen aufgelöst."""
        cid = int(cid)
        ids = []
        for iid in h.body().get("ids") or []:
            it = db.one("SELECT id,kind FROM items WHERE id=?", (int(iid),))
            if not it:
                continue
            if it["kind"] == "show":
                ids += [r["id"] for r in db.q("SELECT id FROM items WHERE show_id=? AND kind='episode' AND season>0 "
                                              "ORDER BY season, episode", (it["id"],))]
            elif it["kind"] == "season":
                ids += [r["id"] for r in db.q("SELECT id FROM items WHERE parent_id=? AND kind='episode' "
                                              "ORDER BY episode", (it["id"],))]
            else:
                ids.append(it["id"])
        pos = db.val("SELECT MAX(pos) FROM vchannel_items WHERE channel_id=?", (cid,), 0)
        db.exmany("INSERT INTO vchannel_items(channel_id,item_id,pos) VALUES(?,?,?)",
                  [(cid, i, pos + n + 1) for n, i in enumerate(ids)])
        h.send_json({"added": len(ids)})

    @route("POST", r"/api/channels/(\d+)/library", "admin")
    def r_add_lib(h, cid):
        """Ganze Bibliothek (alle Filme bzw. alle Folgen) hinzufügen."""
        lib = db.one("SELECT * FROM libraries WHERE id=?", (int(h.body().get("lib") or 0),))
        if not lib:
            return h.send_json({"error": "Bibliothek unbekannt"}, 400)
        kind = "movie" if lib["kind"] == "movie" else "episode"
        order = "sort_title" if kind == "movie" else "show_id, season, episode"
        rows = db.q(f"SELECT id FROM items WHERE lib_id=? AND kind=? {'AND season>0' if kind == 'episode' else ''} "
                    f"ORDER BY {order}", (lib["id"], kind))
        pos = db.val("SELECT MAX(pos) FROM vchannel_items WHERE channel_id=?", (int(cid),), 0)
        db.exmany("INSERT INTO vchannel_items(channel_id,item_id,pos) VALUES(?,?,?)",
                  [(int(cid), r["id"], pos + n + 1) for n, r in enumerate(rows)])
        h.send_json({"added": len(rows)})

    @route("DELETE", r"/api/channels/(\d+)/items/(\d+)", "admin")
    def r_rm(h, cid, row):
        db.ex("DELETE FROM vchannel_items WHERE channel_id=? AND id=?", (int(cid), int(row)))
        h.send_json({"ok": True})

    @route("DELETE", r"/api/channels/(\d+)/items", "admin")
    def r_clear(h, cid):
        db.ex("DELETE FROM vchannel_items WHERE channel_id=?", (int(cid),))
        h.send_json({"ok": True})

    @route("PUT", r"/api/channels/(\d+)/order", "admin")
    def r_order(h, cid):
        b = h.body()
        rows = [r["id"] for r in db.q("SELECT id FROM vchannel_items WHERE channel_id=? ORDER BY pos, id", (int(cid),))]
        if b.get("shuffle"):
            random.shuffle(rows)
        elif b.get("rows"):
            want = [int(x) for x in b["rows"] if int(x) in rows]
            rows = want + [r for r in rows if r not in want]
        db.exmany("UPDATE vchannel_items SET pos=? WHERE id=?", [(n, r) for n, r in enumerate(rows)])
        h.send_json({"ok": True})

    @route("POST", r"/api/channels/(\d+)/logo", "admin")
    def r_logo_up(h, cid):
        data = h.raw_body(5 * 1024 * 1024)
        ext = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"RIFF": ".webp"}
        e = next((v for k, v in ext.items() if data.startswith(k)), None)
        if not e:
            return h.send_json({"error": "Nur PNG, JPG oder WebP"}, 400)
        d = db.path("chlogos")
        os.makedirs(d, exist_ok=True)
        fn = os.path.join(d, f"{int(cid)}_{int(time.time())}{e}")
        with open(fn, "wb") as f:
            f.write(data)
        old = db.val("SELECT logo FROM vchannels WHERE id=?", (int(cid),))
        if old and os.path.exists(old):
            os.remove(old)
        db.ex("UPDATE vchannels SET logo=? WHERE id=?", (fn, int(cid)))
        h.send_json({"ok": True})

    @route("PUT", "/api/channels/access", "admin")
    def r_access(h):
        db.set_setting("channels_access", h.body().get("users"))
        h.send_json({"ok": True})
