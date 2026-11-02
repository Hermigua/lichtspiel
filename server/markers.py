"""Intro- und Abspann-Marken aus den Kapiteln der Videodatei."""
import json
import re

import db

INTRO = re.compile(r"\b(intro|vorspann|opening|op)\b", re.I)
CREDITS = re.compile(r"\b(credits|abspann|ending|outro|ed|end credits)\b", re.I)


def markers(item_id):
    it = db.one("SELECT media, duration FROM items WHERE id=?", (item_id,))
    if not it or not it["media"]:
        return []
    chs = json.loads(it["media"]).get("chapters") or []
    out = []
    for c in chs:
        t = c.get("title") or ""
        if INTRO.search(t) and c["end"] > c["start"] and c["end"] - c["start"] < 300:
            out.append({"type": "intro", "start": c["start"], "end": c["end"]})
        elif CREDITS.search(t) and (not it["duration"] or c["start"] > it["duration"] * 0.6):
            out.append({"type": "credits", "start": c["start"], "end": c["end"]})
    return out


def init(route, H):
    pass
