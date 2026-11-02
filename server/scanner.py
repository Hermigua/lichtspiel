"""Bibliotheken einlesen: Filme und Serien aus Ordnern, Metadaten aus NFO, Bilder aus dem Ordner."""
import json
import os
import queue
import re
import subprocess
import threading
import time
import traceback

import db
import nfo

VIDEO_EXT = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts", ".webm", ".wmv", ".mpg", ".mpeg", ".flv"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa"}
IMG_EXT = (".jpg", ".png", ".jpeg", ".webp")
SKIP_DIRS = {"extras", "trailers", "featurettes", "behind the scenes", "deleted scenes", "interviews",
             "scenes", "samples", "shorts", "other", "@eadir", "#recycle", "lost+found"}
SE_RE = re.compile(r"[Ss](\d{1,3})[ ._-]?[Ee](\d{1,4})(?:[-Ee]+(\d{1,4}))?")
X_RE = re.compile(r"(?<!\d)(\d{1,2})x(\d{2,3})(?!\d)")
SEASON_DIR_RE = re.compile(r"(?:staffel|season|serie|s)\s*0*(\d{1,3})\b", re.I)
YEAR_RE = re.compile(r"\s*[\(\[](\d{4})[\)\]]\s*$")
ARTICLES = ("der ", "die ", "das ", "the ", "a ", "an ", "ein ", "eine ", "le ", "la ", "les ")

state = {"running": None, "lib": None, "done": 0, "found": 0, "msg": "", "log": []}
_scan_lock = threading.Lock()


def log(msg):
    state["log"] = (state["log"] + [time.strftime("%H:%M:%S ") + msg])[-50:]
    print("[scan]", msg, flush=True)


def sort_key(t):
    t = (t or "").strip().casefold()
    for a in ARTICLES:
        if t.startswith(a) and len(t) > len(a):
            t = t[len(a):]
            break
    t = t.translate(str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss", "é": "e", "è": "e"}))
    return re.sub(r"^[^\w]+", "", t)


def is_video(name):
    n = name.lower()
    ext = os.path.splitext(n)[1]
    if ext not in VIDEO_EXT:
        return False
    stem = os.path.splitext(n)[0]
    if stem.endswith(("-trailer", ".trailer", "_trailer", "-sample", ".sample", "-featurette", "-extra",
                      "-behindthescenes", "-deleted", "-interview", "-scene", "-short", "-clip")):
        return False
    if stem in ("sample", "trailer"):
        return False
    return True


def listdir(d):
    try:
        return list(os.scandir(d))
    except OSError:
        return []


def find_img(files, *stems):
    """files: Menge kleingeschriebener Dateinamen -> echter Name; liefert ersten Treffer."""
    for s in stems:
        for e in IMG_EXT:
            n = (s + e).lower()
            if n in files:
                return files[n]
    return None


def ext_subs(dirpath, files, base):
    out = []
    bl = base.lower()
    for low, real in files.items():
        stem, ext = os.path.splitext(low)
        if ext in SUB_EXT and (stem == bl or stem.startswith(bl + ".")):
            tags = stem[len(bl):].strip(".").split(".") if stem != bl else []
            lang = next((t for t in tags if len(t) in (2, 3) and t.isalpha()), "")
            out.append({"file": os.path.join(dirpath, real), "lang": lang,
                        "forced": "forced" in tags, "codec": ext[1:]})
    return out


def clean_title(name):
    name = os.path.splitext(name)[0] if os.path.splitext(name)[1].lower() in VIDEO_EXT else name
    m = YEAR_RE.search(name)
    year = int(m.group(1)) if m else None
    if m:
        name = name[: m.start()]
    return name.replace(".", " ").replace("_", " ").strip(), year


class Scan:
    def __init__(self, lib, full=False):
        self.lib = lib
        self.full = full
        self.seen = set()
        self.known = {r["path"]: r for r in db.q(
            "SELECT id,path,size,mtime,nfo_mtime,kind FROM items WHERE lib_id=?", (lib["id"],))}
        self.n = 0

    # -- Hilfen ---------------------------------------------------------------
    def upsert(self, path, fields, size=None, mtime=None, nfo_mtime=None):
        """Legt Eintrag an oder aktualisiert ihn; gibt id zurück."""
        k = self.known.get(path)
        now = db.now()
        if k and not self.full and k["size"] == size and k["mtime"] == mtime and k["nfo_mtime"] == nfo_mtime \
                and size is not None:
            self.seen.add(k["id"])
            return k["id"]
        fields = dict(fields)
        for key in ("genres", "people"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key] or [], ensure_ascii=False)
        fields.update(size=size, mtime=mtime, nfo_mtime=nfo_mtime, updated=now, missing=0)
        if k:
            if k["size"] != size or k["mtime"] != mtime:
                fields["probed"] = 0
            cols = ",".join(f"{c}=?" for c in fields)
            db.ex(f"UPDATE items SET {cols} WHERE id=?", list(fields.values()) + [k["id"]])
            self.seen.add(k["id"])
            return k["id"]
        added = min(now, mtime) if mtime else now
        fields.update(lib_id=self.lib["id"], path=path, added=added)
        cols = ",".join(fields)
        iid = db.ex(f"INSERT INTO items({cols}) VALUES({','.join('?' * len(fields))})", list(fields.values()))
        self.known[path] = {"id": iid, "path": path, "size": size, "mtime": mtime, "nfo_mtime": nfo_mtime}
        self.seen.add(iid)
        self.n += 1
        return iid

    @staticmethod
    def stat(p):
        try:
            s = os.stat(p)
            return s.st_size, round(s.st_mtime, 3)
        except OSError:
            return None, None

    # -- Filme ----------------------------------------------------------------
    def movies(self, root):
        for dirpath, dirs, fnames in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not d.lower().endswith(".trickplay")
                             and d.lower() not in SKIP_DIRS)
            vids = sorted(f for f in fnames if is_video(f))
            if not vids:
                continue
            files = {f.lower(): f for f in fnames}
            single = len(vids) == 1
            for v in vids:
                fp = os.path.join(dirpath, v)
                base = os.path.splitext(v)[0]
                nfn = files.get((base + ".nfo").lower()) or (files.get("movie.nfo") if single else None)
                nfo_p = os.path.join(dirpath, nfn) if nfn else None
                size, mtime = self.stat(fp)
                nmt = self.stat(nfo_p)[1] if nfo_p else None
                k = self.known.get(fp)
                if k and not self.full and k["size"] == size and k["mtime"] == mtime and k["nfo_mtime"] == nmt:
                    self.seen.add(k["id"])
                    state["done"] += 1
                    continue
                d = nfo.read(nfo_p) if nfo_p else None
                title, year = clean_title(v if not single else (os.path.basename(dirpath) if
                                          YEAR_RE.search(os.path.basename(dirpath)) else v))
                d = d or {}
                im = lambda *s: (lambda r: os.path.join(dirpath, r) if r else None)(find_img(files, *s))
                f = {
                    "kind": "movie", "parent_id": None, "show_id": None,
                    "title": d.get("title") or title, "orig_title": d.get("orig_title"),
                    "year": d.get("year") or year, "plot": d.get("plot"), "tagline": d.get("tagline"),
                    "genres": d.get("genres") or [], "studio": d.get("studio"), "mpaa": d.get("mpaa"),
                    "rating": d.get("rating"), "runtime": d.get("runtime"), "people": d.get("people") or [],
                    "dir": dirpath, "duration": d.get("duration"),
                    "poster": im(base + "-poster", *(("poster", "folder", "cover", "movie") if single else ())),
                    "backdrop": im(base + "-fanart", base + "-backdrop",
                                   *(("backdrop", "fanart", "background", "landscape") if single else ())),
                    "logo": im(base + "-clearlogo", base + "-logo", *(("clearlogo", "logo") if single else ())),
                    "thumb": im(base + "-thumb", base + "-landscape"),
                }
                f["sort_title"] = sort_key(d.get("sort_title") or f["title"])
                f["media"] = json.dumps({"ext_subs": ext_subs(dirpath, files, base)})
                self.upsert(fp, f, size, mtime, nmt)
                state["done"] += 1

    # -- Serien ---------------------------------------------------------------
    def shows(self, root):
        for e in sorted(listdir(root), key=lambda x: x.name.lower()):
            if not e.is_dir() or e.name.startswith(".") or e.name.lower() in SKIP_DIRS:
                continue
            try:
                self.show(e.path)
            except Exception:
                log("Fehler bei " + e.path + ": " + traceback.format_exc(limit=2))

    def show(self, sdir):
        top = listdir(sdir)
        files = {x.name.lower(): x.name for x in top if x.is_file()}
        nfo_p = os.path.join(sdir, files["tvshow.nfo"]) if "tvshow.nfo" in files else None
        nmt = self.stat(nfo_p)[1] if nfo_p else None
        # Folgen sammeln
        eps = []
        for dirpath, dirs, fnames in os.walk(sdir):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not d.lower().endswith(".trickplay")
                             and d.lower() not in SKIP_DIRS)
            vids = [f for f in fnames if is_video(f)]
            if vids:
                eps.append((dirpath, {f.lower(): f for f in fnames}, sorted(vids)))
        if not eps:
            return
        d = nfo.read(nfo_p) if nfo_p else {}
        d = d or {}
        title, year = clean_title(os.path.basename(sdir))
        im = lambda *s: (lambda r: os.path.join(sdir, r) if r else None)(find_img(files, *s))
        _, smt = self.stat(sdir)
        sf = {
            "kind": "show", "title": d.get("title") or title, "orig_title": d.get("orig_title"),
            "year": d.get("year") or year, "plot": d.get("plot"), "genres": d.get("genres") or [],
            "studio": d.get("studio"), "mpaa": d.get("mpaa"), "rating": d.get("rating"),
            "people": d.get("people") or [], "aired": d.get("aired"), "dir": sdir,
            "poster": im("poster", "folder", "cover"), "backdrop": im("backdrop", "fanart", "background", "landscape"),
            "logo": im("clearlogo", "logo"), "thumb": im("landscape", "thumb"),
        }
        sf["sort_title"] = sort_key(d.get("sort_title") or sf["title"])
        # Serie immer aktualisieren, wenn sich Bilder geändert haben könnten -> Größe = Dateianzahl
        show_id = self.upsert(sdir, sf, len(files), smt, nmt)
        seasons = {}

        def season_id(n, sdirpath, sfiles):
            if n in seasons:
                return seasons[n]
            key = f"{sdir}#S{n}"
            stem = "season-specials" if n == 0 else f"season{n:02d}"
            sp = find_img(files, stem + "-poster")
            sp = os.path.join(sdir, sp) if sp else None
            if not sp and sdirpath != sdir:
                r = find_img(sfiles, "poster", "folder", "cover")
                sp = os.path.join(sdirpath, r) if r else None
            sb = find_img(files, stem + "-fanart", stem + "-landscape", stem + "-backdrop")
            snfo = files.get(stem + ".nfo")
            sd = nfo.read(os.path.join(sdir, snfo)) if snfo else None
            stitle = (sd or {}).get("title") or ("Specials" if n == 0 else f"Staffel {n}")
            if re.fullmatch(r"(season|staffel)\s*\d+", stitle, re.I):
                stitle = f"Staffel {n}"
            f = {"kind": "season", "parent_id": show_id, "show_id": show_id, "title": stitle,
                 "season": n, "sort_title": f"{n:04d}", "dir": sdirpath, "plot": (sd or {}).get("plot"),
                 "year": (sd or {}).get("year"), "poster": sp,
                 "backdrop": os.path.join(sdir, sb) if sb else None}
            seasons[n] = self.upsert(key, f, None, None, None)
            return seasons[n]

        for dirpath, dfiles, vids in eps:
            dm = SEASON_DIR_RE.search(os.path.basename(dirpath)) if dirpath != sdir else None
            dseason = 0 if re.search(r"specials?|extras?", os.path.basename(dirpath), re.I) and dirpath != sdir \
                else (int(dm.group(1)) if dm else None)
            for i, v in enumerate(vids):
                fp = os.path.join(dirpath, v)
                base = os.path.splitext(v)[0]
                size, mtime = self.stat(fp)
                enfo = dfiles.get((base + ".nfo").lower())
                enfo_p = os.path.join(dirpath, enfo) if enfo else None
                emt = self.stat(enfo_p)[1] if enfo_p else None
                k = self.known.get(fp)
                m = SE_RE.search(v) or X_RE.search(v)
                s_no = int(m.group(1)) if m else (dseason if dseason is not None else 1)
                if k and not self.full and k["size"] == size and k["mtime"] == mtime and k["nfo_mtime"] == emt:
                    season_id(s_no, dirpath, dfiles)
                    self.seen.add(k["id"])
                    state["done"] += 1
                    continue
                ed = (nfo.read(enfo_p) if enfo_p else None) or {}
                if ed.get("season") is not None:
                    s_no = ed["season"]
                e_no = ed.get("episode")
                if e_no is None:
                    e_no = int(m.group(2)) if m else i + 1
                etitle = ed.get("title")
                if not etitle:
                    rest = v[m.end():] if m else base
                    rest = os.path.splitext(rest)[0] if m else rest
                    etitle = re.sub(r"^[\s._-]+", "", rest).replace(".", " ").strip() or f"Folge {e_no}"
                thumb = find_img(dfiles, base, base + "-thumb")
                f = {"kind": "episode", "parent_id": season_id(s_no, dirpath, dfiles), "show_id": show_id,
                     "title": etitle, "orig_title": ed.get("orig_title"), "season": s_no, "episode": e_no,
                     "sort_title": f"{s_no:04d}{e_no:05d}", "plot": ed.get("plot"), "aired": ed.get("aired"),
                     "year": ed.get("year"), "rating": ed.get("rating"), "runtime": ed.get("runtime"),
                     "people": ed.get("people") or [], "duration": ed.get("duration"), "dir": dirpath,
                     "thumb": os.path.join(dirpath, thumb) if thumb else None,
                     "media": json.dumps({"ext_subs": ext_subs(dirpath, dfiles, base)})}
                self.upsert(fp, f, size, mtime, emt)
                state["done"] += 1

    # -- Ablauf ---------------------------------------------------------------
    def run(self):
        paths = json.loads(self.lib["paths"] or "[]")
        ok_roots = []
        for p in paths:
            if not os.path.isdir(p) or not listdir(p):
                log(f"Pfad nicht erreichbar oder leer, übersprungen: {p}")
                continue
            ok_roots.append(p)
            (self.movies if self.lib["kind"] == "movie" else self.shows)(p)
        # Verschwundene Einträge entfernen – nur unterhalb erreichbarer Pfade
        gone = [r for r in self.known.values() if r["id"] not in self.seen
                and any(r["path"].startswith(rt.rstrip("/") + "/") for rt in ok_roots)]
        for r in gone:
            if r["kind"] in ("movie", "episode") and os.path.exists(r["path"]):
                continue
            db.ex("DELETE FROM items WHERE id=?", (r["id"],))
        # leere Staffeln/Serien aufräumen
        db.ex("DELETE FROM items WHERE lib_id=? AND kind='season' AND id NOT IN "
              "(SELECT parent_id FROM items WHERE kind='episode' AND parent_id IS NOT NULL)", (self.lib["id"],))
        db.ex("DELETE FROM items WHERE lib_id=? AND kind='show' AND id NOT IN "
              "(SELECT show_id FROM items WHERE kind='episode' AND show_id IS NOT NULL)", (self.lib["id"],))
        db.ex("UPDATE libraries SET scanned=? WHERE id=?", (db.now(), self.lib["id"]))
        log(f"{self.lib['name']}: {self.n} neu, {len(gone)} entfernt")


_pending = []


def scan(lib_ids=None, full=False):
    """Startet einen Scan; läuft schon einer, wird der Auftrag danach erledigt."""
    if not _scan_lock.acquire(blocking=False):
        _pending.append((lib_ids, full))
        return False

    def work():
        try:
            libs = db.q("SELECT * FROM libraries ORDER BY pos,id")
            for lib in libs:
                if lib_ids and lib["id"] not in lib_ids:
                    continue
                state.update(running=True, lib=lib["name"], done=0)
                db.set_setting(f"scan_open:{lib['id']}", 1)
                try:
                    Scan(lib, full).run()
                except Exception:
                    log("Fehler: " + traceback.format_exc(limit=3))
                db.ex("DELETE FROM settings WHERE key=?", (f"scan_open:{lib['id']}",))
        finally:
            state.update(running=None, lib=None)
            _scan_lock.release()
            prober.kick()
            if _pending:
                ids, fl = _pending.pop(0)
                scan(ids, fl)

    threading.Thread(target=work, name="scan", daemon=True).start()
    return True


def resume_open_scans():
    ids = [int(r["key"].split(":")[1]) for r in db.q("SELECT key FROM settings WHERE key LIKE 'scan_open:%'")]
    if ids:
        log(f"Unterbrochene Scans werden fortgesetzt: {ids}")
        scan(ids)


# -- Medieninfo per ffprobe ---------------------------------------------------
def probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters",
                              path], capture_output=True, timeout=120).stdout
        j = json.loads(out or b"{}")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    fmt = j.get("format") or {}
    if not fmt:
        return None
    m = {"container": fmt.get("format_name", ""), "duration": float(fmt.get("duration") or 0),
         "bitrate": int(fmt.get("bit_rate") or 0), "video": None, "audio": [], "subs": []}
    ai = si = 0
    for s in j.get("streams", []):
        t = s.get("codec_type")
        tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
        disp = s.get("disposition") or {}
        if t == "video" and not disp.get("attached_pic") and m["video"] is None:
            m["video"] = {"codec": s.get("codec_name"), "width": s.get("width"), "height": s.get("height"),
                          "profile": s.get("profile"), "pix_fmt": s.get("pix_fmt"),
                          "hdr": s.get("color_transfer") in ("smpte2084", "arib-std-b67"),
                          "fps": s.get("avg_frame_rate"), "bitrate": int(s.get("bit_rate") or tags.get("bps") or 0)}
        elif t == "audio":
            m["audio"].append({"i": ai, "codec": s.get("codec_name"), "channels": s.get("channels"),
                               "lang": tags.get("language", ""), "title": tags.get("title", ""),
                               "default": bool(disp.get("default")),
                               "bitrate": int(s.get("bit_rate") or tags.get("bps") or 0)})
            ai += 1
        elif t == "subtitle":
            m["subs"].append({"i": si, "codec": s.get("codec_name"), "lang": tags.get("language", ""),
                              "title": tags.get("title", ""), "forced": bool(disp.get("forced")),
                              "default": bool(disp.get("default")),
                              "text": s.get("codec_name") in ("subrip", "ass", "ssa", "webvtt", "mov_text", "text")})
            si += 1
    m["chapters"] = [{"start": float(c.get("start_time") or 0), "end": float(c.get("end_time") or 0),
                      "title": (c.get("tags") or {}).get("title", "")} for c in j.get("chapters", [])][:200]
    return m


def probe_item(iid):
    it = db.one("SELECT id,path,media FROM items WHERE id=?", (iid,))
    if not it:
        return None
    m = probe(it["path"])
    old = json.loads(it["media"] or "{}")
    if m is None:
        db.ex("UPDATE items SET probed=-1 WHERE id=?", (iid,))
        return old
    m["ext_subs"] = old.get("ext_subs", [])
    db.ex("UPDATE items SET media=?, probed=1, duration=? WHERE id=?",
          (json.dumps(m, ensure_ascii=False), m["duration"] or None, iid))
    return m


class Prober:
    """Ergänzt im Hintergrund die Medieninfos (Spuren, Codecs, Dauer)."""

    def __init__(self):
        self.ev = threading.Event()
        self.started = False

    def kick(self):
        self.ev.set()
        if not self.started:
            self.started = True
            threading.Thread(target=self.loop, name="probe", daemon=True).start()

    def loop(self):
        while True:
            self.ev.wait(600)
            self.ev.clear()
            while True:
                rows = db.q("SELECT id FROM items WHERE kind IN ('movie','episode') AND probed=0 "
                            "ORDER BY added DESC LIMIT 200")
                if not rows:
                    break
                qq = queue.Queue()
                for r in rows:
                    qq.put(r["id"])

                def w():
                    while True:
                        try:
                            i = qq.get_nowait()
                        except queue.Empty:
                            return
                        try:
                            probe_item(i)
                        except Exception:
                            db.ex("UPDATE items SET probed=-1 WHERE id=?", (i,))
                n = max(1, int(db.setting("probe_workers") or 2))
                ts = [threading.Thread(target=w, daemon=True) for _ in range(n)]
                for t in ts:
                    t.start()
                for t in ts:
                    t.join()


prober = Prober()


def scheduler():
    def loop():
        while True:
            time.sleep(300)
            h = float(db.setting("scan_interval_h") or 0)
            if h <= 0:
                continue
            last = db.val("SELECT MIN(COALESCE(scanned,0)) FROM libraries", default=None)
            if last is not None and time.time() - last > h * 3600:
                scan()
    threading.Thread(target=loop, name="scan-timer", daemon=True).start()
