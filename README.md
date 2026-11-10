# Lichtspiel

## About

**Lichtspiel** is a self-hosted media server for your own movies and TV shows, with a web interface, an Android TV app,
live TV (IPTV), self-made TV channels built from your library, internet radio and viewing statistics.

It has **no third-party dependencies**: the server uses only the Python standard library (3.9+) plus an installed
`ffmpeg`/`ffprobe`, the web UI is plain HTML/CSS/JavaScript, and the Android TV app is plain Java against the Android SDK.
It does not contact any online services – metadata and artwork come from NFO files and images in your media folders.
Released into the public domain (The Unlicense).

**Features**

- Movie and TV show libraries from folders; metadata from NFO files (Kodi/tinyMediaManager format), artwork from the folder
- Direct play, remux or H.264 transcoding per device; text subtitles as WebVTT, image subtitles burned in
- Multiple profiles with resume, “continue watching”, “next episode”, favorites and watched state
- Player with chapters, playback speed, sleep timer, remaining time, pause screen and intro/credits markers
- Live TV from your own M3U/M3U8 lists with XMLTV program guide
- Channel overview for live TV and custom channels: random “stage” with zapping, live snapshots, groups, favorites, search
- Custom TV channels: movies and episodes from your libraries playing as a continuous schedule
- Internet radio: stations added by hand or imported from M3U/M3U8/PLS, streamed as MP3, “now playing” from ICY metadata
- Viewing statistics, live activity, screensaver, per-user access rights
- Android TV app (Android 8+)

**Screenshots:** see [`docs/screenshots/`](docs/screenshots/).

> **Note: the UI is German only.**

---

Eigener Medienserver mit Weboberfläche, Android-TV-App, Live-TV, eigenen TV-Sendern, Radio und Statistik.

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

Bildschirmfotos: [`docs/screenshots/`](docs/screenshots/)

## Funktionen

- **Bibliotheken** für Filme und Serien aus Ordnern, Metadaten aus NFO-Dateien, Bilder aus dem Ordner, Medieninfos per ffprobe
- **Profile** („Wer schaut?“) mit Fortschritt, Weiterschauen, Nächste Folge, Favoriten und Gesehen-Status
- **Player** mit Kapiteln, Tempo, Schlaf-Timer, Restzeit, Pause-Ansicht und Intro-/Abspann-Marken
- **Live-TV** aus eigenen M3U/M3U8-Listen mit Programmführer (XMLTV)
- **Senderübersicht** für Live-TV und eigene Sender: Bühne mit zufälligem Sender und Weiterzappen, Standbilder,
  Gruppen, Favoriten, Suche
- **Eigene Sender:** Filme und Folgen aus den Bibliotheken laufen als Endlos-Programm
- **Radio:** selbst eingetragene Sender (von Hand oder als M3U/M3U8/PLS), Ton als MP3 über den Server,
  „Läuft gerade“ aus den ICY-Metadaten, Favoriten je Profil, Player-Leiste beim Blättern
- **Schnellzugriff** auf Favoriten, Radio und Bildschirmschoner
- **Statistik** und Aktivität, **Bildschirmschoner**, **Zugriffsrechte** je Benutzer für Bibliotheken, Live-TV,
  eigene Sender und Radio

## Aufbau

| Ordner | Inhalt |
|---|---|
| `server/` | `server.py` (HTTP + API), `db.py` (SQLite), `scanner.py` (Ordner, NFO, ffprobe), `nfo.py`, `stream.py` (Direkt/Remux/Umwandlung, Untertitel, Bilder), `live.py` (M3U/XMLTV), `channels.py` (eigene Sender), `radio.py` (Radio), `markers.py` (Intro/Abspann aus Kapiteln), `extras.py` (Statistik, Aktivität), `web/` |
| `android/` | TV-App `de.lichtspiel.tv` |
| `deploy/` | systemd-Dienst |
| `docs/screenshots/` | Bildschirmfotos |

## Server starten

    LS_DATA=/var/lib/lichtspiel LS_PORT=8400 python3 server/server.py

Im Browser `http://<server>:8400` öffnen, Administrator anlegen, unter *Einstellungen → Bibliotheken* Film- bzw.
Serienordner eintragen. Erwartete Ordnerstruktur:

- Filme: beliebig verschachtelt, je Film eine Videodatei, optional `<Name>.nfo`, `poster.jpg`, `backdrop.jpg`/`fanart.jpg`, `clearlogo.png`.
- Serien: `<Serie>/tvshow.nfo`, `poster.jpg`, … und darunter Staffelordner (`Staffel 1`, `Season 01`, `Specials`)
  mit Dateien wie `Serie - S01E02 - Titel.mkv` (+ `.nfo`, `.jpg`). Darstellerbilder in `.actors/Vorname_Nachname.jpg`.

Live-TV, eigene Sender und Radio werden ebenfalls im Browser unter *Einstellungen* eingerichtet.

### Als Dienst

    cp -r server/* /opt/lichtspiel/ && cp deploy/lichtspiel.service /etc/systemd/system/
    systemctl daemon-reload && systemctl enable --now lichtspiel

## Wiedergabe

Der Server entscheidet je Gerät: **Direkt** (Datei mit Range), **Remux** (Video kopiert, Ton ggf. nach AAC, als
fragmentiertes MP4) oder **Umwandeln** (H.264 über ffmpeg). Spulen bei Remux/Umwandlung startet den Datenstrom an der
neuen Stelle neu. Text-Untertitel (SRT/ASS/eingebettet) werden als WebVTT geliefert und von Web und App selbst
dargestellt, Bild-Untertitel (PGS/VobSub) werden eingebrannt.

Im Web-Player gibt es Kapitel, Tempo (0,75× bis 2×), einen Schlaf-Timer (nach Zeit oder am Ende des Titels),
die Restzeit und eine Pause-Ansicht mit Titel und Beschreibung. Enthält eine Datei Kapitel namens Intro/Vorspann oder
Abspann/Credits, werden sie als Marken angezeigt (in der TV-App mit „Intro überspringen“).

Radio-Sender spielt der Server immer als MP3 aus (ffmpeg), sodass auch HLS-Sender in jedem Browser laufen.

## TV-App bauen

    cd android
    JAVA_HOME=… GRADLE="gradle --offline" ./build.sh http://<server>:8400

Der Signaturschlüssel entsteht beim ersten Bau in `android/signing/` – **sichern**, sonst sind keine Updates möglich.
Installieren: `adb install -r dist/lichtspiel.apk`.

Bedienung im Player: OK = Pause, ←/→ = spulen (mehrfach drücken summiert), ↑ = Ton/Untertitel/Qualität,
Zurück = beenden. Live-TV: ↑/↓ bzw. Kanal +/- schaltet um.

Die TV-App enthält noch kein Radio.
