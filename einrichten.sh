#!/usr/bin/env bash
# Einrichten des Maschinenraums. Schritte und Proben der Neueinrichtung stehen in docs/handbuch.md.
#
#   ./einrichten.sh                                       wie ./installieren.sh: Ordner ~/Maschinenraum, Programm in
#                                                         eigenem venv, Oberfläche, Dienst (launchd) und Menüleiste
#   ./einrichten.sh --probe --ziel DIR --port-versatz N   Probelauf des Handbuchs: Programm und Oberfläche in DIR, ein
#                                                         eigener Ordner DIR/ordner ohne Dienste und ohne Leitstelle,
#                                                         Oberfläche und Durchleitung nur an 127.0.0.1 und um N
#                                                         verschoben, gestartet als Prozess (kein launchd, keine
#                                                         Menüleiste, nichts in ~/Library/LaunchAgents)
#   ./einrichten.sh --probe --ziel DIR --abbauen          beendet den Prozess
set -euo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
WARTEN_S=60

probe_aufbauen() {
  local ziel="$1" versatz="$2" ordner="$1/ordner" py oberflaeche durchleitung
  cd "$ziel"
  ( cd frontend && npm ci --no-audit --no-fund --silent && npm run build --silent )
  "$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" version.json > maschinenraum/VERSION
  mkdir -p "$ordner"
  "$PYTHON" -m venv "$ziel/.venv"
  "$ziel/.venv/bin/pip" install --quiet --upgrade pip
  "$ziel/.venv/bin/pip" install --quiet "$ziel"
  py="$ziel/.venv/bin/python"
  # Ports aus den Vorgaben des Programms (maschinenraum/konfig.py), verschoben um den Versatz
  read -r oberflaeche durchleitung < <("$py" -c "from maschinenraum.konfig import Einstellungen as E; e = E(); print(e.oberflaeche.port, e.durchleitung.port)")
  oberflaeche=$(( oberflaeche + versatz )); durchleitung=$(( durchleitung + versatz ))
  cat > "$ordner/einstellungen.toml" <<EOF
# Probelauf des Handbuchs: ohne Leitstelle, ohne Läufer, ohne macmon und Schlafmeldung, nur an diesem Rechner
name = "Probelauf"

[oberflaeche]
adresse = "127.0.0.1"
port = $oberflaeche

[durchleitung]
adresse = "127.0.0.1"
port = $durchleitung

[messung]
macmon = false

[schlaf]
melden = false
leerlauf_aufschieben = false

[nachbar]
modell_laeufer = ""
EOF
  nohup "$py" -m maschinenraum "$ordner" > "$ziel/maschinenraum.log" 2>&1 &
  echo $! > "$ziel/maschinenraum.pid"
  local ende=$(( $(date +%s) + WARTEN_S ))
  while [ "$(date +%s)" -lt "$ende" ]; do
    if curl -sf "http://127.0.0.1:$oberflaeche/api/version" >/dev/null && curl -sf -o /dev/null "http://127.0.0.1:$oberflaeche/"; then
      echo "ANTWORTET http://127.0.0.1:$oberflaeche/api/version"
      return 0
    fi
    sleep 1
  done
  echo "Der Maschinenraum antwortet nach $WARTEN_S s nicht" >&2
  tail -n 40 "$ziel/maschinenraum.log" >&2 || true
  return 1
}

probe_abbauen() {
  local pid
  if [ -f "$1/maschinenraum.pid" ]; then
    pid="$(cat "$1/maschinenraum.pid")"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$1/maschinenraum.pid"
  fi
}

probe=0; abbauen=0; ziel=""; versatz=""
while [ $# -gt 0 ]; do
  case "$1" in
    --probe) probe=1 ;;
    --abbauen) abbauen=1 ;;
    --ziel) ziel="${2:?--ziel braucht einen Ordner}"; shift ;;
    --port-versatz) versatz="${2:?--port-versatz braucht eine Zahl}"; shift ;;
    *) echo "unbekannte Angabe: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$probe" = 0 ]; then
  exec "$HIER/installieren.sh"
elif [ -z "$ziel" ] || [ ! -d "$ziel" ]; then
  echo "--probe braucht --ziel mit einem vorhandenen Ordner" >&2; exit 2
elif [ "$abbauen" = 1 ]; then
  probe_abbauen "$(cd "$ziel" && pwd)"
else
  probe_aufbauen "$(cd "$ziel" && pwd)" "${versatz:?--port-versatz fehlt}"
fi
