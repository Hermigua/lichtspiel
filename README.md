# Lichtspiel

Eigener Medienserver mit Weboberfläche, Android-TV-App, Live-TV, eigenen TV-Sendern und Statistik.

**Lizenzfrei:** Der gesamte Code ist selbst geschrieben und gemeinfrei (The Unlicense, siehe `LICENSE`).
Es wird kein fremder Code mitgeliefert:

- Server: nur Python-Standardbibliothek (ab 3.9). Für Medieninfos, Umwandlung, Untertitel und Bildgrößen ruft er
  das auf dem System installierte **ffmpeg/ffprobe** als eigenständiges Programm auf (wird nicht mitgeliefert).
- Weboberfläche: eigenes HTML/CSS/JavaScript ohne Bibliotheken; Videos laufen über den Browser selbst
  (Direktwiedergabe oder fragmentiertes MP4 vom Server – kein HLS-Abspieler nötig).
- TV-App: reines Java gegen das Android-SDK (MediaPlayer, HttpURLConnection, org.json) – kein AndroidX, kein Kotlin,
  keine Bild- oder Player-Bibliothek. Gebaut wird mit Gradle/Android-Gradle-Plugin (Werkzeuge, nicht im APK).
- Keine fremden Logos, Cover oder Senderlisten im Projekt. Metadaten und Bilder kommen aus den eigenen Medienordnern
  (NFO + Bilder, z. B. von einem Metadaten-Programm angelegt), Senderlisten und Programmdaten nur aus selbst eingetragenen Quellen.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `server/` | `server.py` (HTTP + API), `db.py` (SQLite), `scanner.py` (Ordner, NFO, ffprobe), `nfo.py`, `stream.py` (Direkt/Remux/Umwandlung, Untertitel, Bilder), `live.py` (M3U/XMLTV), `channels.py` (eigene Sender), `markers.py` (Intro/Abspann aus Kapiteln), `extras.py` (Statistik, Aktivität), `web/` |
| `android/` | TV-App `de.lichtspiel.tv` |
| `deploy/` | systemd-Dienst |

## Server starten

    LS_DATA=/var/lib/lichtspiel LS_PORT=8400 python3 server/server.py

Im Browser `http://<server>:8400` öffnen, Administrator anlegen, unter *Einstellungen → Bibliotheken* Film- bzw.
Serienordner eintragen. Erwartete Ordnerstruktur:

- Filme: beliebig verschachtelt, je Film eine Videodatei, optional `<Name>.nfo`, `poster.jpg`, `backdrop.jpg`/`fanart.jpg`, `clearlogo.png`.
- Serien: `<Serie>/tvshow.nfo`, `poster.jpg`, … und darunter Staffelordner (`Staffel 1`, `Season 01`, `Specials`)
  mit Dateien wie `Serie - S01E02 - Titel.mkv` (+ `.nfo`, `.jpg`). Darstellerbilder in `.actors/Vorname_Nachname.jpg`.

### Als Dienst

    cp -r server/* /opt/lichtspiel/ && cp deploy/lichtspiel.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now lichtspiel

## Wiedergabe

Der Server entscheidet je Gerät: **Direkt** (Datei mit Range), **Remux** (Video kopiert, Ton ggf. nach AAC, als
fragmentiertes MP4) oder **Umwandeln** (H.264 über ffmpeg). Spulen bei Remux/Umwandlung startet den Datenstrom an der
neuen Stelle neu. Text-Untertitel (SRT/ASS/eingebettet) werden als WebVTT geliefert und von Web und App selbst
dargestellt, Bild-Untertitel (PGS/VobSub) werden eingebrannt.

## TV-App bauen

    cd android
    JAVA_HOME=… GRADLE="gradle --offline" ./build.sh http://<server>:8400

Der Signaturschlüssel entsteht beim ersten Bau in `android/signing/` – **sichern**, sonst sind keine Updates möglich.
Installieren: `adb install -r dist/lichtspiel.apk`.

Bedienung im Player: OK = Pause, ←/→ = spulen (mehrfach drücken summiert), ↑ = Ton/Untertitel/Qualität,
Zurück = beenden. Live-TV: ↑/↓ bzw. Kanal +/- schaltet um.
