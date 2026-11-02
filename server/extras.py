"""Zusatzfunktionen: Statistik, Aktivität, Marker (Intro/Abspann). Weitere Module hängen sich hier ein."""
import importlib
import json
import time

import db

MODULES = []  # optionale Module mit init(route, H) – z. B. live, channels, markers


def markers(item_id):
    out = []
    for m in MODULES:
        f = getattr(m, "markers", None)
        if f:
            out += f(item_id) or []
    return out


def init(route, H):
    for name in ("live", "channels", "markers"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        MODULES.append(mod)
        mod.init(route, H)

    @route("GET", "/api/activity", "admin")
    def r_activity(h):
        now = time.time()
        rows = db.q("SELECT p.*, u.name AS user, u.color FROM plays p JOIN users u ON u.id=p.user_id "
                    "WHERE p.last > ? ORDER BY p.last DESC", (now - 45,))
        h.send_json([{"play": r["id"], "user": r["user"], "color": r["color"], "item": r["item_id"],
                      "title": r["title"], "mode": r["mode"].rstrip("*"), "client": r["client"],
                      "pos": r["pos"], "started": r["started"]} for r in rows])

    @route("GET", "/api/stats")
    def r_stats(h):
        u = h.user()
        days = max(1, min(int(h.query.get("days", ["30"])[0] or 30), 3650))
        since = time.time() - days * 86400
        uid = h.query.get("user", [None])[0]
        if not u["admin"]:
            uid = u["id"]
        cond, args = "p.started > ? AND p.seconds > 30", [since]
        if uid:
            cond += " AND p.user_id=?"
            args.append(int(uid))
        tot = db.one(f"SELECT COUNT(*) AS plays, COALESCE(SUM(seconds),0) AS secs FROM plays p WHERE {cond}", args)
        users = db.q(f"SELECT u.id,u.name,u.color,COUNT(*) AS plays,SUM(p.seconds) AS secs,MAX(p.last) AS last "
                     f"FROM plays p JOIN users u ON u.id=p.user_id WHERE {cond} GROUP BY u.id ORDER BY secs DESC",
                     args)
        top_m = db.q(f"SELECT p.item_id AS id, i.title, i.year, COUNT(*) AS plays, SUM(p.seconds) AS secs, "
                     f"COUNT(DISTINCT p.user_id) AS users FROM plays p JOIN items i ON i.id=p.item_id WHERE {cond} "
                     f"AND i.kind='movie' GROUP BY p.item_id ORDER BY plays DESC, secs DESC LIMIT 10", args)
        top_s = db.q(f"SELECT s.id, s.title, s.year, COUNT(*) AS plays, SUM(p.seconds) AS secs, "
                     f"COUNT(DISTINCT p.user_id) AS users FROM plays p JOIN items i ON i.id=p.item_id "
                     f"JOIN items s ON s.id=i.show_id WHERE {cond} GROUP BY s.id ORDER BY plays DESC, secs DESC "
                     f"LIMIT 10", args)
        daily = db.q(f"SELECT date(p.started,'unixepoch','localtime') AS d, COUNT(*) AS plays, "
                     f"SUM(p.seconds) AS secs FROM plays p WHERE {cond} GROUP BY d ORDER BY d", args)
        hours = db.q(f"SELECT CAST(strftime('%H',p.started,'unixepoch','localtime') AS INTEGER) AS h, "
                     f"COUNT(*) AS plays FROM plays p WHERE {cond} GROUP BY h", args)
        weekdays = db.q(f"SELECT CAST(strftime('%w',p.started,'unixepoch','localtime') AS INTEGER) AS w, "
                        f"COUNT(*) AS plays FROM plays p WHERE {cond} GROUP BY w", args)
        modes = db.q(f"SELECT REPLACE(p.mode,'*','') AS mode, COUNT(*) AS plays FROM plays p WHERE {cond} "
                     f"GROUP BY 1", args)
        genres = db.q(f"SELECT g.value AS genre, COUNT(*) AS plays FROM plays p JOIN items i ON i.id=p.item_id "
                      f"LEFT JOIN items s ON s.id=i.show_id, json_each(COALESCE(NULLIF(i.genres,'[]'),s.genres,'[]')) g "
                      f"WHERE {cond} GROUP BY g.value ORDER BY plays DESC LIMIT 12", args)
        hist = db.q(f"SELECT p.id,p.item_id,p.title,p.kind,p.mode,p.started,p.seconds,p.client,u.name AS user,"
                    f"u.color FROM plays p JOIN users u ON u.id=p.user_id WHERE {cond} ORDER BY p.started DESC "
                    f"LIMIT 200", args)
        for r in hist:
            r["mode"] = (r["mode"] or "").rstrip("*")
        lib = db.q("SELECT l.name, l.kind, (SELECT COUNT(*) FROM items i WHERE i.lib_id=l.id AND "
                   "i.kind IN ('movie','episode')) AS files, (SELECT COALESCE(SUM(size),0) FROM items i WHERE "
                   "i.lib_id=l.id) AS bytes, (SELECT COALESCE(SUM(duration),0) FROM items i WHERE i.lib_id=l.id) "
                   "AS secs FROM libraries l ORDER BY l.pos, l.id")
        h.send_json({"days": days, "total": tot, "users": users if u["admin"] else [], "top_movies": top_m,
                     "top_shows": top_s, "daily": daily, "hours": hours, "weekdays": weekdays, "modes": modes,
                     "genres": genres, "history": hist, "libraries": lib})

    @route("DELETE", r"/api/plays/(\d+)", "admin")
    def r_play_del(h, pid):
        db.ex("DELETE FROM plays WHERE id=?", (int(pid),))
        h.send_json({"ok": True})
