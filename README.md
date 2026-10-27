# Maschinenraum

Ein Ort für alle KI-Dienste eines Rechners, die neben einem Modell-Läufer laufen: Sprachsynthese, Spracherkennung,
Bilderzeugung, Musik und was sonst ein Modell hält und eine Fähigkeit anbietet. Statt dass jedes Projekt seine Modelle
irgendwo im Hintergrund lädt, stehen sie hier in einer Liste: was läuft, wie viel Speicher es belegt, starten,
anhalten, neu starten, Protokoll lesen. Dazu der Speicher des ganzen Rechners nach Herkunft.

Der Maschinenraum nimmt nur KI-Dienste an: jede Dienstdatei braucht mindestens eine Fähigkeit. Eigene Webapps, ihre
Datenbanken und Docker verwaltet das [Stellwerk](https://github.com/HalloWelt42/stellwerk); sie nutzen KI nur über die
Leitstelle.

- **Oberfläche im Browser** unter `http://127.0.0.1:8540/`, nur auf diesem Rechner erreichbar.
- **Menüleistensymbol** auf dem Mac: zeigt die KI-Dienste mit Zustand und Speicher und öffnet die Weboberflächen von
  Maschinenraum, Stellwerk und Leitstelle. Geschaltet wird dort, nicht im Symbol: KI-Dienste in der Oberfläche des
  Maschinenraums (oder von der Leitstelle), die Apps allein im Stellwerk.
- **Übersteht Neustarts:** läuft als launchd- oder systemd-Dienst; was laufen soll, startet wieder.
- **Abstürze** werden mit Pausen neu gestartet; stürzt ein Dienst zu oft ab, bleibt er aus.
- **Optional mit Leitstelle:** eine Leitstelle im Netz kann die Dienste mit einplanen, starten und anhalten
  und sieht den echten Speicher dieses Rechners. Ohne sie arbeitet der Maschinenraum genauso.

## Zusammenspiel mit der Leitstelle

Maschinenraum und [Leitstelle](https://github.com/HalloWelt42/leitstelle) gehören zusammen. Die Leitstelle ist die
zentrale Steuerung und Überwachung: sie sorgt dafür, dass Ressourcen nicht überlaufen, verteilt die Arbeit und greift
ein, wo es nötig ist; sie muss dafür nicht jedes Bit durchschleifen. Den Modell-Läufer eines Rechners spricht sie
direkt an. Der Maschinenraum ist je Rechner die zweite Stelle daneben: Er bündelt alle übrigen KI-Modelle und Dienste,
die nicht im Modell-Läufer laufen, etwa die des [Klangwerks](https://github.com/HalloWelt42/klangwerk), meldet sie der
Leitstelle als alternative Anbindung und ist für sich allein bedienbar. Dazu misst er für die Leitstelle, was sie zum
Eingreifen braucht: echten Speicher, Zugriffe am Leitstand vorbei und die Last des Läufers und des Rechners.

```
Webapps (Stellwerk)  ->  Leitstelle  ->  Modell-Läufer      (Sprachmodelle)
                                     ->  Maschinenraum      (übrige KI-Dienste, je Rechner)
```

Starten, Anhalten, Abhängigkeiten, Neustarts, Sollzustand und Prozessmessung teilen sich Maschinenraum und Stellwerk
über den [Dienstkern](https://github.com/HalloWelt42/dienstkern).

Weil die Namen ähnlich klingen, steht neben jedem Namen ein Kurzzweck: Maschinenraum · KI-Dienste, Stellwerk ·
App-Steuerung, Leitstelle · KI-Vermittlung. Beim Maschinenraum stehen Name und Kurzzweck an einer Stelle,
`frontend/marke.ts`; Kopfzeile, Tab-Titel und Manifest der installierten Web-App lesen sie dort. Das Menüleistensymbol
beschriftet jeden Knopf zum Öffnen mit dem Namen, den die Oberfläche in ihrem Manifest (`site.webmanifest`) selbst
nennt, bis dahin mit dem bekannten Namen.

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
| `modelle/` | Modellablage des Rechners: die Modelldateien aller Dienste an einem Ort (siehe unten) |
| `schluessel` | Schlüssel für die Leitstelle, nur für den Benutzer lesbar; jeder Rechner braucht seinen eigenen (in der Leitstelle auf der Karte des Rechners ausgestellt). Einen Ordner mit Schlüssel auf einen zweiten Mac kopieren heißt: beide melden sich als derselbe Rechner und trennen sich gegenseitig |

Neue oder geänderte Dienstdateien liest der Maschinenraum im nächsten Takt; ein Neustart ist nicht nötig. Stand
ohne Oberfläche:

```bash
~/Maschinenraum/.venv/bin/maschinenraum --liste
```

## Modellablage

Alle Modelle außerhalb des Modell-Läufers liegen an einem Ort, `modelle/` im Ordner des Maschinenraums, nach Art
geordnet (`bild/`, `musik/`, `sprache/`) und mit `huggingface/` als Zwischenspeicher von Hugging Face. Jeder Dienst
bekommt dafür zwei Variablen in seine Umgebung:

| Variable | Wert |
|---|---|
| `MASCHINENRAUM_MODELLE` | der Ordner `modelle/`; in der Dienstdatei als `$MASCHINENRAUM_MODELLE` nutzbar |
| `HF_HUB_CACHE` | `modelle/huggingface`: Modelle von Hugging Face landen hier statt in `~/.cache/huggingface` (Anmeldedaten bleiben dort) |

Einträge unter `[umgebung]` in der Dienstdatei gehen vor. Programme, die nicht im Maschinenraum laufen, zeigen mit
einer eigenen Einstellung auf denselben Ordner, damit kein Modell zweimal auf der Platte liegt.

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
| `instanzen` | 1 | so viele Prozesse darf die Leitstelle bei Andrang starten; Instanz n heißt `<kennung>.<n>`, läuft auf `port + 100 (n-1)` und bekommt ihren Port in `MASCHINENRAUM_PORT` (im `befehl` als `$MASCHINENRAUM_PORT`, Pflicht ab 2). Weitere Instanzen folgen der Datei; angehalten sind sie weg, nach einem Neustart des Maschinenraums werden laufende wiedergefunden (siehe unten) |
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
sie nie. Im Menüleistensymbol hat jedes laufende Steuerprogramm mit Oberfläche einen Knopf zum Öffnen; geschaltet
werden Steuerprogramme in der Oberfläche des Maschinenraums, die Apps allein im Stellwerk.

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

Weitere Instanzen (`<kennung>.<n>`) startet die Leitstelle; welche laufen, steht im Sollzustand (`zustand.json`, mit
Prozessgruppe) und an ihren Ports. Beim Start findet der Maschinenraum sie dort wieder: was noch läuft, übernimmt er
(eigene Gruppe, sonst Port, wie bei der Grundinstanz) und meldet es der Leitstelle; was nicht mehr läuft, vergisst er,
ohne es neu zu starten (die Leitstelle startet bei Bedarf); was über der Höchstzahl der Dienstdatei läuft und
nachweislich von ihm stammt (eigene Gruppe), beendet er. Ein fremdes Programm auf dem Port einer solchen Stufe bleibt
unberührt. Erst wenn alles Laufende übernommen ist, beginnt die Beobachtung; vorher hielte sie eigene Dienste für fremd.


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
| `nachbar` | `modell_laeufer` | http://127.0.0.1:1234 | Modell-Läufer auf diesem Rechner: angezeigt und beobachtet (Zugriffe am Leitstand vorbei, Last seiner Prozesse) |
| `beobachtung` | `aktiv` | ja | der Leitstelle melden, was an ihr vorbei auf Modelle dieses Rechners zugreift und wie belastet Läufer und Rechner sind |
| `beobachtung` | `takt_s` | 15 | Abstand der Beobachtungen, eigener Takt neben den Messwerten (von Beginn zu Beginn); zugleich die Frist für die Messung des Docker-Rechners |
| `beobachtung` | `docker` | ja | mit der Last die des Docker-Rechners melden: Kerne, Speicher und je Container Prozessorlast und Speicher |
| `beobachtung` | `schwelle_gb` | 2 | ab so viel Speicher gilt ein Programm außerhalb von Diensten und Läufer als möglicher Modellträger |
| `beobachtung` | `ausnahmen` | Browser, virtuelle Maschinen | Teile der Befehlszeile, die nie als Speicherverbraucher gemeldet werden |
| `beobachtung` | `modelldateien` | .gguf, .safetensors | Endungen von Modelldateien: ein Prozess des Läufers, der eine davon offen hat, ist ein Arbeiter |
| `beobachtung` | `arbeiter_bibliotheken` | /extensions/backends/ | Ordnerteile im Pfad von Bibliotheken eines Rechenwerks: ein Prozess des Läufers, der eine Bibliothek daraus geladen hat, ist ein Arbeiter, auch ohne offene Modelldatei |
| `beobachtung` | `anhaltezeit_s` | 10 | so lange darf ein Arbeiter des Läufers nach der Bitte um Beenden aufräumen, dann wird er hart beendet |
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
plant seinen Speicher ein und hält ihn bei Speichernot wieder an, wenn seine Dienstdatei das erlaubt. Den
Modell-Läufer spricht die Leitstelle direkt an; durch die Durchleitung gehen nur die Dienste des Maschinenraums.

## Am Leitstand vorbei

In eigenem Takt (`beobachtung.takt_s`) meldet der Maschinenraum der Leitstelle (`knoten.fremde`), was an ihr vorbei auf Modelle dieses
Rechners zugreift:

- Verbindungen zum Modell-Läufer, die nicht vom Maschinenraum kommen: ein Programm auf diesem Rechner mit Name,
  Prozess und Arbeitsordner oder eine Adresse im Netz. Ist es die Adresse des Rechners der Leitstelle, steht das dabei
  (meist ist es die Leitstelle selbst, die den Läufer direkt anspricht; das deutet sie selbst).
- Programme mit viel Speicher (ab `beobachtung.schwelle_gb`), die weder Dienst des Maschinenraums noch Teil des Läufers
  sind, etwa ein Bild- oder Sprachmodell im eigenen Prozess. Browser und virtuelle Maschinen stehen in den Ausnahmen.

Gemessen wird mit `lsof` und der Prozesstabelle; ohne `lsof` meldet er, dass er nicht beobachten kann.

## Last des Läufers, des Rechners und des Docker-Rechners

Im selben Takt und aus derselben Aufnahme (ein Aufruf von `ps`, einer von `lsof` am Läufer-Port) meldet der
Maschinenraum der Leitstelle die Last (`knoten.last`). Er misst nur; was daraus folgt, entscheidet die Leitstelle.

- Je Prozess des Läufers (der Prozess am Läufer-Port samt Nachfahren): Name, Rolle, Modelldatei, Prozessorlast und
  Speicher. Rollen: `haupt` lauscht am Port, `arbeiter` ist eine geladene Instanz, `sonstig` ist alles andere, etwa das
  Fenster. Ein Arbeiter hat eine Modelldatei offen (Endungen aus `beobachtung.modelldateien`) oder eine Bibliothek
  eines Rechenwerks geladen (Ordnerteile aus `beobachtung.arbeiter_bibliotheken`, Spalte `txt` von `lsof`). Das zweite
  Merkmal braucht es für Rechenwerke, die das Modell ganz in den Speicher lesen und die Datei danach schließen; bei
  einem solchen Arbeiter bleibt die Modelldatei leer. Beides kommt aus einem Aufruf von `lsof` für alle Läufer-Prozesse.
- Die Fremdlast des Rechners: die Prozessorlast aller übrigen Prozesse, ohne Läufer, ohne Dienste und ohne den
  Maschinenraum selbst, als Anteil aller Kerne. Das ist die Last, die der Mensch und seine übrigen Programme erzeugen;
  drosselt die Leitstelle danach ihre Hintergrundarbeit, schaukelt sie sich nicht an der eigenen Last auf.
- Der Docker-Rechner (`docker`, abschaltbar mit `beobachtung.docker`): seine Kerne und sein Speicher und je laufendem
  Container Name, Compose-Projekt (Label `com.docker.compose.project`), Prozessorlast in Prozent eines Kerns (wie
  `docker stats`) und belegter Speicher. Auf dem Mac laufen die Container in einer virtuellen Maschine, die dort als ein
  einziger Prozess erscheint; was darin welcher Container rechnet, weiß nur Docker. Gemessen wird darum mit
  `docker info`, `docker ps` und `docker stats --no-stream`, nur lesend und nur mit `--format` nach den nötigen Feldern
  (nie die Umgebung der Container). Die drei laufen nebeneinander in einem eigenen Faden neben der Aufnahme und dürfen
  zusammen höchstens einen Takt dauern; `docker stats` braucht ein bis zwei Sekunden, bei voll ausgelastetem
  Docker-Rechner auch vier bis sieben. Ohne Docker, wenn es nicht antwortet oder ein Aufruf scheitert, ist dort
  `gemessen` falsch und die übrigen Felder sagen nichts. Verwaltet wird Docker weiter vom Stellwerk.

Prozessorlast zählt zeitbasiert: verbrauchte Rechenzeit seit der letzten Messung je Wandzeit, beim Läufer in Prozent
eines Kerns. Die erste Messung nach dem Verbinden und neue Prozesse haben noch keinen Wert. Ohne `lsof` oder ohne
eingetragenen Läufer sagt die Liste der Läufer-Prozesse nichts (`gemessen` falsch); ohne `lsof` fehlt auch die
Fremdlast, denn dann ist der Läufer nicht herauszurechnen. Das Feld `docker` ist neu (seit 0.16.0) und darf fehlen:
eine Leitstelle, die es noch nicht kennt, übergeht es.

Auf Befehl der Leitstelle (`laeufer_prozess_beenden` mit der Prozessnummer) beendet der Maschinenraum einen Arbeiter
des Läufers, der ohne Auftrag rechnet. Vorher prüft er frisch, dass der Prozess gerade ein Arbeiter ist; den
Hauptprozess, fremde und verschwundene Prozesse lehnt er ab. Erst die Bitte (SIGTERM), nach
`beobachtung.anhaltezeit_s` hart (SIGKILL); das Ergebnis nennt Name, Modelldatei (wenn er eine offen hat) und Weg.
Der Läufer meldet die Instanz danach als entladen, und die Leitstelle lädt bei Bedarf neu.

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
