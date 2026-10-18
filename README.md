# Maschinenraum

Ein Ort für alle KI-Dienste eines Rechners, die neben einem Modell-Läufer laufen: Sprachsynthese, Spracherkennung,
Bilderzeugung, Musik und was sonst ein Modell hält und eine Fähigkeit anbietet. Statt dass jedes Projekt seine Modelle
irgendwo im Hintergrund lädt, stehen sie hier in einer Liste: was läuft, wie viel Speicher es belegt, starten,
anhalten, neu starten, Protokoll lesen. Dazu der Speicher des ganzen Rechners nach Herkunft.

Der Maschinenraum nimmt nur KI-Dienste an: jede Dienstdatei braucht mindestens eine Fähigkeit. Eigene Webapps, ihre
Datenbanken und Docker verwaltet das [Stellwerk](https://github.com/HalloWelt42/stellwerk); sie nutzen KI nur über die
Leitstelle.

- **Oberfläche im Browser** unter `http://127.0.0.1:8540/`, nur auf diesem Rechner erreichbar.
- **Menüleistensymbol** auf dem Mac, das zentrale Steuerwerk des Rechners: KI-Dienste mit Schaltern, Speicher, darunter
  der Betrieb (Stellwerk starten, anhalten, öffnen und seine Webapps schalten) und der Weg zur Leitstelle.
- **Übersteht Neustarts:** läuft als launchd- oder systemd-Dienst; was laufen soll, startet wieder.
- **Abstürze** werden mit Pausen neu gestartet; stürzt ein Dienst zu oft ab, bleibt er aus.
- **Optional mit Leitstelle:** eine Leitstelle im Netz kann die Dienste mit einplanen, starten und anhalten
  und sieht den echten Speicher dieses Rechners. Ohne sie arbeitet der Maschinenraum genauso.

## Zusammenspiel mit der Leitstelle

Maschinenraum und [Leitstelle](https://github.com/HalloWelt42/leitstelle) gehören zusammen. Der Maschinenraum ist je
Rechner die zweite Stelle neben dem Modell-Läufer: Er bündelt alle KI-Dienste, die der Modell-Läufer nicht verwaltet,
etwa die des [Klangwerks](https://github.com/HalloWelt42/klangwerk), und ist für sich allein bedienbar. Mit einer
Leitstelle geht jeder Zugriff nur noch über sie: Anwendungen rufen die Leitstelle, die Leitstelle startet, misst und
erreicht die Dienste über den Maschinenraum.

```
Webapps (Stellwerk)  ->  Leitstelle  ->  Modell-Läufer      (Sprachmodelle)
                                     ->  Maschinenraum      (übrige KI-Dienste, je Rechner)
```

Starten, Anhalten, Abhängigkeiten, Neustarts, Sollzustand und Prozessmessung teilen sich Maschinenraum und Stellwerk
über den [Dienstkern](https://github.com/HalloWelt42/dienstkern).

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
| `einstellungen.toml` | Port der Oberfläche, Messtakt, Neustartregeln, Schlaf, optional die Leitstelle |
| `dienste/<kennung>.toml` | je KI-Dienst eine Datei; der Dateiname ist die Kennung |
| `protokolle/maschinenraum.log` | Ausgabe des Maschinenraums |
| `protokolle/<kennung>.log` | Ausgabe des Dienstes |
| `zustand.json` | Sollzustand je Dienst und gemessene Höchstwerte |
| `betrieb/<kennung>.toml` | Steuerprogramme des Rechners (etwa das Stellwerk), von deren Installation eingetragen |
| `betrieb.json` | Sollzustand der Steuerprogramme |
| `schluessel` | Schlüssel für die Leitstelle, nur für den Benutzer lesbar; jeder Rechner braucht seinen eigenen (in der Leitstelle auf der Karte des Rechners ausgestellt). Einen Ordner mit Schlüssel auf einen zweiten Mac kopieren heißt: beide melden sich als derselbe Rechner und trennen sich gegenseitig |

Neue oder geänderte Dienstdateien liest der Maschinenraum im nächsten Takt; ein Neustart ist nicht nötig. Stand
ohne Oberfläche:

```bash
~/Maschinenraum/.venv/bin/maschinenraum --liste
```

## Dienstdatei

Beispiel: [beispiele/bildwerkstatt.toml](beispiele/bildwerkstatt.toml). Unbekannte Felder und Dateien ohne Fähigkeit
werden mit einer lesbaren Meldung übergangen.

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `name` | Pflicht | Anzeigename |
| `ordner` | Pflicht | Arbeitsordner; `~` und `$VAR` werden aufgelöst |
| `befehl` | Pflicht | Programm und Argumente als Liste; ein relativer Programmpfad gilt ab `ordner`; `$NAME` kommt aus der Umgebung des Dienstes (auch aus `umgebung_datei`) |
| `vorher` | leer | Befehl, der vor jedem Start einmal läuft |
| `beschreibung` | leer | ein Satz: wofür der Dienst gemacht ist; steht in der Oberfläche und geht als Zweck der Selbstauskunft an die Leitstelle |
| `oberflaeche` | keine | Adresse einer eigenen Oberfläche des Dienstes; die Karte bekommt einen Knopf zum Öffnen |
| `port` | keiner | erreichbar heißt: der Port nimmt Verbindungen an (IPv4 oder IPv6) |
| `pruefadresse` | keine | strenger: eine Antwort unter 500 von dieser Adresse |
| `faehigkeiten` | Pflicht | mindestens eine: `stimme`, `stimme_klonen`, `hoeren`, `sprecher_erkennen`, `sprecher_trennen`, `bild_erzeugen`, `musik`, ... |
| `eignung` | leer | wofür er besonders taugt, Wörter aus `denken`, `programmieren`, `lange_texte`, `schnell`, `gruendlich` (Selbstauskunft) |
| `sprachen` | leer | Sprachen, die er kann, als Kürzel nach ISO 639-1 (`de`, `en`); leer heißt nicht angegeben (Selbstauskunft) |
| `plaetze` | 1 | so viele Anfragen nimmt er gleichzeitig an; die Leitstelle teilt danach zu |
| `instanzen` | 1 | so viele Prozesse darf die Leitstelle bei Andrang starten; Instanz n heißt `<kennung>.<n>`, läuft auf `port + 100 (n-1)` und bekommt ihren Port in `MASCHINENRAUM_PORT` (im `befehl` als `$MASCHINENRAUM_PORT`, Pflicht ab 2). Weitere Instanzen leben nur im Speicher und folgen der Datei; angehalten sind sie weg |
| `speicher_gb` | 1 | Schätzung, bis der Maschinenraum den Dienst gemessen hat |
| `startzeit_s` | 120 | so lange darf der Start bis zur Erreichbarkeit dauern |
| `anhaltezeit_s` | 20 | so lange darf das Beenden dauern, danach hart |
| `umgebung` | leer | zusätzliche Umgebungsvariablen |
| `umgebung_datei` | keine | Datei mit Zeilen `NAME=WERT`, zum Beispiel die `.env` eines Projekts |
| `pfad` | übliche Systempfade | Suchpfad für Programme |
| `neustart` | ja | nach einem Absturz neu starten, solange der Dienst laufen soll |
| `leitstelle_anhalten` | ja | die Leitstelle darf ihn anhalten, wenn ein Modell den Speicher braucht und er nicht arbeitet; nein: nur hier von Hand |
| `aktiv_ab_prozent` | 5 | ab dieser Prozessorlast (Prozent eines Kerns) gilt er als arbeitend; arbeitende Dienste hält die Leitstelle nicht an |
| `steuerung` | prozess | `prozess`: der Befehl ist der Dienst und läuft, bis er angehalten wird. `befehle`: der Befehl startet etwas und kehrt zurück |
| `pruefbefehl` | keiner | erreichbar heißt: dieser Befehl endet mit 0 |
| `anhaltebefehl` | keiner | hält den Dienst mit einem Befehl an statt per Signal; Pflicht bei `befehle` |
| `prozessmuster` | keines | regulärer Ausdruck auf die Befehlszeile der Prozesse, deren Speicher zählt (bei `befehle`) |
| `braucht` | leer | Kennungen von Diensten, die vorher laufen müssen; sie werden mitgestartet |


## Nur KI-Dienste

Jeder Dienst hat mindestens eine Fähigkeit: Die Leitstelle sieht ihn, kann ihn starten, anhalten und Anfragen über
die Durchleitung an ihn richten. Sie vermittelt nur Fähigkeiten; sie lädt selbst nie ein Modell. Programme ohne
Fähigkeit (Oberflächen und Backends eigener Webapps, ihre Datenbanken, Docker) gehören nicht hierher, sondern ins
Stellwerk; eine solche Datei übergeht der Maschinenraum mit einem Hinweis.

## Betrieb: Steuerprogramme

Neben den KI-Diensten startet, hält an und öffnet der Maschinenraum die Steuerprogramme des Rechners, zuerst das
[Stellwerk](https://github.com/HalloWelt42/stellwerk), das die eigenen Webapps startet. Ein Steuerprogramm trägt sich
bei seiner Installation unter `betrieb/` ein (Felder wie eine Dienstdatei, ohne Fähigkeiten; meist `steuerung =
"befehle"` mit dem Start- und Anhaltebefehl des Systemdienstes). Steuerprogramme sind keine KI: die Leitstelle sieht
sie nie. Im Menüleistensymbol stehen sie unter Betrieb, mit den Webapps des Stellwerks darunter; geschaltet werden
die Webapps beim Stellwerk selbst.

| Aufruf | Wirkung |
|---|---|
| `POST /api/betrieb/<kennung>/starten`, `/anhalten`, `/neustarten` | Steuerprogramm schalten |
| `GET /api/betrieb/<kennung>/protokoll` | Ausgabe der Start- und Anhaltebefehle |

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
| `schlaf` | `melden` | ja | auf dem Mac: beim Einschlafen der Leitstelle melden; Aufträge warten dann in den Apps, bis er wach ist |
| `schlaf` | `leerlauf_aufschieben` | ja | solange die Leitstelle über diesen Rechner rechnen lässt, kein Schlaf nach Leerlauf; Deckel, Menü und Ein-Taste wirken weiter |

## Schlaf des Rechners

Der Maschinenraum erkennt selbst, wann der Mac einschläft und aufwacht (Energieverwaltung von macOS, ohne die
Menüleiste). Vor dem Einschlafen meldet er der Leitstelle `knoten.schlaeft` und schließt die Verbindung; die Leitstelle
lässt Aufträge dann nicht scheitern, sondern sagt den Apps, dass sie warten sollen, bis er wach ist. Nach dem Aufwachen
verbindet er sich sofort neu (bei einem kurzen Erwachen ohne Bildschirm, Power Nap, nicht). Kommt keine Weckmeldung,
gilt er nach zwei Minuten Wachzeit als wach. Schlaf nach Leerlauf schiebt er auf, solange eine Anfrage der Leitstelle
durch ihn läuft (Einstellung `schlaf.leerlauf_aufschieben`).

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
| `GET /api/version` | Fassung des laufenden Programms; weicht sie von der eingebauten ab, lädt die Oberfläche von selbst neu |
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
