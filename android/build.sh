#!/bin/sh
# Baut Lichtspiel TV als signiertes APK nach dist/lichtspiel.apk.
# Aufruf: ./build.sh [vorbelegte Server-Adresse]   z. B. ./build.sh http://192.168.1.240:8400
# Braucht JDK 17+ (JAVA_HOME), Gradle (GRADLE oder im PATH) und das Android-SDK (ANDROID_HOME bzw. local.properties).
# Der Signaturschlüssel wird beim ersten Lauf in signing/ erzeugt – SICHERN, sonst sind keine Updates möglich.
set -eu
cd "$(dirname "$0")"
SERVER="${1:-http://}"
GRADLE="${GRADLE:-gradle}"
if [ ! -f signing/keystore.properties ]; then
  mkdir -p signing
  PASS=$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')
  keytool -genkeypair -keystore signing/release.jks -storepass "$PASS" -keypass "$PASS" -alias lichtspiel \
    -keyalg RSA -keysize 3072 -validity 36500 -dname "CN=Lichtspiel" >/dev/null 2>&1
  printf 'storeFile=signing/release.jks\nstorePassword=%s\nkeyAlias=lichtspiel\nkeyPassword=%s\n' "$PASS" "$PASS" > signing/keystore.properties
  chmod 600 signing/keystore.properties signing/release.jks
  echo "Neuer Signaturschlüssel: signing/ (bitte sichern)"
fi
$GRADLE --console=plain -q assembleRelease -PdefaultServer="$SERVER"
mkdir -p dist
cp app/build/outputs/apk/release/app-release.apk dist/lichtspiel.apk
echo "App gebaut: dist/lichtspiel.apk"
