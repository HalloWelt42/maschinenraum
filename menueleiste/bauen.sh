#!/bin/sh
# Baut das Menüleistensymbol: menueleiste/bauen.sh <Zielordner> [Port]
# Ergebnis: <Zielordner>/Maschinenraum.app (nur Menüleiste, kein Dock-Symbol).
set -eu
HIER="$(cd "$(dirname "$0")" && pwd)"
ZIEL="${1:-$HOME/Applications}"
PORT="${2:-8540}"
FASSUNG="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$HIER/../version.json")"
APP="$ZIEL/Maschinenraum.app"
BAU="$HIER/build"

rm -rf "$BAU" && mkdir -p "$BAU"
xcrun swiftc -O -parse-as-library -swift-version 5 -target "$(uname -m)-apple-macos13" -o "$BAU/Maschinenraum" "$HIER/Maschinenraum.swift"

rm -rf "$APP" && mkdir -p "$APP/Contents/MacOS"
cp "$BAU/Maschinenraum" "$APP/Contents/MacOS/Maschinenraum"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Maschinenraum</string>
  <key>CFBundleIdentifier</key><string>maschinenraum.menueleiste</string>
  <key>CFBundleExecutable</key><string>Maschinenraum</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$FASSUNG</string>
  <key>CFBundleVersion</key><string>$FASSUNG</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>MaschinenraumPort</key><integer>$PORT</integer>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
EOF
codesign --force --sign - "$APP" >/dev/null 2>&1 || true
echo "Gebaut: $APP"
