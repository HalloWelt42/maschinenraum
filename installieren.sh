#!/bin/sh
# Maschinenraum installieren oder aktualisieren, für den angemeldeten Benutzer. Aufruf aus dem Projektordner:
#
#   ./installieren.sh
#
# Legt den Ordner ~/Maschinenraum an (oder MASCHINENRAUM_ORDNER), installiert das Programm in ein eigenes venv,
# baut die Oberfläche (wenn Node vorhanden ist) und richtet es als Dienst ein, der Neustarts übersteht:
# macOS launchd (startet mit der Anmeldung), Linux systemd im Benutzerkontext. Auf dem Mac kommt das
# Menüleistensymbol dazu. Dienstdateien, Einstellungen, Schlüssel und Sollzustand bleiben bei einer Aktualisierung.
# Ein Ordner des früheren Knoten-Agenten (~/Leitstelle-Agent) wird einmal übernommen.
set -eu

HIER="$(cd "$(dirname "$0")" && pwd)"
ORDNER="${MASCHINENRAUM_ORDNER:-$HOME/Maschinenraum}"
PYTHON="${PYTHON:-python3}"
KENNUNG="maschinenraum"
ALT="$HOME/Leitstelle-Agent"

meldung() { printf '%s\n' "$*"; }
abbruch() { printf 'Abbruch: %s\n' "$*" >&2; exit 1; }

command -v "$PYTHON" >/dev/null || abbruch "$PYTHON fehlt (Python 3.11 oder neuer)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || abbruch "Python 3.11 oder neuer nötig ($PYTHON)"

mkdir -p "$ORDNER/dienste" "$ORDNER/protokolle"
chmod 700 "$ORDNER"

# ── Übernahme aus dem früheren Knoten-Agenten ────────────────────────────
if [ -d "$ALT" ] && [ ! -f "$ORDNER/zustand.json" ]; then
  meldung "Übernehme $ALT"
  cp -n "$ALT"/dienste/*.toml "$ORDNER/dienste/" 2>/dev/null || true
  [ -f "$ALT/zustand.json" ] && cp "$ALT/zustand.json" "$ORDNER/zustand.json"
  [ -f "$ALT/schluessel" ] && ( umask 077; cp "$ALT/schluessel" "$ORDNER/schluessel" )
  ADRESSE="$(sed -n 's/^leitstelle *= *"\(.*\)"/\1/p' "$ALT/agent.toml" 2>/dev/null | head -1)"
  if [ -n "$ADRESSE" ] && [ ! -f "$ORDNER/einstellungen.toml" ]; then
    printf '[leitstelle]\nadresse = "%s"\n' "$ADRESSE" > "$ORDNER/einstellungen.toml"
  fi
  if [ "$(uname -s)" = "Darwin" ]; then
    launchctl bootout "gui/$(id -u)/leitstelle.agent" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/leitstelle.agent.plist"
  else
    systemctl --user disable --now leitstelle-agent.service 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/leitstelle-agent.service"
  fi
  meldung "Der alte Ordner $ALT bleibt liegen und kann gelöscht werden."
fi

# ── Oberfläche bauen und Programm installieren ───────────────────────────
if command -v npm >/dev/null; then
  ( cd "$HIER/frontend" && npm ci --no-audit --no-fund --silent && npm run build --silent )
elif [ ! -f "$HIER/maschinenraum/oberflaeche/index.html" ]; then
  meldung "Hinweis: ohne Node keine Oberfläche; die Schnittstelle läuft trotzdem."
fi
"$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$HIER/version.json" > "$HIER/maschinenraum/VERSION"
[ -d "$ORDNER/.venv" ] || "$PYTHON" -m venv "$ORDNER/.venv"
"$ORDNER/.venv/bin/pip" install --quiet --upgrade pip
"$ORDNER/.venv/bin/pip" install --quiet --upgrade --force-reinstall --no-deps "$HIER"
"$ORDNER/.venv/bin/pip" install --quiet "$HIER"
rm -f "$HIER/maschinenraum/VERSION"
PY="$ORDNER/.venv/bin/python"
PORT="$("$PY" -c "from maschinenraum.konfig import Ordner; from pathlib import Path; print(Ordner(Path('$ORDNER')).einstellungen().oberflaeche.port)")"

# ── Als Dienst einrichten ────────────────────────────────────────────────
launchd_laden() {   # Abmelden läuft im Hintergrund weiter; erst neu laden, wenn der alte Dienst weg ist
  launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    launchctl print "gui/$(id -u)/$1" >/dev/null 2>&1 || break
    sleep 0.5
  done
  launchctl bootstrap "gui/$(id -u)" "$2"
}

case "$(uname -s)" in
  Darwin)
    mkdir -p "$HOME/Library/LaunchAgents"
    PLIST="$HOME/Library/LaunchAgents/$KENNUNG.plist"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$KENNUNG</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>maschinenraum</string><string>$ORDNER</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string><key>LANG</key><string>de_DE.UTF-8</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$ORDNER/protokolle/start.log</string>
  <key>StandardErrorPath</key><string>$ORDNER/protokolle/start.log</string>
</dict>
</plist>
EOF
    launchd_laden "$KENNUNG" "$PLIST"
    meldung "Maschinenraum läuft als launchd-Dienst $KENNUNG (startet mit der Anmeldung)."
    if [ -x "$HIER/menueleiste/bauen.sh" ] && command -v swiftc >/dev/null; then
      "$HIER/menueleiste/bauen.sh" "$HOME/Applications" "$PORT"
      MPLIST="$HOME/Library/LaunchAgents/$KENNUNG.menueleiste.plist"
      cat > "$MPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$KENNUNG.menueleiste</string>
  <key>ProgramArguments</key><array><string>$HOME/Applications/Maschinenraum.app/Contents/MacOS/Maschinenraum</string></array>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
EOF
      launchd_laden "$KENNUNG.menueleiste" "$MPLIST"
      meldung "Menüleistensymbol eingerichtet (~/Applications/Maschinenraum.app)."
    fi
    ;;
  Linux)
    UNIT="$HOME/.config/systemd/user/$KENNUNG.service"
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<EOF
[Unit]
Description=Maschinenraum
After=network-online.target

[Service]
ExecStart=$PY -m maschinenraum $ORDNER
Restart=always
RestartSec=10
KillMode=process
StandardOutput=append:$ORDNER/protokolle/start.log
StandardError=append:$ORDNER/protokolle/start.log

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$KENNUNG.service"
    systemctl --user restart "$KENNUNG.service"
    meldung "Maschinenraum läuft als systemd-Dienst im Benutzerkontext."
    if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || echo no)" != "yes" ]; then
      meldung "Damit er ohne Anmeldung startet, einmal mit Verwalterrechten: sudo loginctl enable-linger $(id -un)"
    fi
    ;;
  *) abbruch "unbekanntes Betriebssystem $(uname -s)" ;;
esac

meldung "Oberfläche: http://127.0.0.1:$PORT/"
meldung "Ordner: $ORDNER (Dienste unter dienste/, Ausgaben unter protokolle/)"
