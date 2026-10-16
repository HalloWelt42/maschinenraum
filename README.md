# Maschinenraum

Ein Ort für alle Dienste eines Rechners, die neben einem Modell-Läufer laufen: Sprachsynthese, Spracherkennung,
Bilderzeugung, Musik und was sonst als eigener Prozess Speicher belegt. Statt dass jedes Projekt seine Dienste
irgendwo im Hintergrund startet, stehen sie hier in einer Liste: was läuft, wie viel Speicher es belegt, starten,
anhalten, neu starten, Protokoll lesen. Dazu der Speicher des ganzen Rechners nach Herkunft.

- **Oberfläche im Browser** unter `http://127.0.0.1:8540/`, nur auf diesem Rechner erreichbar.
- **Menüleistensymbol** auf dem Mac: Dienste mit Schaltern, Speicher, Oberfläche öffnen.
- **Übersteht Neustarts:** läuft als launchd- oder systemd-Dienst; was laufen soll, startet wieder.
- **Abstürze** werden mit Pausen neu gestartet; stürzt ein Dienst zu oft ab, bleibt er aus.
- **Optional mit Leitstelle:** eine Leitstelle im Netz kann die Dienste mit einplanen, starten und anhalten
  und sieht den echten Speicher dieses Rechners. Ohne sie arbeitet der Maschinenraum genauso.

## Zusammenspiel mit der Leitstelle

Maschinenraum und [Leitstelle](https://github.com/HalloWelt42/leitstelle) gehören zusammen. Der Maschinenraum ist je
Rechner die zweite Stelle neben dem Modell-Läufer: Er bündelt alles, was der Modell-Läufer nicht verwaltet, und ist
für sich allein bedienbar. Mit einer Leitstelle geht jeder Zugriff nur noch über sie: Anwendungen rufen die
Leitstelle, die Leitstelle startet, misst und erreicht die Dienste über den Maschinenraum.

```
Anwendungen  ->  Leitstelle  ->  Modell-Läufer      (Sprachmodelle)
                             ->  Maschinenraum      (alle übrigen Dienste, je Rechner)
```

## Installieren

Python 3.11 oder neuer; für die Oberfläche Node, für das Menüleistensymbol die Befehlszeilenwerkzeuge von Xcode.

```bash
git clone https://github.com/HalloWelt42/maschinenraum.git && cd maschinenraum && ./installieren.sh
```

Das Skript legt den Ordner `~/Maschinenraum` an, installiert das Programm in ein eigenes venv und richtet es als
Dienst ein. Derselbe Befehl aktualisiert; Dienstdateien, Einstellungen und Sollzustand bleiben.

## Der Ordner

| Pfad | Inhalt |
|---|---|
| `einstellungen.toml` | Port der Oberfläche, Messtakt, Neustartregeln, optional die Leitstelle |
| `dienste/<kennung>.toml` | je Dienst eine Datei; der Dateiname ist die Kennung |
| `protokolle/maschinenraum.log` | Ausgabe des Maschinenraums |
| `protokolle/<kennung>.log` | Ausgabe des Dienstes |
| `zustand.json` | Sollzustand je Dienst und gemessene Höchstwerte |
| `schluessel` | Schlüssel für die Leitstelle, nur für den Benutzer lesbar |

Neue oder geänderte Dienstdateien liest der Maschinenraum im nächsten Takt; ein Neustart ist nicht nötig. Stand
ohne Oberfläche:

```bash
~/Maschinenraum/.venv/bin/maschinenraum --liste
```

## Dienstdatei

Beispiel: [beispiele/bildwerkstatt.toml](beispiele/bildwerkstatt.toml).

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `name` | Pflicht | Anzeigename |
| `ordner` | Pflicht | Arbeitsordner; `~` und `$VAR` werden aufgelöst |
| `befehl` | Pflicht | Programm und Argumente als Liste; ein relativer Programmpfad gilt ab `ordner`; `$NAME` kommt aus der Umgebung des Dienstes (auch aus `umgebung_datei`) |
| `vorher` | leer | Befehl, der vor jedem Start einmal läuft |
| `beschreibung` | leer | ein Satz für die Oberfläche |
| `oberflaeche` | keine | Adresse einer eigenen Oberfläche des Dienstes; die Karte bekommt einen Knopf zum Öffnen |
| `port` | keiner | erreichbar heißt: der Port nimmt Verbindungen an (IPv4 oder IPv6) |
| `pruefadresse` | keine | strenger: eine Antwort unter 500 von dieser Adresse |
| `faehigkeiten` | leer | `stimme`, `hoeren`, `bild_erzeugen`, `musik`, ... |
| `speicher_gb` | 1 | Schätzung, bis der Maschinenraum den Dienst gemessen hat |
| `startzeit_s` | 120 | so lange darf der Start bis zur Erreichbarkeit dauern |
| `anhaltezeit_s` | 20 | so lange darf das Beenden dauern, danach hart |
| `umgebung` | leer | zusätzliche Umgebungsvariablen |
| `umgebung_datei` | keine | Datei mit Zeilen `NAME=WERT`, zum Beispiel die `.env` eines Projekts |
| `pfad` | übliche Systempfade | Suchpfad für Programme |
| `neustart` | ja | nach einem Absturz neu starten, solange der Dienst laufen soll |
| `leitstelle_anhalten` | ja | die Leitstelle darf ihn anhalten, wenn ein Modell den Speicher braucht und er nicht arbeitet; nein: nur hier von Hand |
| `aktiv_ab_prozent` | 5 | ab dieser Prozessorlast (Prozent eines Kerns) gilt er als arbeitend; arbeitende Dienste hält die Leitstelle nicht an |


## Abgrenzung je Dienst

Jeder Dienst läuft in eigener Sitzung und Prozessgruppe, im eigenen Arbeitsordner, mit eigener Umgebung (nur
Suchpfad, Heimordner, Sprache und was die Datei nennt) und schreibt in eine eigene Protokolldatei. Anhalten
trifft genau seine Prozessgruppe: erst freundlich, nach `anhaltezeit_s` hart. Dienste, die die Grafik des Mac
nutzen, laufen nativ; Container haben dort keinen Zugriff auf die Grafik.

Läuft ein Dienst schon, ohne vom Maschinenraum gestartet zu sein (sein Port antwortet), übernimmt er ihn:
er misst ihn und kann ihn anhalten (den lauschenden Prozess und dessen Nachfahren), startet ihn aber nicht
doppelt. Der nächste Start geschieht dann durch den Maschinenraum.


## Speicherbedarf

Je Dienst gibt es zwei Zahlen. **Jetzt** ist, was seine Prozesse gerade belegen. **Bedarf** ist, was er laufend
braucht: der höchste je gemessene Wert, mindestens die Schätzung `speicher_gb` der Dienstdatei. Viele Dienste laden
ihre Modelle erst beim ersten Auftrag; gleich nach dem Start belegen sie wenig. Eine Leitstelle plant deshalb mit dem
Bedarf und hält so Platz frei, rechnet aber nur den Ist-Wert als belegt.

## Einstellungen

`einstellungen.toml` schreibt der Maschinenraum selbst, wenn die Oberfläche etwas ändert. Abschnitte und Vorgaben:

| Abschnitt | Feld | Vorgabe | Bedeutung |
|---|---|---|---|
| | `name` | Rechnername | Anzeigename |
| `oberflaeche` | `adresse`, `port` | 127.0.0.1, 8540 | wo die Oberfläche lauscht; nur 127.0.0.1 ist vor dem Netz geschützt |
| `messung` | `takt_s` | 5 | Abstand der Messungen und der Dienstprüfung |
| `messung` | `macmon` | ja | auf dem Mac Grafik, Temperatur und Leistung über macmon, wenn installiert |
| `neustart` | `pausen_s` | 5, 30, 120 | Pausen vor dem ersten, zweiten, dritten Neustart nach Absturz |
| `neustart` | `fenster_s`, `im_fenster` | 600, 3 | mehr Abstürze im Zeitraum: der Dienst bleibt aus |
| `leitstelle` | `adresse` | keine | Basisadresse einer Leitstelle; den Schlüssel trägt man in der Oberfläche ein |
| `durchleitung` | `adresse`, `port` | 0.0.0.0, 8541 | Weg der Leitstelle zu den Diensten, nur mit Schlüssel |
| `nachbar` | `modell_laeufer` | http://127.0.0.1:1234 | Modell-Läufer auf diesem Rechner, nur zur Anzeige |

## Nur über die Leitstelle

Ist eine Leitstelle eingetragen, ist sie der einzige Weg zu den Diensten: Die Dienste lauschen nur auf diesem
Rechner (`127.0.0.1`), Anwendungen rufen die Leitstelle (`/v1/dienste/<kennung>/<pfad>`), und die Leitstelle reicht
über die **Durchleitung** des Maschinenraums durch (Port 8541, Abschnitt `durchleitung` der Einstellungen). Die
Durchleitung nimmt nur Anfragen mit dem Schlüssel dieses Maschinenraums an und nur an Dienste, die laufen; Anfrage
und Antwort gehen unverändert hindurch, auch Audio und Bilder. Die Leitstelle startet einen Dienst dabei bei Bedarf,
plant seinen Speicher ein und hält ihn bei Speichernot wieder an, wenn seine Dienstdatei das erlaubt.

## Schnittstelle

| Aufruf | Wirkung |
|---|---|
| `GET /api/stand` | alle Dienste, Messwerte, Leitstelle, Modell-Läufer |
| `POST /api/dienste/<kennung>/starten`, `/anhalten`, `/neustarten` | schalten; Antwort mit Erfolg und Meldung |
| `GET /api/dienste/<kennung>/protokoll?zeilen=200` | Ende der Protokolldatei |
| `PUT /api/leitstelle` | Adresse und Schlüssel der Leitstelle setzen oder entfernen |

Schreibende Aufrufe brauchen den Kopf `X-Maschinenraum: 1`, und es gelten nur die Rechnernamen dieses Rechners.
So kann keine fremde Webseite im selben Browser Dienste schalten.

## Was gemessen wird

Speicher auf dem Mac: belegt = (anonyme Seiten - löschbare + fest verdrahtete + Kompressor) mal Seitengröße;
das entspricht den Systemanzeigen. Auf Linux: Gesamt minus verfügbar. Dazu Swap, freie Platte, Last; auf Linux
Prozessorlast und Temperatur, auf dem Mac mit macmon Prozessor, Grafik, Temperatur und Leistung. Je Dienst
der Speicher seiner Prozesse (Mac: physischer Fußabdruck, Linux: PSS).

## Entwickeln

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]" && .venv/bin/python -m pytest
```

```bash
cd frontend && npm install && npm run pruefen && npm run build
```

Oberfläche mit Neuladen: `cd frontend && npm run dev` (Port 5540, Schnittstelle vom laufenden Maschinenraum).
Nach Änderungen an den Pydantic-Modellen `npm run typen`.

---

## Lizenz

**Nicht-kommerzielle Nutzung** - Siehe [LICENSE](LICENSE)

Erlaubt: Private Nutzung, Installation, persönliche Anpassungen, Teilen mit Quellenangabe

Verboten: Kommerzielle Nutzung, Verkauf, Einbindung in kommerzielle Produkte

---

## Unterstützen

Maschinenraum ist ein privates Hobby-Projekt. Kein Tracking, keine Werbung, keine Kompromisse.

Wenn dir das Projekt gefällt, kannst du ihm einen Stern geben - oder direkt hier:

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/HalloWelt42)

**Crypto:**

| Coin | Adresse |
|------|---------|
| BTC | `bc1qnd599khdkv3v3npmj9ufxzf6h4fzanny2acwqr` |
| DOGE | `DL7tuiYCqm3xQjMDXChdxeQxqUGMACn1ZV` |
| ETH | `0x8A28fc47bFFFA03C8f685fa0836E2dBe1CA14F27` |

Copyright (c) 2026 HalloWelt42
