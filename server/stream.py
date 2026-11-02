"""Wiedergabe: Entscheidung Direkt/Remux/Umwandeln, Ausgabe als Datei oder fragmentiertes MP4, Untertitel, Bilder."""
import hashlib
import json
import os
import re
import subprocess
import threading
import time

import db

DIRECT_CONTAINERS = {"mp4": ("mov,mp4", "mp4"), "webm": ("webm", "matroska,webm"), "mkv": ("matroska",)}
_procs = {}          # Schlüssel (Sitzung) -> Popen
_plock = threading.Lock()


def ext_container(media, path):
    c = (media or {}).get("container") or ""
    ext = os.path.splitext(path)[1].lower()
    if "mp4" in c or ext in (".mp4", ".m4v", ".mov"):
        return "mp4"
    if ext == ".webm":
        return "webm"
    if "matroska" in c or ext == ".mkv":
        return "mkv"
    return ext.lstrip(".") or c


def decide(item, media, caps, audio=None, height=None, burn=None):
    """caps: {'vc': [...], 'ac': [...], 'ct': [...]} – was der Client kann. Liefert (mode, grund)."""
    v = (media or {}).get("video") or {}
    auds = (media or {}).get("audio") or []
    vc, ac, ct = set(caps.get("vc") or []), set(caps.get("ac") or []), set(caps.get("ct") or [])
    cont = ext_container(media, item["path"])
    a = None
    if auds:
        a = next((x for x in auds if x["i"] == audio), None) if audio is not None else None
        a = a or next((x for x in auds if x.get("default")), auds[0])
    video_ok = v.get("codec") in vc and not (v.get("hdr") and "hdr" not in vc)
    if height and v.get("height") and v["height"] > height * 1.05:
        video_ok = False
    if burn is not None:
        video_ok = False
    audio_ok = a is None or a["codec"] in ac
    first_audio = a is None or a["i"] == auds[0]["i"] or (caps.get("tracks") and cont in ct)
    if video_ok and audio_ok and cont in ct and first_audio:
        return "direct", a
    if video_ok:
        return "remux", a
    return "transcode", a


def stop(key):
    with _plock:
        p = _procs.pop(key, None)
    if p and p.poll() is None:
        try:
            p.kill()
        except OSError:
            pass


def fmp4_cmd(path, t, mode, audio_i, audio_codec, ac, height=None, burn=None, vcodec=None):
    s = db.setting
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if t and t > 0:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", path, "-map", "0:v:0"]
    if audio_i is not None:
        cmd += ["-map", f"0:a:{audio_i}?"]
    if mode == "transcode":
        vf = []
        if burn is not None:
            cmd = cmd[:cmd.index("-map")]
            fc = f"[0:v:0][0:s:{int(burn)}]overlay"
            if height:
                fc += f",scale=-2:'min({int(height)},ih)'"
            cmd += ["-filter_complex", fc + ",format=yuv420p[v]", "-map", "[v]"]
            if audio_i is not None:
                cmd += ["-map", f"0:a:{audio_i}?"]
        else:
            if height:
                vf.append(f"scale=-2:'min({int(height)},ih)'")
            vf.append("format=yuv420p")
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-c:v", "libx264", "-preset", str(s("transcode_preset") or "veryfast"),
                "-crf", str(int(s("transcode_crf") or 21)), "-profile:v", "high", "-level", "4.1",
                "-g", "48", "-keyint_min", "48", "-sc_threshold", "0"]
        th = int(s("transcode_threads") or 0)
        if th:
            cmd += ["-threads", str(th)]
    else:
        cmd += ["-c:v", "copy"]
        if vcodec == "hevc":
            cmd += ["-tag:v", "hvc1"]
    if audio_i is not None:
        if mode == "remux" and audio_codec in ac and audio_codec in ("aac", "mp3", "opus", "flac", "ac3", "eac3"):
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "192k"]
    cmd += ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-frag_duration", "2000000",
            "-avoid_negative_ts", "make_zero", "-f", "mp4", "pipe:1"]
    return cmd


def run_fmp4(handler, key, cmd):
    """Startet ffmpeg und schreibt die Ausgabe in die HTTP-Antwort (Ende = Verbindung schließen)."""
    stop(key)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    with _plock:
        _procs[key] = p
    err = []
    threading.Thread(target=lambda: err.append(p.stderr.read()), daemon=True).start()
    first = p.stdout.read(64 * 1024)
    if not first:
        p.wait()
        msg = (b"".join(e for e in err if e) or b"").decode("utf-8", "replace")[-400:]
        handler.send_json({"error": "Umwandlung fehlgeschlagen", "detail": msg}, 500)
        return
    handler.close_connection = True
    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp4")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        handler.wfile.write(first)
        while True:
            b = p.stdout.read(256 * 1024)
            if not b:
                break
            handler.wfile.write(b)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        if p.poll() is None:
            p.kill()
        with _plock:
            if _procs.get(key) is p:
                _procs.pop(key, None)


MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
        ".webm": "video/webm", ".avi": "video/x-msvideo", ".ts": "video/mp2t", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".vtt": "text/vtt; charset=utf-8",
        ".mp3": "audio/mpeg", ".svg": "image/svg+xml"}


def send_file(handler, path, mime=None, cache=None):
    """Datei mit Range-Unterstützung senden."""
    try:
        st = os.stat(path)
    except OSError:
        return handler.send_json({"error": "Datei nicht gefunden"}, 404)
    size = st.st_size
    mime = mime or MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    rng = handler.headers.get("Range")
    start, end = 0, size - 1
    status = 200
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m:
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            if start >= size:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            status = 206
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", mime)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("Cache-Control", cache or "no-cache")
    handler.end_headers()
    if handler.command == "HEAD":
        return
    try:
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                b = f.read(min(1024 * 1024, left))
                if not b:
                    break
                handler.wfile.write(b)
                left -= len(b)
    except (BrokenPipeError, ConnectionResetError, OSError):
        handler.close_connection = True


# -- Untertitel ---------------------------------------------------------------
def subtitle_vtt(item, key):
    """key: 'i3' = eingebettete Spur 3, 'e0' = externe Datei 0. Liefert Pfad zur VTT im Cache."""
    media = json.loads(item["media"] or "{}")
    d = db.path("subs")
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1(f"{item['path']}|{item['mtime']}|{key}".encode()).hexdigest()[:20]
    out = os.path.join(d, h + ".vtt")
    if os.path.exists(out):
        return out
    with _sub_locks_lock:
        lk = _sub_locks.setdefault(out, threading.Lock())
    with lk:
        if os.path.exists(out):
            return out
        return _extract_sub(item, media, key, out)


_sub_locks = {}
_sub_locks_lock = threading.Lock()


def _extract_sub(item, media, key, out):
    if key.startswith("e"):
        subs = media.get("ext_subs") or []
        n = int(key[1:])
        if n >= len(subs):
            return None
        src, mp = subs[n]["file"], "0:s:0"
    else:
        src, mp = item["path"], f"0:s:{int(key[1:])}"
    tmp = f"{out}.{threading.get_ident()}.tmp"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", src, "-map", mp,
                        "-f", "webvtt", tmp], capture_output=True, timeout=900)
    if r.returncode != 0 or not os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None
    os.replace(tmp, out)
    return out


# -- Bilder -------------------------------------------------------------------
_img_lock = threading.Semaphore(max(3, (os.cpu_count() or 4) // 2))


def image(src, width):
    """Verkleinerte Fassung (JPEG) im Cache; ohne Breite das Original."""
    if not src or not os.path.exists(src):
        return None
    if not width:
        return src
    width = max(40, min(int(width), 3840))
    try:
        mt = os.stat(src).st_mtime
    except OSError:
        return None
    h = hashlib.sha1(f"{src}|{mt}|{width}".encode()).hexdigest()
    d = db.path("img", h[:2])
    out = os.path.join(d, h + (".png" if src.lower().endswith(".png") else ".jpg"))
    if os.path.exists(out):
        return out
    os.makedirs(d, exist_ok=True)
    tmp = out + ".tmp" + os.path.splitext(out)[1]
    with _img_lock:
        if os.path.exists(out):
            return out
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", src,
                            "-vf", f"scale='min({width},iw)':-2", "-frames:v", "1", "-q:v", "4", tmp],
                           capture_output=True, timeout=60)
    if r.returncode != 0 or not os.path.exists(tmp):
        return src
    os.replace(tmp, out)
    return out


def snapshot(path, t, width=480):
    """Einzelbild aus einem Video (für Folgen ohne Vorschaubild)."""
    h = hashlib.sha1(f"{path}|{int(t)}|{width}".encode()).hexdigest()
    d = db.path("img", "snap")
    out = os.path.join(d, h + ".jpg")
    if os.path.exists(out):
        return out
    os.makedirs(d, exist_ok=True)
    with _img_lock:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", str(int(t)),
                            "-i", path, "-vf", f"scale={width}:-2", "-frames:v", "1", "-q:v", "5", out + ".tmp.jpg"],
                           capture_output=True, timeout=60)
    if r.returncode == 0 and os.path.exists(out + ".tmp.jpg"):
        os.replace(out + ".tmp.jpg", out)
        return out
    return None


def cleanup_loop():
    while True:
        time.sleep(3600)
        with _plock:
            for k, p in list(_procs.items()):
                if p.poll() is not None:
                    _procs.pop(k, None)


def warm_images():
    """Cover und Bilder für Folgen im Hintergrund vorbereiten, damit Listen sofort Bilder zeigen."""
    def loop():
        done = set()
        while True:
            rows = db.q("SELECT id,poster,thumb,kind FROM items WHERE (poster IS NOT NULL OR thumb IS NOT NULL) "
                        "ORDER BY added DESC")
            for r in rows:
                if r["id"] in done:
                    continue
                for src, w in ((r["poster"], 300), (r["thumb"], 480)):
                    if src:
                        try:
                            image(src, w)
                        except Exception:
                            pass
                done.add(r["id"])
            time.sleep(1800)
    threading.Thread(target=loop, name="img-warm", daemon=True).start()
