#!/usr/bin/env bash
# Zertifikat der Durchleitung (HELF-166: im Heimnetz nur TLS) aus der Hausstelle dieses Macs (mkcert) für einen Rechner
# mit Maschinenraum, abgelegt in dessen Ordner zertifikate/ (durchleitung.pem, durchleitung-schluessel.pem):
#   tools/zertifikat.sh                          für diesen Mac
#   tools/zertifikat.sh alpha@192.168.178.42     für einen anderen Mac (per ssh; die Hausstelle bleibt hier)
#   tools/zertifikat.sh --pruefen [ziel]         nur prüfen: Zertifikat da und noch mindestens 60 Tage gültig
# Namen im Zertifikat: alle IPv4-Adressen des Rechners im Netz (die Leitstelle spricht ihn unter der Adresse an, von der
# er sich verbindet), sein Rechnername mit .local und sein Name im Heimnetz (handbuch netz). Danach den Maschinenraum neu
# starten (./einrichten.sh wartet, bis keine Anfrage mehr durchgereicht wird).
set -euo pipefail
pruefen=0
[ "${1:-}" = "--pruefen" ] && { pruefen=1; shift; }
ZIEL="${1:-}"
ORDNER_REL="Maschinenraum/zertifikate"

auf_ziel() { if [ -n "$ZIEL" ]; then ssh -o BatchMode=yes -o ConnectTimeout=8 "$ZIEL" "$1"; else bash -c "$1"; fi; }

if [ "$pruefen" = 1 ]; then
  auf_ziel "openssl x509 -in \"\$HOME/$ORDNER_REL/durchleitung.pem\" -noout -checkend 5184000 >/dev/null 2>&1 && test -f \"\$HOME/$ORDNER_REL/durchleitung-schluessel.pem\"" \
    && { echo "Zertifikat der Durchleitung da und noch mindestens 60 Tage gültig"; exit 0; } \
    || { echo "Zertifikat der Durchleitung fehlt oder läuft bald ab"; exit 1; }
fi

command -v mkcert >/dev/null || { echo "mkcert fehlt: das Zertifikat entsteht nur am Mac mit der Hausstelle" >&2; exit 1; }
ADRESSEN="$(auf_ziel "ifconfig | awk '/inet /{print \$2}' | grep -v '^127\\.'" | tr '\n' ' ')"
RECHNER="$(auf_ziel "scutil --get LocalHostName 2>/dev/null || hostname -s")"
[ -n "${ADRESSEN// /}" ] || { echo "Keine Adresse im Netz gefunden" >&2; exit 1; }
NETZNAME=""
if command -v handbuch >/dev/null; then
  NETZNAME="$(handbuch netz --json 2>/dev/null | python3 -c '
import json, sys
adressen = set(sys.argv[1].split())
for g in json.load(sys.stdin)["geraete"]:
    if g.get("adresse") in adressen:
        print(g["netzname"]); break
' "$ADRESSEN" || true)"
fi
NAMEN="$ADRESSEN $RECHNER.local $NETZNAME"
ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT
# shellcheck disable=SC2086  # NAMEN ist eine Liste
(cd "$ARBEIT" && mkcert -cert-file durchleitung.pem -key-file durchleitung-schluessel.pem $NAMEN >/dev/null 2>&1)
auf_ziel "mkdir -p \"\$HOME/$ORDNER_REL\" && chmod 700 \"\$HOME/$ORDNER_REL\""
if [ -n "$ZIEL" ]; then
  scp -q "$ARBEIT/durchleitung.pem" "$ARBEIT/durchleitung-schluessel.pem" "$ZIEL:$ORDNER_REL/"
else
  cp "$ARBEIT/durchleitung.pem" "$ARBEIT/durchleitung-schluessel.pem" "$HOME/$ORDNER_REL/"
fi
auf_ziel "chmod 644 \"\$HOME/$ORDNER_REL/durchleitung.pem\" && chmod 600 \"\$HOME/$ORDNER_REL/durchleitung-schluessel.pem\""
echo "Zertifikat der Durchleitung für $NAMEN abgelegt in ${ZIEL:+$ZIEL:}~/$ORDNER_REL, gültig bis $(openssl x509 -in "$ARBEIT/durchleitung.pem" -noout -enddate | cut -d= -f2)"
