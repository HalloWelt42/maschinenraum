---
zweck: "Startet, misst und hält die KI-Dienste des Macs (Sprache, Bild, Musik) nach Dienstdateien, meldet der Leitstelle den echten Speicher und reicht ihre Anfragen an die Dienste durch."
geraet: [mac]
abhaengigkeiten: [leitstelle]
daten:
  - "Mac: `~/Maschinenraum` mit `einstellungen.toml`, `dienste/` (eine Datei je Dienst), `zustand.json` (Sollzustand), `betrieb/` (Einträge anderer Programme, etwa des Stellwerks), `protokolle/`"
  - "Mac: `~/Maschinenraum/modelle`, die Modellablage aller Dienste (rund 230 GB)"
sicherung:
  - "kein eigenes Werkzeug (Stand 24.10.2026); `~/Maschinenraum` gehört zur Sicherung des Macs (siehe Grundlage Mac). Dienstdateien entstehen bei der Installation der Dienste neu, die Modelle lassen sich neu laden"
schluessel_orte:
  - "Mac: `~/Maschinenraum/schluessel`, Modus 0600: Schlüssel des Knotens bei der Leitstelle, zugleich Zugang der Durchleitung"
  - "Leitstelle: das Gegenstück unter Knoten (im Tresor der Leitstelle)"
einrichten: einrichten.sh
stand: cdd9903
---

# Maschinenraum

## Zweck

Der Maschinenraum ist die zweite Stelle neben dem Modell-Läufer auf dem Mac: er verwaltet alle übrigen KI-Modelle und
Dienste, die nicht im Modell-Läufer laufen, etwa die Sprachdienste des [[Klangwerk]], Bilderzeugung und Musik, und
meldet sie der [[Leitstelle]] als alternative Anbindung. Die Leitstelle ist die zentrale Steuerung und Überwachung;
den Modell-Läufer spricht sie direkt an. Jeder Dienst steht als eigene Datei in `~/Maschinenraum/dienste/` (Befehl, Port, Fähigkeiten,
Speicherbedarf); der Maschinenraum startet ihn in eigener Prozessgruppe, prüft, ob er antwortet, misst Speicher und
Last, startet ihn nach einem Absturz begrenzt neu und hält ihn an. Als Knoten-Agent der Leitstelle meldet er den
gemessenen Speicher des Macs und nimmt ihre Befehle an (Dienst starten, anhalten), und über die Durchleitung reicht er
ihre Anfragen roh an seine Dienste weiter. Er meldet ihr außerdem, was an ihr vorbei auf Modelle des Macs zugreift (fremde Verbindungen
zum Läufer, große Speicherverbraucher außerhalb der Dienste), und die Last: je Prozess des Läufers (Rolle, Modelldatei,
Kerne, Speicher) und die Fremdlast des Macs ohne Läufer und Dienste. Auf ihren Befehl beendet er einen Arbeiter des
Läufers, der ohne Auftrag rechnet, nie den Hauptprozess.

Ohne Maschinenraum hört und spricht im Verbund niemand: die Leitstelle kann die Sprachdienste am Mac weder starten
noch erreichen.

Er läuft als launchd-Dienst `maschinenraum` mit Oberfläche im Browser (nur dieser Rechner, Vorgabe Port 8540) und
Durchleitung für die Leitstelle (im Netz, Vorgabe Port 8541); dazu ein Symbol in der Menüleiste, das auch das
[[Stellwerk]] zeigt. Die Ports stehen als Vorgabe in `maschinenraum/konfig.py` und lassen sich in
`einstellungen.toml` ändern.

## Was sie braucht

- Mac nach [[Grundlage Mac]]: Python ab 3.11, Node.js für die Oberfläche, Xcode für das Symbol in der Menüleiste
  (`swiftc`), macmon für Grafik, Temperatur und Leistung.
- [[Leitstelle]]: dort unter Knoten der Mac mit "Maschinenraum verbinden"; der Maschinenraum braucht ihre Adresse und
  den Schlüssel des Knotens.
- Die Modellablage `~/Maschinenraum/modelle` (siehe [[Grundlage Mac]]); jeder Dienst bekommt sie als
  `MASCHINENRAUM_MODELLE` und `HF_HUB_CACHE`.

## Neu einrichten

Zwei Wege. Aus der Sicherung: den Ordner `~/Maschinenraum` vor der Installation zurückspielen (Einstellungen mit der
Adresse der Leitstelle, Schlüssel, Dienstdateien, Sollzustand, Modelle); die Installation lässt ihn stehen, und der
Mac ist wieder Knoten wie vorher. Frisch: die Installation legt den Ordner leer an; dann in der Leitstelle neu
verbinden und die Dienste mit ihren eigenen Installationen eintragen.

### 1. Klon und Installation

```
git clone {{repo}} {{ordner}}
cd {{ordner}} && ./einrichten.sh
```

`./einrichten.sh` ruft `./installieren.sh`: Ordner `~/Maschinenraum` (Modus 700), Programm in eigenem venv
(`~/Maschinenraum/.venv`), Oberfläche bauen, launchd-Dienst `maschinenraum` (startet mit der Anmeldung) und das Symbol
in der Menüleiste (`~/Applications/Maschinenraum.app`, launchd `maschinenraum.menueleiste`). Eine erneute Installation
aktualisiert und wartet, bis keine Anfrage der Leitstelle mehr durchgereicht wird.

Probe: `curl -s http://127.0.0.1:8540/api/version` meldet `{"version":"{{fassung}}"}`, und
`launchctl print gui/$(id -u)/maschinenraum | grep state` zeigt `running`.

### 2. Mit der Leitstelle verbinden

Aus der Sicherung schon erledigt. Frisch in der [[Leitstelle]] unter Knoten beim Mac "Maschinenraum verbinden"; dann in
der Oberfläche des Maschinenraums (http://127.0.0.1:8540/) unter Leitstelle Adresse und Schlüssel eintragen. Der
Schlüssel landet in `~/Maschinenraum/schluessel` (Modus 0600).

Probe: in der Leitstelle unter Knoten meldet der Mac seinen gemessenen Speicher, und in der Oberfläche des
Maschinenraums steht die Leitstelle auf verbunden.

### 3. Dienste eintragen

Aus der Sicherung liegen die Dienstdateien schon in `~/Maschinenraum/dienste/`. Frisch kommen sie mit der Installation
der Dienste (etwa `./installieren.sh` im [[Klangwerk]]); jede Datei nennt Befehl, Port, Prüfadresse und Fähigkeiten.
Eine fehlerhafte Datei hält ihren Dienst nicht an: er läuft mit der letzten gültigen Fassung weiter, der Fehler steht
unter Ladefehler.

Probe: die Oberfläche zeigt unter Dienste jeden Dienst mit Zustand;
`~/Maschinenraum/.venv/bin/python -m maschinenraum --liste` zeigt dasselbe auf der Befehlszeile.

## Sicherung und Rückspielen

Ein eigenes Sicherungswerkzeug gibt es nicht (Stand 24.10.2026), das Werkzeug Sicherungen holt nichts vom
Maschinenraum. Wichtig sind `einstellungen.toml`, `schluessel`, `dienste/` und `zustand.json` in `~/Maschinenraum`; sie
gehören zur Sicherung des Macs (siehe [[Grundlage Mac]]). Die Modellablage ist groß und lässt sich neu laden, das
dauert aber Stunden. Zurückspielen: den Ordner an seinen Ort legen (Modus 700, `schluessel` 600), dann Schritt 1.

## Wenn etwas klemmt

- Ein Dienst startet nicht: unter Dienste die Ladefehler und das Protokoll des Dienstes ansehen
  (`~/Maschinenraum/protokolle/<dienst>.log`); fehlt ein Modell, steht das dort.
- Die Leitstelle sieht den Mac nicht: Adresse oder Schlüssel unter Leitstelle falsch, oder der Mac schläft (der
  Maschinenraum meldet das Einschlafen; Aufträge warten dann in den Apps).
- Nach einer Installation reagiert nichts: `launchctl print gui/$(id -u)/maschinenraum` und
  `~/Maschinenraum/protokolle/start.log` ansehen.
- Das Symbol fehlt in der Menüleiste: `swiftc` fehlte bei der Installation (Xcode), dann erneut installieren.
- Nach einem Neustart des Maschinenraums laufen weitere Instanzen eines Dienstes (`<dienst>.2` und so weiter) weiter:
  er findet sie über `zustand.json` und ihre Ports wieder und meldet sie der Leitstelle; was nicht mehr läuft, startet
  er nicht neu.
- Die Leitstelle zeigt beim Mac keine Läufer-Prozesse: `lsof` fehlt, kein Läufer eingetragen (`nachbar.modell_laeufer`)
  oder die Beobachtung ist aus (`beobachtung.aktiv`). Erkennt sie Arbeiter nicht, passen die Endungen in
  `beobachtung.modelldateien` nicht zu den Modelldateien des Läufers.
