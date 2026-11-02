"""NFO-Dateien (Kodi-/tinyMediaManager-Format) lesen."""
import re
import xml.etree.ElementTree as ET


def _txt(root, tag):
    e = root.find(tag)
    if e is None or e.text is None:
        return None
    t = e.text.strip()
    return t or None


def _num(s, typ=float):
    if s is None:
        return None
    try:
        return typ(float(str(s).replace(",", ".")))
    except ValueError:
        return None


def read(fn):
    """Liefert ein dict mit den bekannten Feldern oder None."""
    try:
        with open(fn, "rb") as f:
            raw = f.read(4 * 1024 * 1024)
    except OSError:
        return None
    raw = raw.lstrip(b"\xef\xbb\xbf").strip()
    # manche NFOs enthalten nach dem XML noch eine URL-Zeile
    end = max(raw.rfind(b"</movie>"), raw.rfind(b"</tvshow>"), raw.rfind(b"</episodedetails>"),
              raw.rfind(b"</season>"))
    if end > 0:
        raw = raw[: raw.find(b">", end) + 1]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # ggf. mehrere <episodedetails> hintereinander -> erstes nehmen
        m = re.search(rb"<episodedetails>.*?</episodedetails>", raw, re.S)
        if not m:
            return None
        try:
            root = ET.fromstring(m.group(0))
        except ET.ParseError:
            return None
    d = {"root": root.tag}
    d["title"] = _txt(root, "title")
    d["orig_title"] = _txt(root, "originaltitle")
    d["sort_title"] = _txt(root, "sorttitle")
    d["plot"] = _txt(root, "plot") or _txt(root, "outline")
    d["tagline"] = _txt(root, "tagline")
    d["mpaa"] = _txt(root, "mpaa") or _txt(root, "certification")
    d["year"] = _num(_txt(root, "year"), int)
    prem = _txt(root, "premiered") or _txt(root, "aired")
    d["aired"] = prem
    if not d["year"] and prem and re.match(r"\d{4}", prem):
        d["year"] = int(prem[:4])
    d["runtime"] = _num(_txt(root, "runtime"), int)
    d["season"] = _num(_txt(root, "season"), int)
    d["episode"] = _num(_txt(root, "episode"), int)
    d["show_title"] = _txt(root, "showtitle")
    d["genres"] = [g.text.strip() for g in root.findall("genre") if g.text and g.text.strip()]
    st = [s.text.strip() for s in root.findall("studio") if s.text and s.text.strip()]
    d["studio"] = st[0] if st else None
    # Bewertung: bevorzugt themoviedb, sonst Standard, sonst <rating>
    rating = None
    for r in root.findall("ratings/rating"):
        v = _num(_txt(r, "value"))
        if v is None:
            continue
        if r.get("name") == "themoviedb":
            rating = v
            break
        if rating is None or r.get("default") == "true":
            rating = v
    if rating is None:
        rating = _num(_txt(root, "rating"))
    d["rating"] = rating if rating else None
    people = []
    for a in root.findall("actor")[:40]:
        n = _txt(a, "name")
        if n:
            people.append({"name": n, "role": _txt(a, "role") or "", "type": "actor"})
    for tag, typ in (("director", "director"), ("credits", "writer")):
        for e in root.findall(tag)[:5]:
            if e.text and e.text.strip():
                people.append({"name": e.text.strip(), "role": "", "type": typ})
    d["people"] = people
    dur = _txt(root, "fileinfo/streamdetails/video/durationinseconds")
    d["duration"] = _num(dur)
    return d
